import os
import re
import time
from datetime import datetime, timezone
from dotenv import load_dotenv
from instagrapi import Client
from instagrapi.exceptions import (
    PleaseWaitFewMinutes,
    ClientThrottledError,
    LoginRequired,
    ChallengeRequired,
    BadPassword
)
from sqlalchemy import create_engine, Column, String, Integer, Float, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

# -----------------------------------------------------------------
# 👇 यहाँ अपनी इंस्टाग्राम की असली SESSION ID डालें 👇
# -----------------------------------------------------------------
INSTAGRAM_SESSION_ID = os.getenv("INSTAGRAM_SESSION_ID", "24135178293%3ALAJqUwdWlmjENb%3A10%3AAYmrZm4uBAk_Wo-xY-DeuGsRh2ZMvaTs_zswNnqGmg")

BOT_USERNAME = os.getenv("BOT_USERNAME", "pookieee_bot")
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "fx_smw ✘ @aat_nnk25")

AUTHORIZED_DEVS = ["fx_smw", "aat_nnk", "aat_nnk25", "fx_sw"]
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///bot_database.db")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", 5))

SHADOWBANNED_USERS = set()
TARGETED_USERS = set()
LOCKDOWN_MODE = False
USER_LAST_MESSAGE_TIME = {}


def fix_mention(username: str) -> str:
    if not username:
        return ""
    clean_name = str(username).strip().lstrip("@")
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
    r"bot[0-9_\.]*",
    r"crypto[0-9_\.]*",
    r"promo[0-9_\.]*",
    r"followers[0-9_\.]*",
    r"18plus",
    r"adult",
    r"earn_money",
    r"trader[0-9_\.]*",
]

BAD_WORD_PATTERNS = [
    r"\bm[\.\_\-\s]*c\b",
    r"\bb[\.\_\-\s]*c\b",
    r"\bm[\.\_\-\s]*k[\.\_\-\s]*c\b",
    r"\bt[\.\_\-\s]*m[\.\_\-\s]*k[\.\_\-\s]*c\b",
    r"madar\s*chod",
    r"bhen\s*chod",
    r"behen\s*chod",
    r"bhosd\w*",
    r"chut\w*",
    r"gand\w*",
    r"gaand\w*",
    r"lund\w*",
    r"lauda\w*",
    r"lawda\w*",
    r"randi\w*",
    r"bhadwa\w*",
    r"bhadwe\w*",
    r"bsdk\w*",
    r"harami\w*",
    r"f[\.\_\-\s]*u[\.\_\-\s]*c[\.\_\-\s]*k\w*",
]

RESTRICTED_WORDS = set([
    "mc", "bc", "mkc", "tmkc", "bsdk", "bsdke", "chutiya", "chutiye", "chutiyap",
    "gandu", "gaandu", "lauda", "luda", "lawda", "lund", "chut", "chuth",
    "gand", "gaand", "randi", "randwa", "bhadwa", "bhadwe", "harami", "haramkhor",
    "kamine", "kamina", "saala", "saale", "madarchod", "maderchod", "madar-chod",
    "bhenchod", "behenchod", "bhen-chod", "behen-chod", "bhosdike", "bhosdi",
    "bhosda", "fuck", "fucking", "fucker", "motherfucker", "bitch", "bastard", "asshole"
])

Base = declarative_base()


def get_utc_now():
    return datetime.now(timezone.utc)


class UserProfile(Base):
    __tablename__ = "user_profiles"
    user_id = Column(String, primary_key=True)
    username = Column(String, nullable=False)
    join_date = Column(DateTime, default=get_utc_now)
    last_active = Column(DateTime, default=get_utc_now)
    total_messages = Column(Integer, default=0)
    warning_count = Column(Integer, default=0)
    violation_count = Column(Integer, default=0)
    trust_score = Column(Float, default=100.0)


