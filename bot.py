import os
import re
import time
from collections import deque, defaultdict
from datetime import datetime, timezone, timedelta
from threading import Thread, Lock

from flask import Flask
from dotenv import load_dotenv
from instagrapi import Client
from instagrapi.exceptions import (
    PleaseWaitFewMinutes,
    ClientThrottledError,
    LoginRequired,
    ChallengeRequired,
)
from sqlalchemy import create_engine, Column, String, Integer, Float, DateTime, Text, func
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

# ============================================================
# CONFIG — existing deployment variables are preserved
# ============================================================
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Supreme God-Mode Instagram Bot is Running 24/7 Ultra Pro Max!"


def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


BOT_USERNAME = os.getenv("BOT_USERNAME", "YOUR_BOT_USERNAME")
BOT_PASSWORD = os.getenv("BOT_PASSWORD", "YOUR_BOT_PASSWORD")
SESSION_ID = os.getenv("SESSION_ID", "YAHAN_APNI_SESSION_ID_DAL_DENA")

# ONLY these two developers can execute commands.
OWNER_USERNAME = "@fx_smw  ✦  @aat_nnk25"
AUTHORIZED_DEVS = {"fx_smw", "aat_nnk25"}

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///god_mode_bot.db")
POLL_INTERVAL = max(0.8, float(os.getenv("POLL_INTERVAL", "1.0")))

# Per-group state
thread_known_members = {}
thread_lockdown = defaultdict(bool)
thread_antispam = defaultdict(lambda: True)
thread_last_seen = {}

# Bounded caches — avoids unbounded memory growth.
SEEN_MAX = 5000
seen_message_ids = set()
seen_message_queue = deque(maxlen=SEEN_MAX)
recent_sent = {}
recent_activity = defaultdict(lambda: deque(maxlen=8))
state_lock = Lock()

# ============================================================
# CARDS — EXISTING CARD WORDING/DESIGN PRESERVED
# ============================================================
def fix_mention(username: str) -> str:
    if not username:
        return "@User"
    clean_name = str(username).strip().lstrip('@')
    return f"@{clean_name}" if clean_name else "@User"


def footer():
    return f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n👑 𝗗𝗘𝗩 ➜ {OWNER_USERNAME}"


def get_admin_mentions_str(users: list, gc_admins: list) -> str:
    admin_ids = {str(x) for x in gc_admins}
    tags = []
    for u in users:
        if str(getattr(u, "pk", "")) in admin_ids:
            name = getattr(u, "username", None)
            if name:
                tags.append(fix_mention(name))
    return " ".join(tags) if tags else "@Admins"


def card_welcome(username, user_id):
    return (
        f"👋✨ 𝗪𝗘𝗟𝗖𝗢𝗠𝗘 𝗧𝗢 𝗧𝗛𝗘 𝗚𝗖! ✨👋\n\n"
        f"👤 𝗠𝗘𝗠𝗕𝗘𝗥 ➜ {fix_mention(username)}\n"
        f"🆔 𝗨𝗦𝗘𝗥 𝗜𝗗 ➜ `{user_id}`\n"
        f"📜 𝗣𝗟𝗘𝗔𝗦𝗘 𝗖𝗛𝗘𝗖𝗞 𝗥𝗨𝗟𝗘𝗦 ➜ `!rules`\n\n"
        f"{footer()}"
    )


def card_welcome_back(username, user_id):
    return (
        f"🔄✨ 𝗪𝗘𝗟𝗖𝗢𝗠𝗘 𝗕𝗔𝗖𝗞 𝗧𝗢 𝗧𝗛𝗘 𝗚𝗖! ✨🔄\n\n"
        f"👤 𝗠𝗘𝗠𝗕𝗘𝗥 ➜ {fix_mention(username)}\n"
        f"🆔 𝗨𝗦𝗘𝗥 𝗜𝗗 ➜ `{user_id}`\n"
        f"💫 𝗦𝗧𝗔𝗧𝗨𝗦 ➜ 𝗪𝗘𝗟𝗖𝗢𝗠𝗘 𝗕𝗔𝗖𝗞\n\n"
        f"{footer()}"
    )


def card_left(user_id):
    return (
        f"🚪🚶‍♂️ 𝗚𝗖 𝗠𝗘𝗠𝗕𝗘𝗥 • 𝗟𝗘𝗙𝗧 🚶‍♂️🚪\n\n"
        f"🆔 𝗨𝗦𝗘𝗥 𝗜𝗗 ➜ `{user_id}`\n"
        f"💨 𝗦𝗧𝗔𝗧𝗨𝗦 ➜ 𝗟𝗘𝗙𝗧 𝗧𝗛𝗘 𝗚𝗥𝗢𝗨𝗣\n\n"
        f"{footer()}"
    )


