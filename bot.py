import os
import re
import time
import logging
from datetime import datetime, timezone
from threading import Thread, Lock

from flask import Flask, jsonify
from dotenv import load_dotenv

from instagrapi import Client
from instagrapi.exceptions import (
    PleaseWaitFewMinutes,
    ClientThrottledError,
    LoginRequired,
    ChallengeRequired,
)

from sqlalchemy import (
    create_engine,
    Column,
    String,
    Integer,
    Float,
    DateTime,
    Text,
)
from sqlalchemy.orm import declarative_base, sessionmaker


# ============================================================
# CONFIG
# ============================================================

load_dotenv()

BOT_USERNAME = os.getenv("BOT_USERNAME", "").strip()
SESSION_ID = os.getenv("SESSION_ID", "").strip()

OWNER_USERNAME = os.getenv(
    "OWNER_USERNAME",
    "@fx_smw ✘ @aat_nnk25",
)

# ONLY THESE USERS CAN USE COMMANDS
AUTHORIZED_DEVS = {
    x.strip().lower().lstrip("@")
    for x in os.getenv(
        "AUTHORIZED_DEVS",
        "fx_smw,aat_nnk,aat_nnk25,fx_sw",
    ).split(",")
    if x.strip()
}

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///god_mode_bot.db",
)

POLL_INTERVAL = max(
    2.0,
    float(os.getenv("POLL_INTERVAL", "5")),
)

THREAD_BATCH_SIZE = max(
    5,
    int(os.getenv("THREAD_BATCH_SIZE", "20")),
)

LOG_LEVEL = os.getenv(
    "LOG_LEVEL",
    "INFO",
).upper()


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=getattr(
        logging,
        LOG_LEVEL,
        logging.INFO,
    ),
    format="%(asctime)s | %(levelname)s | %(message)s",
)

log = logging.getLogger("SMW-GC-BOT")


# ============================================================
# WEB HEALTH SERVER
# ============================================================

app = Flask(__name__)

BOT_STATE = {
    "started_at": None,
    "last_cycle": None,
    "logged_in": False,
    "last_error": None,
}

STATE_LOCK = Lock()


@app.route("/")
def home():
    return "🤖 Supreme God-Mode Instagram Bot is Running!"


@app.route("/health")
def health():
    with STATE_LOCK:
        return jsonify(dict(BOT_STATE))


def run_flask():
    port = int(os.getenv("PORT", "8080"))

    app.run(
        host="0.0.0.0",
        port=port,
        threaded=True,
        use_reloader=False,
    )


# ============================================================
# DATABASE
# ============================================================

Base = declarative_base()


def get_utc_now():
    return datetime.now(timezone.utc)


class UserProfile(Base):
    __tablename__ = "user_profiles"

    user_id = Column(String, primary_key=True)
    username = Column(String, nullable=False)

    join_date = Column(
        DateTime,
        default=get_utc_now,
    )

    last_active = Column(
        DateTime,
        default=get_utc_now,
    )

    total_messages = Column(
        Integer,
        default=0,
    )

    warning_count = Column(
        Integer,
        default=0,
    )

    violation_count = Column(
        Integer,
        default=0,
    )

    trust_score = Column(
        Float,
        default=100.0,
    )

    username_changes = Column(
        Integer,
        default=0,
    )

    name_changes = Column(
        Integer,
        default=0,
    )

    last_known_fullname = Column(
        String,
        default="",
    )


class SecurityLog(Base):
    __tablename__ = "security_logs"

    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    timestamp = Column(
        DateTime,
        default=get_utc_now,
    )

    group_id = Column(String)
    username = Column(String)
    event_type = Column(String)
    details = Column(Text)


engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args=(
        {"check_same_thread": False}
        if DATABASE_URL.startswith("sqlite")
        else {}
    ),
)

SessionLocal = sessionmaker(bind=engine)


def init_db():
    Base.metadata.create_all(engine)
    log.info("Database ready.")


# ============================================================
# HELPERS
# ============================================================

def fix_mention(username: str) -> str:
    if not username:
        return "@User"

    username = (
        str(username)
        .strip()
        .lstrip("@")
    )

    return f"@{username}" if username else "@User"


def normalize_username(username):
    return (
        str(username or "")
        .strip()
        .lower()
        .lstrip("@")
    )


def is_developer(username):
    return (
        normalize_username(username)
        in AUTHORIZED_DEVS
    )


def get_admin_mentions_str(users, gc_admins):
    admin_ids = {
        str(x)
        for x in gc_admins
    }

    mentions = []

    for user in users:
        pk = str(
            getattr(user, "pk", "")
        )

        if pk in admin_ids:
            username = getattr(
                user,
                "username",
                None,
            )

            if username:
                mentions.append(
                    fix_mention(username)
                )

    return (
        " ".join(mentions)
        if mentions
        else "@Admins"
    )


