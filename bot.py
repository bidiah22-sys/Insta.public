import os
import re
import time
from datetime import datetime, timezone
from threading import Thread
from flask import Flask
from dotenv import load_dotenv
from instagrapi import Client
from instagrapi.exceptions import PleaseWaitFewMinutes, ClientThrottledError, LoginRequired, ChallengeRequired
from sqlalchemy import create_engine, Column, String, Integer, Float, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

# --- Flask Server for Render 24/7 Uptime ---
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Supreme God-Mode Instagram Bot is Running 24/7 Ultra Pro Max!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# --- Credentials & Config ---
BOT_USERNAME = os.getenv("BOT_USERNAME", "pookieee_bot2.0")
BOT_PASSWORD = os.getenv("BOT_PASSWORD", "")
SESSION_ID = os.getenv("SESSION_ID", "")

OWNER_USERNAME = os.getenv("OWNER_USERNAME", "@fx_smw ✘ @aat_nnk25")
# Commands are intentionally restricted to these two developer accounts only.
AUTHORIZED_DEVS = ["fx_smw", "aat_nnk25"]
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///god_mode_bot.db")
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "2.0"))

SHADOWBANNED_USERS = set()
TARGETED_USERS = set()
LOCKDOWN_MODE = False
thread_known_members = {}
user_message_timestamps = {}

def fix_mention(username: str) -> str:
    if not username:
        return "@User"
    clean_name = str(username).strip().lstrip('@')
    return f"@{clean_name}" if clean_name else "@User"

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

# --- ADVANCED ABUSE DETECTION PATTERNS ---
BAD_WORD_PATTERNS = [
    r'bm[\.\_\-\s]*c\b', r'bb[\.\_\-\s]*c\b', r'bm[\.\_\-\s]*k[\.\_\-\s]*c\b',
    r'bt[\.\_\-\s]*m[\.\_\-\s]*c\b', r'madar\s*chod', r'bhen\s*chod', r'behen\s*chod', 
    r'bhosd\w*', r'chut\w*', r'gand\w*', r'gaand\w*', r'lund\w*', r'lauda\w*', 
    r'lawda\w*', r'randi\w*', r'bhadwa\w*', r'bhadwe\w*', r'bsdk\w*', r'harami\w*', 
    r'f[\.\_\-\s]*u[\.\_\-\s]*c[\.\_\-\s]*k'
]

RESTRICTED_WORDS = {
    "mc", "bc", "mkc", "tmkc", "bsdk", "bsdke", "chutiya", "chutiye",
    "chutiyap", "gandu", "gaandu", "lauda", "luda", "lawda", "lund",
    "chut", "chuth", "gand", "gaand", "randi", "randwa", "bhadwa",
    "bhadwe", "harami", "haramkhor", "kamine", "kamina", "saala",
    "saale", "madarchod", "maderchod", "madar-chod", "bhenchod",
    "behenchod", "bhen-chod", "behen-chod", "bhosdike", "bhosdi",
    "bhosda", "fuck", "fucking", "fucker", "motherfucker", "bitch",
    "bastard", "asshole"
}

Base = declarative_base()

def get_utc_now():
    return datetime.now(timezone.utc)

class UserProfile(Base):
    __tablename__ = 'user_profiles'
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
    __tablename__ = 'security_logs'
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


def _clean_value(value, default="N/A"):
    if value is None or value == "":
        return default
    return value

def _bool_text(value, yes="Yes", no="No"):
    return f"✅ {yes}" if bool(value) else f"❌ {no}"

def get_instagram_profile(cl: Client, username: str):
    clean = str(username).strip().lstrip("@").lower()
    if not clean:
        return None
    try:
        return cl.user_info_by_username(clean)
    except Exception:
        return None

def get_tracked_profile(user_id: str):
    db = SessionLocal()
    try:
        return db.query(UserProfile).filter(UserProfile.user_id == str(user_id)).first()
    finally:
        db.close()

