import os
import time
import psutil
from datetime import datetime
from dotenv import load_dotenv
from instagrapi import Client
from instagrapi.exceptions import LoginRequired, ChallengeRequired
from sqlalchemy import create_engine, Column, String, Integer, Float, DateTime, Text, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker

# Environment Variables लोड करना
load_dotenv()

# ==================== CONFIGURATION ====================
SESSION_ID = os.getenv("SESSION_ID", "7207590267%3AOzEdEpuYJTJj6t%3A20%3AAYkMaEgKhgBcicgwWniTeXrUH-O3FDT_4s5sepDRtQ")
BOT_USERNAME = os.getenv("BOT_USERNAME", "smw_vyron_bot")
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "fx_smw ✘ aat_nnk25")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///bot_database.db")

# कॉल रिमाइंडर का समय: 1 घंटा (3600 सेकंड)
CALL_REMINDER_INTERVAL = int(os.getenv("CALL_REMINDER_INTERVAL", 3600))
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", 3))

# Restricted Words (गाली-गलौज / 18+ शब्द)
RESTRICTED_WORDS = [
    '18+', 'adult', 'sex', 'xxx', 'porn', 'nude', 
    'gali', 'bhadve', 'chutiya', 'madarchod', 'behenchod'
]
# =======================================================

# ==================== DATABASE SYSTEM ====================
Base = declarative_base()

class UserProfile(Base):
    __tablename__ = 'user_profiles'
    user_id = Column(String, primary_key=True)
    username = Column(String, nullable=False)
    join_date = Column(DateTime, default=datetime.utcnow)
    last_active = Column(DateTime, default=datetime.utcnow)
    total_messages = Column(Integer, default=0)
    warning_count = Column(Integer, default=0)
    violation_count = Column(Integer, default=0)
    trust_score = Column(Float, default=100.0)
    reputation_score = Column(Float, default=50.0)
    risk_score = Column(Float, default=0.0)

class SecurityLog(Base):
    __tablename__ = 'security_logs'
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    group_id = Column(String)
    user_id = Column(String)
    event_type = Column(String)
    details = Column(Text)

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)

def init_db():
    Base.metadata.create_all(engine)

# ==================== HELPER ENGINES ====================
class ProfileEngine:
    @staticmethod
    def record_activity(user_id: str, username: str):
        db = SessionLocal()
        try:
            profile = db.query(UserProfile).filter(UserProfile.user_id == str(user_id)).first()
            if not profile:
                profile = UserProfile(
                    user_id=str(user_id), 
                    username=username,
                    total_messages=0,
                    trust_score=100.0,
                    warning_count=0,
                    violation_count=0,
                    reputation_score=50.0,
                    risk_score=0.0
                )
                db.add(profile)
            
            # NoneType बग को रोकने के लिए सुरक्षित अपडेट
            profile.username = username
            profile.total_messages = (profile.total_messages or 0) + 1
            profile.last_active = datetime.utcnow()
            profile.trust_score = min(100.0, (profile.trust_score or 100.0) + 0.1)
            db.commit()
        except Exception as e:
            db.rollback()
            print(f"[DB ERROR] {e}")
        finally:
            db.close()

