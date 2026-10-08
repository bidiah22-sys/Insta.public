import os
import re
import time
import logging
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from instagrapi import Client
from instagrapi.exceptions import (
    PleaseWaitFewMinutes,
    ClientThrottledError,
    LoginRequired,
    ChallengeRequired,
    BadPassword,
)
from sqlalchemy import create_engine, Column, String, Integer, DateTime, Text, func
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

# ================================================================
# SMW G-SECURITY — NORMAL / FAST / LIGHTWEIGHT BUILD
# ================================================================
# Session ID is intentionally read from the environment only.
INSTAGRAM_SESSION_ID = os.getenv("INSTAGRAM_SESSION_ID", "19088037883%3AHtKEHjEIjET7Sz%3A28%3AAYn98pLlzJ1fRplqlIEITXLg9JwhxKHjUlZ-618v3A").strip()
BOT_USERNAME = os.getenv("BOT_USERNAME", "pookieee_bot").strip()
AUTHORIZED_DEVS = {"fx_smw", "aat_nnk25"}
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///bot_database.db")
POLL_INTERVAL = max(3, int(os.getenv("POLL_INTERVAL", "3")))
TIMEZONE = ZoneInfo(os.getenv("TIMEZONE", "Asia/Kolkata"))
DEV_LINE = "👑 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ 𝗦𝗠𝗪🚩"
STARTED_AT = time.time()
LAST_SUCCESSFUL_POLL = None
LAST_POLL_ERROR = "None"
TOTAL_SEEN_MESSAGES = 0

logging.basicConfig(
    filename="bot_runtime.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

BAD_WORD_PATTERNS = [
    r"\bm[\.\_\-\s]*c\b", r"\bb[\.\_\-\s]*c\b",
    r"\bm[\.\_\-\s]*k[\.\_\-\s]*c\b",
    r"\bt[\.\_\-\s]*m[\.\_\-\s]*k[\.\_\-\s]*c\b",
    r"madar\s*chod", r"bhen\s*chod", r"behen\s*chod",
    r"bhosd\w*", r"chut\w*", r"gand\w*", r"gaand\w*",
    r"lund\w*", r"lauda\w*", r"lawda\w*", r"randi\w*",
    r"bhadwa\w*", r"bhadwe\w*", r"bsdk\w*", r"harami\w*",
    r"f[\.\_\-\s]*u[\.\_\-\s]*c[\.\_\-\s]*k\w*",
]

RESTRICTED_WORDS = {
    "mc", "bc", "mkc", "tmkc", "bsdk", "bsdke", "chutiya", "chutiye",
    "chutiyap", "gandu", "gaandu", "lauda", "luda", "lawda", "lund",
    "chut", "chuth", "gand", "gaand", "randi", "randwa", "bhadwa",
    "bhadwe", "harami", "haramkhor", "kamine", "kamina", "saala", "saale",
    "madarchod", "maderchod", "madar-chod", "bhenchod", "behenchod",
    "bhen-chod", "behen-chod", "bhosdike", "bhosdi", "bhosda", "fuck",
    "fucking", "fucker", "motherfucker", "bitch", "bastard", "asshole",
}

Base = declarative_base()


def utc_now():
    return datetime.now(timezone.utc)


def fix_mention(username):
    if not username:
        return ""
    clean = str(username).strip().lstrip("@")
    return f"@{clean}" if clean else ""


class GroupAnalytics(Base):
    __tablename__ = "group_analytics"
    group_id = Column(String, primary_key=True)
    group_name = Column(String, nullable=False, default="Unknown GC")
    first_seen = Column(DateTime, default=utc_now)
    last_activity = Column(DateTime, default=utc_now)


class GroupMemberAnalytics(Base):
    __tablename__ = "group_member_analytics"
    group_id = Column(String, primary_key=True)
    user_id = Column(String, primary_key=True)
    username = Column(String, nullable=False, default="User")
    message_count = Column(Integer, default=0)
    first_seen = Column(DateTime, default=utc_now)
    last_activity = Column(DateTime, default=utc_now)


class WarningHistory(Base):
    __tablename__ = "warning_history"
    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(String, index=True)
    user_id = Column(String, index=True)
    username = Column(String, index=True)
    reason = Column(Text)
    detected_text = Column(Text)
    warning_number = Column(Integer, default=1)
    created_at = Column(DateTime, default=utc_now, index=True)


class GroupUserState(Base):
    __tablename__ = "group_user_state"
    group_id = Column(String, primary_key=True)
    user_id = Column(String, primary_key=True)
    username = Column(String, nullable=False, default="User")
    warning_count = Column(Integer, default=0)
    first_seen = Column(DateTime, default=utc_now)
    last_active = Column(DateTime, default=utc_now)


engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)