def profile_card(cl: Client, username: str, thread=None, thread_users=None, gc_admins=None):
    clean = str(username).strip().lstrip("@").lower()
    u = get_instagram_profile(cl, clean)
    if not u:
        return f"❌ 𝗣𝗥𝗢𝗙𝗜𝗟𝗘 𝗡𝗢𝗧 𝗔𝗩𝗔𝗜𝗟𝗔𝗕𝗟𝗘\n\n👤 𝗨𝗦𝗘𝗥 ➜ @{clean}\n\n🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n👑 𝗗𝗘𝗩 ➜ {OWNER_USERNAME}"

    uid = str(_clean_value(getattr(u, "pk", None)))
    uname = _clean_value(getattr(u, "username", None), clean)
    fullname = _clean_value(getattr(u, "full_name", None))
    bio = _clean_value(getattr(u, "biography", None), "No bio")
    followers = _clean_value(getattr(u, "follower_count", None), 0)
    following = _clean_value(getattr(u, "following_count", None), 0)
    media = _clean_value(getattr(u, "media_count", None), 0)
    private = _bool_text(getattr(u, "is_private", False), "Private", "Public")
    verified = _bool_text(getattr(u, "is_verified", False))

    # These fields are shown only when the installed Instagram client actually exposes them.
    # No value is invented if Instagram does not provide it.
    meta_verified_raw = getattr(u, "is_meta_verified", None)
    if meta_verified_raw is None:
        meta_verified_raw = getattr(u, "is_meta_verified", None)
    meta_verified = "N/A • Not exposed by profile endpoint" if meta_verified_raw is None else ("✅ Yes" if meta_verified_raw else "❌ No")
    joined = _clean_value(getattr(u, "date_joined", None), "N/A • Not exposed by profile endpoint")
    based_in = _clean_value(getattr(u, "country", None), None)
    if based_in is None:
        based_in = _clean_value(getattr(u, "location", None), None)
    if based_in is None:
        based_in = "N/A • Not exposed by profile endpoint"
    former = getattr(u, "former_usernames", None)
    if former:
        if isinstance(former, (list, tuple, set)):
            former = ", ".join("@" + str(x).lstrip("@") for x in former)
    else:
        former = "N/A • Not exposed by profile endpoint"

    tracked = get_tracked_profile(uid)
    bot_seen = tracked.join_date.strftime("%Y-%m-%d %H:%M UTC") if tracked and tracked.join_date else "N/A"
    last_active = tracked.last_active.strftime("%Y-%m-%d %H:%M UTC") if tracked and tracked.last_active else "N/A"
    msg_count = tracked.total_messages if tracked else 0
    warnings = tracked.warning_count if tracked else 0
    violations = tracked.violation_count if tracked else 0
    trust = tracked.trust_score if tracked else 100.0
    uname_changes = tracked.username_changes if tracked else 0
    name_changes = tracked.name_changes if tracked else 0

    gc_status = "Not in this GC"
    gc_role = "N/A"
    current_gc = "N/A"
    security = "UNKNOWN"
    if thread is not None and thread_users is not None and gc_admins is not None:
        ids = {str(getattr(x, "pk", "")): x for x in thread_users}
        if uid in ids:
            gc_status = "Member"
            gc_role = "Admin" if uid in {str(x) for x in gc_admins} else "Member"
            current_gc = str(getattr(thread, "thread_title", None) or getattr(thread, "id", "N/A"))
            security = "LOCKDOWN" if LOCKDOWN_MODE else "ACTIVE"

    return (
        "👤✨ 𝗨𝗟𝗧𝗥𝗔 • 𝗜𝗡𝗦𝗧𝗔𝗚𝗥𝗔𝗠 𝗣𝗥𝗢𝗙𝗜𝗟𝗘 ✨👤\n\n"
        f"📌 𝗡𝗔𝗠𝗘 ➜ {fullname}\n"
        f"🏷️ 𝗨𝗦𝗘𝗥𝗡𝗔𝗠𝗘 ➜ @{uname}\n"
        f"🆔 𝗨𝗦𝗘𝗥 𝗜𝗗 ➜ `{uid}`\n"
        f"👥 𝗙𝗢𝗟𝗟𝗢𝗪𝗘𝗥𝗦 ➜ `{followers}`\n"
        f"👣 𝗙𝗢𝗟𝗟𝗢𝗪𝗜𝗡𝗚 ➜ `{following}`\n"
        f"📸 𝗣𝗢𝗦𝗧𝗦 ➜ `{media}`\n"
        f"🔒 𝗔𝗖𝗖𝗢𝗨𝗡𝗧 ➜ {private}\n"
        f"✔️ 𝗩𝗘𝗥𝗜𝗙𝗜𝗘𝗗 ➜ {verified}\n"
        f"🛡️ 𝗠𝗘𝗧𝗔 𝗩𝗘𝗥𝗜𝗙𝗜𝗘𝗗 ➜ {meta_verified}\n"
        f"📅 𝗗𝗔𝗧𝗘 𝗝𝗢𝗜𝗡𝗘𝗗 ➜ {joined}\n"
        f"🌍 𝗕𝗔𝗦𝗘𝗗 𝗜𝗡 / 𝗖𝗢𝗨𝗡𝗧𝗥𝗬 ➜ {based_in}\n"
        f"🔄 𝗙𝗢𝗥𝗠𝗘𝗥 𝗨𝗦𝗘𝗥𝗡𝗔𝗠𝗘𝗦 ➜ {former}\n\n"
        f"📝 𝗕𝗜𝗢 ➜ {bio}\n\n"
        "📊 𝗕𝗢𝗧-𝗧𝗥𝗔𝗖𝗞𝗘𝗗 𝗛𝗜𝗦𝗧𝗢𝗥𝗬\n"
        f"👁️ 𝗕𝗢𝗧 𝗙𝗜𝗥𝗦𝗧 𝗦𝗘𝗘𝗡 ➜ {bot_seen}\n"
        f"🕒 𝗟𝗔𝗦𝗧 𝗔𝗖𝗧𝗜𝗩𝗘 ➜ {last_active}\n"
        f"💬 𝗚𝗖 𝗠𝗘𝗦𝗦𝗔𝗚𝗘𝗦 ➜ {msg_count}\n"
        f"⚠️ 𝗪𝗔𝗥𝗡𝗜𝗡𝗚𝗦 ➜ {warnings}\n"
        f"🚫 𝗩𝗜𝗢𝗟𝗔𝗧𝗜𝗢𝗡𝗦 ➜ {violations}\n"
        f"💎 𝗧𝗥𝗨𝗦𝗧 ➜ {trust}%\n"
        f"🔤 𝗨𝗦𝗘𝗥𝗡𝗔𝗠𝗘 𝗖𝗛𝗔𝗡𝗚𝗘𝗦 ➜ {uname_changes} (tracked by bot)\n"
        f"📝 𝗡𝗔𝗠𝗘 𝗖𝗛𝗔𝗡𝗚𝗘𝗦 ➜ {name_changes} (tracked by bot)\n\n"
        "🛡️ 𝗖𝗨𝗥𝗥𝗘𝗡𝗧 𝗚𝗖 𝗦𝗧𝗔𝗧𝗨𝗦\n"
        f"👥 𝗠𝗘𝗠𝗕𝗘𝗥 𝗦𝗧𝗔𝗧𝗨𝗦 ➜ {gc_status}\n"
        f"👑 𝗚𝗖 𝗥𝗢𝗟𝗘 ➜ {gc_role}\n"
        f"💬 𝗖𝗨𝗥𝗥𝗘𝗡𝗧 𝗚𝗖 ➜ {current_gc}\n"
        f"🔐 𝗚𝗖 𝗦𝗘𝗖𝗨𝗥𝗜𝗧𝗬 ➜ {security}\n\n"
        f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
        f"👑 𝗗𝗘𝗩 ➜ {OWNER_USERNAME}"
    )