# ============================================================
# ABUSE DETECTION
# ============================================================

BAD_WORD_PATTERNS = [
    r"bm[\.\_\-\s]*c\b",
    r"bb[\.\_\-\s]*c\b",
    r"bm[\.\_\-\s]*k[\.\_\-\s]*c\b",
    r"bt[\.\_\-\s]*m[\.\_\-\s]*c\b",
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
    r"f[\.\_\-\s]*u[\.\_\-\s]*c[\.\_\-\s]*k",
]

RESTRICTED_WORDS = {
    "mc", "bc", "mkc", "tmkc",
    "bsdk", "bsdke",
    "chutiya", "chutiye", "chutiyap",
    "gandu", "gaandu",
    "lauda", "luda", "lawda", "lund",
    "chut", "chuth",
    "gand", "gaand",
    "randi", "randwa",
    "bhadwa", "bhadwe",
    "harami", "haramkhor",
    "kamine", "kamina",
    "saala", "saale",
    "madarchod", "maderchod", "madar-chod",
    "bhenchod", "behenchod",
    "bhen-chod", "behen-chod",
    "bhosdike", "bhosdi", "bhosda",
    "fuck", "fucking", "fucker",
    "motherfucker",
    "bitch", "bastard", "asshole",
}


def is_abusive_text(text):
    if not text:
        return False

    text_lower = text.lower()

    words = re.findall(
        r"\b\w+\b",
        text_lower,
    )

    if any(
        word in RESTRICTED_WORDS
        for word in words
    ):
        return True

    return any(
        re.search(
            pattern,
            text_lower,
        )
        for pattern in BAD_WORD_PATTERNS
    )


# ============================================================
# DATABASE ENGINE
# ============================================================

