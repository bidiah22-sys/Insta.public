
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

INSTAGRAM_USERNAME = os.getenv("INSTAGRAM_USERNAME", "bot0.0928")
INSTAGRAM_PASSWORD = os.getenv("INSTAGRAM_PASSWORD", "SIDHU295")

BOT_USERNAME = os.getenv("BOT_USERNAME", "pookieee_bot")
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "fx_smw ✘ aat_nnk25")

AUTHORIZED_DEVS = ["fx_smw", "aat_nnk", "aat_nnk25", "fx_sw"]
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///bot_database.db")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", 25))

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

SPAM_USERNAME_PATTERNS = [
    r'bot[0-9_\.]*', r'crypto[0-9_\.]*', r'promo[0-9_\.]*', r'followers[0-9_\.]*',
    r'18plus', r'adult', r'earn_money', r'trader[0-9_\.]*'
]

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

class SpamAnalyzer:
    @staticmethod
    def is_spam_profile(cl: Client, username: str) -> tuple:
        try:
            u_info = cl.user_info_by_username(username)
            risk = 0
            reasons = []

            u_lower = username.lower()
            for pattern in SPAM_USERNAME_PATTERNS:
                if re.search(pattern, u_lower):
                    risk += 40
                    reasons.append("Suspicious Username Pattern")
                    break

            bio = (u_info.biography or "").lower()
            if any(w in bio for w in ['whatsapp', 'telegram', 'free followers', 'crypto', 'dm for paid', '18+']):
                risk += 35
                reasons.append("Spam Bio Content")

            if u_info.follower_count < 10 and u_info.following_count > 200:
                risk += 30
                reasons.append("Abnormal Following Ratio")

            is_spam = risk >= 50
            reason_str = ", ".join(reasons) if reasons else "Clean Profile"
            return is_spam, reason_str, min(risk, 100), u_info
        except Exception:
            return False, "Could not scan", 0, None

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

    SESSION_FILE = "session.json"

    while True:
        try:
            print("[*] Connecting to Instagram Engine with Device Spoofing...")
            cl = Client()
            cl.set_user_agent("Mozilla/5.0 (Linux; Android 11; SM-G998B Build/RP1A.200720.012; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/115.0.5790.166 Mobile Safari/537.36 Instagram 290.0.0.13.76 Android")

            if os.path.exists(SESSION_FILE):
                try:
                    print("[+] Existing session file found. Loading session...")
                    cl.load_settings(SESSION_FILE)
                    cl.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
                    print("[+] Successfully logged in using Session File!")
                except Exception as e:
                    print(f"[!] Session expired or invalid ({e}). Logging in fresh with Username/Password...")
                    cl.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
                    cl.dump_settings(SESSION_FILE)
                    print("[+] New Session saved to 'session.json'!")
            else:
                print("[+] First time login: Using Username and Password...")
                cl.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
                cl.dump_settings(SESSION_FILE)
                print("[+] New Session successfully saved to 'session.json'!")

            print(f"[+] SUCCESS: Bot @{BOT_USERNAME} FULLY LOADED & ACTIVE! 🚀⚡")

            seen_message_ids = set()
            group_members_state = {}
            ever_seen_members = set()
            welcomed_recently = {}
            recent_sent_texts = {}

            last_morning_wish_date = ""
            last_night_wish_date = ""
            is_first_run = True

            def safe_send_message(thread_id, text_content):
                current_time = time.time()
                if thread_id in recent_sent_texts:
                    last_text, last_time = recent_sent_texts[thread_id]
                    if last_text == text_content and (current_time - last_time < 3):
                        return
                recent_sent_texts[thread_id] = (text_content, current_time)
                cl.direct_send(text_content, thread_ids=[thread_id])
                time.sleep(2)

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
                    current_time_loop = time.time()

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
                        current_members = {str(getattr(u, "pk", "")) for u in users if getattr(u, "pk", None)}

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
                                        
                                        is_spam, spam_reason, risk_score, _ = SpamAnalyzer.is_spam_profile(cl, target_username)

                                        if is_spam:
                                            spam_card = (
                                                f"🚨🛡️ **𝗦𝗣𝗔𝗠 𝗕𝗢𝗧 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗!**\n\n"
                                                f"👤 𝗨𝗦𝗘𝗥 ➜ {fix_mention(target_username)}\n"
                                                f"⚠️ 𝗥𝗜𝗦𝗞 𝗦𝗖𝗢𝗥𝗘 ➜ {risk_score}%\n"
                                                f"🛑 𝗥𝗘𝗔𝗦𝗢𝗡 ➜ {spam_reason}\n"
                                                f"🚫 𝗔𝗖𝗧𝗜𝗢𝗡 ➜ Instantly Kicked for GC Safety!\n\n"
                                                f"📢 **𝗔𝗗𝗠𝗜𝗡 𝗔𝗟𝗘𝗥𝗧** ➜ {admin_mentions_tag}\n\n"
                                                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                                f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
                                            )
                                            safe_send_message(thread_id, spam_card)
                                            execute_kick(thread_id, joined_pk, target_username, f"SPAM BOT DETECTED ({spam_reason})", silent=True)
                                            continue

                                        if joined_pk in ever_seen_members:
                                            welcome_back_card = (  
                                                f"💫🦋 𝗪𝗘𝗟𝗖𝗢𝗠𝗘 𝗕𝗔𝗖𝗞, {fix_mention(target_username)}! 🦋💫\n\n"  
                                                f"🌷 𝗧𝗛𝗘 𝗚𝗖 𝗙𝗘𝗟𝗧 𝗬𝗢𝗨𝗥 𝗔𝗕𝗦𝗘𝗡𝗖𝗘 😌\n"  
                                                f"🔥 𝗕𝗔𝗖𝗞 𝗔𝗚𝗔𝗜𝗡 • 𝗦𝗧𝗔𝗬 𝗔𝗖𝗧𝗜𝗩𝗘\n"  
                                                f"📜 𝗙𝗢𝗟𝗟𝗢𝗪 𝗧𝗛𝗘 𝗥𝗨𝗟𝗘𝗦 & 𝗘𝗡𝗝𝗢𝗬!\n\n"  
                                                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"  
                                                f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"  
                                            )
                                            safe_send_message(thread_id, welcome_back_card)
                                        else:
                                            ever_seen_members.add(joined_pk)
                                            welcome_card = (  
                                                f"🦋✨ 𝗪𝗘𝗟𝗖𝗢𝗠𝗘, {fix_mention(target_username)}! ✨🦋\n\n"  
                                                f"🌸 𝗛𝗘𝗬! 𝗚𝗟𝗔𝗗 𝗧𝗢 𝗛𝗔𝗩𝗘 𝗬𝗢𝗨 𝗛𝗘𝗥𝗘 💫\n"  
                                                f"🤝 𝗦𝗧𝗔𝗬 𝗥𝗘𝗦𝗣𝗘𝗖𝗧𝗙𝗨𝗟 • 𝗙𝗢𝗟𝗟𝗢𝗪 𝗧𝗛𝗘 𝗥𝗨𝗟𝗘𝗦\n"  
                                                f"🔥 𝗘𝗡𝗝𝗢𝗬 𝗧𝗛𝗘 𝗚𝗖 & 𝗦𝗧𝗔𝗬 𝗔𝗖𝗧𝗜𝗩𝗘!\n\n"  
                                                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"  
                                                f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"  
                                            )
                                            safe_send_message(thread_id, welcome_card)
                        else:
                            ever_seen_members.update(current_members)

                        group_members_state[thread_id] = current_members

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

                    is_first_run = False

                except (LoginRequired, ChallengeRequired):
                    print("[!] Session Expired! Resetting session.json...")
                    if os.path.exists(SESSION_FILE):
                        os.remove(SESSION_FILE)
                    time.sleep(30)
                    break
                except (PleaseWaitFewMinutes, ClientThrottledError):
                    print("[!] Rate Limited by Instagram! Sleeping for 2 minutes...")
                    time.sleep(120)
                except Exception as e:
                    print(f"[!] Error in loop: {e}")
                    time.sleep(POLL_INTERVAL)

                time.sleep(POLL_INTERVAL)

        except Exception as e:
            print(f"[!] Critical Error: {e}")
            time.sleep(30)

if __name__ == "__main__":
    start_bot()
"@ | Out-File -FilePath "bot.py" -Encoding utf8; python bot.py