class ModerationEngine:
    @staticmethod
    def record_activity(user_id: str, username: str, fullname: str = ""):
        db = SessionLocal()
        try:
            profile = db.query(UserProfile).filter(UserProfile.user_id == str(user_id)).first()
            if not profile:
                profile = UserProfile(
                    user_id=str(user_id), 
                    username=username.lower(), 
                    total_messages=1, 
                    trust_score=100.0,
                    last_known_fullname=fullname
                )
                db.add(profile)
            else:
                if profile.username != username.lower():
                    profile.username_changes = (profile.username_changes or 0) + 1
                    profile.username = username.lower()
                
                if fullname and profile.last_known_fullname and profile.last_known_fullname != fullname:
                    profile.name_changes = (profile.name_changes or 0) + 1
                    profile.last_known_fullname = fullname
                elif not profile.last_known_fullname and fullname:
                    profile.last_known_fullname = fullname

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
            clean_user = username.lstrip('@').lower()
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
            clean_user = username.lstrip('@').lower()
            profile = db.query(UserProfile).filter(UserProfile.username == clean_user).first()
            if profile:
                profile.warning_count = 0
                db.commit()
        finally:
            db.close()

    @staticmethod
    def get_detailed_user_bio(cl: Client, username: str) -> str:
        return profile_card(cl, username)

    @staticmethod
    def get_user_stats(username: str) -> str:
        db = SessionLocal()
        try:
            clean_user = username.lstrip('@').lower()
            profile = db.query(UserProfile).filter(UserProfile.username == clean_user).first()
            if profile:
                score = int(profile.trust_score)
                filled = score // 10
                bar = "█" * filled + "░" * (10 - filled)
                return (
                    f"📊✨ 𝗚𝗢𝗗-𝗠𝗢𝗗𝗘 • 𝗨𝗦𝗘𝗥 𝗦𝗧𝗔𝗧𝗦 ✨📊\n\n"
                    f"👤 𝗨𝗦𝗘𝗥 ➜ {fix_mention(profile.username)}\n"
                    f"🆔 𝗨𝗦𝗘𝗥 𝗜𝗗 ➜ `{profile.user_id}`\n"
                    f"💬 𝗧𝗢𝗧𝗔𝗟 𝗠𝗦𝗚𝗦 ➜ {profile.total_messages}\n"
                    f"⚠️ 𝗪𝗔𝗥𝗡𝗜𝗡𝗚𝗦 ➜ {profile.warning_count}/3\n"
                    f"🚫 𝗩𝗜𝗢𝗟𝗔𝗧𝗜𝗢𝗡𝗦 ➜ {profile.violation_count}\n"
                    f"💎 𝗧𝗥𝗨𝗦𝗧 𝗦𝗖𝗢𝗥𝗘 ➜ {profile.trust_score}%\n"
                    f"📈 𝗦𝗖𝗢𝗥𝗘 𝗕𝗔𝗥 ➜ [{bar}]\n\n"
                    f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                    f"👑 𝗗𝗘𝗩 ➜ {OWNER_USERNAME}"
                )
            return f"❌ User {fix_mention(clean_user)} not registered in DB yet!\n\n👑 𝗗𝗘𝗩 ➜ {OWNER_USERNAME}"
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

def is_abusive_text(text: str) -> bool:
    if not text:
        return False
    text_lower = text.lower()
    words = re.findall(r'\b\w+\b', text_lower)
    for w in words:
        if w in RESTRICTED_WORDS:
            return True
    for pattern in BAD_WORD_PATTERNS:
        if re.search(pattern, text_lower):
            return True
    return False