class ModerationEngine:

    @staticmethod
    def record_activity(
        user_id,
        username,
        fullname="",
    ):
        db = SessionLocal()

        try:
            clean = normalize_username(username)

            profile = (
                db.query(UserProfile)
                .filter(
                    UserProfile.user_id
                    == str(user_id)
                )
                .first()
            )

            if not profile:
                profile = UserProfile(
                    user_id=str(user_id),
                    username=clean,
                    total_messages=1,
                    trust_score=100.0,
                    last_known_fullname=fullname or "",
                )

                db.add(profile)

            else:
                if profile.username != clean:
                    profile.username_changes = (
                        profile.username_changes or 0
                    ) + 1

                    profile.username = clean

                if (
                    fullname
                    and profile.last_known_fullname
                    and profile.last_known_fullname != fullname
                ):
                    profile.name_changes = (
                        profile.name_changes or 0
                    ) + 1

                if (
                    fullname
                    and not profile.last_known_fullname
                ):
                    profile.last_known_fullname = fullname

                profile.total_messages = (
                    profile.total_messages or 0
                ) + 1

                profile.last_active = get_utc_now()

            db.commit()

        except Exception:
            db.rollback()
            log.exception(
                "record_activity failed"
            )

        finally:
            db.close()

    @staticmethod
    def add_warning(username):
        db = SessionLocal()

        try:
            clean = normalize_username(username)

            profile = (
                db.query(UserProfile)
                .filter(
                    UserProfile.username
                    == clean
                )
                .first()
            )

            if not profile:
                profile = UserProfile(
                    user_id=f"username:{clean}",
                    username=clean,
                    warning_count=1,
                    violation_count=1,
                    trust_score=75.0,
                )

                db.add(profile)
                db.commit()

                return 1, 75.0

            profile.warning_count = (
                profile.warning_count or 0
            ) + 1

            profile.violation_count = (
                profile.violation_count or 0
            ) + 1

            profile.trust_score = max(
                0.0,
                (profile.trust_score or 100.0)
                - 25.0,
            )

            db.commit()

            return (
                profile.warning_count,
                profile.trust_score,
            )

        except Exception:
            db.rollback()
            log.exception(
                "add_warning failed"
            )

            return 1, 75.0

        finally:
            db.close()

    @staticmethod
    def get_user_stats(username):
        db = SessionLocal()

        try:
            clean = normalize_username(username)

            profile = (
                db.query(UserProfile)
                .filter(
                    UserProfile.username
                    == clean
                )
                .first()
            )

            if not profile:
                return (
                    f"❌ User "
                    f"{fix_mention(clean)} "
                    "not registered in DB yet!\n\n"
                    f"👑 𝗗𝗘𝗩 ➜ {OWNER_USERNAME}"
                )

            score = max(
                0,
                min(
                    100,
                    int(
                        profile.trust_score or 0
                    ),
                ),
            )

            filled = score // 10

            bar = (
                "█" * filled
                + "░" * (10 - filled)
            )

            return (
                "📊✨ 𝗚𝗢𝗗-𝗠𝗢𝗗𝗘 • "
                "𝗨𝗦𝗘𝗥 𝗦𝗧𝗔𝗧𝗦 ✨📊\n\n"

                f"👤 𝗨𝗦𝗘𝗥 ➜ "
                f"{fix_mention(profile.username)}\n"

                f"🆔 𝗨𝗦𝗘𝗥 𝗜𝗗 ➜ "
                f"`{profile.user_id}`\n"

                f"💬 𝗧𝗢𝗧𝗔𝗟 𝗠𝗦𝗚𝗦 ➜ "
                f"{profile.total_messages or 0}\n"

                f"⚠️ 𝗪𝗔𝗥𝗡𝗜𝗡𝗚𝗦 ➜ "
                f"{profile.warning_count or 0}/3\n"

                f"🚫 𝗩𝗜𝗢𝗟𝗔𝗧𝗜𝗢𝗡𝗦 ➜ "
                f"{profile.violation_count or 0}\n"

                f"💎 𝗧𝗥𝗨𝗦𝗧 𝗦𝗖𝗢𝗥𝗘 ➜ "
                f"{score}%\n"

                f"📈 𝗦𝗖𝗢𝗥𝗘 𝗕𝗔𝗥 ➜ "
                f"[{bar}]\n\n"

                f"🤖 𝗕𝗢𝗧 ➜ "
                f"{fix_mention(BOT_USERNAME)}\n"

                f"👑 𝗗𝗘𝗩 ➜ "
                f"{OWNER_USERNAME}"
            )

        finally:
            db.close()

    @staticmethod
    def get_detailed_user_bio(
        cl,
        username,
    ):
        try:
            clean_name = (
                str(username)
                .strip()
                .lstrip("@")
            )

            info = cl.user_info_by_username(
                clean_name
            )

            if not info:
                return (
                    f"❌ User @{clean_name} "
                    "not found on Instagram!"
                )

            full_name = getattr(
                info,
                "full_name",
                "N/A",
            )

            biography = getattr(
                info,
                "biography",
                "N/A",
            )

            followers = getattr(
                info,
                "follower_count",
                0,
            )

            following = getattr(
                info,
                "following_count",
                0,
            )

            is_private = (
                "🔒 Private"
                if getattr(
                    info,
                    "is_private",
                    False,
                )
                else "🔓 Public"
            )

            is_verified = (
                "✅ Yes"
                if getattr(
                    info,
                    "is_verified",
                    False,
                )
                else "❌ No"
            )

            media_count = getattr(
                info,
                "media_count",
                0,
            )

            external_url = getattr(
                info,
                "external_url",
                "None",
            )

            user_pk = getattr(
                info,
                "pk",
                "N/A",
            )

            return (
                "👤📋 𝗨𝗦𝗘𝗥 • "
                "𝗗𝗘𝗧𝗔𝗜𝗟𝗘𝗗 𝗕𝗜𝗢𝗗𝗔𝗧𝗔 📋👤\n\n"

                f"📌 𝗡𝗔𝗠𝗘 ➜ {full_name}\n"
                f"🏷️ 𝗨𝗦𝗘𝗥𝗡𝗔𝗠𝗘 ➜ @{clean_name}\n"
                f"🆔 𝗨𝗦𝗘𝗥 𝗜𝗗 ➜ `{user_pk}`\n"
                f"👥 𝗙𝗢𝗟𝗟𝗢𝗪𝗘𝗥𝗦 ➜ `{followers}`\n"
                f"👣 𝗙𝗢𝗟𝗟𝗢𝗪𝗜𝗡𝗚 ➜ `{following}`\n"
                f"📸 𝗣𝗢𝗦𝗧𝗦 ➜ `{media_count}`\n"
                f"🔒 𝗔𝗖𝗖𝗢𝗨𝗡𝗧 ➜ {is_private}\n"
                f"✔️ 𝗩𝗘𝗥𝗜𝗙𝗜𝗘𝗗 ➜ {is_verified}\n"
                f"🔗 𝗕𝗜𝗢 𝗟𝗜𝗡𝗞 ➜ {external_url}\n\n"

                f"📝 𝗕𝗜𝗢𝗚𝗥𝗔𝗣𝗛𝗬:\n"
                f"`{biography}`\n\n"

                f"🤖 𝗕𝗢𝗧 ➜ "
                f"{fix_mention(BOT_USERNAME)}\n"

                f"👑 𝗗𝗘𝗩 ➜ "
                f"{OWNER_USERNAME}"
            )

        except Exception as exc:
            return (
                f"❌ Error fetching bio "
                f"for @{username}: {exc}"
            )

    @staticmethod
    def log_event(
        group_id,
        username,
        event_type,
        details,
    ):
        db = SessionLocal()

        try:
            db.add(
                SecurityLog(
                    group_id=str(group_id),
                    username=str(username),
                    event_type=str(event_type),
                    details=str(details),
                )
            )

            db.commit()

        except Exception:
            db.rollback()
            log.exception(
                "Security logging failed"
            )

        finally:
            db.close()