def init_db():
    Base.metadata.create_all(engine)


def record_activity(group_id, user_id, username):
    now = utc_now()
    db = SessionLocal()
    try:
        group = db.query(GroupAnalytics).filter_by(group_id=str(group_id)).first()
        if group is None:
            group = GroupAnalytics(group_id=str(group_id), group_name="Unknown GC")
            db.add(group)
        group.last_activity = now

        row = db.query(GroupMemberAnalytics).filter_by(
            group_id=str(group_id), user_id=str(user_id)
        ).first()
        if row is None:
            row = GroupMemberAnalytics(
                group_id=str(group_id), user_id=str(user_id),
                username=str(username or "User").lstrip("@"), message_count=0,
                first_seen=now, last_activity=now,
            )
            db.add(row)
        row.username = str(username or row.username).lstrip("@")
        row.message_count = (row.message_count or 0) + 1
        row.last_activity = now

        state = db.query(GroupUserState).filter_by(
            group_id=str(group_id), user_id=str(user_id)
        ).first()
        if state is None:
            state = GroupUserState(
                group_id=str(group_id), user_id=str(user_id),
                username=str(username or "User").lstrip("@"),
                first_seen=now, last_active=now,
            )
            db.add(state)
        else:
            state.username = str(username or state.username).lstrip("@")
            state.last_active = now
        db.commit()
    except Exception:
        db.rollback()
        logging.exception("record_activity_failed")
    finally:
        db.close()


def record_warning(group_id, user_id, username, reason, detected_text):
    now = utc_now()
    db = SessionLocal()
    try:
        state = db.query(GroupUserState).filter_by(
            group_id=str(group_id), user_id=str(user_id)
        ).first()
        if state is None:
            state = GroupUserState(
                group_id=str(group_id), user_id=str(user_id),
                username=str(username or "User").lstrip("@"),
                warning_count=0, first_seen=now, last_active=now,
            )
            db.add(state)
        state.username = str(username or state.username).lstrip("@")
        state.warning_count = (state.warning_count or 0) + 1
        state.last_active = now
        warning_number = state.warning_count

        db.add(WarningHistory(
            group_id=str(group_id),
            user_id=str(user_id),
            username=str(username or "User").lstrip("@"),
            reason=str(reason or "Abuse detected"),
            detected_text=str(detected_text or "")[:500],
            warning_number=warning_number,
            created_at=now,
        ))
        db.commit()
        return warning_number
    except Exception:
        db.rollback()
        logging.exception("record_warning_failed")
        return 1
    finally:
        db.close()


def get_warning_rows(group_id, username=None, limit=25):
    db = SessionLocal()
    try:
        q = db.query(WarningHistory).filter_by(group_id=str(group_id))
        if username:
            clean = str(username).lstrip("@").casefold()
            q = q.filter(func.lower(WarningHistory.username) == clean)
        rows = q.order_by(WarningHistory.id.desc()).limit(limit).all()
        return [{
            "username": r.username, "warning_number": r.warning_number,
            "reason": r.reason, "detected_text": r.detected_text,
            "created_at": r.created_at,
        } for r in rows]
    finally:
        db.close()


def inactive_rows(group_id, days=7, limit=50):
    cutoff = utc_now() - timedelta(days=days)
    db = SessionLocal()
    try:
        rows = db.query(GroupMemberAnalytics).filter(
            GroupMemberAnalytics.group_id == str(group_id),
            GroupMemberAnalytics.last_activity < cutoff,
        ).order_by(GroupMemberAnalytics.last_activity.asc()).limit(limit).all()
        return [{
            "username": r.username, "user_id": r.user_id,
            "last_activity": r.last_activity, "message_count": r.message_count,
        } for r in rows]
    finally:
        db.close()


def detect_abuse_reason(text):
    raw = (text or "").casefold().strip()
    if not raw:
        return None
    for pattern in BAD_WORD_PATTERNS:
        try:
            match = re.search(pattern, raw, re.IGNORECASE)
        except re.error:
            continue
        if match:
            return f"Matched word/phrase: {match.group(0)[:80]}"
    spaced = re.sub(r"[^\w]+", " ", raw, flags=re.UNICODE).strip()
    for word in sorted(RESTRICTED_WORDS, key=len, reverse=True):
        candidate = re.sub(r"[^\w]+", " ", str(word).casefold()).strip()
        if candidate and re.search(rf"(?<!\w){re.escape(candidate)}(?!\w)", spaced, re.UNICODE):
            return f"Matched word/phrase: {word}"
    return None


