import os
import re
import time
import json
import tempfile
import urllib.parse
import urllib.request
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
INSTAGRAM_SESSION_ID = os.getenv("INSTAGRAM_SESSION_ID", "15148784238%3AE9JQq4OmqN0we6%3A22%3AAYnLLA-hZCoDF_JSn-9ZUTyFcnZh90fU2hcNoWzRdw")

BOT_USERNAME = os.getenv("BOT_USERNAME", "pookieee_bot")
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "fx_smw")
AUTHORIZED_DEVS = ["fx_smw", "aat_nnk25"]
DEV_LINE = "👨‍💻 𝗗𝗘𝗩 ➜ @fx_smw • @aat_nnk25"
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///bot_database.db")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", 5))  # सुपर फास्ट रिस्पॉन्स के लिए अंतराल कम किया गया है

SHADOWBANNED_USERS = set()
TARGETED_USERS = set()
LOCKDOWN_MODE = False
USER_LAST_MESSAGE_TIME = {}


def fix_mention(username: str) -> str:
    if not username:
        return ""
    clean_name = str(username).strip().lstrip("@")
    return f"@{clean_name}" if clean_name else ""


def search_itunes_preview(query_text: str) -> dict | None:
    """Find an Apple/iTunes catalog preview; returns metadata and preview URL."""
    params = urllib.parse.urlencode({"term": query_text, "entity": "song", "limit": 1})
    request = urllib.request.Request(
        f"https://itunes.apple.com/search?{params}",
        headers={"User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8"))
    results = payload.get("results") or []
    if not results:
        return None
    track = results[0]
    preview = track.get("previewUrl")
    if not preview:
        return None
    return {
        "title": track.get("trackName") or query_text,
        "artist": track.get("artistName") or "Unknown Artist",
        "album": track.get("collectionName") or "Unknown Album",
        "url": track.get("trackViewUrl") or "",
        "preview_url": preview,
    }


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

