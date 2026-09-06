import os
import time
import json
import logging
import importlib.metadata
from pathlib import Path
from collections import defaultdict, deque

from instagrapi import Client

# ============================================================
# Instagram GC Moderator - Railway FINAL DIAGNOSTIC/SAFE BUILD
# ============================================================
# IMPORTANT:
# - Credentials are read ONLY from Railway environment variables.
# - This build does NOT bypass Instagram 403/rate limits.
# - It performs one inbox-access test, then monitors conservatively.
# - If Instagram rejects Direct inbox access, it pauses instead of
#   hammering the endpoint.
# ============================================================

BOT_USERNAME = os.getenv("BOT_USERNAME") or os.getenv("INSTA_USERNAME")
BOT_PASSWORD = os.getenv("BOT_PASSWORD") or os.getenv("INSTA_PASSWORD")
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "fx_smw")

POLL_SECONDS = max(20, int(os.getenv("POLL_SECONDS", "30")))
THREAD_BATCH_SIZE = min(20, max(1, int(os.getenv("THREAD_BATCH_SIZE", "20"))))
THREAD_MESSAGE_LIMIT = min(20, max(1, int(os.getenv("THREAD_MESSAGE_LIMIT", "10"))))
INBOX_403_COOLDOWN = max(300, int(os.getenv("INBOX_403_COOLDOWN_SECONDS", "900")))
RECONNECT_BASE = 15
RECONNECT_MAX = 300
ACTION_COOLDOWN = 30
STATE_SAVE_SECONDS = 30
MAX_SEEN = 10000

SESSION_FILE = Path(os.getenv("SESSION_FILE", "instagram_session.json"))
STATE_FILE = Path(os.getenv("STATE_FILE", "bot_state.json"))
RESET_SESSION = os.getenv("RESET_SESSION_ON_START", "0") == "1"

LOG_FILE = os.getenv("LOG_FILE", "bot.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8"), logging.StreamHandler()],
)
log = logging.getLogger("gc-bot")

LINK_MARKERS = ("http://", "https://", "www.", "t.me/", "instagram.com/")
RESTRICTED_WORDS = {
    "18+", "adult", "sex", "xxx", "porn", "nude",
    "gali", "bhadve", "chutiya", "madarchod", "behenchod",
}

seen_messages = deque(maxlen=MAX_SEEN)
seen_set = set()
welcomed = set()
last_action = defaultdict(float)
member_cache = {}


def remember_message(message_id):
    if not message_id:
        return False
    key = str(message_id)
    if key in seen_set:
        return False
    if len(seen_messages) >= MAX_SEEN:
        old = seen_messages.popleft()
        seen_set.discard(old)
    seen_messages.append(key)
    seen_set.add(key)
    return True


def load_state():
    if not STATE_FILE.exists():
        log.info("No previous state found; starting fresh.")
        return
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        for x in data.get("seen_messages", []):
            remember_message(x)
        welcomed.update(data.get("welcomed", []))
        member_cache.update({str(k): set(v) for k, v in data.get("member_cache", {}).items()})
        log.info("State restored | seen=%d | welcomed=%d | groups=%d", len(seen_set), len(welcomed), len(member_cache))
    except Exception as exc:
        log.warning("State restore failed: %s", exc)


def save_state():
    try:
        payload = {
            "seen_messages": list(seen_messages),
            "welcomed": list(welcomed),
            "member_cache": {k: list(v) for k, v in member_cache.items()},
        }
        STATE_FILE.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        log.warning("State save failed: %s", exc)


def is_403(exc):
    text = str(exc).lower()
    return "403" in text or "1404006" in text or getattr(exc, "status_code", None) == 403


def safe_text(message):
    return (getattr(message, "text", None) or "").strip()


def sender_username(message):
    user_id = getattr(message, "user_id", None)
    return str(user_id) if user_id is not None else "unknown"


def is_group(thread):
    return bool(getattr(thread, "is_group", False))


def thread_key(thread):
    return str(getattr(thread, "id", None) or getattr(thread, "pk", "unknown"))


def action_allowed(key):
    now = time.time()
    if now - last_action[key] < ACTION_COOLDOWN:
        return False
    last_action[key] = now
    return True


def send_text(cl, thread_id, text, reason=""):
    try:
        cl.direct_send(text, thread_ids=[int(thread_id)])
        log.info("ACTION SENT | thread=%s | reason=%s", thread_id, reason)
        return True
    except Exception as exc:
        log.warning("ACTION FAILED | thread=%s | reason=%s | %s", thread_id, reason, exc)
        return False


