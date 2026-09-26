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

# --- Credentials & Config ---
BOT_USERNAME = "bot0.0928"
BOT_PASSWORD = "SIDHU295"
SESSION_ID = "24360649417%3AS1EM4yIX1dAY38%3A11%3AAYkCUG8dlREoJjaY-RrS3DGn-uegz7unStPHfxlS7A" 

OWNER_USERNAME = "fx_smw ✘ aat_nnk25"
AUTHORIZED_DEVS = ["fx_smw", "aat_nnk", "aat_nnk25", "fx_sw"]
DATABASE_URL = "sqlite:///god_mode_bot.db"
POLL_INTERVAL = 0.5  # Super-fast polling for instant replies

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

ADVANCED_ABUSE_PATTERNS = [
    r'm[\.\_\-\s]*c', r'b[\.\_\-\s]*c', r'm[\.\_\-\s]*k[\.\_\-\s]*c',
    r't[\.\_\-\s]*m[\.\_\-\s]*k[\.\_\-\s]*c', r'madar\s*chod', r'bhen\s*chod', 
    r'behen\s*chod', r'bhosd\w*', r'chut\w*', r'gand\w*', r'gaand\w*', r'lund\w*',
    r'lauda\w*', r'lawda\w*', r'randi\w*', r'bhadwa\w*', r'bhadwe\w*', r'bsdk\w*', 
    r'harami\w*', r'f[\.\_\-\s]*u[\.\_\-\s]*c[\.\_\-\s]*k', r'sex\w*', r'pussy\w*',
    r'dick\w*', r'cock\w*', r'porn\w*', r'xnxx\w*', r'xhamster\w*', r'chutiya\w*',
    r'gandu\w*', r'bhosdike', r'nude\w*', r'mujra\w*', r'bhabhi\w*', r'mc', r'bc'
]

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
                    f"📊✨ 𝗚𝗢𝗗-𝗠𝗢𝗗𝗘 • 𝗨𝗦𝗘𝗥 𝗧𝗥𝗨𝗦𝗧 𝗖𝗔𝗥𝗗 ✨📊\n\n"
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
            return f"❌ User {fix_mention(clean_user)} not registered yet!"
        finally:
            db.close()

    @staticmethod
    def get_history_stats(username: str) -> str:
        db = SessionLocal()
        try:
            clean_user = username.lstrip('@').lower()
            profile = db.query(UserProfile).filter(UserProfile.username == clean_user).first()
            if profile:
                return (
                    f"📜🔍 𝗛𝗜𝗦𝗧𝗢𝗥𝗬 • 𝗖𝗛𝗔𝗡𝗚𝗘 𝗖𝗔𝗥𝗗 🔍📜\n\n"
                    f"👤 𝗨𝗦𝗘𝗥 ➜ {fix_mention(profile.username)}\n"
                    f"🏷️ 𝗨𝗦𝗘𝗥𝗡𝗔𝗠𝗘 𝗖𝗛𝗔𝗡𝗚𝗘𝗦 ➜ `{profile.username_changes}` Times\n"
                    f"📌 𝗡𝗔𝗠𝗘 𝗖𝗛𝗔𝗡𝗚𝗘𝗦 ➜ `{profile.name_changes}` Times\n"
                    f"📝 𝗟𝗔𝗦𝗧 𝗞𝗡𝗢𝗪𝗡 𝗡𝗔𝗠𝗘 ➜ {profile.last_known_fullname or 'N/A'}\n\n"
                    f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                    f"👑 𝗗𝗘𝗩 ➜ {OWNER_USERNAME}"
                )
            return f"❌ History data not found for {fix_mention(clean_user)}!"
        finally:
            db.close()

    @staticmethod
    def get_top_chatters() -> str:
        db = SessionLocal()
        try:
            top_users = db.query(UserProfile).order_by(UserProfile.total_messages.desc()).limit(5).all()
            if not top_users:
                return f"🏆👑 𝗟𝗘𝗔𝗗𝗘𝗥𝗕𝗢𝗔𝗥𝗗 👑🏆\n\n⚠️ No active data found yet!"
            
            list_str = ""
            medals = ["🥇", "🥈", "🥉", "🏅", "🏅"]
            for idx, u in enumerate(top_users, 1):
                list_str += f"{medals[idx-1]} {fix_mention(u.username)} ➜ `{u.total_messages}` msgs\n"

            return (
                f"🏆👑 𝗚𝗖 𝗔𝗖𝗧𝗜𝗩𝗜𝗧𝗬 • 𝗟𝗘𝗔𝗗𝗘𝗥𝗕𝗢𝗔𝗥𝗗 👑🏆\n\n"
                f"{list_str}\n"
                f"🔥 𝗞𝗘𝗘𝗣 𝗖𝗛𝗔𝗧𝗧𝗜𝗡𝗚 & 𝗥𝗢𝗖𝗞 𝗧𝗛𝗘 𝗚𝗖\n\n"
                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}"
            )
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
    for pattern in ADVANCED_ABUSE_PATTERNS:
        if re.search(pattern, text_lower):
            return True
    return False

