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

# ==================== CONFIGURATION ====================
SESSION_ID = ("28257191991%3AZBIY8kRKZ8g29Y%3A9%3AAYmOivsBEoI2sGbJl5rnF715VPYNJ_s2dbEGmwcmSw")
BOT_USERNAME = os.getenv("BOT_USERNAME", "pookieee_bot")
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "fx_smw ✘ @aat_nnk25")

# Dev Usernames List
AUTHORIZED_DEVS = ["fx_smw", "aat_nnk", "aat_nnk25", "fx_sw"]
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///bot_database.db")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", 2))
CALL_REMINDER_INTERVAL = 3600  # 1 Hour

SHADOWBANNED_USERS = set()
TARGETED_USERS = set()
LOCKDOWN_MODE = False

def fix_mention(username: str) -> str:
    """यूजरनेम में ऑटोमैटिकली @ लगाता है और स्पेस/क्लीन करता है"""
    if not username:
        return ""
    clean_name = str(username).strip().lstrip('@')
    return f"@{clean_name}" if clean_name else ""

def get_admin_mentions_str(users: list, gc_admins: list) -> str:
    """GC के सभी एडमिन्स को टैग करने के लिए स्ट्रिंग जनरेट करता है"""
    admin_ids_str = {str(x) for x in gc_admins}
    admin_mentions = []
    for u in users:
        u_pk = str(getattr(u, "pk", ""))
        if u_pk in admin_ids_str:
            uname = getattr(u, "username", None)
            if uname:
                admin_mentions.append(fix_mention(uname))
    return " ".join(admin_mentions) if admin_mentions else "@Admins"

# Regex Patterns for Spam, Bad Words, and Links/Reels
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

# ==================== SPAM & PROFILE ANALYZER ====================
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

