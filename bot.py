import os
import re
import time
import psutil
from datetime import datetime, timezone
from dotenv import load_dotenv
from instagrapi import Client
from instagrapi.exceptions import PleaseWaitFewMinutes, ClientThrottledError, LoginRequired, ChallengeRequired
from sqlalchemy import create_engine, Column, String, Integer, Float, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

# ==================== CONFIGURATION ====================
SESSION_ID = os.getenv("SESSION_ID", "7207590267%3AOzEdEpuYJTJj6t%3A20%3AAYkMaEgKhgBcicgwWniTeXrUH-O3FDT_4s5sepDRtQ")
BOT_USERNAME = os.getenv("BOT_USERNAME", "smw_vyron_bot")
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "fx_smw ✘ aat_nnk25")

AUTHORIZED_DEVS = ["fx_smw", "aat_nnk", "aat_nnk25"]

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///bot_database.db")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", 3))
CALL_REMINDER_INTERVAL = 3600  # 1 घंटा (3600 सेकंड)
MAX_WARNINGS_BEFORE_KICK = 3    # 3 वार्निंग पर ऑटो किक

SHADOWBANNED_USERS = set()
TARGETED_USERS = set()
LOCKDOWN_MODE = False

# ==================== STRICT REGEX & SLANG FILTER ====================
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
    'tatti', 'jhant', 'jhantu', 'lode', 'loda', 'lawde', 'teri maa ki', 'madarchhod',
    'bhenchhod', 'chutmarike', 'gaandmasti', 'fuck', 'fucking', 'fucker', 'motherfucker', 
    'bitch', 'bastard', 'asshole', 'cunt', 'dick', 'pussy', 'slut', 'whore', 'bullshit', 
    'retard', 'nigga', 'nigger', 'faggot', 'cock', 'suck', 'porn', 'nude', 'nudes', 'sex', '18+', 'adult'
])

# ==================== DATABASE SYSTEM ====================
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

# ==================== MODERATION & PROFILE ENGINE ====================
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
                profile.trust_score = max(0.0, profile.trust_score - 20.0)
                db.commit()
                return profile.warning_count, profile.trust_score
            return 1, 80.0
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
                    f"📊✨ **𝗨𝗦𝗘𝗥 𝗦𝗧𝗔𝗧𝗦 • @{profile.username}** ✨📊\n\n"
                    f"🆔 **𝗨𝗦𝗘𝗥 𝗜𝗗** ➜ `{profile.user_id}`\n"
                    f"💬 **𝗧𝗢𝗧𝗔𝗟 𝗠𝗦𝗚𝗦** ➜ {profile.total_messages}\n"
                    f"⚠️ **𝗪𝗔𝗥𝗡𝗜𝗡𝗚𝗦** ➜ {profile.warning_count}/{MAX_WARNINGS_BEFORE_KICK}\n"
                    f"🚫 **𝗩𝗜𝗢𝗟𝗔𝗧𝗜𝗢𝗡𝗦** ➜ {profile.violation_count}\n"
                    f"💎 **𝗧𝗥𝗨𝗦𝗧 𝗦𝗖𝗢𝗥𝗘** ➜ {profile.trust_score}%\n"
                    f"📈 **𝗦𝗖𝗢𝗥𝗘 𝗕𝗔𝗥** ➜ [{bar}]\n\n"
                    f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
                    f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
                )
            return f"❌ User @{clean_user} is not registered in Database!"
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

