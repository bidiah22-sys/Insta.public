import os
import re
import time
import json
import logging
import shutil
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
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
# 👇 यहाँ अपनी इंस्टाग्राम की असली SESSION ID डालें 👇
# -----------------------------------------------------------------
INSTAGRAM_SESSION_ID = "24360649417%3AMyFn5xc4nFl1pK%3A10%3AAYmkTFuXTw6o0giXQ0QZanRJ7wB1fLeT7IqKpfMsHg".strip()

BOT_USERNAME = os.getenv("BOT_USERNAME", "pookieee_bot")
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "")
AUTHORIZED_DEVS = ["fx_smw","aat_nnk25"]
DEV_LINE = "👑 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 : 𝗦𝗠𝗪🚩"
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///bot_database.db")
POLL_INTERVAL = 1  # Instant fast-reply loop interval (optimized for speed)
LOCAL_AUTO_REPLIES = True
DEVELOPER_DISPLAY = "𝗦𝗠𝗪🚩"
SAFE_MODE = os.getenv("SAFE_MODE", "1").lower() in {"1", "true", "yes", "on"}
STARTED_AT = time.time()
TOTAL_SEEN_MESSAGES = 0
LAST_SUCCESSFUL_POLL = None
LAST_POLL_ERROR = "None"
logging.basicConfig(filename="bot_runtime.log", level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

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
            f"👑 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 : 𝗦𝗠𝗪🚩")


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
                    f"👑 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 : 𝗦𝗠𝗪🚩"
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


def normalize_for_moderation(text: str) -> str:
    text = (text or "").casefold()
    text = re.sub(r"[\u200b-\u200f\ufeff]", "", text)
    text = re.sub(r"[\W_]+", "", text, flags=re.UNICODE)
    return text


def detect_abuse_reason(text: str) -> str | None:
    raw = (text or "").casefold()
    normalized = normalize_for_moderation(raw)
    if not raw.strip():
        return None
    for pattern in BAD_WORD_PATTERNS:
        match = re.search(pattern, raw, re.IGNORECASE)
        if match:
            return f"Matched word/phrase: {match.group(0)[:80]}"
    for word in sorted(RESTRICTED_WORDS, key=len, reverse=True):
        compact = normalize_for_moderation(word)
        if compact and compact in normalized:
            return f"Matched word/phrase: {word} (normalized/obfuscated match)"
    return None


def detect_link_type(text: str) -> str | None:
    value = (text or "").casefold().strip()
    if not value:
        return None
    url_pattern = r"(?:https?://|www\.)[^\s<>]+|\b(?:instagram\.com|instagr\.am|bit\.ly|tinyurl\.com|t\.me|wa\.me|youtu\.be|youtube\.com|linktr\.ee|facebook\.com|x\.com|tiktok\.com)/[^\s<>]*"
    if re.search(url_pattern, value, re.IGNORECASE):
        if re.search(r"(?:instagram\.com|instagr\.am)/(?:reel|reels)(?:/|\b)", value, re.IGNORECASE):
            return "Instagram Reel Link"
        if re.search(r"(?:instagram\.com|instagr\.am)/(?:p|tv)/", value, re.IGNORECASE):
            return "Instagram Post / Video Link"
        return "External Link"
    if re.search(r"\b[a-z0-9-]+\.(?:com|net|org|xyz|top|info|site|link|io|me|co|in|app|gg)(?:/[^\s]*)?", value, re.IGNORECASE):
        return "Bare Domain Link"
    return None


