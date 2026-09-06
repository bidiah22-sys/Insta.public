import os
import time
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict, deque

from instagrapi import Client


# ============================================================
# CONFIG
# ============================================================

# Railway-compatible credentials.
# Nothing sensitive is hard-coded here.
# Supports either naming convention:
#   BOT_USERNAME / BOT_PASSWORD
# or:
#   INSTA_USERNAME / INSTA_PASSWORD
BOT_USERNAME = (
    os.getenv("BOT_USERNAME")
    or os.getenv("INSTA_USERNAME")
)

BOT_PASSWORD = (
    os.getenv("BOT_PASSWORD")
    or os.getenv("INSTA_PASSWORD")
)

OWNER_USERNAME = os.getenv("OWNER_USERNAME", "fx_smw")

POLL_SECONDS = float(os.getenv("POLL_SECONDS", "3"))
THREAD_BATCH_SIZE = int(os.getenv("THREAD_BATCH_SIZE", "20"))
MAX_SEEN_MESSAGES = int(os.getenv("MAX_SEEN_MESSAGES", "5000"))
WELCOME_COOLDOWN_SECONDS = int(os.getenv("WELCOME_COOLDOWN_SECONDS", "30"))
RECONNECT_BASE_SECONDS = int(os.getenv("RECONNECT_BASE_SECONDS", "10"))
RECONNECT_MAX_SECONDS = int(os.getenv("RECONNECT_MAX_SECONDS", "300"))
INBOX_403_COOLDOWN_SECONDS = int(os.getenv("INBOX_403_COOLDOWN_SECONDS", "900"))

STATE_FILE = Path(os.getenv("STATE_FILE", "bot_state.json"))
LOG_FILE = Path(os.getenv("LOG_FILE", "bot.log"))


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
log = logging.getLogger("gc-bot")


# ============================================================
# MODERATION CONFIG
# ============================================================

LINK_MARKERS = (
    "http://",
    "https://",
    "www.",
    "t.me/",
    "instagram.com/",
)

RESTRICTED_WORDS = {
    "18+",
    "adult",
    "sex",
    "xxx",
    "porn",
    "nude",
    "gali",
    "bhadve",
    "chutiya",
    "madarchod",
    "behenchod",
}

VIDEO_ITEM_TYPES = {
    "clip",
    "media",
    "video",
    "visual_media",
}


# ============================================================
# STATE
# ============================================================

class BotState:
    def __init__(self):
        self.group_members = {}
        self.ever_seen_members = set()
        self.welcomed_keys = set()
        self.seen_messages = deque(maxlen=MAX_SEEN_MESSAGES)
        self.last_action = {}
        self.gc_errors = defaultdict(int)

    def load(self):
        if not STATE_FILE.exists():
            return

        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))

            self.group_members = {
                str(k): set(map(str, v))
                for k, v in data.get("group_members", {}).items()
            }

            self.ever_seen_members = set(
                map(str, data.get("ever_seen_members", []))
            )

            self.welcomed_keys = set(
                map(str, data.get("welcomed_keys", []))
            )

            self.seen_messages.clear()
            self.seen_messages.extend(
                map(str, data.get("seen_messages", []))
            )

            self.last_action = {
                str(k): float(v)
                for k, v in data.get("last_action", {}).items()
            }

            log.info("Persistent state loaded.")

        except Exception as exc:
            log.warning("State load failed; starting safely: %s", exc)

    def save(self):
        try:
            payload = {
                "group_members": {
                    str(k): list(v)
                    for k, v in self.group_members.items()
                },
                "ever_seen_members": list(self.ever_seen_members),
                "welcomed_keys": list(self.welcomed_keys),
                "seen_messages": list(self.seen_messages),
                "last_action": self.last_action,
            }

            tmp = STATE_FILE.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(payload, ensure_ascii=False),
                encoding="utf-8",
            )
            tmp.replace(STATE_FILE)

        except Exception as exc:
            log.warning("State save failed: %s", exc)


# ============================================================
# HELPERS
# ============================================================

def now_ts():
    return time.time()


def normalize_username(username):
    return str(username or "User").lstrip("@").strip()


def safe_text(message):
    return str(getattr(message, "text", "") or "").strip()