class ModerationEngine:
    @staticmethod
    def check_message(text: str, item_type: str, user_id: str, username: str, group_id: str):
        text_lower = text.lower()
        
        # 1. लिंक डिटेक्शन
        if any(domain in text_lower for domain in ['http://', 'https://', 'www.', '.com', 't.me', 'instagram.com/']):
            return "LINK", (
                f"🚨🔗 𝗛𝗘𝗬 @{username} — 𝗟𝗜𝗡𝗞 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗!\n\n"
                f"⚠️ 𝗨𝗡𝗔𝗨𝗧𝗛𝗢𝗥𝗜𝗭𝗘𝗗 𝗟𝗜𝗡𝗞𝗦 𝗔𝗥𝗘 𝗡𝗢𝗧 𝗔𝗟𝗟𝗢𝗪𝗘𝗗 𝗛𝗘𝗥𝗘.\n"
                f"🛑 𝗣𝗟𝗘𝗔𝗦𝗘 𝗥𝗘𝗠𝗢𝗩𝗘 𝗜𝗧 & 𝗗𝗢𝗡'𝗧 𝗥𝗘𝗣𝗘𝗔𝗧!\n\n"
                f"⚡ 𝗥𝗘𝗣𝗘𝗔𝗧 𝗩𝗜𝗢𝗟𝗔𝗧𝗜𝗢𝗡𝗦 𝗠𝗔𝗬 𝗟𝗘𝗔𝗗 𝗧𝗢 𝗥𝗘𝗠𝗢𝗩𝗔𝗟 🚪\n"
                f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
            )
        
        # 2. रील्स / वीडियो डिटेक्शन
        if item_type in ['clip', 'media', 'video', 'visual_media'] or '/reel/' in text_lower:
            return "REEL", (
                f"🚫🎬 𝗥𝗘𝗘𝗟𝗦 𝗡𝗢𝗧 𝗔𝗟𝗟𝗢𝗪𝗘𝗗!\n\n"
                f"👤 @{username}\n\n"
                f"⚠️ 𝗥𝗘𝗘𝗟𝗦 / 𝗩𝗜𝗗𝗘𝗢𝗦 𝗔𝗥𝗘 𝗡𝗢𝗧 𝗔𝗟𝗟𝗢𝗪𝗘𝗗 𝗛𝗘𝗥𝗘.\n\n"
                f"🛑 𝗣𝗟𝗘𝗔𝗦𝗘 𝗗𝗢𝗡'𝗧 𝗥𝗘𝗣𝗘𝗔𝗧!\n\n"
                f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
                f"👨‍💻 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ @{OWNER_USERNAME}"
            )
        
        # 3. गाली / 18+ कंटेंट डिटेक्शन
        if any(word in text_lower for word in RESTRICTED_WORDS):
            ModerationEngine._register_violation(user_id, group_id, "PROFANITY")
            return "RESTRICTED", (
                f"🚨🛡️ 𝗠𝗢𝗗𝗘𝗥𝗔𝗧𝗜𝗢𝗡 𝗔𝗟𝗘𝗥𝗧!\n\n"
                f"👤 𝗨𝗦𝗘𝗥 ➜ @{username}\n"
                f"🚫 𝗜𝗡𝗔𝗣𝗣𝗥𝗢𝗣𝗥𝗜𝗔𝗧𝗘 𝗠𝗘𝗗𝗜𝗔 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗!\n\n"
                f"⚠️ 𝗧𝗛𝗜𝗦 𝗖𝗢𝗡𝗧𝗘𝗡𝗧 𝗜𝗦 𝗡𝗢𝗧 𝗔𝗟𝗟𝗢𝗪𝗘𝗗 𝗜𝗡 𝗧𝗛𝗜𝗦 𝗚𝗖.\n\n"
                f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
                f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
            )

        return None, None

    @staticmethod
    def _register_violation(user_id: str, group_id: str, v_type: str):
        db = SessionLocal()
        try:
            profile = db.query(UserProfile).filter(UserProfile.user_id == str(user_id)).first()
            if profile:
                profile.violation_count = (profile.violation_count or 0) + 1
                profile.trust_score = max(0.0, (profile.trust_score or 100.0) - 10.0)
                profile.risk_score = min(100.0, (profile.risk_score or 0.0) + 15.0)
            
            log = SecurityLog(group_id=group_id, user_id=str(user_id), event_type=v_type, details="Violation Recorded")
            db.add(log)
            db.commit()
        except Exception as e:
            db.rollback()
        finally:
            db.close()

class SystemMonitor:
    def __init__(self):
        self.start_time = time.time()

    def get_health_report(self) -> str:
        uptime = int(time.time() - self.start_time)
        cpu = psutil.cpu_percent()
        memory = psutil.virtual_memory().percent
        return f"📊 **SYSTEM HEALTH REPORT**\n\n⏱️ Uptime: {uptime}s\n💻 CPU Load: {cpu}%\n🧠 RAM Usage: {memory}%"