def start_bot():
    global LOCKDOWN_MODE, SHADOWBANNED_USERS, TARGETED_USERS, USER_LAST_MESSAGE_TIME, SAFE_MODE, ANTISPAM_ENABLED, ANTISPAM_LIMIT
    init_db()
    restore_runtime_state()

    while True:
        try:
            print("[*] Connecting to Instagram via Session ID...")
            cl = Client()
            cl.set_user_agent(
                "Mozilla/5.0 (Linux; Android 11; SM-G998B Build/RP1A.200720.012; wv) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/115.0.5790.166 "
                "Mobile Safari/537.36 Instagram 290.0.0.13.76 Android"
            )

            if INSTAGRAM_SESSION_ID and INSTAGRAM_SESSION_ID != "PASTE_YOUR_SESSION_ID_HERE":
                cl.login_by_sessionid(INSTAGRAM_SESSION_ID)
                print("[+] Successfully logged in via Session ID!")
            else:
                print("[!] Error: Please provide a valid INSTAGRAM_SESSION_ID!")
                time.sleep(10)
                continue

            print("\n╔══════════════════════════════════════╗")
            print("║       ✦  𝗦𝗠𝗪  𝗕𝗢𝗧  ✦             ║")
            print("║       STATUS: CONNECTED              ║")
            print("║   Group scan loop: STARTING          ║")
            print("╚══════════════════════════════════════╝\n")
            print(f"[+] BOT @{BOT_USERNAME} logged in; polling enabled.")

            seen_message_ids = set()
            group_members_state = {}
            ever_seen_members = set()
            member_name_cache = {}
            welcomed_recently = {}
            recent_sent_texts = {}
            user_message_windows = {}
            duplicate_message_windows = {}
            active_announced_threads = set()
            initialized_message_threads = set()

            last_morning_wish_date = ""
            last_night_wish_date = ""
            is_first_run = True

            def safe_send_message(thread_id, text_content):
                # Normalize every card to exactly one developer footer.
                footer = "👑 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ 𝗦𝗠𝗪🚩"
                lines = [line for line in str(text_content).splitlines()
                         if not re.search(r"DEVELOPER|𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥|DEV ➜", line, re.IGNORECASE)]
                text_content = "\n".join(lines).rstrip() + "\n\n" + footer
                current_time = time.time()
                if thread_id in recent_sent_texts:
                    last_text, last_time = recent_sent_texts[thread_id]
                    if last_text == text_content and (current_time - last_time < 2):
                        return False
                recent_sent_texts[thread_id] = (text_content, current_time)
                try:
                    cl.direct_send(text_content, thread_ids=[thread_id])
                    time.sleep(0.05)
                    return True
                except Exception as e:
                    logging.exception("message_send_failed thread=%s", thread_id)
                    print(f"[!] Send error: {type(e).__name__}: {e}")
                    return False

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
                            f"👑 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 : 𝗦𝗠𝗪🚩"
                        )
                        safe_send_message(thread_id, kick_card)
                except Exception:
                    pass

            while True:
                global TOTAL_SEEN_MESSAGES, LAST_SUCCESSFUL_POLL, LAST_POLL_ERROR
                try:
                    threads = list(cl.direct_threads(amount=500) or [])  # Expand inbox scan; API may still cap or omit older threads.
                    logging.info("thread_scan_ok count=%d", len(threads))
                    LAST_SUCCESSFUL_POLL = datetime.now(timezone.utc).isoformat()
                    LAST_POLL_ERROR = "None"
                    current_time_loop = time.time()

                    now = datetime.now(ZoneInfo("Asia/Kolkata"))
                    current_hour = now.hour
                    current_minute = now.minute
                    current_date_str = now.strftime("%Y-%m-%d")

                    for thread in threads:
                        if not getattr(thread, "is_group", False):
                            logging.debug("thread_skipped_not_group id=%s", getattr(thread, "id", "?"))
                            continue

                        thread_id = thread.id
                        gc_admins = []
                        try:
                            raw_admins = getattr(thread, "admin_user_ids", None) or getattr(thread, "admin_users", None) or []
                            for admin in raw_admins:
                                candidate = (getattr(admin, "pk", None) or getattr(admin, "user_id", None)
                                             or getattr(admin, "id", None) or admin)
                                if candidate is not None:
                                    gc_admins.append(str(candidate).strip())
                        except Exception:
                            logging.exception("admin_list_read_failed thread=%s", thread_id)
                            gc_admins = []

                        bot_pk = str(getattr(cl, "user_id", "")).strip()
                        users = list(getattr(thread, "users", []) or [])
                        gc_name = (getattr(thread, "thread_title", None) or getattr(thread, "title", None) or getattr(thread, "name", None) or "Unknown GC")
                        # Fail closed: only enable a GC when Instagram's thread snapshot explicitly
                        # identifies this account as an administrator. Log enough context to diagnose
                        # stale/incomplete admin metadata without enabling non-admin groups.
                        admin_match = bool(bot_pk) and bot_pk in set(gc_admins)
                        if not admin_match:
                            logging.warning(
                                "group_skipped_not_admin_or_admin_metadata_missing thread=%s title=%r bot_id=%r admin_ids=%r",
                                thread_id, gc_name, bot_pk, gc_admins
                            )
                            continue
                        logging.info("group_admin_verified thread=%s title=%r bot_id=%r", thread_id, gc_name, bot_pk)

                        # Announce only after confirming the bot is a GC admin.
                        if thread_id not in active_announced_threads:
                            active_card = (
                                "✦ 𝗦𝗠𝗪 𝗕𝗢𝗧 ✦\n"
                                "𝗦𝗬𝗦𝗧𝗘𝗠 𝗢𝗡𝗟𝗜𝗡𝗘  •  ● ACTIVE\n\n"
                                "🛡️ 𝗚𝗥𝗢𝗨𝗣 𝗦𝗘𝗖𝗨𝗥𝗜𝗧𝗬 𝗥𝗘𝗔𝗗𝗬\n"
                                "⚙️ 𝗔𝗟𝗟 𝗦𝗬𝗦𝗧𝗘𝗠𝗦 𝗜𝗡𝗜𝗧𝗜𝗔𝗟𝗜𝗭𝗘𝗗\n\n"
                                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                "👑 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ 𝗦𝗠𝗪🚩"
                            )
                            try:
                                if safe_send_message(thread_id, active_card):
                                    active_announced_threads.add(thread_id)
                            except Exception as announce_error:
                                logging.warning("startup_card_failed thread=%s error=%s", thread_id, announce_error)
                        record_group_snapshot(thread_id, str(gc_name), users)
                        current_members = {str(getattr(u, "pk", "")) for u in users if getattr(u, "pk", None)}
                        for member in users:
                            member_pk = str(getattr(member, "pk", "") or "")
                            member_name = getattr(member, "username", None) or getattr(member, "full_name", None) or "Unknown member"
                            if member_pk:
                                member_name_cache[member_pk] = str(member_name)

                        admin_mentions_tag = get_admin_mentions_str(users, gc_admins)

                        if current_hour == 6 and last_morning_wish_date != current_date_str:
                            last_morning_wish_date = current_date_str
                            morning_card = (
                                f"🌅✨ **𝗚𝗢𝗢𝗗 𝗠𝗢𝗥𝗡𝗜𝗡𝗚 𝗘𝗩𝗘𝗥𝗬𝗢𝗡𝗘!** ✨🌅\n\n"
                                f"🌻 𝗛𝗔𝗩𝗘 𝗔𝗡 𝗔𝗠𝗔𝗭𝗜𝗡𝗚 & 𝗣𝗥𝗢𝗗𝗨𝗖𝗧𝗜𝗩𝗘 𝗗𝗔𝗬!\n"
                                f"☕ 𝗦𝗣𝗥𝗘𝗔𝗗 𝗣𝗢𝗦𝗜𝗧𝗜𝗩𝗜𝗧𝗬 𝗜𝗡 𝗧𝗛𝗘 𝗚𝗖 🔥\n\n"
                                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}"
                            )
                            safe_send_message(thread_id, morning_card)

                        if current_hour == 23 and last_night_wish_date != current_date_str:
                            last_night_wish_date = current_date_str
                            night_card = (
                                f"🌙✨ **𝗚𝗢𝗢𝗗 𝗡𝗜𝗚𝗛𝗧 𝗚𝗖 𝗙𝗔𝗠𝗜𝗟𝗬!** ✨🌙\n\n"
                                f"😴 𝗧𝗜𝗠𝗘 𝗧𝗢 𝗥𝗘𝗦𝗧 & 𝗥𝗘𝗖𝗛𝗔𝗥𝗚𝗘!\n"
                                f"💫 𝗦𝗪𝗘𝗘𝗧 𝗗𝗥𝗘𝗔𝗠𝗦 𝗘𝗩𝗘𝗥𝗬𝗢𝗡𝗘 🌙\n\n"
                                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}"
                            )
                            safe_send_message(thread_id, night_card)

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
                            # Establish a baseline: never replay messages already present at startup.
                            for existing_message in messages:
                                existing_id = str(getattr(existing_message, "id", "") or "")
                                if existing_id:
                                    seen_message_ids.add(existing_id)
                            initialized_message_threads.add(thread_id)
                            continue
                        for last_msg in reversed(messages):
                            message_id = str(getattr(last_msg, "id", "") or "")

                            if message_id and message_id not in seen_message_ids:
                                seen_message_ids.add(message_id)
                                TOTAL_SEEN_MESSAGES += 1

                                text = str(getattr(last_msg, "text", "") or "").strip()
                                text_lower = text.lower()
                                sender_id = str(getattr(last_msg, "user_id", ""))

                                sender_username = "User"
                                message_user = getattr(last_msg, "user", None)
                                embedded_username = getattr(message_user, "username", None)
                                if embedded_username:
                                    sender_username = str(embedded_username)
                                else:
                                    for u in users:
                                        if str(getattr(u, "pk", "")) == sender_id:
                                            sender_username = str(getattr(u, "username", "User") or "User")
                                            break

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
                                    if normalized_msg and not text_lower.startswith("!"):
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

                                if text_lower == "!rules":
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
                                link_type = detect_link_type(text)
                                link_violation = bool(link_type)
                                if abuse_reason or link_violation:
                                    warns, trust = ModerationEngine.add_warning(sender_username)
                                    reason = abuse_reason or f"Unauthorized {link_type}"
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
                                            f"🚫 𝗥𝗘𝗔𝗦𝗢𝗡   ➜ {reason}\n"
                                            + (f"🗣️ 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗 𝗧𝗘𝗫𝗧 ➜ {text[:180]}\n" if abuse_reason else "")
                                            + f"⚠️ 𝗪𝗔𝗥𝗡𝗜𝗡𝗚𝗦 ➜ {warns}/2\n"
                                            f"📉 𝗧𝗥𝗨𝗦𝗧 𝗦𝗖𝗢𝗥𝗘 ➜ {trust}%\n\n"
                                            f"📢 **𝗔𝗗𝗠𝗜𝗡 𝗔𝗟𝗘𝗥𝗧** ➜ {admin_mentions_tag}\n\n"
                                            f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}"
                                        )
                                        safe_send_message(thread_id, warn_card)
                                    continue

                                if LOCAL_AUTO_REPLIES and not text_lower.startswith("!"):
                                    answer = None
                                    if any(k in text_lower for k in ["bot help", "bot kya", "commands", "command list"]):
                                        answer = "I am the SMW group assistant. Public command: !rules. Management commands are restricted to authorized developers."
                                    elif "good morning" in text_lower or re.search(r"(?<!\w)gm(?!\w)", text_lower) or "शुभ प्रभात" in text_lower:
                                        answer = f"Good morning, {fix_mention(sender_username)}! Please follow the group rules and enjoy. 🌞"
                                    elif "good night" in text_lower or re.search(r"(?<!\w)gn(?!\w)", text_lower) or "शुभ रात्रि" in text_lower:
                                        answer = f"Good night, {fix_mention(sender_username)}! 🌙"
                                    elif any(k in text_lower for k in ["thank you", "thanks"]):
                                        answer = "You're welcome! 😊"
                                    if answer:
                                        safe_send_message(thread_id, answer)
                                        continue

                                command_token = text_lower.split(maxsplit=1)[0] if text_lower else ""
                                is_trying_command = command_token.startswith("!") and command_token != "!rules"

                                if is_trying_command and not is_dev:
                                    continue

                                if is_dev and text_lower.startswith("!"):
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
                                    elif command_token == "!deadlist":
                                        db = SessionLocal()
                                        try:
                                            tracked = {str(r.user_id): r for r in db.query(GroupMemberAnalytics).filter_by(group_id=str(thread_id)).all()}
                                            candidates = []
                                            for u in users:
                                                uid = str(getattr(u, "pk", "") or "")
                                                uname = getattr(u, "username", None) or "unknown"
                                                row = tracked.get(uid)
                                                if uid and (row is None or (row.message_count or 0) == 0):
                                                    candidates.append(f"@{uname} — no messages recorded")
                                            report = "\n".join(candidates[:35]) or "No zero-recorded-activity members found."
                                            safe_send_message(thread_id, f"🧊 **𝗗𝗘𝗔𝗗 / 𝗜𝗡𝗔𝗖𝗧𝗜𝗩𝗘 𝗖𝗔𝗡𝗗𝗜𝗗𝗔𝗧𝗘𝗦**\nGC: {gc_name}\nListed: {min(len(candidates), 35)}\n\n{report}\n\n⚠️ 𝗔𝗖𝗧𝗜𝗩𝗜𝗧𝗬 𝗥𝗘𝗖𝗢𝗥𝗗 𝗡𝗔𝗛𝗜 𝗠𝗜𝗟𝗔 — 𝗥𝗘𝗠𝗢𝗩𝗘 𝗞𝗔𝗥𝗡𝗘 𝗦𝗘 𝗣𝗘𝗛𝗟𝗘 𝗥𝗘𝗩𝗜𝗘𝗪 𝗞𝗔𝗥𝗘𝗡")
                                        finally:
                                            db.close()
                                        continue
                                    elif command_token == "!gcuser":
                                        parts = text.split(maxsplit=1)
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
                                    if text_lower == "!analytics":
                                        db = SessionLocal()
                                        try:
                                            total_users = db.query(UserProfile).count()
                                            total_msgs = db.query(UserProfile).with_entities(UserProfile.total_messages).all()
                                            total_warns = db.query(UserProfile).with_entities(UserProfile.warning_count).all()
                                            event_count = db.query(SecurityLog).count()
                                            safe_send_message(thread_id, f"📊 𝗦𝗠𝗪 𝗕𝗢𝗧 𝗜𝗡𝗙𝗢𝗥𝗠𝗔𝗧𝗜𝗢𝗡\n\n𝗦𝗧𝗔𝗧𝗨𝗦 ➜ 𝗢𝗡𝗟𝗜𝗡𝗘 & 𝗔𝗖𝗧𝗜𝗩𝗘\n🤖 𝗕𝗢𝗧 ➜ 𝗦𝗠𝗪\n👥 𝗧𝗥𝗔𝗖𝗞𝗘𝗗 𝗨𝗦𝗘𝗥𝗦 ➜ {total_users}\n💬 𝗧𝗥𝗔𝗖𝗞𝗘𝗗 𝗠𝗘𝗦𝗦𝗔𝗚𝗘𝗦 ➜ {sum((x[0] or 0) for x in total_msgs)}\n⚠️ 𝗪𝗔𝗥𝗡𝗜𝗡𝗚𝗦 ➜ {sum((x[0] or 0) for x in total_warns)}\n📋 𝗔𝗨𝗗𝗜𝗧 𝗘𝗩𝗘𝗡𝗧𝗦 ➜ {event_count}\n📨 𝗠𝗘𝗦𝗦𝗔𝗚𝗘𝗦 𝗧𝗛𝗜𝗦 𝗥𝗨𝗡 ➜ {TOTAL_SEEN_MESSAGES}\n\n👑 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 : 𝗦𝗠𝗪🚩")
                                        finally:
                                            db.close()
                                        continue
                                    elif text_lower == "!session":
                                        safe_send_message(thread_id, f"🔐 Session health\nSession ID configured: {'YES' if INSTAGRAM_SESSION_ID else 'NO'}\nLast successful poll: {LAST_SUCCESSFUL_POLL or 'not yet'}\nLast error type: {LAST_POLL_ERROR}")
                                        continue
                                    elif text_lower == "!safe_mode":
                                        SAFE_MODE = not SAFE_MODE
                                        safe_send_message(thread_id, f"🛡️ Safe mode is now {'ON' if SAFE_MODE else 'OFF'}. Auto-removal actions should be reviewed before use.")
                                        continue
                                    elif text_lower in {"!panel", "!status"}:
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
                                    elif text_lower == "!logs":
                                        db = SessionLocal()
                                        try:
                                            rows = db.query(SecurityLog).order_by(SecurityLog.id.desc()).limit(5).all()
                                            report = "\n".join(f"#{r.id} {r.event_type} @{r.username}: {(r.details or '')[:100]}" for r in rows) or "No audit events yet."
                                        finally:
                                            db.close()
                                        safe_send_message(thread_id, "📋 Recent audit logs\n" + report[:1500])
                                        continue
                                    elif text_lower == "!backup":
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
                                    elif text_lower == "!help":
                                        safe_send_message(thread_id, "Developer-only commands: !help !panel !status !analytics !gc !gcanalytics !gcs !gcuser [@user] !session !safe_mode !logs !backup !lockdown !unlock !godmode !target @user/remove/clear/list !shadowban @user/remove/clear/list !nuke @user !resetwarn @user/all !unwarn @user !antispam on/off/status/limit N !report !inactive [days] !tagall !active !members !admins !dp [@user] !profile [@user] !user [@user] !stats [@user] !botinfo. Public: !rules.")
                                        continue
                                    elif text_lower == "!lockdown":
                                        LOCKDOWN_MODE = True
                                        save_runtime_state()
                                        safe_send_message(thread_id, "🔒 𝗟𝗢𝗖𝗞𝗗𝗢𝗪𝗡 𝗔𝗖𝗧𝗜𝗩𝗘\n\n🛡️ Non-admin members will be removed on new messages.")
                                        continue
                                    elif text_lower == "!unlock":
                                        LOCKDOWN_MODE = False
                                        save_runtime_state()
                                        safe_send_message(thread_id, "🔓 𝗟𝗢𝗖𝗞𝗗𝗢𝗪𝗡 𝗗𝗜𝗦𝗔𝗕𝗟𝗘𝗗\n\n🟢 Normal group activity restored.")
                                        continue
                                    elif text_lower == "!godmode":
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
                                    elif text_lower.startswith("!target"):
                                        parts = text.split()
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
                                    elif text_lower.startswith("!shadowban"):
                                        parts = text.split()
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
                                    elif text_lower.startswith("!nuke"):
                                        parts = text.split()
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
                                    elif command_token in {"!resetwarn", "!unwarn"}:
                                        parts = text.split()
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
                                        parts = text.split()
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
                                        parts = text.split()
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
                                    elif text_lower in ("!tagall", "!active", "!members"):
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
                                    elif text_lower == "!admins":
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
                                        parts = text.split()
                                        target_name = parts[1].lstrip("@") if len(parts) > 1 else sender_username
                                        try:
                                            u_info = cl.user_info_by_username(target_name)
                                            if u_info:
                                                dp_url = getattr(getattr(u_info, "hd_profile_pic_url_info", None), "url", None) or getattr(u_info, "profile_pic_url_hd", None) or u_info.profile_pic_url
                                                photo_path = cl.photo_download_by_url(dp_url, filename=f"{target_name}_dp.jpg")
                                                cl.direct_send_photo(photo_path, thread_ids=[thread_id])

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
                                        parts = text.split()
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
                                        parts = text.split()
                                        target_name = parts[1].lstrip("@") if len(parts) > 1 else sender_username
                                        stats_msg = ModerationEngine.get_user_stats(cl, target_name)
                                        safe_send_message(thread_id, stats_msg)
                                        continue
                                    elif text_lower == "!botinfo":
                                        info_card = (
                                            f"🤖✨ **𝗕𝗢𝗧 𝗜𝗡𝗙𝗢𝗥𝗠𝗔𝗧𝗜𝗢𝗡** ✨🤖\n\n"
                                            f"⚡ **Status** ➜ ONLINE & ACTIVE (Instant Fast Reply)\n"
                                            f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}"
                                        )
                                        safe_send_message(thread_id, info_card)
                                        continue
                                    elif command_token.startswith("!"):
                                        safe_send_message(thread_id, f"❓ Unknown command: {command_token}\nUse !help to see the available commands.")
                                        continue

                    is_first_run = False

                except (LoginRequired, ChallengeRequired, BadPassword) as auth_error:
                    print(f"[STOP] Instagram login/challenge required ({type(auth_error).__name__}).")
                    return
                except (PleaseWaitFewMinutes, ClientThrottledError) as limit_error:
                    print(f"[STOP] Instagram rate limit ({type(limit_error).__name__}).")
                    return
                except Exception as e:
                    LAST_POLL_ERROR = type(e).__name__
                    logging.exception("poll_loop_error")
                    time.sleep(POLL_INTERVAL)

                time.sleep(POLL_INTERVAL)

        except (LoginRequired, ChallengeRequired, BadPassword) as auth_error:
            return
        except (PleaseWaitFewMinutes, ClientThrottledError) as limit_error:
            return
        except Exception as e:
            print(f"[!] Critical error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    start_bot()
