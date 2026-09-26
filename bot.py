import os
import re
import time
from datetime import datetime, timezone
from dotenv import load_dotenv
from instagrapi import Client
from instagrapi.exceptions import PleaseWaitFewMinutes, ClientThrottledError, LoginRequired, ChallengeRequired
from sqlalchemy import create_engine, Column, String, Integer, Float, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

# --- अल्ट्रा-फास्ट बॉट क्रेडेंशियल्स ---
BOT_USERNAME = "bot0.0928"
BOT_PASSWORD = "SIDHU295"

# यहाँ अपनी न्यू सेशन आईडी डाल दी है भाई (इसे अपडेट रखना)
SESSION_ID = "24360649417%3AdvTl2cIVjUGYKS%3A7%3AAYlLz9DoDZNK9nOVVQpgGsoTS6bkcCp5wISgktflKg" 

OWNER_USERNAME = "fx_smw ✘ aat_nnk25"
AUTHORIZED_DEVS = ["fx_smw", "aat_nnk", "aat_nnk25", "fx_sw"]
DATABASE_URL = "sqlite:///bot_database.db"
POLL_INTERVAL = 1  # 🚀 अल्ट्रा-फास्ट स्पीड के लिए पोलिंग टाइम सिर्फ 1 सेकंड किया गया है!

SHADOWBANNED_USERS = set()
TARGETED_USERS = set()
LOCKDOWN_MODE = False

def fix_mention(username: str) -> str:
    if not username:
        return ""
    clean_name = str(username).strip().lstrip('@')
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

BAD_WORD_PATTERNS = [
    r'\bm[\.\_\-\s]*c\b', r'\bb[\.\_\-\s]*c\b', r'\bm[\.\_\-\s]*k[\.\_\-\s]*c\b',
    r'\bt[\.\_\-\s]*m[\.\_\-\s]*k[\.\_\-\s]*c\b', r'madar\s*chod', r'bhen\s*chod', 
    r'behen\s*chod', r'bhosd\w*', r'chut\w*', r'gand\w*', r'gaand\w*', r'lund\w*',
    r'lauda\w*', r'lawda\w*', r'randi\w*', r'bhadwa\w*', r'bhadwe\w*', r'bsdk\w*', 
    r'harami\w*', r'f[\.\_\-\s]*u[\.\_\-\s]*c[\.\_\-\s]*k\w*'
]

RESTRICTED_WORDS = set([
    'mc', 'bc', 'mkc', 'tmkc', 'bsdk', 'bsdke', 'chutiya', 'chutiye', 'chutiyap', 
    'gandu', 'gaandu', 'lauda', 'luda', 'lawda', 'lund', 'chut', 'chuth', 
    'gand', 'gaand', 'randi', 'randwa', 'bhadwa', 'bhadwe', 'harami', 'haramkhor', 
    'kamine', 'kamina', 'saala', 'saale', 'madarchod', 'maderchod', 'madar-chod', 
    'bhenchod', 'behenchod', 'bhen-chod', 'behen-chod', 'bhosdike', 'bhosdi', 'bhosda',
    'fuck', 'fucking', 'fucker', 'motherfucker', 'bitch', 'bastard', 'asshole'
])

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
                    f"📊 **𝗨𝗦𝗘𝗥 𝗦𝗧𝗔𝗧𝗦 𝗙𝗢𝗥 {fix_mention(profile.username)}**\n\n"
                    f"🆔 **𝗨𝗦𝗘𝗥 𝗜𝗗** ➜ `{profile.user_id}`\n"
                    f"💬 **𝗧𝗢𝗧𝗔𝗟 𝗠𝗦𝗚𝗦** ➜ {profile.total_messages}\n"
                    f"⚠️ **𝗪𝗔𝗥𝗡𝗜𝗡𝗚𝗦** ➜ {profile.warning_count}/3\n"
                    f"🚫 **𝗩𝗜𝗢𝗟𝗔𝗧𝗜𝗢𝗡𝗦** ➜ {profile.violation_count}\n"
                    f"💎 **𝗧𝗥𝗨𝗦𝗧 𝗦𝗖𝗢𝗥𝗘** ➜ {profile.trust_score}%\n"
                    f"📈 **𝗦𝗖𝗢𝗥𝗘 𝗕𝗔𝗥** ➜ [{bar}]\n\n"
                    f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                    f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
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

