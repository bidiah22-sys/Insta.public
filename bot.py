# -*- coding: utf-8 -*-
"""
𝗦𝗠𝗪🚩 𝗚𝗥𝗢𝗨𝗣 𝗖𝗛𝗔𝗧 𝗣𝗥𝗢𝗧𝗘𝗖𝗧𝗜𝗢𝗡 𝗕𝗢𝗧
𝗦𝗠𝗪🚩 Complete Admin-Gated Build v7 — per-message crash isolation and shared-link detection.
Preserves the existing GC features, admin gate, cards and database. Adds defensive shared-link extraction, per-message exception isolation, and bounded backoff
for repeated Instagram 401/403 failures.

Important: client-side handling cannot override Instagram-side access decisions.
Keep session credentials private and persistent.
"""
import os
import re
import unicodedata
import time
from collections import deque
import json
import logging
import shutil
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from importlib.metadata import version as _package_version

from instagrapi import Client
from instagrapi.exceptions import (
    PleaseWaitFewMinutes,
    ClientThrottledError,
    LoginRequired,
    ChallengeRequired,
    BadPassword
)
from sqlalchemy import create_engine, Column, String, Integer, Float, DateTime, Text, ForeignKey, func
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

# -----------------------------------------------------------------
# Set the Instagram session ID below only in a private local copy.
# -----------------------------------------------------------------
# Existing inline session variable copied from the user's previous bot file.
# Hosting environment variables still take priority if configured.
INLINE_SESSION_ID = ""
INSTAGRAM_SESSION_ID = (os.getenv("INSTAGRAM_SESSION_ID", "").strip()
                        or os.getenv("IG_SESSION_ID", "").strip()
                        or INLINE_SESSION_ID.strip())
# Persistent instagrapi settings keep the same device/session identifiers across restarts.
SESSION_SETTINGS_FILE = Path(os.getenv("SESSION_SETTINGS_FILE", "session.json"))
INSTAGRAM_USERNAME = os.getenv("INSTAGRAM_USERNAME", os.getenv("IG_USERNAME", "")).strip()
INSTAGRAM_PASSWORD = os.getenv("INSTAGRAM_PASSWORD", os.getenv("IG_PASSWORD", "")).strip()

BOT_USERNAME = os.getenv("BOT_USERNAME", "bot_hu_yll")
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "")
AUTHORIZED_DEVS = ["fx_smw","aat_nnk25"]
DEV_LINE = "👑 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ 𝗦𝗠𝗪🚩"
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///bot_database.db")
POLL_INTERVAL = max(1, min(60, int(os.getenv("POLL_INTERVAL", "2"))))  # Fast but bounded polling; avoid aggressive API loops
THREAD_SCAN_AMOUNT = max(20, min(500, int(os.getenv("THREAD_SCAN_AMOUNT", "100"))))
TIMEZONE_NAME = os.getenv("TIMEZONE", "Asia/Kolkata")
SEEN_MESSAGE_CACHE_LIMIT = 5000
LOCAL_AUTO_REPLIES = True
DEVELOPER_DISPLAY = "𝗦𝗠𝗪🚩"
SAFE_MODE = os.getenv("SAFE_MODE", "1").lower() in {"1", "true", "yes", "on"}
STARTED_AT = time.time()
TOTAL_SEEN_MESSAGES = 0
LAST_SUCCESSFUL_POLL = None
LAST_POLL_ERROR = "None"
# Instagram item_ack 403 is not reliably recoverable client-side; pause outgoing sends
# without logging out or stopping read/poll processing.
SEND_COOLDOWN_UNTIL = 0.0
AUTH_FAILURE_COUNT = 0
SEND_COOLDOWN_SECONDS = max(300, min(1800, int(os.getenv("IG_403_SEND_COOLDOWN_SECONDS", "900"))))
LAST_ITEM_ACK_LOG_AT = 0.0
ITEM_ACK_LOG_INTERVAL = max(60, min(3600, int(os.getenv("IG_403_LOG_INTERVAL_SECONDS", "300"))))
logging.basicConfig(filename="bot_runtime.log", level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def _item_ack_403_signature(exc):
    """Return True only for the specific observed Instagram item_ack 403 signature."""
    try:
        http_status, api_status_code, error_code, action = _instagram_error_signature(exc)
        return (http_status == 403 or api_status_code == 403) and action == "item_ack" and error_code == 1404006
    except Exception:
        return False


def _pause_after_item_ack_403(exc, operation, thread_id=None):
    """Apply a global outgoing-send cooldown and rate-limit duplicate diagnostics."""
    global SEND_COOLDOWN_UNTIL, LAST_POLL_ERROR, LAST_ITEM_ACK_LOG_AT
    now = time.time()
    SEND_COOLDOWN_UNTIL = max(SEND_COOLDOWN_UNTIL, now + SEND_COOLDOWN_SECONDS)
    LAST_POLL_ERROR = f"Instagram item_ack 403/1404006 during {operation}; sends paused"
    if now - LAST_ITEM_ACK_LOG_AT >= ITEM_ACK_LOG_INTERVAL:
        LAST_ITEM_ACK_LOG_AT = now
        logging.warning(
            "instagram_item_ack_403 operation=%s thread_id=%s cooldown_seconds=%s exception=%s",
            operation, str(thread_id) if thread_id is not None else "unknown",
            SEND_COOLDOWN_SECONDS, type(exc).__name__
        )
        print(
            f"[!] Instagram returned item_ack 403/1404006 during {operation}. "
            f"Outgoing sends paused for {SEND_COOLDOWN_SECONDS}s; duplicate warnings are rate-limited. "
            "No automatic login or message resend will be attempted."
        )
    return False

SHADOWBANNED_USERS = set()
TARGETED_USERS = set()
LOCKDOWN_MODE = False
USER_LAST_MESSAGE_TIME = {}
ANTISPAM_ENABLED = True
ANTISPAM_LIMIT = 3


def fix_mention(username: str) -> str:
    if not username:
        return ""
    clean_name = str(username).strip().lstrip("@")
    return f"@{clean_name}" if clean_name else ""


def get_admin_mentions_str(users: list, gc_admins: list) -> str:
    admin_ids_str = {str(x) for x in gc_admins}
    admin_mentions = []
    for u in users:
        u_pk = str(getattr(u, "pk", ""))
        if u_pk in admin_ids_str:
            uname = getattr(u, "username", None)
            if uname:
                admin_mentions.append(fix_mention(uname))
    return " ".join(admin_mentions) if admin_mentions else "@Admins"


SPAM_USERNAME_PATTERNS = [
    r"bot[0-9_\.]*",
    r"crypto[0-9_\.]*",
    r"promo[0-9_\.]*",
    r"followers[0-9_\.]*",
    r"18plus",
    r"adult",
    r"earn_money",
    r"trader[0-9_\.]*",
]

BAD_WORD_PATTERNS = [
    r"\bm[\.\_\-\s]*c\b",
    r"\bb[\.\_\-\s]*c\b",
    r"\bm[\.\_\-\s]*k[\.\_\-\s]*c\b",
    r"\bt[\.\_\-\s]*m[\.\_\-\s]*k[\.\_\-\s]*c\b",
    r"madar\s*chod",
    r"bhen\s*chod",
    r"behen\s*chod",
    r"bhosd\w*",
    r"chut\w*",
    r"gand\w*",
    r"gaand\w*",
    r"lund\w*",
    r"lauda\w*",
    r"lawda\w*",
    r"randi\w*",
    r"bhadwa\w*",
    r"bhadwe\w*",
    r"bsdk\w*",
    r"harami\w*",
    r"f[\.\_\-\s]*u[\.\_\-\s]*c[\.\_\-\s]*k\w*",
]

RESTRICTED_WORDS = set([
    "mc", "bc", "mkc", "tmkc", "bsdk", "bsdke", "chutiya", "chutiye", "chutiyap",
    "gandu", "gaandu", "lauda", "luda", "lawda", "lund", "chut", "chuth",
    "gand", "gaand", "randi", "randwa", "bhadwa", "bhadwe", "harami", "haramkhor",
    "kamine", "kamina", "saala", "saale", "madarchod", "maderchod", "madar-chod",
    "bhenchod", "behenchod", "bhen-chod", "behen-chod", "bhosdike", "bhosdi",
    "bhosda", "fuck", "fucking", "fucker", "motherfucker", "bitch", "bastard", "asshole"
])

Base = declarative_base()


def get_utc_now():
    return datetime.now(timezone.utc)


class UserProfile(Base):
    __tablename__ = "user_profiles"
    user_id = Column(String, primary_key=True)
    username = Column(String, nullable=False)
    join_date = Column(DateTime, default=get_utc_now)
    last_active = Column(DateTime, default=get_utc_now)
    total_messages = Column(Integer, default=0)
    warning_count = Column(Integer, default=0)
    violation_count = Column(Integer, default=0)
    trust_score = Column(Float, default=100.0)


class GroupAnalytics(Base):
    __tablename__ = "group_analytics"
    group_id = Column(String, primary_key=True)
    group_name = Column(String, nullable=False, default="Unknown GC")
    observed_members = Column(Integer, default=0)
    message_count = Column(Integer, default=0)
    first_seen = Column(DateTime, default=get_utc_now)
    last_activity = Column(DateTime, default=get_utc_now)


class GroupMemberAnalytics(Base):
    __tablename__ = "group_member_analytics"
    group_id = Column(String, primary_key=True)
    user_id = Column(String, primary_key=True)
    username = Column(String, nullable=False, default="User")
    message_count = Column(Integer, default=0)
    first_seen = Column(DateTime, default=get_utc_now)
    last_activity = Column(DateTime, default=get_utc_now)


class BotSetting(Base):
    __tablename__ = "bot_settings"
    key = Column(String, primary_key=True)
    value = Column(Text, nullable=False, default="")


class SecurityLog(Base):
    __tablename__ = "security_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=get_utc_now)
    group_id = Column(String)
    username = Column(String)
    event_type = Column(String)
    details = Column(Text)


engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)


def init_db():
    Base.metadata.create_all(engine)


def save_setting(key: str, value: str):
    db = SessionLocal()
    try:
        row = db.query(BotSetting).filter(BotSetting.key == key).first()
        if row is None:
            row = BotSetting(key=key, value=str(value))
            db.add(row)
        else:
            row.value = str(value)
        db.commit()
    except Exception:
        db.rollback()
        logging.exception("setting_save_failed key=%s", key)
    finally:
        db.close()


def load_setting(key: str, default: str = "") -> str:
    db = SessionLocal()
    try:
        row = db.query(BotSetting).filter(BotSetting.key == key).first()
        return row.value if row else default
    finally:
        db.close()


def save_runtime_state():
    save_setting("targets", json.dumps(sorted(TARGETED_USERS)))
    save_setting("shadowbans", json.dumps(sorted(SHADOWBANNED_USERS)))
    save_setting("lockdown", "1" if LOCKDOWN_MODE else "0")
    save_setting("antispam_enabled", "1" if ANTISPAM_ENABLED else "0")
    save_setting("antispam_limit", str(ANTISPAM_LIMIT))


def restore_runtime_state():
    global LOCKDOWN_MODE, ANTISPAM_ENABLED, ANTISPAM_LIMIT
    try:
        TARGETED_USERS.update(str(x).casefold() for x in json.loads(load_setting("targets", "[]")))
        SHADOWBANNED_USERS.update(str(x).casefold() for x in json.loads(load_setting("shadowbans", "[]")))
    except Exception:
        logging.exception("runtime_list_restore_failed")
    LOCKDOWN_MODE = load_setting("lockdown", "0") == "1"
    ANTISPAM_ENABLED = load_setting("antispam_enabled", "1") == "1"
    try:
        ANTISPAM_LIMIT = max(2, min(10, int(load_setting("antispam_limit", "3"))))
    except ValueError:
        ANTISPAM_LIMIT = 3


def load_custom_commands() -> dict:
    """Load safe text-only custom replies from the existing settings table."""
    try:
        data = json.loads(load_setting("custom_commands", "{}"))
        if not isinstance(data, dict):
            return {}
        return {str(k).casefold().lstrip("!"): str(v)[:1200] for k, v in data.items()
                if str(k).strip() and isinstance(v, str)}
    except Exception:
        logging.exception("custom_commands_load_failed")
        return {}


def save_custom_commands(commands: dict) -> None:
    save_setting("custom_commands", json.dumps(commands, ensure_ascii=False))


def record_group_snapshot(group_id: str, group_name: str, users: list):
    db = SessionLocal()
    try:
        row = db.query(GroupAnalytics).filter_by(group_id=str(group_id)).first()
        if row is None:
            row = GroupAnalytics(group_id=str(group_id), group_name=group_name or "Unknown GC")
            db.add(row)
        else:
            row.group_name = group_name or row.group_name or "Unknown GC"
        row.observed_members = len({str(getattr(u, "pk", "")) for u in users if getattr(u, "pk", None)})
        row.last_activity = get_utc_now()
        db.commit()
    except Exception:
        db.rollback(); logging.exception("group_snapshot_failed")
    finally:
        db.close()


def record_group_message(group_id: str, group_name: str, user_id: str, username: str):
    db = SessionLocal()
    try:
        group = db.query(GroupAnalytics).filter_by(group_id=str(group_id)).first()
        if group is None:
            group = GroupAnalytics(group_id=str(group_id), group_name=group_name or "Unknown GC", message_count=0)
            db.add(group)
        group.group_name = group_name or group.group_name or "Unknown GC"
        group.message_count = (group.message_count or 0) + 1
        group.last_activity = get_utc_now()
        member = db.query(GroupMemberAnalytics).filter_by(group_id=str(group_id), user_id=str(user_id)).first()
        if member is None:
            member = GroupMemberAnalytics(group_id=str(group_id), user_id=str(user_id), username=username or "User", message_count=0)
            db.add(member)
        member.username = username or member.username
        member.message_count = (member.message_count or 0) + 1
        member.last_activity = get_utc_now()
        db.commit()
    except Exception:
        db.rollback(); logging.exception("group_message_record_failed")
    finally:
        db.close()