def card_kick(target_pk, target_username, reason, admin_tags):
    return (
        f"🚨⚡ 𝗚𝗢𝗗-𝗠𝗢𝗗𝗘 • 𝗔𝗨𝗧𝗢-𝗞𝗜𝗖𝗞 ⚡🚨\n\n"
        f"👤 𝗢𝗙𝗙𝗘𝗡𝗗𝗘𝗥 ➜ {fix_mention(target_username)}\n"
        f"🆔 𝗨𝗦𝗘𝗥 𝗜𝗗 ➜ `{target_pk}`\n"
        f"🚫 𝗥𝗘𝗔𝗦𝗢𝗡 ➜ {reason}\n"
        f"🛑 𝗦𝗧𝗔𝗧𝗨𝗦 ➜ 𝗣𝗘𝗥𝗠𝗔𝗡𝗘𝗡𝗧𝗟𝗬 𝗥𝗘𝗠𝗢𝗩𝗘𝗗\n\n"
        f"📢 𝗔𝗗𝗠𝗜𝗡𝗦 ➜ {admin_tags}\n\n"
        f"{footer()}"
    )


def card_warning(username, reason, warns):
    return (
        f"⚠️🚨 𝗩𝗜𝗢𝗟𝗔𝗧𝗜𝗢𝗡 𝗪𝗔𝗥𝗡𝗜𝗡𝗚 🚨⚠️\n\n"
        f"👤 𝗢𝗙𝗙𝗘𝗡𝗗𝗘𝗥 ➜ {fix_mention(username)}\n"
        f"🚫 𝗥𝗘𝗔𝗦𝗢𝗡 ➜ {reason}\n"
        f"⚠️ 𝗪𝗔𝗥𝗡𝗜𝗡𝗚𝗦 ➜ {warns}/3\n\n"
        f"{footer()}"
    )


def card_rules():
    return (
        "⚜️🌷 𝗚𝗖 𝗥𝗨𝗟𝗘𝗦 • 𝗣𝗟𝗘𝗔𝗦𝗘 𝗥𝗘𝗔𝗗 🌷⚜️\n\n"
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
        "🚫 𝗥𝗘𝗣𝗘𝗔𝗧𝗘𝗗 𝗩𝗜𝗢𝗟𝗔𝗧𝗜𝗢𝗡𝗦 = 𝗥𝗘𝗠𝗢𝗩𝗔𝗟\n\n"
        "🌷 𝗦𝗧𝗔𝗬 𝗔𝗖𝗧𝗜𝗩𝗘 • 𝗦𝗧𝗔𝗬 𝗥𝗘𝗦𝗣𝗘𝗖𝗧𝗙𝗨𝗟 🌷\n"
        "💫 𝗘𝗡𝗝𝗢𝗬 • 𝗖𝗛𝗔𝗧 • 𝗚𝗥𝗢𝗪 • 𝗖𝗢𝗡𝗡𝗘𝗖𝗧 💫\n\n"
        f"{footer()}"
    )


def card_ping():
    return (
        "⚡🏓 𝗚𝗢𝗗-𝗠𝗢𝗗𝗘 • 𝗣𝗜𝗡𝗚 𝗢𝗡𝗟𝗜𝗡𝗘 🏓⚡\n\n"
        "🚀 STATUS ➜ ULTRA PRO MAX ONLINE\n\n"
        f"{footer()}"
    )


