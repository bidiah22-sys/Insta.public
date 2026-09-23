import os
import time
import psutil
from datetime import datetime, timezone
from dotenv import load_dotenv
from instagrapi import Client
from instagrapi.exceptions import (
    LoginRequired, ChallengeRequired, PleaseWaitFewMinutes, ClientThrottledError
)
from sqlalchemy import create_engine, Column, String, Integer, Float, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker

# Environment Variables Load
load_dotenv()

# ==================== CONFIGURATION ====================
SESSION_ID = os.getenv("SESSION_ID", "7207590267%3AOzEdEpuYJTJj6t%3A20%3AAYkMaEgKhgBcicgwWniTeXrUH-O3FDT_4s5sepDRtQ")
BOT_USERNAME = os.getenv("BOT_USERNAME", "smw_vyron_bot")

# AUTHORIZED DEVELOPERS / OWNERS
OWNER_1 = "fx_smw ✘ aat_nnk25"
OWNER_2 = "aat_nnk"
AUTHORIZED_DEVS = ["fx_smw", "aat_nnk", "aat_nnk25", "fx_smw ✘ aat_nnk25"]

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///bot_database.db")
CALL_REMINDER_INTERVAL = int(os.getenv("CALL_REMINDER_INTERVAL", 3600))
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", 6)) 

# ----------------- DYNAMIC RESTRICTED WORDS LIST -----------------
RESTRICTED_WORDS = set([
    'madarchod', 'maderchod', 'madar-chod', 'mc', 'mkc', 'tmkc', 
    'bhenchod', 'behenchod', 'bc', 'bhosdike', 'bhosdi', 'bhosda',
    'chutiya', 'chutiye', 'chutiyap', 'gandu', 'gaand', 'gand',
    'lund', 'luda', 'lauda', 'chut', 'chuth', 'randi', 'randwa',
    'bhadwa', 'bhadwe', 'harami', 'haramkhor', 'kamine', 'kamina',
    'saala', 'saale', 'bsdk', 'bhen-chod', 'behen-chod',
    '18+', 'adult', 'sex', 'xxx', 'porn', 'nude', 'nudes', 
    'fuck', 'fucking', 'bitch', 'bastard', 'asshole', 'pussy', 'dick'
])
# =====================================================================

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
    reputation_score = Column(Float, default=50.0)
    risk_score = Column(Float, default=0.0)

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
            
            profile.username = username
            profile.total_messages = (profile.total_messages or 0) + 1
            profile.last_active = get_utc_now()
            profile.trust_score = min(100.0, (profile.trust_score or 100.0) + 0.1)
            db.commit()
        except Exception as e:
            db.rollback()
        finally:
            db.close()

    @staticmethod
    def get_user_stats(username: str) -> str:
        db = SessionLocal()
        try:
            clean_user = username.lstrip('@')
            profile = db.query(UserProfile).filter(UserProfile.username.ilike(clean_user)).first()
            if profile:
                return (
                    f"🛡️📊 **𝗨𝗦𝗘𝗥 𝗦𝗘𝗖𝗨𝗥𝗜𝗧𝗬 𝗣𝗥𝗢𝗙𝗜𝗟𝗘** 📊🛡️\n\n"
                    f"👤 **𝗨𝗦𝗘𝗥𝗡𝗔𝗠𝗘** ➜ @{profile.username}\n"
                    f"💬 **𝗧𝗢𝗧𝗔𝗟 𝗠𝗦𝗚𝗦** ➜ {profile.total_messages}\n"
                    f"⚠️ **𝗪𝗔𝗥𝗡𝗜𝗡𝗚𝗦** ➜ {profile.warning_count}/3\n"
                    f"🚫 **𝗩𝗜𝗢𝗟𝗔𝗧𝗜𝗢𝗡𝗦** ➜ {profile.violation_count}\n"
                    f"🔥 **𝗥𝗜𝗦𝗞 𝗦𝗖𝗢𝗥𝗘** ➜ {profile.risk_score}%\n"
                    f"💎 **𝗧𝗥𝗨𝗦𝗧 𝗦𝗖𝗢𝗥𝗘** ➜ {profile.trust_score}%\n\n"
                    f"🤖 **𝗕𝗢𝗧** ➜ @{BOT_USERNAME}"
                )
            return f"❌ User @{clean_user} not found in Database!"
        finally:
            db.close()

