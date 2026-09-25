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
SESSION_ID = "24360649417%3AdvTl2cIVjUGYKS%3A7%3AAYlLz9DoDZNK9nOVVQpgGsoTS6bkcCp5wISgktflKg" 

OWNER_USERNAME = "fx_smw ✘ aat_nnk25"
AUTHORIZED_DEVS = ["fx_smw", "aat_nnk", "aat_nnk25", "fx_sw"]
DATABASE_URL = "sqlite:///bot_database.db"
POLL_INTERVAL = 3  # Super fast response time

SHADOWBANNED_USERS = set()
TARGETED_USERS = set()
LOCKDOWN_MODE = False
INITIALIZED_THREADS = set()  # To track threads so existing members aren't welcomed on bot start

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
    r'harami\w*', r'f[\.\_\-\s]*u[\.\_\-\s]*c[\.\_\-\s]*k\w*', r'sex\w*', r'pussy\w*',
    r'dick\w*', r'cock\w*', r'porn\w*', r'xnxx\w*', r'xhamster\w*'
]

RESTRICTED_WORDS = set([
    'mc', 'bc', 'mkc', 'tmkc', 'bsdk', 'bsdke', 'chutiya', 'chutiye', 'chutiyap', 
    'gandu', 'gaandu', 'lauda', 'luda', 'lawda', 'lund', 'chut', 'chuth', 
    'gand', 'gaand', 'randi', 'randwa', 'bhadwa', 'bhadwe', 'harami', 'haramkhor', 
    'kamine', 'kamina', 'saala', 'saale', 'madarchod', 'maderchod', 'madar-chod', 
    'bhenchod', 'behenchod', 'bhen-chod', 'behen-chod', 'bhosdike', 'bhosdi', 'bhosda',
    'fuck', 'fucking', 'fucker', 'motherfucker', 'bitch', 'bastard', 'asshole',
    'sex', 'porn', 'xnxx', 'xhamster', 'hotvideo', '18plus', 'xxx'
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
                    f"📊✨ **𝗨𝗦𝗘𝗥 𝗦𝗧𝗔𝗧𝗦 𝗖𝗔𝗥𝗗** ✨📊\n\n"
                    f"👤 **𝗨𝗦𝗘𝗥** ➜ {fix_mention(profile.username)}\n"
                    f"🆔 **𝗨𝗦𝗘𝗥 𝗜𝗗** ➜ `{profile.user_id}`\n"
                    f"💬 **𝗧𝗢𝗧𝗔𝗟 𝗠𝗦𝗚𝗦** ➜ {profile.total_messages}\n"
                    f"⚠️ **𝗪𝗔𝗥𝗡𝗜𝗡𝗚𝗦** ➜ {profile.warning_count}/3\n"
                    f"🚫 **𝗩𝗜𝗢𝗟𝗔𝗧𝗜𝗢𝗡𝗦** ➜ {profile.violation_count}\n"
                    f"💎 **𝗧𝗥𝗨𝗦𝗧 𝗦𝗖𝗢𝗥𝗘** ➜ {profile.trust_score}%\n"
                    f"📈 **𝗦𝗖𝗢𝗥𝗘 𝗕𝗔𝗥** ➜ [{bar}]\n\n"
                    f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                    f"👨‍💻 𝗗𝗘𝗩𝗦 ➜ {OWNER_USERNAME}"
                )
            return f"❌ User {fix_mention(clean_user)} is not registered in Database!"
        finally:
            db.close()

def is_abusive_text(text: str) -> bool:
    text_lower = text.lower()
    words_in_text = re.findall(r'\b\w+\b', text_lower)
    for word in words_in_text:
        if word in RESTRICTED_WORDS:
            return True
    for pattern in BAD_WORD_PATTERNS:
        if re.search(pattern, text_lower):
            return True
    return False

def start_bot():
    global LOCKDOWN_MODE, SHADOWBANNED_USERS, TARGETED_USERS, INITIALIZED_THREADS
    init_db()

    while True:
        try:
            print("[*] Initializing Instagram Client...")
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

            print(f"[+] SUCCESS: Bot @{BOT_USERNAME} IS LIVE & SUPER FAST! 🚀⚡")

            seen_message_ids = set()
            last_morning_wish_date = ""
            last_night_wish_date = ""
            recent_sent_texts = {}
            thread_known_members = {}

            def safe_send_message(thread_id, text_content):
                current_time = time.time()
                if thread_id in recent_sent_texts:
                    last_text, last_time = recent_sent_texts[thread_id]
                    if last_text == text_content and (current_time - last_time < 1):
                        return
                recent_sent_texts[thread_id] = (text_content, current_time)
                try:
                    cl.direct_send(text_content, thread_ids=[thread_id])
                except Exception:
                    pass
                time.sleep(0.5)

            def execute_kick(thread_id, target_pk, target_username, reason, admin_tags, silent=False):
                try:
                    cl.user_remove_from_thread(thread_id, target_pk)
                    if not silent:
                        kick_card = (
                            f"🚨🚪 **𝗔𝗨𝗧𝗢-𝗞𝗜𝗖𝗞 𝗖𝗔𝗥𝗗** 🚪🚨\n\n"
                            f"👤 𝗢𝗙𝗙𝗘𝗡𝗗𝗘𝗥 ➜ {fix_mention(target_username)}\n"
                            f"🆔 𝗨𝗦𝗘𝗥 𝗜𝗗  ➜ `{target_pk}`\n"
                            f"🚫 𝗥𝗘𝗔𝗦𝗢𝗡   ➜ {reason}\n"
                            f"🛑 𝗔𝗖𝗧𝗜𝗢𝗡   ➜ REMOVED PERMANENTLY!\n\n"
                            f"📢 **𝗔𝗗𝗠𝗜𝗡𝗦** ➜ {admin_tags}\n\n"
                            f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                            f"👨‍💻 𝗗𝗘𝗩𝗦 ➜ {OWNER_USERNAME}"
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
                        except Exception:
                            gc_admins = []

                        bot_pk = str(cl.user_id)
                        users = list(getattr(thread, "users", []) or [])
                        admin_ids_str = {str(x) for x in gc_admins}
                        admin_mentions_tag = get_admin_mentions_str(users, gc_admins)

                        # --- Smart Welcome System (Only welcomes NEW members joining after bot starts) ---
                        current_user_pks = {str(getattr(u, "pk", "")) for u in users if str(getattr(u, "pk", "")) != bot_pk}
                        if thread_id not in thread_known_members:
                            # First time seeing this thread during this session, cache existing members without welcoming them
                            thread_known_members[thread_id] = current_user_pks
                        else:
                            new_members = current_user_pks - thread_known_members[thread_id]
                            for new_pk in new_members:
                                thread_known_members[thread_id].add(new_pk)
                                new_username = "User"
                                for u in users:
                                    if str(getattr(u, "pk", "")) == new_pk:
                                        new_username = getattr(u, "username", "User")
                                        break
                                welcome_card = (
                                    f"👋✨ **𝗪𝗘𝗟𝗖𝗢𝗠𝗘 𝗧𝗢 𝗧𝗛𝗘 𝗚𝗖!** ✨👋\n\n"
                                    f"👤 𝗡𝗘𝗪 𝗠𝗘𝗠𝗕𝗘𝗥 ➜ {fix_mention(new_username)}\n"
                                    f"🌟 𝗚𝗟𝗔𝗗 𝗧𝗢 𝗛𝗔𝗩𝗘 𝗬𝗢𝗨 𝗛𝗘𝗥𝗘!\n"
                                    f"📜 𝗣𝗟𝗘𝗔𝗦𝗘 𝗖𝗛𝗘𝗖𝗞 `!rules`!\n\n"
                                    f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                    f"👨‍💻 𝗗𝗘𝗩𝗦 ➜ {OWNER_USERNAME}"
                                )
                                safe_send_message(thread_id, welcome_card)

                        # --- Morning Wish Card ---
                        if current_hour == 6 and last_morning_wish_date != current_date_str:
                            last_morning_wish_date = current_date_str
                            morning_card = (
                                f"🌅✨ **𝗚𝗢𝗢𝗗 𝗠𝗢𝗥𝗡𝗜𝗡𝗚 𝗖𝗔𝗥𝗗** ✨🌅\n\n"
                                f"🌻 𝗛𝗔𝗩𝗘 𝗔𝗡 𝗔𝗠𝗔𝗭𝗜𝗡𝗚 & 𝗣𝗥𝗢𝗗𝗨𝗖𝗧𝗜𝗩𝗘 𝗗𝗔𝗬!\n"
                                f"☕ 𝗦𝗣𝗥𝗘𝗔𝗗 𝗣𝗢𝗦𝗜𝗧𝗜𝗩𝗜𝗧𝗬 𝗜𝗡 𝗧𝗛𝗘 𝗚𝗖 🔥\n\n"
                                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                f"👨‍💻 𝗗𝗘𝗩𝗦 ➜ {OWNER_USERNAME}"
                            )
                            safe_send_message(thread_id, morning_card)

                        # --- Night Wish Card ---
                        if current_hour == 23 and last_night_wish_date != current_date_str:
                            last_night_wish_date = current_date_str
                            night_card = (
                                f"🌙✨ **𝗚𝗢𝗢𝗗 𝗡𝗜𝗚𝗛𝗧 𝗖𝗔𝗥𝗗** ✨🌙\n\n"
                                f"😴 𝗧𝗜𝗠𝗘 𝗧𝗢 𝗥𝗘𝗦𝗧 & 𝗥𝗘𝗖𝗛𝗔𝗥𝗚𝗘!\n"
                                f"💫 𝗦𝗪𝗘𝗘𝗧 𝗗𝗥𝗘𝗔𝗠𝗦 𝗘𝗩𝗘𝗥𝗬𝗢𝗡𝗘 🌙\n\n"
                                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                f"👨‍💻 𝗗𝗘𝗩𝗦 ➜ {OWNER_USERNAME}"
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

                                is_sender_admin = sender_id in admin_ids_str
                                is_dev = sender_username.lower() in [d.lower() for d in AUTHORIZED_DEVS]

                                ModerationEngine.record_activity(sender_id, sender_username)

                                if LOCKDOWN_MODE and not is_dev:
                                    execute_kick(thread_id, sender_id, sender_username, "GC LOCKDOWN ACTIVE", admin_mentions_tag)
                                    continue

                                if sender_username.lower() in TARGETED_USERS:
                                    execute_kick(thread_id, sender_id, sender_username, "TARGET ELIMINATED", admin_mentions_tag)
                                    continue

                                # --- Strict Auto-Moderation ---
                                if not is_dev:
                                    is_abuse = is_abusive_text(text)
                                    is_unauthorized_link = "instagram.com/reel" in text_lower or "http" in text_lower or "www." in text_lower

                                    if is_abuse or is_unauthorized_link:
                                        warns, trust = ModerationEngine.add_warning(sender_username)
                                        reason = "Abusive Language / 18+ Content" if is_abuse else "Unauthorized Links / Reels Promotion"

                                        if warns >= 3:
                                            execute_kick(thread_id, sender_id, sender_username, f"3 Warnings Reached ({reason})", admin_mentions_tag)
                                        else:
                                            warn_card = (
                                                f"⚠️🚨 **𝗩𝗜𝗢𝗟𝗔𝗧𝗜𝗢𝗡 𝗪𝗔𝗥𝗡𝗜𝗡𝗚 𝗖𝗔𝗥𝗗** 🚨⚠️\n\n"
                                                f"👤 𝗢𝗙𝗙𝗘𝗡𝗗𝗘𝗥 ➜ {fix_mention(sender_username)}\n"
                                                f"🚫 𝗥𝗘𝗔𝗦𝗢𝗡   ➜ {reason}\n"
                                                f"⚠️ 𝗪𝗔𝗥𝗡𝗜𝗡𝗚𝗦 ➜ {warns}/3\n"
                                                f"📉 𝗧𝗥𝗨𝗦𝗧 𝗦𝗖𝗢𝗥𝗘 ➜ {trust}%\n\n"
                                                f"📢 **𝗔𝗗𝗠𝗜𝗡𝗦 𝗔𝗟𝗘𝗥𝗧** ➜ {admin_mentions_tag}\n\n"
                                                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                                f"👨‍💻 𝗗𝗘𝗩𝗦 ➜ {OWNER_USERNAME}"
                                            )
                                            safe_send_message(thread_id, warn_card)
                                        continue

                                # --- COMMANDS (Strictly restricted to Developers Only: fx_smw & aat_nnk25) ---

                                # 1. MEMBERS LIST COMMAND
                                if text_lower in ["!members", "!memberlist"]:
                                    if is_dev:
                                        try:
                                            total_count = len(users)
                                            member_usernames = [fix_mention(getattr(u, "username", "User")) for u in users if getattr(u, "username", None)]
                                            members_str = ", ".join(member_usernames[:30])
                                            if len(member_usernames) > 30:
                                                members_str += f" ...and {len(member_usernames) - 30} more"

                                            members_card = (
                                                f"👥✨ **𝗚𝗥𝗢𝗨𝗣 𝗠𝗘𝗠𝗕𝗘𝗥𝗦 𝗖𝗔𝗥𝗗** ✨👥\n\n"
                                                f"📊 **𝗧𝗼𝘁𝗮𝗹 𝗠𝗲𝗺𝗯𝗲𝗿𝘀** ➜ `{total_count}`\n"
                                                f"📝 **𝗠𝗲𝗺𝗯𝗲𝗿𝘀 𝗟𝗶𝘀𝘁** ➜ {members_str}\n\n"
                                                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                                f"👨‍💻 𝗗𝗘𝗩𝗦 ➜ {OWNER_USERNAME}"
                                            )
                                            safe_send_message(thread_id, members_card)
                                        except Exception as e:
                                            safe_send_message(thread_id, f"❌ Error: {e}")
                                    else:
                                        safe_send_message(thread_id, "⚠️ **Access Denied:** Developers only!")
                                    continue

                                # 2. ADMINS LIST COMMAND
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
                                                f"👑🛡️ **𝗢𝗙𝗙𝗜𝗖𝗜𝗔𝗟 𝗚𝗖 𝗔𝗗𝗠𝗜𝗡𝗦 𝗖𝗔𝗥𝗗** 🛡️👑\n\n"
                                                f"📊 **𝗧𝗢𝗧𝗔𝗟 𝗔𝗗𝗠𝗜𝗡𝗦** ➜ {len(gc_admins)}\n\n"
                                                f"✨ **𝗔𝗖𝗧𝗜𝗩𝗘 𝗔𝗗𝗠𝗜𝗡𝗦**:\n{admin_list_str}\n\n"
                                                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                                f"👨‍💻 𝗗𝗘𝗩𝗦 ➜ {OWNER_USERNAME}"
                                            )
                                            safe_send_message(thread_id, admin_card)
                                        except Exception as e:
                                            safe_send_message(thread_id, f"❌ Error: {e}")
                                    else:
                                        safe_send_message(thread_id, "⚠️ **Access Denied:** Developers only!")
                                    continue

                                # 3. SONG COMMAND
                                if text_lower.startswith("!song"):
                                    if is_dev:
                                        song_name = text[5:].strip()
                                        if song_name:
                                            yt_url = f"https://music.youtube.com/search?q={song_name.replace(' ', '+')}"
                                            spotify_url = f"https://open.spotify.com/search/{song_name.replace(' ', '%20')}"
                                            song_card = (
                                                f"🎵✨ **𝗦𝗢𝗡𝗚 & 𝗠𝗨𝗦𝗜𝗖 𝗖𝗔𝗥𝗗** ✨🎵\n\n"
                                                f"🎧 **𝗦𝗼𝗻𝗴** ➜ {song_name}\n"
                                                f"▶️ **YouTube Music** ➜ {yt_url}\n"
                                                f"🟢 **Spotify** ➜ {spotify_url}\n\n"
                                                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                                f"👨‍💻 𝗗𝗘𝗩𝗦 ➜ {OWNER_USERNAME}"
                                            )
                                            safe_send_message(thread_id, song_card)
                                        else:
                                            safe_send_message(thread_id, "⚠️ **Usage:** `!song <song name>`")
                                    else:
                                        safe_send_message(thread_id, "⚠️ **Access Denied:** Developers only!")
                                    continue

                                # 4. DP COMMAND
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
                                                    f"📸✨ **𝗛𝗗 𝗗𝗣 𝗖𝗔𝗥𝗗** ✨📸\n\n"
                                                    f"👤 **𝗨𝗦𝗘𝗥** ➜ {fix_mention(target_name)}\n"
                                                    f"✅ **𝗦𝗧𝗔𝗧𝗨𝗦** ➜ High Quality DP Sent!\n\n"
                                                    f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                                    f"👨‍💻 𝗗𝗘𝗩𝗦 ➜ {OWNER_USERNAME}"
                                                )
                                                safe_send_message(thread_id, dp_card)
                                                if os.path.exists(photo_path):
                                                    os.remove(photo_path)
                                            else:
                                                safe_send_message(thread_id, f"❌ Failed to fetch DP for {fix_mention(target_name)}!")
                                        except Exception:
                                            safe_send_message(thread_id, f"❌ DP Fetch Error!")
                                    else:
                                        safe_send_message(thread_id, "⚠️ **Access Denied:** Developers only!")
                                    continue

                                # 5. STATS COMMAND
                                if text_lower.startswith("!stats"):
                                    if is_dev:
                                        parts = text.split()
                                        target_name = parts[1].lstrip('@') if len(parts) > 1 else sender_username
                                        stats_msg = ModerationEngine.get_user_stats(target_name)
                                        safe_send_message(thread_id, stats_msg)
                                    else:
                                        safe_send_message(thread_id, "⚠️ **Access Denied:** Developers only!")
                                    continue

                                # 6. DETAILED USER INFO / PROFILE COMMAND
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
                                                biography = getattr(u_info, 'biography', 'No Bio')
                                                is_private = "Yes 🔒" if getattr(u_info, 'is_private', False) else "No 🔓"
                                                is_verified = "Yes ✅" if getattr(u_info, 'is_verified', False) else "No ❌"
                                                external_url = getattr(u_info, 'external_url', 'None')
                                                
                                                profile_card = (
                                                    f"👤📋 **𝗗𝗘𝗧𝗔𝗜𝗟𝗘𝗗 𝗨𝗦𝗘𝗥 𝗣𝗥𝗢𝗙𝗜𝗟𝗘 𝗖𝗔𝗥𝗗** 📋👤\n\n"
                                                    f"📌 **𝗡𝗮𝗺𝗲** ➜ {full_name}\n"
                                                    f"🏷️ **𝗨𝘀𝗲𝗿𝗻𝗮𝗺𝗲** ➜ {fix_mention(target_name)}\n"
                                                    f"🆔 **𝗨𝗦𝗘𝗥 𝗜𝗗** ➜ `{u_info.pk}`\n"
                                                    f"👥 **𝗙𝗼𝗹𝗹𝗼𝘄𝗲𝗿𝘀** ➜ {followers}\n"
                                                    f"👣 **𝗙𝗼𝗹𝗹𝗼𝘄𝗶𝗻𝗴** ➜ {following}\n"
                                                    f"🔒 **𝗣𝗿𝗶𝘃𝗮𝘁𝗲** ➜ {is_private}\n"
                                                    f"☑️ **𝗩𝗲𝗿𝗶𝗳𝗶𝗲𝗱** ➜ {is_verified}\n"
                                                    f"🔗 **𝗟𝗶𝗻𝗸** ➜ {external_url}\n"
                                                    f"📝 **𝗕𝗶𝗼𝗴𝗿𝗮𝗽𝗵𝘆** ➜ \n{biography}\n\n"
                                                    f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                                    f"👨‍💻 𝗗𝗘𝗩𝗦 ➜ {OWNER_USERNAME}"
                                                )
                                                safe_send_message(thread_id, profile_card)
                                            else:
                                                safe_send_message(thread_id, f"❌ User {fix_mention(target_name)} not found!")
                                        except Exception as e:
                                            safe_send_message(thread_id, f"❌ Error fetching profile info: {e}")
                                    else:
                                        safe_send_message(thread_id, "⚠️ **Access Denied:** Developers only!")
                                    continue

                                # 7. RULES COMMAND
                                if text_lower == "!rules":
                                    if is_dev:
                                        rules_card = (
                                            f"📜✨ **𝗚𝗖 𝗥𝗨𝗟𝗘𝗦 𝗖𝗔𝗥𝗗** ✨📜\n\n"
                                            f"1️⃣ No Abusive Words / 18+ Toxicity\n"
                                            f"2️⃣ No Spam Links or Reels Promotion\n"
                                            f"3️⃣ Respect All Members & Admins\n"
                                            f"4️⃣ 3 Warnings = Automatic Kick!\n\n"
                                            f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                            f"👨‍💻 𝗗𝗘𝗩𝗦 ➜ {OWNER_USERNAME}"
                                        )
                                        safe_send_message(thread_id, rules_card)
                                    else:
                                        safe_send_message(thread_id, "⚠️ **Access Denied:** Developers only!")
                                    continue

                                # 8. BOT INFO COMMAND
                                if text_lower == "!botinfo":
                                    if is_dev:
                                        info_card = (
                                            f"🤖✨ **𝗕𝗢𝗧 𝗜𝗡𝗙𝗢 𝗖𝗔𝗥𝗗** ✨🤖\n\n"
                                            f"⚡ **Status** ➜ ONLINE & ULTRA FAST\n"
                                            f"🛡️ **Security** ➜ Anti-Abuse & Auto-Kick ON\n"
                                            f"👨‍💻 **Developers** ➜ {OWNER_USERNAME}\n\n"
                                            f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}"
                                        )
                                        safe_send_message(thread_id, info_card)
                                    else:
                                        safe_send_message(thread_id, "⚠️ **Access Denied:** Developers only!")
                                    continue

                                # Dev Control Commands (Strictly Developer Only)
                                if is_dev:
                                    if text_lower == "!lockdown":
                                        LOCKDOWN_MODE = True
                                        safe_send_message(thread_id, f"🚨 **LOCKDOWN ACTIVATED:** Non-dev messages will be kicked. 👨‍💻 **DEVS:** {OWNER_USERNAME}")
                                        continue
                                    elif text_lower == "!unlock":
                                        LOCKDOWN_MODE = False
                                        safe_send_message(thread_id, f"🔓 **LOCKDOWN DEACTIVATED:** Group is normal. 👨‍💻 **DEVS:** {OWNER_USERNAME}")
                                        continue
                                    elif text_lower.startswith("!target"):
                                        parts = text.split()
                                        if len(parts) > 1:
                                            target = parts[1].lstrip('@').lower()
                                            TARGETED_USERS.add(target)
                                            safe_send_message(thread_id, f"🎯 Target Added: {fix_mention(target)} | 👨‍💻 **DEVS:** {OWNER_USERNAME}")
                                        continue
                                    elif text_lower.startswith("!resetwarn") or text_lower.startswith("!unwarn"):
                                        parts = text.split()
                                        if len(parts) > 1:
                                            target = parts[1].lstrip('@')
                                            ModerationEngine.reset_warnings(target)
                                            safe_send_message(thread_id, f"✅ Warnings Reset for {fix_mention(target)}! | 👨‍💻 **DEVS:** {OWNER_USERNAME}")
                                        continue

                except (LoginRequired, ChallengeRequired):
                    break
                except (PleaseWaitFewMinutes, ClientThrottledError):
                    time.sleep(30)
                except Exception:
                    time.sleep(POLL_INTERVAL)

                time.sleep(POLL_INTERVAL)

        except Exception:
            time.sleep(10)

if __name__ == "__main__":
    start_bot()
