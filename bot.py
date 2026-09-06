import os
import time
import json
import logging
from pathlib import Path
from collections import defaultdict, deque

from instagrapi import Client

# ============================================================
# RAILWAY CONFIG
# ============================================================
# Credentials are ONLY read from Railway Variables.
BOT_USERNAME = os.getenv("BOT_USERNAME") or os.getenv("INSTA_USERNAME")
BOT_PASSWORD = os.getenv("BOT_PASSWORD") or os.getenv("INSTA_PASSWORD")
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "fx_smw")

# Safer default pacing. Override in Railway Variables if needed.
POLL_SECONDS = float(os.getenv("POLL_SECONDS", "15"))
THREAD_BATCH_SIZE = int(os.getenv("THREAD_BATCH_SIZE", "20"))
THREAD_MESSAGE_LIMIT = int(os.getenv("THREAD_MESSAGE_LIMIT", "20"))
MAX_SEEN_MESSAGES = int(os.getenv("MAX_SEEN_MESSAGES", "10000"))
ACTION_COOLDOWN_SECONDS = int(os.getenv("ACTION_COOLDOWN_SECONDS", "30"))
STATE_SAVE_SECONDS = int(os.getenv("STATE_SAVE_SECONDS", "30"))
INBOX_403_COOLDOWN_SECONDS = int(os.getenv("INBOX_403_COOLDOWN_SECONDS", "900"))
RECONNECT_BASE_SECONDS = int(os.getenv("RECONNECT_BASE_SECONDS", "15"))
RECONNECT_MAX_SECONDS = int(os.getenv("RECONNECT_MAX_SECONDS", "300"))

STATE_FILE = Path(os.getenv("STATE_FILE", "bot_state.json"))
LOG_FILE = Path(os.getenv("LOG_FILE", "bot.log"))
SESSION_FILE = Path(os.getenv("SESSION_FILE", "instagram_session.json"))

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
log = logging.getLogger("instagram-gc-bot")

# ============================================================
# MODERATION RULES
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
            log.info("No previous state found; starting fresh.")
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
            self.seen_messages.extend(
                map(str, data.get("seen_messages", []))
            )
            self.last_action = {
                str(k): float(v)
                for k, v in data.get("last_action", {}).items()
            }
            log.info(
                "State loaded | known_groups=%d | seen_messages=%d",
                len(self.group_members),
                len(self.seen_messages),
            )
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


def get_admin_ids(thread):
    result = set()
    try:
        ids = getattr(thread, "admin_user_ids", None)
        if ids:
            result.update(str(x) for x in ids)
        users = getattr(thread, "admin_users", None)
        if users:
            result.update(str(getattr(x, "pk", x)) for x in users)
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


def can_act(state, key):
    current = now_ts()
    previous = state.last_action.get(key, 0)
    if current - previous < ACTION_COOLDOWN_SECONDS:
        return False
    state.last_action[key] = current
    return True


def send_once(cl, state, thread_id, action_key, text):
    key = f"{thread_id}:{action_key}"
    if not can_act(state, key):
        return False

    try:
        cl.direct_send(text, thread_ids=[thread_id])
        return True
    except Exception:
        state.last_action.pop(key, None)
        raise