def card_permission(username):
    return (
        "🔐🚫 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 𝗢𝗡𝗟𝗬 🚫🔐\n\n"
        f"👤 𝗨𝗦𝗘𝗥 ➜ {fix_mention(username)}\n"
        "⚠️ 𝗦𝗧𝗔𝗧𝗨𝗦 ➜ 𝗬𝗢𝗨 𝗗𝗢 𝗡𝗢𝗧 𝗛𝗔𝗩𝗘 𝗖𝗢𝗠𝗠𝗔𝗡𝗗 𝗣𝗘𝗥𝗠𝗜𝗦𝗦𝗜𝗢𝗡\n\n"
        f"{footer()}"
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
    join_date = Column(DateTime, default=get_utc_now)
    last_active = Column(DateTime, default=get_utc_now)
    total_messages = Column(Integer, default=0)
    warning_count = Column(Integer, default=0)
    violation_count = Column(Integer, default=0)
    trust_score = Column(Float, default=100.0)
    username_changes = Column(Integer, default=0)
    name_changes = Column(Integer, default=0)
    last_known_fullname = Column(String, default="")

class SecurityLog(Base):
    __tablename__ = "security_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=get_utc_now)
    group_id = Column(String)
    username = Column(String)
    event_type = Column(String)
    details = Column(Text)

engine = create_engine(DATABASE_URL, echo=False, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)

def init_db():
    Base.metadata.create_all(engine)

class ModerationEngine:
    @staticmethod
    def record_activity(user_id, username, fullname=""):
        db = SessionLocal()
        try:
            profile = db.query(UserProfile).filter(UserProfile.user_id == str(user_id)).first()
            if not profile:
                db.add(UserProfile(user_id=str(user_id), username=username.lower(), total_messages=1, last_known_fullname=fullname))
            else:
                if profile.username != username.lower():
                    profile.username_changes = (profile.username_changes or 0) + 1
                    profile.username = username.lower()
                if fullname and profile.last_known_fullname and profile.last_known_fullname != fullname:
                    profile.name_changes = (profile.name_changes or 0) + 1
                if fullname:
                    profile.last_known_fullname = fullname
                profile.total_messages = (profile.total_messages or 0) + 1
                profile.last_active = get_utc_now()
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    @staticmethod
    def add_warning(username):
        db = SessionLocal()
        try:
            clean = username.lstrip("@").lower()
            profile = db.query(UserProfile).filter(UserProfile.username == clean).first()
            if profile:
                profile.warning_count = (profile.warning_count or 0) + 1
                profile.violation_count = (profile.violation_count or 0) + 1
                profile.trust_score = max(0.0, (profile.trust_score or 100.0) - 25.0)
                db.commit()
                return profile.warning_count, profile.trust_score
            return 1, 75.0
        finally:
            db.close()

    @staticmethod
    def reset_warnings(username):
        db = SessionLocal()
        try:
            clean = username.lstrip("@").lower()
            profile = db.query(UserProfile).filter(UserProfile.username == clean).first()
            if profile:
                profile.warning_count = 0
                db.commit()
        finally:
            db.close()

    @staticmethod
    def get_stats(username):
        db = SessionLocal()
        try:
            clean = username.lstrip("@").lower()
            p = db.query(UserProfile).filter(UserProfile.username == clean).first()
            if not p:
                return f"❌ User {fix_mention(clean)} not registered in DB yet!\n\n👑 𝗗𝗘𝗩 ➜ {OWNER_USERNAME}"
            score = max(0, min(100, int(p.trust_score or 0)))
            bar = "█" * (score // 10) + "░" * (10 - score // 10)
            return (
                "📊✨ 𝗚𝗢𝗗-𝗠𝗢𝗗𝗘 • 𝗨𝗦𝗘𝗥 𝗦𝗧𝗔𝗧𝗦 ✨📊\n\n"
                f"👤 𝗨𝗦𝗘𝗥 ➜ {fix_mention(p.username)}\n"
                f"🆔 𝗨𝗦𝗘𝗥 𝗜𝗗 ➜ `{p.user_id}`\n"
                f"💬 𝗧𝗢𝗧𝗔𝗟 𝗠𝗦𝗚𝗦 ➜ {p.total_messages}\n"
                f"⚠️ 𝗪𝗔𝗥𝗡𝗜𝗡𝗚𝗦 ➜ {p.warning_count}/3\n"
                f"🚫 𝗩𝗜𝗢𝗟𝗔𝗧𝗜𝗢𝗡𝗦 ➜ {p.violation_count}\n"
                f"💎 𝗧𝗥𝗨𝗦𝗧 𝗦𝗖𝗢𝗥𝗘 ➜ {p.trust_score}%\n"
                f"📈 𝗦𝗖𝗢𝗥𝗘 𝗕𝗔𝗥 ➜ [{bar}]\n\n{footer()}"
            )
        finally:
            db.close()

    @staticmethod
    def logs(limit=10):
        db = SessionLocal()
        try:
            rows = db.query(SecurityLog).order_by(SecurityLog.id.desc()).limit(limit).all()
            if not rows:
                return f"📋 𝗦𝗘𝗖𝗨𝗥𝗜𝗧𝗬 𝗟𝗢𝗚𝗦\n\nNo logs yet.\n\n{footer()}"
            lines = ["📋🛡️ 𝗦𝗘𝗖𝗨𝗥𝗜𝗧𝗬 𝗟𝗢𝗚𝗦 🛡️📋", ""]
            for r in rows:
                lines.append(f"• {r.event_type} | {fix_mention(r.username)} | {r.details[:100]}")
            lines += ["", footer()]
            return "\n".join(lines)
        finally:
            db.close()

    @staticmethod
    def leaderboard(order="messages", limit=10):
        db = SessionLocal()
        try:
            col = UserProfile.total_messages if order == "messages" else UserProfile.trust_score
            rows = db.query(UserProfile).order_by(col.desc()).limit(limit).all()
            title = "𝗧𝗢𝗣 𝗔𝗖𝗧𝗜𝗩𝗘" if order == "messages" else "𝗧𝗢𝗣 𝗧𝗥𝗨𝗦𝗧"
            lines = [f"🏆📊 𝗚𝗢𝗗-𝗠𝗢𝗗𝗘 • {title} 📊🏆", ""]
            for i, p in enumerate(rows, 1):
                value = p.total_messages if order == "messages" else f"{p.trust_score}%"
                lines.append(f"{i}. {fix_mention(p.username)} ➜ `{value}`")
            lines += ["", footer()]
            return "\n".join(lines)
        finally:
            db.close()

    @staticmethod
    def log_event(group_id, username, event_type, details):
        db = SessionLocal()
        try:
            db.add(SecurityLog(group_id=str(group_id), username=username, event_type=event_type, details=details))
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

# ============================================================
# MODERATION
# ============================================================
BAD_WORD_PATTERNS = [
    r"bm[\.\_\-\s]*c\b", r"bb[\.\_\-\s]*c\b", r"bm[\.\_\-\s]*k[\.\_\-\s]*c\b",
    r"bt[\.\_\-\s]*m[\.\_\-\s]*c\b", r"madar\s*chod", r"bhen\s*chod", r"behen\s*chod",
    r"bhosd\w*", r"chut\w*", r"gand\w*", r"gaand\w*", r"lund\w*", r"lauda\w*",
    r"lawda\w*", r"randi\w*", r"bhadwa\w*", r"bhadwe\w*", r"bsdk\w*", r"harami\w*",
    r"f[\.\_\-\s]*u[\.\_\-\s]*c[\.\_\-\s]*k"
]
RESTRICTED_WORDS = {
    "mc", "bc", "mkc", "tmkc", "bsdk", "bsdke", "chutiya", "chutiye", "chutiyap", "gandu",
    "gaandu", "lauda", "luda", "lawda", "lund", "chut", "chuth", "gand", "gaand", "randi",
    "randwa", "bhadwa", "bhadwe", "harami", "haramkhor", "kamine", "kamina", "saala", "saale",
    "madarchod", "maderchod", "madar-chod", "bhenchod", "behenchod", "bhen-chod", "behen-chod",
    "bhosdike", "bhosdi", "bhosda", "fuck", "fucking", "fucker", "motherfucker", "bitch",
    "bastard", "asshole"
}
URL_RE = re.compile(r"https?://\S+|www\.\S+|(?:instagram\.com|t\.me|bit\.ly)/\S+", re.I)


def is_abusive_text(text):
    if not text:
        return False
    low = text.lower()
    if any(w in RESTRICTED_WORDS for w in re.findall(r"\b[\w-]+\b", low)):
        return True
    return any(re.search(p, low) for p in BAD_WORD_PATTERNS)


def is_link_or_promo(text, item_type):
    low = text.lower()
    return bool(URL_RE.search(text)) or item_type in {"clip", "story_share", "media_share"} or "instagram.com/" in low


def mark_seen(message_id):
    if not message_id:
        return False
    with state_lock:
        if message_id in seen_message_ids:
            return True
        if len(seen_message_queue) >= SEEN_MAX:
            old = seen_message_queue.popleft()
            seen_message_ids.discard(old)
        seen_message_queue.append(message_id)
        seen_message_ids.add(message_id)
    return False

# ============================================================
# PROFILE HELPERS
# ============================================================
def obj_get(obj, name, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def get_profile(cl, username):
    return cl.user_info_by_username(username.lstrip("@"))


def profile_card(cl, username):
    try:
        u = get_profile(cl, username)
        if not u:
            return f"❌ User {fix_mention(username)} not found.\n\n{footer()}"
        name = obj_get(u, "full_name", "N/A")
        uname = obj_get(u, "username", username.lstrip("@"))
        uid = obj_get(u, "pk", "N/A")
        followers = obj_get(u, "follower_count", 0)
        following = obj_get(u, "following_count", 0)
        posts = obj_get(u, "media_count", 0)
        bio = obj_get(u, "biography", "N/A") or "N/A"
        private = "🔒 Private" if obj_get(u, "is_private", False) else "🔓 Public"
        verified = "✅ Yes" if obj_get(u, "is_verified", False) else "❌ No"
        meta = obj_get(u, "is_verified_by_instagram", None)
        if meta is None:
            meta = obj_get(u, "is_meta_verified", None)
        meta_text = "N/A" if meta is None else ("✅ Yes" if meta else "❌ No")
        return (
            "👤📋 𝗨𝗦𝗘𝗥 • 𝗙𝗨𝗟𝗟 𝗣𝗥𝗢𝗙𝗜𝗟𝗘 📋👤\n\n"
            f"📌 𝗡𝗔𝗠𝗘 ➜ {name}\n"
            f"🏷️ 𝗨𝗦𝗘𝗥𝗡𝗔𝗠𝗘 ➜ @{uname}\n"
            f"🆔 𝗨𝗦𝗘𝗥 𝗜𝗗 ➜ `{uid}`\n"
            f"👥 𝗙𝗢𝗟𝗟𝗢𝗪𝗘𝗥𝗦 ➜ `{followers}`\n"
            f"👣 𝗙𝗢𝗟𝗟𝗢𝗪𝗜𝗡𝗚 ➜ `{following}`\n"
            f"📸 𝗣𝗢𝗦𝗧𝗦 ➜ `{posts}`\n"
            f"🔒 𝗔𝗖𝗖𝗢𝗨𝗡𝗧 ➜ {private}\n"
            f"✔️ 𝗩𝗘𝗥𝗜𝗙𝗜𝗘𝗗 ➜ {verified}\n"
            f"🛡️ 𝗠𝗘𝗧𝗔 𝗩𝗘𝗥𝗜𝗙𝗜𝗘𝗗 ➜ {meta_text}\n"
            "📅 𝗗𝗔𝗧𝗘 𝗝𝗢𝗜𝗡𝗘𝗗 ➜ N/A (not reliably exposed by this API)\n"
            "🌍 𝗕𝗔𝗦𝗘𝗗 𝗜𝗡 ➜ N/A\n"
            "🔄 𝗙𝗢𝗥𝗠𝗘𝗥 𝗨𝗦𝗘𝗥𝗡𝗔𝗠𝗘𝗦 ➜ N/A\n\n"
            f"📝 𝗕𝗜𝗢𝗚𝗥𝗔𝗣𝗛𝗬:\n`{bio}`\n\n{footer()}"
        )

    except Exception as e:
        return f"❌ Error fetching profile: {e}\n\n{footer()}"

# ============================================================
# BOT LOOP
# ============================================================
def start_bot():
    init_db()
    global BOT_USERNAME

    while True:
        cl = Client()
        cl.set_user_agent(
            "Mozilla/5.0 (Linux; Android 11; SM-G998B) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/115.0.0.0 Mobile Safari/537.36 Instagram"
        )

        try:
            logged_in = False
            if SESSION_ID and SESSION_ID != "YAHAN_APNI_SESSION_ID_DAL_DENA":
                try:
                    cl.login_by_sessionid(SESSION_ID)
                    logged_in = True
                    print("[+] Successfully logged in using Session ID!")
                except Exception as e:
                    print(f"[-] Session ID login failed: {e}")

            if not logged_in:
                cl.login(BOT_USERNAME, BOT_PASSWORD)
                logged_in = True
                print("[+] Successfully logged in using Username & Password!")

            # Derive username when session-only login is used.
            try:
                me = cl.user_info(cl.user_id)
                BOT_USERNAME = obj_get(me, "username", BOT_USERNAME)
            except Exception:
                pass

            print(f"[+] SUCCESS: Bot @{BOT_USERNAME} ACTIVE 🚀")

            while True:
                try:
                    # Fetch a bounded batch. No aggressive polling.
                    threads = cl.direct_threads(amount=20)
                    for mini in threads:
                        if not getattr(mini, "is_group", False):
                            continue
                        thread_id = str(getattr(mini, "id", ""))
                        if not thread_id:
                            continue

                        thread = cl.direct_thread(thread_id)
                        if not thread:
                            continue

                        admins = [str(x) for x in (getattr(thread, "admin_user_ids", None) or [])]
                        bot_pk = str(cl.user_id)

                        # HARD GATE: if bot is not a GC admin, do not process messages/actions.
                        if bot_pk not in set(admins):
                            continue

                        users = list(getattr(thread, "users", []) or [])
                        admin_tags = get_admin_mentions_str(users, admins)
                        current_members = {
                            str(getattr(u, "pk", "")) for u in users
                            if str(getattr(u, "pk", "")) and str(getattr(u, "pk", "")) != bot_pk
                        }

                        # Join/leave detection only for active/admin GCs.
                        previous = thread_known_members.get(thread_id)
                        if previous is None:
                            thread_known_members[thread_id] = set(current_members)
                        else:
                            joined = current_members - previous
                            left = previous - current_members
                            for pk in joined:
                                user = next((u for u in users if str(getattr(u, "pk", "")) == pk), None)
                                if user:
                                    uname = getattr(user, "username", "User")
                                    # If DB already knows them, treat as welcome-back.
                                    db = SessionLocal()
                                    try:
                                        known = db.query(UserProfile).filter(UserProfile.user_id == pk).first()
                                    finally:
                                        db.close()
                                    msg = card_welcome_back(uname, pk) if known else card_welcome(uname, pk)
                                    safe_send_message(cl, thread_id, msg)
                            for pk in left:
                                safe_send_message(cl, thread_id, card_left(pk))
                            thread_known_members[thread_id] = set(current_members)

                        messages = list(getattr(thread, "messages", []) or [])
                        if not messages:
                            continue
                        last = messages[0]
                        message_id = str(getattr(last, "id", ""))
                        if mark_seen(message_id):
                            continue

                        sender_id = str(getattr(last, "user_id", ""))
                        if sender_id == bot_pk:
                            continue

                        sender = next((u for u in users if str(getattr(u, "pk", "")) == sender_id), None)
                        sender_username = getattr(sender, "username", "User") if sender else "User"
                        sender_fullname = getattr(sender, "full_name", "User") if sender else "User"
                        text = str(getattr(last, "text", "") or "").strip()
                        text_lower = text.lower()
                        item_type = str(getattr(last, "item_type", "") or "").lower()

                        ModerationEngine.record_activity(sender_id, sender_username, sender_fullname)

                        # ---------------- STRICT MODERATION ----------------
                        abuse = is_abusive_text(text)
                        link_or_media = is_link_or_promo(text, item_type)
                        now = time.time()
                        activity_key = (thread_id, sender_id)
                        recent_activity[activity_key].append((now, text))
                        repeated = sum(1 for ts, tx in recent_activity[activity_key] if now - ts <= 8 and tx and tx == text) >= 4

                        if abuse or link_or_media or repeated:
                            reason = (
                                "Zero-Tolerance Toxic Abuse" if abuse else
                                "Flood / Repeated Messages" if repeated else
                                "Unauthorized Link / Media Promotion"
                            )
                            warns, _ = ModerationEngine.add_warning(sender_username)
                            # Immediate removal for abuse; 3 warnings for repeated/link violations.
                            if abuse or warns >= 3:
                                try:
                                    cl.user_remove_from_thread(thread_id, sender_id)
                                    ModerationEngine.log_event(thread_id, sender_username, "AUTO-KICK", reason)
                                    safe_send_message(cl, thread_id, card_kick(sender_id, sender_username, reason, admin_tags), message_id)
                                except Exception as e:
                                    ModerationEngine.log_event(thread_id, sender_username, "KICK-FAILED", str(e))
                            else:
                                safe_send_message(cl, thread_id, card_warning(sender_username, reason, warns), message_id)
                            continue

                        # ---------------- COMMAND PERMISSION ----------------
                        if text.startswith("!"):
                            is_dev = sender_username.lower().lstrip("@") in AUTHORIZED_DEVS
                            if not is_dev:
                                safe_send_message(cl, thread_id, card_permission(sender_username), message_id)
                                continue
                            handle_command(cl, thread, users, admins, sender_username, sender_id, text, message_id)

                except (LoginRequired, ChallengeRequired):
                    print("[-] Authentication required. Stopping this client loop for clean re-login.")
                    break
                except (PleaseWaitFewMinutes, ClientThrottledError) as e:
                    print(f"[-] Rate-limit response: {e}; backing off.")
                    time.sleep(20)
                except Exception as e:
                    print(f"[-] GC loop error: {e}")
                    time.sleep(2)

                time.sleep(POLL_INTERVAL)

        except (LoginRequired, ChallengeRequired) as e:
            print(f"[-] Login/challenge state requires user action: {e}")
            time.sleep(30)
        except Exception as e:
            print(f"[-] Bot error: {e}. Restarting in 15 seconds...")
            time.sleep(15)


def send_reply(cl, thread_id, message_id, text):
    try:
        original = cl.direct_message(int(thread_id), int(message_id), amount=20)
        cl.direct_send(text, thread_ids=[int(thread_id)], reply_to_message=original)
        return True
    except Exception as exc:
        print(f"[-] Reply send failed in {thread_id}: {exc}")
        return False


def safe_send_message(cl, thread_id, text_content, reply_to_item_id=None):
    key = (str(thread_id), text_content)
    now = time.time()
    old = recent_sent.get(key)
    if old and now - old < 1.5:
        return False
    recent_sent[key] = now
    if len(recent_sent) > 1000:
        cutoff = now - 60
        for k, ts in list(recent_sent.items()):
            if ts < cutoff:
                recent_sent.pop(k, None)
    try:
        if reply_to_item_id:
            return send_reply(cl, thread_id, reply_to_item_id, text_content)
        cl.direct_send(text_content, thread_ids=[int(thread_id)])
        return True
    except Exception as e:
        print(f"[-] Send failed in {thread_id}: {e}")
        return False


def find_user_in_thread(users, token):
    clean = token.lstrip("@").lower()
    for u in users:
        if str(getattr(u, "username", "")).lower() == clean or str(getattr(u, "pk", "")) == clean:
            return u
    return None


def handle_command(cl, thread, users, admins, sender_username, sender_id, text, message_id):
    thread_id = str(thread.id)
    parts = text.strip().split()
    cmd = parts[0].lower()
    args = parts[1:]

    if cmd in {"!rules"}:
        safe_send_message(cl, thread_id, card_rules(), message_id); return
    if cmd in {"!ping", "!alive"}:
        safe_send_message(cl, thread_id, card_ping(), message_id); return

    if cmd in {"!help", "!commands", "!menu"}:
        safe_send_message(cl, thread_id, command_menu(), message_id); return

    if cmd in {"!profile", "!bio", "!lookup", "!about"}:
        target = args[0] if args else sender_username
        safe_send_message(cl, thread_id, profile_card(cl, target), message_id); return

    if cmd == "!id":
        target = args[0] if args else sender_username
        try:
            u = get_profile(cl, target)
            msg = f"🆔📋 𝗨𝗦𝗘𝗥 𝗜𝗗 ➜ `{obj_get(u, 'pk', 'N/A')}`\n🏷️ 𝗨𝗦𝗘𝗥𝗡𝗔𝗠𝗘 ➜ @{obj_get(u, 'username', target.lstrip('@'))}\n\n{footer()}"
        except Exception as e:
            msg = f"❌ Error: {e}\n\n{footer()}"
        safe_send_message(cl, thread_id, msg, message_id); return

    if cmd in {"!followers", "!following"}:
        target = args[0] if args else sender_username
        try:
            u = get_profile(cl, target)
            field = "follower_count" if cmd == "!followers" else "following_count"
            label = "𝗙𝗢𝗟𝗟𝗢𝗪𝗘𝗥𝗦" if cmd == "!followers" else "𝗙𝗢𝗟𝗟𝗢𝗪𝗜𝗡𝗚"
            msg = f"👥📊 {label} ➜ `{obj_get(u, field, 0)}`\n👤 𝗨𝗦𝗘𝗥 ➜ {fix_mention(obj_get(u, 'username', target))}\n\n{footer()}"
        except Exception as e:
            msg = f"❌ Error: {e}\n\n{footer()}"
        safe_send_message(cl, thread_id, msg, message_id); return

    if cmd == "!dp":
        target = args[0] if args else sender_username
        try:
            u = get_profile(cl, target)
            pic = obj_get(obj_get(u, "hd_profile_pic_url_info", None), "url", None) or obj_get(u, "profile_pic_url_hd", None) or obj_get(u, "profile_pic_url", None)
            if not pic:
                raise RuntimeError("Profile picture URL unavailable")
            path = cl.photo_download_by_url(pic, filename=f"dp_{re.sub(r'[^a-zA-Z0-9_.-]', '_', target)}.jpg")
            cl.direct_send_photo(path, thread_ids=[thread_id])
            try: os.remove(path)
            except OSError: pass
        except Exception as e:
            safe_send_message(cl, thread_id, f"❌ 𝗗𝗣 𝗗𝗢𝗪𝗡𝗟𝗢𝗔𝗗 𝗙𝗔𝗜𝗟𝗘𝗗\n\n{e}\n\n{footer()}", message_id)
        return

    if cmd == "!stats":
        target = args[0] if args else sender_username
        safe_send_message(cl, thread_id, ModerationEngine.get_stats(target), message_id); return

    if cmd in {"!members", "!memberlist"}:
        safe_send_message(cl, thread_id, f"👥📊 𝗚𝗥𝗢𝗨𝗣 • 𝗠𝗘𝗠𝗕𝗘𝗥𝗦 ➜ `{len(users)}` members\n\n{footer()}", message_id); return
    if cmd in {"!admins", "!adminlist"}:
        safe_send_message(cl, thread_id, f"👑🛡️ 𝗚𝗖 𝗔𝗗𝗠𝗜𝗡𝗦 ➜ `{len(admins)}` active\n\n{footer()}", message_id); return
    if cmd in {"!groupid", "!gcinfo"}:
        safe_send_message(cl, thread_id, f"🏠📋 𝗚𝗖 𝗜𝗡𝗙𝗢\n\n🆔 𝗚𝗥𝗢𝗨𝗣 𝗜𝗗 ➜ `{thread_id}`\n👥 𝗠𝗘𝗠𝗕𝗘𝗥𝗦 ➜ `{len(users)}`\n🛡️ 𝗕𝗢𝗧 𝗔𝗗𝗠𝗜𝗡 ➜ ✅\n\n{footer()}", message_id); return

    if cmd in {"!botstatus", "!health"}:
        safe_send_message(cl, thread_id, f"🟢⚡ 𝗕𝗢𝗧 𝗦𝗧𝗔𝗧𝗨𝗦\n\n🚀 𝗦𝗧𝗔𝗧𝗨𝗦 ➜ ONLINE\n🛡️ 𝗚𝗖 𝗔𝗗𝗠𝗜𝗡 ➜ YES\n👑 𝗗𝗘𝗩 𝗔𝗖𝗖𝗘𝗦𝗦 ➜ YES\n\n{footer()}", message_id); return

    if cmd == "!warnings":
        target = args[0] if args else sender_username
        db = SessionLocal()
        try:
            p = db.query(UserProfile).filter(UserProfile.username == target.lstrip("@").lower()).first()
            val = p.warning_count if p else 0
        finally: db.close()
        safe_send_message(cl, thread_id, f"⚠️📊 𝗪𝗔𝗥𝗡𝗜𝗡𝗚𝗦 ➜ `{val}/3`\n👤 𝗨𝗦𝗘𝗥 ➜ {fix_mention(target)}\n\n{footer()}", message_id); return

    if cmd in {"!warn", "!resetwarn", "!kick"}:
        if not args:
            safe_send_message(cl, thread_id, f"❌ Usage: `{cmd} @username`\n\n{footer()}", message_id); return
        target = find_user_in_thread(users, args[0])
        if not target:
            safe_send_message(cl, thread_id, f"❌ User `{args[0]}` is not currently in this GC.\n\n{footer()}", message_id); return
        tpk = str(getattr(target, "pk", "")); tun = getattr(target, "username", "User")
        if tpk == str(cl.user_id):
            safe_send_message(cl, thread_id, f"❌ I cannot remove myself.\n\n{footer()}", message_id); return
        if cmd == "!warn":
            warns, _ = ModerationEngine.add_warning(tun)
            safe_send_message(cl, thread_id, card_warning(tun, "Developer warning", warns), message_id); return
        if cmd == "!resetwarn":
            ModerationEngine.reset_warnings(tun)
            safe_send_message(cl, thread_id, f"♻️✅ 𝗪𝗔𝗥𝗡𝗜𝗡𝗚𝗦 𝗥𝗘𝗦𝗘𝗧 ➜ {fix_mention(tun)}\n\n{footer()}", message_id); return
        try:
            cl.user_remove_from_thread(thread_id, tpk)
            ModerationEngine.log_event(thread_id, tun, "MANUAL-KICK", f"Requested by @{sender_username}")
            safe_send_message(cl, thread_id, card_kick(tpk, tun, "Developer Manual Kick", get_admin_mentions_str(users, admins)), message_id)
        except Exception as e:
            safe_send_message(cl, thread_id, f"❌ 𝗞𝗜𝗖𝗞 𝗙𝗔𝗜𝗟𝗘𝗗 ➜ {e}\n\n{footer()}", message_id)
        return

    if cmd == "!security":
        safe_send_message(cl, thread_id, f"🛡️⚡ 𝗦𝗘𝗖𝗨𝗥𝗜𝗧𝗬 𝗠𝗢𝗗𝗘\n\n🚫 𝗔𝗕𝗨𝗦𝗘 ➜ IMMEDIATE ACTION\n🔗 𝗟𝗜𝗡𝗞/𝗠𝗘𝗗𝗜𝗔 ➜ WARNING SYSTEM\n📢 𝗙𝗟𝗢𝗢𝗗 ➜ WARNING SYSTEM\n🛡️ 𝗕𝗢𝗧 𝗔𝗗𝗠𝗜𝗡 𝗚𝗔𝗧𝗘 ➜ ON\n\n{footer()}", message_id); return
    if cmd == "!logs":
        safe_send_message(cl, thread_id, ModerationEngine.logs(10), message_id); return
    if cmd == "!antispam":
        thread_antispam[thread_id] = not thread_antispam[thread_id]
        state = "ON" if thread_antispam[thread_id] else "OFF"
        safe_send_message(cl, thread_id, f"🛡️📢 𝗔𝗡𝗧𝗜-𝗦𝗣𝗔𝗠 ➜ `{state}`\n\n{footer()}", message_id); return
    if cmd == "!lockdown":
        thread_lockdown[thread_id] = True
        safe_send_message(cl, thread_id, f"🔒🚨 𝗟𝗢𝗖𝗞𝗗𝗢𝗪𝗡 𝗠𝗢𝗗𝗘 ➜ `ON`\n\n{footer()}", message_id); return
    if cmd == "!unlockdown":
        thread_lockdown[thread_id] = False
        safe_send_message(cl, thread_id, f"🔓✅ 𝗟𝗢𝗖𝗞𝗗𝗢𝗪𝗡 𝗠𝗢𝗗𝗘 ➜ `OFF`\n\n{footer()}", message_id); return

    if cmd in {"!topactive", "!activity", "!leaderboard", "!rank"}:
        safe_send_message(cl, thread_id, ModerationEngine.leaderboard("messages"), message_id); return
    if cmd == "!toptrust":
        safe_send_message(cl, thread_id, ModerationEngine.leaderboard("trust"), message_id); return
    if cmd == "!dbstats":
        db = SessionLocal()
        try:
            count = db.query(func.count(UserProfile.user_id)).scalar() or 0
            logs = db.query(func.count(SecurityLog.id)).scalar() or 0
        finally: db.close()
        safe_send_message(cl, thread_id, f"🗄️📊 𝗗𝗔𝗧𝗔𝗕𝗔𝗦𝗘 𝗦𝗧𝗔𝗧𝗦\n\n👤 𝗣𝗥𝗢𝗙𝗜𝗟𝗘𝗦 ➜ `{count}`\n📋 𝗟𝗢𝗚𝗦 ➜ `{logs}`\n\n{footer()}", message_id); return

    if cmd == "!devpanel":
        safe_send_message(cl, thread_id, f"👑🛠️ 𝗗𝗘𝗩 𝗣𝗔𝗡𝗘𝗟\n\n👑 𝗗𝗘𝗩𝗦 ➜ {OWNER_USERNAME}\n🛡️ 𝗖𝗢𝗠𝗠𝗔𝗡𝗗 𝗔𝗖𝗖𝗘𝗦𝗦 ➜ DEVELOPER ONLY\n🚀 𝗚𝗖 𝗚𝗔𝗧𝗘 ➜ BOT MUST BE ADMIN\n\n{footer()}", message_id); return

    if cmd == "!reload":
        recent_sent.clear(); thread_last_seen.clear()
        safe_send_message(cl, thread_id, f"♻️⚡ 𝗥𝗘𝗟𝗢𝗔𝗗 𝗖𝗟𝗘𝗔𝗡𝗨𝗣 𝗖𝗢𝗠𝗣𝗟𝗘𝗧𝗘\n\n{footer()}", message_id); return

    safe_send_message(cl, thread_id, f"❓ 𝗨𝗡𝗞𝗡𝗢𝗪𝗡 𝗖𝗢𝗠𝗠𝗔𝗡𝗗 ➜ `{cmd}`\n📜 Use `!help`\n\n{footer()}", message_id)


def command_menu():
    return (
        "📜🤖 𝗖𝗢𝗠𝗠𝗔𝗡𝗗𝗦 𝗟𝗜𝗦𝗧 🤖📜\n\n"
        "👤 𝗣𝗥𝗢𝗙𝗜𝗟𝗘\n"
        "➜ `!profile @user` • `!bio @user` • `!about @user`\n"
        "➜ `!lookup @user` • `!id @user` • `!dp @user`\n"
        "➜ `!followers @user` • `!following @user` • `!stats @user`\n\n"
        "🏠 𝗚𝗖\n"
        "➜ `!gcinfo` • `!groupid` • `!members` • `!memberlist`\n"
        "➜ `!admins` • `!adminlist` • `!rules`\n\n"
        "🛡️ 𝗠𝗢𝗗𝗘𝗥𝗔𝗧𝗜𝗢𝗡\n"
        "➜ `!warn @user` • `!warnings @user` • `!resetwarn @user`\n"
        "➜ `!kick @user` • `!security` • `!logs`\n"
        "➜ `!antispam` • `!lockdown` • `!unlockdown`\n\n"
        "📊 𝗦𝗧𝗔𝗧𝗦\n"
        "➜ `!topactive` • `!toptrust` • `!activity` • `!rank`\n"
        "➜ `!leaderboard` • `!dbstats`\n\n"
        "⚡ 𝗦𝗬𝗦𝗧𝗘𝗠\n"
        "➜ `!ping` • `!alive` • `!botstatus` • `!health`\n"
        "➜ `!devpanel` • `!reload`\n\n"
        "🔐 𝗡𝗢𝗧𝗘 ➜ 𝗖𝗢𝗠𝗠𝗔𝗡𝗗𝗦 𝗔𝗥𝗘 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥-𝗢𝗡𝗟𝗬\n"
        "🛡️ 𝗚𝗖 𝗠𝗨𝗦𝗧 𝗛𝗔𝗩𝗘 𝗕𝗢𝗧 𝗔𝗦 𝗔𝗡 𝗔𝗗𝗠𝗜𝗡\n\n"
        f"{footer()}"
    )


if __name__ == "__main__":
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    start_bot()
