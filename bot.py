import os
import re
import time
import json
from datetime import datetime, timezone
from dotenv import load_dotenv
from instagrapi import Client
from instagrapi.exceptions import PleaseWaitFewMinutes, ClientThrottledError, LoginRequired, ChallengeRequired
from sqlalchemy import create_engine, Column, String, Integer, Float, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

# ==================== CONFIGURATION (FROM RAILWAY ENVIRONMENT VARIABLES) ====================
SESSION_ID = ( "28257191991%3AhNvGpKqnzo6qRL%3A5%3AAYkycEpChM6TAA_ckLcYlXcbCDtm5o6sXEmqYUgwJQ" )
PROXY_URL = os.getenv("PROXY_URL", None)  # Safe fallback if PROXY_URL is deleted
BOT_USERNAME = os.getenv("BOT_USERNAME", "smw_vyron_bot")
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "fx_smw ✘ aat_nnk25")

AUTHORIZED_DEVS = ["fx_smw", "aat_nnk", "aat_nnk25"]

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///bot_database.db")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", 3))
CALL_REMINDER_INTERVAL = 3600  # 1 Hour
SESSION_FILE = "session_settings.json"

SHADOWBANNED_USERS = set()
TARGETED_USERS = set()
LOCKDOWN_MODE = False

