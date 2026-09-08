import os
import time
import re
from instagrapi import Client

# =========================
# CONFIG
# =========================

BOT_USERNAME = os.getenv("BOT_USERNAME", "bot222703")
OWNER_USERNAME = "fx_smw"

# ==========================================
# यहाँ अपनी लैपटॉप से निकाली हुई Session ID डाल
# ==========================================
SESSION_ID = "27413581604%3A91cVN5zOMUK05d%3A5%3AAYhafaXxMTZ1DIBd5DyT1RiuLCVGMmbf0qQbSjOINA"

POLL_INTERVAL = 5

if not SESSION_ID or SESSION_ID == "YAHAN_APNI_SESSION_ID_DAL":
    raise RuntimeError("Valid Instagram Session ID is missing in code or environment variables.")


# =========================
# HELPERS
# =========================

def clean_username(username):
    if not username:
        return "User"
    return str(username).lstrip("@").strip()


def get_sender_username(message):
    try:
        if getattr(message, "user", None):
            return clean_username(message.user.username)
    except Exception:
        pass

    return "User"


def get_admin_usernames(thread, bot_pk):
    """
    GC के available admins निकालता है.
    Bot को admin alert में include नहीं करता.
    """
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

            if (
                uid
                and uid in admin_ids
                and uid != str(bot_pk)
                and username
                and username != "User"
            ):
                admins.append(username)
    except Exception:
        pass

    # duplicate usernames हटाओ
    return list(dict.fromkeys(admins))


def admin_alert_text(admins):
    if not admins:
        return "@ADMIN"

    return " ".join(f"@{username}" for username in admins)


def is_link(text):
    text = (text or "").lower()

    patterns = [
        r"https?://",
        r"www\.",
        r"\b[a-z0-9-]+\.(com|net|org|in|co|io|me|xyz|shop|site|online)\b",
        r"t\.me/",
        r"instagram\.com/",
    ]

    return any(re.search(pattern, text) for pattern in patterns)


def is_reel_or_video(message, text):
    text = (text or "").lower()
    item_type = str(getattr(message, "item_type", "") or "").lower()

    video_types = {
        "clip",
        "video",
        "visual_media",
        "media",
    }

    video_words = [
        "/reel/",
        "/reels/",
    ]

    return (
        item_type in video_types
        or "video" in item_type
        or any(x in text for x in video_words)
    )


# =========================
# BOT
# =========================