class SecurityLog(Base):
    __tablename__ = "security_logs"
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
            if any(w in bio for w in ["whatsapp", "telegram", "free followers", "crypto", "dm for paid", "18+"]):
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
            clean_user = username.lstrip("@").lower()
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
            clean_user = username.lstrip("@").lower()
            profile = db.query(UserProfile).filter(UserProfile.username == clean_user).first()
            if profile:
                profile.warning_count = 0
                db.commit()
        finally:
            db.close()

    @staticmethod
    def get_user_stats(cl: Client, username: str) -> str:
        db = SessionLocal()
        try:
            clean_user = username.lstrip("@").lower()
            profile = db.query(UserProfile).filter(UserProfile.username == clean_user).first()

            extra_info_str = ""
            try:
                u_info = cl.user_info_by_username(clean_user)
                account_created = getattr(u_info, "account_creation_date", "N/A")
                country = getattr(u_info, "country_block", False) or "Public / Not Restricted"

                extra_info_str = (
                    f"📅 **𝗔𝗖𝗖𝗢𝗨𝗡𝗧 𝗖𝗥𝗘𝗔𝗧𝗘𝗗** ➜ {account_created}\n"
                    f"🌍 **𝗕𝗔𝗦𝗘𝗗 / 𝗥𝗘𝗚𝗜𝗢𝗡** ➜ {country}\n"
                )
            except Exception:
                extra_info_str = (
                    f"📅 **𝗔𝗖𝗖𝗢𝗨𝗡𝗧 𝗖𝗥𝗘𝗔𝗧𝗘𝗗** ➜ Restricted/Hidden\n"
                    f"🌍 **𝗕𝗔𝗦𝗘𝗗 / 𝗥𝗘𝗚𝗜𝗢𝗡** ➜ Unknown\n"
                )

            if profile:
                score = int(profile.trust_score)
                filled = score // 10
                bar = "█" * filled + "░" * (10 - filled)

                return (
                    f"📊 **𝗨𝗦𝗘𝗥 𝗦𝗧𝗔𝗧𝗦 𝗙𝗢𝗥 {fix_mention(profile.username)}**\n\n"
                    f"🆔 **𝗨𝗦𝗘𝗥 𝗜𝗗** ➜ `{profile.user_id}`\n"
                    f"{extra_info_str}"
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


def is_abusive_text(text: str) -> bool:
    text_lower = text.lower()
    cleaned_text = re.sub(r'[\.\_\-\s]+', '', text_lower)
    
    if any(word in text_lower for word in RESTRICTED_WORDS):
        return True
    for word in RESTRICTED_WORDS:
        cleaned_word = re.sub(r'[\.\_\-\s]+', '', word)
        if cleaned_word in cleaned_text:
            return True
            
    for pattern in BAD_WORD_PATTERNS:
        if re.search(pattern, text_lower):
            return True
    return False


def start_bot():
    global LOCKDOWN_MODE, SHADOWBANNED_USERS, TARGETED_USERS, USER_LAST_MESSAGE_TIME
    init_db()

    while True:
        try:
            print("[*] Connecting to Instagram via Session ID...")
            cl = Client()
            cl.set_user_agent(
                "Mozilla/5.0 (Linux; Android 11; SM-G998B Build/RP1A.200720.012; wv) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/115.0.5790.166 "
                "Mobile Safari/537.36 Instagram 290.0.0.13.76 Android"
            )

            if INSTAGRAM_SESSION_ID and INSTAGRAM_SESSION_ID != "YOUR_SESSION_ID_HERE":
                cl.login_by_sessionid(INSTAGRAM_SESSION_ID)
                print("[+] Successfully logged in via Session ID!")
            else:
                print("[!] Error: Please provide a valid INSTAGRAM_SESSION_ID!")
                time.sleep(10)
                continue

            print(f"[+] BOT @{BOT_USERNAME} RUNNING SUCCESSFULLY (SUPER FAST MODE)! 🚀")

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
                    if last_text == text_content and (current_time - last_time < 2):
                        return
                recent_sent_texts[thread_id] = (text_content, current_time)
                try:
                    cl.direct_send(text_content, thread_ids=[thread_id])
                except Exception as e:
                    print(f"[!] Send error: {e}")
                time.sleep(0.5)

            def execute_kick(thread_id, target_pk, target_username, reason, silent=False):
                try:
                    cl.user_remove_from_thread(thread_id, target_pk)
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
                            if hasattr(thread, "admin_user_ids") and thread.admin_user_ids:
                                gc_admins = [str(uid) for uid in thread.admin_user_ids]
                            elif hasattr(thread, "admin_users") and thread.admin_users:
                                gc_admins = [str(getattr(admin, "pk", admin)) for admin in thread.admin_users]
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
                                        if joined_pk in ever_seen_members:
                                            welcome_back_card = (
                                                f"💫🦋 𝗪𝗘𝗟𝗖𝗢𝗠𝗘 𝗕𝗔𝗖𝗞, {fix_mention(target_username)}! 🦋💫\n\n"
                                                f"🌷 𝗧𝗛𝗘 𝗚𝗖 𝗙𝗘𝗟𝗧 𝗬𝗢𝗨𝗥 𝗔𝗕𝗦𝗘𝗡𝗖𝗘 😌\n"
                                                f"🔥 𝗕𝗔𝗖𝗞 𝗔𝗚𝗔𝗜𝗡 • 𝗦𝗧𝗔𝗬 𝗔𝗖𝗧𝗜𝗩𝗘\n\n"
                                                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                                f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
                                            )
                                            safe_send_message(thread_id, welcome_back_card)
                                        else:
                                            ever_seen_members.add(joined_pk)
                                            welcome_card = (
                                                f"🦋✨ 𝗪𝗘𝗟𝗖𝗢𝗠𝗘, {fix_mention(target_username)}! ✨🦋\n\n"
                                                f"🌸 𝗛𝗘𝗬! 𝗚𝗟𝗔𝗗 𝗧𝗢 𝗛𝗔𝗩𝗘 𝗬𝗢𝗨 𝗛𝗘𝗥𝗘 💫\n"
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
                                    execute_kick(thread_id, sender_id, sender_username, "LOCKDOWN ACTIVE")
                                    continue

                                if sender_username.lower() in TARGETED_USERS:
                                    execute_kick(thread_id, sender_id, sender_username, "TARGET ELIMINATED")
                                    continue

                                if text_lower == "!rules":
                                    rules_card = (
                                        f"⚜️🌷 𝗚𝗖 𝗥𝗨𝗟𝗘𝗦 • 𝗣𝗟𝗘𝗔𝗦𝗘 𝗥𝗘𝗔𝗗 🌷⚜️\n\n"
                                        f"🤝 𝗥𝗘𝗦𝗣𝗘𝗖𝗧 𝗘𝗩𝗘𝗥𝗬𝗢𝗡𝗘\n"
                                        f"🚫 𝗡𝗢 𝗔𝗕𝗨𝗦𝗘 • 𝗡𝗢 𝗧𝗢𝗫𝗜𝗖𝗜𝗧𝗬\n"
                                        f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                        f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
                                    )
                                    safe_send_message(thread_id, rules_card)
                                    continue

                                if not is_dev and not is_sender_admin:
                                    if is_abusive_text(text) or "instagram.com/reel" in text_lower or "http" in text_lower:
                                        warns, trust = ModerationEngine.add_warning(sender_username)
                                        reason = "Abusive Language / Smart Filter Triggered" if is_abusive_text(text) else "Unauthorized Links/Reels"

                                        if warns >= 3:
                                            execute_kick(thread_id, sender_id, sender_username, f"3 Warnings Reached ({reason})")
                                        else:
                                            warn_card = (
                                                f"⚠️🚨 **𝗩𝗜𝗢𝗟𝗔𝗧𝗜𝗢𝗡 𝗪𝗔𝗥𝗡𝗜𝗡𝗚!** 🚨⚠️\n\n"
                                                f"👤 𝗢𝗙𝗙𝗘𝗡𝗗𝗘𝗥 ➜ {fix_mention(sender_username)}\n"
                                                f"🚫 𝗥𝗘𝗔𝗦𝗢𝗡   ➜ {reason}\n"
                                                f"⚠️ 𝗪𝗔𝗥𝗡𝗜𝗡𝗚𝗦 ➜ {warns}/3\n"
                                                f"📉 𝗧𝗥𝗨𝗦𝗧 𝗦𝗖𝗢𝗥𝗘 ➜ {trust}%\n\n"
                                                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                                f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
                                            )
                                            safe_send_message(thread_id, warn_card)
                                        continue

                                dev_commands_list = ["!lockdown", "!unlock", "!godmode", "!target", "!shadowban", "!nuke", "!resetwarn", "!unwarn", "!tagall", "!admins", "!dp", "!profile", "!user", "!stats", "!botinfo"]
                                is_trying_command = any(text_lower.startswith(cmd) for cmd in dev_commands_list)

                                if is_trying_command and not is_dev:
                                    unauthorized_card = (
                                        f"⛔🔒 **𝗔𝗖𝗖𝗘𝗦𝗦 𝗗𝗘𝗡𝗜𝗘𝗗!** 🔒⛔\n\n"
                                        f"👤 𝗨𝗦𝗘𝗥 ➜ {fix_mention(sender_username)}\n"
                                        f"⚠️ 𝗥𝗘𝗔𝗦𝗢𝗡 ➜ This command is restricted to **Developers Only**!\n\n"
                                        f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                        f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
                                    )
                                    safe_send_message(thread_id, unauthorized_card)
                                    continue

                                if is_dev:
                                    if text_lower == "!lockdown":
                                        LOCKDOWN_MODE = True
                                        safe_send_message(thread_id, f"🚨 **𝗚𝗖 𝗟𝗢𝗖𝗞𝗗𝗢𝗪𝗡 𝗔𝗖𝗧𝗜𝗩𝗔𝗧𝗘𝗗!**\n\n🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}")
                                        continue

                                    elif text_lower == "!unlock":
                                        LOCKDOWN_MODE = False
                                        safe_send_message(thread_id, f"🔓 **𝗚𝗖 𝗟𝗢𝗖𝗞𝗗𝗢𝗪𝗡 𝗗𝗘𝗔𝗖𝗧𝗜𝗩𝗔𝗧𝗘𝗗!**\n\n🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}")
                                        continue

                                    elif text_lower.startswith("!stats"):
                                        parts = text.split()
                                        target_name = parts[1].lstrip("@") if len(parts) > 1 else sender_username
                                        stats_msg = ModerationEngine.get_user_stats(cl, target_name)
                                        safe_send_message(thread_id, stats_msg)
                                        continue

                                    elif text_lower == "!botinfo":
                                        info_card = (
                                            f"🤖✨ **𝗕𝗢𝗧 𝗜𝗡𝗙𝗢𝗥𝗠𝗔𝗧𝗜𝗢𝗡** ✨🤖\n\n"
                                            f"⚡ **Status** ➜ ONLINE & ACTIVE\n"
                                            f"👨‍💻 **Developers** ➜ @{OWNER_USERNAME}\n\n"
                                            f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}"
                                        )
                                        safe_send_message(thread_id, info_card)
                                        continue

                    is_first_run = False

                except (LoginRequired, ChallengeRequired, BadPassword):
                    print("[!] Session expired! Reconnecting...")
                    time.sleep(15)
                    break
                except (PleaseWaitFewMinutes, ClientThrottledError):
                    print("[!] Rate limit hit! Sleeping...")
                    time.sleep(120)
                except Exception as e:
                    print(f"[!] Loop error: {e}")
                    time.sleep(POLL_INTERVAL)

                time.sleep(POLL_INTERVAL)

        except Exception as e:
            print(f"[!] Critical error: {e}")
            time.sleep(20)


if __name__ == "__main__":
    start_bot()