class ModerationEngine:
    @staticmethod
    def check_message(text: str, item_type: str, user_id: str, username: str, group_id: str, admin_mentions_str: str):
        text_lower = text.lower()
        
        # 1. Profanity Detection
        if any(word in text_lower for word in RESTRICTED_WORDS):
            warn_count = ModerationEngine._register_violation(user_id, username, group_id, "PROFANITY")
            return "RESTRICTED", (
                f"🚨🤬 **𝗦𝗧𝗥𝗜𝗖𝗧 𝗣𝗥𝗢𝗙𝗔𝗡𝗜𝗧𝗬 & 𝗔𝗕𝗨𝗦𝗘 𝗔𝗟𝗘𝗥𝗧!**\n\n"
                f"👤 **𝗢𝗙𝗙𝗘𝗡𝗗𝗘𝗥** ➜ @{username}\n"
                f"🚫 **𝗩𝗜𝗢𝗟𝗔𝗧𝗜𝗢𝗡** ➜ ABUSIVE / RESTRICTED LANGUAGE\n"
                f"⚠️ **𝗪𝗔𝗥𝗡𝗜𝗡𝗚 𝗟𝗘𝗩𝗘𝗟** ➜ [{warn_count}/3]\n"
                f"🛑 **𝗦𝗧𝗔𝗧𝗨𝗦** ➜ Violation Saved in Database!\n\n"
                f"📢 **𝗔𝗗𝗠𝗜𝗡 𝗔𝗟𝗘𝗥𝗧** ➜ {admin_mentions_str}\n\n"
                f"🤖 **𝗕𝗢𝗧** ➜ @{BOT_USERNAME}\n"
                f"👨‍💻 **𝗗🇪𝗩𝗦** ➜ @fx_smw | @aat_nnk"
            )

        # 2. Unauthorized Link Detection
        if any(domain in text_lower for domain in ['http://', 'https://', 'www.', '.com', 't.me', 'instagram.com/']):
            warn_count = ModerationEngine._register_violation(user_id, username, group_id, "LINK")
            return "LINK", (
                f"🚨🔗 **𝗟𝗜𝗡𝗞 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗 • 𝗥𝗨𝗟🇪 𝗩𝗜𝗢𝗟𝗔𝗧𝗜𝗢𝗡!**\n\n"
                f"👤 **𝗨𝗦𝗘𝗥** ➜ @{username}\n"
                f"⚠️ **𝗪𝗔𝗥𝗡𝗜𝗡𝗚 𝗟🇪𝗩🇪𝗟** ➜ [{warn_count}/3]\n"
                f"🛑 **𝗔𝗖𝗧𝗜𝗢𝗡** ➜ Unauthorized links prohibited!\n\n"
                f"📢 **𝗔𝗗𝗠𝗜𝗡 𝗔𝗟🇪𝗥𝗧** ➜ {admin_mentions_str}\n\n"
                f"🤖 **𝗕𝗢𝗧** ➜ @{BOT_USERNAME}\n"
                f"👨‍💻 **𝗗🇪𝗩𝗦** ➜ @fx_smw | @aat_nnk"
            )
        
        # 3. Reels & Media Restrictions
        if item_type in ['clip', 'media', 'video', 'visual_media', 'felix_share', 'story_share'] or '/reel/' in text_lower or '/reels/' in text_lower or '/p/' in text_lower:
            return "REEL", (
                f"🚫🎬 **𝗥🇪🇪𝗟𝗦 / 𝗠🇪𝗗𝗜𝗔 𝗡𝗢𝗧 𝗔𝗟𝗟𝗢𝗪🇪𝗗!**\n\n"
                f"👤 **𝗨𝗦🇪𝗥** ➜ @{username}\n"
                f"⚠️ **𝗔𝗟🇪𝗥𝗧** ➜ Sharing media/reels is not permitted.\n\n"
                f"📢 **𝗔𝗗𝗠𝗜𝗡 𝗔𝗟🇪𝗥𝗧** ➜ {admin_mentions_str}\n\n"
                f"🤖 **𝗕𝗢𝗧** ➜ @{BOT_USERNAME}\n"
                f"👨‍💻 **𝗗🇪𝗩𝗦** ➜ @fx_smw | @aat_nnk"
            )

        return None, None

    @staticmethod
    def _register_violation(user_id: str, username: str, group_id: str, v_type: str) -> int:
        db = SessionLocal()
        warn_count = 1
        try:
            profile = db.query(UserProfile).filter(UserProfile.user_id == str(user_id)).first()
            if profile:
                profile.warning_count = (profile.warning_count or 0) + 1
                profile.violation_count = (profile.violation_count or 0) + 1
                profile.trust_score = max(0.0, (profile.trust_score or 100.0) - 15.0)
                profile.risk_score = min(100.0, (profile.risk_score or 0.0) + 20.0)
                warn_count = profile.warning_count
            
            log = SecurityLog(group_id=group_id, username=username, event_type=v_type, details="Rule Violation Logged")
            db.add(log)
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()
        return warn_count