def group_report(db, group_id: str, group_name: str) -> str:
    group = db.query(GroupAnalytics).filter_by(group_id=str(group_id)).first()
    members = db.query(GroupMemberAnalytics).filter_by(group_id=str(group_id)).count()
    messages = group.message_count if group else 0
    observed = group.observed_members if group else 0
    return (f"📊 𝗚𝗖 𝗟𝗜𝗩𝗘 𝗔𝗡𝗔𝗟𝗬𝗧𝗜𝗖𝗦\n\n"
            f"🏷️ 𝗚𝗖 𝗡𝗔𝗠𝗘 ➜ {group_name or (group.group_name if group else 'Unknown GC')}\n"
            f"🆔 𝗚𝗖 / 𝗧𝗛𝗥𝗘𝗔𝗗 𝗜𝗗 ➜ `{group_id}`\n"
            f"👥 𝗖𝗨𝗥𝗥𝗘𝗡𝗧 𝗢𝗕𝗦𝗘𝗥𝗩𝗘𝗗 𝗠𝗘𝗠𝗕𝗘𝗥𝗦 ➜ {observed}\n"
            f"🧾 𝗠𝗘𝗠𝗕𝗘𝗥𝗦 𝗪𝗜𝗧𝗛 𝗠𝗘𝗦𝗦𝗔𝗚𝗘 𝗛𝗜𝗦𝗧𝗢𝗥𝗬 ➜ {members}\n"
            f"💬 𝗠𝗘𝗦𝗦𝗔𝗚𝗘𝗦 𝗥𝗘𝗖𝗢𝗥𝗗𝗘𝗗 𝗕𝗬 𝗕𝗢𝗧 ➜ {messages}\n\n"
            f"👑 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ 𝗦𝗠𝗪🚩")


class SpamAnalyzer:
    @staticmethod
    def is_spam_profile(cl: Client, username: str) -> tuple:
        try:
            u_info = cl.user_info_by_username(username)
            risk = 0
            reasons = []

            u_lower = username.lower()
            for pattern in SPAM_USERNAME_PATTERNS:
                if re.search(pattern, u_lower):
                    risk += 40
                    reasons.append("Suspicious Username Pattern")
                    break

            bio = (u_info.biography or "").lower()
            if any(w in bio for w in ["whatsapp", "telegram", "free followers", "crypto", "dm for paid", "18+"]):
                risk += 35
                reasons.append("Spam Bio Content")

            if u_info.follower_count < 10 and u_info.following_count > 200:
                risk += 30
                reasons.append("Abnormal Following Ratio")

            is_spam = risk >= 50
            reason_str = ", ".join(reasons) if reasons else "Clean Profile"
            return is_spam, reason_str, min(risk, 100), u_info
        except Exception:
            return False, "Could not scan", 0, None


class ModerationEngine:
    @staticmethod
    def record_activity(user_id: str, username: str):
        db = SessionLocal()
        try:
            profile = db.query(UserProfile).filter(UserProfile.user_id == str(user_id)).first()
            if not profile:
                profile = UserProfile(
                    user_id=str(user_id),
                    username=username.lower(),
                    total_messages=1,
                    trust_score=100.0,
                    warning_count=0,
                    violation_count=0
                )
                db.add(profile)
            else:
                profile.username = username.lower()
                profile.total_messages = (profile.total_messages or 0) + 1
                profile.last_active = get_utc_now()
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    @staticmethod
    def add_warning(username: str) -> tuple:
        db = SessionLocal()
        try:
            clean_user = username.lstrip("@").lower()
            profile = db.query(UserProfile).filter(UserProfile.username == clean_user).first()
            if profile:
                profile.warning_count = (profile.warning_count or 0) + 1
                profile.violation_count = (profile.violation_count or 0) + 1
                profile.trust_score = max(0.0, profile.trust_score - 25.0)
                db.commit()
                return profile.warning_count, profile.trust_score
            return 1, 75.0
        finally:
            db.close()

    @staticmethod
    def reset_warnings(username: str):
        db = SessionLocal()
        try:
            clean_user = username.lstrip("@").lower()
            profile = db.query(UserProfile).filter(UserProfile.username == clean_user).first()
            if profile:
                profile.warning_count = 0
                db.commit()
        finally:
            db.close()

    @staticmethod
    def get_user_stats(cl: Client, username: str) -> str:
        db = SessionLocal()
        try:
            clean_user = username.lstrip("@").lower()
            profile = db.query(UserProfile).filter(UserProfile.username == clean_user).first()

            if profile:
                score = int(profile.trust_score)
                filled = score // 10
                bar = "█" * filled + "░" * (10 - filled)

                return (
                    f"📊 **𝗨𝗦𝗘𝗥 𝗦𝗧𝗔𝗧𝗦 𝗙𝗢𝗥 {fix_mention(profile.username)}**\n\n"
                    f"🆔 **𝗨𝗦𝗘𝗥 𝗜𝗗** ➜ `{re.sub(r'\\D', '', str(profile.user_id))}`\n"
                    f"💬 **𝗧𝗢𝗧𝗔𝗟 𝗠𝗦𝗚𝗦** ➜ {profile.total_messages}\n"
                    f"⚠️ **𝗪𝗔𝗥𝗡𝗜𝗡𝗚𝗦** ➜ {profile.warning_count}/3\n"
                    f"🚫 **𝗩𝗜𝗢𝗟𝗔𝗧𝗜𝗢𝗡𝗦** ➜ {profile.violation_count}\n"
                    f"💎 **𝗧𝗥𝗨𝗦𝗧 𝗦𝗖𝗢𝗥𝗘** ➜ {profile.trust_score}%\n"
                    f"📈 **𝗦𝗖𝗢𝗥𝗘 𝗕𝗔𝗥** ➜ [{bar}]\n\n"
                    f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                    f"👑 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ 𝗦𝗠𝗪🚩"
                )
            return f"❌ User {fix_mention(clean_user)} is not registered in Database!"
        finally:
            db.close()

    @staticmethod
    def log_event(group_id: str, username: str, event_type: str, details: str):
        db = SessionLocal()
        try:
            log = SecurityLog(group_id=group_id, username=username, event_type=event_type, details=details)
            db.add(log)
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()


# Explicit profanity list. Matching is boundary-aware to avoid false positives such as
# ordinary names/phrases that merely contain a short character sequence.
ABUSIVE_TERMS = [
    # Explicit Romanized Hindi / Hinglish profanity and common spellings.
    "madarchod", "madar chod", "maderchod", "madarchood", "maa chod", "ma chod",
    "behenchod", "bhenchod", "behen chod", "bhen chod", "bhen ke lode", "maa ke lode", "ma ke lode",
    "bhosdike", "bhosdi ke", "bhosdika", "bhosda", "bhosdi", "bhosadike", "bhosadika",
    "chutiya", "chutiye", "chutiyap", "chutiapa", "chutmarika", "chutmarani", "chut ka",
    "gandu", "gaandu", "gandua", "gaand mara", "gand mara", "gaandfat", "gandfat", "gandfattu", "gaandfattu",
    "lund", "lauda", "lawda", "loda", "lodu", "lode", "lund fakir", "lund le",
    "randi", "randwa", "randibaaz", "raand", "bhadwa", "bhadwe", "bhadwi", "haramkhor", "haraamkhor",
    "teri maa ki", "teri bahan ki", "teri behen ki", "teri gaand", "teri gand", "teri mkc", "tmkc", "bsdk", "bkl",
    "jhatu", "jhaatu", "gaand mein", "gaand me", "gaand maar", "gaand marao", "gaand phaad",
    # Common Devanagari-script variants of explicit Hindi profanity.
    "मादरचोद", "मादर चोद", "बहनचोद", "बहन चोद", "भोसड़ीके", "भोसड़ी के", "चूतिया",
    "गांडू", "लंड", "रंडी", "हरामी", "हरामखोर", "कमीना", "कमीने",
    # Explicit English profanity and direct vulgar insults.
    "fuck", "fucking", "fucked", "fucker", "fuckers", "motherfucker", "motherfuckers", "bullshit",
    "shithead", "shitface", "shit", "shitty", "bitch", "bitches", "bastard", "bastards", "asshole", "assholes",
    "dickhead", "dickheads", "dickwad", "prick", "piss off", "son of a bitch", "slut", "sluts", "whore", "whores",
    "cunt", "cunts", "twat", "wanker", "wankers", "dumbass", "jackass", "dipshit", "arsehole", "arse",
    # Compound insults that are unambiguously abusive.
    "stupid bastard", "fat bitch", "dirty bitch", "piece of shit", "fuck off", "go fuck yourself",
]

# Build patterns that allow punctuation/spacing between letters while requiring word boundaries.
def _abuse_pattern(term: str) -> re.Pattern:
    words = [w for w in re.split(r"\s+", term.casefold().strip()) if w]
    body = r"\s+".join(r"[\W_]*".join(re.escape(ch) for ch in word) for word in words)
    return re.compile(r"(?<![\w])" + body + r"(?![\w])", re.IGNORECASE | re.UNICODE)

_ABUSE_PATTERNS = [(term, _abuse_pattern(term)) for term in ABUSIVE_TERMS]


def normalize_for_moderation(text: str) -> str:
    """Normalize Unicode and zero-width characters for consistent text checks."""
    text = unicodedata.normalize("NFKC", text or "").casefold()
    text = re.sub(r"[\u200b-\u200f\ufeff\u202a-\u202e]", "", text)
    return text


def detect_abuse_reason(text: str) -> str | None:
    """Return a reason only for an explicit abusive term, not ordinary substrings."""
    raw = normalize_for_moderation(text)
    if not raw.strip():
        return None
    for term, pattern in _ABUSE_PATTERNS:
        match = pattern.search(raw)
        if match:
            # Show the actual text that triggered the detector in the warning card.
            detected = re.sub(r"\s+", " ", match.group(0)).strip()
            return f"Matched abusive term: {detected}"
    return None


def detect_link_type(text: str) -> str | None:
    """Fail-safe URL detector. Malformed/unusual message data never escapes this function."""
    try:
        value = unicodedata.normalize("NFKC", str(text or "")).casefold()
        value = re.sub(r"[\u200b-\u200f\ufeff\u202a-\u202e]", "", value).strip()
        if not value:
            return None
        probe = value
        probe = re.sub(r"(?i)hxxps?\s*:\s*/\s*/", "https://", probe)
        probe = re.sub(r"(?i)\b(h\s*t\s*t\s*p)\s*:\s*/\s*/", r"http://", probe)
        probe = re.sub(r"(?i)\s*(?:\[\s*dot\s*\]|\(\s*dot\s*\)|\{\s*dot\s*\})\s*", ".", probe)
        probe = re.sub(r"\s*\[\s*\.\s*\]\s*", ".", probe)
        probe = re.sub(r"(?i)([a-z0-9-])\s+dot\s+([a-z]{2,63})(?=[:/\s?#]|$)", r"\1.\2", probe)
        # URLs, domains (including unfamiliar TLDs), IP URLs, and common obfuscations.
        explicit = re.compile(r"(?<![\w@])(?:https?://|ftp://|www\.)[^\s<>\"']+", re.I)
        domain = re.compile(r"(?<![\w@])(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}(?::\d{1,5})?(?:[/\?#][^\s<>\"']*)?", re.I)
        ip_url = re.compile(r"(?<![\w@])(?:https?://)?(?:\d{1,3}\.){3}\d{1,3}(?::\d{1,5})?(?:[/\?#][^\s<>\"']*)?", re.I)
        obfuscated = re.compile(r"(?<!\w)h\s*t\s*t\s*p\s*(?::|：)\s*/\s*/|(?<!\w)w\s*w\s*w\s*\.", re.I)
        if not (explicit.search(probe) or domain.search(probe) or ip_url.search(probe) or obfuscated.search(probe)):
            return None
        if re.search(r"(?:instagram\.com|instagr\.am)/(?:reel|reels)(?:/|\b)", probe, re.I):
            return "Instagram Reel Link"
        if re.search(r"(?:instagram\.com|instagr\.am)/(?:p|tv)/", probe, re.I):
            return "Instagram Post / Video Link"
        if re.search(r"(?:instagram\.com|instagr\.am)/(?:channels?|broadcast|direct)/", probe, re.I):
            return "Instagram Channel / Broadcast Link"
        return "External Link"
    except Exception:
        logging.exception("link_detector_error")
        return None


