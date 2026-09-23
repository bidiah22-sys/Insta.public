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

load_dotenv()

# ==================== CONFIGURATION ====================
SESSION_ID = os.getenv("SESSION_ID", "7207590267%3AOzEdEpuYJTJj6t%3A20%3AAYkMaEgKhgBcicgwWniTeXrUH-O3FDT_4s5sepDRtQ")
BOT_USERNAME = os.getenv("BOT_USERNAME", "smw_vyron_bot")

OWNER_1 = "fx_smw"
OWNER_2 = "aat_nnk"
AUTHORIZED_DEVS = ["fx_smw", "aat_nnk"]

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///bot_database.db")
CALL_REMINDER_INTERVAL = int(os.getenv("CALL_REMINDER_INTERVAL", 3600))
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", 4))

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

# ==================== ENGINES ====================
class ProfileEngine:
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
    def get_user_stats(username: str) -> str:
        db = SessionLocal()
        try:
            clean_user = username.lstrip('@').lower()
            profile = db.query(UserProfile).filter(UserProfile.username == clean_user).first()
            if profile:
                return (
                    f"👑━━━━━━━━━━━━━━━━━━━━━━👑\n"
                    f"   🔥 𝗣𝗢𝗢𝗞𝗜🇪🇪 𝗨𝗟𝗧𝗥𝗔 𝗦𝗧𝗔𝗧𝗦 🔥\n"
                    f"👑━━━━━━━━━━━━━━━━━━━━━━👑\n\n"
                    f"👤 **𝗨𝗦🇪𝗥𝗡𝗔𝗠🇪** ➜ @{profile.username}\n"
                    f"🆔 **𝗨𝗦🇪𝗥 𝗜🇩** ➜ `{profile.user_id}`\n"
                    f"💬 **𝗧𝗢𝗧𝗔𝗟 𝗠𝗦𝗚𝗦** ➜ {profile.total_messages}\n"
                    f"⚠️ **𝗪𝗔𝗥𝗡𝗜𝗡𝗚𝗦** ➜ {profile.warning_count}/3\n"
                    f"🚫 **𝗩𝗜𝗢𝗟𝗔𝗧𝗜𝗢𝗡𝗦** ➜ {profile.violation_count}\n"
                    f"💎 **𝗧𝗥𝗨𝗦𝗧 𝗦𝗖𝗢𝗥🇪** ➜ {profile.trust_score}%\n\n"
                    f"🤖 **𝗕𝗢𝗧** ➜ @{BOT_USERNAME}\n"
                    f"👨‍💻 **𝗗🇪𝗩𝗦** ➜ @fx_smw | @aat_nnk"
                )
            return f"❌ User @{clean_user} is not yet registered in Database!"
        finally:
            db.close()

    @staticmethod
    def log_violation(group_id: str, username: str, v_type: str, details: str):
        db = SessionLocal()
        try:
            log = SecurityLog(group_id=group_id, username=username, event_type=v_type, details=details)
            db.add(log)
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