def get_message_username(message):
    try:
        user = getattr(message, "user", None)
        return normalize_username(getattr(user, "username", "User"))
    except Exception:
        return "User"


def get_admin_ids(thread):
    admins = set()

    try:
        ids = getattr(thread, "admin_user_ids", None)
        if ids:
            admins.update(str(x) for x in ids)

        users = getattr(thread, "admin_users", None)
        if users:
            admins.update(
                str(getattr(x, "pk", x))
                for x in users
            )
    except Exception:
        pass

    return admins


def get_member_ids(thread):
    result = set()

    try:
        for user in getattr(thread, "users", []) or []:
            pk = getattr(user, "pk", None)
            if pk is not None:
                result.add(str(pk))
    except Exception:
        pass

    return result


def find_user(thread, user_id):
    try:
        for user in getattr(thread, "users", []) or []:
            if str(getattr(user, "pk", "")) == str(user_id):
                return user
    except Exception:
        pass

    return None


def looks_like_link(text):
    lowered = text.lower()
    return any(marker in lowered for marker in LINK_MARKERS)


def looks_like_video(message, text):
    item_type = str(getattr(message, "item_type", "") or "").lower()

    return (
        item_type in VIDEO_ITEM_TYPES
        or "video" in item_type
        or "/reel/" in text.lower()
    )


def contains_restricted_word(text):
    lowered = text.lower()
    return any(word in lowered for word in RESTRICTED_WORDS)


def can_act(state, key, cooldown):
    current = now_ts()
    previous = state.last_action.get(key, 0)

    if current - previous < cooldown:
        return False

    state.last_action[key] = current
    return True


def send_once(cl, state, thread_id, action_key, text):
    """
    Sends one moderation/welcome response only when the same
    action is not inside its cooldown window.
    """
    key = f"{thread_id}:{action_key}"

    if not can_act(state, key, WELCOME_COOLDOWN_SECONDS):
        log.info(
            "Suppressed duplicate action | thread=%s | action=%s",
            thread_id,
            action_key,
        )
        return False

    try:
        cl.direct_send(text, thread_ids=[thread_id])
        return True
    except Exception:
        # Roll back cooldown if the actual send failed.
        state.last_action.pop(key, None)
        raise


# ============================================================
# WELCOME
# ============================================================

def process_membership_changes(cl, state, thread, bot_pk, first_scan):
    thread_id = str(thread.id)
    current_members = get_member_ids(thread)

    if thread_id not in state.group_members:
        # First observation: establish baseline only.
        state.group_members[thread_id] = current_members
        state.ever_seen_members.update(current_members)
        return

    old_members = state.group_members[thread_id]
    newly_joined = current_members - old_members

    # Update state even if no action is required.
    state.group_members[thread_id] = current_members

    if first_scan or not newly_joined:
        state.ever_seen_members.update(current_members)
        return

    for joined_pk in newly_joined:
        if joined_pk == bot_pk:
            continue

        user = find_user(thread, joined_pk)
        if not user:
            state.ever_seen_members.add(joined_pk)
            continue

        username = normalize_username(
            getattr(user, "username", "User")
        )

        # Per-GC + per-user permanent protection.
        welcome_key = f"{thread_id}:{joined_pk}"

        if welcome_key in state.welcomed_keys:
            state.ever_seen_members.add(joined_pk)
            continue

        was_here_before = joined_pk in state.ever_seen_members

        if was_here_before:
            message = (
                f"💫🦋 𝗪𝗘𝗟𝗖𝗢𝗠𝗘 𝗕𝗔𝗖𝗞, @{username}! 🦋💫\n\n"
                f"🌷 𝗚𝗟𝗔𝗗 𝗧𝗢 𝗦𝗘𝗘 𝗬𝗢𝗨 𝗔𝗚𝗔𝗜𝗡!\n"
                f"🔥 𝗦𝗧𝗔𝗬 𝗔𝗖𝗧𝗜𝗩𝗘 • 𝗙𝗢𝗟𝗟𝗢𝗪 𝗧𝗛𝗘 𝗥𝗨𝗟𝗘𝗦\n\n"
                f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
                f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
            )
            action_name = f"welcome_back:{joined_pk}"
        else:
            message = (
                f"🦋✨ 𝗪𝗘𝗟𝗖𝗢𝗠𝗘, @{username}! ✨🦋\n\n"
                f"🌸 𝗚𝗟𝗔𝗗 𝗧𝗢 𝗛𝗔𝗩𝗘 𝗬𝗢𝗨 𝗛𝗘𝗥𝗘!\n"
                f"🤝 𝗦𝗧𝗔𝗬 𝗥𝗘𝗦𝗣𝗘𝗖𝗧𝗙𝗨𝗟 • 𝗙𝗢𝗟𝗟𝗢𝗪 𝗧𝗛𝗘 𝗥𝗨𝗟𝗘𝗦\n"
                f"🔥 𝗘𝗡𝗝𝗢𝗬 𝗧𝗛𝗘 𝗚𝗖 & 𝗦𝗧𝗔𝗬 𝗔𝗖𝗧𝗜𝗩𝗘!\n\n"
                f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
                f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
            )
            action_name = f"welcome:{joined_pk}"

        try:
            # Mark before sending to avoid two sends from overlapping scans.
            state.welcomed_keys.add(welcome_key)

            if send_once(
                cl,
                state,
                thread_id,
                action_name,
                message,
            ):
                log.info(
                    "Welcome action sent | thread=%s | user=@%s",
                    thread_id,
                    username,
                )

        except Exception as exc:
            # Allow retry after a real send failure.
            state.welcomed_keys.discard(welcome_key)
            log.warning(
                "Welcome send failed | thread=%s | user=@%s | %s",
                thread_id,
                username,
                exc,
            )

        state.ever_seen_members.add(joined_pk)