# ==================== MAIN BOT ENGINE ====================
def start_bot():
    init_db()
    monitor = SystemMonitor()

    while True:
        try:
            print("[*] Connecting to Instagram Server via Session ID...")
            cl = Client()
            cl.login_by_sessionid(SESSION_ID)
            print(f"[+] SUCCESS: Bot @{BOT_USERNAME} is LIVE with Database & System Health Monitoring! 🚀")

            seen_message_ids = set()
            group_members_state = {}
            ever_seen_members = set()
            welcomed_recently = {}
            recent_sent_texts = {}
            last_call_broadcast = {}

            last_morning_wish_date = ""
            last_night_wish_date = ""
            is_first_run = True

            def safe_send_message(thread_id, text_content):
                current_time = time.time()
                if thread_id in recent_sent_texts:
                    last_text, last_time = recent_sent_texts[thread_id]
                    if last_text == text_content and (current_time - last_time < 10):
                        return
                
                recent_sent_texts[thread_id] = (text_content, current_time)
                cl.direct_send(text_content, thread_ids=[thread_id])
                time.sleep(1)

            while True:
                try:
                    threads = cl.direct_threads(amount=2)
                    current_time_loop = time.time()
                    now = datetime.now()
                    current_hour = now.hour
                    current_date_str = now.strftime("%Y-%m-%d")

                    for thread in threads:
                        if not getattr(thread, "is_group", False):
                            continue

                        thread_id = thread.id
                        bot_tag = f"@{BOT_USERNAME.lower()}"

                        # 1. Admins List Fetching
                        gc_admins = []
                        try:
                            if hasattr(thread, 'admin_user_ids') and thread.admin_user_ids:
                                gc_admins = [str(uid) for uid in thread.admin_user_ids]
                            elif hasattr(thread, 'admin_users') and thread.admin_users:
                                gc_admins = [str(getattr(admin, 'pk', admin)) for admin in thread.admin_users]
                        except Exception:
                            gc_admins = []

                        if not gc_admins:
                            continue

                        bot_pk = str(cl.user_id)
                        users = list(getattr(thread, "users", []) or [])
                        current_members = {str(getattr(u, "pk", "")) for u in users if getattr(u, "pk", None)}

                        # 2. MORNING & NIGHT WISH SYSTEM
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

                        # 3. AUTO CALL BROADCAST SYSTEM (1 घंटा)
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

                        # 4. WELCOME & WELCOME BACK LOGIC
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

                        # 5. FAST MESSAGE SCANNER & MODERATION
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
                                item_type = str(getattr(last_msg, 'item_type', '') or '')

                                if sender_id == bot_pk:
                                    continue

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
                                admin_ids_str = {str(x) for x in gc_admins}
                                is_sender_admin = sender_id in admin_ids_str

                                # सुरक्षित यूज़र एक्टिविटी और डेटाबेस अपडेट
                                ProfileEngine.record_activity(sender_id, sender_username)

                                if not is_sender_admin:
                                    mod_type, mod_msg = ModerationEngine.check_message(
                                        text, item_type, sender_id, sender_username, thread_id
                                    )
                                    if mod_msg:
                                        safe_send_message(thread_id, mod_msg)
                                        continue

                                # @everyone या बोट टैग करने पर उत्तर
                                if "@everyone" in text_lower or bot_tag in text_lower:
                                    response_msg = (
                                        f"👋 𝗛𝗘𝗟𝗟𝗢 @{sender_username}!\n\n"
                                        f"🤖 𝗕𝗢𝗧 𝗜𝗦 𝗔𝗖𝗧𝗜𝗩𝗘 𝗔𝗡𝗗 𝗠𝗔𝗡𝗔𝗚𝗜𝗡𝗚 𝗧𝗛𝗘 𝗚𝗖 𝗦𝗠𝗢𝗢𝗧𝗛𝗟𝗬. 🚀\n\n"
                                        f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
                                        f"👨‍💻 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ @{OWNER_USERNAME}"
                                    )
                                    safe_send_message(thread_id, response_msg)

                                # हेल्थ कमांड चेक
                                elif text_lower == "!health":
                                    safe_send_message(thread_id, monitor.get_health_report())

                    is_first_run = False

                except (LoginRequired, ChallengeRequired) as session_err:
                    print(f"[-] SESSION EXPIRED / CHECKPOINT CAUGHT: {session_err}")
                    raise session_err

                except Exception as inner_e:
                    print(f"[LOOP ERROR] {inner_e}")
                    time.sleep(10)

                time.sleep(POLL_INTERVAL)

        except Exception as outer_e:
            print(f"[-] RECONNECTING DUE TO SESSION/ERROR... Waiting 30 seconds: {outer_e}")
            time.sleep(30)

if __name__ == "__main__":
    start_bot()

