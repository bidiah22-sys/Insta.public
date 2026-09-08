import os
import time
import re
import logging
from instagrapi import Client

# ==========================================
# LOGGING SETUP
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] ➔ %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("SMW_FINAL_FIXED_BOT")

# ==========================================
# CONFIGURATION
# ==========================================
BOT_USERNAME = os.getenv("BOT_USERNAME", "smw_bot2.0")
OWNER_USERNAME = "fx_smw"
SESSION_ID = "27413581604%3A91cVN5zOMUK05d%3A5%3AAYhafaXxMTZ1DIBd5DyT1RiuLCVGMmbf0qQbSjOINA"
POLL_INTERVAL = 5  # रेट-लिमिट और डबल रिक्वेस्ट से बचने के लिए थोड़ा बढ़ाया गया सेफ इंटरवल

if not SESSION_ID or SESSION_ID == "YAHAN_APNI_SESSION_ID_DAL":
    raise RuntimeError("Critical Error: Instagram Session ID is missing!")


# ==========================================
# HELPERS & NORMALIZERS
# ==========================================

def clean_username(username):
    if not username:
        return "User"
    return str(username).lstrip("@").strip()


def get_sender_username(message, thread=None):
    try:
        if getattr(message, "user", None):
            uname = getattr(message.user, "username", None)
            if uname:
                return clean_username(uname)
    except Exception:
        pass

    try:
        sender_id = str(getattr(message, "user_id", ""))
        if sender_id and thread and hasattr(thread, "users"):
            for u in thread.users:
                if str(getattr(u, "pk", "")) == sender_id:
                    uname = getattr(u, "username", None)
                    if uname:
                        return clean_username(uname)
    except Exception:
        pass

    return "User"


def get_admin_usernames(thread, bot_pk):
    admin_ids = set()
    try:
        ids = getattr(thread, "admin_user_ids", None)
        if ids:
            admin_ids = {str(x) for x in ids}
    except Exception:
        pass

    admins = []
    try:
        for user in getattr(thread, "users", []) or []:
            uid = str(getattr(user, "pk", ""))
            username = clean_username(getattr(user, "username", ""))
            if uid and uid in admin_ids and uid != str(bot_pk) and username and username != "User":
                admins.append(username)
    except Exception:
        pass

    return list(dict.fromkeys(admins))


def admin_alert_text(admins):
    if not admins:
        return "@ADMIN"
    return " ".join(f"@{username}" for username in admins)


def normalize_text(text):
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r'[\s\-_.,?!@#]+', '', text)
    return text


def is_link(text):
    if not text:
        return False
    raw_text = text.lower()
    patterns = [
        r"https?://",
        r"www\.",
        r"\b[a-z0-9-]+\.(com|net|org|in|co|io|me|xyz|shop|site|online|tech)\b",
        r"t\.me/",
        r"instagram\.com/",
        r"ig\.me/"
    ]
    return any(re.search(pat, raw_text) for pat in patterns)


def is_reel_or_video(message, text):
    text_lower = (text or "").lower()
    item_type = str(getattr(message, "item_type", "") or "").lower()
    video_types = {"clip", "video", "visual_media", "media", "sid_video"}
    video_keywords = ["/reel/", "/reels/", "instagram.com/reel"]
    return (
        item_type in video_types
        or any(kw in text_lower for kw in video_keywords)
    )


# ==========================================
# MAIN BOT ENGINE (ULTRA-STABLE & DEDUPLICATED)
# ==========================================