# ============================================================
# MODERATION
# ============================================================

def moderate_message(cl, state, thread, message, bot_pk):
    thread_id = str(thread.id)

    sender_id = str(getattr(message, "user_id", ""))
    if not sender_id or sender_id == bot_pk:
        return

    text = safe_text(message)
    text_lower = text.lower()
    username = get_message_username(message)

    admin_ids = get_admin_ids(thread)

    # Never moderate admins.
    if sender_id in admin_ids:
        return

    # --------------------------------------------------------
    # LINK
    # --------------------------------------------------------

    if looks_like_link(text):
        action_key = f"link:{sender_id}"

        if not can_act(
            state,
            f"{thread_id}:{action_key}",
            WELCOME_COOLDOWN_SECONDS,
        ):
            return

        message_text = (
            f"🚨🔗 𝗟𝗜𝗡𝗞 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗 — @{username}\n\n"
            f"⚠️ 𝗟𝗜𝗡𝗞𝗦 𝗔𝗥𝗘 𝗡𝗢𝗧 𝗔𝗟𝗟𝗢𝗪𝗘𝗗 𝗛𝗘𝗥𝗘.\n"
            f"🛑 𝗣𝗟𝗘𝗔𝗦𝗘 𝗥𝗘𝗠𝗢𝗩𝗘 𝗜𝗧 & 𝗙𝗢𝗟𝗟𝗢𝗪 𝗧𝗛𝗘 𝗥𝗨𝗟𝗘𝗦.\n\n"
            f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
        )

        try:
            cl.direct_send(
                message_text,
                thread_ids=[thread_id],
            )
            log.info(
                "Link warning | thread=%s | user=@%s",
                thread_id,
                username,
            )
        except Exception:
            state.last_action.pop(
                f"{thread_id}:{action_key}",
                None,
            )
            raise

        return

    # --------------------------------------------------------
    # REELS / VIDEO
    # --------------------------------------------------------

    if looks_like_video(message, text):
        action_key = f"video:{sender_id}"

        if not can_act(
            state,
            f"{thread_id}:{action_key}",
            WELCOME_COOLDOWN_SECONDS,
        ):
            return

        message_text = (
            f"🚫🎬 𝗥𝗘𝗘𝗟𝗦 / 𝗩𝗜𝗗𝗘𝗢 𝗡𝗢𝗧 𝗔𝗟𝗟𝗢𝗪𝗘𝗗!\n\n"
            f"👤 @{username}\n\n"
            f"⚠️ 𝗣𝗟𝗘𝗔𝗦𝗘 𝗙𝗢𝗟𝗟𝗢𝗪 𝗧𝗛𝗘 𝗚𝗖 𝗥𝗨𝗟𝗘𝗦.\n\n"
            f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
            f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
        )

        try:
            cl.direct_send(
                message_text,
                thread_ids=[thread_id],
            )
            log.info(
                "Video warning | thread=%s | user=@%s",
                thread_id,
                username,
            )
        except Exception:
            state.last_action.pop(
                f"{thread_id}:{action_key}",
                None,
            )
            raise

        return

    # --------------------------------------------------------
    # RESTRICTED TEXT
    # --------------------------------------------------------

    if contains_restricted_word(text):
        action_key = f"restricted:{sender_id}"

        if not can_act(
            state,
            f"{thread_id}:{action_key}",
            WELCOME_COOLDOWN_SECONDS,
        ):
            return

        admin_tag = "@ADMIN"

        for user in getattr(thread, "users", []) or []:
            if str(getattr(user, "pk", "")) in admin_ids:
                admin_tag = f"@{normalize_username(getattr(user, 'username', 'ADMIN'))}"
                break

        message_text = (
            f"🚨🛡️ 𝗠𝗢𝗗𝗘𝗥𝗔𝗧𝗜𝗢𝗡 𝗔𝗟𝗘𝗥𝗧!\n\n"
            f"👤 𝗨𝗦𝗘𝗥 ➜ @{username}\n"
            f"🚫 𝗜𝗡𝗔𝗣𝗣𝗥𝗢𝗣𝗥𝗜𝗔𝗧𝗘 𝗖𝗢𝗡𝗧𝗘𝗡𝗧 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗!\n\n"
            f"⚠️ 𝗧𝗛𝗜𝗦 𝗖𝗢𝗡𝗧𝗘𝗡𝗧 𝗜𝗦 𝗡𝗢𝗧 𝗔𝗟𝗟𝗢𝗪𝗘𝗗.\n"
            f"👑 𝗔𝗗𝗠𝗜𝗡 ➜ {admin_tag}\n"
            f"🔎 𝗣𝗟𝗘𝗔𝗦𝗘 𝗥𝗘𝗩𝗜𝗘𝗪 & 𝗧𝗔𝗞𝗘 𝗔𝗖𝗧𝗜𝗢𝗡.\n\n"
            f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
            f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
        )

        try:
            cl.direct_send(
                message_text,
                thread_ids=[thread_id],
            )
            log.info(
                "Restricted-content warning | thread=%s | user=@%s",
                thread_id,
                username,
            )
        except Exception:
            state.last_action.pop(
                f"{thread_id}:{action_key}",
                None,
            )
            raise