class SystemMonitor:
    def __init__(self):
        self.start_time = time.time()

    def get_health_report(self) -> str:
        uptime_sec = int(time.time() - self.start_time)
        hours, remainder = divmod(uptime_sec, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        return (
            f"⚡━━━━━━━━━━━━━━━━━━━━━━⚡\n"
            f"   📊 𝗦𝗬𝗦𝗧🇪𝗠 𝗛🇪𝗔𝗟𝗧𝗛 & 𝗨𝗣𝗧𝗜𝗠🇪 📊\n"
            f"⚡━━━━━━━━━━━━━━━━━━━━━━⚡\n\n"
            f"🟢 𝗦𝗧𝗔𝗧𝗨𝗦 ➜ ONLINE & OPTIMIZED\n"
            f"⏱️ 𝗨𝗣𝗧𝗜𝗠🇪 ➜ {hours}h {minutes}m {seconds}s\n"
            f"💻 𝗖𝗣𝗨 𝗟𝗢𝗔𝗗 ➜ {psutil.cpu_percent()}%\n"
            f"🧠 𝗥𝗔𝗠 𝗨𝗦𝗔𝗚🇪 ➜ {psutil.virtual_memory().percent}%\n\n"
            f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
            f"👨‍💻 𝗗🇪𝗩𝗦 ➜ @fx_smw | @aat_nnk"
        )

    @staticmethod
    def get_recent_logs() -> str:
        db = SessionLocal()
        try:
            logs = db.query(SecurityLog).order_by(SecurityLog.id.desc()).limit(5).all()
            if not logs:
                return "📜 **AUDIT LOGS:** No violations recorded in Database!"
            
            log_str = "📜🛡️ **LIVE AUDIT & SECURITY LOGS** 🛡️📜\n\n"
            for log in logs:
                log_str += f"🔹 **User:** @{log.username} | **Type:** {log.event_type}\n"
            log_str += f"\n🤖 **BOT** ➜ @{BOT_USERNAME}"
            return log_str
        finally:
            db.close()

# ==================== MAIN ENGINE ====================
def start_bot():
    init_db()
    monitor = SystemMonitor()

    while True:
        try:
            print("[*] Connecting to Instagram...")
            cl = Client()
            cl.login_by_sessionid(SESSION_ID)
            print(f"[+] SUCCESS: Bot @{BOT_USERNAME} is ONLINE!")

            seen_message_ids = set()
            recent_sent_texts = {}
            user_spam_tracker = {}  # {user_id: [timestamp1, timestamp2, ...]}

            def safe_send(thread_id, text_content):
                c_time = time.time()
                if thread_id in recent_sent_texts:
                    l_text, l_time = recent_sent_texts[thread_id]
                    if l_text == text_content and (c_time - l_time < 8):
                        return
                recent_sent_texts[thread_id] = (text_content, c_time)
                cl.direct_send(text_content, thread_ids=[thread_id])
                time.sleep(2)

            def execute_kick(thread_id, target_pk, target_username, reason):
                try:
                    cl.user_remove_from_thread(thread_id, target_pk)
                    kick_card = (
                        f"🚨⚡━━━━━━━━━━━━━━━━━━━━━━⚡🚨\n"
                        f"   🚫 **𝗜𝗡𝗦𝗧𝗔𝗡𝗧 𝗔𝗨𝗧𝗢-𝗞𝗜𝗖𝗞 𝗔𝗟🇪𝗥𝗧** 🚫\n"
                        f"🚨⚡━━━━━━━━━━━━━━━━━━━━━━⚡🚨\n\n"
                        f"👤 **𝗢𝗙𝗙🇪𝗡🇩🇪𝗥** ➜ @{target_username}\n"
                        f"🆔 **𝗨𝗦🇪𝗥 𝗜🇩** ➜ `{target_pk}`\n"
                        f"🚫 **𝗩𝗜𝗢𝗟𝗔𝗧𝗜𝗢𝗡** ➜ {reason}\n"
                        f"🛑 **𝗔𝗖𝗧𝗜𝗢𝗡** ➜ KICKED FROM GC IMMEDIATELY!\n\n"
                        f"💬 **𝗣𝗢𝗟𝗜𝗖𝗬** ➜ Zero Tolerance Strict Mode\n\n"
                        f"🤖 **𝗕𝗢𝗧** ➜ @{BOT_USERNAME}\n"
                        f"👨‍💻 **𝗗🇪𝗩𝗦** ➜ @fx_smw | @aat_nnk"
                    )
                    safe_send(thread_id, kick_card)
                    ProfileEngine.log_violation(thread_id, target_username, "AUTO-KICK", reason)
                except Exception as e:
                    safe_send(thread_id, f"❌ Failed to Kick @{target_username}! Check if Bot is GC Admin.")

            while True:
                try:
                    threads = cl.direct_threads(amount=2)

                    for thread in threads:
                        if not getattr(thread, "is_group", False):
                            continue

                        thread_id = thread.id
                        bot_pk = str(cl.user_id)

                        gc_admins = []
                        try:
                            if hasattr(thread, 'admin_user_ids') and thread.admin_user_ids:
                                gc_admins = [str(uid) for uid in thread.admin_user_ids]
                        except Exception:
                            gc_admins = []

                        users = list(getattr(thread, "users", []) or [])
                        
                        # Auto DB Sync
                        for u in users:
                            if getattr(u, "pk", None) and getattr(u, "username", None):
                                ProfileEngine.record_activity(str(u.pk), u.username)

                        messages = list(getattr(thread, "messages", []) or [])
                        if messages:
                            last_msg = messages[0]
                            msg_id = str(getattr(last_msg, "id", ""))

                            if msg_id and msg_id not in seen_message_ids:
                                seen_message_ids.add(msg_id)
                                text = str(getattr(last_msg, "text", "") or "").strip()
                                text_lower = text.lower()
                                sender_id = str(getattr(last_msg, "user_id", ""))
                                item_type = str(getattr(last_msg, 'item_type', '') or '')

                                if sender_id == bot_pk:
                                    continue

                                sender_username = "user"
                                for u in users:
                                    if str(getattr(u, "pk", "")) == sender_id:
                                        sender_username = getattr(u, "username", "user")
                                        break

                                is_admin = sender_id in gc_admins
                                is_dev = sender_username.lower() in [d.lower() for d in AUTHORIZED_DEVS]

                                ProfileEngine.record_activity(sender_id, sender_username)

                                # ================= AUTO-KICK MODERATION (For Non-Admins & Non-Devs) =================
                                if not is_admin and not is_dev:
                                    current_t = time.time()
                                    
                                    # 1. Anti-Spam Rate Detector (4+ msgs in 5 sec)
                                    if sender_id not in user_spam_tracker:
                                        user_spam_tracker[sender_id] = []
                                    user_spam_tracker[sender_id].append(current_t)
                                    user_spam_tracker[sender_id] = [t for t in user_spam_tracker[sender_id] if current_t - t < 5]

                                    if len(user_spam_tracker[sender_id]) >= 4:
                                        execute_kick(thread_id, sender_id, sender_username, "LOUD MESSAGE SPAMMING")
                                        continue

                                    # 2. Profanity Check -> INSTANT KICK
                                    if any(word in text_lower for word in RESTRICTED_WORDS):
                                        execute_kick(thread_id, sender_id, sender_username, "ABUSIVE / PROFANITY LANGUAGE")
                                        continue

                                    # 3. Link Detection -> INSTANT KICK
                                    if any(domain in text_lower for domain in ['http://', 'https://', 'www.', '.com', 't.me', 'instagram.com/']):
                                        execute_kick(thread_id, sender_id, sender_username, "UNAUTHORIZED LINK SPAM")
                                        continue

                                    # 4. Media/Reels Spam -> INSTANT KICK
                                    if item_type in ['clip', 'media', 'video', 'visual_media', 'felix_share', 'story_share'] or '/reel/' in text_lower:
                                        execute_kick(thread_id, sender_id, sender_username, "REELS / MEDIA SPAM")
                                        continue

                                # ================= PUBLIC COMMANDS =================
                                if text_lower == "!botinfo":
                                    info_card = (
                                        f"⚡👑 **𝗣𝗢𝗢𝗞𝗜🇪🇪 𝗕𝗢𝗧** 👑⚡\n\n"
                                        f"🛡️ **𝗠𝗢𝗗🇪 ➜** AUTO STRICT ZERO-TOLERANCE MODERATION\n"
                                        f"⚡ **𝗔𝗨𝗥𝗔 ➜** SUPREME GC GUARDIAN\n\n"
                                        f"🤖 **𝗕𝗢𝗧** ➜ @{BOT_USERNAME}\n"
                                        f"👨‍💻 **𝗖𝗥🇪𝗔𝗧𝗢𝗥𝗦** ➜ @fx_smw & @aat_nnk"
                                    )
                                    safe_send(thread_id, info_card)

                                elif text_lower == "!rules":
                                    rules_card = (
                                        f"⚡━━━━━━━━━━━━━━━━━━━━━━⚡\n"
                                        f"   📜 𝗢𝗙𝗙𝗜𝗖𝗜𝗔𝗟 𝗚𝗖 𝗥𝗨𝗟🇪𝗦 & 𝗟𝗔𝗪𝗦 📜\n"
                                        f"⚡━━━━━━━━━━━━━━━━━━━━━━⚡\n\n"
                                        f"1️⃣ 🚫 **𝗡𝗢 𝗔𝗕𝗨𝗦𝗜𝗩🇪 𝗟𝗔𝗡𝗚𝗨𝗔𝗚🇪** (Instant Auto-Kick)\n"
                                        f"2️⃣ 🚫 **𝗡𝗢 𝗟𝗜𝗡𝗞𝗦 / 𝗦𝗣𝗔𝗠𝗠𝗜𝗡𝗚** (Instant Auto-Kick)\n"
                                        f"3️⃣ 🚫 **𝗡𝗢 𝗥🇪🇪𝗟𝗦 / 𝗠🇪🇩𝗜𝗔 𝗙𝗟𝗢𝗢𝗗** (Instant Auto-Kick)\n"
                                        f"4️⃣ 👑 **𝗥🇪𝗦𝗣🇪𝗖𝗧 𝗔𝗟𝗟 𝗔𝗗𝗠𝗜𝗡𝗦**\n\n"
                                        f"🤖 **𝗕𝗢𝗧** ➜ @{BOT_USERNAME}\n"
                                        f"👨‍💻 **𝗗🇪𝗩𝗦** ➜ @fx_smw | @aat_nnk"
                                    )
                                    safe_send(thread_id, rules_card)

                                elif text_lower.startswith("!stats"):
                                    parts = text.split()
                                    target_user = parts[1] if len(parts) > 1 else f"@{sender_username}"
                                    safe_send(thread_id, ProfileEngine.get_user_stats(target_user))

                                elif text_lower.startswith("!userinfo"):
                                    parts = text.split()
                                    if len(parts) > 1:
                                        target_name = parts[1].lstrip('@')
                                        try:
                                            u_info = cl.user_info_by_username(target_name)
                                            info_str = (
                                                f"👑━━━━━━━━━━━━━━━━━━━━━━👑\n"
                                                f"   🔥 𝗜𝗡𝗦𝗧𝗔𝗚𝗥𝗔𝗠 𝗟𝗜𝗩🇪 𝗜𝗡𝗙𝗢 🔥\n"
                                                f"👑━━━━━━━━━━━━━━━━━━━━━━👑\n\n"
                                                f"👤 **𝗨𝗦🇪𝗥𝗡𝗔𝗠🇪** ➜ @{u_info.username}\n"
                                                f"📛 **𝗙𝗨𝗟𝗟 𝗡𝗔𝗠🇪** ➜ {u_info.full_name}\n"
                                                f"🆔 **𝗜🇩** ➜ `{u_info.pk}`\n"
                                                f"👥 **𝗙𝗢𝗟𝗟𝗢𝗪🇪𝗥𝗦** ➜ {u_info.follower_count}\n"
                                                f"🔄 **𝗙𝗢𝗟𝗟𝗢𝗪𝗜𝗡𝗚** ➜ {u_info.following_count}\n"
                                                f"📝 **𝗕𝗜𝗢** ➜ {u_info.biography}\n"
                                                f"🔒 **𝗣𝗥𝗜𝗩𝗔𝗧🇪** ➜ {u_info.is_private}\n\n"
                                                f"🤖 **𝗕𝗢𝗧** ➜ @{BOT_USERNAME}\n"
                                                f"👨‍💻 **𝗗🇪𝗩𝗦** ➜ @fx_smw | @aat_nnk"
                                            )
                                            safe_send(thread_id, info_str)
                                        except Exception:
                                            safe_send(thread_id, f"❌ Failed to fetch live data for @{target_name}!")
                                    else:
                                        safe_send(thread_id, "⚠️ **Usage:** `!userinfo @username`")

                                # ================= DEVELOPER / ADMIN COMMANDS =================
                                if is_dev or is_admin:
                                    if text_lower == "!health":
                                        safe_send(thread_id, monitor.get_health_report())

                                    elif text_lower == "!logs":
                                        safe_send(thread_id, SystemMonitor.get_recent_logs())

                                    elif text_lower.startswith("!kick"):
                                        parts = text.split()
                                        if len(parts) > 1:
                                            target_name = parts[1].lstrip('@')
                                            target_obj = next((u for u in users if getattr(u, "username", "").lower() == target_name.lower()), None)
                                            if target_obj:
                                                execute_kick(thread_id, str(getattr(target_obj, "pk")), target_name, "MANUAL ADMIN/DEV KICK")
                                            else:
                                                safe_send(thread_id, f"❌ User @{target_name} not found in GC!")

                                    elif text_lower.startswith("!addword"):
                                        parts = text.split(maxsplit=1)
                                        if len(parts) > 1:
                                            RESTRICTED_WORDS.add(parts[1].strip().lower())
                                            safe_send(thread_id, f"✅ Word added to Blocklist: `{parts[1].strip()}`")

                                    elif text_lower.startswith("!delword"):
                                        parts = text.split(maxsplit=1)
                                        if len(parts) > 1:
                                            RESTRICTED_WORDS.discard(parts[1].strip().lower())
                                            safe_send(thread_id, f"🗑️ Word removed from Blocklist: `{parts[1].strip()}`")

                except (PleaseWaitFewMinutes, ClientThrottledError):
                    time.sleep(60)
                except Exception as loop_e:
                    time.sleep(POLL_INTERVAL)

                time.sleep(POLL_INTERVAL)

        except Exception as outer_e:
            time.sleep(30)

if __name__ == "__main__":
    start_bot()