def get_message_detection_text(message, plain_text: str = "") -> str:
    """Safely extract link-bearing fields from ordinary and shared-link message payloads."""
    parts = []
    seen = set()
    def add(value):
        try:
            if isinstance(value, str):
                item = value.strip()
                if item and item not in seen:
                    seen.add(item)
                    parts.append(item)
        except Exception:
            pass
    add(plain_text)
    keys = {"url", "href", "link", "weburi", "web_uri", "caption", "title", "text", "share_url", "permalink", "shortcode"}
    def walk(obj, depth=0):
        if depth > 5 or obj is None:
            return
        try:
            if isinstance(obj, str):
                # Avoid treating arbitrary huge serialized blobs as message text.
                if len(obj) <= 10000:
                    add(obj)
                return
            if isinstance(obj, dict):
                for key, val in obj.items():
                    if str(key).casefold() in keys:
                        if isinstance(val, str): add(val)
                        elif isinstance(val, (dict, list, tuple)): walk(val, depth + 1)
                    elif isinstance(val, (dict, list, tuple)):
                        walk(val, depth + 1)
                return
            if isinstance(obj, (list, tuple)):
                for item in obj[:100]: walk(item, depth + 1)
                return
            # Only inspect known message containers; avoid walking arbitrary client objects.
            for field in ("link", "url", "href", "caption", "title", "text", "extra", "share", "media", "clip", "reel", "item", "payload", "message"):
                try:
                    val = getattr(obj, field, None)
                    if isinstance(val, str): add(val)
                    elif isinstance(val, (dict, list, tuple)): walk(val, depth + 1)
                except Exception:
                    continue
            try:
                data = obj.dict()
                if isinstance(data, dict): walk(data, depth + 1)
            except Exception:
                pass
        except Exception:
            logging.debug("shared_link_field_extract_skipped", exc_info=True)
    walk(message)
    return " ".join(parts)


def _instagram_error_signature(exc):
    """Extract a minimal error signature from response JSON or serialized exception text."""
    response = getattr(exc, "response", None)
    body = {}
    if response is not None:
        try:
            parsed = response.json()
            if isinstance(parsed, dict):
                body = parsed
        except Exception:
            body = {}

    # Some instagrapi exceptions preserve the API body in str(exc) but expose no response.
    # Parse only the known fields; never log cookies, headers, or session identifiers.
    if not body:
        raw = str(exc)
        try:
            start = raw.find("{")
            end = raw.rfind("}")
            if start >= 0 and end > start:
                candidate = json.loads(raw[start:end + 1])
                if isinstance(candidate, dict):
                    body = candidate
        except Exception:
            body = {}

    payload = body.get("payload") if isinstance(body.get("payload"), dict) else {}
    try:
        http_status = int(getattr(response, "status_code", 0) or 0)
    except Exception:
        http_status = 0
    try:
        api_status_code = int(body.get("status_code", 0) or 0)
    except Exception:
        api_status_code = 0
    # Instagram's item_ack payload has appeared with error_code at the top level,
    # while some wrappers may nest it inside payload. Check both shapes.
    try:
        error_code = int(body.get("error_code", payload.get("error_code", 0)) or 0)
    except Exception:
        try:
            error_code = int(payload.get("error_code", 0) or 0)
        except Exception:
            error_code = 0
    action = body.get("action") if body.get("action") == "item_ack" else ""
    # If status code is embedded only in the serialized body, retain it above.
    return http_status, api_status_code, error_code, action