# ==================== MAIN GOD ENGINE ====================
def start_bot():
    global LOCKDOWN_MODE, SHADOWBANNED_USERS, TARGETED_USERS
    init_db()

    while True:
        try:
            print("[*] Connecting to Instagram Engine...")
            cl = Client()
            cl.login_by_sessionid(SESSION_ID.strip())
            print(f"[+] SUCCESS: Bot @{BOT_USERNAME} FULLY LOADED & ACTIVE! 🚀⚡")

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
                    if last_text == text_content and (current_time - last_time < 3):
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
                        bot_tag = fix_mention(BOT_USERNAME).lower()

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

                        # 1. MORNING & NIGHT WISH CARDS
                        if current_hour == 6 and last_morning_wish_date != current_date_str:
                            last_morning_wish_date = current_date_str
                            morning_card = (
                                f"🌸✨ **𝗥𝗔𝗗𝗛𝗘 𝗥𝗔𝗗𝗛𝗘 • JAI SHRI RAM!** ✨🌸\n\n"
                                f"🌅 𝗚𝗢𝗢𝗗 𝗠𝗢𝗥𝗡𝗜𝗡𝗚 𝗚𝗖 𝗙𝗔𝗠𝗜𝗟𝗬! ☕💫\n"
                                f"🙏 𝗛𝗔𝗩𝗘 𝗔 𝗕𝗟𝗘𝗦𝗦𝗘𝗗, 𝗛𝗔𝗣𝗣𝗬 & 𝗔𝗖𝗧𝗜𝗩𝗘 𝗗𝗔𝗬 𝗔𝗛𝗘𝗔𝗗!\n"
                                f"🔥 𝗟𝗘𝗧'𝗦 𝗦𝗧𝗔𝗥𝗧 𝗧𝗛𝗘 𝗗𝗔𝗬 𝗪𝗜𝗧𝗛 𝗚𝗢𝗢𝗗 𝗩𝗜𝗕𝗦!\n\n"
                                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
                            )
                            safe_send_message(thread_id, morning_card)

                        elif current_hour == 23 and last_night_wish_date != current_date_str:
                            last_night_wish_date = current_date_str
                            night_card = (
                                f"🌙💤 **𝗚𝗢𝗢𝗗 𝗡𝗜𝗚𝗛𝗧, 𝗚𝗖 𝗙𝗔𝗠𝗜𝗟𝗬!** 🌌✨\n\n"
                                f"🛌 𝗧𝗜𝗠𝗘 𝗧𝗢 𝗥𝗘𝗦𝗧 & 𝗥𝗘𝗖𝗛𝗔𝗥𝗚𝗘 𝗙𝗢𝗥 𝗧𝗢𝗠𝗢𝗥𝗥𝗢𝗪!\n"
                                f"🌟 𝗦𝗟𝗘𝗘𝗣 𝗧𝗜𝗚𝗛𝗧, 𝗦𝗪𝗘𝗘𝗧 𝗗𝗥𝗘𝗔𝗠𝗦 𝗘𝗩𝗘𝗥𝗬𝗢𝗡𝗘!\n\n"
                                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
                            )
                            safe_send_message(thread_id, night_card)

                        # 2. CALL REMINDER BROADCAST
                        if thread_id not in last_call_broadcast:
                            last_call_broadcast[thread_id] = current_time_loop
                        
                        if current_time_loop - last_call_broadcast[thread_id] > CALL_REMINDER_INTERVAL:
                            last_call_broadcast[thread_id] = current_time_loop
                            call_broadcast_card = (
                                f"🔥📞 **@EVERYONE • GC CALL ALERT!** 📞🔥\n\n"
                                f"👑 𝗛𝗘𝗬 𝗚𝗨𝗬𝗦, 𝗦𝗧𝗔𝗥𝗧 𝗔 𝗖𝗔𝗟𝗟 𝗢𝗥 𝗝𝗢𝗜𝗡 𝗡𝗢𝗪!\n"
                                f"💬 𝗟𝗘𝗧'𝗦 𝗖𝗛𝗔𝗧, 𝗩𝗜𝗕𝗘 & 𝗛𝗔𝗡𝗚𝗢𝗨𝗧 𝗧𝗢𝗚𝗘𝗧𝗛𝗘𝗥 💫\n\n"
                                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                f"👨‍💻 𝗗EV ➜ @{OWNER_USERNAME}"
                            )
                            safe_send_message(thread_id, call_broadcast_card)

                        # 3. WELCOME & WELCOME BACK CARDS WITH SPAM SCAN & AUTO ADMIN TAG
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
                                        
                                        # SPAM SCAN ON JOIN (WITH AUTO ADMIN TAG CARD)
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

                                        # WELCOME / WELCOME BACK CARDS
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

                        # 4. MESSAGE SCANNER & MODERATION
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

                                item_type = str(getattr(last_msg, 'item_type', '') or '')

                                if sender_id == bot_pk:
                                    continue

                                admin_ids_str = {str(x) for x in gc_admins}
                                is_sender_admin = sender_id in admin_ids_str
                                is_dev = sender_username.lower() in [d.lower() for d in AUTHORIZED_DEVS]

                                ModerationEngine.record_activity(sender_id, sender_username)

                                # TARGET LOCK / SHADOWBAN / LOCKDOWN KICKS
                                if sender_username.lower() in TARGETED_USERS and not is_dev and not is_sender_admin:
                                    execute_kick(thread_id, sender_id, sender_username, "LOCKED TARGET TERMINATED")
                                    continue

                                if sender_username.lower() in SHADOWBANNED_USERS and not is_dev and not is_sender_admin:
                                    execute_kick(thread_id, sender_id, sender_username, "SHADOWBANNED TARGET", silent=True)
                                    continue

                                if LOCKDOWN_MODE and not is_sender_admin and not is_dev:
                                    execute_kick(thread_id, sender_id, sender_username, "GC LOCKDOWN ENFORCEMENT")
                                    continue

                                # 5. LINKS DETECTION (WITH AUTO ADMIN TAG CARD)
                                if not is_sender_admin and not is_dev:
                                    if any(domain in text_lower for domain in ['http://', 'https://', 'www.', '.com', 't.me', 'instagram.com/']):
                                        warn_count, trust_score = ModerationEngine.add_warning(sender_username)
                                        if warn_count >= 3:
                                            execute_kick(thread_id, sender_id, sender_username, "MAX WARNS: LINK SPAM")
                                        else:
                                            link_msg = (  
                                                f"🚨🔗 𝗛𝗘𝗬 {fix_mention(sender_username)} — 𝗟𝗜𝗡𝗞 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗!\n\n"  
                                                f"⚠️ 𝗨𝗡𝗔𝗨𝗧𝗛𝗢𝗥𝗜𝗭𝗘𝗗 𝗟𝗜𝗡𝗞𝗦 𝗔𝗥𝗘 𝗡𝗢𝗧 𝗔𝗟𝗟𝗢𝗪𝗘𝗗 𝗛𝗘𝗥𝗘.\n"  
                                                f"🛑 𝗣𝗟𝗘𝗔𝗦𝗘 𝗥𝗘𝗠𝗢𝗩𝗘 𝗜𝗧 & 𝗗𝗢𝗡'𝗧 𝗥𝗘𝗣𝗘𝗔𝗧!\n"  
                                                f"⚡ 𝗥𝗘𝗣𝗘𝗔𝗧 𝗩𝗜𝗢𝗟𝗔𝗧𝗜𝗢𝗡𝗦 𝗠𝗔𝗬 𝗟𝗘𝗔𝗗 𝗧𝗢 𝗥𝗘𝗠𝗢𝗩𝗔𝗟 🚪\n\n"  
                                                f"📢 **𝗔𝗗𝗠𝗜𝗡 𝗔𝗟𝗘𝗥𝗧** ➜ {admin_mentions_tag}\n\n"
                                                f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"  
                                            )
                                            safe_send_message(thread_id, link_msg)
                                        continue

                                    # REELS DETECTION (WITH AUTO ADMIN TAG CARD)
                                    if item_type in ['clip', 'media', 'video', 'visual_media'] or '/reel/' in text_lower or '/reels/' in text_lower:
                                        warn_count, trust_score = ModerationEngine.add_warning(sender_username)
                                        if warn_count >= 3:
                                            execute_kick(thread_id, sender_id, sender_username, "MAX WARNS: REELS SPAM")
                                        else:
                                            reel_msg = (  
                                                f"🚫🎬 𝗥𝗘𝗘𝗟𝗦 𝗡𝗢𝗧 𝗔𝗟𝗟𝗢𝗪𝗘𝗗!\n\n"  
                                                f"👤 𝗨𝗦𝗘𝗥 ➜ {fix_mention(sender_username)}\n"  
                                                f"⚠️ 𝗥𝗘𝗘𝗟𝗦 / 𝗩𝗜𝗗𝗘𝗢𝗦 𝗔𝗥𝗘 𝗡𝗢𝗧 𝗔𝗟𝗟𝗢𝗪𝗘𝗗 𝗛𝗘𝗥𝗘.\n"  
                                                f"🛑 𝗣𝗟𝗘𝗔𝗦𝗘 𝗗𝗢𝗡'𝗧 𝗥𝗘𝗣𝗘𝗔𝗧!\n\n"  
                                                f"📢 **𝗔𝗗𝗠𝗜𝗡 𝗔𝗟𝗘𝗥𝗧** ➜ {admin_mentions_tag}\n\n"
                                                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"  
                                                f"👨‍💻 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ @{OWNER_USERNAME}"  
                                            )
                                            safe_send_message(thread_id, reel_msg)
                                        continue

                                    # ABUSIVE / BAD WORDS WARNING (WITH AUTO ADMIN TAG CARD)
                                    if is_abusive_text(text):
                                        warn_count, trust_score = ModerationEngine.add_warning(sender_username)
                                        if warn_count >= 3:
                                            execute_kick(thread_id, sender_id, sender_username, "MAX WARNINGS EXCEEDED (3/3)")
                                        else:
                                            adult_msg = (  
                                                f"🚨🛡️ 𝗠𝗢𝗗𝗘𝗥𝗔𝗧𝗜𝗢𝗡 𝗔𝗟𝗘𝗥𝗧!\n\n"  
                                                f"👤 𝗨𝗦𝗘𝗥 ➜ {fix_mention(sender_username)}\n"  
                                                f"🚫 𝗜𝗡𝗔𝗣𝗣𝗥𝗢𝗣𝗥𝗜𝗔𝗧𝗘 𝗠𝗘𝗗𝗜𝗔 / 𝗟𝗔𝗡𝗚𝗨𝗔𝗚𝗘 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗!\n"  
                                                f"⚠️ 𝗧𝗛𝗜𝗦 𝗖𝗢𝗡𝗧𝗘𝗡𝗧 𝗜𝗦 𝗡𝗢𝗧 𝗔𝗟𝗟𝗢𝗪𝗘𝗗 𝗜𝗡 𝗧𝗛𝗜𝗦 𝗚𝗖.\n\n"  
                                                f"📢 **𝗔𝗗𝗠𝗜𝗡 𝗔𝗟𝗘𝗥𝗧** ➜ {admin_mentions_tag}\n"  
                                                f"🔎 𝗣𝗟𝗘𝗔𝗦𝗘 𝗥𝗘𝗩𝗜𝗘𝗪 & 𝗧𝗔𝗞𝗘 𝗔𝗖𝗧𝗜𝗢𝗡.\n\n"  
                                                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"  
                                                f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"  
                                            )
                                            safe_send_message(thread_id, adult_msg)
                                        continue

                                # BOT TAG / @EVERYONE RESPONSE CARD
                                if "@everyone" in text_lower or bot_tag in text_lower:
                                    response_msg = (  
                                        f"👋 𝗛𝗘𝗟𝗟𝗢 {fix_mention(sender_username)}!\n\n"  
                                        f"🤖 𝗕𝗢𝗧 𝗜𝗦 𝗔𝗖𝗧𝗜𝗩𝗘 𝗔𝗡𝗗 𝗠𝗔𝗡𝗔𝗚𝗜𝗡𝗚 𝗧𝗛𝗘 𝗚𝗖 𝗦𝗠𝗢𝗢𝗧𝗛𝗟𝗬. 🚀\n\n"  
                                        f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"  
                                        f"👨‍💻 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ @{OWNER_USERNAME}"  
                                    )
                                    safe_send_message(thread_id, response_msg)
                                    continue

                                # ================= ALL USER & DEV COMMANDS =================
                                
                                # 📸 FIXED HD DP DOWNLOADER CARD
                                if text_lower.startswith("!dp"):
                                    parts = text.split()
                                    target_name = parts[1].lstrip('@') if len(parts) > 1 else sender_username
                                    try:
                                        safe_send_message(thread_id, f"📸 𝗙𝗘𝗧𝗖𝗛𝗜𝗡𝗚 𝗛𝗗 𝗣𝗥𝗢𝗙𝗜𝗟𝗘 𝗣𝗜𝗖 𝗙𝗢𝗥 {fix_mention(target_name)}...")
                                        
                                        try:
                                            u_info = cl.user_info_by_username(target_name)
                                        except Exception:
                                            u_id = cl.user_id_from_username(target_name)
                                            u_info = cl.user_info(u_id)

                                        dp_url = None
                                        if hasattr(u_info, 'hd_profile_pic_url_info') and u_info.hd_profile_pic_url_info:
                                            dp_url = u_info.hd_profile_pic_url_info.url
                                        elif hasattr(u_info, 'profile_pic_url_hd') and u_info.profile_pic_url_hd:
                                            dp_url = u_info.profile_pic_url_hd
                                        else:
                                            dp_url = u_info.profile_pic_url

                                        if dp_url:
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
                                            safe_send_message(thread_id, f"❌ 𝗛𝗗 𝗗𝗣 𝗨𝗡𝗔𝗩𝗔𝗜𝗟𝗔𝗕𝗟𝗘 𝗙𝗢𝗥 {fix_mention(target_name)}")
                                    except Exception:
                                        safe_send_message(thread_id, f"❌ 𝗙𝗔𝗜𝗟𝗘𝗗 𝗧𝗢 𝗙𝗘𝗧𝗖𝗛 𝗗𝗣 𝗙𝗢𝗥 {fix_mention(target_name)}!")

                                # 🎵 MUSIC PLAYER CARD
                                elif text_lower.startswith("!song"):
                                    song_query = text[5:].strip()
                                    if song_query:
                                        formatted_query = song_query.replace(' ', '+')
                                        song_url = f"http://www.youtube.com/results?search_query={formatted_query}"
                                        
                                        music_card = (
                                            f"🎵🎧 **𝗡𝗢𝗪 𝗣𝗟𝗔𝗬𝗜𝗡𝗚: {song_query.title()}** 🎧🎵\n\n"
                                            f"🎙️ 𝗦𝗢𝗨𝗥𝗖𝗘 ➜ YouTube Music HD\n"
                                            f"📊 𝗦𝗧𝗔𝗧𝗨𝗦 ➜ 🟢 Ready to Stream\n\n"
                                            f"🔗 𝗟𝗜𝗦𝗧𝗘𝗡 𝗛𝗘𝗥𝗘 ➜ {song_url}\n\n"
                                            f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                            f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
                                        )
                                        safe_send_message(thread_id, music_card)
                                    else:
                                        safe_send_message(thread_id, "💡 Usage: `!song [Song Name]`")

                                # 📜 GROUP RULES CARD
                                elif text_lower == "!rules":
                                    rules_card = (
                                        f"📜🛡️ **𝗚𝗖 𝗢𝗙𝗙𝗜𝗖𝗜𝗔𝗟 𝗥𝗨𝗟𝗘𝗦** 🛡️📜\n\n"
                                        f"1️⃣ **𝗡𝗢 𝗔𝗕𝗨𝗦𝗘** ➜ Bad words strictly forbidden.\n"
                                        f"2️⃣ **𝗡𝗢 𝗥𝗘𝗘𝗟𝗦/𝗟𝗜𝗡𝗞𝗦** ➜ Unsolicited links/reels not allowed.\n"
                                        f"3️⃣ **𝗡𝗢 𝗦𝗣𝗔𝗠𝗠𝗜𝗡𝗚** ➜ Fast spam leads to Auto-Kick.\n"
                                        f"4️⃣ **𝗥𝗘𝗦𝗣𝗘𝗖𝗧 𝗔𝗟𝗟** ➜ Treat members with respect.\n\n"
                                        f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                        f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
                                    )
                                    safe_send_message(thread_id, rules_card)

                                # 🤖 BOT INFO CARD
                                elif text_lower == "!botinfo":
                                    info_card = (
                                        f"🤖⚡ **𝗕𝗢𝗧 𝗜𝗡𝗙𝗢𝗥𝗠𝗔𝗧𝗜𝗢𝗡** ⚡🤖\n\n"
                                        f"🤖 𝗕𝗢𝗧 𝗡𝗔𝗠𝗘 ➜ {fix_mention(BOT_USERNAME)}\n"
                                        f"🛡️ 𝗦𝗘𝗖𝗨𝗥𝗜𝗧𝗬 ➜ Ultra Shield Active\n"
                                        f"🟢 𝗦𝗧𝗔𝗧𝗨𝗦   ➜ Operational\n\n"
                                        f"👨‍💻 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ @{OWNER_USERNAME}"
                                    )
                                    safe_send_message(thread_id, info_card)

                                # 📊 USER STATS CARD
                                elif text_lower.startswith("!stats"):
                                    parts = text.split()
                                    target_user = parts[1] if len(parts) > 1 else sender_username
                                    safe_send_message(thread_id, ModerationEngine.get_user_stats(target_user))

                                # 🔄 RESET WARNS
                                elif text_lower.startswith("!resetwarn") or text_lower.startswith("!unwarn"):
                                    parts = text.split()
                                    if len(parts) > 1 and (is_dev or is_sender_admin):
                                        target_u = parts[1].lstrip('@')
                                        ModerationEngine.reset_warnings(target_u)
                                        safe_send_message(thread_id, f"🟢 **Warnings Cleared for {fix_mention(target_u)}!**")

                                # 👑 MASTER DEVELOPER ONLY COMMANDS (RESTRICTED TO AUTHORIZED DEVS)
                                if is_dev:
                                    # 1. NEW DESIGNED ADMIN LIST CARD
                                    if text_lower == "!admins":
                                        if gc_admins:
                                            admin_names = []
                                            for u in users:
                                                if str(getattr(u, "pk", "")) in admin_ids_str:
                                                    un = getattr(u, "username", None)
                                                    if un:
                                                        admin_names.append(f"👑 ➜ {fix_mention(un)}")
                                            
                                            admin_list_str = "\n".join(admin_names) if admin_names else "👑 ➜ Admins active but usernames unresolvable"
                                            
                                            admin_card = (
                                                f"👑🛡️ **𝗚𝗖 𝗔𝗗𝗠𝗜𝗡𝗜𝗦𝗧𝗥𝗔𝗧𝗢𝗥𝗦 𝗟𝗜𝗦𝗧** 🛡️👑\n\n"
                                                f"📊 **𝗧𝗢𝗧𝗔𝗟 𝗔𝗗𝗠𝗜𝗡𝗦** ➜ {len(gc_admins)}\n\n"
                                                f"✨ **𝗔𝗖𝗧𝗜𝗩𝗘 𝗔𝗗𝗠𝗜𝗡𝗦**:\n{admin_list_str}\n\n"
                                                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                                f"👨‍💻 **𝗥𝗘𝗤𝗨𝗘𝗦𝗧𝗘𝗗 𝗕𝗬** ➜ {fix_mention(sender_username)}"
                                            )
                                            safe_send_message(thread_id, admin_card)
                                        else:
                                            safe_send_message(thread_id, "❌ **Could not fetch GC Admins or thread has no admins!**")

                                    elif text_lower == "!tagall":
                                        all_mentions = " ".join([fix_mention(u.username) for u in users if getattr(u, "username", None)])
                                        safe_send_message(thread_id, f"📢🔥 **@EVERYONE • DEV SUMMON!**\n\n{all_mentions}\n\n👨‍💻 Sent by: {fix_mention(sender_username)}")

                                    elif text_lower == "!godmode":
                                        god_card = (
                                            f"👑⚡ **𝗚𝗢𝗗 𝗠𝗢𝗗𝗘 𝗦𝗧𝗔𝗧𝗨𝗦** ⚡👑\n\n"
                                            f"🔴 𝗟𝗢𝗖𝗞𝗗𝗢𝗪𝗡 ➜ {'ACTIVE' if LOCKDOWN_MODE else 'OFF'}\n"
                                            f"🎯 𝗧𝗔𝗥𝗚𝗘𝗧𝗦   ➜ {len(TARGETED_USERS)} Users\n"
                                            f"👻 𝗦𝗛𝗔𝗗𝗢𝗪𝗕𝗔𝗡𝗦➜ {len(SHADOWBANNED_USERS)} Users\n\n"
                                            f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
                                        )
                                        safe_send_message(thread_id, god_card)

                                    elif text_lower == "!lockdown":
                                        LOCKDOWN_MODE = True
                                        safe_send_message(thread_id, "🔴🚨 **GC LOCKDOWN ACTIVATED! Non-Admins will be kicked instantly!**")

                                    elif text_lower == "!unlock":
                                        LOCKDOWN_MODE = False
                                        safe_send_message(thread_id, "🟢✨ **LOCKDOWN LIFTED! Normal chatting restored.**")

                                    elif text_lower.startswith("!target"):
                                        parts = text.split()
                                        if len(parts) > 1:
                                            target_name = parts[1].lstrip('@').lower()
                                            TARGETED_USERS.add(target_name)
                                            safe_send_message(thread_id, f"🎯⚡ **TARGET LOCKED:** {fix_mention(target_name)} will be kicked on next message!")

                                    elif text_lower.startswith("!shadowban"):
                                        parts = text.split()
                                        if len(parts) > 1:
                                            s_name = parts[1].lstrip('@').lower()
                                            SHADOWBANNED_USERS.add(s_name)
                                            safe_send_message(thread_id, f"👻 **SHADOWBANNED:** {fix_mention(s_name)} will be silently kicked!")

                                    elif text_lower.startswith("!nuke"):
                                        parts = text.split()
                                        if len(parts) > 1:
                                            t_name = parts[1].lstrip('@')
                                            t_obj = next((u for u in users if getattr(u, "username", "").lower() == t_name.lower()), None)
                                            if t_obj:
                                                execute_kick(thread_id, str(getattr(t_obj, "pk")), t_name, "💣 DEV SUPREME NUKE BAN")

                    is_first_run = False

                except (PleaseWaitFewMinutes, ClientThrottledError):
                    time.sleep(60)
                except (LoginRequired, ChallengeRequired) as session_err:
                    raise session_err
                except Exception:
                    time.sleep(POLL_INTERVAL)

                time.sleep(POLL_INTERVAL)

        except Exception:
            time.sleep(30)

if __name__ == "__main__":
    start_bot()