# ============================================================
# BOT TAG
# ============================================================

def process_bot_tag(cl, state, thread, message):
    text = safe_text(message).lower()
    if not text:
        return

    bot_tag = f"@{BOT_USERNAME.lower()}"

    if "@everyone" not in text and bot_tag not in text:
        return

    thread_id = str(thread.id)
    sender_username = get_message_username(message)

    action_key = f"tag:{getattr(message, 'id', '')}"

    if not can_act(
        state,
        f"{thread_id}:{action_key}",
        WELCOME_COOLDOWN_SECONDS,
    ):
        return

    response = (
        f"👋 𝗛𝗘𝗟𝗟𝗢 @{sender_username}!\n\n"
        f"🤖 𝗕𝗢𝗧 𝗜𝗦 𝗔𝗖𝗧𝗜𝗩𝗘 & 𝗠𝗢𝗡𝗜𝗧𝗢𝗥𝗜𝗡𝗚 𝗧𝗛𝗘 𝗚𝗖. 🚀\n\n"
        f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
        f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
    )

    try:
        cl.direct_send(
            response,
            thread_ids=[thread_id],
        )
    except Exception:
        state.last_action.pop(
            f"{thread_id}:{action_key}",
            None,
        )
        raise


# ============================================================
# THREAD PROCESSING
# ============================================================