def start_bot():
    global LOCKDOWN_MODE, SHADOWBANNED_USERS, TARGETED_USERS, thread_known_members, user_message_timestamps
    init_db()

    while True:
        try:
            print("[*] Initializing Supreme God-Mode Engine...")
            cl = Client()
            cl.set_user_agent("Mozilla/5.0 (Linux; Android 11; SM-G998B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Mobile Safari/537.36 Instagram")

            logged_in = False
            if SESSION_ID and SESSION_ID != "YOUR_SESSION_ID_HERE":
                try:
                    cl.login_by_sessionid(SESSION_ID)
                    logged_in = True
                    print("[+] Session ID login successful!")
                except Exception:
                    pass

            if not logged_in:
                cl.login(BOT_USERNAME, BOT_PASSWORD)
                print("[+] ID-Password login successful!")

            print(f"[+] SUCCESS: Bot @{BOT_USERNAME} SUPREME GOD-MODE ACTIVE! 🚀🔥")

            seen_message_ids = set()
            last_morning_wish_date = ""
            last_night_wish_date = ""
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
                time.sleep(0.2)

            def execute_kick(thread_id, target_pk, target_username, reason, admin_tags, reply_to_id=None, silent=False):
                try:
                    cl.user_remove_from_thread(thread_id, target_pk)
                    ModerationEngine.log_event(thread_id, target_username, "AUTO-KICK", reason)
                    if not silent:
                        kick_card = (
                            f"🚨⚡ 𝗚𝗢𝗗-𝗠𝗢𝗗𝗘 • 𝗣𝗢𝗪𝗘𝗥𝗙𝗨𝗟 𝗔𝗨𝗧𝗢-𝗞𝗜𝗖𝗞 ⚡🚨\n\n"
                            f"👤 𝗢𝗙𝗙𝗘𝗡𝗗𝗘𝗥 ➜ {fix_mention(target_username)}\n"
                            f"🆔 𝗨𝗦𝗘𝗥 𝗜𝗗 ➜ `{target_pk}`\n"
                            f"🚫 𝗥𝗘𝗔𝗦𝗢𝗡 ➜ {reason}\n"
                            f"🛑 𝗦𝗧𝗔𝗧𝗨𝗦 ➜ 𝗣𝗘𝗥𝗠𝗔𝗡𝗘𝗡𝗧𝗟𝗬 𝗥𝗘𝗠𝗢𝗩𝗘𝗗\n\n"
                            f"📢 𝗔𝗗𝗠𝗜𝗡𝗦 ➜ {admin_tags}\n"
                            f"🛡️ 𝗚𝗖 𝗜𝗦 𝗡𝗢𝗪 𝗦𝗔𝗙𝗘 & 𝗦𝗘𝗖𝗨𝗥𝗘\n\n"
                            f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}"
                        )
                        safe_send_message(thread_id, kick_card, reply_to_item_id=reply_to_id)
                except Exception:
                    pass

            while True:
                try:
                    threads = cl.direct_threads(amount=5)
                    now = datetime.now()
                    current_hour = now.hour
                    current_minute = now.minute
                    current_date_str = now.strftime("%Y-%m-%d")

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
                            new_members = current_user_pks - old_members
                            for new_pk in new_members:
                                thread_known_members[thread_id].add(new_pk)
                                new_username = "User"
                                for u in users:
                                    if str(getattr(u, "pk", "")) == new_pk:
                                        new_username = getattr(u, "username", "User")
                                        break
                                
                                if "bot" in new_username.lower() and new_username.lower() != BOT_USERNAME.lower():
                                    execute_kick(thread_id, new_pk, new_username, "Unauthorized Bot Protection", admin_mentions_tag)
                                    continue

                                welcome_card = (
                                    f"👋✨ 𝗪𝗘𝗟𝗖𝗢𝗠𝗘 / 𝗪𝗘𝗟𝗖𝗢𝗠𝗘 𝗕𝗔𝗖𝗞 ✨👋\n\n"
                                    f"👤 𝗠𝗘𝗠𝗕𝗘𝗥 ➜ {fix_mention(new_username)}\n"
                                    f"🔥 𝗚𝗟𝗔𝗗 𝗧𝗢 𝗦𝗘𝗘 𝗬𝗢𝗨 𝗛𝗘𝗥𝗘\n"
                                    f"📜 𝗣𝗟𝗘𝗔𝗦𝗘 𝗖𝗛𝗘𝗖𝗞 𝗥𝗨𝗟𝗘𝗦 ➜ `!rules`\n\n"
                                    f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}"
                                )
                                safe_send_message(thread_id, welcome_card)

                        # --- Morning Wish (6:00 AM) ---
                        if current_hour == 6 and last_morning_wish_date != current_date_str:
                            last_morning_wish_date = current_date_str
                            morning_card = (
                                f"☀️🌷 𝗚𝗢𝗗 𝗠𝗢𝗥𝗡𝗜𝗡𝗚, 𝗘𝗩𝗘𝗥𝗬𝗢𝗡𝗘! 🌷☀️\n\n"
                                f"✨ 𝗡𝗘𝗪 𝗗𝗔𝗬 • 𝗡𝗘𝗪 𝗚𝗢𝗔𝗟𝗦\n"
                                f"🚀 𝗦𝗧𝗔𝗬 𝗣𝗢𝗦𝗜𝗧𝗜𝗩𝗘 • 𝗦𝗧𝗔𝗬 𝗙𝗢𝗖𝗨𝗦𝗘𝗗\n\n"
                                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}"
                            )
                            safe_send_message(thread_id, morning_card)

                        # --- Night Wish (10:30 PM) ---
                        if current_hour == 22 and current_minute >= 30 and last_night_wish_date != current_date_str:
                            last_night_wish_date = current_date_str
                            night_card = (
                                f"🌙✨ 𝗚𝗢𝗗 𝗡𝗜𝗚𝗛𝗧, 𝗘𝗩𝗘𝗥𝗬𝗢𝗡𝗘! ✨🌙\n\n"
                                f"😴 𝗧𝗜𝗠𝗘 𝗧𝗢 𝗥𝗘𝗦𝗧 & 𝗥𝗘𝗖𝗛𝗔𝗥𝗚𝗘\n"
                                f"💫 𝗦𝗪𝗘𝗘𝗧 𝗗𝗥𝗘𝗔𝗠𝗦 • 𝗦𝗟𝗘𝗘𝗣 𝗪𝗘𝗟𝗟\n\n"
                                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}"
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

                                # --- God-Mode Anti-Flood Protection ---
                                if not is_dev and not is_sender_admin:
                                    current_t = time.time()
                                    if sender_id not in user_message_timestamps:
                                        user_message_timestamps[sender_id] = []
                                    user_message_timestamps[sender_id] = [t for t in user_message_timestamps[sender_id] if current_t - t < 4]
                                    user_message_timestamps[sender_id].append(current_t)
                                    
                                    if len(user_message_timestamps[sender_id]) > 4:
                                        execute_kick(thread_id, sender_id, sender_username, "God-Mode Anti-Flood Rapid Spam Triggered", admin_mentions_tag, reply_to_id=message_id)
                                        continue

                                if LOCKDOWN_MODE and not is_dev and not is_sender_admin:
                                    execute_kick(thread_id, sender_id, sender_username, "GC LOCKDOWN MODE ACTIVE", admin_mentions_tag, reply_to_id=message_id)
                                    continue

                                if sender_username.lower() in TARGETED_USERS:
                                    execute_kick(thread_id, sender_id, sender_username, "TARGET ELIMINATED ON SIGHT", admin_mentions_tag, reply_to_id=message_id)
                                    continue

                                if sender_username.lower() in SHADOWBANNED_USERS:
                                    execute_kick(thread_id, sender_id, sender_username, "SHADOWBANNED", admin_mentions_tag, reply_to_id=message_id, silent=True)
                                    continue

                                # --- POWERFUL AUTO-KICK & ABUSE/NSFW/LINK ENGINE ---
                                if not is_dev and not is_sender_admin:
                                    is_abuse = is_abusive_text(text)
                                    is_reel_or_link = any(kw in text_lower for kw in [
                                        "http://", "https://", "www.", "instagram.com", "t.me", "bit.ly", 
                                        "reel", "reels", "post", "share", "profile", "igtv", "story", "whatsapp"
                                    ]) or item_type in ["clip", "story_share", "media_share", "felix_share_target"]
                                        
                                    is_nsfw_content = (
                                        item_type in ["media", "visual_media", "raven_media", "sticker"] or
                                        any(word in text_lower for word in ['18+', 'adult', 'xxx', 'sex', 'porn', 'hot video', 'bra', 'panty', 'xnxx', 'xhamster', 'nude', 'mujra', 'bhabhi'])
                                    )

                                    if is_abuse or is_reel_or_link or is_nsfw_content:
                                        reason = "Zero-Tolerance Toxic Abuse / Slang" if is_abuse else ("Unauthorized Link / Reel / Promotion" if is_reel_or_link else "18+ / NSFW Content / Sticker")
                                        warns, trust = ModerationEngine.add_warning(sender_username)

                                        if warns >= 3 or is_abuse or is_nsfw_content:  # Instant kick for abuse/NSFW, 3 warnings for links
                                            execute_kick(thread_id, sender_id, sender_username, reason, admin_mentions_tag, reply_to_id=message_id)
                                        else:
                                            warn_card = (
                                                f"⚠️🚨 𝗩𝗜𝗢𝗟𝗔𝗧𝗜𝗢𝗡 𝗪𝗔𝗥𝗡𝗜𝗡𝗚 🚨⚠️\n\n"
                                                f"👤 𝗢𝗙𝗙𝗘𝗡𝗗𝗘𝗥 ➜ {fix_mention(sender_username)}\n"
                                                f"🚫 𝗥𝗘𝗔𝗦𝗢𝗡 ➜ {reason}\n"
                                                f"⚠️ 𝗪𝗔𝗥𝗡𝗜𝗡𝗚𝗦 ➜ {warns}/3\n"
                                                f"📉 𝗧𝗥𝗨𝗦𝗧 𝗦𝗖𝗢𝗥𝗘 ➜ {trust}%\n\n"
                                                f"📢 𝗔𝗗𝗠𝗜𝗡𝗦 ➜ {admin_mentions_tag}\n\n"
                                                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}"
                                            )
                                            safe_send_message(thread_id, warn_card, reply_to_item_id=message_id)
                                        continue

                                # --- ALL COMMAND CARDS HANDLER ---
                                if text_lower == "!rules":
                                    rules_card = (
                                        f"⚜️🌷 𝗚𝗖 𝗥𝗨𝗟𝗘𝗦 • 𝗚𝗢𝗗-𝗠𝗢𝗗𝗘 🌷⚜️\n\n"
                                        f"🤝 Respect Everyone & Keep Vibe Friendly\n"
                                        f"🚫 No Abuse / Toxicity (Instant Kick)\n"
                                        f"🔞 No NSFW / Adult Content / Stickers\n"
                                        f"🎥 No Reels / Links / Promotions\n\n"
                                        f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}"
                                    )
                                    safe_send_message(thread_id, rules_card, reply_to_item_id=message_id)
                                    continue

                                if text_lower in ["!ping", "!alive"]:
                                    ping_card = (
                                        f"⚡🏓 𝗚𝗢𝗗-𝗠𝗢𝗗𝗘 • 𝗣𝗜𝗡𝗚 𝗖𝗛𝗘𝗖𝗞 🏓⚡\n\n"
                                        f"🚀 STATUS ➜ ULTRA PRO MAX ONLINE\n"
                                        f"💨 SPEED ➜ 0.5s (INSTANT REPLY)\n"
                                        f"🛡️ SECURITY ➜ GOD LEVEL\n\n"
                                        f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}"
                                    )
                                    safe_send_message(thread_id, ping_card, reply_to_item_id=message_id)
                                    continue

                                if text_lower == "!botinfo":
                                    info_card = (
                                        f"🤖📊 𝗕𝗢𝗧 𝗜𝗡𝗙𝗢 • 𝗚𝗢𝗗-𝗠𝗢𝗗𝗘 📊🤖\n\n"
                                        f"⚡ STATUS ➜ 100% ONLINE\n"
                                        f"🛡️ MODERATION ➜ ACTIVE\n\n"
                                        f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}"
                                    )
                                    safe_send_message(thread_id, info_card, reply_to_item_id=message_id)
                                    continue

                                if text_lower in ["!help", "!commands", "!menu"]:
                                    help_card = (
                                        f"📜🤖 𝗚𝗢𝗗-𝗠𝗢𝗗𝗘 • 𝗖𝗢𝗠𝗠𝗔𝗡𝗗𝗦 𝗟𝗜𝗦𝗧 🤖📜\n\n"
                                        f"➜ `!rules` : Show GC Rules\n"
                                        f"➜ `!ping` / `!alive` : Check Bot Speed\n"
                                        f"➜ `!botinfo` : System Status\n"
                                        f"➜ `!dp <username>` : Download HD DP\n"
                                        f"➜ `!stats <username>` : User Trust Score\n"
                                        f"➜ `!history <username>` : Change History\n"
                                        f"➜ `!topchatters` : Leaderboard\n"
                                        f"➜ `!profile <username>` : Profile Info\n"
                                        f"➜ `!members` : Member List Count\n"
                                        f"➜ `!admins` : Admin List Count\n"
                                        f"➜ `!security` : GC Security Status\n"
                                        f"➜ `!lockdown` / `!unlock` : GC Security Mode\n"
                                        f"➜ `!target <username>` : Kill on Sight\n\n"
                                        f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}"
                                    )
                                    safe_send_message(thread_id, help_card, reply_to_item_id=message_id)
                                    continue

                                # Dev/Admin Commands
                                if is_dev or is_sender_admin:
                                    if text_lower == "!lockdown":
                                        LOCKDOWN_MODE = True
                                        safe_send_message(thread_id, f"🚨🔒 **LOCKDOWN ACTIVATED**\n\n🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}", reply_to_item_id=message_id)
                                        continue
                                    elif text_lower == "!unlock":
                                        LOCKDOWN_MODE = False
                                        safe_send_message(thread_id, f"🔓✨ **LOCKDOWN DEACTIVATED**\n\n🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}", reply_to_item_id=message_id)
                                        continue
                                    elif text_lower.startswith("!target"):
                                        parts = text.split()
                                        if len(parts) > 1:
                                            target = parts[1].lstrip('@').lower()
                                            TARGETED_USERS.add(target)
                                            safe_send_message(thread_id, f"🎯🎯 **TARGET LOCKED**: {fix_mention(target)}", reply_to_item_id=message_id)
                                        continue
                                    elif text_lower.startswith("!resetwarn"):
                                        parts = text.split()
                                        if len(parts) > 1:
                                            target = parts[1].lstrip('@')
                                            ModerationEngine.reset_warnings(target)
                                            safe_send_message(thread_id, f"✅ Warnings reset for {fix_mention(target)}", reply_to_item_id=message_id)
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
                                        else:
                                            safe_send_message(thread_id, f"❌ User not found!", reply_to_item_id=message_id)
                                    except Exception:
                                        safe_send_message(thread_id, f"❌ DP Fetch Error!", reply_to_item_id=message_id)
                                    continue

                                if text_lower.startswith("!stats"):
                                    parts = text.split()
                                    target_name = parts[1].lstrip('@') if len(parts) > 1 else sender_username
                                    stats_msg = ModerationEngine.get_user_stats(target_name)
                                    safe_send_message(thread_id, stats_msg, reply_to_item_id=message_id)
                                    continue

                                if text_lower.startswith("!history"):
                                    parts = text.split()
                                    target_name = parts[1].lstrip('@') if len(parts) > 1 else sender_username
                                    history_msg = ModerationEngine.get_history_stats(target_name)
                                    safe_send_message(thread_id, history_msg, reply_to_item_id=message_id)
                                    continue

                                if text_lower in ["!topchatters", "!leaderboard", "!active"]:
                                    leaderboard_msg = ModerationEngine.get_top_chatters()
                                    safe_send_message(thread_id, leaderboard_msg, reply_to_item_id=message_id)
                                    continue

                                if text_lower.startswith("!userinfo") or text_lower.startswith("!profile"):
                                    parts = text.split()
                                    target_name = parts[1].lstrip('@') if len(parts) > 1 else sender_username
                                    try:
                                        u_info = cl.user_info_by_username(target_name)
                                        if u_info:
                                            profile_card = (
                                                f"👤📋 𝗨𝗦𝗘𝗥 • 𝗣𝗥𝗢𝗙𝗜𝗟𝗘 𝗜𝗡𝗙𝗢 📋👤\n\n"
                                                f"📌 NAME ➜ {getattr(u_info, 'full_name', 'N/A')}\n"
                                                f"🏷️ USERNAME ➜ {fix_mention(target_name)}\n"
                                                f"🆔 USER ID ➜ `{u_info.pk}`\n"
                                                f"👥 FOLLOWERS ➜ {getattr(u_info, 'follower_count', 0)}\n"
                                                f"🔒 PRIVATE ➜ {'Yes 🔒' if getattr(u_info, 'is_private', False) else 'No 🔓'}\n\n"
                                                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}"
                                            )
                                            safe_send_message(thread_id, profile_card, reply_to_item_id=message_id)
                                    except Exception:
                                        safe_send_message(thread_id, f"❌ Profile Fetch Error!", reply_to_item_id=message_id)
                                    continue

                                if text_lower in ["!members", "!memberlist"]:
                                    try:
                                        total_count = len(users)
                                        members_card = f"👥📊 𝗚𝗥𝗢𝗨𝗣 • 𝗠𝗘𝗠𝗕𝗘𝗥𝗦 ➜ `{total_count}` members\n\n🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}"
                                        safe_send_message(thread_id, members_card, reply_to_item_id=message_id)
                                    except Exception:
                                        pass
                                    continue

                                if text_lower in ["!admins", "!adminlist"]:
                                    try:
                                        admin_card = f"👑🛡️ 𝗚𝗖 𝗔𝗗𝗠𝗜𝗡𝗦 𝗖𝗢𝗨𝗡𝗧 ➜ `{len(gc_admins)}` admins active\n\n🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}"
                                        safe_send_message(thread_id, admin_card, reply_to_item_id=message_id)
                                    except Exception:
                                        pass
                                    continue

                                if text_lower == "!security":
                                    sec_status = "🔒 LOCKED DOWN" if LOCKDOWN_MODE else "🟢 SECURE"
                                    sec_card = (
                                        f"🛡️🔒 𝗚𝗖 𝗦𝗘𝗖𝗨𝗥𝗜𝗧𝗬 • 𝗦𝗧𝗔𝗧𝗨𝗦 🔒🛡️\n\n"
                                        f"⚡ MODE ➜ {sec_status}\n"
                                        f"🚫 ABUSE / NSFW / LINKS ➜ `ACTIVE`\n\n"
                                        f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}"
                                    )
                                    safe_send_message(thread_id, sec_card, reply_to_item_id=message_id)
                                    continue

                except (LoginRequired, ChallengeRequired):
                    break
                except (PleaseWaitFewMinutes, ClientThrottledError):
                    time.sleep(15)
                except Exception:
                    time.sleep(POLL_INTERVAL)

                time.sleep(POLL_INTERVAL)

        except Exception:
            time.sleep(10)

if __name__ == "__main__":
    start_bot()