def start_bot():
    while True:
        try:
            logger.info("Initializing Instagram Client with Anti-Double Lock v2...")
            cl = Client()
            try:
                cl.delay_range = [1, 3]
            except Exception:
                pass

            cl.login_by_sessionid(SESSION_ID)
            bot_pk = str(cl.user_id)
            logger.info(f"SUCCESS: Bot @{BOT_USERNAME} logged in! (PK: {bot_pk})")

            processed_messages = set()
            recent_welcome_times = {}
            recent_action_times = {}
            group_members = {}
            initialized_threads = set() # यह ट्रैक रखेगा कि कौन सा ग्रुप पहली बार स्कैन हो चुका है

            while True:
                try:
                    threads = cl.direct_threads(amount=10)

                    for thread in threads:
                        if not getattr(thread, "is_group", False):
                            continue

                        thread_id = str(thread.id)
                        
                        # ----------------------------------
                        # 🔒 MANDATORY ADMIN CHECK
                        # ----------------------------------
                        try:
                            raw_admin_ids = getattr(thread, "admin_user_ids", []) or []
                            admin_ids_str = {str(x) for x in raw_admin_ids}
                            is_bot_admin = bot_pk in admin_ids_str
                        except Exception:
                            is_bot_admin = False

                        if not is_bot_admin:
                            continue

                        users = list(getattr(thread, "users", []) or [])
                        current_members = {str(getattr(u, "pk", "")) for u in users if getattr(u, "pk", None)}

                        admins = get_admin_usernames(thread, bot_pk)
                        admins_text = admin_alert_text(admins)

                        # ----------------------------------
                        # 1. BULLETPROOF WELCOME HANDLER
                        # ----------------------------------
                        if thread_id not in initialized_threads:
                            # पहली बार जब इस ग्रुप को बोट देखेगा, तो सिर्फ मेंबर्स को सेव करेगा, वेलकम किसी को नहीं भेजेगा!
                            group_members[thread_id] = current_members
                            initialized_threads.add(thread_id)
                            logger.info(f"Thread {thread_id} initialized safely. Skipping initial welcome dump.")
                        else:
                            old_members = group_members.get(thread_id, set())
                            newly_joined = current_members - old_members

                            if newly_joined:
                                for joined_id in newly_joined:
                                    welcome_key = f"{thread_id}:{joined_id}"
                                    current_time = time.time()

                                    if welcome_key in recent_welcome_times and (current_time - recent_welcome_times[welcome_key] < 60):
                                        continue

                                    recent_welcome_times[welcome_key] = current_time

                                    user_obj = next((u for u in users if str(getattr(u, "pk", "")) == joined_id), None)
                                    if not user_obj:
                                        continue

                                    username = clean_username(getattr(user_obj, "username", "User"))

                                    try:
                                        welcome_msg = (
                                            f"🌸✨ 𝗪𝗘𝗟𝗖𝗢𝗠𝗘 𝗧𝗢 𝗚𝗖 ✨🌸\n\n"
                                            f"👋 𝗛𝗘𝗬 @{username}, 𝗪𝗘𝗟𝗖𝗢𝗠𝗘! 💗\n\n"
                                            f"🔥 𝗚𝗟𝗔𝗗 𝗧𝗢 𝗛𝗔𝗩𝗘 𝗬𝗢𝗨 𝗛𝗘𝗥𝗘!\n"
                                            f"🤝 𝗝𝗢𝗜𝗡 𝗧𝗛𝗘 𝗩𝗜𝗕𝗘 • 𝗦𝗧𝗔𝗬 𝗔𝗖𝗧𝗜𝗩𝗘 ✨\n\n"
                                            f"⚠️ 𝗥𝗘𝗦𝗣𝗘𝗖𝗧 𝗧𝗛𝗘 𝗚𝗖 • 𝗙𝗢𝗟𝗟𝗢𝗪 𝗧𝗛𝗘 𝗥𝗨𝗟𝗘𝗦\n\n"
                                            f"👑 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ @{OWNER_USERNAME}\n"
                                            f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}"
                                        )
                                        cl.direct_send(welcome_msg, thread_ids=[thread_id])
                                        logger.info(f"Real new member @{username} welcomed in thread {thread_id}")
                                        time.sleep(2)
                                    except Exception as e:
                                        logger.error(f"Welcome Error: {e}")

                            group_members[thread_id] = current_members

                        # ----------------------------------
                        # 2. STRICT ATOMIC MESSAGE SCANNER (NO DOUBLE MESSAGES)
                        # ----------------------------------
                        messages = list(getattr(thread, "messages", []) or [])
                        if not messages:
                            continue

                        for message in messages[:6]:
                            message_id = str(getattr(message, "id", ""))
                            if not message_id:
                                continue

                            # 🛑 सबसे पहले मैसेज आईडी को प्रोसेस्ड सेट में डालो ताकि डबल लूप इसे दोबारा छू न सके!
                            if message_id in processed_messages:
                                continue
                            processed_messages.add(message_id)

                            sender_id = str(getattr(message, "user_id", ""))
                            if sender_id == bot_pk:
                                continue

                            current_time = time.time()
                            if message_id in recent_action_times and (current_time - recent_action_times[message_id] < 30):
                                continue

                            text = str(getattr(message, "text", "") or "").strip()
                            clean_text_norm = normalize_text(text)
                            sender_username = get_sender_username(message, thread)

                            try:
                                is_sender_admin = sender_id in admin_ids_str

                                if not is_sender_admin:
                                    # चेक A: लिंक डिटेक्शन
                                    if is_link(text):
                                        recent_action_times[message_id] = current_time

                                        alert_msg = (
                                            f"🚨🔗 𝗟𝗜𝗡𝗞 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗!\n\n"
                                            f"👤 𝗨𝗦𝗘𝗥 ➜ @{sender_username}\n"
                                            f"⚠️ 𝗟𝗜𝗡𝗞𝗦 𝗔𝗥𝗘 𝗡𝗢𝗧 𝗔𝗟𝗟𝗢𝗪𝗘𝗗 𝗛𝗘𝗥𝗘.\n\n"
                                            f"👑 𝗔𝗗𝗠𝗜𝗡 ➜ {admins_text}\n"
                                            f"🔎 𝗣𝗟𝗘𝗔𝗦𝗘 𝗥𝗘𝗩𝗜𝗘𝗪.\n\n"
                                            f"👑 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ @{OWNER_USERNAME}\n"
                                            f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}"
                                        )
                                        cl.direct_send(alert_msg, thread_ids=[thread_id])
                                        logger.warning(f"Link blocked from @{sender_username}")
                                        time.sleep(2)
                                        continue

                                    # चेक B: रील या वीडियो डिटेक्शन
                                    if is_reel_or_video(message, text):
                                        recent_action_times[message_id] = current_time

                                        alert_msg = (
                                            f"🚫🎬 𝗥𝗘𝗘𝗟 / 𝗩𝗜𝗗𝗘𝗢 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗!\n\n"
                                            f"👤 𝗨𝗦𝗘𝗥 ➜ @{sender_username}\n"
                                            f"⚠️ 𝗥𝗘𝗘𝗟𝗦 / 𝗩𝗜𝗗𝗘𝗢𝗦 𝗔𝗥𝗘 𝗡𝗢𝗧 𝗔𝗟𝗟𝗢𝗪𝗘𝗗.\n\n"
                                            f"👑 𝗔𝗗𝗠𝗜𝗡 ➜ {admins_text}\n"
                                            f"🔎 𝗣𝗟𝗘𝗔𝗦𝗘 𝗥𝗘𝗩𝗜𝗘𝗪.\n\n"
                                            f"👑 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ @{OWNER_USERNAME}\n"
                                            f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}"
                                        )
                                        cl.direct_send(alert_msg, thread_ids=[thread_id])
                                        logger.warning(f"Reel blocked from @{sender_username}")
                                        time.sleep(2)
                                        continue

                                    # चेक C: गाली / एब्यूसिव वर्ड्स
                                    restricted_words = [
                                        "18", "adult", "sex", "xxx", "porn", "nude",
                                        "madhrchod", "madarchod", "madrchod", "mc",
                                        "bhosdike", "bsdk", "banchod", "bhenchod",
                                        "madar", "choot", "lund", "gandu"
                                    ]
                                    
                                    hit_abuse = any(word in clean_text_norm for word in restricted_words)

                                    if hit_abuse:
                                        recent_action_times[message_id] = current_time

                                        alert_msg = (
                                            f"🚨🛡️ 𝗠𝗢𝗗𝗘𝗥𝗔𝗧𝗜𝗢Ն 𝗔𝗟𝗘𝗥𝗧!\n\n"
                                            f"👤 𝗨𝗦𝗘𝗥 ➜ @{sender_username}\n"
                                            f"⚠️ 𝗜𝗡𝗔𝗣𝗣𝗥𝗢𝗣𝗥𝗜𝗔𝗧𝗘 𝗖𝗢𝗡𝗧𝗘𝗡𝗧 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗!\n\n"
                                            f"👑 ADMIN ➜ {admins_text}\n"
                                            f"🔎 𝗣𝗟𝗘𝗔𝗦𝗘 𝗥𝗘𝗩𝗜𝗘𝗪 & 𝗧𝗔𝗞𝗘 𝗔𝗖𝗧𝗜𝗢𝗡.\n\n"
                                            f"👑 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ @{OWNER_USERNAME}\n"
                                            f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}"
                                        )
                                        cl.direct_send(alert_msg, thread_ids=[thread_id])
                                        logger.warning(f"Abuse caught & reported for @{sender_username}: '{text}'")
                                        time.sleep(2)
                                        continue

                                # चेक D: बोट टैग रिप्लाई
                                bot_tag = f"@{BOT_USERNAME.lower()}"
                                if "@everyone" in text.lower() or bot_tag in text.lower():
                                    recent_action_times[message_id] = current_time

                                    response_msg = (
                                        f"👋 𝗛𝗘𝗬 @{sender_username}!\n\n"
                                        f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME} IS ACTIVE & READY! 🚀\n\n"
                                        f"👑 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ @{OWNER_USERNAME}"
                                    )
                                    cl.direct_send(response_msg, thread_ids=[thread_id])
                                    time.sleep(2)

                            except Exception as e:
                                logger.error(f"Message Processing Error: {e}")

                        # मेमोरी ऑटो-क्लीनअप
                        if len(processed_messages) > 3000:
                            processed_messages = set(list(processed_messages)[-1500:])
                        if len(recent_welcome_times) > 500:
                            recent_welcome_times.clear()
                        if len(recent_action_times) > 500:
                            recent_action_times.clear()

                except Exception as inner_e:
                    logger.error(f"Polling Loop Exception: {inner_e}")

                time.sleep(POLL_INTERVAL)

        except Exception as outer_e:
            logger.critical(f"Connection Lost / Reconnecting... Details: {outer_e}")
            time.sleep(20)


if __name__ == "__main__":
    logger.info("Starting Ultra-Stable Anti-Duplicate Instagram Bot...")
    start_bot()