def start_bot():

    while True:

        try:
            print("[*] Connecting to Instagram via Session ID...")

            cl = Client()

            # Rate-limit friendly delay
            try:
                cl.delay_range = [1, 2]
            except Exception:
                pass

            # SESSION-ID LOGIN
            cl.login_by_sessionid(SESSION_ID)

            bot_pk = str(cl.user_id)

            print(
                f"[+] BOT @{BOT_USERNAME} IS LIVE 🚀"
            )

            # ---------------------------------
            # IMPORTANT DEDUPE STATE
            # ---------------------------------

            processed_messages = set()

            # Welcome key: thread_id:user_id
            welcomed_users = set()

            # Prevent same message from being processed
            processing_messages = set()

            # Prevent same welcome from being sent twice.
            processing_welcomes = set()

            # GC member state
            group_members = {}

            first_scan = True

            # =========================
            # MAIN LOOP
            # =========================

            while True:

                try:

                    threads = cl.direct_threads(amount=10)

                    for thread in threads:

                        if not getattr(thread, "is_group", False):
                            continue

                        thread_id = str(thread.id)

                        users = list(
                            getattr(thread, "users", []) or []
                        )

                        current_members = {
                            str(getattr(user, "pk", ""))
                            for user in users
                            if getattr(user, "pk", None)
                        }

                        # ==================================
                        # ADMIN LIST
                        # ==================================

                        admins = get_admin_usernames(
                            thread,
                            bot_pk
                        )

                        admins_text = admin_alert_text(admins)

                        # ==================================
                        # WELCOME (DOUBLE MESSAGE FIX)
                        # ==================================

                        old_members = group_members.get(
                            thread_id,
                            set()
                        )

                        if not first_scan:

                            newly_joined = (
                                current_members - old_members
                            )

                            for joined_id in newly_joined:

                                welcome_key = (
                                    f"{thread_id}:{joined_id}"
                                )

                                # HARD DEDUPE & INSTANT LOCK
                                if welcome_key in welcomed_users:
                                    continue

                                if welcome_key in processing_welcomes:
                                    continue

                                user_obj = next(
                                    (
                                        u for u in users
                                        if str(getattr(u, "pk", "")) == joined_id
                                    ),
                                    None
                                )

                                if not user_obj:
                                    continue

                                username = clean_username(
                                    getattr(
                                        user_obj,
                                        "username",
                                        "User"
                                    )
                                )

                                # भेजने से ठीक पहले लॉक करो ताकि दूसरा लूप इसे न पकड़ सके
                                processing_welcomes.add(welcome_key)
                                welcomed_users.add(welcome_key)

                                try:

                                    welcome_message = (
                                        f"🌸✨ 𝗪𝗘𝗟𝗖𝗢𝗠𝗘 𝗧𝗢 𝗚𝗖 ✨🌸\n\n"
                                        f"👋 𝗛𝗘𝗬 @{username}, 𝗪𝗘𝗟𝗖𝗢𝗠𝗘! 💗\n\n"
                                        f"🔥 𝗚𝗟𝗔𝗗 𝗧𝗢 𝗛𝗔𝗩𝗘 𝗬𝗢𝗨 𝗛𝗘𝗥𝗘!\n"
                                        f"🤝 𝗝𝗢𝗜𝗡 𝗧𝗛𝗘 𝗩𝗜𝗕𝗘 • 𝗦𝗧𝗔𝗬 𝗔𝗖𝗧𝗜𝗩𝗘 ✨\n\n"
                                        f"⚠️ 𝗥𝗘𝗦𝗣𝗘𝗖𝗧 𝗧𝗛𝗘 𝗚𝗖 • 𝗙𝗢𝗟𝗟𝗢𝗪 𝗧𝗛𝗘 𝗥𝗨𝗟𝗘𝗦\n\n"
                                        f"👑 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ @{OWNER_USERNAME}\n"
                                        f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}"
                                    )

                                    cl.direct_send(
                                        welcome_message,
                                        thread_ids=[thread_id]
                                    )

                                except Exception as e:
                                    print(
                                        f"[WELCOME ERROR] {e}"
                                    )
                                    welcomed_users.discard(welcome_key)

                                finally:
                                    processing_welcomes.discard(
                                        welcome_key
                                    )

                        group_members[thread_id] = (
                            current_members
                        )

                        # ==================================
                        # MESSAGE SCANNER
                        # ==================================

                        messages = list(
                            getattr(thread, "messages", [])
                            or []
                        )

                        if not messages:
                            continue

                        for message in messages[:5]:

                            message_id = str(
                                getattr(message, "id", "")
                            )

                            if not message_id:
                                continue

                            # ==================================
                            # HARD MESSAGE DEDUPE
                            # ==================================

                            if message_id in processed_messages:
                                continue

                            if message_id in processing_messages:
                                continue

                            sender_id = str(
                                getattr(
                                    message,
                                    "user_id",
                                    ""
                                )
                            )

                            # Ignore bot's own messages.
                            if sender_id == bot_pk:
                                processed_messages.add(
                                    message_id
                                )
                                continue

                            text = str(
                                getattr(
                                    message,
                                    "text",
                                    ""
                                ) or ""
                            ).strip()

                            text_lower = text.lower()

                            sender_username = (
                                get_sender_username(message)
                            )

                            item_type = str(
                                getattr(
                                    message,
                                    "item_type",
                                    ""
                                ) or ""
                            ).lower()

                            # Reserve BEFORE processing.
                            processing_messages.add(
                                message_id
                            )

                            try:

                                # ==================================
                                # ADMIN CHECK
                                # ==================================

                                try:
                                    raw_admin_ids = getattr(
                                        thread,
                                        "admin_user_ids",
                                        []
                                    ) or []

                                    is_admin = (
                                        sender_id
                                        in {
                                            str(x)
                                            for x in raw_admin_ids
                                        }
                                    )

                                except Exception:
                                    is_admin = False

                                # ==================================
                                # NON-ADMIN MODERATION
                                # ==================================

                                if not is_admin:

                                    # ------------------------------
                                    # LINK
                                    # ------------------------------

                                    if is_link(text):

                                        response = (
                                            f"🚨🔗 𝗟𝗜𝗡𝗞 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗!\n\n"
                                            f"👤 𝗨𝗦𝗘𝗥 ➜ @{sender_username}\n"
                                            f"⚠️ 𝗟𝗜𝗡𝗞𝗦 𝗔𝗥𝗘 𝗡𝗢𝗧 𝗔𝗟𝗟𝗢𝗪𝗘𝗗 𝗛𝗘𝗥𝗘.\n\n"
                                            f"👑 𝗔𝗗𝗠𝗜𝗡 ➜ {admins_text}\n"
                                            f"🔎 𝗣𝗟𝗘𝗔𝗦𝗘 𝗥𝗘𝗩𝗜𝗘𝗪.\n\n"
                                            f"👑 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ @{OWNER_USERNAME}\n"
                                            f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}"
                                        )

                                        cl.direct_send(
                                            response,
                                            thread_ids=[thread_id]
                                        )

                                        processed_messages.add(
                                            message_id
                                        )

                                        continue

                                    # ------------------------------
                                    # REEL / VIDEO
                                    # ------------------------------

                                    if is_reel_or_video(
                                        message,
                                        text
                                    ):

                                        response = (
                                            f"🚫🎬 𝗥𝗘𝗘𝗟 / 𝗩𝗜𝗗𝗘𝗢 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗!\n\n"
                                            f"👤 𝗨𝗦𝗘𝗥 ➜ @{sender_username}\n"
                                            f"⚠️ 𝗥𝗘𝗘𝗟𝗦 / 𝗩𝗜𝗗𝗘𝗢𝗦 𝗔𝗥𝗘 𝗡𝗢𝗧 𝗔𝗟𝗟𝗢𝗪𝗘𝗗.\n\n"
                                            f"👑 𝗔𝗗𝗠𝗜𝗡 ➜ {admins_text}\n"
                                            f"🔎 𝗣𝗟𝗘𝗔𝗦𝗘 𝗥𝗘𝗩𝗜𝗘𝗪.\n\n"
                                            f"👑 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ @{OWNER_USERNAME}\n"
                                            f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}"
                                        )

                                        cl.direct_send(
                                            response,
                                            thread_ids=[thread_id]
                                        )

                                        processed_messages.add(
                                            message_id
                                        )

                                        continue

                                    # ------------------------------
                                    # BAD WORD / UNSAFE CONTENT
                                    # ------------------------------

                                    restricted_words = [
                                        "18+",
                                        "adult",
                                        "sex",
                                        "xxx",
                                        "porn",
                                        "nude",
                                    ]

                                    if any(
                                        word in text_lower
                                        for word in restricted_words
                                    ):

                                        response = (
                                            f"🚨🛡️ 𝗠𝗢𝗗𝗘𝗥𝗔𝗧𝗜𝗢𝗡 𝗔𝗟𝗘𝗥𝗧!\n\n"
                                            f"👤 𝗨𝗦𝗘𝗥 ➜ @{sender_username}\n"
                                            f"⚠️ 𝗜𝗡𝗔𝗣𝗣𝗥𝗢𝗣𝗥𝗜𝗔𝗧𝗘 𝗖𝗢𝗡𝗧𝗘𝗡𝗧 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗!\n\n"
                                            f"👑 ADMIN ➜ {admins_text}\n"
                                            f"🔎 𝗣𝗟𝗘𝗔𝗦𝗘 𝗥𝗘𝗩𝗜𝗘𝗪 & 𝗧𝗔𝗞𝗘 𝗔𝗖𝗧𝗜𝗢𝗡.\n\n"
                                            f"👑 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ @{OWNER_USERNAME}\n"
                                            f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}"
                                        )

                                        cl.direct_send(
                                            response,
                                            thread_ids=[thread_id]
                                        )

                                        processed_messages.add(
                                            message_id
                                        )

                                        continue

                                # ==================================
                                # @BOT / @EVERYONE
                                # ==================================

                                bot_tag = (
                                    f"@{BOT_USERNAME.lower()}"
                                )

                                if (
                                    "@everyone"
                                    in text_lower
                                    or bot_tag
                                    in text_lower
                                ):

                                    response = (
                                        f"👋 𝗛𝗘𝗬 @{sender_username}!\n\n"
                                        f"🤖 𝗕𝗢𝗧 𝗜𝗦 𝗔𝗖𝗧𝗜𝗩𝗘 & 𝗥𝗘𝗔𝗗𝗬! 🚀\n\n"
                                        f"👑 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ @{OWNER_USERNAME}\n"
                                        f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}"
                                    )

                                    cl.direct_send(
                                        response,
                                        thread_ids=[thread_id]
                                    )

                                processed_messages.add(
                                    message_id
                                )

                            except Exception as e:
                                print(
                                    f"[MESSAGE ERROR] {e}"
                                )

                            finally:
                                processing_messages.discard(
                                    message_id
                                )

                        # Keep memory bounded
                        if len(processed_messages) > 2000:
                            processed_messages = set(
                                list(processed_messages)[-1000:]
                            )

                    first_scan = False

                except Exception as e:
                    print(
                        f"[LOOP ERROR] {e}"
                    )

                time.sleep(POLL_INTERVAL)

        except Exception as e:

            print(
                f"[-] RECONNECTING... {e}"
            )

            time.sleep(15)


if __name__ == "__main__":
    start_bot()