def start_bot():
    global LOCKDOWN_MODE, SHADOWBANNED_USERS, TARGETED_USERS, thread_known_members, user_message_timestamps
    init_db()

    while True:
        try:
            print("[*] Initializing Supreme God-Mode Bot Engine...")
            cl = Client()
            cl.set_user_agent("Mozilla/5.0 (Linux; Android 11; SM-G998B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Mobile Safari/537.36 Instagram")

            logged_in = False

            if SESSION_ID and SESSION_ID != "YAHAN_APNI_SESSION_ID_DAL_DENA":
                try:
                    cl.login_by_sessionid(SESSION_ID)
                    logged_in = True
                    print("[+] Successfully logged in using Session ID!")
                except Exception as e:
                    print(f"[-] Session ID login failed: {e}")

            if not logged_in and BOT_PASSWORD:
                try:
                    cl.login(BOT_USERNAME, BOT_PASSWORD)
                    logged_in = True
                    print("[+] Successfully logged in using configured credentials!")
                except Exception as e:
                    print(f"[-] Credentials login failed: {e}")
                    time.sleep(20)
                    continue

            if not logged_in:
                print("[-] No valid SESSION_ID or BOT_PASSWORD configured.")
                time.sleep(20)
                continue

            print(f"[+] SUCCESS: Bot @{BOT_USERNAME} ULTRA PRO MAX ACTIVE! 🚀🔥")

            seen_message_ids = set()
            recent_sent_texts = {}

            def safe_send_message(thread_id, text_content, reply_to_item_id=None):
                current_time = time.time()
                if thread_id in recent_sent_texts:
                    last_text, last_time = recent_sent_texts[thread_id]
                    if last_text == text_content and (current_time - last_time < 0.5):
                        return
                recent_sent_texts[thread_id] = (text_content, current_time)
                try:
                    if reply_to_item_id:
                        cl.direct_answer(thread_id, reply_to_item_id, text_content)
                    else:
                        cl.direct_send(text_content, thread_ids=[thread_id])
                except Exception:
                    try:
                        cl.direct_send(text_content, thread_ids=[thread_id])
                    except Exception:
                        pass
                time.sleep(0.1)

            def execute_kick(thread_id, target_pk, target_username, reason, admin_tags, reply_to_id=None, silent=False):
                try:
                    cl.user_remove_from_thread(thread_id, target_pk)
                    ModerationEngine.log_event(thread_id, target_username, "AUTO-KICK", reason)
                    if not silent:
                        kick_card = (
                            f"🚨⚡ 𝗚𝗢𝗗-𝗠𝗢𝗗𝗘 • 𝗔𝗨𝗧𝗢-𝗞𝗜𝗖𝗞 ⚡🚨\n\n"
                            f"👤 𝗢𝗙𝗙𝗘𝗡𝗗𝗘𝗥 ➜ {fix_mention(target_username)}\n"
                            f"🆔 𝗨𝗦𝗘𝗥 𝗜𝗗 ➜ `{target_pk}`\n"
                            f"🚫 𝗥𝗘𝗔𝗦𝗢𝗡 ➜ {reason}\n"
                            f"🛑 𝗦𝗧𝗔𝗧𝗨𝗦 ➜ 𝗣𝗘𝗥𝗠𝗔𝗡𝗘𝗡𝗧𝗟𝗬 𝗥𝗘𝗠𝗢𝗩𝗘𝗗\n\n"
                            f"📢 𝗔𝗗𝗠𝗜𝗡𝗦 ➜ {admin_tags}\n\n"
                            f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                            f"👑 𝗗𝗘𝗩 ➜ {OWNER_USERNAME}"
                        )
                        safe_send_message(thread_id, kick_card, reply_to_item_id=reply_to_id)
                except Exception:
                    pass

            while True:
                try:
                    threads = cl.direct_threads(amount=20)

                    for thread_mini in threads:
                        if not getattr(thread_mini, "is_group", False):
                            continue

                        thread_id = thread_mini.id
                        thread = cl.direct_thread(thread_id)
                        if not thread:
                            continue

                        gc_admins = []
                        try:
                            if hasattr(thread, 'admin_user_ids') and thread.admin_user_ids:
                                gc_admins = [str(uid) for uid in thread.admin_user_ids]
                        except Exception:
                            gc_admins = []

                        bot_pk = str(cl.user_id)
                        users = list(getattr(thread, "users", []) or [])
                        admin_ids_str = {str(x) for x in gc_admins}
                        # The bot only operates inside GCs where its own account is an admin.
                        if bot_pk not in admin_ids_str:
                            continue
                        admin_mentions_tag = get_admin_mentions_str(users, gc_admins)

                        current_user_pks = {str(getattr(u, "pk", "")) for u in users if str(getattr(u, "pk", "")) != bot_pk}
                        if thread_id not in thread_known_members:
                            thread_known_members[thread_id] = current_user_pks
                        else:
                            old_members = thread_known_members[thread_id]
                            
                            # --- 1. NEW MEMBERS JOIN DETECTION ---
                            new_members = current_user_pks - old_members
                            if new_members:
                                for new_pk in new_members:
                                    thread_known_members[thread_id].add(new_pk)

                                new_users_info = []
                                for npk in new_members:
                                    for u in users:
                                        if str(getattr(u, "pk", "")) == npk:
                                            uname = getattr(u, "username", "User")
                                            upk_val = npk
                                            new_users_info.append((uname, upk_val))
                                            break

                                if len(new_users_info) == 1:
                                    u_name, u_id = new_users_info[0]
                                    welcome_card = (
                                        f"👋✨ 𝗪𝗘𝗟𝗖𝗢𝗠𝗘 𝗧𝗢 𝗧𝗛𝗘 𝗚𝗖! ✨👋\n\n"
                                        f"👤 𝗠𝗘𝗠𝗕𝗘𝗥 ➜ {fix_mention(u_name)}\n"
                                        f"🆔 𝗨𝗦𝗘𝗥 𝗜𝗗 ➜ `{u_id}`\n"
                                        f"📜 𝗣𝗟𝗘𝗔𝗦𝗘 𝗖𝗛𝗘𝗖𝗞 𝗥𝗨𝗟𝗘𝗦 ➜ `!rules`\n\n"
                                        f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                        f"👑 𝗗𝗘𝗩 ➜ {OWNER_USERNAME}"
                                    )
                                    safe_send_message(thread_id, welcome_card)

                            # --- 2. MEMBERS LEFT DETECTION ---
                            left_members = old_members - current_user_pks
                            if left_members:
                                for left_pk in left_members:
                                    thread_known_members[thread_id].discard(left_pk)
                                    left_card = (
                                        f"🚪🚶‍♂️ 𝗚𝗖 𝗠𝗘𝗠𝗕𝗘𝗥 • 𝗟𝗘𝗙𝗧 🚶‍♂️🚪\n\n"
                                        f"🆔 𝗨𝗦𝗘𝗥 𝗜𝗗 ➜ `{left_pk}`\n"
                                        f"💨 𝗦𝗧𝗔𝗧𝗨𝗦 ➜ 𝗟𝗘𝗙𝗧 𝗧𝗛𝗘 𝗚𝗥𝗢𝗨𝗣\n\n"
                                        f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                        f"👑 𝗗𝗘𝗩 ➜ {OWNER_USERNAME}"
                                    )
                                    safe_send_message(thread_id, left_card)

                        messages = list(getattr(thread, "messages", []) or [])
                        if messages:
                            last_msg = messages[0]
                            message_id = str(getattr(last_msg, "id", ""))

                            if message_id and message_id not in seen_message_ids:
                                seen_message_ids.add(message_id)
                                if len(seen_message_ids) > 5000:
                                    seen_message_ids.clear()

                                text = str(getattr(last_msg, "text", "") or "").strip()
                                text_lower = text.lower()
                                sender_id = str(getattr(last_msg, "user_id", ""))
                                item_type = str(getattr(last_msg, "item_type", "") or "").lower()

                                sender_username = "User"
                                sender_fullname = "User"
                                for u in users:
                                    if str(getattr(u, "pk", "")) == sender_id:
                                        sender_username = getattr(u, "username", "User")
                                        sender_fullname = getattr(u, "full_name", "User")
                                        break

                                if sender_id == bot_pk:
                                    continue

                                is_sender_admin = sender_id in admin_ids_str
                                is_dev = sender_username.lower() in [d.lower() for d in AUTHORIZED_DEVS]

                                ModerationEngine.record_activity(sender_id, sender_username, sender_fullname)

                                # --- ABUSE & LINK MODERATION ---
                                if not is_dev and not is_sender_admin:
                                    is_abuse = is_abusive_text(text)
                                    is_reel_or_link = any(kw in text_lower for kw in [
                                        "http://", "https://", "www.", "instagram.com", "t.me", "bit.ly", 
                                        "instagram.com/reel", "instagram.com/p/", "instagram.com/tv/", "instagram.com/stories/"
                                    ]) or item_type in ["clip", "story_share", "media_share"]

                                    if is_abuse or is_reel_or_link:
                                        reason = "Zero-Tolerance Toxic Abuse" if is_abuse else "Unauthorized Link / Reel Promotion"
                                        warns, trust = ModerationEngine.add_warning(sender_username)

                                        if warns >= 3 or is_abuse:
                                            execute_kick(thread_id, sender_id, sender_username, reason, admin_mentions_tag, reply_to_id=message_id)
                                        else:
                                            warn_card = (
                                                f"⚠️🚨 𝗩𝗜𝗢𝗟𝗔𝗧𝗜𝗢𝗡 𝗪𝗔𝗥𝗡𝗜𝗡𝗚 🚨⚠️\n\n"
                                                f"👤 𝗢𝗙𝗙𝗘𝗡𝗗𝗘𝗥 ➜ {fix_mention(sender_username)}\n"
                                                f"🚫 𝗥𝗘𝗔𝗦𝗢𝗡 ➜ {reason}\n"
                                                f"⚠️ 𝗪𝗔𝗥𝗡𝗜𝗡𝗚𝗦 ➜ {warns}/3\n\n"
                                                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                                f"👑 𝗗𝗘𝗩 ➜ {OWNER_USERNAME}"
                                            )
                                            safe_send_message(thread_id, warn_card, reply_to_item_id=message_id)
                                        continue

                                # --- COMMAND AUTHORIZATION ---
                                # GC-admin status does NOT grant command access. Only the two configured developers may run commands.
                                command_prefix = text_lower.startswith("!")
                                if command_prefix and not is_dev:
                                    continue

                                # --- ALL COMMANDS HANDLER ---
                                if text_lower == "!rules":
                                    rules_card = (
                                        f"⚜️🌷 𝗚𝗖 𝗥𝗨𝗟𝗘𝗦 • 𝗣𝗟𝗘𝗔𝗦𝗘 𝗥𝗘𝗔𝗗 🌷⚜️\n\n"
                                        f"🤝 𝗥𝗘𝗦𝗣𝗘𝗖𝗧 𝗘𝗩𝗘𝗥𝗬𝗢𝗡𝗘\n"
                                        f"🚫 𝗡𝗢 𝗔𝗕𝗨𝗦𝗘 • 𝗡𝗢 𝗧𝗢𝗫𝗜𝗖𝗜𝗧𝗬\n"
                                        f"🔞 𝗡𝗢 𝗡𝗦𝗙𝗪 / 𝗔𝗗𝗨𝗟𝗧 𝗖𝗢𝗡𝗧𝗘𝗡𝗧\n"
                                        f"🔗 𝗡𝗢 𝗨𝗡𝗔𝗨𝗧𝗛𝗢𝗥𝗜𝗭𝗘𝗗 𝗟𝗜𝗡𝗞𝗦\n\n"
                                        f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                        f"👑 𝗗𝗘𝗩 ➜ {OWNER_USERNAME}"
                                    )
                                    safe_send_message(thread_id, rules_card, reply_to_item_id=message_id)
                                    continue

                                if text_lower in ["!ping", "!alive"]:
                                    ping_card = (
                                        f"⚡🏓 𝗚𝗢𝗗-𝗠𝗢𝗗𝗘 • 𝗣𝗜𝗡𝗚 𝗢𝗡𝗟𝗜𝗡𝗘 🏓⚡\n\n"
                                        f"🚀 STATUS ➜ ULTRA PRO MAX ONLINE\n\n"
                                        f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                        f"👑 𝗗𝗘𝗩 ➜ {OWNER_USERNAME}"
                                    )
                                    safe_send_message(thread_id, ping_card, reply_to_item_id=message_id)
                                    continue

                                if text_lower in ["!help", "!commands", "!menu"]:
                                    help_card = (
                                        f"📜🤖 𝗖𝗢𝗠𝗠𝗔𝗡𝗗𝗦 𝗟𝗜𝗦𝗧 🤖📜\n\n"
                                        f"➜ `!rules` • `!ping` • `!alive`\n"
                                        f"➜ `!profile @user` • `!bio @user` • `!lookup @user`\n"
                                        f"➜ `!id @user` • `!followers @user` • `!following @user`\n"
                                        f"➜ `!dp @user` • `!stats @user` • `!warnings @user`\n"
                                        f"➜ `!members` • `!memberlist` • `!admins` • `!adminlist`\n"
                                        f"➜ `!gcinfo` • `!groupid` • `!whois` • `!botstatus`\n"
                                        f"➜ `!warn @user` • `!resetwarn @user` • `!kick @user`\n"
                                        f"➜ `!security` • `!logs` • `!antispam` • `!lockdown` • `!unlockdown`\n"
                                        f"➜ `!topactive` • `!toptrust` • `!leaderboard` • `!dbstats`\n"
                                        f"➜ `!devpanel` • `!health` • `!morning` • `!night` • `!reload`\n\n"
                                        f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                        f"👑 𝗗𝗘𝗩 ➜ {OWNER_USERNAME}"
                                    )
                                    safe_send_message(thread_id, help_card, reply_to_item_id=message_id)
                                    continue

                                # --- DETAILED BIO / BIODATA COMMAND ---
                                if text_lower.startswith("!bio"):
                                    parts = text.split()
                                    target_name = parts[1].lstrip('@') if len(parts) > 1 else sender_username
                                    bio_msg = ModerationEngine.get_detailed_user_bio(cl, target_name)
                                    safe_send_message(thread_id, bio_msg, reply_to_item_id=message_id)
                                    continue

                                if text_lower.startswith("!dp"):
                                    parts = text.split()
                                    target_name = parts[1].lstrip('@') if len(parts) > 1 else sender_username
                                    try:
                                        u_info = cl.user_info_by_username(target_name)
                                        if u_info:
                                            dp_url = getattr(getattr(u_info, 'hd_profile_pic_url_info', None), 'url', None) or getattr(u_info, 'profile_pic_url_hd', None) or u_info.profile_pic_url
                                            photo_path = cl.photo_download_by_url(dp_url, filename=f"{target_name}_dp.jpg")
                                            cl.direct_send_photo(photo_path, thread_ids=[thread_id])
                                            if os.path.exists(photo_path):
                                                os.remove(photo_path)
                                    except Exception:
                                        pass
                                    continue

                                if text_lower.startswith("!stats"):
                                    parts = text.split()
                                    target_name = parts[1].lstrip('@') if len(parts) > 1 else sender_username
                                    stats_msg = ModerationEngine.get_user_stats(target_name)
                                    safe_send_message(thread_id, stats_msg, reply_to_item_id=message_id)
                                    continue

                                if text_lower.startswith("!profile") or text_lower.startswith("!lookup") or text_lower.startswith("!profileinfo") or text_lower.startswith("!about"):
                                    parts = text.split()
                                    target_name = parts[1].lstrip('@') if len(parts) > 1 else sender_username
                                    card = profile_card(cl, target_name, thread=thread, thread_users=users, gc_admins=gc_admins)
                                    safe_send_message(thread_id, card, reply_to_item_id=message_id)
                                    continue

                                if text_lower.startswith("!id"):
                                    parts = text.split(); target_name = parts[1].lstrip('@') if len(parts) > 1 else sender_username
                                    u = get_instagram_profile(cl, target_name)
                                    card = f"🆔✨ 𝗨𝗦𝗘𝗥 𝗜𝗗 ➜ `{getattr(u, 'pk', 'N/A') if u else 'N/A'}`\n👤 𝗨𝗦𝗘𝗥 ➜ @{target_name}\n\n🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n👑 𝗗𝗘𝗩 ➜ {OWNER_USERNAME}"
                                    safe_send_message(thread_id, card, reply_to_item_id=message_id); continue

                                if text_lower.startswith("!followers") or text_lower.startswith("!following"):
                                    parts = text.split(); target_name = parts[1].lstrip('@') if len(parts) > 1 else sender_username
                                    u = get_instagram_profile(cl, target_name)
                                    field = "follower_count" if text_lower.startswith("!followers") else "following_count"
                                    label = "𝗙𝗢𝗟𝗟𝗢𝗪𝗘𝗥𝗦" if field == "follower_count" else "𝗙𝗢𝗟𝗟𝗢𝗪𝗜𝗡𝗚"
                                    value = getattr(u, field, "N/A") if u else "N/A"
                                    card = f"📊 𝗣𝗥𝗢𝗙𝗜𝗟𝗘 • {label}\n\n👤 ➜ @{target_name}\n🔢 ➜ `{value}`\n\n🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n👑 𝗗𝗘𝗩 ➜ {OWNER_USERNAME}"
                                    safe_send_message(thread_id, card, reply_to_item_id=message_id); continue

                                if text_lower in ["!gcinfo", "!groupid", "!whois"] or text_lower.startswith("!gcinfo") or text_lower.startswith("!whois"):
                                    title = str(getattr(thread, "thread_title", None) or "Unnamed GC")
                                    card = (f"🏠✨ 𝗚𝗖 𝗜𝗡𝗙𝗢 ✨🏠\n\n📛 𝗡𝗔𝗠𝗘 ➜ {title}\n🆔 𝗚𝗥𝗢𝗨𝗣 𝗜𝗗 ➜ `{thread_id}`\n👥 𝗠𝗘𝗠𝗕𝗘𝗥𝗦 ➜ `{len(users)}`\n👑 𝗔𝗗𝗠𝗜𝗡𝗦 ➜ `{len(gc_admins)}`\n🤖 𝗕𝗢𝗧 𝗔𝗗𝗠𝗜𝗡 ➜ {'Yes' if bot_pk in admin_ids_str else 'No'}\n🔐 𝗦𝗘𝗖𝗨𝗥𝗜𝗧𝗬 ➜ {'LOCKDOWN' if LOCKDOWN_MODE else 'ACTIVE'}\n\n🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n👑 𝗗𝗘𝗩 ➜ {OWNER_USERNAME}")
                                    safe_send_message(thread_id, card, reply_to_item_id=message_id); continue

                                if text_lower in ["!botstatus", "!health"]:
                                    card = f"⚡🛡️ 𝗕𝗢𝗧 • 𝗦𝗧𝗔𝗧𝗨𝗦 🛡️⚡\n\n🟢 𝗖𝗢𝗥𝗘 ➜ ONLINE\n🤖 𝗕𝗢𝗧 𝗔𝗗𝗠𝗜𝗡 ➜ {'YES' if bot_pk in admin_ids_str else 'NO'}\n🔐 𝗟𝗢𝗖𝗞𝗗𝗢𝗪𝗡 ➜ {'ON' if LOCKDOWN_MODE else 'OFF'}\n🗃️ 𝗗𝗔𝗧𝗔𝗕𝗔𝗦 ➜ READY\n\n🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n👑 𝗗𝗘𝗩 ➜ {OWNER_USERNAME}"
                                    safe_send_message(thread_id, card, reply_to_item_id=message_id); continue

                                if text_lower == "!warnings" or text_lower.startswith("!warnings "):
                                    parts=text.split(); target=parts[1].lstrip('@') if len(parts)>1 else sender_username
                                    db=SessionLocal(); prof=db.query(UserProfile).filter(UserProfile.username==target.lower()).first(); db.close()
                                    card=f"⚠️ 𝗪𝗔𝗥𝗡𝗜𝗡𝗚 𝗦𝗧𝗔𝗧𝗨𝗦\n\n👤 ➜ @{target}\n⚠️ 𝗪𝗔𝗥𝗡𝗜𝗡𝗚𝗦 ➜ {prof.warning_count if prof else 0}/3\n🚫 𝗩𝗜𝗢𝗟𝗔𝗧𝗜𝗢𝗡𝗦 ➜ {prof.violation_count if prof else 0}\n\n🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n👑 𝗗𝗘𝗩 ➜ {OWNER_USERNAME}"
                                    safe_send_message(thread_id, card, reply_to_item_id=message_id); continue

                                if text_lower.startswith("!resetwarn"):
                                    parts=text.split()
                                    if len(parts)>1:
                                        ModerationEngine.reset_warnings(parts[1])
                                        safe_send_message(thread_id, f"✅ 𝗪𝗔𝗥𝗡𝗜𝗡𝗚𝗦 𝗥𝗘𝗦𝗘𝗧 ➜ {fix_mention(parts[1])}", reply_to_item_id=message_id)
                                    continue

                                if text_lower in ["!security", "!logs"]:
                                    db=SessionLocal(); count=db.query(SecurityLog).count(); db.close()
                                    card=f"🛡️📜 𝗦𝗘𝗖𝗨𝗥𝗜𝗧𝗬 𝗣𝗔𝗡𝗘𝗟\n\n🔐 𝗟𝗢𝗖𝗞𝗗𝗢𝗪𝗡 ➜ {'ON' if LOCKDOWN_MODE else 'OFF'}\n📋 𝗟𝗢𝗚 𝗘𝗡𝗧𝗥𝗜𝗘𝗦 ➜ `{count}`\n👑 𝗚𝗖 𝗕𝗢𝗧 𝗔𝗗𝗠𝗜𝗡 ➜ {'YES' if bot_pk in admin_ids_str else 'NO'}\n\n🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n👑 𝗗𝗘𝗩 ➜ {OWNER_USERNAME}"
                                    safe_send_message(thread_id, card, reply_to_item_id=message_id); continue

                                if text_lower == "!lockdown":
                                    LOCKDOWN_MODE=True
                                    safe_send_message(thread_id, "🔒 𝗟𝗢𝗖𝗞𝗗𝗢𝗪𝗡 ➜ ENABLED\n🛡️ 𝗦𝗘𝗖𝗨𝗥𝗜𝗧𝗬 𝗠𝗢𝗗𝗘 𝗔𝗖𝗧𝗜𝗩𝗘", reply_to_item_id=message_id); continue
                                if text_lower == "!unlockdown":
                                    LOCKDOWN_MODE=False
                                    safe_send_message(thread_id, "🔓 𝗟𝗢𝗖𝗞𝗗𝗢𝗪𝗡 ➜ DISABLED\n🛡️ 𝗦𝗘𝗖𝗨𝗥𝗜𝗧𝗬 𝗠𝗢𝗗𝗘 𝗡ORMAL", reply_to_item_id=message_id); continue

                                if text_lower.startswith("!warn"):
                                    parts=text.split()
                                    if len(parts)>1:
                                        target=parts[1].lstrip('@')
                                        warns, trust=ModerationEngine.add_warning(target)
                                        safe_send_message(thread_id, f"⚠️ 𝗪𝗔𝗥𝗡𝗜𝗡𝗚 𝗔𝗣𝗣𝗟𝗜𝗘𝗗\n\n👤 ➜ {fix_mention(target)}\n⚠️ 𝗪𝗔𝗥𝗡𝗜𝗡𝗚𝗦 ➜ {warns}/3\n💎 𝗧𝗥𝗨𝗦𝗧 ➜ {trust}%", reply_to_item_id=message_id)
                                    continue

                                if text_lower.startswith("!kick"):
                                    parts=text.split()
                                    if len(parts)>1:
                                        target=parts[1].lstrip('@')
                                        u=get_instagram_profile(cl,target)
                                        target_pk=str(getattr(u,'pk','')) if u else ''
                                        if target_pk and target_pk != bot_pk:
                                            execute_kick(thread_id,target_pk,target,"Developer Manual Removal",admin_mentions_tag,reply_to_id=message_id)
                                        else:
                                            safe_send_message(thread_id,"❌ 𝗨𝗦𝗘𝗥 𝗡𝗢𝗧 𝗙𝗢𝗨𝗡𝗗 / 𝗡𝗢𝗧 𝗥𝗘𝗠𝗢𝗩𝗔𝗕𝗟𝗘",reply_to_item_id=message_id)
                                    continue

                                if text_lower in ["!antispam"]:
                                    safe_send_message(thread_id, "🛡️ 𝗔𝗡𝗧𝗜-𝗦𝗣𝗔𝗠 ➜ ACTIVE\n📢 𝗥𝗘𝗣𝗘𝗔𝗧𝗘𝗗 𝗠𝗘𝗦𝗦𝗔𝗚𝗘𝗦 ➜ MONITORED\n🚫 𝗔𝗕𝗨𝗦𝗘 ➜ ZERO-TOLERANCE", reply_to_item_id=message_id); continue

                                if text_lower in ["!topactive", "!leaderboard", "!rank", "!activity", "!toptrust"]:
                                    db=SessionLocal(); rows=db.query(UserProfile).order_by(UserProfile.total_messages.desc()).limit(10).all(); db.close()
                                    if text_lower == "!toptrust":
                                        rows=sorted(rows,key=lambda x:(x.trust_score or 0),reverse=True)
                                    lines=[f"{i}. @{r.username} — {r.total_messages} msgs • {r.trust_score}% trust" for i,r in enumerate(rows,1)]
                                    card="🏆✨ 𝗚𝗖 • 𝗟𝗘𝗔𝗗𝗘𝗥𝗕𝗢𝗔𝗥𝗗 ✨🏆\n\n"+("\n".join(lines) if lines else "No tracked users yet.")+f"\n\n🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n👑 𝗗𝗘𝗩 ➜ {OWNER_USERNAME}"
                                    safe_send_message(thread_id,card,reply_to_item_id=message_id); continue

                                if text_lower in ["!dbstats", "!profiledb"]:
                                    db=SessionLocal(); users_count=db.query(UserProfile).count(); logs_count=db.query(SecurityLog).count(); db.close()
                                    card=f"🗃️📊 𝗗𝗔𝗧𝗔𝗕𝗔𝗦 𝗦𝗧𝗔𝗧𝗦\n\n👤 𝗣𝗥𝗢𝗙𝗜𝗟𝗘𝗦 ➜ `{users_count}`\n📜 𝗦𝗘𝗖𝗨𝗥𝗜𝗧𝗬 𝗟𝗢𝗚𝗦 ➜ `{logs_count}`\n💾 𝗦𝗧𝗔𝗧𝗨𝗦 ➜ READY\n\n🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n👑 𝗗𝗘𝗩 ➜ {OWNER_USERNAME}"
                                    safe_send_message(thread_id,card,reply_to_item_id=message_id); continue

                                if text_lower == "!devpanel":
                                    safe_send_message(thread_id,"👑⚡ 𝗗𝗘𝗩 𝗣𝗔𝗡𝗘𝗟 ⚡👑\n\n🔐 Commands are developer-only.\n🛡️ GC-admin status does not grant command access.\n🤖 Bot operates only in GCs where it is an admin.",reply_to_item_id=message_id); continue

                                if text_lower in ["!morning", "!night"]:
                                    label="𝗚𝗢𝗢𝗗 𝗠𝗢𝗥𝗡𝗜𝗡𝗚 🌅" if text_lower=="!morning" else "𝗚𝗢𝗢𝗗 𝗡𝗜𝗚𝗛𝗧 🌙"
                                    safe_send_message(thread_id,f"✨ {label} ✨\n\n🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n👑 𝗗𝗘𝗩 ➜ {OWNER_USERNAME}",reply_to_item_id=message_id); continue

                                if text_lower in ["!reload"]:
                                    safe_send_message(thread_id,"♻️ 𝗥𝗘𝗟𝗢𝗔𝗗 𝗥𝗘𝗤𝗨𝗘𝗦𝗧𝗘𝗗\n🔄 Core loop will refresh on the next safe cycle.",reply_to_item_id=message_id); continue

                                if text_lower in ["!members", "!memberlist"]:
                                    members_card = f"👥📊 𝗚𝗥𝗢𝗨𝗣 • 𝗠𝗘𝗠𝗕𝗘𝗥𝗦 ➜ `{len(users)}` members\n\n🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n👑 𝗗𝗘𝗩 ➜ {OWNER_USERNAME}"
                                    safe_send_message(thread_id, members_card, reply_to_item_id=message_id)
                                    continue

                                if text_lower in ["!admins", "!adminlist"]:
                                    admin_card = f"👑🛡️ 𝗚𝗖 ADMINS ➜ `{len(gc_admins)}` active\n\n🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n👑 𝗗𝗘𝗩 ➜ {OWNER_USERNAME}"
                                    safe_send_message(thread_id, admin_card, reply_to_item_id=message_id)
                                    continue

                except (LoginRequired, ChallengeRequired):
                    print("[-] Login required or challenge triggered. Re-authenticating...")
                    break
                except (PleaseWaitFewMinutes, ClientThrottledError):
                    time.sleep(15)
                except Exception:
                    time.sleep(POLL_INTERVAL)

                time.sleep(POLL_INTERVAL)

        except Exception as e:
            print(f"[-] Bot error: {e}. Restarting loop in 10 seconds...")
            time.sleep(10)

if __name__ == "__main__":
    # Start Flask Web Server in background thread so Render Web Service never sleeps
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    # Start Instagram Bot Core Engine
    start_bot()