def detect_link_type(text):
    value = (text or "").casefold().strip()
    if not value:
        return None
    url_pattern = (
        r"(?:https?://|www\.)[^\s<>]+|"
        r"\b(?:instagram\.com|instagr\.am|bit\.ly|tinyurl\.com|t\.me|wa\.me|"
        r"youtu\.be|youtube\.com|linktr\.ee|facebook\.com|x\.com|tiktok\.com)/[^\s<>]*"
    )
    if re.search(url_pattern, value, re.IGNORECASE):
        if re.search(r"(?:instagram\.com|instagr\.am)/(?:reel|reels)(?:/|\b)", value, re.IGNORECASE):
            return "Instagram Reel Link"
        if re.search(r"(?:instagram\.com|instagr\.am)/(?:p|tv)/", value, re.IGNORECASE):
            return "Instagram Post / Video Link"
        return "External Link"
    if re.search(r"\b[a-z0-9-]+\.(?:com|net|org|xyz|top|info|site|link|io|me|co|in|app|gg)(?:/[^\s]*)?", value, re.IGNORECASE):
        return "Bare Domain Link"
    return None


def get_admin_ids(thread):
    raw_admins = getattr(thread, "admin_user_ids", None) or getattr(thread, "admin_users", None) or []
    result = []
    for admin in raw_admins:
        candidate = (
            getattr(admin, "pk", None)
            or getattr(admin, "user_id", None)
            or getattr(admin, "id", None)
            or admin
        )
        if candidate is not None:
            result.append(str(candidate).strip())
    return result


def get_admin_mentions(users, admin_ids):
    wanted = {str(x) for x in admin_ids}
    names = []
    for user in users:
        if str(getattr(user, "pk", "")) in wanted:
            name = getattr(user, "username", None)
            if name:
                names.append(fix_mention(name))
    return " ".join(names) if names else "@Admins"


def build_warnings_card(group_id, gc_name, rows, target=None):
    if not rows:
        body = "No abuse warnings recorded for this GC."
    else:
        lines = []
        for row in rows:
            stamp = row['created_at']
            if stamp and stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            local = stamp.astimezone(TIMEZONE).strftime("%d %b %Y, %I:%M %p") if stamp else "Unknown time"
            lines.append(
                f"• {fix_mention(row['username'])} | Warning #{row['warning_number']}\n"
                f"  Reason: {row['reason']}\n"
                f"  Text: {row['detected_text'][:100]}\n"
                f"  Time: {local}"
            )
        body = "\n\n".join(lines)
    return (
        "📋 𝗦𝗠𝗪 𝗔𝗕𝗨𝗦𝗘 𝗪𝗔𝗥𝗡𝗜𝗡𝗚 𝗛𝗜𝗦𝗧𝗢𝗥𝗬\n\n"
        f"🏷️ 𝗚𝗖 ➜ {gc_name}\n"
        + (f"👤 𝗨𝗦𝗘𝗥 ➜ {fix_mention(target)}\n\n" if target else "")
        + body[:5000] + "\n\n" + DEV_LINE
    )


def build_inactive_card(gc_name, rows, days):
    if not rows:
        body = f"No tracked member has been inactive for {days}+ days."
    else:
        lines = []
        for row in rows:
            stamp = row['last_activity']
            if stamp and stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            local = stamp.astimezone(TIMEZONE).strftime("%d %b %Y, %I:%M %p") if stamp else "Unknown"
            lines.append(
                f"• {fix_mention(row['username'])}\n"
                f"  🆔 {row['user_id']}\n"
                f"  🕒 Last active: {local}\n"
                f"  💬 Messages: {row['message_count'] or 0}"
            )
        body = "\n\n".join(lines)
    return (
        "🧊 𝗦𝗠𝗪 𝟳-𝗗𝗔𝗬 𝗜𝗡𝗔𝗖𝗧𝗜𝗩𝗘 𝗥𝗘𝗣𝗢𝗥𝗧\n\n"
        f"🏷️ 𝗚𝗖 ➜ {gc_name}\n"
        f"⏳ 𝗜𝗡𝗔𝗖𝗧𝗜𝗩𝗘 𝗙𝗢𝗥 ➜ {days}+ days\n\n"
        f"{body}\n\n"
        "⚠️ Review before removing members.\n\n"
        + DEV_LINE
    )