def moderate_message(cl, thread, message):
    text = safe_text(message).lower()
    if not text:
        return

    tid = thread_key(thread)
    mid = getattr(message, "id", None)
    sender = sender_username(message)

    if sender == str(getattr(cl, "user_id", "")):
        return

    if any(marker in text for marker in LINK_MARKERS):
        key = f"link:{tid}:{sender}"
        if action_allowed(key):
            send_text(cl, tid, "⚠️ Links are not allowed in this group.", "link")
        return

    if any(word in text for word in RESTRICTED_WORDS):
        key = f"restricted:{tid}:{sender}"
        if action_allowed(key):
            send_text(cl, tid, "⚠️ Please keep the group chat respectful and appropriate.", "restricted-text")
        return

    bot_name = (BOT_USERNAME or "").lower().lstrip("@")
    if bot_name and (f"@{bot_name}" in text or text.strip() in {"@everyone", "everyone"}):
        key = f"tag:{tid}:{sender}:{mid}"
        if action_allowed(key):
            send_text(cl, tid, "👋 I'm online. Send your message and I'll handle the group rules.", "bot-tag")


def scan_thread(cl, thread):
    if not is_group(thread):
        return 0

    tid = thread_key(thread)
    messages = list(getattr(thread, "messages", []) or [])
    log.info("GC SCAN | thread=%s | messages=%d", tid, len(messages))

    for message in reversed(messages):
        mid = getattr(message, "id", None)
        if not remember_message(mid):
            continue
        moderate_message(cl, thread, message)
    return len(messages)


def login_client():
    version = importlib.metadata.version("instagrapi")
    log.info("instagrapi version=%s", version)

    if not BOT_USERNAME or not BOT_PASSWORD:
        raise RuntimeError("BOT_USERNAME and BOT_PASSWORD must be set in Railway Variables")

    cl = Client()
    cl.delay_range = [1, 3]

    if RESET_SESSION and SESSION_FILE.exists():
        try:
            SESSION_FILE.unlink()
            log.warning("RESET_SESSION_ON_START=1 -> removed saved Instagram session once")
        except Exception as exc:
            log.warning("Could not remove old session: %s", exc)

    if SESSION_FILE.exists():
        try:
            cl.load_settings(SESSION_FILE)
            log.info("Saved Instagram session loaded")
        except Exception as exc:
            log.warning("Saved session load failed; continuing with normal login: %s", exc)

    cl.login(BOT_USERNAME, BOT_PASSWORD)

    try:
        cl.dump_settings(SESSION_FILE)
        log.info("Instagram session settings saved")
    except Exception as exc:
        log.warning("Session save failed: %s", exc)

    log.info("BOT ONLINE | @%s | user_id=%s", BOT_USERNAME, getattr(cl, "user_id", "unknown"))
    return cl


def inbox_poll(cl):
    log.info("INBOX POLL START | amount=%d | message_limit=%d", THREAD_BATCH_SIZE, THREAD_MESSAGE_LIMIT)
    threads = cl.direct_threads(
        amount=THREAD_BATCH_SIZE,
        thread_message_limit=THREAD_MESSAGE_LIMIT,
    )
    groups = [t for t in threads if is_group(t)]
    log.info("INBOX OK | threads=%d | group_threads=%d", len(threads), len(groups))

    total_messages = 0
    for thread in groups:
        total_messages += scan_thread(cl, thread)

    log.info("CYCLE COMPLETE | groups=%d | messages_seen=%d", len(groups), total_messages)
    return len(groups)


def main():
    load_state()
    reconnect_wait = RECONNECT_BASE
    last_save = time.time()
    cl = None

    while True:
        try:
            if cl is None:
                log.info("CONNECTING TO INSTAGRAM...")
                cl = login_client()
                reconnect_wait = RECONNECT_BASE

            groups = inbox_poll(cl)
            if groups == 0:
                log.warning("No group threads returned in this cycle.")

            if time.time() - last_save >= STATE_SAVE_SECONDS:
                save_state()
                last_save = time.time()

            time.sleep(POLL_SECONDS)

        except KeyboardInterrupt:
            save_state()
            log.info("Bot stopped.")
            return

        except Exception as exc:
            if is_403(exc):
                log.error(
                    "INBOX ACCESS 403 / 1404006 | Instagram rejected Direct inbox access. "
                    "Pausing for %ss. No bypass is attempted. Update instagrapi/session and retry later.",
                    INBOX_403_COOLDOWN,
                )
                time.sleep(INBOX_403_COOLDOWN)
                continue

            log.exception("BOT LOOP ERROR")
            cl = None
            save_state()
            log.info("Reconnecting in %ss", reconnect_wait)
            time.sleep(reconnect_wait)
            reconnect_wait = min(RECONNECT_MAX, reconnect_wait * 2)


if __name__ == "__main__":
    main()