# ============================================================
# WELCOME / WELCOME BACK
# ============================================================
def process_membership_changes(cl, state, thread, bot_pk, first_scan):
    thread_id = str(thread.id)
    current_members = get_member_ids(thread)

    if thread_id not in state.group_members:
        state.group_members[thread_id] = current_members
        state.ever_seen_members.update(current_members)
        return

    old_members = state.group_members[thread_id]
    newly_joined = current_members - old_members
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

        username = normalize_username(getattr(user, "username", "User"))
        welcome_key = f"{thread_id}:{joined_pk}"

        if welcome_key in state.welcomed_keys:
            state.ever_seen_members.add(joined_pk)
            continue

        if joined_pk in state.ever_seen_members:
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
            state.welcomed_keys.add(welcome_key)
            if send_once(cl, state, thread_id, action_name, message):
                log.info(
                    "WELCOME SENT | thread=%s | user=@%s",
                    thread_id,
                    username,
                )
        except Exception as exc:
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
    username = get_message_username(message)
    admin_ids = get_admin_ids(thread)

    if sender_id in admin_ids:
        return

    if looks_like_link(text):
        message_text = (
            f"🚨🔗 𝗟𝗜𝗡𝗞 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗 — @{username}\n\n"
            f"⚠️ 𝗟𝗜𝗡𝗞𝗦 𝗔𝗥𝗘 𝗡𝗢𝗧 𝗔𝗟𝗟𝗢𝗪𝗘𝗗 𝗛𝗘𝗥𝗘.\n"
            f"🛑 𝗣𝗟𝗘𝗔𝗦𝗘 𝗥𝗘𝗠𝗢𝗩𝗘 𝗜𝗧 & 𝗙𝗢𝗟𝗟𝗢𝗪 𝗧𝗛𝗘 𝗥𝗨𝗟𝗘𝗦.\n\n"
            f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
        )
        if send_once(cl, state, thread_id, f"link:{sender_id}", message_text):
            log.info("LINK WARNING SENT | thread=%s | user=@%s", thread_id, username)
        return

    if looks_like_video(message, text):
        message_text = (
            f"🚫🎬 𝗥𝗘𝗘𝗟𝗦 / 𝗩𝗜𝗗𝗘𝗢 𝗡𝗢𝗧 𝗔𝗟𝗟𝗢𝗪𝗘𝗗!\n\n"
            f"👤 @{username}\n\n"
            f"⚠️ 𝗣𝗟𝗘𝗔𝗦𝗘 𝗙𝗢𝗟𝗟𝗢𝗪 𝗧𝗛𝗘 𝗚𝗖 𝗥𝗨𝗟𝗘𝗦.\n\n"
            f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
            f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
        )
        if send_once(cl, state, thread_id, f"video:{sender_id}", message_text):
            log.info("VIDEO WARNING SENT | thread=%s | user=@%s", thread_id, username)
        return

    if contains_restricted_word(text):
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
        if send_once(cl, state, thread_id, f"restricted:{sender_id}", message_text):
            log.info("MODERATION WARNING SENT | thread=%s | user=@%s", thread_id, username)

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
    response = (
        f"👋 𝗛𝗘𝗟𝗟𝗢 @{sender_username}!\n\n"
        f"🤖 𝗕𝗢𝗧 𝗜𝗦 𝗔𝗖𝗧𝗜𝗩𝗘 & 𝗠𝗢𝗡𝗜𝗧𝗢𝗥𝗜𝗡𝗚 𝗧𝗛𝗘 𝗚𝗖. 🚀\n\n"
        f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
        f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
    )
    if send_once(cl, state, thread_id, f"tag:{getattr(message, 'id', '')}", response):
        log.info("TAG RESPONSE SENT | thread=%s | user=@%s", thread_id, sender_username)

# ============================================================
# THREAD PROCESSING
# ============================================================
def process_thread(cl, state, thread, bot_pk, first_scan):
    thread_id = str(getattr(thread, "id", ""))
    title = str(getattr(thread, "thread_title", "") or getattr(thread, "title", "") or "Unnamed GC")

    try:
        process_membership_changes(cl, state, thread, bot_pk, first_scan)

        messages = getattr(thread, "messages", None) or []
        log.info(
            "GC SCAN | thread=%s | title=%s | messages=%d | members=%d",
            thread_id,
            title[:60],
            len(messages),
            len(getattr(thread, "users", []) or []),
        )

        for message in reversed(messages):
            message_id = str(getattr(message, "id", ""))
            if not message_id or message_id in state.seen_messages:
                continue

            state.seen_messages.append(message_id)
            try:
                moderate_message(cl, state, thread, message, bot_pk)
                process_bot_tag(cl, state, thread, message)
            except Exception as exc:
                state.gc_errors[thread_id] += 1
                log.warning(
                    "MESSAGE ACTION ERROR | thread=%s | %s: %s",
                    thread_id,
                    type(exc).__name__,
                    exc,
                )

    except Exception as exc:
        state.gc_errors[thread_id] += 1
        log.warning(
            "GC PROCESS ERROR | thread=%s | %s: %s",
            thread_id,
            type(exc).__name__,
            exc,
        )

