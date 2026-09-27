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
BOT_USERNAME = "bot0.0928"
BOT_PASSWORD = "SIDHU295"
SESSION_ID = os.getenv("SESSION_ID", "YAHAN_APNI_SESSION_ID_DAL_DENA")

OWNER_USERNAME = "fx_smw ✘ aat_nnk25"
AUTHORIZED_DEVS = ["fx_smw", "aat_nnk", "aat_nnk25", "fx_sw"]
DATABASE_URL = "sqlite:///god_mode_bot.db"
POLL_INTERVAL = 0.2  # Ultra-fast response time

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
        try:
            clean_name = username.lstrip('@')
            u_info = cl.user_info_by_username(clean_name)
            if not u_info:
                return f"❌ User @{clean_name} not found on Instagram!"
            
            # Extract profile details
            full_name = getattr(u_info, 'full_name', 'N/A')
            biography = getattr(u_info, 'biography', 'N/A')
            followers = getattr(u_info, 'follower_count', 0)
            following = getattr(u_info, 'following_count', 0)
            is_private = "🔒 Private" if getattr(u_info, 'is_private', False) else "🔓 Public"
            is_verified = "✅ Yes" if getattr(u_info, 'is_verified', False) else "❌ No"
            media_count = getattr(u_info, 'media_count', 0)
            external_url = getattr(u_info, 'external_url', 'None')
            user_pk = getattr(u_info, 'pk', 'N/A')

            return (
                f"👤📋 𝗨𝗦𝗘𝗥 • 𝗗𝗘𝗧𝗔𝗜𝗟𝗘𝗗 𝗕𝗜𝗢𝗗𝗔𝗧𝗔 📋👤\n\n"
                f"📌 𝗡𝗔𝗠𝗘 ➜ {full_name}\n"
                f"🏷️ 𝗨𝗦𝗘𝗥𝗡𝗔𝗠𝗘 ➜ @{clean_name}\n"
                f"🆔 𝗨𝗦𝗘𝗥 𝗜𝗗 ➜ `{user_pk}`\n"
                f"👥 𝗙𝗢𝗟𝗟𝗢𝗪𝗘𝗥𝗦 ➜ `{followers}`\n"
                f"👣 𝗙𝗢𝗟𝗟𝗢𝗪𝗜𝗡𝗚 ➜ `{following}`\n"
                f"📸 𝗣𝗢𝗦𝗧𝗦 ➜ `{media_count}`\n"
                f"🔒 𝗔𝗖𝗖𝗢𝗨𝗡𝗧 ➜ {is_private}\n"
                f"✔️ 𝗩𝗘𝗥𝗜𝗙𝗜𝗘𝗗 ➜ {is_verified}\n"
                f"🔗 𝗕𝗜𝗢 𝗟𝗜𝗡𝗞 ➜ {external_url}\n\n"
                f"📝 𝗕𝗜𝗢𝗚𝗥𝗔𝗣𝗛𝗬:\n`{biography}`\n\n"
                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                f"👑 𝗗𝗘𝗩 ➜ {OWNER_USERNAME}"
            )
        except Exception as e:
            return f"❌ Error fetching bio for @{username}: {str(e)}"

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

            if not logged_in:
                try:
                    cl.login(BOT_USERNAME, BOT_PASSWORD)
                    logged_in = True
                    print("[+] Successfully logged in using Username & Password!")
                except Exception as e:
                    print(f"[-] Credentials login failed: {e}")
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
                    threads = cl.direct_threads(amount=5)

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
                                        "reel", "reels", "post", "share", "profile", "igtv", "story"
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
                                        f"➜ `!rules` : Show GC Rules\n"
                                        f"➜ `!ping` : Check Bot Speed\n"
                                        f"➜ `!bio <username>` : Get Detailed Biodata & Stats\n"
                                        f"➜ `!dp <username>` : Download HD DP\n"
                                        f"➜ `!stats <username>` : User Trust Score\n"
                                        f"➜ `!members` : Member Count\n"
                                        f"➜ `!admins` : Admin Count\n\n"
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