class SystemMonitor:
    def __init__(self):
        self.start_time = time.time()

    def get_health_report(self) -> str:
        uptime_sec = int(time.time() - self.start_time)
        hours, remainder = divmod(uptime_sec, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        return (
            f"⚡💻 **𝗦𝗬𝗦𝗧𝗘𝗠 𝗛𝗘𝗔𝗟𝗧𝗛 𝗥𝗘𝗣𝗢𝗥𝗧** 💻⚡\n\n"
            f"🟢 **𝗦𝗧𝗔𝗧𝗨𝗦** ➜ ONLINE & ACTIVE\n"
            f"⏱️ **𝗨𝗣𝗧𝗜𝗠𝗘** ➜ {hours}h {minutes}m {seconds}s\n"
            f"💻 **𝗖𝗣𝗨 𝗟𝗢𝗔𝗗** ➜ {psutil.cpu_percent()}%\n"
            f"🧠 **𝗥𝗔𝗠 𝗨𝗦𝗔𝗚𝗘** ➜ {psutil.virtual_memory().percent}%\n"
            f"👻 **𝗦𝗛𝗔𝗗𝗢𝗪𝗕𝗔𝗡𝗦** ➜ {len(SHADOWBANNED_USERS)}\n"
            f"🎯 **𝗧𝗔𝗥𝗚𝗘𝗧𝗦** ➜ {len(TARGETED_USERS)}\n\n"
            f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
            f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
        )

# ==================== MAIN GOD ENGINE ====================
def start_bot():
    global LOCKDOWN_MODE, SHADOWBANNED_USERS, TARGETED_USERS
    init_db()
    monitor = SystemMonitor()

    while True:
        try:
            print("[*] Connecting to Instagram Engine...")
            cl = Client()
            cl.login_by_sessionid(SESSION_ID)
            print(f"[+] SUCCESS: Bot @{BOT_USERNAME} initialized with ALL MERGED FEATURES! 🚀")

            seen_message_ids = set()
            group_members_state = {}
            ever_seen_members = set()
            welcomed_recently = {}
            recent_sent_texts = {}
            last_call_broadcast = {}
            user_spam_tracker = {}

            last_morning_wish_date = ""
            last_night_wish_date = ""
            is_first_run = True

            def safe_send_message(thread_id, text_content):
                current_time = time.time()
                if thread_id in recent_sent_texts:
                    last_text, last_time = recent_sent_texts[thread_id]
                    if last_text == text_content and (current_time - last_time < 8):
                        return
                recent_sent_texts[thread_id] = (text_content, current_time)
                cl.direct_send(text_content, thread_ids=[thread_id])
                time.sleep(1)

            def execute_kick(thread_id, target_pk, target_username, reason, silent=False):
                try:
                    cl.user_remove_from_thread(thread_id, target_pk)
                    ModerationEngine.log_event(thread_id, target_username, "AUTO-KICK", reason)

                    if not silent:
                        kick_card = (
                            f"🚨🚪 **𝗔𝗨𝗧𝗢-𝗞𝗜𝗖𝗞 𝗔𝗟𝗘𝗥𝗧!** 🚪🚨\n\n"
                            f"👤 𝗨𝗦𝗘𝗥 ➜ @{target_username}\n"
                            f"🚫 𝗥𝗘𝗔𝗦𝗢𝗡 ➜ {reason}\n"
                            f"🛑 𝗔𝗖𝗧𝗜𝗢𝗡 ➜ REMOVED FROM GC!\n\n"
                            f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
                            f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
                        )
                        safe_send_message(thread_id, kick_card)
                except Exception:
                    pass

            while True:
                try:
                    threads = cl.direct_threads(amount=3)
                    current_time_loop = time.time()

                    now = datetime.now()
                    current_hour = now.hour
                    current_date_str = now.strftime("%Y-%m-%d")

                    for thread in threads:
                        if not getattr(thread, "is_group", False):
                            continue

                        thread_id = thread.id
                        bot_tag = f"@{BOT_USERNAME.lower()}"

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
                        current_members = {str(getattr(u, "pk", "")) for u in users if getattr(u, "pk", None)}

                        # 1. MORNING & NIGHT WISH SYSTEM
                        if current_hour == 6 and last_morning_wish_date != current_date_str:
                            last_morning_wish_date = current_date_str
                            morning_card = (
                                f"🌸✨ **𝗥𝗔𝗗𝗛𝗘 𝗥𝗔𝗗𝗛𝗘 • JAI SHRI RAM!** ✨🌸\n\n"
                                f"🌅 𝗚𝗢𝗢𝗗 𝗠𝗢𝗥𝗡𝗜𝗡𝗚 𝗚𝗖 𝗙𝗔𝗠𝗜𝗟𝗬! ☕💫\n"
                                f"🙏 𝗛𝗔𝗩𝗘 𝗔 𝗕𝗟𝗘𝗦𝗦𝗘𝗗, 𝗛𝗔𝗣𝗣𝗬 & 𝗔𝗖𝗧𝗜𝗩𝗘 𝗗𝗔𝗬 𝗔𝗛𝗘𝗔𝗗!\n"
                                f"🔥 𝗟𝗘𝗧'𝗦 𝗦𝗧𝗔𝗥𝗧 𝗧𝗛𝗘 𝗗𝗔𝗬 𝗪𝗜𝗧𝗛 𝗚𝗢𝗢𝗗 𝗩𝗜𝗕𝗦!\n\n"
                                f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
                                f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
                            )
                            safe_send_message(thread_id, morning_card)

                        elif current_hour == 23 and last_night_wish_date != current_date_str:
                            last_night_wish_date = current_date_str
                            night_card = (
                                f"🌙💤 **𝗚𝗢𝗢𝗗 𝗡𝗜𝗚𝗛𝗧, 𝗚𝗖 𝗙𝗔𝗠𝗜𝗟𝗬!** 🌌✨\n\n"
                                f"🛌 𝗧𝗜𝗠𝗘 𝗧𝗢 𝗥𝗘𝗦𝗧 & 𝗥𝗘𝗖𝗛𝗔𝗥𝗚𝗘 𝗙𝗢𝗥 𝗧𝗢𝗠𝗢𝗥𝗥𝗢𝗪!\n"
                                f"🌟 𝗦𝗟𝗘𝗘𝗣 𝗧𝗜𝗚𝗛𝗧, 𝗦𝗪𝗘𝗘𝗧 𝗗𝗥𝗘𝗔𝗠𝗦 𝗘𝗩𝗘𝗥𝗬𝗢𝗡𝗘!\n\n"
                                f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
                                f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
                            )
                            safe_send_message(thread_id, night_card)

                        # 2. AUTO CALL BROADCAST SYSTEM (हर 1 घंटे में)
                        if thread_id not in last_call_broadcast:
                            last_call_broadcast[thread_id] = current_time_loop
                        
                        if current_time_loop - last_call_broadcast[thread_id] > CALL_REMINDER_INTERVAL:
                            last_call_broadcast[thread_id] = current_time_loop
                            call_broadcast_card = (
                                f"🔥📞 **@EVERYONE • GC CALL ALERT!** 📞🔥\n\n"
                                f"👑 𝗛𝗘𝗬 𝗚𝗨𝗬𝗦, 𝗦𝗧𝗔𝗥𝗧 𝗔 𝗖𝗔𝗟𝗟 𝗢𝗥 𝗝𝗢𝗜𝗡 𝗡𝗢𝗪!\n"
                                f"💬 𝗟𝗘𝗧'𝗦 𝗖𝗛𝗔𝗧, 𝗩𝗜𝗕𝗘 & 𝗛𝗔𝗡𝗚𝗢𝗨𝗧 𝗧𝗢𝗚𝗘𝗧𝗛𝗘𝗥 💫\n\n"
                                f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
                                f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
                            )
                            safe_send_message(thread_id, call_broadcast_card)

                        # 3. WELCOME & WELCOME BACK LOGIC
                        if thread_id in group_members_state:
                            old_members = group_members_state[thread_id]
                            newly_joined = current_members - old_members

                            if newly_joined and not is_first_run:
                                for joined_pk in newly_joined:
                                    if joined_pk in welcomed_recently and (current_time_loop - welcomed_recently[joined_pk] < 60):
                                        continue
                                    
                                    welcomed_recently[joined_pk] = current_time_loop
                                    user_obj = next((u for u in users if str(getattr(u, "pk", "")) == joined_pk), None)
                                    if user_obj:
                                        target_username = getattr(user_obj, "username", "User")
                                          
                                        if joined_pk in ever_seen_members:
                                            welcome_back_card = (
                                                f"💫🦋 𝗪𝗘𝗟𝗖𝗢𝗠𝗘 𝗕𝗔𝗖𝗞, @{target_username}! 🦋💫\n\n"
                                                f"🌷 𝗧𝗛𝗘 𝗚𝗖 𝗙𝗘𝗟𝗧 𝗬𝗢𝗨𝗥 𝗔𝗕𝗦𝗘𝗡𝗖𝗘 😌\n"
                                                f"🔥 𝗕𝗔𝗖𝗞 𝗔𝗚𝗔𝗜𝗡 • 𝗦𝗧𝗔𝗬 𝗔𝗖𝗧𝗜𝗩𝗘\n"
                                                f"📜 𝗙𝗢𝗟𝗟𝗢𝗪 𝗧𝗛𝗘 𝗥𝗨𝗟𝗘𝗦 & 𝗘𝗡𝗝𝗢𝗬!\n\n"
                                                f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
                                                f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
                                            )
                                            safe_send_message(thread_id, welcome_back_card)
                                        else:
                                            ever_seen_members.add(joined_pk)
                                            welcome_card = (
                                                f"🦋✨ 𝗪𝗘𝗟𝗖𝗢𝗠𝗘, @{target_username}! ✨🦋\n\n"
                                                f"🌸 𝗛𝗘𝗬! 𝗚𝗟𝗔𝗗 𝗧𝗢 𝗛𝗔𝗩𝗘 𝗬𝗢𝗨 𝗛𝗘𝗥𝗘 💫\n"
                                                f"🤝 𝗦𝗧𝗔𝗬 𝗥𝗘𝗦𝗣𝗘𝗖𝗧𝗙𝗨𝗟 • 𝗙𝗢𝗟𝗟𝗢𝗪 𝗧𝗛𝗘 𝗥𝗨𝗟𝗘𝗦\n"
                                                f"🔥 𝗘𝗡𝗝𝗢𝗬 𝗧𝗛𝗘 𝗚𝗖 & 𝗦𝗧𝗔𝗬 𝗔𝗖𝗧𝗜𝗩𝗘!\n\n"
                                                f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
                                                f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
                                            )
                                            safe_send_message(thread_id, welcome_card)
                        else:
                            ever_seen_members.update(current_members)

                        group_members_state[thread_id] = current_members

                        # DB Synchro
                        for u in users:
                            if getattr(u, "pk", None) and getattr(u, "username", None):
                                ModerationEngine.record_activity(str(u.pk), u.username)

                        # 4. MESSAGE SCANNER & MODERATION
                        messages = list(getattr(thread, "messages", []) or [])
                        if messages:
                            last_msg = messages[0]
                            message_id = str(getattr(last_msg, "id", ""))

                            if message_id and message_id not in seen_message_ids:
                                seen_message_ids.add(message_id)

                                if len(seen_message_ids) > 500:
                                    seen_message_ids.pop()

                                text = str(getattr(last_msg, "text", "") or "").strip()
                                text_lower = text.lower()
                                sender_id = str(getattr(last_msg, "user_id", ""))

                                raw_username = "User"
                                try:
                                    if hasattr(last_msg, 'user') and last_msg.user and hasattr(last_msg.user, 'username'):
                                        raw_username = last_msg.user.username
                                    else:
                                        for u in users:
                                            if str(getattr(u, "pk", "")) == sender_id:
                                                raw_username = getattr(u, "username", "User")
                                                break
                                except Exception:
                                    pass

                                sender_username = str(raw_username).lstrip('@')
                                item_type = str(getattr(last_msg, 'item_type', '') or '')

                                if sender_id == bot_pk:
                                    continue

                                admin_ids_str = {str(x) for x in gc_admins}
                                is_sender_admin = sender_id in admin_ids_str
                                is_dev = sender_username.lower() in [d.lower() for d in AUTHORIZED_DEVS]

                                ModerationEngine.record_activity(sender_id, sender_username)

                                # TARGET LOCK ENFORCEMENT
                                if sender_username.lower() in TARGETED_USERS and not is_dev and not is_sender_admin:
                                    execute_kick(thread_id, sender_id, sender_username, "LOCKED TARGET TERMINATED")
                                    continue

                                # SHADOWBAN CHECK
                                if sender_username.lower() in SHADOWBANNED_USERS and not is_dev and not is_sender_admin:
                                    execute_kick(thread_id, sender_id, sender_username, "SHADOWBANNED TARGET", silent=True)
                                    continue

                                # LOCKDOWN ENFORCEMENT
                                if LOCKDOWN_MODE and not is_sender_admin and not is_dev:
                                    execute_kick(thread_id, sender_id, sender_username, "GC LOCKDOWN ENFORCEMENT")
                                    continue

                                # ================= MODERATION (NON-ADMINS) =================
                                if not is_sender_admin and not is_dev:
                                    current_t = time.time()

                                    # Fast Flood Control
                                    if sender_id not in user_spam_tracker:
                                        user_spam_tracker[sender_id] = []
                                    user_spam_tracker[sender_id].append(current_t)
                                    user_spam_tracker[sender_id] = [t for t in user_spam_tracker[sender_id] if current_t - t < 5]

                                    if len(user_spam_tracker[sender_id]) >= 4:
                                        execute_kick(thread_id, sender_id, sender_username, "MESSAGE FLOODING SPAM")
                                        continue

                                    # Strict Bad Word / Slang Check
                                    if is_abusive_text(text):
                                        warn_count, trust_score = ModerationEngine.add_warning(sender_username)
                                        ModerationEngine.log_event(thread_id, sender_username, "ABUSE_DETECTED", text)

                                        if warn_count >= MAX_WARNINGS_BEFORE_KICK:
                                            execute_kick(thread_id, sender_id, sender_username, "EXCEEDED MAXIMUM WARNINGS (3/3)")
                                        else:
                                            abuse_card = (
                                                f"🚨🛡️ **𝗠𝗢𝗗𝗘𝗥𝗔𝗧𝗜𝗢𝗡 𝗔𝗟𝗘𝗥𝗧 • 𝗔𝗕𝗨𝗦𝗘!**\n\n"
                                                f"👤 **𝗨𝗦𝗘𝗥** ➜ @{sender_username}\n"
                                                f"⚠️ **𝗩𝗜𝗢𝗟𝗔𝗧𝗜𝗢𝗡** ➜ ABUSIVE LANGUAGE DETECTED!\n"
                                                f"🛑 **𝗪𝗔𝗥𝗡𝗜𝗡𝗚** ➜ {warn_count}/{MAX_WARNINGS_BEFORE_KICK}\n"
                                                f"📉 **𝗧𝗥𝗨𝗦𝗧 𝗦𝗖𝗢𝗥𝗘** ➜ {trust_score}%\n\n"
                                                f"❗ *3 Warnings will result in Automatic Kick!*\n\n"
                                                f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
                                                f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
                                            )
                                            safe_send_message(thread_id, abuse_card)
                                        continue

                                    # Link Control
                                    if any(domain in text_lower for domain in ['http://', 'https://', 'www.', '.com', 't.me', 'instagram.com/']):
                                        link_msg = (
                                            f"🚨🔗 **𝗛𝗘𝗬 @{sender_username} — 𝗟𝗜𝗡𝗞 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗!**\n\n"
                                            f"⚠️ 𝗨𝗡𝗔𝗨𝗧𝗛𝗢𝗥𝗜𝗭𝗘𝗗 𝗟𝗜𝗡𝗞𝗦 𝗔𝗥𝗘 𝗡𝗢𝗧 𝗔𝗟𝗟𝗢𝗪𝗘𝗗 𝗛𝗘𝗥𝗘.\n"
                                            f"🛑 𝗣𝗟𝗘𝗔𝗦𝗘 𝗥𝗘𝗠𝗢𝗩𝗘 𝗜𝗧 & 𝗗𝗢𝗡'𝗧 𝗥𝗘𝗣𝗘𝗔𝗧!\n\n"
                                            f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
                                        )
                                        safe_send_message(thread_id, link_msg)
                                        continue

                                    # Media & Reels Spam Filter
                                    if item_type in ['clip', 'media', 'video', 'visual_media', 'felix_share', 'story_share'] or '/reel/' in text_lower:
                                        reel_msg = (
                                            f"🚫🎬 **𝗥𝗘𝗘𝗟𝗦 / 𝗠𝗘𝗗𝗜𝗔 𝗡𝗢𝗧 𝗔𝗟𝗟𝗢𝗪𝗘𝗗!**\n\n"
                                            f"👤 𝗨𝗦𝗘𝗥 ➜ @{sender_username}\n\n"
                                            f"⚠️ 𝗣𝗟𝗘𝗔𝗦𝗘 𝗗𝗢 𝗡𝗢𝗧 𝗦𝗣𝗔𝗠 𝗩𝗜𝗗𝗘𝗢𝗦 / 𝗥𝗘𝗘𝗟𝗦 𝗜𝗡 𝗚𝗖.\n\n"
                                            f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
                                            f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
                                        )
                                        safe_send_message(thread_id, reel_msg)
                                        continue

                                # ================= PUBLIC COMMAND CARDS =================
                                if text_lower.startswith("!stats"):
                                    parts = text.split()
                                    target_user = parts[1] if len(parts) > 1 else f"@{sender_username}"
                                    safe_send_message(thread_id, ModerationEngine.get_user_stats(target_user))

                                elif text_lower == "!botinfo":
                                    info_card = (
                                        f"⚡🤖 **𝗕𝗢𝗧 𝗜𝗡𝗙𝗢 & 𝗦𝗧𝗔𝗧𝗨𝗦** 🤖⚡\n\n"
                                        f"🛡️ **𝗠𝗢𝗗𝗘** ➜ ZERO-TOLERANCE ULTRA SHIELD\n"
                                        f"⚙️ **𝗩𝗘𝗥𝗦𝗜𝗢𝗡** ➜ 2026 MERGED MASTER VIP\n"
                                        f"🔥 **𝗔𝗨𝗥𝗔** ➜ GC PROTECTOR & MANAGER\n\n"
                                        f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
                                        f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
                                    )
                                    safe_send_message(thread_id, info_card)

                                elif text_lower == "!rules":
                                    rules_card = (
                                        f"📜✨ **𝗚𝗖 𝗥𝗨𝗟𝗘𝗦 & 𝗠𝗢𝗗𝗘𝗥𝗔𝗧𝗜𝗢𝗡** ✨📜\n\n"
                                        f"1️⃣ 🚫 **𝗡𝗢 𝗔𝗕𝗨𝗦𝗜𝗩𝗘 𝗟𝗔𝗡𝗚𝗨𝗔𝗚𝗘** (3 Warns = Auto Kick)\n"
                                        f"2️⃣ 🚫 **𝗡𝗢 𝗟𝗜𝗡𝗞𝗦 / 𝗦𝗣𝗔𝗠𝗠𝗜𝗡𝗚** (Auto Filter)\n"
                                        f"3️⃣ 🚫 **𝗡𝗢 𝗥𝗘𝗘𝗟𝗦 / 𝗩𝗜𝗗𝗘𝗢 𝗙𝗟𝗢𝗢𝗗** (Auto Warning)\n"
                                        f"4️⃣ 🤝 **𝗥𝗘𝗦𝗣𝗘𝗖𝗧 𝗔𝗟𝗟 𝗠𝗘𝗠𝗕𝗘𝗥𝗦 & 𝗔𝗗𝗠𝗜𝗡𝗦**\n\n"
                                        f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
                                        f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
                                    )
                                    safe_send_message(thread_id, rules_card)

                                elif text_lower.startswith("!userinfo"):
                                    parts = text.split()
                                    if len(parts) > 1:
                                        target_name = parts[1].lstrip('@')
                                        try:
                                            u_info = cl.user_info_by_username(target_name)
                                            info_str = (
                                                f"👑✨ **𝗜𝗡𝗦𝗧𝗔𝗚𝗥𝗔𝗠 𝗟𝗜𝗩𝗘 𝗜𝗡𝗙𝗢** ✨👑\n\n"
                                                f"👤 **𝗨𝗦𝗘𝗥𝗡𝗔𝗠𝗘** ➜ @{u_info.username}\n"
                                                f"📛 **𝗙𝗨𝗟𝗟 𝗡𝗔𝗠𝗘** ➜ {u_info.full_name}\n"
                                                f"🆔 **𝗨𝗦𝗘𝗥 𝗜𝗗** ➜ `{u_info.pk}`\n"
                                                f"👥 **𝗙𝗢𝗟𝗟𝗢𝗪𝗘𝗥𝗦** ➜ {u_info.follower_count}\n"
                                                f"🔄 **𝗙𝗢𝗟𝗟𝗢𝗪𝗜𝗡𝗚** ➜ {u_info.following_count}\n"
                                                f"🔒 **𝗣𝗥𝗜𝗩𝗔𝗧𝗘** ➜ {u_info.is_private}\n\n"
                                                f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
                                                f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
                                            )
                                            safe_send_message(thread_id, info_str)
                                        except Exception:
                                            safe_send_message(thread_id, f"❌ Failed to fetch Instagram live info for @{target_name}!")

                                # ================= ADMIN / DEV COMMANDS =================
                                if is_sender_admin or is_dev:
                                    if text_lower.startswith("!warn"):
                                        parts = text.split()
                                        if len(parts) > 1:
                                            target_user = parts[1].lstrip('@')
                                            w_cnt, t_sc = ModerationEngine.add_warning(target_user)
                                            safe_send_message(thread_id, f"⚠️ **MANUAL WARN:** @{target_user} now has {w_cnt}/{MAX_WARNINGS_BEFORE_KICK} warnings!")

                                    elif text_lower.startswith("!unwarn") or text_lower.startswith("!resetwarn"):
                                        parts = text.split()
                                        if len(parts) > 1:
                                            target_user = parts[1].lstrip('@')
                                            ModerationEngine.reset_warnings(target_user)
                                            safe_send_message(thread_id, f"🟢✨ **WARNINGS RESET:** All warnings for @{target_user} have been cleared!")

                                # ================= MASTER DEVELOPER COMMANDS =================
                                if is_dev:
                                    if text_lower == "!tagall":
                                        all_mentions = " ".join([f"@{u.username}" for u in users if getattr(u, "username", None)])
                                        tag_card = (
                                            f"📢🔥 **@EVERYONE • 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 𝗔𝗟𝗘𝗥𝗧!** 🔥📢\n\n"
                                            f"💬 𝗠𝗘𝗦𝗦𝗔𝗚𝗘 ➜ Developer Summoned Everyone!\n\n"
                                            f"👥 **𝗧𝗔𝗚𝗚𝗘𝗗 𝗠𝗘𝗠𝗕𝗘𝗥𝗦** ➜\n{all_mentions}\n\n"
                                            f"👨‍💻 𝗗𝗘𝗩 ➜ @{sender_username}"
                                        )
                                        safe_send_message(thread_id, tag_card)

                                    elif text_lower == "!godmode":
                                        god_card = (
                                            f"👑⚡ **𝗣𝗢𝗢𝗞𝗜𝗘𝗘𝗘 𝗚𝗢𝗗 𝗠𝗢𝗗𝗘** ⚡👑\n\n"
                                            f"💻 **𝗦𝗬𝗦𝗧𝗘𝗠** ➜ ONLINE & FULL CONTROL\n"
                                            f"🛡️ **𝗟𝗢𝗖𝗞𝗗𝗢𝗪𝗡** ➜ {'ENABLED 🔴' if LOCKDOWN_MODE else 'DISABLED 🟢'}\n"
                                            f"👻 **𝗦𝗛𝗔𝗗𝗢𝗪𝗕𝗔𝗡𝗦** ➜ {len(SHADOWBANNED_USERS)} Active\n"
                                            f"🎯 **𝗧𝗔𝗥𝗚𝗘𝗧𝗦** ➜ {len(TARGETED_USERS)} Active\n\n"
                                            f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
                                            f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
                                        )
                                        safe_send_message(thread_id, god_card)

                                    elif text_lower == "!lockdown":
                                        LOCKDOWN_MODE = True
                                        safe_send_message(thread_id, "🔴🚨 **EMERGENCY LOCKDOWN ACTIVATED! Non-Admins will be kicked on message.**")

                                    elif text_lower == "!unlock":
                                        LOCKDOWN_MODE = False
                                        safe_send_message(thread_id, "🟢✨ **LOCKDOWN LIFTED!** GC is back to normal.")

                                    elif text_lower.startswith("!target"):
                                        parts = text.split()
                                        if len(parts) > 1:
                                            target_name = parts[1].lstrip('@').lower()
                                            TARGETED_USERS.add(target_name)
                                            safe_send_message(thread_id, f"🎯⚡ **TARGET LOCKED:** @{target_name} marked for instant removal upon next message!")

                                    elif text_lower.startswith("!shadowban"):
                                        parts = text.split()
                                        if len(parts) > 1:
                                            target_name = parts[1].lstrip('@').lower()
                                            SHADOWBANNED_USERS.add(target_name)
                                            safe_send_message(thread_id, f"👻 **SHADOWBAN ACTIVATED:** @{target_name} will be silently kicked!")

                                    elif text_lower.startswith("!nuke"):
                                        parts = text.split()
                                        if len(parts) > 1:
                                            target_name = parts[1].lstrip('@')
                                            target_obj = next((u for u in users if getattr(u, "username", "").lower() == target_name.lower()), None)
                                            if target_obj:
                                                execute_kick(thread_id, str(getattr(target_obj, "pk")), target_name, "💣 DEV SUPREME NUKE BAN")

                                    elif text_lower == "!health":
                                        safe_send_message(thread_id, monitor.get_health_report())

                                    elif text_lower.startswith("!addword"):
                                        parts = text.split(maxsplit=1)
                                        if len(parts) > 1:
                                            RESTRICTED_WORDS.add(parts[1].strip().lower())
                                            safe_send_message(thread_id, f"✅ Word added to Blocklist: `{parts[1].strip()}`")

                                # @everyone या @bot टैग करने पर उत्तर
                                elif "@everyone" in text_lower or bot_tag in text_lower:
                                    response_msg = (
                                        f"👋 𝗛𝗘𝗟𝗟𝗢 @{sender_username}!\n\n"
                                        f"🤖 𝗕𝗢𝗧 𝗜𝗦 𝗔𝗖𝗧𝗜𝗩𝗘 𝗔𝗡𝗗 𝗠𝗔𝗡𝗔𝗚𝗜𝗡𝗚 𝗧𝗛𝗘 𝗚𝗖 𝗦𝗠𝗢𝗢𝗧𝗛𝗟𝗬. 🚀\n\n"
                                        f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
                                        f"👨‍💻 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ @{OWNER_USERNAME}"
                                    )
                                    safe_send_message(thread_id, response_msg)

                    is_first_run = False

                except (PleaseWaitFewMinutes, ClientThrottledError):
                    time.sleep(60)
                except (LoginRequired, ChallengeRequired) as session_err:
                    print(f"[-] SESSION EXPIRED / CHECKPOINT CAUGHT: {session_err}")
                    raise session_err
                except Exception as inner_e:
                    print(f"[LOOP ERROR] {inner_e}")
                    time.sleep(POLL_INTERVAL)

                time.sleep(POLL_INTERVAL)

        except Exception as outer_e:
            print(f"[-] RECONNECTING DUE TO ERROR... Waiting 30 seconds: {outer_e}")
            time.sleep(30)

if __name__ == "__main__":
    start_bot()