def start_bot():
    global LOCKDOWN_MODE, SHADOWBANNED_USERS, TARGETED_USERS, USER_LAST_MESSAGE_TIME, SAFE_MODE, ANTISPAM_ENABLED, ANTISPAM_LIMIT, SEND_COOLDOWN_UNTIL, AUTH_FAILURE_COUNT
    init_db()
    restore_runtime_state()

    while True:
        try:
            try:
                installed_instagrapi = _package_version("instagrapi")
            except Exception:
                installed_instagrapi = "unknown"
            print(f"[*] Connecting to Instagram... (instagrapi={installed_instagrapi})")
            logging.info("startup_instagram_library_version=%s", installed_instagrapi)
            cl = Client()
            # Reuse saved device/session settings when available. The file must live on
            # persistent storage (for example, a Railway Volume) to survive redeploys.
            login_error = None
            session_id = INSTAGRAM_SESSION_ID.strip()
            has_session_id = bool(session_id) and session_id not in {
                "PASTE_YOUR_SESSION_ID_HERE", "PASTE_YOUR_NEW_SESSION_ID_HERE", "YOUR_SESSION_ID_HERE"
            }
            has_credentials = bool(INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD)

            # First try the provided Session ID, preserving the user's existing login path.
            if has_session_id:
                try:
                    cl.login_by_sessionid(session_id)
                    logging.info("instagram_session_id_login_succeeded")
                    print("[+] Successfully logged in via Session ID!")
                except Exception as exc:
                    login_error = exc
                    logging.exception("instagram_session_id_login_failed")
                    print(f"[!] Session ID login failed: {type(exc).__name__}: {exc}")
                    if not has_credentials:
                        raise RuntimeError(
                            "Session ID login failed and username/password Variables are not both set. "
                            f"Original error: {type(exc).__name__}: {exc}"
                        ) from exc
                    # Use a fresh client for fallback, so failed Session ID cookies do not leak in.
                    print("[*] Trying username/password recovery login...")
                    # Use a fresh default Client for credential recovery. Older session.json
                    # files can carry obsolete Instagram app/device metadata and trigger
                    # needs_upgrade even when the installed instagrapi is current.
                    cl = Client()
                    cl.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
                    logging.info("instagram_credential_fallback_login_succeeded")
                    print("[+] Successfully recovered login with configured credentials!")
            elif has_credentials:
                # No Session ID: reuse saved settings/device identifiers, then authenticate.
                if SESSION_SETTINGS_FILE.exists():
                    try:
                        # Preserve stable device identifiers but refresh obsolete app metadata.
                        cl.load_settings(str(SESSION_SETTINGS_FILE), override_app_version=True)
                        logging.info("saved_instagram_session_settings_loaded_with_current_app_profile")
                    except TypeError:
                        # Compatibility fallback for older instagrapi releases.
                        try:
                            cl.load_settings(str(SESSION_SETTINGS_FILE))
                            logging.info("saved_instagram_session_settings_loaded")
                        except Exception:
                            logging.exception("saved_instagram_session_settings_load_failed")
                    except Exception:
                        logging.exception("saved_instagram_session_settings_load_failed")
                cl.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
                logging.info("instagram_login_succeeded_with_credentials")
                print("[+] Successfully logged in with configured credentials!")
            else:
                raise RuntimeError(
                    "No usable login credentials found. Set INSTAGRAM_SESSION_ID, or set both "
                    "INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD in hosting Variables."
                )

            # Persist refreshed cookies/device settings after every successful login.
            try:
                SESSION_SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
                cl.dump_settings(str(SESSION_SETTINGS_FILE))
                logging.info("instagram_session_settings_saved path=%s", SESSION_SETTINGS_FILE)
                print(f"[+] Session settings saved to {SESSION_SETTINGS_FILE}")
            except Exception:
                logging.exception("instagram_session_settings_save_failed")
                print("[!] Warning: could not save session settings; check persistent-volume path/permissions.")

            print("\n╔══════════════════════════════════════╗")
            print("║       ✦  𝗦𝗠𝗪  𝗕𝗢𝗧  ✦             ║")
            print("║       STATUS: CONNECTED              ║")
            print("║   Group scan loop: STARTING          ║")
            print("╚══════════════════════════════════════╝\n")
            AUTH_FAILURE_COUNT = 0
            print(f"[+] BOT @{BOT_USERNAME} logged in; polling every {POLL_INTERVAL}s; scanning up to {THREAD_SCAN_AMOUNT} recent threads per poll.")
            print("[i] 𝗦𝗠𝗪🚩 Admin-gated mode enabled. Instagram 403s are handled with cooldowns; they cannot be bypassed locally.")

            seen_message_ids = set()
            seen_message_order = deque()
            group_members_state = {}
            ever_seen_members = set()
            member_name_cache = {}
            username_by_id_cache = {}
            welcomed_recently = {}
            recent_sent_texts = {}
            user_message_windows = {}
            duplicate_message_windows = {}
            active_announced_threads = set()
            initialized_message_threads = set()

            # Schedule state is stored per GC/date so every GC gets its own daily greeting.
            is_first_run = True

            def apply_smw_font(text_content):
                """Apply the SMW bold Unicode style to plain English text while preserving links, handles and IDs."""
                bold_map = str.maketrans(
                    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789",
                    "𝗔𝗕𝗖𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝗫𝗬𝗭𝗮𝗯𝗰𝗱𝗲𝗳𝗴𝗵𝗶𝗷𝗸𝗹𝗺𝗻𝗼𝗽𝗾𝗿𝘀𝘁𝘂𝘃𝘄𝘅𝘆𝘇𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵"
                )
                protected = re.compile(r"𝗦𝗠𝗪🚩\s*![A-Za-z0-9_]+|![A-Za-z0-9_]+|https?://[^\s]+|www\.[^\s]+|@[A-Za-z0-9._]+|`[^`]*`", re.IGNORECASE)
                chunks = []
                last = 0
                for match in protected.finditer(str(text_content)):
                    chunks.append(str(text_content)[last:match.start()].translate(bold_map))
                    chunks.append(match.group(0))
                    last = match.end()
                chunks.append(str(text_content)[last:].translate(bold_map))
                return "".join(chunks)

            def safe_send_message(thread_id, text_content):
                global SEND_COOLDOWN_UNTIL, LAST_POLL_ERROR
                # If Instagram is rejecting item_ack writes, do not hammer the same endpoint.
                # Continue polling/read-only processing while outgoing replies are paused.
                if time.time() < SEND_COOLDOWN_UNTIL:
                    return False
                # Keep all bot-facing English replies/cards in the consistent SMW bold font.
                # Links, Instagram @mentions, and backtick-wrapped IDs are preserved verbatim.
                footer = "👑 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ 𝗦𝗠𝗪🚩"
                text_content = apply_smw_font(str(text_content))
                footer_patterns = (
                    r"(?im)^.*(?:DEV(?:ELOPER)?\s*(?:➜|:|—|-)?\s*SMW|SMW\s+DEVELOPER|DEVELOPER\s*➜\s*SMW).*?$",
                    r"(?im)^.*👑\s*𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥.*𝗦𝗠𝗪🚩.*?$",
                )
                for pattern in footer_patterns:
                    text_content = re.sub(pattern, "", text_content)
                text_content = text_content.rstrip() + "\n\n" + footer
                current_time = time.time()
                if thread_id in recent_sent_texts:
                    last_text, last_time = recent_sent_texts[thread_id]
                    if last_text == text_content and (current_time - last_time < 2):
                        return True
                try:
                    cl.direct_send(text_content, thread_ids=[thread_id])
                    recent_sent_texts[thread_id] = (text_content, current_time)
                    return True
                except Exception as e:
                    http_status, api_status_code, error_code, action = _instagram_error_signature(e)
                    if (http_status == 403 or api_status_code == 403) and action == "item_ack" and error_code == 1404006:
                        _pause_after_item_ack_403(e, "direct_send", thread_id)
                    else:
                        logging.exception("direct_send_failed thread_id=%s error_type=%s", str(thread_id), type(e).__name__)
                        print(f"[!] Send error ({type(e).__name__}); details saved in bot_runtime.log")
                    return False
                # No artificial delay after send; polling interval controls API request rate.

            def execute_kick(thread_id, target_pk, target_username, reason, silent=False):
                try:
                    if SAFE_MODE:
                        ModerationEngine.log_event(thread_id, target_username, "SAFE_MODE_REVIEW", reason)
                        if not silent:
                            safe_send_message(thread_id, f"🛡️ Safe mode: proposed removal for @{target_username} was not executed. Reason: {reason}. Admin review required.")
                        return
                    cl.user_remove_from_thread(thread_id, target_pk)
                    ModerationEngine.log_event(thread_id, target_username, "AUTO-KICK", reason)

                    if not silent:
                        kick_card = (
                            f"🚨🚪 **𝗔𝗨𝗧𝗢-𝗞𝗜𝗖𝗞 𝗘𝗫𝗘𝗖𝗨𝗧𝗘𝗗!**\n\n"
                            f"👤 𝗢𝗙𝗙𝗘𝗡𝗗𝗘𝗥 ➜ {fix_mention(target_username)}\n"
                            f"🆔 𝗨𝗦𝗘𝗥 𝗜𝗗  ➜ `{target_pk}`\n"
                            f"🚫 𝗥𝗘𝗔𝗦𝗢𝗡   ➜ {reason}\n"
                            f"🛑 𝗔𝗖𝗧𝗜𝗢𝗡   ➜ REMOVED FROM GC PERMANENTLY!\n\n"
                            f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                            f"👑 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ 𝗦𝗠𝗪🚩"
                        )
                        safe_send_message(thread_id, kick_card)
                except Exception:
                    pass

            # Consecutive 403/forbidden errors use a bounded exponential backoff.
            # Do not automatically re-login on a 403: that can trigger more challenges.
            consecutive_forbidden_errors = 0
            while True:
                global TOTAL_SEEN_MESSAGES, LAST_SUCCESSFUL_POLL, LAST_POLL_ERROR
                try:
                    threads = list(cl.direct_threads(amount=THREAD_SCAN_AMOUNT) or [])
                    LAST_SUCCESSFUL_POLL = datetime.now(timezone.utc).isoformat()
                    LAST_POLL_ERROR = "None"
                    current_time_loop = time.time()

                    try:
                        now = datetime.now(ZoneInfo(TIMEZONE_NAME))
                    except Exception:
                        now = datetime.now(ZoneInfo("Asia/Kolkata"))
                    current_hour = now.hour
                    current_minute = now.minute
                    current_date_str = now.strftime("%Y-%m-%d")

                    for thread in threads:
                        if not getattr(thread, "is_group", False):
                            continue

                        thread_id = thread.id
                        gc_admins = []
                        try:
                            if hasattr(thread, "admin_user_ids") and thread.admin_user_ids:
                                gc_admins = [str(uid) for uid in thread.admin_user_ids]
                            elif hasattr(thread, "admin_users") and thread.admin_users:
                                gc_admins = [str(getattr(admin, "pk", admin)) for admin in thread.admin_users]
                        except Exception:
                            gc_admins = []

                        # Silent hard gate: no messages, analytics, moderation, or commands unless bot is a GC admin.
                        bot_pk = str(cl.user_id)
                        if bot_pk not in {str(uid) for uid in gc_admins}:
                            continue

                        if thread_id not in active_announced_threads:
                            active_card = "🎀 𝗦𝗠𝗪🚩 𝗕𝗢𝗧 𝗔𝗖𝗧𝗜𝗩𝗘 🎀"
                            if safe_send_message(thread_id, active_card):
                                active_announced_threads.add(thread_id)
                        users = list(getattr(thread, "users", []) or [])
                        gc_name = (getattr(thread, "thread_title", None) or getattr(thread, "title", None) or getattr(thread, "name", None) or "Unknown GC")
                        record_group_snapshot(thread_id, str(gc_name), users)
                        current_members = {str(getattr(u, "pk", "")) for u in users if getattr(u, "pk", None)}
                        for member in users:
                            member_pk = str(getattr(member, "pk", "") or "")
                            member_name = getattr(member, "username", None) or getattr(member, "full_name", None) or "Unknown member"
                            if member_pk:
                                member_name_cache[member_pk] = str(member_name)

                        admin_mentions_tag = get_admin_mentions_str(users, gc_admins)

                        morning_key = f"gc_morning_sent:{thread_id}:{current_date_str}"
                        night_key = f"gc_night_sent:{thread_id}:{current_date_str}"
                        if current_hour == 6 and load_setting(morning_key, "0") != "1":
                            morning_card = (
                                f"🌅✨ **𝗚𝗢𝗢𝗗 𝗠𝗢𝗥𝗡𝗜𝗡𝗚 𝗘𝗩𝗘𝗥𝗬𝗢𝗡𝗘!** ✨🌅\n\n"
                                f"🌻 𝗛𝗔𝗩𝗘 𝗔𝗡 𝗔𝗠𝗔𝗭𝗜𝗡𝗚 & 𝗣𝗥𝗢𝗗𝗨𝗖𝗧𝗜𝗩𝗘 𝗗𝗔𝗬!\n"
                                f"☕ 𝗦𝗣𝗥𝗘𝗔𝗗 𝗣𝗢𝗦𝗜𝗧𝗜𝗩𝗜𝗧𝗬 𝗜𝗡 𝗧𝗛𝗘 𝗚𝗖 🔥\n\n"
                                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}"
                            )
                            if safe_send_message(thread_id, morning_card):
                                save_setting(morning_key, "1")

                        if current_hour == 23 and load_setting(night_key, "0") != "1":
                            night_card = (
                                f"🌙✨ **𝗚𝗢𝗢𝗗 𝗡𝗜𝗚𝗛𝗧 𝗚𝗖 𝗙𝗔𝗠𝗜𝗟𝗬!** ✨🌙\n\n"
                                f"😴 𝗧𝗜𝗠𝗘 𝗧𝗢 𝗥𝗘𝗦𝗧 & 𝗥𝗘𝗖𝗛𝗔𝗥𝗚𝗘!\n"
                                f"💫 𝗦𝗪𝗘𝗘𝗧 𝗗𝗥𝗘𝗔𝗠𝗦 𝗘𝗩𝗘𝗥𝗬𝗢𝗡𝗘 🌙\n\n"
                                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}"
                            )
                            if safe_send_message(thread_id, night_card):
                                save_setting(night_key, "1")

                        if thread_id in group_members_state:
                            old_members = group_members_state[thread_id]
                            newly_joined = current_members - old_members

                            if newly_joined and not is_first_run:
                                welcome_new = []
                                welcome_back = []
                                for joined_pk in newly_joined:
                                    if joined_pk in welcomed_recently and (current_time_loop - welcomed_recently[joined_pk] < 60):
                                        continue
                                    welcomed_recently[joined_pk] = current_time_loop
                                    user_obj = next((u for u in users if str(getattr(u, "pk", "")) == joined_pk), None)
                                    if not user_obj:
                                        continue
                                    target_username = getattr(user_obj, "username", None)
                                    if not target_username:
                                        continue
                                    is_spam, spam_reason, risk_score, _ = SpamAnalyzer.is_spam_profile(cl, target_username)
                                    if is_spam:
                                        spam_card = (
                                            f"🚨🛡 **𝗦𝗣𝗔𝗠 𝗕𝗢𝗧 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗!**\n\n"
                                            f"👤 𝗨𝗦𝗘𝗥 ➜ {fix_mention(target_username)}\n"
                                            f"⚠️ 𝗥𝗜𝗦𝗞 𝗦𝗖𝗢𝗥𝗘 ➜ {risk_score}%\n"
                                            f"🛑 𝗥𝗘𝗔𝗦𝗢𝗡 ➜ {spam_reason}\n"
                                            f"🚫 𝗔𝗖𝗧𝗜𝗢𝗡 ➜ Kick attempted for GC safety\n\n"
                                            f"📢 **𝗔𝗗𝗠𝗜𝗡 𝗔𝗟𝗘𝗥𝗧** ➜ {admin_mentions_tag}\n\n"
                                            f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}"
                                        )
                                        safe_send_message(thread_id, spam_card)
                                        execute_kick(thread_id, joined_pk, target_username, f"SPAM BOT ({spam_reason})", silent=True)
                                        continue
                                    if joined_pk in ever_seen_members:
                                        welcome_back.append(target_username)
                                    else:
                                        welcome_new.append(target_username)
                                        ever_seen_members.add(joined_pk)

                                if len(welcome_new) > 1:
                                    names = "\n".join(f"• {fix_mention(name)}" for name in welcome_new)
                                    card = (f"🦋✨ 𝗪𝗘𝗟𝗖𝗢𝗠𝗘, {names}! ✨🦋\n\n"
                                            f"🌸 𝗛𝗘𝗬! 𝗚𝗟𝗔𝗗 𝗧𝗢 𝗛𝗔𝗩𝗘 𝗬𝗢𝗨 𝗛𝗘𝗥𝗘 💫\n\n"
                                            f"🔥 𝗘𝗡𝗝𝗢𝗬 𝗧𝗛𝗘 𝗚𝗖 & 𝗦𝗧𝗔𝗬 𝗔𝗖𝗧𝗜𝗩𝗘!\n\n"
                                            f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}")
                                    safe_send_message(thread_id, card)
                                elif welcome_new:
                                    name = welcome_new[0]
                                    card = (f"🦋✨ 𝗪𝗘𝗟𝗖𝗢𝗠𝗘, {fix_mention(name)}! ✨🦋\n\n"
                                            f"🌸 𝗛𝗘𝗬! 𝗚𝗟𝗔𝗗 𝗧𝗢 𝗛𝗔𝗩𝗘 𝗬𝗢𝗨 𝗛𝗘𝗥𝗘 💫\n"
                                            f"🔥 𝗘𝗡𝗝𝗢𝗬 𝗧𝗛𝗘 𝗚𝗖 & 𝗦𝗧𝗔𝗬 𝗔𝗖𝗧𝗜𝗩𝗘!\n\n"
                                            f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}")
                                    safe_send_message(thread_id, card)
                                if len(welcome_back) > 1:
                                    names = "\n".join(f"• {fix_mention(name)}" for name in welcome_back)
                                    card = (f"💫🦋 **𝗪𝗘𝗟𝗖𝗢𝗠𝗘 𝗕𝗔𝗖𝗞, {names}!** 🦋💫\n\n"
                                            f"🌷 𝗧𝗛𝗘 𝗚𝗖 𝗠𝗜𝗦𝗦𝗘𝗗 𝗬𝗢𝗨!\n\n"
                                            f"🔥 𝗕𝗔𝗖𝗞 𝗔𝗚𝗔𝗜𝗡 • 𝗦𝗧𝗔𝗬 𝗔𝗖𝗧𝗜𝗩𝗘\n\n"
                                            f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}")
                                    safe_send_message(thread_id, card)
                                elif welcome_back:
                                    name = welcome_back[0]
                                    card = (f"💫🦋 𝗪𝗘𝗟𝗖𝗢𝗠𝗘 𝗕𝗔𝗖𝗞, {fix_mention(name)}! 🦋💫\n\n"
                                            f"🌷 𝗧𝗛𝗘 𝗚𝗖 𝗙𝗘𝗟𝗧 𝗬𝗢𝗨𝗥 𝗔𝗕𝗦𝗘𝗡𝗖𝗘 😌\n"
                                            f"🔥 𝗕𝗔𝗖𝗞 𝗔𝗚𝗔𝗜𝗡 • 𝗦𝗧𝗔𝗬 𝗔𝗖𝗧𝗜𝗩𝗘\n\n"
                                            f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}")
                                    safe_send_message(thread_id, card)
                        else:
                            ever_seen_members.update(current_members)

                        if thread_id in group_members_state and not is_first_run:
                            departed = group_members_state[thread_id] - current_members
                            for departed_pk in departed:
                                departed_name = member_name_cache.get(departed_pk, "Unknown member")
                                left_card = (
                                    f"👋🚪 𝗠𝗘𝗠𝗕𝗘𝗥 𝗟𝗘𝗙𝗧 𝗧𝗛𝗘 𝗚𝗖\n\n"
                                    f"👤 𝗨𝗦𝗘𝗥 ➜ {fix_mention(departed_name)}\n"
                                    f"🆔 𝗨𝗦𝗘𝗥 𝗜𝗗 ➜ `{departed_pk}`\n\n"
                                    f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}"
                                )
                                safe_send_message(thread_id, left_card)

                        group_members_state[thread_id] = current_members

                        messages = list(getattr(thread, "messages", []) or [])
                        if thread_id not in initialized_message_threads:
                            # Ignore the backlog fetched on startup; process only messages
                            # first observed on later polls, so old commands are not replayed.
                            for old_msg in messages:
                                old_id = str(getattr(old_msg, "id", "") or "")
                                if old_id and old_id not in seen_message_ids:
                                    seen_message_ids.add(old_id)
                                    seen_message_order.append(old_id)
                                    if len(seen_message_order) > SEEN_MESSAGE_CACHE_LIMIT:
                                        expired_id = seen_message_order.popleft()
                                        seen_message_ids.discard(expired_id)
                            initialized_message_threads.add(thread_id)
                            continue

                        for last_msg in reversed(messages):
                            try:
                                message_id = str(getattr(last_msg, "id", "") or "")

                                if message_id and message_id not in seen_message_ids:
                                    seen_message_ids.add(message_id)
                                    seen_message_order.append(message_id)
                                    if len(seen_message_order) > SEEN_MESSAGE_CACHE_LIMIT:
                                        expired_id = seen_message_order.popleft()
                                        seen_message_ids.discard(expired_id)
                                    TOTAL_SEEN_MESSAGES += 1

                                    text = str(getattr(last_msg, "text", "") or "").strip()
                                    text_lower = text.lower()
                                    # Management commands must use the exact SMW prefix.
                                    # Example: 𝗦𝗠𝗪🚩 !help
                                    command_prefix_present = text.startswith("𝗦𝗠𝗪🚩 !")
                                    command_text = text[len("𝗦𝗠𝗪🚩"):].strip() if command_prefix_present else ""
                                    command_lower = command_text.lower()
                                    command_token = command_lower.split(maxsplit=1)[0] if command_lower else ""
                                    sender_id = str(getattr(last_msg, "user_id", ""))

                                    sender_username = ""
                                    message_user = getattr(last_msg, "user", None)
                                    embedded_username = getattr(message_user, "username", None)
                                    if embedded_username:
                                        sender_username = str(embedded_username).strip().lstrip("@")
                                    else:
                                        for u in users:
                                            if str(getattr(u, "pk", "")) == sender_id:
                                                candidate = getattr(u, "username", None)
                                                if candidate:
                                                    sender_username = str(candidate).strip().lstrip("@")
                                                break
                                    # Resolve missing usernames through the logged-in client and cache them.
                                    if not sender_username and sender_id in username_by_id_cache:
                                        sender_username = username_by_id_cache[sender_id]
                                    if not sender_username and sender_id:
                                        try:
                                            profile_info = cl.user_info(int(sender_id))
                                            candidate = getattr(profile_info, "username", None)
                                            if candidate:
                                                sender_username = str(candidate).strip().lstrip("@")
                                        except Exception as username_error:
                                            logging.warning("username_lookup_failed uid=%s error=%s", sender_id, type(username_error).__name__)
                                    if not sender_username:
                                        # Do not silently label an unidentified offender as a generic 'User'.
                                        sender_username = f"unknown_user_{sender_id}" if sender_id else "unknown_user_id_unavailable"
                                    if sender_id:
                                        username_by_id_cache[sender_id] = sender_username

                                    if sender_id == bot_pk:
                                        continue

                                    admin_ids_str = {str(x) for x in gc_admins}
                                    is_sender_admin = sender_id in admin_ids_str
                                    is_dev = sender_username.lstrip("@").casefold() in {d.lstrip("@").casefold() for d in AUTHORIZED_DEVS}

                                    ModerationEngine.record_activity(sender_id, sender_username)
                                    record_group_message(thread_id, str(gc_name), sender_id, sender_username)
                                    logging.info("message_seen thread=%s user=%s", thread_id, sender_username)

                                    if ANTISPAM_ENABLED and text and sender_username.casefold() not in {d.casefold() for d in AUTHORIZED_DEVS}:
                                        normalized_msg = re.sub(r"\s+", " ", text.casefold()).strip()
                                        if normalized_msg and not command_prefix_present:
                                            recent = [item for item in duplicate_message_windows.get(sender_id, []) if current_time_loop - item[0] < 60]
                                            recent.append((current_time_loop, normalized_msg))
                                            duplicate_message_windows[sender_id] = recent[-12:]
                                            repeats = sum(1 for _, item in recent if item == normalized_msg)
                                            if repeats >= ANTISPAM_LIMIT and sender_id not in {str(x) for x in gc_admins} and sender_username.casefold() not in {d.casefold() for d in AUTHORIZED_DEVS}:
                                                reason = f"Repeated text spam ({repeats} identical messages in 60s)"
                                                ModerationEngine.log_event(thread_id, sender_username, "ANTI_SPAM_ALERT", reason)
                                                safe_send_message(thread_id, f"🛡️ 𝗔𝗡𝗧𝗜-𝗦𝗣𝗔𝗠 𝗔𝗟𝗘𝗥𝗧\n👤 USER ➜ {fix_mention(sender_username)}\n⚠️ {reason}\n📢 Admin review required.")
                                                duplicate_message_windows[sender_id] = []
                                                continue

                                    if LOCKDOWN_MODE and not is_dev and not is_sender_admin:
                                        execute_kick(thread_id, sender_id, sender_username, "LOCKDOWN ACTIVE")
                                        continue

                                    if sender_username.lower() in TARGETED_USERS:
                                        execute_kick(thread_id, sender_id, sender_username, "TARGET ELIMINATED")
                                        continue

                                    if sender_username.lower() in SHADOWBANNED_USERS:
                                        execute_kick(thread_id, sender_id, sender_username, "SHADOWBANNED", silent=True)
                                        continue

                                    if not is_dev and not is_sender_admin:
                                        window = [t for t in user_message_windows.get(sender_id, []) if current_time_loop - t < 12]
                                        window.append(current_time_loop)
                                        user_message_windows[sender_id] = window[-12:]
                                        USER_LAST_MESSAGE_TIME[sender_id] = current_time_loop
                                        if len(window) >= 7:
                                            warns, trust = ModerationEngine.add_warning(sender_username)
                                            ModerationEngine.log_event(thread_id, sender_username, "FLOOD_WARNING", f"{len(window)} messages in 12 seconds")
                                            user_message_windows[sender_id] = []
                                            safe_send_message(thread_id, f"⚠️ {fix_mention(sender_username)} slow down please. Flood warning {warns}/3; admins have been notified.")
                                            continue

                                    if command_prefix_present and command_lower == "!rules":
                                        rules_card = (
                                            f"⚜🌷 𝗚𝗖 𝗥𝗨𝗟𝗘𝗦 • 𝗣𝗟𝗘𝗔𝗦𝗘 𝗥𝗘𝗔𝗗 🌷⚜️\n\n"
                                            f"🤝 𝗥𝗘𝗦𝗣𝗘𝗖𝗧 𝗘𝗩𝗘𝗥𝗬𝗢𝗡𝗘\n"
                                            f"💌 𝗞𝗘𝗘𝗣 𝗧𝗛𝗘 𝗩𝗜𝗕𝗘 𝗙𝗥𝗜𝗘𝗡𝗗𝗟𝗬\n\n"
                                            f"🚫 𝗡𝗢 𝗔𝗕𝗨𝗦𝗘 • 𝗡𝗢 𝗧𝗢𝗫𝗜𝗖𝗜𝗧𝗬\n"
                                            f"⚠️ 𝗗𝗥𝗔𝗠𝗔 & 𝗙𝗜𝗚𝗛𝗧𝗦 𝗔𝗥𝗘 𝗡𝗢𝗧 𝗔𝗟𝗟𝗢𝗪𝗘𝗗\n\n"
                                            f"🔞 𝗡𝗢 𝗡𝗦𝗙𝗪 / 𝗔𝗗𝗨𝗟𝗧 𝗖𝗢𝗡𝗧𝗘𝗡𝗧\n"
                                            f"🛡️ 𝗞𝗘𝗘𝗣 𝗧𝗛𝗘 𝗚𝗖 𝗖𝗟𝗘𝗔𝗡\n\n"
                                            f"📢 𝗡𝗢 𝗦𝗣𝗔𝗠 • 𝗡𝗢 𝗙𝗟𝗢𝗢𝗗𝗜𝗡𝗚\n"
                                            f"🚫 𝗗𝗢𝗡'𝗧 𝗦𝗘𝗡𝗗 𝗥𝗘𝗣𝗘𝗔𝗧𝗘𝗗 𝗠𝗘𝗦𝗦𝗔𝗚𝗘𝗦\n\n"
                                            f"🔗 𝗡𝗢 𝗨𝗡𝗔𝗨𝗧𝗛𝗢𝗥𝗜𝗭𝗘𝗗 𝗟𝗜𝗡𝗞𝗦\n"
                                            f"📩 𝗔𝗦𝗞 𝗔𝗗𝗠𝗜𝗡𝗦 𝗙𝗜𝗥𝗦𝗧\n\n"
                                            f"👑 𝗥𝗘𝗦𝗣𝗘𝗖𝗧 𝗔𝗗𝗠𝗜𝗡𝗦 & 𝗠𝗢𝗗𝗘𝗥𝗔𝗧𝗢𝗥𝗦\n"
                                            f"✨ 𝗙𝗢𝗟𝗟𝗢𝗪 𝗢𝗙𝗙𝗜𝗖𝗜𝗔𝗟 𝗜𝗡𝗦𝗧𝗥𝗨𝗖𝗧𝗜𝗢𝗡𝗦\n\n"
                                            f"⚠️ 𝗥𝗨𝗟𝗘𝗦 𝗕𝗥𝗘𝗔𝗞 = 𝗪𝗔𝗥𝗡𝗜𝗡𝗚\n"
                                            f"🚫 𝗥𝗘𝗣𝗘𝗔𝗧𝗘𝗗 𝗩𝗜𝗢𝗟𝗔𝗧𝗜𝗢𝗡𝗦 = 𝗥𝗘𝗠𝗢𝗩𝗔𝗟\n\n"
                                            f"🌷 𝗦𝗧𝗔𝗬 𝗔𝗖𝗧𝗜𝗩𝗘 • 𝗦𝗧𝗔𝗬 𝗥𝗘𝗦𝗣𝗘𝗖𝗧𝗙𝗨𝗟 🌷\n"
                                            f"💫 𝗘𝗡𝗝𝗢𝗬 • 𝗖𝗛𝗔𝗧 • 𝗚𝗥𝗢𝗪 • 𝗖𝗢𝗡𝗡𝗘𝗖𝗧 💫\n\n"
                                            f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}"
                                        )
                                        safe_send_message(thread_id, rules_card)
                                        continue

                                    abuse_reason = detect_abuse_reason(text)
                                    detection_text = get_message_detection_text(last_msg, text)
                                    link_type = detect_link_type(detection_text)
                                    link_violation = bool(link_type)
                                    if abuse_reason or link_violation:
                                        warns, trust = ModerationEngine.add_warning(sender_username)
                                        reason = abuse_reason or f"Unauthorized {link_type}"
                                        detected_link_match = re.search(
                                            r"(?i)(?<![\w@])(?:https?://|ftp://|www\.)[^\s<>\"']+|"
                                            r"(?<![\w@])(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}(?::\d{1,5})?(?:[/\?#][^\s<>\"']*)?|"
                                            r"(?<![\w@])(?:\d{1,3}\.){3}\d{1,3}(?::\d{1,5})?(?:[/\?#][^\s<>\"']*)?",
                                            detection_text, re.IGNORECASE)
                                        detected_link = detected_link_match.group(0)[:180] if detected_link_match else "Link detected in message"
                                        ModerationEngine.log_event(thread_id, sender_username, "WARNING", reason)

                                        if warns >= 2 and not (is_dev or is_sender_admin):
                                            execute_kick(thread_id, sender_id, sender_username, f"Second Violation ({reason})")
                                        elif warns >= 2:
                                            safe_send_message(thread_id, f"🚨 Repeat abuse alert for {fix_mention(sender_username)}. Admin review required; no automatic removal for privileged accounts.")
                                        else:
                                            warn_heading = (
                                                "⚠️ **𝗔𝗕𝗨𝗦𝗜𝗡𝗚 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗!** ⚠️\n\n" if abuse_reason else
                                                ("🎬🔗 **𝗜𝗡𝗦𝗧𝗔𝗚𝗥𝗔𝗠 𝗥𝗘𝗘𝗟 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗!** 🔗🎬\n\n" if link_type == "Instagram Reel Link" else "⚠️🚨 **𝗚𝗖 𝗦𝗔𝗙𝗘𝗧𝗬 𝗔𝗟𝗘𝗥𝗧!** 🚨⚠️\n\n")
                                            )
                                            warn_card = (
                                                warn_heading
                                                + f"👤 𝗢𝗙𝗙𝗘𝗡𝗗𝗘𝗥 ➜ {fix_mention(sender_username)}\n"
                                                + f"🆔 𝗨𝗦𝗘𝗥 𝗜𝗗 ➜ {sender_id or 'Unavailable'}\n"
                                                + (f"🔗 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗 𝗟𝗜𝗡𝗞 ➜ {detected_link}\n" if link_violation else "")
                                                + f"🚫 𝗥𝗘𝗔𝗦𝗢𝗡   ➜ {reason}\n"
                                                + f"⚠️ 𝗪𝗔𝗥𝗡𝗜𝗡𝗚𝗦 ➜ {warns}/2\n"
                                                + f"📉 𝗧𝗥𝗨𝗦𝗧 𝗦𝗖𝗢𝗥𝗘 ➜ {trust}%\n\n"
                                                + f"📢 **𝗔𝗗𝗠𝗜𝗡 𝗔𝗟𝗘𝗥𝗧** ➜ {admin_mentions_tag}\n\n"
                                                + f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}"
                                            )
                                            safe_send_message(thread_id, warn_card)
                                        continue

                                    if LOCAL_AUTO_REPLIES and not command_prefix_present:
                                        answer = None
                                        if any(k in text_lower for k in ["bot help", "bot kya", "commands", "command list", "help me", "how to use bot"]):
                                            answer = ("🔐 𝗦𝗠𝗪 𝗕𝗢𝗧 𝗦𝗨𝗣𝗣𝗢𝗥𝗧\n\n"
                                                      "𝗖𝗢𝗠𝗠𝗔𝗡𝗗 𝗟𝗜𝗦𝗧𝗦 𝗔𝗥𝗘 𝗣𝗥𝗜𝗩𝗔𝗧𝗘. 𝗣𝗟𝗘𝗔𝗦𝗘 𝗖𝗢𝗡𝗧𝗔𝗖𝗧 𝗦𝗠𝗪 (𝗦𝗧𝗔𝗬 𝗡𝗜𝗡𝗘) 𝗙𝗢𝗥 𝗖𝗢𝗠𝗠𝗔𝗡𝗗 𝗔𝗖𝗖𝗘𝗦𝗦.\n\n"
                                                      "𝗠𝗔𝗡𝗨𝗔𝗟 𝗖𝗢𝗠𝗠𝗔𝗡𝗗𝗦 𝗥𝗘𝗤𝗨𝗜𝗥𝗘: 𝗦𝗠𝗪🚩 !𝗰𝗼𝗺𝗺𝗮𝗻𝗱")
                                        elif "good morning" in text_lower or re.search(r"(?<!\w)gm(?!\w)", text_lower):
                                            answer = f"Good morning, {fix_mention(sender_username)}! Please follow the group rules and enjoy. 🌞"
                                        elif "good night" in text_lower or re.search(r"(?<!\w)gn(?!\w)", text_lower):
                                            answer = f"Good night, {fix_mention(sender_username)}! 🌙"
                                        elif any(k in text_lower for k in ["thank you", "thanks"]):
                                            answer = "You're welcome! 😊"
                                        if answer:
                                            safe_send_message(thread_id, answer)
                                            continue

                                    command_token = command_lower.split(maxsplit=1)[0] if command_lower else ""
                                    # User-created text-only commands are public replies; command creation/deletion stays developer-only.
                                    if command_prefix_present and command_token.startswith("!") and command_token != "!rules":
                                        custom_commands = load_custom_commands()
                                        custom_name = command_token[1:].casefold()
                                        if custom_name in custom_commands and custom_name not in {"addcmd", "editcmd", "delcmd", "cmds"}:
                                            safe_send_message(thread_id, custom_commands[custom_name])
                                            continue

                                    is_trying_command = command_prefix_present and command_token.startswith("!") and command_token != "!rules"

                                    if is_trying_command and not is_dev:
                                        continue

                                    if is_dev and command_prefix_present and command_lower.startswith("!"):
                                        if command_token in {"!gc", "!gcanalytics"}:
                                            db = SessionLocal()
                                            try:
                                                safe_send_message(thread_id, group_report(db, thread_id, str(gc_name)))
                                            finally:
                                                db.close()
                                            continue
                                        elif command_token == "!gcs":
                                            db = SessionLocal()
                                            try:
                                                rows = db.query(GroupAnalytics).order_by(GroupAnalytics.last_activity.desc()).limit(30).all()
                                                lines = [f"• {r.group_name} | ID: {r.group_id} | Members: {r.observed_members or 0} | Msgs: {r.message_count or 0}" for r in rows]
                                                safe_send_message(thread_id, "📚 TRACKED GROUPS\n\n" + ("\n".join(lines) if lines else "No GC records yet."))
                                            finally:
                                                db.close()
                                            continue
                                        elif command_token == "!gcuser":
                                            parts = command_text.split(maxsplit=1)
                                            target = parts[1].lstrip("@") if len(parts) > 1 else ""
                                            db = SessionLocal()
                                            try:
                                                q = db.query(GroupMemberAnalytics).filter_by(group_id=str(thread_id))
                                                if target:
                                                    q = q.filter(func.lower(GroupMemberAnalytics.username) == target.lower())
                                                rows = q.order_by(GroupMemberAnalytics.message_count.desc()).limit(20).all()
                                                lines = [f"@{r.username} | UID: {r.user_id} | Msgs: {r.message_count}" for r in rows]
                                                safe_send_message(thread_id, "👥 GC MEMBER ACTIVITY\n\n" + ("\n".join(lines) if lines else "No matching member activity recorded."))
                                            finally:
                                                db.close()
                                            continue
                                        if command_lower == "!analytics":
                                            db = SessionLocal()
                                            try:
                                                total_users = db.query(UserProfile).count()
                                                total_msgs = db.query(UserProfile).with_entities(UserProfile.total_messages).all()
                                                total_warns = db.query(UserProfile).with_entities(UserProfile.warning_count).all()
                                                event_count = db.query(SecurityLog).count()
                                                safe_send_message(thread_id, f"📊 𝗦𝗠𝗪 𝗕𝗢𝗧 𝗜𝗡𝗙𝗢𝗥𝗠𝗔𝗧𝗜𝗢𝗡\n\n𝗦𝗧𝗔𝗧𝗨𝗦 ➜ 𝗢𝗡𝗟𝗜𝗡𝗘 & 𝗔𝗖𝗧𝗜𝗩𝗘\n🤖 𝗕𝗢𝗧 ➜ 𝗦𝗠𝗪\n👥 𝗧𝗥𝗔𝗖𝗞𝗘𝗗 𝗨𝗦𝗘𝗥𝗦 ➜ {total_users}\n💬 𝗧𝗥𝗔𝗖𝗞𝗘𝗗 𝗠𝗘𝗦𝗦𝗔𝗚𝗘𝗦 ➜ {sum((x[0] or 0) for x in total_msgs)}\n⚠️ 𝗪𝗔𝗥𝗡𝗜𝗡𝗚𝗦 ➜ {sum((x[0] or 0) for x in total_warns)}\n📋 𝗔𝗨𝗗𝗜𝗧 𝗘𝗩𝗘𝗡𝗧𝗦 ➜ {event_count}\n📨 𝗠𝗘𝗦𝗦𝗔𝗚𝗘𝗦 𝗧𝗛𝗜𝗦 𝗥𝗨𝗡 ➜ {TOTAL_SEEN_MESSAGES}\n\n👑 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ 𝗦𝗠𝗪🚩")
                                            finally:
                                                db.close()
                                            continue
                                        elif command_lower == "!session":
                                            safe_send_message(thread_id, f"🔐 Session health\nSession ID configured: {'YES' if INSTAGRAM_SESSION_ID and INSTAGRAM_SESSION_ID not in {'PASTE_YOUR_SESSION_ID_HERE', 'PASTE_YOUR_NEW_SESSION_ID_HERE', 'YOUR_SESSION_ID_HERE'} else 'NO'}\nLast successful poll: {LAST_SUCCESSFUL_POLL or 'not yet'}\nLast error type: {LAST_POLL_ERROR}")
                                            continue
                                        elif command_token == "!safe_mode":
                                            safe_parts = command_text.split(maxsplit=2)
                                            safe_action = safe_parts[1].casefold() if len(safe_parts) > 1 else "toggle"
                                            if safe_action in {"clear", "remove", "reset"}:
                                                target = safe_parts[2].strip().split()[0].lstrip("@") if len(safe_parts) > 2 else ""
                                                if not target:
                                                    safe_send_message(thread_id, "🛡️ 𝗦𝗔𝗙𝗘 𝗠𝗢𝗗𝗘 𝗨𝗦𝗘𝗥 𝗖𝗟𝗘𝗔𝗥\n\nUsage: 𝗦𝗠𝗪🚩 !safe_mode clear @username")
                                                    continue
                                                target_key = target.casefold()
                                                TARGETED_USERS.discard(target_key)
                                                SHADOWBANNED_USERS.discard(target_key)
                                                save_runtime_state()
                                                try:
                                                    target_uid = str(cl.user_id_from_username(target))
                                                    user_message_windows.pop(target_uid, None)
                                                    duplicate_message_windows.pop(target_uid, None)
                                                    USER_LAST_MESSAGE_TIME.pop(target_uid, None)
                                                except Exception:
                                                    target_uid = "not resolved"
                                                db = SessionLocal()
                                                try:
                                                    profile = db.query(UserProfile).filter(func.lower(UserProfile.username) == target_key).first()
                                                    if profile:
                                                        profile.warning_count = 0
                                                        profile.trust_score = 100.0
                                                        db.commit()
                                                except Exception:
                                                    db.rollback()
                                                    logging.exception("safe_mode_user_clear_failed username=%s", target_key)
                                                finally:
                                                    db.close()
                                                ModerationEngine.log_event(thread_id, target_key, "SAFE_MODE_USER_CLEARED", f"Developer cleared user tracking; user_id={target_uid}")
                                                safe_send_message(thread_id, f"🛡️ 𝗦𝗔𝗙𝗘 𝗠𝗢𝗗𝗘 𝗨𝗦𝗘𝗥 𝗖𝗟𝗘𝗔𝗥𝗘𝗗\n\n👤 𝗨𝗦𝗘𝗥 ➜ @{target_key}\n✅ Restrictions and warning state cleared where resolvable.\n🛡️ 𝗚𝗟𝗢𝗕𝗔𝗟 𝗦𝗔𝗙𝗘 𝗠𝗢𝗗𝗘 ➜ {'ON' if SAFE_MODE else 'OFF'} (unchanged)\n👑 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ 𝗦𝗠𝗪🚩")
                                            else:
                                                SAFE_MODE = not SAFE_MODE
                                                safe_send_message(thread_id, f"🛡️ 𝗦𝗔𝗙𝗘 𝗠𝗢𝗗𝗘 ➜ {'ON' if SAFE_MODE else 'OFF'}\nUse 𝗦𝗠𝗪🚩 !safe_mode clear @username to clear one user's bot-managed restrictions without changing global Safe Mode.")
                                            continue
                                        elif command_token == "!safeclear":
                                            # Alias for clearing one user's bot-managed Safe Mode/restriction state.
                                            safe_parts = command_text.split(maxsplit=1)
                                            target = safe_parts[1].strip().split()[0].lstrip("@") if len(safe_parts) > 1 else ""
                                            if not target:
                                                safe_send_message(thread_id, "Usage: 𝗦𝗠𝗪🚩 !safeclear @username")
                                                continue
                                            TARGETED_USERS.discard(target.casefold())
                                            SHADOWBANNED_USERS.discard(target.casefold())
                                            save_runtime_state()
                                            try:
                                                target_uid = str(cl.user_id_from_username(target))
                                                user_message_windows.pop(target_uid, None)
                                                duplicate_message_windows.pop(target_uid, None)
                                                USER_LAST_MESSAGE_TIME.pop(target_uid, None)
                                            except Exception:
                                                target_uid = "not resolved"
                                            ModerationEngine.log_event(thread_id, target.casefold(), "SAFE_MODE_USER_CLEARED", f"Developer cleared user tracking; user_id={target_uid}")
                                            safe_send_message(thread_id, f"🛡️ 𝗦𝗔𝗙𝗘 𝗠𝗢𝗗𝗘 𝗨𝗦𝗘𝗥 𝗖𝗟𝗘𝗔𝗥𝗘𝗗\n👤 𝗨𝗦𝗘𝗥 ➜ @{target.casefold()}\n🛡️ 𝗚𝗟𝗢𝗕𝗔𝗟 𝗦𝗔𝗙𝗘 𝗠𝗢𝗗𝗘 ➜ {'ON' if SAFE_MODE else 'OFF'} (unchanged)\n👑 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ 𝗦𝗠𝗪🚩")
                                            continue
                                        elif command_lower in {"!panel", "!status"}:
                                            uptime = int(time.time() - STARTED_AT)
                                            db = SessionLocal()
                                            try:
                                                profiles = db.query(UserProfile).count()
                                                warnings = db.query(UserProfile).with_entities(UserProfile.warning_count).all()
                                                warning_total = sum((x[0] or 0) for x in warnings)
                                                log_total = db.query(SecurityLog).count()
                                            finally:
                                                db.close()
                                            safe_send_message(thread_id, f"🧠 SMART BOT PANEL\nMode: {'LOCKDOWN' if LOCKDOWN_MODE else 'NORMAL'}\nUptime: {uptime}s\nMembers tracked: {profiles}\nWarnings recorded: {warning_total}\nAudit events: {log_total}\nMessages seen this run: {TOTAL_SEEN_MESSAGES}\nLast poll: {LAST_SUCCESSFUL_POLL or 'pending'}\nLast poll error: {LAST_POLL_ERROR}")
                                            continue
                                        elif command_lower == "!logs":
                                            db = SessionLocal()
                                            try:
                                                rows = db.query(SecurityLog).order_by(SecurityLog.id.desc()).limit(5).all()
                                                report = "\n".join(f"#{r.id} {r.event_type} @{r.username}: {(r.details or '')[:100]}" for r in rows) or "No audit events yet."
                                            finally:
                                                db.close()
                                            safe_send_message(thread_id, "📋 Recent audit logs\n" + report[:1500])
                                            continue
                                        elif command_lower == "!backup":
                                            try:
                                                if DATABASE_URL.startswith("sqlite:///"):
                                                    db_path = DATABASE_URL.replace("sqlite:///", "", 1)
                                                    if db_path == ":memory:":
                                                        raise RuntimeError("In-memory database cannot be backed up")
                                                    src = sqlite3.connect(db_path)
                                                    dst_path = f"{Path(db_path).stem}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
                                                    dst = sqlite3.connect(dst_path)
                                                    with dst:
                                                        src.backup(dst)
                                                    dst.close(); src.close()
                                                    safe_send_message(thread_id, f"✅ Database backup created on bot host: {dst_path}.")
                                                else:
                                                    safe_send_message(thread_id, "Backup requires a SQLite DATABASE_URL.")
                                            except Exception as backup_error:
                                                logging.exception("backup_failed")
                                                safe_send_message(thread_id, f"Backup failed: {type(backup_error).__name__}")
                                            continue
                                        elif command_lower == "!help":
                                            # Never publish the private command catalogue in a group chat.
                                            # Authorized developers can request the full command guide privately from SMW.
                                            safe_send_message(
                                                thread_id,
                                                "🔐 𝗣𝗥𝗜𝗩𝗔𝗧𝗘 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 𝗦𝗨𝗣𝗣𝗢𝗥𝗧\n\n"
                                                "𝗧𝗛𝗘 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 𝗖𝗢𝗠𝗠𝗔𝗡𝗗 𝗟𝗜𝗦𝗧 𝗜𝗦 𝗣𝗥𝗜𝗩𝗔𝗧𝗘 𝗔𝗡𝗗 𝗪𝗜𝗟𝗟 𝗡𝗢𝗧 𝗕𝗘 𝗦𝗛𝗢𝗪𝗡 𝗜𝗡 𝗧𝗛𝗜𝗦 𝗚𝗥𝗢𝗨𝗣.\n\n"
                                                "𝗙𝗢𝗥 𝗖𝗢𝗠𝗠𝗔𝗡𝗗 𝗔𝗖𝗖𝗘𝗦𝗦 𝗢𝗥 𝗦𝗨𝗣𝗣𝗢𝗥𝗧, 𝗖𝗢𝗡𝗧𝗔𝗖𝗧 𝗦𝗠𝗪 (𝗦𝗧𝗔𝗬 𝗡𝗜𝗡𝗘).\n\n"
                                                "𝗠𝗔𝗡𝗨𝗔𝗟 𝗖𝗢𝗠𝗠𝗔𝗡𝗗 𝗙𝗢𝗥𝗠𝗔𝗧: 𝗦𝗠𝗪🚩 !𝗰𝗼𝗺𝗺𝗮𝗻𝗱\n"
                                                "𝗔𝗨𝗧𝗢𝗠𝗔𝗧𝗜𝗖 𝗦𝗘𝗖𝗨𝗥𝗜𝗧𝗬 𝗙𝗘𝗔𝗧𝗨𝗥𝗘𝗦 𝗥𝗨𝗡 𝗢𝗡 𝗧𝗛𝗘𝗜𝗥 𝗢𝗪𝗡."
                                            )
                                            continue
                                        elif command_token in {"!addcmd", "!editcmd"}:
                                            parts = command_text.split(maxsplit=2)
                                            if len(parts) < 3 or "|" not in parts[2]:
                                                safe_send_message(thread_id, "Usage: 𝗦𝗠𝗪🚩 !addcmd command | reply text\nExample: 𝗦𝗠𝗪🚩 !addcmd support | Contact the GC admins.")
                                            else:
                                                cmd_name = parts[1].strip().lstrip("!").casefold()
                                                reply_text = parts[2].split("|", 1)[1].strip()
                                                if not re.fullmatch(r"[a-z0-9_]{2,32}", cmd_name) or cmd_name in {"help", "panel", "status", "analytics", "rules", "addcmd", "editcmd", "delcmd", "cmds", "clearuser", "resetuser", "unrestrict", "gc", "gcanalytics", "gcs", "gcuser", "session", "safe_mode", "logs", "backup", "lockdown", "unlock", "godmode", "target", "shadowban", "nuke", "resetwarn", "unwarn", "antispam", "report", "inactive", "tagall", "active", "members", "admins", "dp", "profile", "user", "stats", "botinfo"}:
                                                    safe_send_message(thread_id, "❌ Invalid or reserved command name. Use 2-32 letters, digits, or underscores.")
                                                elif not reply_text:
                                                    safe_send_message(thread_id, "❌ Reply text cannot be empty.")
                                                else:
                                                    custom_commands = load_custom_commands()
                                                    existed = cmd_name in custom_commands
                                                    custom_commands[cmd_name] = reply_text[:1200]
                                                    save_custom_commands(custom_commands)
                                                    safe_send_message(thread_id, f"✅ Custom command {'updated' if existed else 'created'}: !{cmd_name}\nMembers can use: 𝗦𝗠𝗪🚩 !{cmd_name}")
                                            continue
                                        elif command_token == "!delcmd":
                                            parts = command_text.split(maxsplit=1)
                                            cmd_name = parts[1].strip().lstrip("!").casefold() if len(parts) > 1 else ""
                                            custom_commands = load_custom_commands()
                                            if cmd_name in custom_commands:
                                                del custom_commands[cmd_name]
                                                save_custom_commands(custom_commands)
                                                safe_send_message(thread_id, f"✅ Custom command deleted: !{cmd_name}")
                                            else:
                                                safe_send_message(thread_id, f"ℹ️ Custom command not found: !{cmd_name or '(missing name)'}")
                                            continue
                                        elif command_token == "!cmds":
                                            custom_commands = load_custom_commands()
                                            listing = "\n".join(f"• 𝗦𝗠𝗪🚩 !{name}" for name in sorted(custom_commands)) or "No custom commands created yet."
                                            safe_send_message(thread_id, "🧩 CUSTOM COMMANDS\n\n" + listing[:1400])
                                            continue
                                        elif command_lower == "!lockdown":
                                            LOCKDOWN_MODE = True
                                            save_runtime_state()
                                            safe_send_message(thread_id, "🔒 𝗟𝗢𝗖𝗞𝗗𝗢𝗪𝗡 𝗔𝗖𝗧𝗜𝗩𝗘\n\n🛡️ Non-admin members will be removed on new messages.")
                                            continue
                                        elif command_lower == "!unlock":
                                            LOCKDOWN_MODE = False
                                            save_runtime_state()
                                            safe_send_message(thread_id, "🔓 𝗟𝗢𝗖𝗞𝗗𝗢𝗪𝗡 𝗗𝗜𝗦𝗔𝗕𝗟𝗘𝗗\n\n🟢 Normal group activity restored.")
                                            continue
                                        elif command_lower == "!godmode":
                                            status_card = (
                                                f"⚡🛡️ **𝗚𝗢𝗗𝗠𝗢𝗗𝗘 𝗦𝗧𝗔𝗧𝗨𝗦** 🛡️⚡\n\n"
                                                f"🔒 **𝗟𝗼𝗰𝗸𝗱𝗼𝘄𝗻** ➜ {'ON 🚨' if LOCKDOWN_MODE else 'OFF 🟢'}\n"
                                                f"🎯 **𝗧𝗮𝗿𝗴𝗲𝘁𝘀** ➜ {len(TARGETED_USERS)} Users\n"
                                                f"🛡️ **Anti-Spam** ➜ {'ON' if ANTISPAM_ENABLED else 'OFF'} (limit {ANTISPAM_LIMIT})\n"
                                                f"👻 **𝗦𝗵𝗮𝗱𝗼𝘄𝗯𝗮𝗻𝘀** ➜ {len(SHADOWBANNED_USERS)} Users\n\n"
                                                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                            )
                                            safe_send_message(thread_id, status_card)
                                            continue
                                        elif command_lower.startswith("!target"):
                                            parts = command_text.split()
                                            action = parts[1].lower() if len(parts) > 1 else "help"
                                            if action in {"remove", "del", "delete", "off"} and len(parts) > 2:
                                                target = parts[2].lstrip("@").casefold()
                                                if target in TARGETED_USERS:
                                                    TARGETED_USERS.discard(target)
                                                    save_runtime_state()
                                                    safe_send_message(thread_id, f"✅ Target removed: @{target}")
                                                else:
                                                    safe_send_message(thread_id, f"ℹ @{target} target list mein nahi hai.")
                                            elif action in {"clear", "reset", "all"}:
                                                TARGETED_USERS.clear()
                                                save_runtime_state()
                                                safe_send_message(thread_id, "✅ Saare target rules clear kar diye gaye.")
                                            elif action in {"list", "show"}:
                                                targets = ", ".join(f"@{name}" for name in sorted(TARGETED_USERS)) or "None"
                                                safe_send_message(thread_id, f"🎯 Active targets: {targets}")
                                            elif len(parts) > 1:
                                                target = parts[1].lstrip("@").casefold()
                                                TARGETED_USERS.add(target)
                                                save_runtime_state()
                                                safe_send_message(thread_id, f"🎯 Target registered: @{target}")
                                            else:
                                                safe_send_message(thread_id, "Usage: !target @username | !target remove @username | !target clear | !target list")
                                            continue
                                        elif command_lower.startswith("!shadowban"):
                                            parts = command_text.split()
                                            action = parts[1].lower() if len(parts) > 1 else "help"
                                            if action in {"remove", "del", "delete", "off"} and len(parts) > 2:
                                                target = parts[2].lstrip("@").casefold()
                                                SHADOWBANNED_USERS.discard(target)
                                                save_runtime_state()
                                                safe_send_message(thread_id, f"✅ Shadowban removed for @{target}")
                                            elif action in {"clear", "reset", "all"}:
                                                SHADOWBANNED_USERS.clear(); save_runtime_state()
                                                safe_send_message(thread_id, "✅ All shadowban entries cleared.")
                                            elif action in {"list", "show"}:
                                                safe_send_message(thread_id, "👻 Shadowbanned: " + (", ".join("@"+x for x in sorted(SHADOWBANNED_USERS)) or "None"))
                                            elif len(parts) > 1:
                                                target = parts[1].lstrip("@").casefold()
                                                SHADOWBANNED_USERS.add(target); save_runtime_state()
                                                safe_send_message(thread_id, f"👻 Shadowban rule registered: @{target}")
                                            else:
                                                safe_send_message(thread_id, "Usage: !shadowban @user | remove @user | clear | list")
                                            continue
                                        elif command_lower.startswith("!nuke"):
                                            parts = command_text.split()
                                            if len(parts) > 1:
                                                target = parts[1].lstrip("@")
                                                try:
                                                    u_id = cl.user_id_from_username(target)
                                                    execute_kick(thread_id, u_id, target, "NUKE BAN")
                                                except Exception as e:
                                                    safe_send_message(thread_id, f"❌ Could not remove @{target}: {e}")
                                            else:
                                                safe_send_message(thread_id, "Usage: !nuke @username")
                                            continue
                                        elif command_token == "!kick":
                                            # Hidden developer-only manual removal. Safe Mode blocks automatic removals,
                                            # but never blocks an explicit, authorized developer decision.
                                            parts = command_text.split(maxsplit=1)
                                            target = parts[1].strip().split()[0].lstrip("@") if len(parts) > 1 else ""
                                            if not target:
                                                safe_send_message(thread_id, "Usage: 𝗦𝗠𝗪🚩 !kick @username")
                                                continue
                                            target_user = next((u for u in users if str(getattr(u, "username", "") or "").casefold() == target.casefold()), None)
                                            target_uid = str(getattr(target_user, "pk", "") or "") if target_user else ""
                                            canonical_username = str(getattr(target_user, "username", "") or target).lstrip("@")
                                            if not target_uid:
                                                try:
                                                    target_uid = str(cl.user_id_from_username(canonical_username))
                                                except Exception:
                                                    target_uid = ""
                                            if not target_uid:
                                                safe_send_message(thread_id, f"❌ USER NOT FOUND\nUsername: @{canonical_username}\nThe account could not be resolved. Check the exact Instagram username.")
                                                continue
                                            try:
                                                cl.user_remove_from_thread(thread_id, int(target_uid))
                                                target_key = canonical_username.casefold()
                                                TARGETED_USERS.discard(target_key)
                                                SHADOWBANNED_USERS.discard(target_key)
                                                save_runtime_state()
                                                ModerationEngine.log_event(thread_id, target_key, "DEVELOPER_MANUAL_REMOVAL", f"Removed by authorized developer; user_id={target_uid}; Safe Mode={SAFE_MODE}")
                                                safe_send_message(thread_id, f"🚪 MEMBER REMOVED\n👤 USERNAME ➜ @{canonical_username}\n🆔 USER ID ➜ {target_uid}\n🛡️ SAFE MODE ➜ {'ON (manual developer action allowed)' if SAFE_MODE else 'OFF'}\n👑 AUTHORIZED BY ➜ SMW🚩")
                                            except Exception as removal_error:
                                                logging.exception("developer_manual_removal_failed thread=%s uid=%s", thread_id, target_uid)
                                                safe_send_message(thread_id, f"❌ REMOVAL FAILED\n👤 USERNAME ➜ @{canonical_username}\nReason: Instagram rejected the removal ({type(removal_error).__name__}). Check the bot account's group permissions and API support.")
                                            continue
                                        elif command_token in {"!clearuser", "!resetuser", "!unrestrict"}:
                                            parts = command_text.split(maxsplit=1)
                                            target = parts[1].strip().split()[0].lstrip("@") if len(parts) > 1 else ""
                                            if not target:
                                                safe_send_message(thread_id, "Usage: 𝗦𝗠𝗪🚩 !clearuser @username\nClears this bot's warnings and active restrictions for one user.")
                                                continue
                                            target_key = target.casefold()
                                            # Remove all bot-managed username restrictions.
                                            TARGETED_USERS.discard(target_key)
                                            SHADOWBANNED_USERS.discard(target_key)
                                            save_runtime_state()
                                            db = SessionLocal()
                                            try:
                                                profile = db.query(UserProfile).filter(func.lower(UserProfile.username) == target_key).first()
                                                if profile:
                                                    profile.warning_count = 0
                                                    profile.trust_score = 100.0
                                                    db.commit()
                                                else:
                                                    db.rollback()
                                            except Exception:
                                                db.rollback()
                                                logging.exception("clearuser_profile_reset_failed username=%s", target_key)
                                            finally:
                                                db.close()
                                            # Clear in-memory anti-flood/repeat windows when a username can be resolved.
                                            try:
                                                target_uid = str(cl.user_id_from_username(target))
                                                user_message_windows.pop(target_uid, None)
                                                duplicate_message_windows.pop(target_uid, None)
                                                USER_LAST_MESSAGE_TIME.pop(target_uid, None)
                                            except Exception:
                                                target_uid = "not resolved"
                                            ModerationEngine.log_event(thread_id, target_key, "DEVELOPER_CLEAR_USER", f"Warnings/restrictions reset by developer; user_id={target_uid}")
                                            safe_send_message(thread_id, f"✅ USER RESET COMPLETE\n👤 USERNAME ➜ @{target_key}\n⚠️ Warning count reset; trust score restored; target/shadowban entries removed; temporary spam/flood state cleared when resolvable.\nℹ️ If the user was already removed from the GC, this command does not automatically re-add them.")
                                            continue
                                        elif command_token in {"!resetwarn", "!unwarn"}:
                                            parts = command_text.split()
                                            if len(parts) > 1 and parts[1].lower() in {"all", "everyone"}:
                                                db = SessionLocal()
                                                try:
                                                    db.query(UserProfile).update({UserProfile.warning_count: 0}, synchronize_session=False); db.commit()
                                                    safe_send_message(thread_id, "✅ All tracked warning counts reset.")
                                                except Exception:
                                                    db.rollback(); safe_send_message(thread_id, "❌ Could not reset all warnings.")
                                                finally:
                                                    db.close()
                                            elif len(parts) > 1:
                                                target = parts[1].lstrip("@").strip()
                                                ModerationEngine.reset_warnings(target)
                                                safe_send_message(thread_id, f"✅ Warnings reset for @{target}.")
                                            else:
                                                safe_send_message(thread_id, "Usage: !resetwarn @username | !resetwarn all")
                                            continue
                                        elif command_token == "!antispam":
                                            parts = command_text.split()
                                            action = parts[1].lower() if len(parts) > 1 else "status"
                                            if action in {"on", "off"}:
                                                ANTISPAM_ENABLED = action == "on"; save_runtime_state()
                                                safe_send_message(thread_id, f"🛡️ Anti-spam {action.upper()}.")
                                            elif action == "limit" and len(parts) > 2:
                                                try:
                                                    ANTISPAM_LIMIT = max(2, min(10, int(parts[2]))); save_runtime_state()
                                                    safe_send_message(thread_id, f"✅ Duplicate threshold set to {ANTISPAM_LIMIT} messages/60s.")
                                                except ValueError:
                                                    safe_send_message(thread_id, "Usage: !antispam limit 2-10")
                                            else:
                                                safe_send_message(thread_id, f"Anti-spam: {'ON' if ANTISPAM_ENABLED else 'OFF'} | threshold: {ANTISPAM_LIMIT}/60s")
                                            continue
                                        elif command_token == "!inactive":
                                            parts = command_text.split()
                                            try: days = max(1, min(365, int(parts[1]))) if len(parts) > 1 else 30
                                            except ValueError: days = 30
                                            cutoff = get_utc_now().replace(tzinfo=None) - __import__('datetime').timedelta(days=days)
                                            db = SessionLocal()
                                            try:
                                                rows = db.query(UserProfile).filter(UserProfile.last_active < cutoff).order_by(UserProfile.last_active.asc()).limit(30).all()
                                                report = "\n".join(f"@{r.username} — last active {r.last_active}" for r in rows) or "No tracked inactive users."
                                                safe_send_message(thread_id, f"📋 INACTIVE REPORT (>{days} days)\n{report}")
                                            finally: db.close()
                                            continue
                                        elif command_token == "!report":
                                            db = SessionLocal()
                                            try:
                                                total = db.query(UserProfile).count()
                                                msgs = db.query(func.sum(UserProfile.total_messages)).scalar() or 0
                                                warns = db.query(func.sum(UserProfile.warning_count)).scalar() or 0
                                                logs = db.query(SecurityLog).count()
                                                safe_send_message(thread_id, f"📊 SMW GROUP REPORT\nTracked members: {total}\nRecorded messages: {msgs}\nCurrent warnings: {warns}\nSecurity events: {logs}")
                                            finally: db.close()
                                            continue
                                        elif command_lower in ("!tagall", "!active", "!members"):
                                            all_tags = [fix_mention(getattr(u, "username", "")) for u in users if getattr(u, "username", None)]
                                            if not all_tags:
                                                safe_send_message(thread_id, "❌ No visible group members were found.")
                                            else:
                                                intro = "📢 EVERYONE, PLEASE BE ACTIVE!\n\n"
                                                chunks = []
                                                current = intro
                                                for tag in all_tags:
                                                    addition = tag + " "
                                                    if len(current) + len(addition) > 1700:
                                                        chunks.append(current.rstrip())
                                                        current = "📢 EVERYONE, PLEASE BE ACTIVE! (continued)\n\n"
                                                    current += addition
                                                current += f"\n\n🤖 BOT ➜ {fix_mention(BOT_USERNAME)}"
                                                chunks.append(current)
                                                for chunk in chunks:
                                                    safe_send_message(thread_id, chunk)
                                            continue
                                        elif command_lower == "!admins":
                                            if gc_admins:
                                                admin_names = []
                                                for u in users:
                                                    if str(getattr(u, "pk", "")) in admin_ids_str:
                                                        un = getattr(u, "username", None)
                                                        if un:
                                                            admin_names.append(f"👑 ➜ {fix_mention(un)}")

                                                admin_card = (
                                                    f"👑🛡️ **𝗚𝗖 𝗔𝗗𝗠𝗜𝗡𝗜𝗦𝗧𝗥𝗔𝗧𝗢𝗥𝗦** 🛡️👑\n\n"
                                                    f"📊 **𝗧𝗢𝗧𝗔𝗟** ➜ {len(gc_admins)}\n\n"
                                                    f"{'\n'.join(admin_names)}\n\n"
                                                    f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}"
                                                )
                                                safe_send_message(thread_id, admin_card)
                                            else:
                                                safe_send_message(thread_id, "ℹ️ Group admin list is not exposed in this thread snapshot.")
                                            continue
                                        elif command_token == "!dp":
                                            parts = command_text.split()
                                            target_name = parts[1].lstrip("@") if len(parts) > 1 else sender_username
                                            try:
                                                u_info = cl.user_info_by_username(target_name)
                                                if u_info:
                                                    dp_url = getattr(getattr(u_info, "hd_profile_pic_url_info", None), "url", None) or getattr(u_info, "profile_pic_url_hd", None) or u_info.profile_pic_url
                                                    photo_path = cl.photo_download_by_url(dp_url, filename=f"{target_name}_dp.jpg")
                                                    # All outbound operations respect the same global 403 cooldown.
                                                    if time.time() < SEND_COOLDOWN_UNTIL:
                                                        logging.info("outgoing_photo_skipped_during_403_cooldown thread_id=%s", str(thread_id))
                                                        continue
                                                    try:
                                                        cl.direct_send_photo(photo_path, thread_ids=[thread_id])
                                                    except Exception as send_exc:
                                                        if _item_ack_403_signature(send_exc):
                                                            _pause_after_item_ack_403(send_exc, "direct_send_photo", thread_id)
                                                            continue
                                                        raise

                                                    dp_card = (
                                                        f"📸✨ **𝗛𝗗 𝗗𝗣 𝗙𝗘𝗧𝗖𝗛𝗘𝗗** ✨📸\n\n"
                                                        f"👤 𝗨𝗦𝗘𝗥 ➜ {fix_mention(target_name)}\n\n"
                                                        f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}"
                                                    )
                                                    safe_send_message(thread_id, dp_card)

                                                    if os.path.exists(photo_path):
                                                        os.remove(photo_path)
                                            except Exception:
                                                safe_send_message(thread_id, f"❌ Failed to fetch DP for {fix_mention(target_name)}!")
                                            continue
                                        elif command_token in {"!profile", "!user"}:
                                            parts = command_text.split()
                                            target_name = parts[1].lstrip("@") if len(parts) > 1 else sender_username
                                            try:
                                                u_info = cl.user_info_by_username(target_name)
                                                if u_info:
                                                    def format_count(count):
                                                        if count >= 1_000_000:
                                                            return f"{count / 1_000_000:.1f}M"
                                                        elif count >= 1_000:
                                                            return f"{count / 1_000:.1f}k"
                                                        return str(count)

                                                    tracked_since = "Not recorded by this bot"
                                                    try:
                                                        with SessionLocal() as db:
                                                            tracked = db.query(UserProfile).filter(UserProfile.username == target_name.lower()).first()
                                                            if tracked and tracked.join_date:
                                                                tracked_since = tracked.join_date.strftime("%Y-%m-%d")
                                                    except Exception:
                                                        pass

                                                    profile_card = (
                                                        f"👤✨ **𝗨𝗦𝗘𝗥 𝗣𝗥𝗢𝗙𝗜𝗟𝗘 𝗗𝗘𝗧𝗔𝗜𝗟𝗦** ✨👤\n\n"
                                                        f"📌 **𝗡𝗮𝗺𝗲** ➜ {u_info.full_name or 'Not Provided'}\n"
                                                        f"🆔 **𝗨𝘀𝗲𝗿𝗻𝗮𝗺𝗲** ➜ @{u_info.username}\n"
                                                        f"🔢 **𝗨𝘀𝗲𝗿 𝗜𝗗** ➜ `{u_info.pk}`\n"
                                                        f"🗓️ **𝗙𝗶𝗿𝘀𝘁 𝗥𝗲𝗰𝗼𝗿𝗱𝗲𝗱** ➜ {tracked_since}\n"
                                                        f"👥 **𝗙𝗼𝗹𝗹𝗼𝘄𝗲𝗿𝘀** ➜ {format_count(u_info.follower_count)}\n"
                                                        f"🫂 **𝗙𝗼𝗹𝗹𝗼𝘄𝗶𝗻𝗴** ➜ {format_count(u_info.following_count)}\n"
                                                        f"📸 **𝗧𝗼𝘁𝗮𝗹 𝗣𝗼𝘀𝘁𝘀** ➜ {u_info.media_count}\n"
                                                        f"🔗 **𝗕𝗶𝗼** ➜ {u_info.biography.replace('\n', ' ') if u_info.biography else 'No Bio'}\n"
                                                        f"🔒 **𝗣𝗿𝗶𝘃𝗮𝘁𝗲** ➜ {'Yes 🔒' if u_info.is_private else 'No 🟢'}\n\n"
                                                        f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}"
                                                    )
                                                    safe_send_message(thread_id, profile_card)
                                            except Exception as e:
                                                safe_send_message(thread_id, f"❌ Error fetching profile: {str(e)}")
                                            continue
                                        elif command_token == "!stats":
                                            parts = command_text.split()
                                            target_name = parts[1].lstrip("@") if len(parts) > 1 else sender_username
                                            stats_msg = ModerationEngine.get_user_stats(cl, target_name)
                                            safe_send_message(thread_id, stats_msg)
                                            continue
                                        elif command_lower == "!botinfo":
                                            info_card = (
                                                f"🤖✨ **𝗕𝗢𝗧 𝗜𝗡𝗙𝗢𝗥𝗠𝗔𝗧𝗜𝗢𝗡** ✨🤖\n\n"
                                                f"⚡ **Status** ➜ ONLINE & ACTIVE (Instant Fast Reply)\n"
                                                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}"
                                            )
                                            safe_send_message(thread_id, info_card)
                                            continue
                                        elif command_token.startswith("!"):
                                            safe_send_message(thread_id, f"❓ Unknown command: {command_token}\nUse 𝗦𝗠𝗪🚩 !help to see the available commands.")
                                            continue

                            except Exception as message_error:
                                # Isolate malformed shared URLs / unsupported message payloads.
                                # Log only a short ID/type, then keep processing other messages.
                                failed_id = str(getattr(last_msg, "id", "") or "unknown")[:80]
                                logging.exception("message_processing_error message_id=%s error_type=%s", failed_id, type(message_error).__name__)
                                LAST_POLL_ERROR = f"message processing error: {type(message_error).__name__}"
                                continue

                    is_first_run = False
                    # Reset the 403 backoff only after a complete successful poll cycle.
                    consecutive_forbidden_errors = 0

                except (LoginRequired, ChallengeRequired, BadPassword) as auth_error:
                    print(f"[STOP] Instagram login/challenge required ({type(auth_error).__name__}).")
                    return
                except (PleaseWaitFewMinutes, ClientThrottledError) as limit_error:
                    print(f"[STOP] Instagram rate limit ({type(limit_error).__name__}).")
                    return
                except Exception as e:
                    LAST_POLL_ERROR = type(e).__name__
                    logging.exception("poll_loop_error")
                    error_text = str(e).lower()
                    http_status, api_status_code, error_code, action = _instagram_error_signature(e)
                    if (http_status == 403 or api_status_code == 403) and action == "item_ack" and error_code == 1404006:
                        # A 403 is a server rejection, not a transient local exception. Back off
                        # the polling call itself, not only outgoing replies. Never relogin/resend.
                        consecutive_forbidden_errors += 1
                        backoff_seconds = min(300 * (2 ** min(consecutive_forbidden_errors - 1, 3)), 1800)
                        SEND_COOLDOWN_UNTIL = max(SEND_COOLDOWN_UNTIL, time.time() + backoff_seconds)
                        LAST_POLL_ERROR = f"item_ack 403/1404006; poll retry in {backoff_seconds}s"
                        _pause_after_item_ack_403(e, "poll_loop")
                        logging.warning(
                            "poll_backoff_seconds=%s consecutive_forbidden_errors=%s",
                            backoff_seconds, consecutive_forbidden_errors
                        )
                        print(f"[!] Polling paused for {backoff_seconds}s after item_ack 403; session kept, no automatic login/resend.")
                        time.sleep(backoff_seconds)
                        continue
                    is_forbidden_403 = (
                        type(e).__name__ == "ClientForbiddenError"
                        or "status_code\":\"403\"" in error_text
                        or "status_code': 403" in error_text
                        or ("403" in error_text and "forbidden" in error_text)
                    )
                    if is_forbidden_403:
                        consecutive_forbidden_errors += 1
                        # 5m, 10m, 20m, then cap at 30m between retries.
                        backoff_seconds = min(300 * (2 ** min(consecutive_forbidden_errors - 1, 3)), 1800)
                        LAST_POLL_ERROR = f"{type(e).__name__} (403); retry in {backoff_seconds}s"
                        logging.error(
                            "Instagram returned 403/forbidden during polling; keeping the process alive, "
                            "preserving the current session, and retrying after %s seconds (consecutive=%s).",
                            backoff_seconds, consecutive_forbidden_errors
                        )
                        print(
                            f"[!] Instagram returned 403 ({type(e).__name__}); "
                            f"pausing polling for {backoff_seconds}s before retry. "
                            "No automatic re-login will be attempted."
                        )
                        time.sleep(backoff_seconds)
                        continue
                    time.sleep(POLL_INTERVAL)

                time.sleep(POLL_INTERVAL)

        except (LoginRequired, ChallengeRequired, BadPassword) as auth_error:
            return
        except (PleaseWaitFewMinutes, ClientThrottledError) as limit_error:
            return
        except Exception as e:
            LAST_POLL_ERROR = type(e).__name__
            http_status, api_status_code, error_code, action = _instagram_error_signature(e)
            error_text = str(e).casefold()
            is_unauthorized = (
                http_status == 401 or api_status_code == 401
                or "401 client error" in error_text
                or "unauthorized for url" in error_text
                or "clientunauthorizederror" in type(e).__name__.casefold()
            )
            if is_unauthorized:
                AUTH_FAILURE_COUNT += 1
                # Do not hammer Instagram's GraphQL endpoint with repeated logins.
                # 5m, 10m, 20m, then cap at 30m; successful connection resets this counter.
                backoff_seconds = min(300 * (2 ** min(AUTH_FAILURE_COUNT - 1, 3)), 1800)
                LAST_POLL_ERROR = f"Instagram authentication rejected (401); retry in {backoff_seconds}s"
                logging.error(
                    "instagram_auth_401 retry_backoff_seconds=%s consecutive_failures=%s exception_type=%s",
                    backoff_seconds, AUTH_FAILURE_COUNT, type(e).__name__
                )
                print(
                    f"[!] Instagram returned 401 Unauthorized ({type(e).__name__}). "
                    f"Pausing {backoff_seconds}s before retry; check whether the Session ID is still valid. "
                    "The bot will not repeatedly log in every few seconds."
                )
                time.sleep(backoff_seconds)
                continue
            logging.exception("critical_connection_or_login_error")
            print(f"[!] Critical error: {type(e).__name__}: {e}")
            time.sleep(min(60, POLL_INTERVAL * 2))


if __name__ == "__main__":
    start_bot()