# ============================================================
# ERROR HANDLING
# ============================================================
def is_inbox_403_error(exc):
    text = str(exc).lower()
    return (
        "status_code" in text and "403" in text
        or "[403]" in text
        or "1404006" in text
    )

# ============================================================
# SESSION / CLIENT
# ============================================================
def create_client():
    cl = Client()

    # Reuse a locally stored instagrapi settings file when available.
    # Never print its contents to logs.
    if SESSION_FILE.exists():
        try:
            cl.load_settings(SESSION_FILE)
            log.info("Previous Instagram session settings loaded.")
        except Exception as exc:
            log.warning("Previous session settings could not be loaded: %s", exc)

    cl.login(BOT_USERNAME, BOT_PASSWORD)

    try:
        cl.dump_settings(SESSION_FILE)
        log.info("Instagram session settings saved locally.")
    except Exception as exc:
        log.warning("Session settings save skipped: %s", exc)

    return cl

# ============================================================
# MAIN LOOP
# ============================================================
def start_bot():
    if not BOT_USERNAME or not BOT_PASSWORD:
        raise RuntimeError(
            "Instagram credentials are missing. Set BOT_USERNAME + BOT_PASSWORD "
            "or INSTA_USERNAME + INSTA_PASSWORD in Railway Variables."
        )

    state = BotState()
    state.load()
    reconnect_delay = RECONNECT_BASE_SECONDS

    while True:
        try:
            log.info("====================================================")
            log.info("CONNECTING TO INSTAGRAM")
            cl = create_client()
            bot_pk = str(cl.user_id)
            log.info("BOT ONLINE | @%s | user_id=%s", BOT_USERNAME, bot_pk)
            log.info(
                "MONITOR CONFIG | poll=%ss | threads=%d | messages/thread=%d",
                POLL_SECONDS,
                THREAD_BATCH_SIZE,
                THREAD_MESSAGE_LIMIT,
            )

            first_scan = True
            reconnect_delay = RECONNECT_BASE_SECONDS
            last_state_save = now_ts()

            while True:
                cycle_started = now_ts()
                log.info("INBOX POLL START")

                try:
                    # thread_message_limit is important: it asks the inbox
                    # response to include recent messages for each thread.
                    threads = cl.direct_threads(
                        amount=THREAD_BATCH_SIZE,
                        thread_message_limit=THREAD_MESSAGE_LIMIT,
                    )

                    group_threads = [
                        thread
                        for thread in threads
                        if getattr(thread, "is_group", False)
                    ]

                    log.info(
                        "INBOX OK | threads=%d | group_threads=%d",
                        len(threads),
                        len(group_threads),
                    )

                    for thread in group_threads:
                        process_thread(
                            cl,
                            state,
                            thread,
                            bot_pk,
                            first_scan,
                        )

                    first_scan = False

                    if now_ts() - last_state_save >= STATE_SAVE_SECONDS:
                        state.save()
                        last_state_save = now_ts()
                        log.info("STATE SAVED | known_groups=%d", len(state.group_members))

                except Exception as exc:
                    if is_inbox_403_error(exc):
                        log.error(
                            "INBOX ACCESS 403 / 1404006 | Instagram rejected the Direct inbox request. "
                            "Pausing for %ss; no bypass is attempted.",
                            INBOX_403_COOLDOWN_SECONDS,
                        )
                        time.sleep(INBOX_403_COOLDOWN_SECONDS)
                    else:
                        log.warning(
                            "INBOX POLL ERROR | %s: %s",
                            type(exc).__name__,
                            exc,
                        )
                        time.sleep(min(60, max(5, POLL_SECONDS)))

                elapsed = now_ts() - cycle_started
                time.sleep(max(0.5, POLL_SECONDS - elapsed))

        except KeyboardInterrupt:
            log.info("Shutdown requested.")
            state.save()
            break

        except Exception as exc:
            state.save()
            log.error(
                "RUNTIME ERROR | %s: %s",
                type(exc).__name__,
                exc,
            )
            log.info("RECONNECTING IN %ss", reconnect_delay)
            time.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, RECONNECT_MAX_SECONDS)


if __name__ == "__main__":
    start_bot()