# ============================================================
# BOT
# ============================================================

def start_bot():

    init_db()

    if not BOT_USERNAME:
        raise RuntimeError(
            "BOT_USERNAME is missing."
        )

    if not SESSION_ID:
        raise RuntimeError(
            "SESSION_ID is missing."
        )

    known_members = {}
    seen_message_ids = set()
    recent_sent_texts = {}

    while True:

        try:
            log.info(
                "Starting Instagram client..."
            )

            cl = Client()

            # Normal client configuration.
            # No challenge/detection bypass.
            logged_in = False

            try:
                cl.login_by_sessionid(
                    SESSION_ID
                )

                logged_in = True

                log.info(
                    "Session login successful."
                )

            except Exception as exc:

                log.error(
                    "Session login failed: %s",
                    exc,
                )

                with STATE_LOCK:
                    BOT_STATE[
                        "logged_in"
                    ] = False
                    BOT_STATE[
                        "last_error"
                    ] = repr(exc)

                time.sleep(30)
                continue

            with STATE_LOCK:
                BOT_STATE[
                    "logged_in"
                ] = logged_in
                BOT_STATE[
                    "last_error"
                ] = None

            # ========================================================
            # SEND
            # ========================================================

            def safe_send(
                thread_id,
                message,
                reply_to=None,
            ):

                now = time.time()

                previous = (
                    recent_sent_texts.get(
                        thread_id
                    )
                )

                if (
                    previous
                    and previous[0] == message
                    and now - previous[1] < 2
                ):
                    return False

                recent_sent_texts[
                    thread_id
                ] = (
                    message,
                    now,
                )

                try:

                    if reply_to:
                        cl.direct_answer(
                            thread_id,
                            reply_to,
                            message,
                        )
                    else:
                        cl.direct_send(
                            message,
                            thread_ids=[
                                thread_id
                            ],
                        )

                    return True

                except Exception as exc:

                    log.warning(
                        "Message send failed: %s",
                        exc,
                    )

                    return False

            # ========================================================
            # MAIN LOOP
            # ========================================================

            while True:

                try:

                    threads = list(
                        cl.direct_threads(
                            amount=THREAD_BATCH_SIZE
                        )
                        or []
                    )

                    for thread_mini in threads:

                        if not getattr(
                            thread_mini,
                            "is_group",
                            False,
                        ):
                            continue

                        thread_id = str(
                            thread_mini.id
                        )

                        try:
                            thread = (
                                cl.direct_thread(
                                    thread_id
                                )
                            )
                        except Exception as exc:
                            log.warning(
                                "Thread read failed: %s",
                                exc,
                            )
                            continue

                        if not thread:
                            continue

                        users = list(
                            getattr(
                                thread,
                                "users",
                                [],
                            )
                            or []
                        )

                        gc_admins = [
                            str(x)
                            for x in (
                                getattr(
                                    thread,
                                    "admin_user_ids",
                                    [],
                                )
                                or []
                            )
                        ]

                        admin_ids = set(
                            gc_admins
                        )

                        admin_mentions = (
                            get_admin_mentions_str(
                                users,
                                gc_admins,
                            )
                        )

                        bot_pk = str(
                            cl.user_id
                        )

                        # =================================================
                        # MEMBER TRACKING
                        # =================================================

                        current_members = {
                            str(
                                getattr(
                                    u,
                                    "pk",
                                    "",
                                )
                            )

                            for u in users

                            if str(
                                getattr(
                                    u,
                                    "pk",
                                    "",
                                )
                            )
                            and str(
                                getattr(
                                    u,
                                    "pk",
                                    "",
                                )
                            ) != bot_pk
                        }

                        if thread_id not in known_members:

                            known_members[
                                thread_id
                            ] = (
                                current_members.copy()
                            )

                        else:

                            old_members = (
                                known_members[
                                    thread_id
                                ]
                            )

                            new_members = (
                                current_members
                                - old_members
                            )

                            left_members = (
                                old_members
                                - current_members
                            )

                            # NEW MEMBER
                            for new_pk in new_members:

                                known_members[
                                    thread_id
                                ].add(new_pk)

                                new_user = next(
                                    (
                                        u
                                        for u in users
                                        if str(
                                            getattr(
                                                u,
                                                "pk",
                                                "",
                                            )
                                        )
                                        == new_pk
                                    ),
                                    None,
                                )

                                if new_user:

                                    username = getattr(
                                        new_user,
                                        "username",
                                        "User",
                                    )

                                    welcome_card = (
                                        "👋✨ 𝗪𝗘𝗟𝗖𝗢𝗠𝗘 "
                                        "𝗧𝗢 𝗧𝗛𝗘 𝗚𝗖! ✨👋\n\n"

                                        f"👤 𝗠𝗘𝗠𝗕𝗘𝗥 ➜ "
                                        f"{fix_mention(username)}\n"

                                        f"🆔 𝗨𝗦𝗘𝗥 𝗜𝗗 ➜ "
                                        f"`{new_pk}`\n"

                                        "📜 𝗣𝗟𝗘𝗔𝗦𝗘 "
                                        "𝗖𝗛𝗘𝗖𝗞 𝗥𝗨𝗟𝗘𝗦 ➜ "
                                        "`!rules`\n\n"

                                        f"🤖 𝗕𝗢𝗧 ➜ "
                                        f"{fix_mention(BOT_USERNAME)}\n"

                                        f"👑 𝗗𝗘𝗩 ➜ "
                                        f"{OWNER_USERNAME}"
                                    )

                                    safe_send(
                                        thread_id,
                                        welcome_card,
                                    )

                            # LEFT MEMBER
                            for left_pk in left_members:

                                known_members[
                                    thread_id
                                ].discard(
                                    left_pk
                                )

                                left_card = (
                                    "🚪🚶‍♂️ 𝗚𝗖 𝗠𝗘𝗠𝗕𝗘𝗥 • "
                                    "𝗟𝗘𝗙𝗧 🚶‍♂️🚪\n\n"

                                    f"🆔 𝗨𝗦𝗘𝗥 𝗜𝗗 ➜ "
                                    f"`{left_pk}`\n"

                                    "💨 𝗦𝗧𝗔𝗧𝗨𝗦 ➜ "
                                    "𝗟𝗘𝗙𝗧 𝗧𝗛𝗘 𝗚𝗥𝗢𝗨𝗣\n\n"

                                    f"🤖 𝗕𝗢𝗧 ➜ "
                                    f"{fix_mention(BOT_USERNAME)}\n"

                                    f"👑 𝗗𝗘𝗩 ➜ "
                                    f"{OWNER_USERNAME}"
                                )

                                safe_send(
                                    thread_id,
                                    left_card,
                                )

                        # =================================================
                        # MESSAGE
                        # =================================================

                        messages = list(
                            getattr(
                                thread,
                                "messages",
                                [],
                            )
                            or []
                        )

                        if not messages:
                            continue

                        last_msg = messages[0]

                        message_id = str(
                            getattr(
                                last_msg,
                                "id",
                                "",
                            )
                        )

                        if (
                            not message_id
                            or message_id
                            in seen_message_ids
                        ):
                            continue

                        seen_message_ids.add(
                            message_id
                        )

                        if len(
                            seen_message_ids
                        ) > 5000:

                            seen_message_ids = set(
                                list(
                                    seen_message_ids
                                )[-2500:]
                            )

                        text = str(
                            getattr(
                                last_msg,
                                "text",
                                "",
                            )
                            or ""
                        ).strip()

                        text_lower = text.lower()

                        sender_id = str(
                            getattr(
                                last_msg,
                                "user_id",
                                "",
                            )
                        )

                        item_type = str(
                            getattr(
                                last_msg,
                                "item_type",
                                "",
                            )
                            or ""
                        ).lower()

                        sender = next(
                            (
                                u
                                for u in users
                                if str(
                                    getattr(
                                        u,
                                        "pk",
                                        "",
                                    )
                                )
                                == sender_id
                            ),
                            None,
                        )

                        sender_username = (
                            getattr(
                                sender,
                                "username",
                                "User",
                            )
                            if sender
                            else "User"
                        )

                        sender_fullname = (
                            getattr(
                                sender,
                                "full_name",
                                "User",
                            )
                            if sender
                            else "User"
                        )

                        if sender_id == bot_pk:
                            continue

                        is_admin = (
                            sender_id
                            in admin_ids
                        )

                        is_dev = is_developer(
                            sender_username
                        )

                        ModerationEngine.record_activity(
                            sender_id,
                            sender_username,
                            sender_fullname,
                        )

                        # =================================================
                        # MODERATION
                        # =================================================

                        if (
                            not is_admin
                            and not is_dev
                        ):

                            abuse = (
                                is_abusive_text(
                                    text
                                )
                            )

                            link_or_share = (
                                any(
                                    key
                                    in text_lower
                                    for key in [
                                        "http://",
                                        "https://",
                                        "www.",
                                        "instagram.com",
                                        "t.me",
                                        "bit.ly",
                                    ]
                                )
                                or
                                item_type in {
                                    "clip",
                                    "story_share",
                                    "media_share",
                                }
                            )

                            if abuse or link_or_share:

                                reason = (
                                    "Zero-Tolerance "
                                    "Toxic Abuse"
                                    if abuse
                                    else
                                    "Unauthorized "
                                    "Link / Reel Promotion"
                                )

                                warns, trust = (
                                    ModerationEngine
                                    .add_warning(
                                        sender_username
                                    )
                                )

                                if (
                                    warns >= 3
                                    or abuse
                                ):

                                    try:
                                        cl.user_remove_from_thread(
                                            thread_id,
                                            sender_id,
                                        )

                                        ModerationEngine.log_event(
                                            thread_id,
                                            sender_username,
                                            "AUTO-KICK",
                                            reason,
                                        )

                                        kick_card = (
                                            "🚨⚡ 𝗚𝗢𝗗-𝗠𝗢𝗗𝗘 • "
                                            "𝗔𝗨𝗧𝗢-𝗞𝗜𝗖𝗞 ⚡🚨\n\n"

                                            f"👤 𝗢𝗙𝗙𝗘𝗡𝗗𝗘𝗥 ➜ "
                                            f"{fix_mention(sender_username)}\n"

                                            f"🆔 𝗨𝗦𝗘𝗥 𝗜𝗗 ➜ "
                                            f"`{sender_id}`\n"

                                            f"🚫 𝗥𝗘𝗔𝗦𝗢𝗡 ➜ "
                                            f"{reason}\n"

                                            "🛑 𝗦𝗧𝗔𝗧𝗨𝗦 ➜ "
                                            "𝗣𝗘𝗥𝗠𝗔𝗡𝗘𝗡𝗧𝗟𝗬 𝗥𝗘𝗠𝗢𝗩𝗘𝗗\n\n"

                                            f"📢 𝗔𝗗𝗠𝗜𝗡𝗦 ➜ "
                                            f"{admin_mentions}\n\n"

                                            f"🤖 𝗕𝗢𝗧 ➜ "
                                            f"{fix_mention(BOT_USERNAME)}\n"

                                            f"👑 𝗗𝗘𝗩 ➜ "
                                            f"{OWNER_USERNAME}"
                                        )

                                        safe_send(
                                            thread_id,
                                            kick_card,
                                            message_id,
                                        )

                                    except Exception as exc:
                                        log.warning(
                                            "Kick failed: %s",
                                            exc,
                                        )

                                else:

                                    warn_card = (
                                        "⚠️🚨 𝗩𝗜𝗢𝗟𝗔𝗧𝗜𝗢𝗡 "
                                        "𝗪𝗔𝗥𝗡𝗜𝗡𝗚 🚨⚠️\n\n"

                                        f"👤 𝗢𝗙𝗙𝗘𝗡𝗗𝗘𝗥 ➜ "
                                        f"{fix_mention(sender_username)}\n"

                                        f"🚫 𝗥𝗘𝗔𝗦𝗢𝗡 ➜ "
                                        f"{reason}\n"

                                        f"⚠️ 𝗪𝗔𝗥𝗡𝗜𝗡𝗚𝗦 ➜ "
                                        f"{warns}/3\n\n"

                                        f"🤖 𝗕𝗢𝗧 ➜ "
                                        f"{fix_mention(BOT_USERNAME)}\n"

                                        f"👑 𝗗𝗘𝗩 ➜ "
                                        f"{OWNER_USERNAME}"
                                    )

                                    safe_send(
                                        thread_id,
                                        warn_card,
                                        message_id,
                                    )

                                continue

                        # =================================================
                        # 🔐 DEVELOPER-ONLY COMMAND GATE
                        # =================================================

                        if text.startswith("!"):

                            if not is_dev:

                                log.info(
                                    "Blocked command from @%s",
                                    sender_username,
                                )

                                continue

                        # =================================================
                        # COMMAND PARSER
                        # =================================================

                        parts = text.split()

                        command = (
                            parts[0].lower()
                            if parts
                            else ""
                        )

                        argument = (
                            parts[1].lstrip("@")
                            if len(parts) > 1
                            else sender_username
                        )

                        # =================================================
                        # RULES
                        # =================================================

                        if command == "!rules":

                            rules_card = (
                                "⚜️🌷 𝗚𝗖 𝗥𝗨𝗟𝗘𝗦 • "
                                "𝗣𝗟𝗘𝗔𝗦𝗘 𝗥𝗘𝗔𝗗 🌷⚜️\n\n"

                                "🤝 𝗥𝗘𝗦𝗣𝗘𝗖𝗧 "
                                "𝗘𝗩𝗘𝗥𝗬𝗢𝗡𝗘\n"

                                "🚫 𝗡𝗢 𝗔𝗕𝗨𝗦𝗘 • "
                                "𝗡𝗢 𝗧𝗢𝗫𝗜𝗖𝗜𝗧𝗬\n"

                                "🔞 𝗡𝗢 𝗡𝗦𝗙𝗪 / "
                                "𝗔𝗗𝗨𝗟𝗧 𝗖𝗢𝗡𝗧𝗘𝗡𝗧\n"

                                "🔗 𝗡𝗢 "
                                "𝗨𝗡𝗔𝗨𝗧𝗛𝗢𝗥𝗜𝗭𝗘𝗗 𝗟𝗜𝗡𝗞𝗦\n\n"

                                f"🤖 𝗕𝗢𝗧 ➜ "
                                f"{fix_mention(BOT_USERNAME)}\n"

                                f"👑 𝗗𝗘𝗩 ➜ "
                                f"{OWNER_USERNAME}"
                            )

                            safe_send(
                                thread_id,
                                rules_card,
                                message_id,
                            )

                            continue

                        # =================================================
                        # PING / ALIVE
                        # =================================================

                        if command in {
                            "!ping",
                            "!alive",
                        }:

                            ping_card = (
                                "⚡🏓 𝗚𝗢𝗗-𝗠𝗢𝗗𝗘 • "
                                "𝗣𝗜𝗡𝗚 𝗢𝗡𝗟𝗜𝗡𝗘 🏓⚡\n\n"

                                "🚀 STATUS ➜ "
                                "ULTRA PRO MAX ONLINE\n\n"

                                f"🤖 𝗕𝗢𝗧 ➜ "
                                f"{fix_mention(BOT_USERNAME)}\n"

                                f"👑 𝗗𝗘𝗩 ➜ "
                                f"{OWNER_USERNAME}"
                            )

                            safe_send(
                                thread_id,
                                ping_card,
                                message_id,
                            )

                            continue

                        # =================================================
                        # HELP
                        # =================================================

                        if command in {
                            "!help",
                            "!commands",
                            "!menu",
                        }:

                            help_card = (
                                "📜🤖 𝗖𝗢𝗠𝗠𝗔𝗡𝗗𝗦 "
                                "𝗟𝗜𝗦𝗧 🤖📜\n\n"

                                "➜ `!rules` : Show GC Rules\n"
                                "➜ `!ping` : Check Bot Speed\n"
                                "➜ `!bio <username>` : Get Detailed Biodata & Stats\n"
                                "➜ `!dp <username>` : Download HD DP\n"
                                "➜ `!stats <username>` : User Trust Score\n"
                                "➜ `!members` : Member Count\n"
                                "➜ `!admins` : Admin Count\n\n"

                                f"🤖 𝗕𝗢𝗧 ➜ "
                                f"{fix_mention(BOT_USERNAME)}\n"

                                f"👑 𝗗𝗘𝗩 ➜ "
                                f"{OWNER_USERNAME}"
                            )

                            safe_send(
                                thread_id,
                                help_card,
                                message_id,
                            )

                            continue

                        # =================================================
                        # BIO
                        # =================================================

                        if command == "!bio":

                            bio_msg = (
                                ModerationEngine
                                .get_detailed_user_bio(
                                    cl,
                                    argument,
                                )
                            )

                            safe_send(
                                thread_id,
                                bio_msg,
                                message_id,
                            )

                            continue

                        # =================================================
                        # DP
                        # =================================================

                        if command == "!dp":

                            try:

                                info = (
                                    cl.user_info_by_username(
                                        argument
                                    )
                                )

                                if info:

                                    dp_url = (
                                        getattr(
                                            getattr(
                                                info,
                                                "hd_profile_pic_url_info",
                                                None,
                                            ),
                                            "url",
                                            None,
                                        )
                                        or
                                        getattr(
                                            info,
                                            "profile_pic_url_hd",
                                            None,
                                        )
                                        or
                                        getattr(
                                            info,
                                            "profile_pic_url",
                                            None,
                                        )
                                    )

                                    if dp_url:

                                        photo_path = (
                                            cl.photo_download_by_url(
                                                dp_url,
                                                filename=(
                                                    f"{argument}_dp.jpg"
                                                ),
                                            )
                                        )

                                        cl.direct_send_photo(
                                            photo_path,
                                            thread_ids=[
                                                thread_id
                                            ],
                                        )

                                        if os.path.exists(
                                            photo_path
                                        ):
                                            os.remove(
                                                photo_path
                                            )

                            except Exception:
                                log.exception(
                                    "DP command failed"
                                )

                            continue

                        # =================================================
                        # STATS
                        # =================================================

                        if command == "!stats":

                            stats_msg = (
                                ModerationEngine
                                .get_user_stats(
                                    argument
                                )
                            )

                            safe_send(
                                thread_id,
                                stats_msg,
                                message_id,
                            )

                            continue

                        # =================================================
                        # MEMBERS
                        # =================================================

                        if command in {
                            "!members",
                            "!memberlist",
                        }:

                            members_card = (
                                f"👥📊 𝗚𝗥𝗢𝗨𝗣 • "
                                f"𝗠𝗘𝗠𝗕𝗘𝗥𝗦 ➜ "
                                f"`{len(users)}` members\n\n"

                                f"🤖 𝗕𝗢𝗧 ➜ "
                                f"{fix_mention(BOT_USERNAME)}\n"

                                f"👑 𝗗𝗘𝗩 ➜ "
                                f"{OWNER_USERNAME}"
                            )

                            safe_send(
                                thread_id,
                                members_card,
                                message_id,
                            )

                            continue

                        # =================================================
                        # ADMINS
                        # =================================================

                        if command in {
                            "!admins",
                            "!adminlist",
                        }:

                            admin_card = (
                                f"👑🛡️ 𝗚𝗖 ADMINS ➜ "
                                f"`{len(gc_admins)}` active\n\n"

                                f"🤖 𝗕𝗢𝗧 ➜ "
                                f"{fix_mention(BOT_USERNAME)}\n"

                                f"👑 𝗗𝗘𝗩 ➜ "
                                f"{OWNER_USERNAME}"
                            )

                            safe_send(
                                thread_id,
                                admin_card,
                                message_id,
                            )

                            continue

                    # =====================================================
                    # LOOP ERROR
                    # =====================================================

                    with STATE_LOCK:
                        BOT_STATE[
                            "last_cycle"
                        ] = datetime.now(
                            timezone.utc
                        ).isoformat()

                        BOT_STATE[
                            "last_error"
                        ] = None

                    time.sleep(
                        POLL_INTERVAL
                    )

                except (
                    PleaseWaitFewMinutes,
                    ClientThrottledError,
                ) as exc:

                    log.warning(
                        "Rate/throttle response: %s",
                        exc,
                    )

                    time.sleep(60)

                except (
                    LoginRequired,
                    ChallengeRequired,
                ) as exc:

                    with STATE_LOCK:
                        BOT_STATE[
                            "logged_in"
                        ] = False
                        BOT_STATE[
                            "last_error"
                        ] = type(exc).__name__

                    log.error(
                        "Authentication requires attention: %s",
                        type(exc).__name__,
                    )

                    break

                except Exception as exc:

                    with STATE_LOCK:
                        BOT_STATE[
                            "last_error"
                        ] = repr(exc)

                    log.exception(
                        "GC loop error; continuing..."
                    )

                    time.sleep(
                        POLL_INTERVAL
                    )

        except (
            LoginRequired,
            ChallengeRequired,
        ) as exc:

            with STATE_LOCK:
                BOT_STATE[
                    "logged_in"
                ] = False
                BOT_STATE[
                    "last_error"
                ] = type(exc).__name__

            log.error(
                "Login/challenge required: %s",
                type(exc).__name__,
            )

            time.sleep(30)

        except Exception as exc:

            with STATE_LOCK:
                BOT_STATE[
                    "logged_in"
                ] = False
                BOT_STATE[
                    "last_error"
                ] = repr(exc)

            log.exception(
                "Bot crashed; restarting safely..."
            )

            time.sleep(15)


# ============================================================
# START
# ============================================================

def main():

    init_db()

    with STATE_LOCK:
        BOT_STATE[
            "started_at"
        ] = datetime.now(
            timezone.utc
        ).isoformat()

    Thread(
        target=run_flask,
        daemon=True,
    ).start()

    log.info(
        "Health server started."
    )

    start_bot()


if __name__ == "__main__":
    main()