def process_thread(cl, state, thread, bot_pk, first_scan):
    """
    One GC failing must not stop processing of other GCs.
    """

    thread_id = str(thread.id)

    try:
        process_membership_changes(
            cl,
            state,
            thread,
            bot_pk,
            first_scan,
        )

        messages = getattr(thread, "messages", None) or []

        if not messages:
            return

        # Process only messages we have not already seen.
        # We do not take action merely because a thread was scanned.
        for message in reversed(messages):
            message_id = str(getattr(message, "id", ""))

            if not message_id:
                continue

            if message_id in state.seen_messages:
                continue

            state.seen_messages.append(message_id)

            try:
                moderate_message(
                    cl,
                    state,
                    thread,
                    message,
                    bot_pk,
                )

                process_bot_tag(
                    cl,
                    state,
                    thread,
                    message,
                )

            except Exception as exc:
                state.gc_errors[thread_id] += 1
                log.warning(
                    "Message processing error | thread=%s | %s",
                    thread_id,
                    exc,
                )

    except Exception as exc:
        state.gc_errors[thread_id] += 1
        log.warning(
            "GC processing error | thread=%s | %s",
            thread_id,
            exc,
        )


# ============================================================
# INSTAGRAM INBOX ERROR HANDLING
# ============================================================

def is_inbox_403_error(exc):
    """
    Detect Instagram 403 / error_code 1404006 responses.
    This does not bypass the restriction; it prevents repeated
    requests from hammering the same endpoint.
    """
    text = str(exc).lower()
    return (
        "status_code" in text and "403" in text
        or "[403]" in text
        or "1404006" in text
    )


# ============================================================
# MAIN LOOP
# ============================================================


def create_client():
    cl = Client()
    cl.login(BOT_USERNAME, BOT_PASSWORD)
    return cl


def start_bot():
    if not BOT_USERNAME or not BOT_PASSWORD:
        raise RuntimeError(
            "Instagram credentials are missing. "
            "Set BOT_USERNAME + BOT_PASSWORD "
            "or INSTA_USERNAME + INSTA_PASSWORD "
            "in Railway Variables."
        )

    state = BotState()
    state.load()

    reconnect_delay = RECONNECT_BASE_SECONDS

    while True:
        cl = None

        try:
            log.info("Connecting to Instagram...")
            cl = create_client()

            bot_pk = str(cl.user_id)

            log.info(
                "Bot online: @%s | persistent monitoring enabled",
                BOT_USERNAME,
            )

            first_scan = True
            reconnect_delay = RECONNECT_BASE_SECONDS

            last_state_save = now_ts()

            while True:
                cycle_started = now_ts()

                try:
                    # Keep the polling loop alive continuously.
                    threads = cl.direct_threads(
                        amount=THREAD_BATCH_SIZE
                    )

                    for thread in threads:
                        if not getattr(thread, "is_group", False):
                            continue

                        process_thread(
                            cl,
                            state,
                            thread,
                            bot_pk,
                            first_scan,
                        )

                    first_scan = False

                    # Periodic persistent save.
                    if now_ts() - last_state_save >= 15:
                        state.save()
                        last_state_save = now_ts()

                except Exception as exc:
                    if is_inbox_403_error(exc):
                        log.error(
                            "Instagram inbox returned 403 / 1404006. "
                            "Pausing inbox polling for %s seconds. "
                            "This is a server-side/API response, not a "
                            "Python parsing error.",
                            INBOX_403_COOLDOWN_SECONDS,
                        )
                        time.sleep(INBOX_403_COOLDOWN_SECONDS)
                    else:
                        log.warning(
                            "Polling cycle error: %s",
                            exc,
                        )
                        time.sleep(min(30, max(3, POLL_SECONDS)))

                elapsed = now_ts() - cycle_started
                sleep_for = max(0.5, POLL_SECONDS - elapsed)
                time.sleep(sleep_for)

        except KeyboardInterrupt:
            log.info("Shutdown requested.")
            state.save()
            break

        except Exception as exc:
            log.error(
                "Connection/runtime error: %s",
                exc,
            )

            state.save()

            log.info(
                "Reconnecting in %s seconds...",
                reconnect_delay,
            )

            time.sleep(reconnect_delay)

            reconnect_delay = min(
                reconnect_delay * 2,
                RECONNECT_MAX_SECONDS,
            )


if __name__ == "__main__":
    start_bot()