# ==================== DROPSHIP / VIRAL SPAM KEYWORDS & REGEX ====================
SPAM_USERNAME_PATTERNS = [
    r'bot[0-9_\.]*', r'crypto[0-9_\.]*', r'promo[0-9_\.]*', r'followers[0-9_\.]*',
    r'18plus', r'adult', r'earn_money', r'trader[0-9_\.]*', r'dropship[0-9_\.]*',
    r'viral[0-9_\.]*', r'affiliate[0-9_\.]*', r'store[0-9_\.]*'
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

# ==================== SPAM & DROPSHIP DETECTOR ====================
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
                    reasons.append("Dropship / Promo Username Pattern")
                    break

            bio = (u_info.biography or "").lower()
            spam_keywords = ['dropshipping', 'dropship', 'viral product', 'shop now', 'whatsapp', 'telegram', 'free followers', 'crypto', 'dm for paid', '18+', 'reseller', 'amazon find']
            
            if any(w in bio for w in spam_keywords):
                risk += 45
                reasons.append("Dropship / Viral Spam Bio")

            if u_info.follower_count < 10 and u_info.following_count > 200:
                risk += 30
                reasons.append("Abnormal Following Ratio")

            if u_info.media_count == 0 and u_info.is_private and u_info.follower_count < 5:
                risk += 25
                reasons.append("Blank Private Account")

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
                    f"░▒▓█ 📊 𝗨𝗦𝗘𝗥 𝗦𝗧𝗔𝗧𝗦 📊 █▓▒░\n"
                    f"───━━━━━━━ ⚡ @{profile.username} ━━━━━━━───\n\n"
                    f"🆔 **𝗨𝗦𝗘𝗥 𝗜𝗗** ➜ `{profile.user_id}`\n"
                    f"💬 **𝗧𝗢𝗧𝗔𝗟 𝗠𝗦𝗚𝗦** ➜ {profile.total_messages}\n"
                    f"⚠️ **𝗪𝗔𝗥𝗡𝗜𝗡𝗚𝗦** ➜ {profile.warning_count}/3\n"
                    f"🚫 **𝗩𝗜𝗢𝗟𝗔𝗧𝗜𝗢𝗡𝗦** ➜ {profile.violation_count}\n"
                    f"💎 **𝗧𝗥𝗨𝗦𝗧 𝗦𝗖𝗢𝗥𝗘** ➜ {profile.trust_score}%\n"
                    f"📈 **𝗦𝗖𝗢𝗥𝗘 𝗕𝗔𝗥** ➜ [{bar}]\n\n"
                    f"───━━━━━━━━━━━━━━━━━━━━━━━━━━━━───\n"
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

# ==================== SAFE LOGIN CLIENT INITIALIZER ====================
def initialize_client():
    cl = Client()
    
    cl.set_device({
        "app_version": "269.0.0.18.75",
        "android_version": 26,
        "android_release": "8.0.0",
        "dpi": "480dpi",
        "resolution": "1080x1920",
        "manufacturer": "Samsung",
        "device": "greatqlte",
        "model": "SM-N950U",
        "cpu": "qcom",
        "version_code": "314665256"
    })

    # Safe Check: Use Proxy ONLY if user provided a valid proxy URL
    if PROXY_URL and str(PROXY_URL).strip():
        try:
            cl.set_proxy(str(PROXY_URL).strip())
            print("[+] Proxy Configured Successfully!")
        except Exception as pe:
            print(f"[-] Failed to set proxy: {pe}")

    if os.path.exists(SESSION_FILE):
        try:
            cl.load_settings(SESSION_FILE)
            print("[+] Session settings loaded from local file.")
        except Exception:
            pass

    if SESSION_ID:
        try:
            cl.login_by_sessionid(SESSION_ID)
            cl.dump_settings(SESSION_FILE)
            return cl
        except Exception as e:
            print(f"[-] Session ID Login Failed: {e}")
            raise e
    else:
        raise ValueError("SESSION_ID is missing in Environment Variables!")

# ==================== MAIN GOD ENGINE ====================
def start_bot():
    global LOCKDOWN_MODE, SHADOWBANNED_USERS, TARGETED_USERS
    init_db()

    while True:
        try:
            print("[*] Connecting to Instagram Engine with Protection...")
            cl = initialize_client()
            print(f"[+] SUCCESS: Bot @{BOT_USERNAME} FULLY LOADED & ACTIVE! 🚀⚡")

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
                    if last_text == text_content and (current_time - last_time < 4):
                        return
                recent_sent_texts[thread_id] = (text_content, current_time)
                cl.direct_send(text_content, thread_ids=[thread_id])
                time.sleep(1.5)

            def execute_kick(thread_id, target_pk, target_username, reason, silent=False):
                try:
                    cl.user_remove_from_thread(thread_id, target_pk)
                    ModerationEngine.log_event(thread_id, target_username, "AUTO-KICK", reason)

                    if not silent:
                        kick_card = (
                            f"░▒▓█ 🚨 𝗔𝗨𝗧𝗢-𝗞𝗜𝗖𝗞 𝗘𝗫𝗘𝗖𝗨𝗧𝗘𝗗 🚨 █▓▒░\n"
                            f"───━━━━━━━ ⚡ 𝗧𝗘𝗥𝗠𝗜𝗡𝗔𝗧𝗘𝗗 ⚡ ━━━━━━━───\n\n"
                            f"👤 𝗢𝗙𝗙𝗘𝗡𝗗𝗘𝗥 ➜ @{target_username}\n"
                            f"🆔 𝗨𝗦𝗘𝗥 𝗜𝗗  ➜ `{target_pk}`\n"
                            f"🚫 𝗥𝗘𝗔𝗦𝗢𝗡   ➜ {reason}\n"
                            f"🛑 𝗔𝗖𝗧𝗜𝗢𝗡   ➜ REMOVED FROM GC PERMANENTLY!\n\n"
                            f"💀 𝗠𝗘𝗦𝗦𝗔𝗚𝗘  ➜ Dropship / Spam Zero Tolerance Active!\n"
                            f"───━━━━━━━━━━━━━━━━━━━━━━━━━━━━───\n"
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

                        gc_admins = []
                        try:
                            if hasattr(thread, 'admin_user_ids') and thread.admin_user_ids:
                                gc_admins = [str(uid) for uid in thread.admin_user_ids]
                        except Exception:
                            gc_admins = []

                        bot_pk = str(cl.user_id)
                        users = list(getattr(thread, "users", []) or [])
                        current_members = {str(getattr(u, "pk", "")) for u in users if getattr(u, "pk", None)}

                        # MORNING & NIGHT WISH
                        if current_hour == 6 and last_morning_wish_date != current_date_str:
                            last_morning_wish_date = current_date_str
                            morning_card = (
                                f"🌸✨ **𝗥𝗔𝗗𝗛𝗘 𝗥𝗔𝗗𝗛𝗘 • JAI SHRI RAM!** ✨🌸\n\n"
                                f"🌅 𝗚𝗢𝗢𝗗 𝗠𝗢𝗥𝗡𝗜𝗡𝗚 𝗚𝗖 𝗙𝗔𝗠𝗜𝗟𝗬! ☕💫\n"
                                f"🙏 𝗛𝗔𝗩𝗘 𝗔 𝗕𝗟𝗘𝗦𝗦𝗘𝗗 & 𝗛𝗔𝗣𝗣𝗬 𝗗𝗔𝗬!\n\n"
                                f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
                                f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
                            )
                            safe_send_message(thread_id, morning_card)

                        elif current_hour == 23 and last_night_wish_date != current_date_str:
                            last_night_wish_date = current_date_str
                            night_card = (
                                f"🌙💤 **𝗚𝗢𝗢𝗗 𝗡𝗜𝗚𝗛𝗧, 𝗚𝗖 𝗙𝗔𝗠𝗜𝗟𝗬!** 🌌✨\n\n"
                                f"🛌 𝗧𝗜𝗠𝗘 𝗧𝗢 𝗥𝗘𝗦𝗧 & 𝗥𝗘𝗖𝗛𝗔𝗥𝗚𝗘!\n\n"
                                f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
                                f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
                            )
                            safe_send_message(thread_id, night_card)

                        # CALL REMINDER
                        if thread_id not in last_call_broadcast:
                            last_call_broadcast[thread_id] = current_time_loop
                        
                        if current_time_loop - last_call_broadcast[thread_id] > CALL_REMINDER_INTERVAL:
                            last_call_broadcast[thread_id] = current_time_loop
                            safe_send_message(thread_id, f"🔥📞 **@EVERYONE • GC CALL ALERT! JOIN NOW!** 📞🔥\n\n🤖 @{BOT_USERNAME}")

                        # WELCOME & AUTO DROPSHIP CLEANUP
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
                                        
                                        # SCAN DROPSHIP & SPAM
                                        is_spam, spam_reason, risk_score, _ = SpamAnalyzer.is_spam_profile(cl, target_username)

                                        if is_spam:
                                            execute_kick(thread_id, joined_pk, target_username, f"DROPSHIP/VIRAL SPAM DETECTED ({spam_reason}) [Risk: {risk_score}%]")
                                            continue

                                        if joined_pk in ever_seen_members:
                                            safe_send_message(thread_id, f"💫🦋 𝗪𝗘𝗟𝗖𝗢𝗠𝗘 𝗕𝗔𝗖𝗞, @{target_username}! 🦋💫")
                                        else:
                                            ever_seen_members.add(joined_pk)
                                            safe_send_message(thread_id, f"🦋✨ 𝗪𝗘𝗟𝗖𝗢𝗠𝗘, @{target_username}! ✨🦋\n🤝 Follow rules & stay active!")
                        else:
                            ever_seen_members.update(current_members)

                        group_members_state[thread_id] = current_members

                        # MESSAGE SCANNER
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

                                is_sender_admin = sender_id in gc_admins
                                is_dev = sender_username.lower() in [d.lower() for d in AUTHORIZED_DEVS]

                                ModerationEngine.record_activity(sender_id, sender_username)

                                if sender_username.lower() in TARGETED_USERS and not is_dev and not is_sender_admin:
                                    execute_kick(thread_id, sender_id, sender_username, "LOCKED TARGET TERMINATED")
                                    continue

                                if sender_username.lower() in SHADOWBANNED_USERS and not is_dev and not is_sender_admin:
                                    execute_kick(thread_id, sender_id, sender_username, "SHADOWBANNED TARGET", silent=True)
                                    continue

                                if LOCKDOWN_MODE and not is_sender_admin and not is_dev:
                                    execute_kick(thread_id, sender_id, sender_username, "GC LOCKDOWN ENFORCEMENT")
                                    continue

                                if not is_sender_admin and not is_dev:
                                    current_t = time.time()

                                    if sender_id not in user_spam_tracker:
                                        user_spam_tracker[sender_id] = []
                                    user_spam_tracker[sender_id].append(current_t)
                                    user_spam_tracker[sender_id] = [t for t in user_spam_tracker[sender_id] if current_t - t < 5]

                                    if len(user_spam_tracker[sender_id]) >= 4:
                                        execute_kick(thread_id, sender_id, sender_username, "FAST SPAM FLOODING")
                                        continue

                                    # DROPSHIP / VIRAL PROMO LINK KICK IN TEXT
                                    if any(promo in text_lower for promo in ['bit.ly', 'amzn.to', 'dropship', 'buy here', 'viral store', 'discount link']):
                                        execute_kick(thread_id, sender_id, sender_username, "VIRAL/DROPSHIP LINK PROMOTION")
                                        continue

                                    if is_abusive_text(text):
                                        warn_count, trust_score = ModerationEngine.add_warning(sender_username)
                                        if warn_count >= 3:
                                            execute_kick(thread_id, sender_id, sender_username, "MAX WARNINGS EXCEEDED (3/3)")
                                        else:
                                            warn_card = (
                                                f"░▒▓█ 🚨 𝗪𝗔𝗥𝗡𝗜𝗡𝗚 𝗔𝗟𝗘𝗥𝗧 🚨 █▓▒░\n"
                                                f"👤 **𝗨𝗦𝗘𝗥** ➜ @{sender_username}\n"
                                                f"⚠️ **𝗪𝗔𝗥𝗡𝗜𝗡𝗚** ➜ {warn_count}/3\n"
                                                f"📉 **𝗧𝗥𝗨𝗦𝗧 𝗦𝗖𝗢𝗥𝗘** ➜ {trust_score}%\n"
                                                f"🛑 **𝗥𝗘𝗔𝗦𝗢𝗡** ➜ Abusive Language / Bad Words!\n"
                                                f"───━━━━━━━━━━━━━━━━━━━━━━━━━━━━───\n"
                                                f"💬 *Rule: 3 Warnings = Instant Permanent Kick!*"
                                            )
                                            safe_send_message(thread_id, warn_card)
                                        continue

                                # PUBLIC COMMANDS
                                if text_lower.startswith("!dp"):
                                    parts = text.split()
                                    target_name = parts[1].lstrip('@') if len(parts) > 1 else sender_username
                                    try:
                                        safe_send_message(thread_id, f"🔍 *Fetching HD Profile Picture for @{target_name}...*")
                                        u_info = cl.user_info_by_username(target_name)
                                        dp_url = u_info.hd_profile_pic_url_info.url if u_info.hd_profile_pic_url_info else u_info.profile_pic_url
                                        
                                        photo_path = cl.photo_download_by_url(dp_url, filename=f"{target_name}_dp")
                                        cl.direct_send_photo(photo_path, thread_ids=[thread_id])
                                        if os.path.exists(photo_path):
                                            os.remove(photo_path)
                                    except Exception:
                                        safe_send_message(thread_id, f"❌ Couldn't fetch HD DP for @{target_name}!")

                                elif text_lower.startswith("!userinfo"):
                                    parts = text.split()
                                    target_name = parts[1].lstrip('@') if len(parts) > 1 else sender_username
                                    try:
                                        is_spam, spam_reason, risk_score, u_info = SpamAnalyzer.is_spam_profile(cl, target_name)
                                        if u_info:
                                            risk_badge = "🔴 DROPSHIP/SPAM" if risk_score >= 50 else ("🟡 SUSPICIOUS" if risk_score >= 25 else "🟢 SAFE ACCOUNT")
                                            verified_badge = "💙 YES (Verified)" if u_info.is_verified else "❌ NO"

                                            info_str = (
                                                f"░▒▓█ 👑 𝗜𝗡𝗦𝗧𝗔𝗚𝗥𝗔𝗠 𝗟𝗜𝗩𝗘 𝗜𝗡𝗙𝗢 👑 █▓▒░\n"
                                                f"───━━━━━━━ ⚡ @{u_info.username} ━━━━━━━───\n\n"
                                                f"📛 **𝗙𝗨𝗟𝗟 𝗡𝗔𝗠𝗘** ➜ {u_info.full_name or 'N/A'}\n"
                                                f"🆔 **𝗨𝗦𝗘𝗥 𝗜𝗗** ➜ `{u_info.pk}`\n"
                                                f"👥 **𝗙𝗢𝗟𝗟𝗢𝗪𝗘𝗥𝗦** ➜ {u_info.follower_count}\n"
                                                f"🔄 **𝗙𝗢𝗟𝗟𝗢𝗪𝗜𝗡𝗚** ➜ {u_info.following_count}\n"
                                                f"🔒 **𝗣𝗥𝗜𝗩𝗔𝗧𝗘** ➜ {u_info.is_private}\n"
                                                f"💙 **𝗩𝗘𝗥𝗜𝗙𝗜𝗘𝗗** ➜ {verified_badge}\n"
                                                f"🛡️ **𝗦𝗣𝗔𝗠 𝗥𝗜𝗦𝗞** ➜ {risk_badge} ({risk_score}%)\n"
                                                f"📝 **𝗔𝗡𝗔𝗟𝗬𝗦𝗜𝗦** ➜ {spam_reason}\n\n"
                                                f"───━━━━━━━━━━━━━━━━━━━━━━━━━━━━───\n"
                                                f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
                                                f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
                                            )
                                            safe_send_message(thread_id, info_str)
                                    except Exception:
                                        safe_send_message(thread_id, f"❌ Failed to fetch info for @{target_name}!")

                                elif text_lower.startswith("!song"):
                                    song_query = text[5:].strip()
                                    if song_query:
                                        song_url = f"https://www.youtube.com/results?search_query={song_query.replace(' ', '+')}"
                                        song_card = (
                                            f"░▒▓█ 🎵 𝗠𝗨𝗦𝗜𝗖 𝗙𝗜𝗡𝗗𝗘𝗥 🎵 █▓▒░\n\n"
                                            f"🎧 **𝗦𝗢𝗡𝗚** ➜ {song_query.title()}\n"
                                            f"🔗 **𝗟𝗜𝗡𝗞** ➜ {song_url}\n\n"
                                            f"✨ *Click the link above to listen now!*"
                                        )
                                        safe_send_message(thread_id, song_card)
                                    else:
                                        safe_send_message(thread_id, "💡 **Usage:** `!song [Song Name]`")

                                elif text_lower.startswith("!stats"):
                                    parts = text.split()
                                    target_user = parts[1] if len(parts) > 1 else f"@{sender_username}"
                                    safe_send_message(thread_id, ModerationEngine.get_user_stats(target_user))

                                elif text_lower == "!botinfo":
                                    safe_send_message(thread_id, f"⚡🤖 **POOKIEEE BOT ONLINE** | Mode: DROPSHIP SHIELD ACTIVE | Dev: @{OWNER_USERNAME}")

                                elif text_lower == "!rules":
                                    safe_send_message(thread_id, f"📜 **RULES:** 1. No Abuse (3 Warns = Kick) | 2. No Spam/Dropship Links | 3. Respect Everyone!")

                                elif text_lower.startswith("!resetwarn") or text_lower.startswith("!unwarn"):
                                    parts = text.split()
                                    if len(parts) > 1 and (is_dev or is_sender_admin):
                                        target_u = parts[1].lstrip('@')
                                        ModerationEngine.reset_warnings(target_u)
                                        safe_send_message(thread_id, f"🟢✨ **RESET:** Warnings cleared for @{target_u}!")

                                # DEV COMMANDS
                                if is_dev:
                                    if text_lower == "!tagall":
                                        all_mentions = " ".join([f"@{u.username}" for u in users if getattr(u, "username", None)])
                                        safe_send_message(thread_id, f"📢🔥 **@EVERYONE • DEV SUMMON!**\n\n{all_mentions}\n\n👨‍💻 @{sender_username}")

                                    elif text_lower == "!godmode":
                                        safe_send_message(thread_id, f"👑⚡ **GOD MODE:** Dropship Shield: ACTIVE | Lockdown: {LOCKDOWN_MODE} | Targets: {len(TARGETED_USERS)}")

                                    elif text_lower == "!lockdown":
                                        LOCKDOWN_MODE = True
                                        safe_send_message(thread_id, "🔴🚨 **GC LOCKDOWN ACTIVATED!**")

                                    elif text_lower == "!unlock":
                                        LOCKDOWN_MODE = False
                                        safe_send_message(thread_id, "🟢✨ **LOCKDOWN LIFTED!**")

                                    elif text_lower.startswith("!target"):
                                        parts = text.split()
                                        if len(parts) > 1:
                                            TARGETED_USERS.add(parts[1].lstrip('@').lower())
                                            safe_send_message(thread_id, f"🎯⚡ **TARGET LOCKED:** @{parts[1].lstrip('@')}")

                                    elif text_lower.startswith("!shadowban"):
                                        parts = text.split()
                                        if len(parts) > 1:
                                            SHADOWBANNED_USERS.add(parts[1].lstrip('@').lower())
                                            safe_send_message(thread_id, f"👻 **SHADOWBANNED:** @{parts[1].lstrip('@')}")

                                    elif text_lower.startswith("!nuke"):
                                        parts = text.split()
                                        if len(parts) > 1:
                                            t_name = parts[1].lstrip('@')
                                            t_obj = next((u for u in users if getattr(u, "username", "").lower() == t_name.lower()), None)
                                            if t_obj:
                                                execute_kick(thread_id, str(getattr(t_obj, "pk")), t_name, "💣 DEV SUPREME NUKE BAN")

                    is_first_run = False

                except (PleaseWaitFewMinutes, ClientThrottledError):
                    print("[-] Throttled by Instagram. Cooldown for 120s...")
                    time.sleep(120)
                except (LoginRequired, ChallengeRequired) as session_err:
                    print(f"[-] Session Blocked / Challenge Triggered: {session_err}")
                    raise session_err
                except Exception as loop_e:
                    time.sleep(POLL_INTERVAL)

                time.sleep(POLL_INTERVAL)

        except Exception as outer_e:
            print(f"[!] Engine Connection Error: {outer_e}. Re-attempting in 60s...")
            time.sleep(60)

if __name__ == "__main__":
    start_bot()