# स्मार्ट फजी टेक्स्ट मैचिंग और एब्यूज पैटर्न्स
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
    # बिना स्पेसेस या सिंबल्स वाले शब्द हटाने के लिए क्लीन करना
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
                    ModerationEngine.log_event(thread_id, target_username, "AUTO-KICK", reason)

                    if not silent:
                        kick_card = (
                            f"🚨🚪 **𝗔𝗨𝗧𝗢-𝗞𝗜𝗖𝗞 𝗘𝗫𝗘𝗖𝗨𝗧𝗘𝗗!**\n\n"
                            f"👤 𝗢𝗙𝗙𝗘𝗡𝗗𝗘𝗥 ➜ {fix_mention(target_username)}\n"
                            f"🆔 𝗨𝗦𝗘𝗥 𝗜𝗗  ➜ `{target_pk}`\n"
                            f"🚫 𝗥𝗘𝗔𝗦𝗢𝗡   ➜ {reason}\n"
                            f"🛑 𝗔𝗖𝗧𝗜𝗢𝗡   ➜ REMOVED FROM GC PERMANENTLY!\n\n"
                            f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
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

                        # Morning Wish Card
                        if current_hour == 6 and last_morning_wish_date != current_date_str:
                            last_morning_wish_date = current_date_str
                            morning_card = (
                                f"🌅✨ **𝗚𝗢𝗢𝗗 𝗠𝗢𝗥𝗡𝗜𝗡𝗚 𝗘𝗩𝗘𝗥𝗬𝗢𝗡𝗘!** ✨🌅\n\n"
                                f"🌻 𝗛𝗔𝗩𝗘 𝗔𝗡 𝗔𝗠𝗔𝗭𝗜𝗡𝗚 & 𝗣𝗥𝗢𝗗𝗨𝗖𝗧𝗜𝗩𝗘 𝗗𝗔𝗬!\n"
                                f"☕ 𝗦𝗣𝗥𝗘𝗔𝗗 𝗣𝗢𝗦𝗜𝗧𝗜𝗩𝗜𝗧𝗬 𝗜𝗡 𝗧𝗛𝗘 𝗚𝗖 🔥\n\n"
                                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                            )
                            safe_send_message(thread_id, morning_card)

                        # Night Wish Card
                        if current_hour == 23 and last_night_wish_date != current_date_str:
                            last_night_wish_date = current_date_str
                            night_card = (
                                f"🌙✨ **𝗚𝗢𝗢𝗗 𝗡𝗜𝗚𝗛𝗧 𝗚𝗖 𝗙𝗔𝗠𝗜𝗟𝗬!** ✨🌙\n\n"
                                f"😴 𝗧𝗜𝗠𝗘 𝗧𝗢 𝗥𝗘𝗦𝗧 & 𝗥𝗘𝗖𝗛𝗔𝗥𝗚𝗘!\n"
                                f"💫 𝗦𝗪𝗘𝗘𝗧 𝗗𝗥𝗘𝗔𝗠𝗦 𝗘𝗩𝗘𝗥𝗬𝗢𝗡𝗘 🌙\n\n"
                                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
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
                                            )
                                            safe_send_message(thread_id, spam_card)
                                            execute_kick(thread_id, joined_pk, target_username, f"SPAM BOT ({spam_reason})", silent=True)
                                            continue

                                        if joined_pk in ever_seen_members:
                                            welcome_back_card = (
                                                f"💫🦋 𝗪𝗘𝗟𝗖𝗢𝗠𝗘 𝗕𝗔𝗖𝗞, {fix_mention(target_username)}! 🦋💫\n\n"
                                                f"🌷 𝗧𝗛𝗘 𝗚𝗖 𝗙𝗘𝗟𝗧 𝗬𝗢𝗨𝗥 𝗔𝗕𝗦𝗘𝗡𝗖𝗘 😌\n"
                                                f"🔥 𝗕𝗔𝗖𝗞 𝗔𝗚𝗔𝗜𝗡 • 𝗦𝗧𝗔𝗬 𝗔𝗖𝗧𝗜𝗩𝗘\n\n"
                                                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                            )
                                            safe_send_message(thread_id, welcome_back_card)
                                        else:
                                            ever_seen_members.add(joined_pk)
                                            welcome_card = (
                                                f"🦋✨ 𝗪𝗘𝗟𝗖𝗢𝗠𝗘, {fix_mention(target_username)}! ✨🦋\n\n"
                                                f"🌸 𝗛𝗘𝗬! 𝗚𝗟𝗔𝗗 𝗧𝗢 𝗛𝗔𝗩𝗘 𝗬𝗢𝗨 𝗛𝗘𝗥𝗘 💫\n"
                                                f"🔥 𝗘𝗡𝗝𝗢𝗬 𝗧𝗛𝗘 𝗚𝗖 & 𝗦𝗧𝗔𝗬 𝗔𝗖𝗧𝗜𝗩𝗘!\n\n"
                                                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
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

                                if sender_username.lower() in SHADOWBANNED_USERS:
                                    execute_kick(thread_id, sender_id, sender_username, "SHADOWBANNED", silent=True)
                                    continue

                                # स्पैम फ्लड प्रोटेक्शन (Raid Protection)
                                if not is_dev and not is_sender_admin:
                                    last_time_sent = USER_LAST_MESSAGE_TIME.get(sender_id, 0)
                                    if current_time_loop - last_time_sent < 1.2:
                                        execute_kick(thread_id, sender_id, sender_username, "Spam Flooding / Fast Messaging")
                                        continue
                                    USER_LAST_MESSAGE_TIME[sender_id] = current_time_loop

                                # -------------------------------------------------------------
                                # 🎵 SONG FINDER — Apple catalog preview + Instagram voice note
                                # -------------------------------------------------------------
                                if text_lower == "!song" or text_lower.startswith("!song "):
                                    song_query = text[5:].strip()
                                    if not song_query:
                                        song_help_card = (
                                            f"🎶🎧 **𝗦𝗢𝗡𝗚 𝗙𝗜𝗡𝗗𝗘𝗥!** 🎧🎶\n\n"
                                            f"🔎 **𝗛𝗢𝗪 𝗧𝗢 𝗨𝗦𝗘** ➜ `!song Song Name`\n"
                                            f"🎤 **𝗘𝗫𝗔𝗠𝗣𝗟𝗘** ➜ `!song Tum Hi Ho`\n\n"
                                            f"💡 𝗦𝗘𝗡𝗗 𝗧𝗛𝗘 𝗦𝗢𝗡𝗚 𝗡𝗔𝗠𝗘 𝗔𝗙𝗧𝗘𝗥 `!song`\n\n"
                                            f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n{DEV_LINE}"
                                        )
                                        safe_send_message(thread_id, song_help_card)
                                    else:
                                        searching_card = (
                                            f"🔍🎶 **𝗦𝗢𝗡𝗚 𝗦𝗘𝗔𝗥𝗖𝗛𝗜𝗡𝗚...** 🎶🔍\n\n"
                                            f"🎵 **𝗦𝗘𝗔𝗥𝗖𝗛** ➜ {song_query[:160]}\n"
                                            f"👤 **𝗥𝗘𝗤𝗨𝗘𝗦𝗧𝗘𝗗 𝗕𝗬** ➜ {fix_mention(sender_username)}\n"
                                            f"⏳ **𝗦𝗧𝗔𝗧𝗨𝗦** ➜ 𝗣𝗟𝗘𝗔𝗦𝗘 𝗪𝗔𝗜𝗧...\n"
                                            f"📥 𝗙𝗜𝗡𝗗𝗜𝗡𝗚 𝗔𝗩𝗔𝗜𝗟𝗔𝗕𝗟𝗘 𝗔𝗨𝗗𝗜𝗢 𝗣𝗥𝗘𝗩𝗜𝗘𝗪\n\n"
                                            f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n{DEV_LINE}"
                                        )
                                        safe_send_message(thread_id, searching_card)
                                        try:
                                            track = search_itunes_preview(song_query)
                                            if not track:
                                                song_not_found_card = (
                                                    f"❌🎵 **𝗦𝗢𝗡𝗚 𝗡𝗢𝗧 𝗙𝗢𝗨𝗡𝗗!** 🎵❌\n\n"
                                                    f"🔍 **𝗦𝗘𝗔𝗥𝗖𝗛** ➜ {song_query[:160]}\n"
                                                    f"⚠️ **𝗦𝗧𝗔𝗧𝗨𝗦** ➜ No playable catalog preview found.\n"
                                                    f"💡 **𝗧𝗜𝗣** ➜ Try song title with artist name.\n\n"
                                                    f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n{DEV_LINE}"
                                                )
                                                safe_send_message(thread_id, song_not_found_card)
                                                continue

                                            song_title = track["title"]
                                            artist_name = track["artist"]
                                            album_name = track["album"]
                                            song_url = track["url"]
                                            song_sending_card = (
                                                f"📥🎶 **𝗗𝗢𝗪𝗡𝗟𝗢𝗔𝗗𝗜𝗡𝗚 & 𝗦𝗘𝗡𝗗𝗜𝗡𝗚...** 🎶📥\n\n"
                                                f"🎵 **𝗧𝗶𝘁𝗹𝗲** ➜ {song_title}\n"
                                                f"🎤 **𝗔𝗿𝘁𝗶𝘀𝘁** ➜ {artist_name}\n"
                                                f"⏳ **𝗦𝘁𝗮𝘁𝘂𝘀** ➜ Fetching catalog preview; please wait...\n\n"
                                                f"✨ 𝗔𝗨𝗗𝗜𝗢 𝗣𝗥𝗘𝗩𝗜𝗘𝗪 𝗪𝗜𝗟𝗟 𝗕𝗘 𝗦𝗘𝗡𝗧 𝗦𝗛𝗢𝗥𝗧𝗟𝗬! 🚀\n\n"
                                                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n{DEV_LINE}"
                                            )
                                            safe_send_message(thread_id, song_sending_card)
                                            with tempfile.TemporaryDirectory(prefix="song_preview_") as temp_dir:
                                                audio_path = os.path.join(temp_dir, "preview.m4a")
                                                req = urllib.request.Request(track["preview_url"], headers={"User-Agent": "Mozilla/5.0"})
                                                with urllib.request.urlopen(req, timeout=25) as response, open(audio_path, "wb") as output:
                                                    output.write(response.read())
                                                if os.path.getsize(audio_path) < 1024:
                                                    raise RuntimeError("Preview audio file is empty or incomplete")
                                                cl.direct_send_voice(audio_path, thread_ids=[thread_id])
                                            song_found_card = (
                                                f"🎶🎧 **𝗦𝗢𝗡𝗚 𝗙𝗢𝗨𝗡𝗗!** 🎧🎶\n\n"
                                                f"🎵 **𝗧𝗶𝘁𝗹𝗲** ➜ {song_title}\n"
                                                f"🎤 **𝗔𝗿𝘁𝗶𝘀𝘁** ➜ {artist_name}\n"
                                                f"💿 **𝗔𝗹𝗯𝘂𝗺** ➜ {album_name}\n"
                                                f"🔗 **𝗟𝗶𝗻𝗸** ➜ {song_url}\n\n"
                                                f"✨ 𝗘𝗡𝗝𝗢𝗬 𝗧𝗛𝗘 𝗠𝗨𝗦𝗜𝗖 • 𝗩𝗜𝗕𝗘 𝗢𝗨𝗧 🔥\n\n"
                                                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n{DEV_LINE}"
                                            )
                                            safe_send_message(thread_id, song_found_card)
                                        except Exception as song_error:
                                            print(f"[!] Song feature error: {song_error}")
                                            safe_send_message(thread_id, (
                                                f"⚠️🎵 **𝗦𝗢𝗡𝗚 𝗦𝗘𝗡𝗗𝗜𝗡𝗚 𝗙𝗔𝗜𝗟𝗘𝗗** 🎵⚠️\n\n"
                                                f"🔧 **𝗗𝗘𝗧𝗔𝗜𝗟** ➜ Audio preview was found or requested, but Instagram could not confirm voice delivery.\n"
                                                f"💡 **𝗧𝗜𝗣** ➜ Check instagrapi version, account limits, and group permissions.\n\n"
                                                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n{DEV_LINE}"
                                            ))
                                    continue

                                # -------------------------------------------------------------
                                # 🟢 PUBLIC COMMAND: !rules
                                # -------------------------------------------------------------
                                if text_lower == "!rules":
                                    rules_card = (
                                        f"⚜️🌷 𝗚𝗖 𝗥𝗨𝗟𝗘𝗦 • 𝗣𝗟𝗘𝗔𝗦𝗘 𝗥𝗘𝗔𝗗 🌷⚜️\n\n"
                                        f"🤝 𝗥𝗘𝗦𝗣𝗘𝗖𝗧 𝗘𝗩𝗘𝗥𝗬𝗢𝗡𝗘\n"
                                        f"💌 𝗞𝗘𝗘𝗣 𝗧𝗛𝗘 𝗩𝗜𝗕𝗘 𝗙𝗥𝗜𝗘𝗡𝗗𝗟𝗬\n\n"
                                        f"🚫 𝗡𝗢 𝗔𝗕𝗨𝗦𝗘 • 𝗡𝗢 𝗧𝗢𝗫𝗜𝗖𝗜𝗧𝗬\n"
                                        f"⚠️ 𝗗𝗥𝗔𝗠𝗔 & 𝗙𝗜𝗚𝗛𝗧𝗦 𝗔𝗥𝗘 𝗡𝗢𝗧 𝗔𝗟𝗟𝗢𝗪𝗘𝗗\n\n"
                                        f"🔞 𝗡𝗢 𝗡𝗦𝗙𝗪 / 𝗔𝗗𝗨𝗟𝗧 𝗖𝗢𝗡𝗧𝗘𝗡𝗧\n"
                                        f"🛡️ 𝗞𝗘𝗘𝗣 𝗧𝗛𝗘 𝗚𝗖 𝗖𝗟𝗘𝗔𝗡\n\n"
                                        f"📢 𝗡𝗢 𝗦𝗣𝗔𝗠 • 𝗡𝗢 𝗙𝗟𝗢𝗢𝗗𝗜𝗡𝗚\n"
                                        f"🚫 𝗗𝗢𝗡'𝗧 𝗦𝗘𝗡𝗗 𝗥𝗘𝗣𝗘𝗔𝗧𝗘𝗗 𝗠𝗘𝗦𝗦𝗔𝗚𝗘𝗦\n\n"
                                        f"🔗 𝗡𝗢 𝗨𝗡𝗔𝗨𝗧𝗛𝗢𝗥𝗜𝗭𝗘𝗗 𝗟𝗜𝗡𝗞𝗦\n"
                                        f"📩 𝗔𝗦𝗞 𝗔𝗗𝗠𝗜𝗡𝗦 𝗙𝗜𝗥𝗦𝗧\n\n"
                                        f"👑 𝗥𝗘𝗦𝗣𝗘𝗖𝗧 𝗔𝗗𝗠𝗜𝗡𝗦 & 𝗠𝗢𝗗𝗘𝗥𝗔𝗧𝗢𝗥𝗦\n"
                                        f"✨ 𝗙𝗢𝗟𝗟𝗢𝗪 𝗢𝗙𝗙𝗜𝗖𝗜𝗔𝗟 𝗜𝗡𝗦𝗧𝗥𝗨𝗖𝗧𝗜𝗢𝗡𝗦\n\n"
                                        f"⚠️ 𝗥𝗨𝗟𝗘𝗦 𝗕𝗥𝗘𝗔𝗞 = 𝗪𝗔𝗥𝗡𝗜𝗡𝗚\n"
                                        f"🚫 𝗥𝗘𝗣𝗘𝗔𝗧𝗘𝗗 𝗩𝗜𝗢𝗟𝗔𝗧𝗜𝗢𝗡𝗦 = 𝗥𝗘𝗠𝗢𝗩𝗔𝗟\n\n"
                                        f"🌷 𝗦𝗧𝗔𝗬 𝗔𝗖𝗧𝗜𝗩𝗘 • 𝗦𝗧𝗔𝗬 𝗥𝗘𝗦𝗣𝗘𝗖𝗧𝗙𝗨𝗟 🌷\n"
                                        f"💫 𝗘𝗡𝗝𝗢𝗬 • 𝗖𝗛𝗔𝗧 • 𝗚𝗥𝗢𝗪 • 𝗖𝗢𝗡𝗡𝗘𝗖𝗧 💫\n\n"
                                        f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                    )
                                    safe_send_message(thread_id, rules_card)
                                    continue

                                # -------------------------------------------------------------
                                # 🛡️ AUTOMATED ABUSE & LINK MODERATION (SMART FUZZY MATCH)
                                # -------------------------------------------------------------
                                if not is_dev and not is_sender_admin:
                                    if is_abusive_text(text) or re.search(r"(?:https?://|www\.|instagram\.com|bit\.ly/|tinyurl\.com/|t\.me/|wa\.me/|\b[a-z0-9-]+\.(?:com|net|org|xyz|top|info|site|link)\b)", text_lower, re.IGNORECASE):
                                        warns, trust = ModerationEngine.add_warning(sender_username)
                                        reason = "Abusive Language / Smart Filter Triggered" if is_abusive_text(text) else "Unauthorized Link / Reel / URL Spam"

                                        if warns >= 2:
                                            execute_kick(thread_id, sender_id, sender_username, f"Second Violation ({reason})")
                                        else:
                                            warn_card = (
                                                f"⚠️🚨 **𝗩𝗜𝗢𝗟𝗔𝗧𝗜𝗢𝗡 𝗪𝗔𝗥𝗡𝗜𝗡𝗚!** 🚨⚠️\n\n"
                                                f"👤 𝗢𝗙𝗙𝗘𝗡𝗗𝗘𝗥 ➜ {fix_mention(sender_username)}\n"
                                                f"🚫 𝗥𝗘𝗔𝗦𝗢𝗡   ➜ {reason}\n"
                                                f"⚠️ 𝗪𝗔𝗥𝗡𝗜𝗡𝗚𝗦 ➜ {warns}/2\n"
                                                f"📉 𝗧𝗥𝗨𝗦𝗧 𝗦𝗖𝗢𝗥𝗘 ➜ {trust}%\n\n"
                                                f"📢 **𝗔𝗗𝗠𝗜𝗡 𝗔𝗟𝗘𝗥𝗧** ➜ {admin_mentions_tag}\n\n"
                                                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                            )
                                            safe_send_message(thread_id, warn_card)
                                        continue

                                # -------------------------------------------------------------
                                # 👑 DEVELOPER-ONLY COMMANDS & RESTRICTION HANDLER
                                # -------------------------------------------------------------
                                is_trying_command = text_lower.startswith("!") and text_lower != "!rules"

                                if is_trying_command and not is_dev:
                                    unauthorized_card = (
                                        f"⛔🔒 **𝗔𝗖𝗖𝗘𝗦𝗦 𝗗𝗘𝗡𝗜𝗘𝗗!** 🔒⛔\n\n"
                                        f"👤 𝗨𝗦𝗘𝗥 ➜ {fix_mention(sender_username)}\n"
                                        f"⚠️ 𝗥𝗘𝗔𝗦𝗢𝗡 ➜ This command is restricted to **Developers Only**!\n"
                                        f"🚫 𝗔𝗖𝗧𝗜𝗢𝗡 ➜ You cannot execute bot management commands.\n\n"
                                        f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                    )
                                    safe_send_message(thread_id, unauthorized_card)
                                    continue

                                if is_dev:
                                    if text_lower == "!lockdown":
                                        LOCKDOWN_MODE = True
                                        continue

                                    elif text_lower == "!unlock":
                                        LOCKDOWN_MODE = False
                                        continue

                                    elif text_lower == "!godmode":
                                        status_card = (
                                            f"⚡🛡️ **𝗚𝗢𝗗𝗠𝗢𝗗𝗘 𝗦𝗧𝗔𝗧𝗨𝗦** 🛡️⚡\n\n"
                                            f"🔒 **𝗟𝗼𝗰𝗸𝗱𝗼𝘄𝗻** ➜ {'ON 🚨' if LOCKDOWN_MODE else 'OFF 🟢'}\n"
                                            f"🎯 **𝗧𝗮𝗿𝗴𝗲𝘁𝘀** ➜ {len(TARGETED_USERS)} Users\n"
                                            f"👻 **𝗦𝗵𝗮𝗱𝗼𝘄𝗯𝗮𝗻𝘀** ➜ {len(SHADOWBANNED_USERS)} Users\n\n"
                                            f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                        )
                                        safe_send_message(thread_id, status_card)
                                        continue

                                    elif text_lower.startswith("!target"):
                                        parts = text.split()
                                        if len(parts) > 1:
                                            target = parts[1].lstrip("@").lower()
                                            TARGETED_USERS.add(target)
                                        continue

                                    elif text_lower.startswith("!shadowban"):
                                        parts = text.split()
                                        if len(parts) > 1:
                                            target = parts[1].lstrip("@").lower()
                                            SHADOWBANNED_USERS.add(target)
                                        continue

                                    elif text_lower.startswith("!nuke"):
                                        parts = text.split()
                                        if len(parts) > 1:
                                            target = parts[1].lstrip("@")
                                            u_id = cl.user_id_from_username(target)
                                            execute_kick(thread_id, u_id, target, "NUKE BAN")
                                        continue

                                    elif text_lower.startswith("!resetwarn") or text_lower.startswith("!unwarn"):
                                        parts = text.split()
                                        if len(parts) > 1:
                                            target = parts[1].lstrip("@")
                                            ModerationEngine.reset_warnings(target)
                                        continue

                                    elif text_lower == "!tagall":
                                        all_tags = [fix_mention(getattr(u, "username", "")) for u in users if getattr(u, "username", None)]
                                        continue

                                    elif text_lower == "!admins":
                                        if gc_admins:
                                            admin_names = []
                                            for u in users:
                                                if str(getattr(u, "pk", "")) in admin_ids_str:
                                                    un = getattr(u, "username", None)
                                                    if un:
                                                        admin_names.append(f"👑 ➜ {fix_mention(un)}")

                                            admin_card = (
                                                f"👑🛡️ **𝗚𝗖 𝗔𝗗𝗠𝗜𝗡𝗜𝗦𝗧𝗥𝗔𝗧𝗢𝗥𝗦** 🛡️👑\n\n"
                                                f"📊 **𝗧𝗢𝗧𝗔𝗟** ➜ {len(gc_admins)}\n\n"
                                                f"{'\n'.join(admin_names)}\n\n"
                                                f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                            )
                                            safe_send_message(thread_id, admin_card)
                                        continue

                                    elif text_lower.startswith("!dp"):
                                        parts = text.split()
                                        target_name = parts[1].lstrip("@") if len(parts) > 1 else sender_username
                                        try:
                                            u_info = cl.user_info_by_username(target_name)
                                            if u_info:
                                                dp_url = getattr(getattr(u_info, "hd_profile_pic_url_info", None), "url", None) or getattr(u_info, "profile_pic_url_hd", None) or u_info.profile_pic_url
                                                photo_path = cl.photo_download_by_url(dp_url, filename=f"{target_name}_dp.jpg")
                                                cl.direct_send_photo(photo_path, thread_ids=[thread_id])

                                                dp_card = (
                                                    f"📸✨ **𝗛𝗗 𝗗𝗣 𝗙𝗘𝗧𝗖𝗛𝗘𝗗** ✨📸\n\n"
                                                    f"👤 𝗨𝗦𝗘𝗥 ➜ {fix_mention(target_name)}\n\n"
                                                    f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                                )
                                                safe_send_message(thread_id, dp_card)

                                                if os.path.exists(photo_path):
                                                    os.remove(photo_path)
                                        except Exception:
                                            safe_send_message(thread_id, f"❌ Failed to fetch DP for {fix_mention(target_name)}!")
                                        continue

                                    elif text_lower.startswith("!profile") or text_lower.startswith("!user"):
                                        parts = text.split()
                                        target_name = parts[1].lstrip("@") if len(parts) > 1 else sender_username
                                        try:
                                            u_info = cl.user_info_by_username(target_name)
                                            if u_info:
                                                def format_count(count):
                                                    if count >= 1_000_000:
                                                        return f"{count / 1_000_000:.1f}M"
                                                    elif count >= 1_000:
                                                        return f"{count / 1_000:.1f}k"
                                                    return str(count)

                                                account_created = getattr(u_info, "account_creation_date", "Not Available")
                                                country = getattr(u_info, "country_block", False) or "Public / Global"

                                                profile_card = (
                                                    f"👤✨ **𝗨𝗦𝗘𝗥 𝗣𝗥𝗢𝗙𝗜𝗟𝗘 𝗗𝗘𝗧𝗔𝗜𝗟𝗦** ✨👤\n\n"
                                                    f"📌 **𝗡𝗮𝗺𝗲** ➜ {u_info.full_name or 'Not Provided'}\n"
                                                    f"🆔 **𝗨𝘀𝗲𝗿𝗻𝗮𝗺𝗲** ➜ @{u_info.username}\n"
                                                    f"🔢 **𝗨𝘀𝗲𝗿 𝗜𝗗** ➜ `{u_info.pk}`\n"
                                                    f"📅 **𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗖𝗿𝗲𝗮𝘁𝗲𝗱** ➜ {account_created}\n"
                                                    f"🌍 **𝗕𝗮𝘀𝗲𝗱 / 𝗥𝗲𝗴𝗶𝗢𝗻** ➜ {country}\n"
                                                    f"👥 **𝗙𝗼𝗹𝗹𝗼𝘄𝗲𝗿𝘀** ➜ {format_count(u_info.follower_count)}\n"
                                                    f"🫂 **𝗙𝗼𝗹𝗹𝗼𝘄𝗶𝗻𝗴** ➜ {format_count(u_info.following_count)}\n"
                                                    f"📸 **𝗧𝗼𝘁𝗮𝗹 𝗣𝗼𝘀𝘁𝘀** ➜ {u_info.media_count}\n"
                                                    f"🔗 **𝗕𝗶𝗼** ➜ {u_info.biography.replace('\n', ' ') if u_info.biography else 'No Bio'}\n"
                                                    f"🔒 **𝗣𝗿𝗶𝘃𝗮𝘁𝗲** ➜ {'Yes 🔒' if u_info.is_private else 'No 🟢'}\n\n"
                                                    f"🤖 𝗕𝗢𝗧 ➜ {fix_mention(BOT_USERNAME)}\n"
                                                )
                                                safe_send_message(thread_id, profile_card)
                                        except Exception as e:
                                            safe_send_message(thread_id, f"❌ Error fetching profile: {str(e)}")
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
                                            f"⚡ **Status** ➜ ONLINE & ACTIVE (Super Fast)\n"
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