class SystemMonitor:
    def __init__(self):
        self.start_time = time.time()

    def get_health_report(self) -> str:
        uptime_sec = int(time.time() - self.start_time)
        hours, remainder = divmod(uptime_sec, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_fmt = f"{hours}h {minutes}m {seconds}s"
        
        cpu = psutil.cpu_percent()
        memory = psutil.virtual_memory().percent
        
        return (
            f"⚡📊 **𝗨𝗟𝗧𝗥𝗔 𝗦𝗬𝗦𝗧🇪𝗠 & 𝗦🇪𝗥𝗩🇪𝗥 𝗛🇪𝗔𝗟𝗧𝗛** 📊⚡\n\n"
            f"👑 **𝗔𝗖𝗖🇪𝗦𝗦** ➜ AUTHORIZED DEVELOPERS ONLY\n"
            f"🟢 **𝗦𝗧𝗔𝗧𝗨𝗦** ➜ 24/7 ONLINE & FULLY OPTIMIZED\n"
            f"⏱️ **𝗨𝗣𝗧𝗜𝗠🇪** ➜ {uptime_fmt}\n"
            f"💻 **𝗖𝗣𝗨 𝗟𝗢𝗔𝗗** ➜ {cpu}%\n"
            f"🧠 **𝗥𝗔𝗠 𝗨𝗦𝗔𝗚🇪** ➜ {memory}%\n"
            f"🛡️ **𝗠𝗢𝗗🇪𝗥𝗔𝗧𝗜𝗢𝗡** ➜ ULTRA PRO MAX STRICT MODE\n\n"
            f"🤖 **𝗕𝗢𝗧** ➜ @{BOT_USERNAME}\n"
            f"👨‍💻 **𝗗🇪𝗩𝗦** ➜ @fx_smw | @aat_nnk"
        )

    @staticmethod
    def get_recent_logs() -> str:
        db = SessionLocal()
        try:
            logs = db.query(SecurityLog).order_by(SecurityLog.id.desc()).limit(5).all()
            if not logs:
                return "📜 **AUDIT LOGS:** No violations recorded yet!"
            
            log_str = "📜🛡️ **LIVE AUDIT & SECURITY LOGS (LAST 5)** 🛡️📜\n\n"
            for log in logs:
                log_str += f"🔹 **User:** @{log.username} | **Type:** {log.event_type}\n"
            log_str += f"\n🤖 **BOT** ➜ @{BOT_USERNAME}"
            return log_str
        finally:
            db.close()

# ==================== MAIN BOT ENGINE ====================
def start_bot():
    init_db()
    monitor = SystemMonitor()

    while True:
        try:
            print("[*] Connecting to Instagram Server via Session ID...")
            cl = Client()
            cl.login_by_sessionid(SESSION_ID)
            print(f"[+] SUCCESS: Bot @{BOT_USERNAME} is LIVE in ULTRA PRO MAX MODE! 🚀")

            seen_message_ids = set()
            group_members_state = {}
            ever_seen_members = set()
            welcomed_recently = {}
            recent_sent_texts = {}
            last_call_broadcast = {}

            last_morning_wish_date = ""
            last_night_wish_date = ""
            is_first_run = True

            def safe_send_message(thread_id, text_content, reply_to_item_id=None):
                current_time = time.time()
                if thread_id in recent_sent_texts:
                    last_text, last_time = recent_sent_texts[thread_id]
                    if last_text == text_content and (current_time - last_time < 8):
                        return
                
                recent_sent_texts[thread_id] = (text_content, current_time)
                cl.direct_send(text_content, thread_ids=[thread_id], reply_to_item_id=reply_to_item_id)
                time.sleep(2)

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
                        bot_pk = str(cl.user_id)

                        gc_admins = []
                        admin_usernames = []
                        try:
                            if hasattr(thread, 'admin_user_ids') and thread.admin_user_ids:
                                gc_admins = [str(uid) for uid in thread.admin_user_ids]
                            
                            users_list = list(getattr(thread, "users", []) or [])
                            for u in users_list:
                                u_pk = str(getattr(u, "pk", ""))
                                u_name = getattr(u, "username", "")
                                if u_pk in gc_admins and u_name:
                                    admin_usernames.append(f"@{u_name}")
                        except Exception:
                            gc_admins = []

                        # STRICT REQUIREMENT: Bot must be Admin in GC
                        if bot_pk not in gc_admins:
                            continue

                        admin_mentions_str = " ".join(admin_usernames) if admin_usernames else "Admins"
                        users = list(getattr(thread, "users", []) or [])
                        current_members = {str(getattr(u, "pk", "")) for u in users if getattr(u, "pk", None)}

                        # Morning & Night Wishes
                        if current_hour == 6 and last_morning_wish_date != current_date_str:
                            last_morning_wish_date = current_date_str
                            morning_card = (
                                f"🌸✨ **𝗥𝗔𝗗𝗛🇪 𝗥𝗔𝗗𝗛🇪 • JAI SHRI RAM!** ✨🌸\n\n"
                                f"🌅 𝗚𝗢𝗢🇩 𝗠𝗢𝗥𝗡𝗜𝗡𝗚 𝗚𝗖 𝗙𝗔𝗠𝗜𝗟𝗬! ☕💫\n"
                                f"🙏 𝗛𝗔𝗩🇪 𝗔 𝗕𝗟🇪𝗦𝗦🇪🇩, 𝗛𝗔𝗣𝗣𝗬 & 𝗔𝗖𝗧𝗜𝗩🇪 𝗗𝗔𝗬 𝗔𝗛🇪𝗔𝗗!\n\n"
                                f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
                                f"👨‍💻 𝗗🇪𝗩𝗦 ➜ @fx_smw | @aat_nnk"
                            )
                            safe_send_message(thread_id, morning_card)

                        elif current_hour == 23 and last_night_wish_date != current_date_str:
                            last_night_wish_date = current_date_str
                            night_card = (
                                f"🌙💤 **𝗚𝗢𝗢🇩 𝗡𝗜𝗚𝗛𝗧, 𝗚𝗖 𝗙𝗔𝗠𝗜𝗟𝗬!** 🌌✨\n\n"
                                f"🛌 𝗧𝗜𝗠🇪 𝗧𝗢 𝗥🇪𝗦𝗧 & 𝗥🇪𝗖𝗛𝗔𝗥𝗚🇪!\n\n"
                                f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
                                f"👨‍💻 𝗗🇪𝗩𝗦 ➜ @fx_smw | @aat_nnk"
                            )
                            safe_send_message(thread_id, night_card)

                        # Call Reminder Broadcast
                        if thread_id not in last_call_broadcast:
                            last_call_broadcast[thread_id] = current_time_loop
                        
                        if current_time_loop - last_call_broadcast[thread_id] > CALL_REMINDER_INTERVAL:
                            last_call_broadcast[thread_id] = current_time_loop
                            call_broadcast_card = (
                                f"🔥📞 **@EVERYONE • GC CALL ALERT!** 📞🔥\n\n"
                                f"👑 𝗛🇪𝗬 𝗚𝗨𝗬𝗦, 𝗦𝗧𝗔𝗥𝗧 𝗔 𝗖𝗔𝗟𝗟 𝗢𝗥 𝗝𝗢𝗜𝗡 𝗡𝗢𝗪!\n\n"
                                f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
                                f"👨‍💻 𝗗🇪𝗩𝗦 ➜ @fx_smw | @aat_nnk"
                            )
                            safe_send_message(thread_id, call_broadcast_card)

                        # Welcome System
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
                                            safe_send_message(thread_id, f"💫 𝗪🇪𝗟𝗖𝗢𝗠🇪 𝗕𝗔𝗖𝗞 @{target_username}! 💫")
                                        else:
                                            ever_seen_members.add(joined_pk)
                                            safe_send_message(thread_id, f"🦋✨ 𝗪🇪𝗟𝗖𝗢𝗠🇪 @{target_username}! ✨🦋")
                        else:
                            ever_seen_members.update(current_members)

                        group_members_state[thread_id] = current_members

                        # Message Scanner & Moderation
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
                                is_sender_admin = sender_id in {str(x) for x in gc_admins}
                                is_sender_dev = any(dev_name.lower() in sender_username.lower() for dev_name in AUTHORIZED_DEVS)

                                ProfileEngine.record_activity(sender_id, sender_username)

                                # Moderation (Non-Admins & Non-Devs)
                                if not is_sender_admin and not is_sender_dev:
                                    mod_type, mod_msg = ModerationEngine.check_message(
                                        text, item_type, sender_id, sender_username, thread_id, admin_mentions_str
                                    )
                                    if mod_msg:
                                        safe_send_message(thread_id, mod_msg, reply_to_item_id=message_id)
                                        continue

                                # ================= PUBLIC COMMANDS =================
                                if text_lower == "!rules":
                                    rules_card = (
                                        f"📜🛡️ **𝗚𝗖 𝗢𝗙𝗙𝗜𝗖𝗜𝗔𝗟 𝗥𝗨𝗟🇪𝗦 & 𝗚𝗨𝗜𝗗🇪𝗟𝗜𝗡🇪𝗦** 🛡️📜\n\n"
                                        f"1️⃣ 🚫 **𝗡𝗢 𝗔𝗕𝗨𝗦𝗜𝗩🇪 𝗟𝗔𝗡𝗚𝗨𝗔𝗚🇪** (Strict Action)\n"
                                        f"2️⃣ 🚫 **𝗡𝗢 𝗨𝗡𝗔𝗨𝗧𝗛𝗢𝗥𝗜𝗦🇪𝗗 𝗟𝗜𝗡𝗞𝗦** (Spam Restricted)\n"
                                        f"3️⃣ 🚫 **𝗡𝗢 𝗥🇪🇪𝗟𝗦 / 𝗠🇪𝗗𝗜𝗔 𝗦𝗣𝗔𝗠𝗠𝗜𝗡𝗚**\n"
                                        f"4️⃣ 👑 **𝗥🇪𝗦𝗣🇪𝗖𝗧 𝗔𝗟𝗟 𝗔𝗗𝗠𝗜𝗡𝗦 & 𝗠🇪𝗠𝗕🇪𝗥𝗦**\n\n"
                                        f"🤖 **𝗠𝗢𝗗🇪𝗥𝗔𝗧🇪𝗗 𝗕𝗬** ➜ @{BOT_USERNAME}"
                                    )
                                    safe_send_message(thread_id, rules_card, reply_to_item_id=message_id)

                                elif text_lower.startswith("!stats"):
                                    parts = text.split()
                                    target_user = parts[1] if len(parts) > 1 else f"@{sender_username}"
                                    stats_msg = ProfileEngine.get_user_stats(target_user)
                                    safe_send_message(thread_id, stats_msg, reply_to_item_id=message_id)

                                elif text_lower == "!botinfo":
                                    info_card = (
                                        f"⚡👑 **𝗣𝗢𝗢𝗞𝗜𝗘🇪🇪 𝗕𝗢𝗧** 👑⚡\n\n"
                                        f"🛡️ **𝗠𝗢𝗗🇪 ➜** AUTOMATIC STRICT MODERATION\n"
                                        f"⚡ **𝗔𝗨𝗥𝗔 ➜** UNTOUCHABLE & SUPREME\n\n"
                                        f"👨‍💻 **𝗖𝗥🇪𝗔𝗧𝗢𝗥𝗦** ➜ @fx_smw & @aat_nnk"
                                    )
                                    safe_send_message(thread_id, info_card, reply_to_item_id=message_id)

                                elif "@everyone" in text_lower or bot_tag in text_lower:
                                    safe_send_message(thread_id, f"👋 𝗛🇪𝗟𝗟𝗢 @{sender_username}! 🤖 𝗕𝗢𝗧 𝗜𝗦 𝗔𝗖𝗧𝗜𝗩🇪!", reply_to_item_id=message_id)

                                # ================= DEVELOPER ONLY COMMANDS (YOU & YOUR FRIEND) =================
                                if is_sender_dev:
                                    if text_lower == "!health":
                                        safe_send_message(thread_id, monitor.get_health_report(), reply_to_item_id=message_id)

                                    elif text_lower == "!logs":
                                        safe_send_message(thread_id, SystemMonitor.get_recent_logs(), reply_to_item_id=message_id)

                                    elif text_lower.startswith("!userinfo"):
                                        parts = text.split()
                                        if len(parts) > 1:
                                            target_username = parts[1].lstrip('@')
                                            try:
                                                user_id_target = cl.user_id_from_username(target_username)
                                                info = cl.user_info(user_id_target)

                                                info_card = (
                                                    f"🕵️‍♂️🔍 **𝗜𝗡𝗦𝗧𝗔𝗚𝗥𝗔𝗠 𝗨𝗦🇪𝗥 𝗜𝗡𝗙𝗢 🇪𝗫𝗧𝗥𝗔𝗖𝗧𝗢𝗥** 🔍🕵️‍♂️\n\n"
                                                    f"👑 **𝗔𝗖𝗖🇪𝗦𝗦** ➜ DEVELOPERS ONLY (CONFIDENTIAL)\n\n"
                                                    f"👤 **𝗙𝗨𝗟𝗟 𝗡𝗔𝗠🇪** ➜ {info.full_name or 'N/A'}\n"
                                                    f"🆔 **𝗨𝗦🇪𝗥𝗡𝗔𝗠🇪** ➜ @{info.username}\n"
                                                    f"👥 **𝗙𝗢𝗟𝗟𝗢𝗪🇪𝗥𝗦** ➜ {info.follower_count:,}\n"
                                                    f"🔄 **𝗙𝗢𝗟𝗟𝗢𝗪𝗜𝗡𝗚** ➜ {info.following_count:,}\n"
                                                    f"📸 **𝗧𝗢𝗧𝗔𝗟 𝗣𝗢𝗦𝗧𝗦** ➜ {info.media_count:,}\n"
                                                    f"🔐 **𝗣𝗥𝗜𝗩𝗔𝗧🇪 𝗔𝗖𝗖𝗢𝗨𝗡𝗧** ➜ {'YES 🔒' if info.is_private else 'NO 🔓'}\n"
                                                    f"📝 **𝗕𝗜𝗢** ➜ {info.biography or 'No Bio'}\n\n"
                                                    f"🖼️ **𝗛𝗗 𝗣𝗥𝗢𝗙𝗜𝗟🇪 𝗣𝗜𝗖** ➜ {info.profile_pic_url_hd}\n\n"
                                                    f"🤖 **𝗕𝗢𝗧** ➜ @{BOT_USERNAME}"
                                                )
                                                safe_send_message(thread_id, info_card, reply_to_item_id=message_id)

                                            except Exception:
                                                safe_send_message(thread_id, f"❌ @{target_username} की डिटेल्स निकालने में एरर आया या अकाउंट मौजूद नहीं है!", reply_to_item_id=message_id)
                                        else:
                                            safe_send_message(thread_id, "⚠️ **Command Syntax:** `!userinfo @username`", reply_to_item_id=message_id)

                                    elif text_lower.startswith("!addword"):
                                        parts = text.split(maxsplit=1)
                                        if len(parts) > 1:
                                            new_word = parts[1].strip().lower()
                                            RESTRICTED_WORDS.add(new_word)
                                            safe_send_message(thread_id, f"✅ **Word Added to Blocklist:** `{new_word}`", reply_to_item_id=message_id)

                                    elif text_lower.startswith("!delword"):
                                        parts = text.split(maxsplit=1)
                                        if len(parts) > 1:
                                            rem_word = parts[1].strip().lower()
                                            RESTRICTED_WORDS.discard(rem_word)
                                            safe_send_message(thread_id, f"🗑️ **Word Removed from Blocklist:** `{rem_word}`", reply_to_item_id=message_id)

                                    elif text_lower.startswith("!kick") or text_lower.startswith("!ban"):
                                        parts = text.split()
                                        if len(parts) > 1:
                                            target_name = parts[1].lstrip('@')
                                            target_user_obj = next((u for u in users if getattr(u, "username", "").lower() == target_name.lower()), None)
                                            if target_user_obj:
                                                kick_pk = getattr(target_user_obj, "pk", "")
                                                cl.user_remove_from_thread(thread_id, kick_pk)
                                                safe_send_message(thread_id, f"⚡🚫 **USER REMOVED!** @{target_name} has been kicked by Developer Power!")
                                            else:
                                                safe_send_message(thread_id, f"❌ User @{target_name} not found in this GC!")

                    is_first_run = False

                except (PleaseWaitFewMinutes, ClientThrottledError) as rate_err:
                    print(f"[RATE LIMIT] Waiting 60s: {rate_err}")
                    time.sleep(60)

                except (LoginRequired, ChallengeRequired) as session_err:
                    print(f"[-] SESSION EXPIRED: {session_err}")
                    raise session_err

                except Exception as inner_e:
                    print(f"[LOOP WARNING] {inner_e}")
                    time.sleep(5)

                time.sleep(POLL_INTERVAL)

        except Exception as outer_e:
            print(f"[-] RECONNECTING... Waiting 30s: {outer_e}")
            time.sleep(30)

if __name__ == "__main__":
    start_bot()

