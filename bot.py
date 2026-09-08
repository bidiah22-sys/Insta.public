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
logger = logging.getLogger("SMW_AUTOKICK_STRICT")

# ==========================================
# CONFIGURATION
# ==========================================
BOT_USERNAME = os.getenv("BOT_USERNAME", "smw_bot0.1")
OWNER_USERNAME = "fx_smw"
SESSION_ID = "27413581604%3AouSmyrPKPDgZ9t%3A22%3AAYjPEsJzAujJahaw35cBMkO0idvr-xouZfgBEYczYA"
POLL_INTERVAL = 6

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
# MAIN AUTO-KICK ENGINE
# ==========================================

def start_bot():
    while True:
        try:
            logger.info("Initializing Instagram Client with Strict Auto-Kick Engine...")
            cl = Client()
            try:
                cl.delay_range = [2, 4]
            except Exception:
                pass

            cl.login_by_sessionid(SESSION_ID)
            bot_pk = str(cl.user_id)
            logger.info(f"SUCCESS: Bot @{BOT_USERNAME} logged in! (PK: {bot_pk})")

            processed_messages = set()
            recent_welcome_times = {}
            group_members = {}
            initialized_threads = set()

            while True:
                try:
                    threads = cl.direct_threads(amount=10)

                    for thread in threads:
                        if not getattr(thread, "is_group", False):
                            continue

                        thread_id = str(thread.id)
                        
                        # ----------------------------------
                        # 🔒 MANDATORY ADMIN CHECK (बोट एडमिन होना चाहिए)
                        # ----------------------------------
                        try:
                            raw_admin_ids = getattr(thread, "admin_user_ids", []) or []
                            admin_ids_str = {str(x) for x in raw_admin_ids}
                            is_bot_admin = bot_pk in admin_ids_str
                        except Exception:
                            is_bot_admin = False

                        # अगर बोट इस ग्रुप में एडमिन नहीं है, तो इस ग्रुप को पूरी तरह छोड़ दो!
                        if not is_bot_admin:
                            continue

                        users = list(getattr(thread, "users", []) or [])
                        current_members = {str(getattr(u, "pk", "")) for u in users if getattr(u, "pk", None)}

                        # ----------------------------------
                        # 1. WELCOME HANDLER (सिर्फ नए मेंबर्स के लिए)
                        # ----------------------------------
                        if thread_id not in initialized_threads:
                            group_members[thread_id] = current_members
                            initialized_threads.add(thread_id)
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
                                        logger.info(f"Welcomed @{username} in thread {thread_id}")
                                        time.sleep(2)
                                    except Exception as e:
                                        logger.error(f"Welcome Error: {e}")

                            group_members[thread_id] = current_members

                        # ----------------------------------
                        # 2. STRICT AUTO-KICK SCANNER
                        # ----------------------------------
                        messages = list(getattr(thread, "messages", []) or [])
                        if not messages:
                            continue

                        for message in messages[:5]:
                            message_id = str(getattr(message, "id", ""))
                            if not message_id or message_id in processed_messages:
                                continue

                            # डबल मैसेज रोकने के लिए तुरंत लॉक करें
                            processed_messages.add(message_id)

                            sender_id = str(getattr(message, "user_id", ""))
                            if sender_id == bot_pk:
                                continue

                            text = str(getattr(message, "text", "") or "").strip()
                            clean_text_norm = normalize_text(text)
                            sender_username = get_sender_username(message, thread)

                            try:
                                # अगर भेजने वाला खुद एडमिन है, तो उसे किक नहीं करना
                                if sender_id in admin_ids_str:
                                    continue

                                should_kick = False
                                violation_type = ""

                                # नियम A: लिंक या इनवाइट
                                if is_link(text):
                                    should_kick = True
                                    violation_type = "LINK / INVITE"

                                # नियम B: रील या वीडियो
                                elif is_reel_or_video(message, text):
                                    should_kick = True
                                    violation_type = "REEL / VIDEO"

                                # नियम C: गालियां या एब्यूज
                                else:
                                    restricted_words = [
                                        "18", "adult", "sex", "xxx", "porn", "nude",
                                        "madhrchod", "madarchod", "madrchod", "mc",
                                        "bhosdike", "bsdk", "banchod", "bhenchod",
                                        "madar", "choot", "lund", "gandu"
                                    ]
                                    if any(word in clean_text_norm for word in restricted_words):
                                        should_kick = True
                                        violation_type = "ABUSE / SLANG"

                                # अगर नियम टूटा है तो सीधे किक करो!
                                if should_kick:
                                    logger.warning(f"Violation ({violation_type}) by @{sender_username}. Executing Auto-Kick...")
                                    
                                    try:
                                        cl.direct_thread_remove_user(thread_id, sender_id)
                                        logger.info(f"Successfully kicked @{sender_username} from thread {thread_id}")
                                    except Exception as kick_err:
                                        logger.error(f"Kick command failed: {kick_err}")

                                    # ग्रुप में इन्फॉर्म करने के लिए छोटा सा अलर्ट मैसेज
                                    alert_msg = (
                                        f"🚨 𝗔𝗨𝗧𝗢-𝗞𝗜𝗖𝗞 𝗔𝗟𝗘𝗥𝗧 🚨\n\n"
                                        f"👤 𝗨𝗦𝗘𝗥 ➜ @{sender_username}\n"
                                        f"⚠️ 𝗥𝗘𝗔𝗦𝗢𝗡 ➜ {violation_type} 𝗡𝗢𝗧 𝗔𝗟𝗟𝗢𝗪𝗘𝗗!\n"
                                        f"👢 𝗦𝗧𝗔𝗧𝗨𝗦 ➜ 𝗞𝗜𝗖𝗞𝗘𝗗 𝗢𝗨𝗧 𝗢𝗙 𝗧𝗛𝗘 𝗚𝗖!\n\n"
                                        f"👑 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ @{OWNER_USERNAME}\n"
                                        f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}"
                                    )
                                    cl.direct_send(alert_msg, thread_ids=[thread_id])
                                    time.sleep(2)

                            except Exception as e:
                                logger.error(f"Processing Error: {e}")

                        # मेमोरी क्लीनअप
                        if len(processed_messages) > 2000:
                            processed_messages = set(list(processed_messages)[-1000:])
                        if len(recent_welcome_times) > 400:
                            recent_welcome_times.clear()

                except Exception as inner_e:
                    logger.error(f"Polling Loop Exception: {inner_e}")

                time.sleep(POLL_INTERVAL)

        except Exception as outer_e:
            logger.critical(f"Connection Lost / Reconnecting... Details: {outer_e}")
            time.sleep(20)


if __name__ == "__main__":
    logger.info("Starting Strict Auto-Kick Instagram Bot...")
    start_bot()