def is_abusive_text(text: str) -> bool:
    text_lower = text.lower()
    if any(word in text_lower for word in RESTRICTED_WORDS):
        return True
    for pattern in BAD_WORD_PATTERNS:
        if re.search(pattern, text_lower):
            return True
    return False

def start_bot():
    global LOCKDOWN_MODE, SHADOWBANNED_USERS, TARGETED_USERS
    init_db()

    while True:
        try:
            print("[*] Initializing Ultra-Fast Instagram Client...")
            cl = Client()
            cl.set_user_agent("Mozilla/5.0 (Linux; Android 11; SM-G998B Build/RP1A.200720.012; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/115.0.5790.166 Mobile Safari/537.36 Instagram 290.0.0.13.76 Android")

            logged_in = False

            if SESSION_ID and SESSION_ID != "YOUR_SESSION_ID_HERE":
                try:
                    print("[+] Connecting via Session ID...")
                    cl.login_by_sessionid(SESSION_ID)
                    logged_in = True
                    print("[+] Session ID login successful!")
                except Exception as e:
                    print(f"[!] Session ID error: {e}")

            if not logged_in:
                print("[*] Trying fallback ID-Password login...")
                try:
                    cl.login(BOT_USERNAME, BOT_PASSWORD)
                    print("[+] ID-Password login successful!")
                except Exception as login_err:
                    print(f"[!] Login Error: {login_err}")
                    time.sleep(10)
                    continue

            print(f"[+] ULTRA BOT @{BOT_USERNAME} IS LIVE & RUNNING AT MAX SPEED! 🚀🔥")

            seen_message_ids = set()
            last_morning_wish_date = ""
            last_night_wish_date = ""
            recent_sent_texts = {}

            def safe_send_message(thread_id, text_content):
                current_time = time.time()
                if thread_id in recent_sent_texts:
                    last_text, last_time = recent_sent_texts[thread_id]
                    if last_text == text_content and (current_time - last_time < 1):
                        return
                recent_sent_texts[thread_id] = (text_content, current_time)
                cl.direct_send(text_content, thread_ids=[thread_id])
                time.sleep(0.5)  # ⚡ सुपर फास्ट रिप्लाई डिले

            def execute_kick(thread_id, target_pk, target_username, reason, silent=False):
                try:
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
                            f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
                        )
                        safe_send_message(thread_id, kick_card)
                except Exception:
                    pass

            while True:
                try:
                    threads = cl.direct_threads(amount=3)
                    now = datetime.now()
                    current_hour = now.hour
                    current_date_str = now.strftime("%Y-%m-%d")

                    for thread in threads:
                        if not getattr(thread, "is_group", False):
                            continue

                        thread_id = thread.id
                        gc_admins = []
                        try:
                            if hasattr(thread, 'admin_user_ids') and thread.admin_user_ids:
                                gc_admins = [str(uid) for uid in thread.admin_user_ids]
                            elif hasattr(thread, 'admin_users') and thread.admin_users:
                                gc_admins = [str(getattr(admin, 'pk', admin)) for admin in thread.admin_users]
                        except Exception:
                            gc_admins = []

                        bot_pk = str(cl.user_id)
                        users = list(getattr(thread, "users", []) or [])
                        admin_mentions_tag = get_admin_mentions_str(users, gc_admins)

                        if current_hour == 6 and last_morning_wish_date != current_date_str:
                            last_morning_wish_date = current_date_str
                            morning_card = (
                                f"🌅✨ **𝗚𝗢𝗢𝗗 𝗠𝗢𝗥𝗡𝗜𝗡𝗚 𝗘𝗩𝗘𝗥𝗬𝗢𝗡𝗘!** ✨🌅\n\n"
                                f"🌻 𝗛𝗔𝗩𝗘 𝗔𝗡 𝗔𝗠𝗔𝗭𝗜𝗡𝗚 & 𝗣𝗥𝗢𝗗𝗨𝗖𝗧𝗜𝗩𝗘 𝗗𝗔𝗬!\n"
                                f"☕ 𝗦𝗣𝗥𝗘𝗔𝗗 𝗣𝗢𝗦𝗜𝗧𝗜𝗩𝗜𝗧𝗬 𝗜𝗡 𝗧𝗛𝗘 𝗚𝗖 🔥\n\n"
                                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
                            )
                            safe_send_message(thread_id, morning_card)

                        if current_hour == 23 and last_night_wish_date != current_date_str:
                            last_night_wish_date = current_date_str
                            night_card = (
                                f"🌙✨ **𝗚𝗢𝗢𝗗 𝗡𝗜𝗚𝗛𝗧 𝗚𝗖 𝗙𝗔𝗠𝗜𝗟𝗬!** ✨🌙\n\n"
                                f"😴 𝗧𝗜𝗠𝗘 𝗧𝗢 𝗥𝗘𝗦𝗧 & 𝗥𝗘𝗖𝗛𝗔𝗥𝗚𝗘!\n"
                                f"💫 𝗦𝗪𝗘𝗘𝗧 𝗗𝗥𝗘𝗔𝗠𝗦 𝗘𝗩𝗘𝗥𝗬𝗢𝗡𝗘 🌙\n\n"
                                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
                            )
                            safe_send_message(thread_id, night_card)

                        messages = list(getattr(thread, "messages", []) or [])
                        if messages:
                            last_msg = messages[0]
                            message_id = str(getattr(last_msg, "id", ""))

                            if message_id and message_id not in seen_message_ids:
                                seen_message_ids.add(message_id)

                                text = str(getattr(last_msg, "text", "") or "").strip()
                                text_lower = text.lower()
                                sender_id = str(getattr(last_msg, "user_id", ""))

                                sender_username = "User"
                                for u in users:
                                    if str(getattr(u, "pk", "")) == sender_id:
                                        sender_username = getattr(u, "username", "User")
                                        break

                                if sender_id == bot_pk:
                                    continue

                                admin_ids_str = {str(x) for x in gc_admins}
                                is_sender_admin = sender_id in admin_ids_str
                                is_dev = sender_username.lower() in [d.lower() for d in AUTHORIZED_DEVS]

                                ModerationEngine.record_activity(sender_id, sender_username)

                                if LOCKDOWN_MODE and not is_dev and not is_sender_admin:
                                    execute_kick(thread_id, sender_id, sender_username, "GC LOCKDOWN ACTIVE")
                                    continue

                                if sender_username.lower() in TARGETED_USERS:
                                    execute_kick(thread_id, sender_id, sender_username, "TARGET ELIMINATED")
                                    continue

                                if sender_username.lower() in SHADOWBANNED_USERS:
                                    execute_kick(thread_id, sender_id, sender_username, "SHADOWBANNED", silent=True)
                                    continue

                                if not is_dev and not is_sender_admin:
                                    if is_abusive_text(text) or "instagram.com/reel" in text_lower or "http" in text_lower:
                                        warns, trust = ModerationEngine.add_warning(sender_username)
                                        reason = "Abusive Language" if is_abusive_text(text) else "Unauthorized Links/Reels"

                                        if warns >= 3:
                                            execute_kick(thread_id, sender_id, sender_username, f"3 Warnings Reached ({reason})")
                                        else:
                                            warn_card = (
                                                f"⚠️🚨 **𝗩𝗜𝗢𝗟𝗔𝗧𝗜𝗢𝗡 𝗪𝗔𝗥𝗡𝗜𝗡𝗚!** 🚨⚠️\n\n"
                                                f"👤 𝗢𝗙𝗙𝗘𝗡𝗗𝗘𝗥 ➜ {fix_mention(sender_username)}\n"
                                                f"🚫 𝗥𝗘𝗔𝗦𝗢𝗡   ➜ {reason}\n"
                                                f"⚠️ 𝗪𝗔𝗥𝗡𝗜𝗡𝗚𝗦 ➜ {warns}/3\n"
                                                f"📉 𝗧𝗥𝗨𝗦𝗧 𝗦𝗖𝗢𝗥𝗘 ➜ {trust}%\n\n"
                                                f"📢 **𝗔𝗗𝗠𝗜𝗡 𝗔𝗟𝗘𝗥𝗧** ➜ {admin_mentions_tag}\n\n"
                                                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}"
                                            )
                                            safe_send_message(thread_id, warn_card)
                                        continue

                                if is_dev:
                                    if text_lower == "!lockdown":
                                        LOCKDOWN_MODE = True
                                        safe_send_message(thread_id, "🚨 **𝗚𝗖 𝗟𝗢𝗖𝗞𝗗𝗢𝗪𝗡 𝗔𝗖𝗧𝗜𝗩𝗔𝗧𝗘𝗗!** Non-dev messages will trigger instant kick.")
                                        continue

                                    elif text_lower == "!unlock":
                                        LOCKDOWN_MODE = False
                                        safe_send_message(thread_id, "🔓 **𝗚𝗖 𝗟𝗢𝗖𝗞𝗗𝗢𝗪𝗡 𝗗𝗘𝗔𝗖𝗧𝗜𝗩𝗔𝗧𝗘𝗗!** Group is now normal.")
                                        continue

                                    elif text_lower == "!godmode":
                                        status_card = (
                                            f"⚡🛡️ **𝗚𝗢𝗗𝗠𝗢𝗗𝗘 𝗦𝗧𝗔𝗧𝗨𝗦** 🛡️⚡\n\n"
                                            f"🔒 **𝗟𝗼𝗰𝗸𝗱𝗼𝘄𝗻** ➜ {'ON 🚨' if LOCKDOWN_MODE else 'OFF 🟢'}\n"
                                            f"🎯 **𝗧𝗮𝗿𝗴𝗲𝘁𝘀** ➜ {len(TARGETED_USERS)} Users\n"
                                            f"👻 **𝗦𝗵𝗮𝗱𝗼𝘄𝗯𝗮𝗻𝘀** ➜ {len(SHADOWBANNED_USERS)} Users\n"
                                            f"⚡ **𝗕𝗼𝘁 𝗦𝘁𝗮𝘁𝘂𝘀** ➜ 100% ONLINE & PROTECTED\n\n"
                                            f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}"
                                        )
                                        safe_send_message(thread_id, status_card)
                                        continue

                                    elif text_lower.startswith("!target"):
                                        parts = text.split()
                                        if len(parts) > 1:
                                            target = parts[1].lstrip('@').lower()
                                            TARGETED_USERS.add(target)
                                            safe_send_message(thread_id, f"🎯 {fix_mention(target)} is now LOCKED in Target list!")
                                        continue

                                    elif text_lower.startswith("!shadowban"):
                                        parts = text.split()
                                        if len(parts) > 1:
                                            target = parts[1].lstrip('@').lower()
                                            SHADOWBANNED_USERS.add(target)
                                            safe_send_message(thread_id, f"👻 {fix_mention(target)} added to Shadowban!")
                                        continue

                                    elif text_lower.startswith("!nuke"):
                                        parts = text.split()
                                        if len(parts) > 1:
                                            target = parts[1].lstrip('@')
                                            u_id = cl.user_id_from_username(target)
                                            execute_kick(thread_id, u_id, target, "PERMANENT NUKE BAN")
                                        continue

                                    elif text_lower.startswith("!resetwarn") or text_lower.startswith("!unwarn"):
                                        parts = text.split()
                                        if len(parts) > 1:
                                            target = parts[1].lstrip('@')
                                            ModerationEngine.reset_warnings(target)
                                            safe_send_message(thread_id, f"✅ Warnings reset to 0 for {fix_mention(target)}!")
                                        continue

                                    elif text_lower == "!tagall":
                                        all_tags = [fix_mention(getattr(u, "username", "")) for u in users if getattr(u, "username", None)]
                                        tag_str = " ".join(all_tags)
                                        safe_send_message(thread_id, f"📢 **TAG ALL ATTENTION!**\n\n{tag_str}")
                                        continue

                                    elif text_lower == "!admins":
                                        if gc_admins:
                                            admin_names = []
                                            for u in users:
                                                if str(getattr(u, "pk", "")) in admin_ids_str:
                                                    un = getattr(u, "username", None)
                                                    if un:
                                                        admin_names.append(f"👑 ➜ {fix_mention(un)}")
                                            
                                            admin_list_str = "\n".join(admin_names) if admin_names else "👑 ➜ Admins active"
                                            admin_card = (
                                                f"👑🛡️ **𝗚𝗖 𝗔𝗗𝗠𝗜𝗡𝗜𝗦𝗧𝗥𝗔𝗧𝗢𝗥𝗦 𝗟𝗜𝗦𝗧** 🛡️👑\n\n"
                                                f"📊 **𝗧𝗢𝗧𝗔𝗟 𝗔𝗗𝗠𝗜𝗡𝗦** ➜ {len(gc_admins)}\n\n"
                                                f"✨ **𝗔𝗖𝗧𝗜𝗩𝗘 𝗔𝗗𝗠𝗜𝗡𝗦**:\n{admin_list_str}\n\n"
                                                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                                f"👨‍💻 **𝗥𝗘𝗤𝗨𝗘𝗦𝗧𝗘𝗗 𝗕𝗬** ➜ {fix_mention(sender_username)}"
                                            )
                                            safe_send_message(thread_id, admin_card)
                                        continue

                                if text_lower.startswith("!dp"):
                                    parts = text.split()
                                    target_name = parts[1].lstrip('@') if len(parts) > 1 else sender_username
                                    try:
                                        safe_send_message(thread_id, f"📸 𝗙𝗘𝗧𝗖𝗛𝗜𝗡𝗚 𝗛𝗗 𝗣𝗥𝗢𝗙𝗜𝗟𝗘 𝗣𝗜𝗖 𝗙𝗢𝗥 {fix_mention(target_name)}...")
                                        u_info = None
                                        try:
                                            u_info = cl.user_info_by_username(target_name)
                                        except Exception:
                                            pass

                                        if u_info:
                                            dp_url = getattr(getattr(u_info, 'hd_profile_pic_url_info', None), 'url', None) or getattr(u_info, 'profile_pic_url_hd', None) or u_info.profile_pic_url
                                            photo_path = cl.photo_download_by_url(dp_url, filename=f"{target_name}_dp.jpg")
                                            cl.direct_send_photo(photo_path, thread_ids=[thread_id])
                                            
                                            dp_card = (
                                                f"📸✨ 𝗛𝗗 𝗗𝗣 𝗙𝗘𝗧𝗖𝗛𝗘𝗗 𝗦𝗨𝗖𝗖𝗘𝗦𝗦𝗙𝗨𝗟𝗟𝗬! ✨📸\n\n"
                                                f"👤 𝗨𝗦𝗘𝗥 ➜ {fix_mention(target_name)}\n"
                                                f"✅ 𝗦𝗧𝗔𝗧𝗨𝗦 ➜ 𝗛𝗜𝗚𝗛 𝗤𝗨𝗔𝗟𝗜𝗧𝗬 𝗣𝗜𝗖 𝗦𝗘𝗡𝗧 𝗔𝗕𝗢𝗩𝗘!\n\n"
                                                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                                f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
                                            )
                                            safe_send_message(thread_id, dp_card)
                                            if os.path.exists(photo_path):
                                                os.remove(photo_path)
                                        else:
                                            safe_send_message(thread_id, f"❌ 𝗙𝗔𝗜𝗟𝗘𝗗 𝗧𝗢 𝗙𝗘𝗧𝗖𝗛 𝗗𝗣 𝗙𝗢𝗥 {fix_mention(target_name)}!")
                                    except Exception:
                                        safe_send_message(thread_id, f"❌ 𝗙𝗔𝗜𝗟𝗘𝗗 𝗧𝗢 𝗙𝗘𝗧𝗖𝗛 𝗗𝗣!")
                                    continue

                                elif text_lower.startswith("!song"):
                                    song_name = text[5:].strip()
                                    if song_name:
                                        search_url = f"https://music.youtube.com/search?q={song_name.replace(' ', '+')}"
                                        song_card = (
                                            f"🎵✨ 𝗦𝗢𝗡𝗚 𝗙𝗜𝗡𝗗𝗘𝗥 ✨🎵\n\n"
                                            f"🎧 𝗦𝗼𝗻𝗴 𝗡𝗮𝗺𝗲 ➜ {song_name}\n"
                                            f"🔗 𝗟𝗶𝘀𝘁𝗲𝗻 𝗛𝗲𝗿𝗲 ➜ {search_url}\n\n"
                                            f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}"
                                        )
                                        safe_send_message(thread_id, song_card)
                                    else:
                                        safe_send_message(thread_id, "⚠️ Usage: `!song <song name>`")
                                    continue

                                elif text_lower.startswith("!stats"):
                                    parts = text.split()
                                    target_name = parts[1].lstrip('@') if len(parts) > 1 else sender_username
                                    stats_msg = ModerationEngine.get_user_stats(target_name)
                                    safe_send_message(thread_id, stats_msg)
                                    continue

                                elif text_lower == "!rules":
                                    rules_card = (
                                        f"📜✨ **𝗚𝗖 𝗢𝗙𝗙𝗜𝗖𝗜𝗔𝗟 𝗥𝗨𝗟𝗘𝗦** ✨📜\n\n"
                                        f"1️⃣ No Abusive Words / Toxicity\n"
                                        f"2️⃣ No Spam Links or Reels Promotion\n"
                                        f"3️⃣ Respect All Members & Admins\n"
                                        f"4️⃣ 3 Warnings = Automatic Kick!\n\n"
                                        f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}"
                                    )
                                    safe_send_message(thread_id, rules_card)
                                    continue

                                elif text_lower == "!botinfo":
                                    info_card = (
                                        f"🤖✨ **𝗕𝗢𝗧 𝗜𝗡𝗙𝗢𝗥𝗠𝗔𝗧𝗜𝗢𝗡** ✨🤖\n\n"
                                        f"⚡ **Status** ➜ ONLINE & ACTIVE\n"
                                        f"🛡️ **Security** ➜ Anti-Spam & Auto-Kick ON\n"
                                        f"👨‍💻 **Developers** ➜ @{OWNER_USERNAME}\n\n"
                                        f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}"
                                    )
                                    safe_send_message(thread_id, info_card)
                                    continue

                except (LoginRequired, ChallengeRequired):
                    print("[!] Session expired! Re-authenticating immediately...")
                    break
                except (PleaseWaitFewMinutes, ClientThrottledError):
                    print("[!] Rate limit hit, quick recovery sleep (10s)...")
                    time.sleep(10)
                except Exception as e:
                    print(f"[!] Loop warning: {e}")
                    time.sleep(POLL_INTERVAL)

                time.sleep(POLL_INTERVAL)

        except Exception as e:
            print(f"[!] Critical error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    start_bot()