def start_bot():
    global LAST_SUCCESSFUL_POLL, LAST_POLL_ERROR, TOTAL_SEEN_MESSAGES
    if not INSTAGRAM_SESSION_ID:
        raise RuntimeError("INSTAGRAM_SESSION_ID is missing. Put it in .env.")

    init_db()
    cl = Client()
    cl.delay_range = [1, 2]

    try:
        cl.login_by_sessionid(INSTAGRAM_SESSION_ID)
    except (LoginRequired, ChallengeRequired, BadPassword, PleaseWaitFewMinutes, ClientThrottledError) as exc:
        logging.error("initial_login_failed type=%s", type(exc).__name__)
        print(f"[!] Instagram session/authentication failed: {type(exc).__name__}")
        return
    except Exception as exc:
        logging.exception("initial_login_failed")
        print(f"[!] Login failed: {type(exc).__name__}: {exc}")
        return

    print(f"[+] @{BOT_USERNAME} logged in. Lightweight GC monitor started.")

    seen_message_ids = set()
    group_members_state = {}
    ever_seen_members = {}
    member_name_cache = {}
    active_announced_threads = set()
    initialized_message_threads = set()
    welcomed_users = {}
    last_morning = {}
    last_night = {}
    recent_sent = {}

    def send(thread_id, text):
        footer = DEV_LINE
        lines = [
            line for line in str(text).splitlines()
            if not re.search(r"DEVELOPER|𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥|DEV ➜", line, re.IGNORECASE)
        ]
        content = "\n".join(lines).rstrip() + "\n\n" + footer
        now = time.time()
        old = recent_sent.get(str(thread_id))
        if old and old[0] == content and now - old[1] < 2:
            return False
        recent_sent[str(thread_id)] = (content, now)
        try:
            cl.direct_send(content, thread_ids=[thread_id])
            return True
        except Exception as exc:
            logging.exception("send_failed thread=%s", thread_id)
            return False

    while True:
        try:
            threads = list(cl.direct_threads(amount=200) or [])
            LAST_SUCCESSFUL_POLL = datetime.now(timezone.utc).isoformat()
            LAST_POLL_ERROR = "None"
            now_local = datetime.now(TIMEZONE)
            date_key = now_local.strftime("%Y-%m-%d")

            for thread in threads:
                try:
                    if not getattr(thread, "is_group", False):
                        continue

                    thread_id = str(thread.id)
                    admin_ids = get_admin_ids(thread)
                    bot_pk = str(getattr(cl, "user_id", "") or "")
                    # HARD GC GATE: if bot is not an admin, do absolutely nothing.
                    if not bot_pk or bot_pk not in set(admin_ids):
                        logging.info("gc_skipped_not_admin thread=%s", thread_id)
                        continue

                    users = list(getattr(thread, "users", []) or [])
                    gc_name = (
                        getattr(thread, "thread_title", None)
                        or getattr(thread, "title", None)
                        or getattr(thread, "name", None)
                        or "Unknown GC"
                    )
                    admin_mentions = get_admin_mentions(users, admin_ids)

                    if now_local.hour == 6 and last_morning.get(thread_id) != date_key:
                        morning_card = (
                            "🌅✨ 𝗚𝗢𝗢𝗗 𝗠𝗢𝗥𝗡𝗜𝗡𝗚, 𝗘𝗩𝗘𝗥𝗬𝗢𝗡𝗘! ✨🌅\n\n"
                            "🌻 𝗛𝗔𝗩𝗘 𝗔𝗡 𝗔𝗠𝗔𝗭𝗜𝗡𝗚 & 𝗣𝗥𝗢𝗗𝗨𝗖𝗧𝗜𝗩𝗘 𝗗𝗔𝗬!\n"
                            "☕ 𝗦𝗣𝗥𝗘𝗔𝗗 𝗣𝗢𝗦𝗜𝗧𝗜𝗩𝗜𝗧𝗬 & 𝗞𝗘𝗘𝗣 𝗧𝗛𝗘 𝗚𝗖 𝗔𝗖𝗧𝗜𝗩𝗘!\n\n"
                            f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}"
                        )
                        if send(thread_id, morning_card):
                            last_morning[thread_id] = date_key

                    if now_local.hour == 23 and last_night.get(thread_id) != date_key:
                        night_card = (
                            "🌙✨ 𝗚𝗢𝗢𝗗 𝗡𝗜𝗚𝗛𝗧, 𝗚𝗖 𝗙𝗔𝗠𝗜𝗟𝗬! ✨🌙\n\n"
                            "😴 𝗧𝗜𝗠𝗘 𝗧𝗢 𝗥𝗘𝗦𝗧 & 𝗥𝗘𝗖𝗛𝗔𝗥𝗚𝗘!\n"
                            "💫 𝗦𝗪𝗘𝗘𝗧 𝗗𝗥𝗘𝗔𝗠𝗦 & 𝗦𝗘𝗘 𝗬𝗢𝗨 𝗧𝗢𝗠𝗢𝗥𝗥𝗢𝗪! 🌙\n\n"
                            f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}"
                        )
                        if send(thread_id, night_card):
                            last_night[thread_id] = date_key

                    if thread_id not in active_announced_threads:
                        active_card = (
                            "✦ 𝗦𝗠𝗪 𝗕𝗢𝗧 ✦\n"
                            "𝗦𝗬𝗦𝗧𝗘𝗠 𝗢𝗡𝗟𝗜𝗡𝗘  •  ● ACTIVE\n\n"
                            "🛡️ 𝗚𝗥𝗢𝗨𝗣 𝗦𝗘𝗖𝗨𝗥𝗜𝗧𝗬 𝗥𝗘𝗔𝗗𝗬\n"
                            "⚙️ 𝗔𝗟𝗟 𝗦𝗬𝗦𝗧𝗘𝗠𝗦 𝗜𝗡𝗜𝗧𝗜𝗔𝗟𝗜𝗭𝗘𝗗\n\n"
                            f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}"
                        )
                        if send(thread_id, active_card):
                            active_announced_threads.add(thread_id)

                    current_members = {
                        str(getattr(u, "pk", "")) for u in users if getattr(u, "pk", None)
                    }
                    for member in users:
                        pk = str(getattr(member, "pk", "") or "")
                        name = getattr(member, "username", None) or getattr(member, "full_name", None)
                        if pk and name:
                            member_name_cache[pk] = str(name)

                    previous_members = group_members_state.get(thread_id)
                    seen_before = ever_seen_members.setdefault(thread_id, set())
                    if previous_members is not None:
                        joined = current_members - previous_members
                        departed = previous_members - current_members

                        for pk in joined:
                            if pk in welcomed_users and time.time() - welcomed_users[pk] < 60:
                                continue
                            user_obj = next((u for u in users if str(getattr(u, "pk", "")) == pk), None)
                            username = getattr(user_obj, "username", None) if user_obj else None
                            if not username:
                                continue
                            welcomed_users[pk] = time.time()
                            if pk in seen_before:
                                welcome_card = (
                                    f"💫🦋 𝗪𝗘𝗟𝗖𝗢𝗠𝗘 𝗕𝗔𝗖𝗞, {fix_mention(username)}! 🦋💫\n\n"
                                    "🌷 𝗧𝗛𝗘 𝗚𝗖 𝗠𝗜𝗦𝗦𝗘𝗗 𝗬𝗢𝗨!\n\n"
                                    "🔥 𝗕𝗔𝗖𝗞 𝗔𝗚𝗔𝗜𝗡 • 𝗦𝗧𝗔𝗬 𝗔𝗖𝗧𝗜𝗩𝗘\n\n"
                                    f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}"
                                )
                            else:
                                welcome_card = (
                                    f"🦋✨ 𝗪𝗘𝗟𝗖𝗢𝗠𝗘, {fix_mention(username)}! ✨🦋\n\n"
                                    "🌸 𝗛𝗘𝗬! 𝗚𝗟𝗔𝗗 𝗧𝗢 𝗛𝗔𝗩𝗘 𝗬𝗢𝗨 𝗛𝗘𝗥𝗘 💫\n"
                                    "🔥 𝗘𝗡𝗝𝗢𝗬 𝗧𝗛𝗘 𝗚𝗖 & 𝗦𝗧𝗔𝗬 𝗔𝗖𝗧𝗜𝗩𝗘!\n\n"
                                    f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}"
                                )
                            send(thread_id, welcome_card)
                            seen_before.add(pk)

                        for pk in departed:
                            username = member_name_cache.get(pk, "Unknown member")
                            left_card = (
                                "👋🚪 𝗠𝗘𝗠𝗕𝗘𝗥 𝗟𝗘𝗙𝗧 / 𝗪𝗔𝗦 𝗥𝗘𝗠𝗢𝗩𝗘𝗗\n\n"
                                f"👤 𝗨𝗦𝗘𝗥 ➜ {fix_mention(username)}\n"
                                f"🆔 𝗨𝗦𝗘𝗥 𝗜𝗗 ➜ `{pk}`\n"
                                "📌 𝗦𝗧𝗔𝗧𝗨𝗦 ➜ Member is no longer in the GC\n\n"
                                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}"
                            )
                            send(thread_id, left_card)

                    group_members_state[thread_id] = current_members
                    seen_before.update(current_members)

                    # Existing messages are used only as baseline on first observation.
                    messages = list(getattr(thread, "messages", []) or [])
                    if thread_id not in initialized_message_threads:
                        for msg in messages:
                            mid = str(getattr(msg, "id", "") or "")
                            if mid:
                                seen_message_ids.add(mid)
                        initialized_message_threads.add(thread_id)
                        continue

                    for msg in reversed(messages):
                        mid = str(getattr(msg, "id", "") or "")
                        if not mid or mid in seen_message_ids:
                            continue
                        seen_message_ids.add(mid)
                        TOTAL_SEEN_MESSAGES += 1

                        text = str(getattr(msg, "text", "") or "").strip()
                        if not text:
                            continue
                        sender_id = str(getattr(msg, "user_id", "") or "")
                        if sender_id == bot_pk:
                            continue

                        sender_obj = getattr(msg, "user", None)
                        sender_username = getattr(sender_obj, "username", None)
                        if not sender_username:
                            sender_username = next(
                                (getattr(u, "username", None) for u in users if str(getattr(u, "pk", "")) == sender_id),
                                "User",
                            )
                        sender_username = str(sender_username or "User")
                        is_admin = sender_id in set(admin_ids)
                        is_dev = sender_username.lstrip("@").casefold() in {x.casefold() for x in AUTHORIZED_DEVS}

                        # Every observed message is activity for this GC only.
                        record_activity(thread_id, sender_id, sender_username)

                        text_lower = text.casefold()

                        # Public rules command.
                        if text_lower == "!rules":
                            rules_card = (
                                "⚜🌷 𝗚𝗖 𝗥𝗨𝗟𝗘𝗦 • 𝗣𝗟𝗘𝗔𝗦𝗘 𝗥𝗘𝗔𝗗 🌷⚜️\n\n"
                                "🤝 𝗥𝗘𝗦𝗣𝗘𝗖𝗧 𝗘𝗩𝗘𝗥𝗬𝗢𝗡𝗘\n"
                                "💌 𝗞𝗘𝗘𝗣 𝗧𝗛𝗘 𝗩𝗜𝗕𝗘 𝗙𝗥𝗜𝗘𝗡𝗗𝗟𝗬\n\n"
                                "🚫 𝗡𝗢 𝗔𝗕𝗨𝗦𝗘 • 𝗡𝗢 𝗧𝗢𝗫𝗜𝗖𝗜𝗧𝗬\n"
                                "⚠️ 𝗗𝗥𝗔𝗠𝗔 & 𝗙𝗜𝗚𝗛𝗧𝗦 𝗔𝗥𝗘 𝗡𝗢𝗧 𝗔𝗟𝗟𝗢𝗪𝗘𝗗\n\n"
                                "🔞 𝗡𝗢 𝗡𝗦𝗙𝗪 / 𝗔𝗗𝗨𝗟𝗧 𝗖𝗢𝗡𝗧𝗘𝗡𝗧\n"
                                "🛡️ 𝗞𝗘𝗘𝗣 𝗧𝗛𝗘 𝗚𝗖 𝗖𝗟𝗘𝗔𝗡\n\n"
                                "📢 𝗡𝗢 𝗦𝗣𝗔𝗠 • 𝗡𝗢 𝗙𝗟𝗢𝗢𝗗𝗜𝗡𝗚\n"
                                "🚫 𝗗𝗢𝗡'𝗧 𝗦𝗘𝗡𝗗 𝗥𝗘𝗣𝗘𝗔𝗧𝗘𝗗 𝗠𝗘𝗦𝗦𝗔𝗚𝗘𝗦\n\n"
                                "🔗 𝗡𝗢 𝗨𝗡𝗔𝗨𝗧𝗛𝗢𝗥𝗜𝗭𝗘𝗗 𝗟𝗜𝗡𝗞𝗦\n"
                                "📩 𝗔𝗦𝗞 𝗔𝗗𝗠𝗜𝗡𝗦 𝗙𝗜𝗥𝗦𝗧\n\n"
                                "👑 𝗥𝗘𝗦𝗣𝗘𝗖𝗧 𝗔𝗗𝗠𝗜𝗡𝗦 & 𝗠𝗢𝗗𝗘𝗥𝗔𝗧𝗢𝗥𝗦\n"
                                "✨ 𝗙𝗢𝗟𝗟𝗢𝗪 𝗢𝗙𝗙𝗜𝗖𝗜𝗔𝗟 𝗜𝗡𝗦𝗧𝗥𝗨𝗖𝗧𝗜𝗢𝗡𝗦\n\n"
                                "⚠️ 𝗥𝗨𝗟𝗘𝗦 𝗕𝗥𝗘𝗔𝗞 = 𝗪𝗔𝗥𝗡𝗜𝗡𝗚\n"
                                "🚫 𝗥𝗘𝗣𝗘𝗔𝗧𝗘𝗗 𝗩𝗜𝗢𝗟𝗔𝗧𝗜𝗢𝗡𝗦 = 𝗥𝗘𝗩𝗜𝗘𝗪\n\n"
                                "🌷 𝗦𝗧𝗔𝗬 𝗔𝗖𝗧𝗜𝗩𝗘 • 𝗦𝗧𝗔𝗬 𝗥𝗘𝗦𝗣𝗘𝗖𝗧𝗙𝗨𝗟 🌷\n"
                                "💫 𝗘𝗡𝗝𝗢𝗬 • 𝗖𝗛𝗔𝗧 • 𝗚𝗥𝗢𝗪 • 𝗖𝗢𝗡𝗡𝗘𝗖𝗧 💫\n\n"
                                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}"
                            )
                            send(thread_id, rules_card)
                            continue

                        # Lightweight link-spam detection. No heavy profile/AI/risk scan.
                        if not (is_admin or is_dev):
                            link_type = detect_link_type(text)
                            if link_type:
                                link_card = (
                                    "🔗🚨 𝗟𝗜𝗡𝗞 𝗦𝗣𝗔𝗠 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗\n\n"
                                    f"👤 𝗨𝗦𝗘𝗥 ➜ {fix_mention(sender_username)}\n"
                                    f"🔗 𝗧𝗬𝗣𝗘 ➜ {link_type}\n"
                                    "⚠️ 𝗦𝗧𝗔𝗧𝗨𝗦 ➜ Link detected in GC\n"
                                    "🛡️ 𝗔𝗖𝗧𝗜𝗢𝗡 ➜ Admin review required\n\n"
                                    f"📢 𝗔𝗗𝗠𝗜𝗡 𝗔𝗟𝗘𝗥𝗧 ➜ {admin_mentions}\n"
                                    f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}"
                                )
                                send(thread_id, link_card)
                                continue

                        # Abuse: warning only. Every event is permanently stored.
                        if not (is_admin or is_dev):
                            abuse_reason = detect_abuse_reason(text)
                            if abuse_reason:
                                warning_no = record_warning(
                                    thread_id, sender_id, sender_username,
                                    abuse_reason, text,
                                )
                                warn_card = (
                                    "⚠️ 𝗔𝗕𝗨𝗦𝗜𝗡𝗚 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗! ⚠️\n\n"
                                    f"👤 𝗢𝗙𝗙𝗘𝗡𝗗𝗘𝗥 ➜ {fix_mention(sender_username)}\n"
                                    f"🚫 𝗥𝗘𝗔𝗦𝗢𝗡 ➜ {abuse_reason}\n"
                                    f"🗣️ 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗 𝗧𝗘𝗫𝗧 ➜ {text[:180]}\n"
                                    f"⚠️ 𝗪𝗔𝗥𝗡𝗜𝗡𝗚 ➜ #{warning_no}\n\n"
                                    f"📢 𝗔𝗗𝗠𝗜𝗡 𝗔𝗟𝗘𝗥𝗧 ➜ {admin_mentions}\n"
                                    "🛡️ 𝗔𝗖𝗧𝗜𝗢𝗡 ➜ Warning recorded permanently\n\n"
                                    f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}"
                                )
                                send(thread_id, warn_card)
                                continue

                        # Lightweight automatic replies only.
                        normalized = re.sub(r"[^a-z0-9@' ]+", " ", text_lower)
                        normalized = re.sub(r"\s+", " ", normalized).strip()
                        answer = None
                        if normalized in {"bot help", "commands", "command list", "help bot"}:
                            answer = "I am the SMW group assistant. Public command: !rules. Admin/developer tools are available to authorized users."
                        elif normalized in {"good morning", "gm", "morning everyone", "morning all"}:
                            answer = f"Good morning, {fix_mention(sender_username)}! Have a great day. 🌞"
                        elif normalized in {"good night", "gn", "night everyone", "goodnight"}:
                            answer = f"Good night, {fix_mention(sender_username)}! Sleep well. 🌙"
                        elif normalized in {"thank you", "thanks", "thank you bot", "thanks bot", "ty"}:
                            answer = f"You're welcome, {fix_mention(sender_username)}! 😊"
                        if answer and not text.startswith("!"):
                            send(thread_id, answer)
                            continue

                        # Admin/developer commands only.
                        if not (is_admin or is_dev) or not text_lower.startswith("!"):
                            continue

                        parts = text.split()
                        command = parts[0].casefold()
                        target = parts[1].lstrip("@") if len(parts) > 1 else None

                        if command in {"!warnings", "!warninglog"}:
                            rows = get_warning_rows(thread_id, target, 30)
                            card = build_warnings_card(thread_id, gc_name, rows, target)
                            send(thread_id, card)
                        elif command == "!inactive":
                            days = 7
                            if len(parts) > 1:
                                try:
                                    days = max(1, min(365, int(parts[1])))
                                except ValueError:
                                    days = 7
                            rows = inactive_rows(thread_id, days, 50)
                            send(thread_id, build_inactive_card(gc_name, rows, days))
                        elif command in {"!status", "!health", "!botinfo"}:
                            uptime = int(time.time() - STARTED_AT)
                            send(
                                thread_id,
                                "❤️‍🔥✨ 𝗦𝗠𝗪 𝗦𝗬𝗦𝗧𝗘𝗠 𝗛𝗘𝗔𝗟𝗧𝗛 ✨❤️‍🔥\n\n"
                                "🟢 𝗦𝗧𝗔𝗧𝗨𝗦 ➜ ONLINE & ACTIVE\n"
                                "👑 𝗕𝗢𝗧 𝗔𝗗𝗠𝗜𝗡 ➜ YES\n"
                                f"⏱️ 𝗨𝗣𝗧𝗜𝗠𝗘 ➜ {uptime}s\n"
                                f"📡 𝗟𝗔𝗦𝗧 𝗣𝗢𝗟𝗟 ➜ {LAST_SUCCESSFUL_POLL or 'PENDING'}\n"
                                f"⚠️ 𝗟𝗔𝗦𝗧 𝗘𝗥𝗥𝗢𝗥 ➜ {LAST_POLL_ERROR}"
                            )
                        elif command == "!help":
                            send(
                                thread_id,
                                "𝗦𝗠𝗪 𝗠𝗢𝗗𝗘𝗥𝗔𝗧𝗜𝗢𝗡 𝗖𝗢𝗠𝗠𝗔𝗡𝗗𝗦\n\n"
                                "!rules — Public GC rules\n"
                                "!warnings [@user] — Warning history\n"
                                "!warninglog [@user] — Warning history\n"
                                "!inactive — Members inactive for 7+ days\n"
                                "!inactive 14 — Members inactive for 14+ days\n"
                                "!status / !health — Bot health\n"
                                "!help — Command list"
                            )
                        elif command.startswith("!"):
                            send(thread_id, f"❓ Unknown command: {command}\nUse !help to see the available commands.")

                except Exception as thread_error:
                    logging.exception("group_processing_error thread=%s", getattr(thread, "id", "?"))

            time.sleep(POLL_INTERVAL)

        except (LoginRequired, ChallengeRequired, BadPassword, PleaseWaitFewMinutes, ClientThrottledError) as exc:
            LAST_POLL_ERROR = type(exc).__name__
            logging.error("session_or_rate_limit_stop type=%s", type(exc).__name__)
            print(f"[!] Instagram session/rate limit event: {type(exc).__name__}. Stopping without auto re-login.")
            return
        except Exception as loop_error:
            LAST_POLL_ERROR = type(loop_error).__name__
            logging.exception("main_polling_loop_failed")
            # Keep the same authenticated client; do not create a new session or auto-login.
            time.sleep(max(15, POLL_INTERVAL))


if __name__ == "__main__":
    start_bot()
