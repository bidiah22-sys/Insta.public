import os
import re
import time
from datetime import datetime, timezone
from dotenv import load_dotenv
from instagrapi import Client
from instagrapi.exceptions import PleaseWaitFewMinutes, ClientThrottledError, LoginRequired, ChallengeRequired
from sqlalchemy import create_engine, Column, String, Integer, Float, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

# --- Credentials & Config ---
BOT_USERNAME = "bot0.0928"
BOT_PASSWORD = "SIDHU295"
SESSION_ID = "24360649417%3AvRVfBhx2zv7DT5%3A7%3AAYn9ArgOOM8UXnSdmdTLzUaS11Rvk5vfce-QeB32Vw" 

OWNER_USERNAME = "@fx_smw ✘ @aat_nnk25"
AUTHORIZED_DEVS = ["fx_smw", "aat_nnk", "aat_nnk25", "fx_sw"]
DATABASE_URL = "sqlite:///god_mode_bot.db"
POLL_INTERVAL = 0.5  # Hyper-fast response time (0.5s loop)

TARGETED_USERS = set()
LOCKDOWN_MODE = False
thread_known_members = {}
user_message_timestamps = {}
user_violation_tracker = {}

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

# --- God-Level Regex & Evasion Filters (Bypasses spelling tricks) ---
ADVANCED_ABUSE_PATTERNS = [
    r'm[\.\_\-\s]*c', r'b[\.\_\-\s]*c', r'm[\.\_\-\s]*k[\.\_\-\s]*c',
    r't[\.\_\-\s]*m[\.\_\-\s]*k[\.\_\-\s]*c', r'madar\s*chod', r'bhen\s*chod', 
    r'behen\s*chod', r'bhosd\w*', r'chut\w*', r'gand\w*', r'gaand\w*', r'lund\w*',
    r'lauda\w*', r'lawda\w*', r'randi\w*', r'bhadwa\w*', r'bhadwe\w*', r'bsdk\w*', 
    r'harami\w*', r'f[\.\_\-\s]*u[\.\_\-\s]*c[\.\_\-\s]*k', r'sex\w*', r'pussy\w*',
    r'dick\w*', r'cock\w*', r'porn\w*', r'xnxx\w*', r'xhamster\w*', r'chutiya\w*',
    r'gandu\w*', r'bhosdike', r'nude\w*', r'mujra\w*', r'bhabhi\w*'
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
    violation_count = Column(Integer, default=0)
    trust_score = Column(Float, default=100.0)

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
                profile = UserProfile(user_id=str(user_id), username=username.lower(), total_messages=1, trust_score=100.0)
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
    def record_violation(username: str):
        db = SessionLocal()
        try:
            clean_user = username.lstrip('@').lower()
            profile = db.query(UserProfile).filter(UserProfile.username == clean_user).first()
            if profile:
                profile.violation_count = (profile.violation_count or 0) + 1
                profile.trust_score = max(0.0, profile.trust_score - 50.0)
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
                return (
                    f"📊✨ 𝗚𝗢𝗗-𝗠𝗢𝗗𝗘 • 𝗨𝗦𝗘𝗥 𝗧𝗥𝗨𝗦𝗧 𝗖𝗔𝗥𝗗 ✨📊\n\n"
                    f"👤 𝗨𝗦𝗘𝗥 ➜ {fix_mention(profile.username)}\n"
                    f"🆔 𝗨𝗦𝗘𝗥 𝗜𝗗 ➜ `{profile.user_id}`\n"
                    f"💬 𝗧𝗢𝗧𝗔𝗟 𝗠𝗦𝗚𝗦 ➜ {profile.total_messages}\n"
                    f"🚫 𝗩𝗜𝗢𝗟𝗔𝗧𝗜𝗢𝗡𝗦 ➜ {profile.violation_count}\n"
                    f"💎 𝗧𝗥𝗨𝗦𝗧 𝗦𝗖𝗢𝗥𝗘 ➜ {profile.trust_score}%\n\n"
                    f"📈 𝗦𝗧𝗔𝗧𝗨𝗦 ➜ 𝗔𝗖𝗧𝗜𝗩𝗘 𝗠𝗘𝗠𝗕𝗘𝗥\n\n"
                    f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                    f"👑 𝗗𝗘𝗩 ➜ {OWNER_USERNAME}"
                )
            return (
                f"📊✨ 𝗚𝗢𝗗-𝗠𝗢𝗗𝗘 • 𝗨𝗦𝗘𝗥 𝗧𝗥𝗨𝗦𝗧 𝗖𝗔𝗥𝗗 ✨📊\n\n"
                f"❌ User {fix_mention(clean_user)} not registered yet!\n\n"
                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                f"👑 𝗗𝗘𝗩 ➜ {OWNER_USERNAME}"
            )
        finally:
            db.close()

    @staticmethod
    def get_top_chatters() -> str:
        db = SessionLocal()
        try:
            top_users = db.query(UserProfile).order_by(UserProfile.total_messages.desc()).limit(5).all()
            if not top_users:
                return f"🏆👑 𝗟𝗘𝗔𝗗𝗘𝗥𝗕𝗢𝗔𝗥𝗗 👑🏆\n\n⚠️ No active data found yet!\n\n🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}"
            
            list_str = ""
            medals = ["🥇", "🥈", "🥉", "🏅", "🏅"]
            for idx, u in enumerate(top_users, 1):
                list_str += f"{medals[idx-1]} {fix_mention(u.username)} ➜ `{u.total_messages}` msgs\n"

            return (
                f"🏆👑 𝗚𝗖 𝗔𝗖𝗧𝗜𝗩𝗜𝗧𝗬 • 𝗟𝗘𝗔𝗗𝗘𝗥𝗕𝗢𝗔𝗥𝗗 👑🏆\n\n"
                f"{list_str}\n"
                f"🔥 𝗞𝗘𝗘𝗣 𝗖𝗛𝗔𝗧𝗧𝗜𝗡𝗚 & 𝗥𝗢𝗖𝗞 𝗧𝗛𝗘 𝗚𝗖\n\n"
                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                f"👑 𝗗𝗘𝗩 ➜ {OWNER_USERNAME}"
            )
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
    global LOCKDOWN_MODE, TARGETED_USERS, thread_known_members, user_message_timestamps
    init_db()

    while True:
        try:
            print("[*] Initializing God-Mode Instagram Engine...")
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

            print(f"[+] SUCCESS: Bot @{BOT_USERNAME} GOD-MODE ACTIVE! 🚀🔥")

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
                time.sleep(0.15)

            def execute_kick(thread_id, target_pk, target_username, reason, admin_tags, reply_to_id=None):
                try:
                    cl.user_remove_from_thread(thread_id, target_pk)
                    kick_card = (
                        f"🚨⚡ 𝗚𝗢𝗗-𝗠𝗢𝗗𝗘 • 𝗜𝗡𝗦𝗧𝗔𝗡𝗧 𝗞𝗜𝗖𝗞 ⚡🚨\n\n"
                        f"👤 𝗢𝗙𝗙𝗘𝗡𝗗𝗘𝗥 ➜ {fix_mention(target_username)}\n"
                        f"🆔 𝗨𝗦𝗘𝗥 𝗜𝗗 ➜ `{target_pk}`\n"
                        f"🚫 𝗥𝗘𝗔𝗦𝗢𝗡 ➜ {reason}\n"
                        f"🛑 𝗦𝗧𝗔𝗧𝗨𝗦 ➜ 𝗣𝗘𝗥𝗠𝗔𝗡𝗘𝗡𝗧𝗟𝗬 𝗥𝗘𝗠𝗢𝗩𝗘𝗗\n\n"
                        f"📢 𝗔𝗗𝗠𝗜𝗡𝗦 ➜ {admin_tags}\n"
                        f"🛡️ 𝗚𝗖 𝗜𝗦 𝗡𝗢𝗪 𝗦𝗔𝗙𝗘 & 𝗦𝗘𝗖𝗨𝗥𝗘\n\n"
                        f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                        f"👑 𝗗𝗘𝗩 ➜ {OWNER_USERNAME}"
                    )
                    safe_send_message(thread_id, kick_card, reply_to_item_id=reply_to_id)
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
                            
                            # Welcome / Welcome Back Card
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
                                    f"🌷 𝗘𝗡𝗝𝗢𝗬 𝗬𝗢𝗨𝗥 𝗧𝗜𝗠𝗘 𝗜𝗡 𝗚𝗖 🌷\n\n"
                                    f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                    f"👑 𝗗𝗘𝗩 ➜ {OWNER_USERNAME}"
                                )
                                safe_send_message(thread_id, welcome_card)

                            # Goodbye Card
                            left_members = old_members - current_user_pks
                            for left_pk in left_members:
                                thread_known_members[thread_id].discard(left_pk)
                                goodbye_card = (
                                    f"🚪🏃‍♂️ 𝗚𝗢𝗢𝗗𝗕𝗬𝗘 • 𝗠𝗘𝗠𝗕𝗘𝗥 𝗟𝗘𝗙𝗧 🏃‍♂️🚪\n\n"
                                    f"👤 𝗨𝗦𝗘𝗥 𝗜𝗗 ➜ `{left_pk}`\n"
                                    f"👋 𝗦𝗧𝗔𝗧𝗨𝗦 ➜ 𝗟𝗘𝗙𝗧 𝗧𝗛𝗘 𝗚𝗖\n\n"
                                    f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                    f"👑 𝗗𝗘𝗩 ➜ {OWNER_USERNAME}"
                                )
                                safe_send_message(thread_id, goodbye_card)

                        # --- Morning Wish Card ---
                        if current_hour == 6 and last_morning_wish_date != current_date_str:
                            last_morning_wish_date = current_date_str
                            morning_card = (
                                f"☀️🌷 𝗚𝗢𝗢𝗗 𝗠𝗢𝗥𝗡𝗜𝗡𝗚, 𝗘𝗩𝗘𝗥𝗬𝗢𝗡𝗘! 🌷☀️\n\n"
                                f"✨ 𝗡𝗘𝗪 𝗗𝗔𝗬 • 𝗡𝗘𝗪 𝗚𝗢𝗔𝗟𝗦\n"
                                f"🚀 𝗦𝗧𝗔𝗬 𝗣𝗢𝗦𝗜𝗧𝗜𝗩𝗘 • 𝗦𝗧𝗔𝗬 𝗙𝗢𝗖𝗨𝗦𝗘𝗗\n\n"
                                f"🌸 𝗛𝗔𝗩𝗘 𝗔 𝗕𝗘𝗔𝗨𝗧𝗜𝗙𝗨𝗟 𝗗𝗔𝗬!\n\n"
                                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                f"👑 𝗗𝗘𝗩 ➜ {OWNER_USERNAME}"
                            )
                            safe_send_message(thread_id, morning_card)

                        # --- Night Wish Card ---
                        if current_hour == 23 and last_night_wish_date != current_date_str:
                            last_night_wish_date = current_date_str
                            night_card = (
                                f"🌙✨ 𝗚𝗢𝗢𝗗 𝗡𝗜𝗚𝗛𝗧, 𝗘𝗩𝗘𝗥𝗬𝗢𝗡𝗘! ✨🌙\n\n"
                                f"😴 𝗧𝗜𝗠𝗘 𝗧𝗢 𝗥𝗘𝗦𝗧 & 𝗥𝗘𝗖𝗛𝗔𝗥𝗚𝗘\n"
                                f"💫 𝗦𝗪𝗘𝗘𝗧 𝗗𝗥𝗘𝗔𝗠𝗦 • 𝗦𝗟𝗘𝗘𝗣 𝗪𝗘𝗟𝗟\n\n"
                                f"🌌 𝗦𝗘𝗘 𝗬𝗢𝗨 𝗔𝗟𝗟 𝗧𝗢𝗠𝗢𝗥𝗥𝗢𝗪!\n\n"
                                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                f"👑 𝗗𝗘𝗩 ➜ {OWNER_USERNAME}"
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
                                for u in users:
                                    if str(getattr(u, "pk", "")) == sender_id:
                                        sender_username = getattr(u, "username", "User")
                                        break

                                if sender_id == bot_pk:
                                    continue

                                is_dev = sender_username.lower() in [d.lower() for d in AUTHORIZED_DEVS]

                                ModerationEngine.record_activity(sender_id, sender_username)

                                # --- God-Tier Anti-Flood & Spam Protection ---
                                if not is_dev:
                                    current_t = time.time()
                                    if sender_id not in user_message_timestamps:
                                        user_message_timestamps[sender_id] = []
                                    user_message_timestamps[sender_id] = [t for t in user_message_timestamps[sender_id] if current_t - t < 4]
                                    user_message_timestamps[sender_id].append(current_t)
                                    
                                    if len(user_message_timestamps[sender_id]) > 4:
                                        execute_kick(thread_id, sender_id, sender_username, "God-Mode Anti-Flood Rapid Spam Triggered", admin_mentions_tag, reply_to_id=message_id)
                                        continue

                                if LOCKDOWN_MODE and not is_dev:
                                    execute_kick(thread_id, sender_id, sender_username, "GC LOCKDOWN MODE ACTIVE", admin_mentions_tag, reply_to_id=message_id)
                                    continue

                                if sender_username.lower() in TARGETED_USERS:
                                    execute_kick(thread_id, sender_id, sender_username, "TARGET ELIMINATED ON SIGHT", admin_mentions_tag, reply_to_id=message_id)
                                    continue

                                # --- ZERO-TOLERANCE SUPREME AUTO MODERATION ---
                                if not is_dev:
                                    is_abuse = is_abusive_text(text)
                                    
                                    # Reel, Link & Promotion Detection
                                    is_reel_or_link = any(kw in text_lower for kw in [
                                        "http://", "https://", "www.", "instagram.com", "t.me", "bit.ly", 
                                        "reel", "reels", "post", "share", "profile", "igtv", "story", "whatsapp"
                                    ]) or item_type in ["clip", "story_share", "media_share", "felix_share_target"]:
                                        
                                    # 18+ / NSFW Content, Media & Stickers Detection
                                    is_nsfw_content = (
                                        item_type in ["media", "visual_media", "raven_media", "sticker"] or
                                        any(word in text_lower for word in ['18+', 'adult', 'xxx', 'sex', 'porn', 'hot video', 'bra', 'panty', 'xnxx', 'xhamster', 'nude', 'mujra', 'bhabhi'])
                                    )

                                    if is_abuse or is_reel_or_link or is_nsfw_content:
                                        if is_abuse:
                                            violation_reason = "Advanced Abusive / Toxic Language Detected"
                                        elif is_reel_or_link:
                                            violation_reason = "Unauthorized Reel / External Link / Promotion"
                                        else:
                                            violation_reason = "18+ / NSFW Content / Forbidden Media / Sticker"

                                        ModerationEngine.record_violation(sender_username)
                                        execute_kick(thread_id, sender_id, sender_username, violation_reason, admin_mentions_tag, reply_to_id=message_id)
                                        continue

                                # --- COMMANDS & UTILITIES WITH REPLY CARDS ---
                                if text_lower == "!rules":
                                    if is_dev:
                                        rules_card = (
                                            f"⚜️🌷 𝗚𝗖 𝗥𝗨𝗟𝗘𝗦 • 𝗚𝗢𝗗-𝗠𝗢𝗗𝗘 🌷⚜️\n\n"
                                            f"🤝 𝗥𝗘𝗦𝗣𝗘𝗖𝗧 𝗘𝗩𝗘𝗥𝗬𝗢𝗡𝗘\n"
                                            f"💌 𝗞𝗘𝗘𝗣 𝗧𝗛𝗘 𝗩𝗜𝗕𝗘 𝗙𝗥𝗜𝗘𝗡𝗗𝗟𝗬\n\n"
                                            f"🚫 𝗡𝗢 𝗔𝗕𝗨𝗦𝗘 • 𝗡𝗢 𝗧𝗢𝗫𝗜𝗖𝗜𝗧𝗬\n"
                                            f"⚠️ 𝗗𝗥𝗔𝗠𝗔 & 𝗙𝗜𝗚𝗛𝗧𝗦 𝗔𝗥𝗘 𝗕𝗔𝗡𝗡𝗘𝗗\n\n"
                                            f"🔞 𝗡𝗢 𝗡𝗦𝗙𝗪 / 𝗔𝗗𝗨𝗟𝗧 𝗖𝗢𝗡𝗧𝗘𝗡𝗧 / 𝗦𝗧𝗜𝗖𝗞𝗘𝗥𝗦\n"
                                            f"🎥 𝗡𝗢 𝗥𝗘𝗘𝗟𝗦 / 𝗟𝗜𝗡𝗞𝗦 / 𝗣𝗥𝗢𝗠𝗢𝗧𝗜𝗢𝗡𝗦\n"
                                            f"🛡️ 𝗜𝗡𝗦𝗧𝗔𝗡𝗧 𝗞𝗜𝗖𝗞 𝗢𝗡 𝗕𝗥𝗘𝗔𝗖𝗛\n\n"
                                            f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                            f"👑 𝗗𝗘𝗩 ➜ {OWNER_USERNAME}"
                                        )
                                        safe_send_message(thread_id, rules_card, reply_to_item_id=message_id)
                                    else:
                                        safe_send_message(thread_id, f"⚠️🔒 **ACCESS DENIED**\n\n👤 𝗨𝗦𝗘𝗥 ➜ {fix_mention(sender_username)}\n❌ Developers Only Command\n\n🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}", reply_to_item_id=message_id)
                                    continue

                                if text_lower in ["!ping", "!alive"]:
                                    if is_dev:
                                        ping_card = (
                                            f"⚡🏓 𝗚𝗢𝗗-𝗠𝗢𝗗𝗘 • 𝗣𝗜𝗡𝗚 𝗖𝗛𝗘𝗖𝗞 🏓⚡\n\n"
                                            f"🚀 𝗦𝗧𝗔𝗧𝗨𝗦 ➜ 𝗨𝗟𝗧𝗥𝗔 𝗣𝗥𝗢 𝗠𝗔𝗫 𝗢𝗡𝗟𝗜𝗡𝗘\n"
                                            f"💨 𝗦𝗣𝗘𝗘𝗗 ➜ 𝟬.𝟭𝘀 (𝗜𝗡𝗦𝗧𝗔𝗡𝗧)\n"
                                            f"🛡️ 𝗦𝗘𝗖𝗨𝗥𝗜𝗧𝗬 ➜ 𝗚𝗢𝗗 𝗟𝗘𝗩𝗘𝗟\n\n"
                                            f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                            f"👑 𝗗𝗘𝗩 ➜ {OWNER_USERNAME}"
                                        )
                                        safe_send_message(thread_id, ping_card, reply_to_item_id=message_id)
                                    else:
                                        safe_send_message(thread_id, f"⚠️🔒 **ACCESS DENIED**\n\n👤 𝗨𝗦𝗘𝗥 ➜ {fix_mention(sender_username)}\n❌ Developers Only Command\n\n🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}", reply_to_item_id=message_id)
                                    continue

                                if text_lower == "!botinfo":
                                    if is_dev:
                                        info_card = (
                                            f"🤖📊 𝗕𝗢𝗧 𝗜𝗡𝗙𝗢 • 𝗚𝗢𝗗-𝗠𝗢𝗗𝗘 📊🤖\n\n"
                                            f"⚡ 𝗦𝗧𝗔𝗧𝗨𝗦 ➜ 𝟭𝟬𝟬% 𝗢𝗡𝗟𝗜𝗡𝗘\n"
                                            f"🛡️ 𝗠𝗢𝗗𝗘𝗥𝗔𝗧𝗜𝗢𝗡 ➜ 𝗛𝗬𝗣𝗘𝗥-𝗙𝗔𝗦𝗧 𝗔𝗨𝗧𝗢-𝗞𝗜𝗖𝗞\n"
                                            f"🔥 𝗔𝗕𝗨𝗦𝗘, 𝗥𝗘𝗘𝗟𝗦, 𝗟𝗜𝗡𝗞𝗦 & 𝟭𝟴+ 𝗙𝗜𝗟𝗧𝗘𝗥 ➜ 𝗔𝗖𝗧𝗜𝗩𝗘\n\n"
                                            f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                            f"👑 𝗗𝗘𝗩 ➜ {OWNER_USERNAME}"
                                        )
                                        safe_send_message(thread_id, info_card, reply_to_item_id=message_id)
                                    else:
                                        safe_send_message(thread_id, f"⚠️🔒 **ACCESS DENIED**\n\n👤 𝗨𝗦𝗘𝗥 ➜ {fix_mention(sender_username)}\n❌ Developers Only Command\n\n🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}", reply_to_item_id=message_id)
                                    continue

                                if text_lower in ["!help", "!commands", "!menu"]:
                                    if is_dev:
                                        help_card = (
                                            f"📜🤖 𝗚𝗢𝗗-𝗠𝗢𝗗𝗘 • 𝗖𝗢𝗠𝗠𝗔𝗡𝗗𝗦 𝗟𝗜𝗦𝗧 🤖📜\n\n"
                                            f"🛠️ 𝗗𝗘𝗩 𝗖𝗢𝗠𝗠𝗔𝗡𝗗𝗦 ➜\n"
                                            f"➜ `!rules` : Show GC Rules\n"
                                            f"➜ `!ping` / `!alive` : Check Bot Speed\n"
                                            f"➜ `!botinfo` : System Status\n"
                                            f"➜ `!dp <username>` : Download HD DP\n"
                                            f"➜ `!stats <username>` : User Trust Score\n"
                                            f"➜ `!topchatters` : GC Activity Leaderboard\n"
                                            f"➜ `!profile <username>` : Deep Profile Info\n"
                                            f"➜ `!members` : Member List Count\n"
                                            f"➜ `!admins` : Admin List Count\n"
                                            f"➜ `!lockdown` / `!unlock` : GC Security Mode\n"
                                            f"➜ `!target <username>` : Permanent Kill on Sight\n\n"
                                            f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                            f"👑 𝗗𝗘𝗩 ➜ {OWNER_USERNAME}"
                                        )
                                        safe_send_message(thread_id, help_card, reply_to_item_id=message_id)
                                    else:
                                        safe_send_message(thread_id, f"⚠️🔒 **ACCESS DENIED**\n\n👤 𝗨𝗦𝗘𝗥 ➜ {fix_mention(sender_username)}\n❌ Developers Only Command\n\n🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}", reply_to_item_id=message_id)
                                    continue

                                if text_lower.startswith("!dp"):
                                    if is_dev:
                                        parts = text.split()
                                        target_name = parts[1].lstrip('@') if len(parts) > 1 else sender_username
                                        try:
                                            u_info = cl.user_info_by_username(target_name)
                                            if u_info:
                                                dp_url = getattr(getattr(u_info, 'hd_profile_pic_url_info', None), 'url', None) or getattr(u_info, 'profile_pic_url_hd', None) or u_info.profile_pic_url
                                                photo_path = cl.photo_download_by_url(dp_url, filename=f"{target_name}_dp.jpg")
                                                cl.direct_send_photo(photo_path, thread_ids=[thread_id])
                                                
                                                dp_card = (
                                                    f"📸✨ 𝗛𝗗 𝗗𝗣 • 𝗗𝗢𝗪𝗡𝗟𝗢𝗔𝗗𝗘𝗗 ✨📸\n\n"
                                                    f"👤 𝗨𝗦𝗘𝗥 ➜ {fix_mention(target_name)}\n"
                                                    f"✅ 𝗦𝗧𝗔𝗧𝗨𝗦 ➜ 𝗦𝗘𝗡𝗧 𝗦𝗨𝗖𝗖𝗘𝗦𝗦𝗙𝗨𝗟𝗟𝗬\n\n"
                                                    f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                                    f"👑 𝗗𝗘𝗩 ➜ {OWNER_USERNAME}"
                                                )
                                                safe_send_message(thread_id, dp_card, reply_to_item_id=message_id)
                                                if os.path.exists(photo_path):
                                                    os.remove(photo_path)
                                            else:
                                                safe_send_message(thread_id, f"❌📸 User {fix_mention(target_name)} not found!", reply_to_item_id=message_id)
                                        except Exception:
                                            safe_send_message(thread_id, f"❌📸 DP Fetch Error Occurred!", reply_to_item_id=message_id)
                                    else:
                                        safe_send_message(thread_id, f"⚠️🔒 **ACCESS DENIED**\n\n👤 𝗨𝗦𝗘𝗥 ➜ {fix_mention(sender_username)}\n❌ Developers Only Command", reply_to_item_id=message_id)
                                    continue

                                if text_lower.startswith("!stats"):
                                    if is_dev:
                                        parts = text.split()
                                        target_name = parts[1].lstrip('@') if len(parts) > 1 else sender_username
                                        stats_msg = ModerationEngine.get_user_stats(target_name)
                                        safe_send_message(thread_id, stats_msg, reply_to_item_id=message_id)
                                    else:
                                        safe_send_message(thread_id, f"⚠️🔒 **ACCESS DENIED**", reply_to_item_id=message_id)
                                    continue

                                if text_lower in ["!topchatters", "!leaderboard", "!active"]:
                                    if is_dev:
                                        leaderboard_msg = ModerationEngine.get_top_chatters()
                                        safe_send_message(thread_id, leaderboard_msg, reply_to_item_id=message_id)
                                    else:
                                        safe_send_message(thread_id, f"⚠️🔒 **ACCESS DENIED**", reply_to_item_id=message_id)
                                    continue

                                if text_lower.startswith("!userinfo") or text_lower.startswith("!profile"):
                                    if is_dev:
                                        parts = text.split()
                                        target_name = parts[1].lstrip('@') if len(parts) > 1 else sender_username
                                        try:
                                            u_info = cl.user_info_by_username(target_name)
                                            if u_info:
                                                full_name = getattr(u_info, 'full_name', 'N/A')
                                                followers = getattr(u_info, 'follower_count', 0)
                                                following = getattr(u_info, 'following_count', 0)
                                                is_private = "Yes 🔒" if getattr(u_info, 'is_private', False) else "No 🔓"
                                                is_verified = "Yes ✅" if getattr(u_info, 'is_verified', False) else "No ❌"
                                                
                                                profile_card = (
                                                    f"👤📋 𝗨𝗦𝗘𝗥 • 𝗣𝗥𝗢𝗙𝗜𝗟𝗘 𝗜𝗡𝗙𝗢 📋👤\n\n"
                                                    f"📌 𝗡𝗔𝗠𝗘 ➜ {full_name}\n"
                                                    f"🏷️ 𝗨𝗦𝗘𝗥𝗡𝗔𝗠𝗘 ➜ {fix_mention(target_name)}\n"
                                                    f"🆔 𝗨𝗦𝗘𝗥 𝗜𝗗 ➜ `{u_info.pk}`\n"
                                                    f"👥 𝗙𝗢𝗟𝗟𝗢𝗪𝗘𝗥𝗦 ➜ {followers}\n"
                                                    f"👣 𝗙𝗢𝗟𝗟𝗢𝗪𝗜𝗡𝗚 ➜ {following}\n"
                                                    f"🔒 𝗣𝗥𝗜𝗩𝗔𝗧𝗘 ➜ {is_private}\n"
                                                    f"☑️ 𝗩𝗘𝗥𝗜𝗙𝗜𝗘𝗗 ➜ {is_verified}\n\n"
                                                    f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                                    f"👑 𝗗𝗘𝗩 ➜ {OWNER_USERNAME}"
                                                )
                                                safe_send_message(thread_id, profile_card, reply_to_item_id=message_id)
                                            else:
                                                safe_send_message(thread_id, f"❌ User {fix_mention(target_name)} not found!", reply_to_item_id=message_id)
                                        except Exception:
                                            safe_send_message(thread_id, f"❌ Profile Fetch Error!", reply_to_item_id=message_id)
                                    else:
                                        safe_send_message(thread_id, f"⚠️🔒 **ACCESS DENIED**", reply_to_item_id=message_id)
                                    continue

                                if text_lower in ["!members", "!memberlist"]:
                                    if is_dev:
                                        try:
                                            total_count = len(users)
                                            member_usernames = [fix_mention(getattr(u, "username", "User")) for u in users if getattr(u, "username", None)]
                                            members_str = ", ".join(member_usernames[:25])
                                            if len(member_usernames) > 25:
                                                members_str += f" ...and {len(member_usernames) - 25} more"

                                            members_card = (
                                                f"👥📊 𝗚𝗥𝗢𝗨𝗣 • 𝗠𝗘𝗠𝗕𝗘𝗥𝗦 𝗟𝗜𝗦𝗧 📊👥\n\n"
                                                f"📊 𝗧𝗢𝗧𝗔𝗟 𝗠𝗘𝗠𝗕𝗘𝗥𝗦 ➜ `{total_count}`\n"
                                                f"📝 𝗠𝗘𝗠𝗕𝗘𝗥𝗦 ➜ {members_str}\n\n"
                                                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                                f"👑 𝗗𝗘𝗩 ➜ {OWNER_USERNAME}"
                                            )
                                            safe_send_message(thread_id, members_card, reply_to_item_id=message_id)
                                        except Exception:
                                            safe_send_message(thread_id, f"❌ Error fetching members!", reply_to_item_id=message_id)
                                    else:
                                        safe_send_message(thread_id, f"⚠️🔒 **ACCESS DENIED**", reply_to_item_id=message_id)
                                    continue

                                if text_lower in ["!admins", "!adminlist"]:
                                    if is_dev:
                                        try:
                                            admin_names = []
                                            for u in users:
                                                if str(getattr(u, "pk", "")) in admin_ids_str:
                                                    un = getattr(u, "username", None)
                                                    if un:
                                                        admin_names.append(f"👑 ➜ {fix_mention(un)}")
                                            
                                            admin_list_str = "\n".join(admin_names) if admin_names else "👑 ➜ Admins active"
                                            admin_card = (
                                                f"👑🛡️ 𝗢𝗙𝗙𝗜𝗖𝗜𝗔𝗟 • 𝗚𝗖 𝗔𝗗𝗠𝗜𝗡𝗦 🛡️👑\n\n"
                                                f"📊 𝗧𝗢𝗧𝗔𝗟 𝗔𝗗𝗠𝗜𝗡𝗦 ➜ {len(gc_admins)}\n"
                                                f"✨ 𝗔𝗖𝗧𝗜𝗩𝗘 𝗟𝗜𝗦𝗧 ➜\n{admin_list_str}\n\n"
                                                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                                f"👑 𝗗𝗘𝗩 ➜ {OWNER_USERNAME}"
                                            )
                                            safe_send_message(thread_id, admin_card, reply_to_item_id=message_id)
                                        except Exception:
                                            safe_send_message(thread_id, f"❌ Error fetching admins!", reply_to_item_id=message_id)
                                    else:
                                        safe_send_message(thread_id, f"⚠️🔒 **ACCESS DENIED**", reply_to_item_id=message_id)
                                    continue

                                if is_dev:
                                    if text_lower == "!lockdown":
                                        LOCKDOWN_MODE = True
                                        safe_send_message(thread_id, f"🚨🔒 **LOCKDOWN ACTIVATED**\n\nNon-dev messages will be kicked instantly.\n\n🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}", reply_to_item_id=message_id)
                                        continue
                                    elif text_lower == "!unlock":
                                        LOCKDOWN_MODE = False
                                        safe_send_message(thread_id, f"🔓✨ **LOCKDOWN DEACTIVATED**\n\nGroup back to normal.\n\n🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}", reply_to_item_id=message_id)
                                        continue
                                    elif text_lower.startswith("!target"):
                                        parts = text.split()
                                        if len(parts) > 1:
                                            target = parts[1].lstrip('@').lower()
                                            TARGETED_USERS.add(target)
                                            safe_send_message(thread_id, f"🎯🎯 **TARGET LOCKED**\n\nUser {fix_mention(target)} will be kicked on sight.\n\n🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}", reply_to_item_id=message_id)
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
