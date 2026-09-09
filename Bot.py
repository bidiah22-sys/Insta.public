import os
import time
import sqlite3
import hashlib
import threading
from instagrapi import Client

# ============================================================
# CONFIG
# ============================================================

SESSION_ID = "67689365007%3ArMwOlX83z4ytk1%3A18%3AAYhKN_qvfDT4KUMtuWF3aPD1Ppz5PmELC3IT4g8TVw"

BOT_USERNAME = "bot222703"
OWNER_USERNAME = "fx_smw"

DB_FILE = "bot_dedup.sqlite3"

POLL_SECONDS = 2
RECONNECT_SECONDS = 10

# Same user + same event type ko itne seconds ke andar repeat
# hone par ignore kiya jayega.
EVENT_COOLDOWN = 20

# Old dedup records ko itne din baad clean kar sakte hain.
RETENTION_DAYS = 30

# ============================================================
# GLOBAL LOCKS
# ============================================================

DB_LOCK = threading.RLock()
SEND_LOCK = threading.RLock()


# ============================================================
# DATABASE
# ============================================================

def db_connect():
    conn = sqlite3.connect(
        DB_FILE,
        timeout=30,
        check_same_thread=False
    )
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def init_db():
    with DB_LOCK:
        conn = db_connect()

        conn.execute("""
            CREATE TABLE IF NOT EXISTS sent_events (
                event_key TEXT PRIMARY KEY,
                thread_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                message_id TEXT,
                created_at INTEGER NOT NULL
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_sent_events_cooldown
            ON sent_events(thread_id, user_id, event_type, created_at)
        """)

        conn.commit()
        conn.close()


def cleanup_db():
    cutoff = int(time.time()) - RETENTION_DAYS * 86400

    with DB_LOCK:
        conn = db_connect()
        conn.execute(
            "DELETE FROM sent_events WHERE created_at < ?",
            (cutoff,)
        )
        conn.commit()
        conn.close()


# ============================================================
# DEDUPLICATION
# ============================================================

def event_fingerprint(
    thread_id,
    user_id,
    event_type,
    message_id="",
    extra=""
):
    raw = "|".join([
        str(thread_id),
        str(user_id),
        str(event_type),
        str(message_id),
        str(extra)
    ])

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


def reserve_event(
    thread_id,
    user_id,
    event_type,
    message_id="",
    extra=""
):
    """
    Returns True only once for a particular event.

    The database reservation happens BEFORE sending.
    This prevents duplicate sends when polling sees the same
    Instagram object more than once.
    """

    thread_id = str(thread_id)
    user_id = str(user_id)
    message_id = str(message_id or "")

    key = event_fingerprint(
        thread_id,
        user_id,
        event_type,
        message_id,
        extra
    )

    now = int(time.time())
    cutoff = now - EVENT_COOLDOWN

    with DB_LOCK:
        conn = db_connect()

        try:
            conn.execute("BEGIN IMMEDIATE")

            # Exact event already reserved?
            exists = conn.execute("""
                SELECT 1
                FROM sent_events
                WHERE event_key = ?
                LIMIT 1
            """, (key,)).fetchone()

            if exists:
                conn.rollback()
                conn.close()
                return False

            # Same user + same event type recently handled?
            recent = conn.execute("""
                SELECT 1
                FROM sent_events
                WHERE thread_id = ?
                  AND user_id = ?
                  AND event_type = ?
                  AND created_at >= ?
                LIMIT 1
            """, (
                thread_id,
                user_id,
                event_type,
                cutoff
            )).fetchone()

            if recent:
                conn.rollback()
                conn.close()
                return False

            conn.execute("""
                INSERT INTO sent_events (
                    event_key,
                    thread_id,
                    user_id,
                    event_type,
                    message_id,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                key,
                thread_id,
                user_id,
                event_type,
                message_id,
                now
            ))

            conn.commit()
            conn.close()
            return True

        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass

            conn.close()

            print("[DEDUP ERROR]", e)
            return False


def send_deduplicated(
    cl,
    thread_id,
    user_id,
    event_type,
    text,
    message_id="",
    extra=""
):
    """
    One event -> maximum one outgoing response.

    If the event was already reserved, nothing is sent.
    """

    allowed = reserve_event(
        thread_id=thread_id,
        user_id=user_id,
        event_type=event_type,
        message_id=message_id,
        extra=extra
    )

    if not allowed:
        print(
            f"[DUPLICATE BLOCKED] "
            f"type={event_type} "
            f"user={user_id} "
            f"thread={thread_id}"
        )
        return False

    with SEND_LOCK:
        try:
            cl.direct_send(
                text,
                thread_ids=[thread_id]
            )

            print(
                f"[SENT] "
                f"type={event_type} "
                f"user={user_id} "
                f"thread={thread_id}"
            )

            time.sleep(1)
            return True

        except Exception as e:
            print(
                f"[SEND ERROR] "
                f"type={event_type}: {e}"
            )
            return False


# ============================================================
# HELPERS
# ============================================================

def username_of(user):
    try:
        username = getattr(user, "username", None)
        if username:
            return str(username).lstrip("@")
    except Exception:
        pass

    return "User"


def find_user(users, user_id):
    user_id = str(user_id)

    for user in users:
        try:
            if str(getattr(user, "pk", "")) == user_id:
                return user
        except Exception:
            pass

    return None


def get_admin_ids(thread):
    result = set()

    try:
        ids = getattr(thread, "admin_user_ids", None)
        if ids:
            result.update(str(x) for x in ids)
    except Exception:
        pass

    try:
        admins = getattr(thread, "admin_users", None)
        if admins:
            for admin in admins:
                pk = getattr(admin, "pk", None)
                if pk:
                    result.add(str(pk))
    except Exception:
        pass

    return result


def admin_tag(users, admin_ids, bot_id):
    for user in users:
        try:
            uid = str(getattr(user, "pk", ""))

            if uid in admin_ids and uid != str(bot_id):
                name = username_of(user)
                if name != "User":
                    return f"@{name}"
        except Exception:
            pass

    return "@ADMIN"


# ============================================================
# DETECTION
# ============================================================

LINK_PATTERNS = (
    "http://",
    "https://",
    "www.",
    "t.me",
    "instagram.com/"
)

RESTRICTED_WORDS = (
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
    "behenchod"
)


def has_link(text):
    text = text.lower()
    return any(x in text for x in LINK_PATTERNS)


def has_restricted_word(text):
    text = text.lower()
    return any(x in text for x in RESTRICTED_WORDS)


def is_video(item_type, text):
    item_type = str(item_type or "").lower()
    text = text.lower()

    return (
        item_type in {
            "clip",
            "media",
            "video",
            "visual_media"
        }
        or "/reel/" in text
        or "video" in item_type
    )


# ============================================================
# TEXT CARDS
# ============================================================

def welcome_card(username):
    return (
        f"🦋✨ 𝗪𝗘𝗟𝗖𝗢𝗠𝗘, @{username}! ✨🦋\n\n"
        f"🌸 𝗛𝗘𝗬! 𝗚𝗟𝗔𝗗 𝗧𝗢 𝗛𝗔𝗩𝗘 𝗬𝗢𝗨 𝗛𝗘𝗥𝗘 💫\n"
        f"🤝 𝗦𝗧𝗔𝗬 𝗥𝗘𝗦𝗣𝗘𝗖𝗧𝗙𝗨𝗟 • 𝗙𝗢𝗟𝗟𝗢𝗪 𝗧𝗛𝗘 𝗥𝗨𝗟𝗘𝗦\n"
        f"🔥 𝗘𝗡𝗝𝗢𝗬 𝗧𝗛𝗘 𝗚𝗖 & 𝗦𝗧𝗔𝗬 𝗔𝗖𝗧𝗜𝗩𝗘!\n\n"
        f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
        f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
    )


def welcome_back_card(username):
    return (
        f"💫🦋 𝗪𝗘𝗟𝗖𝗢𝗠𝗘 𝗕𝗔𝗖𝗞, @{username}! 🦋💫\n\n"
        f"🌷 𝗧𝗛𝗘 𝗚𝗖 𝗙𝗘𝗟𝗧 𝗬𝗢𝗨𝗥 𝗔𝗕𝗦𝗘𝗡𝗖𝗘 😌\n"
        f"🔥 𝗕𝗔𝗖𝗞 𝗔𝗚𝗔𝗜𝗡 • 𝗦𝗧𝗔𝗬 𝗔𝗖𝗧𝗜𝗩𝗘\n"
        f"📜 𝗙𝗢𝗟𝗟𝗢𝗪 𝗧𝗛𝗘 𝗥𝗨𝗟𝗘𝗦 & 𝗘𝗡𝗝𝗢𝗬!\n\n"
        f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
        f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
    )


def link_card(username):
    return (
        f"🚨🔗 𝗛𝗘𝗬 @{username} — 𝗟𝗜𝗡𝗞 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗!\n\n"
        f"⚠️ 𝗨𝗡𝗔𝗨𝗧𝗛𝗢𝗥𝗜𝗭𝗘𝗗 𝗟𝗜𝗡𝗞𝗦 𝗔𝗥𝗘 𝗡𝗢𝗧 𝗔𝗟𝗟𝗢𝗪𝗘𝗗 𝗛𝗘𝗥𝗘.\n"
        f"🛑 𝗣𝗟𝗘𝗔𝗦𝗘 𝗥𝗘𝗠𝗢𝗩𝗘 𝗜𝗧 & 𝗗𝗢𝗡'𝗧 𝗥𝗘𝗣𝗘𝗔𝗧!\n\n"
        f"⚡ 𝗥𝗘𝗣𝗘𝗔𝗧 𝗩𝗜𝗢𝗟𝗔𝗧𝗜𝗢𝗡𝗦 𝗠𝗔𝗬 𝗟𝗘𝗔𝗗 𝗧𝗢 𝗥𝗘𝗠𝗢𝗩𝗔𝗟 🚪\n"
        f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
    )


def video_card(username):
    return (
        f"🚫🎬 𝗥𝗘𝗘𝗟𝗦 𝗡𝗢𝗧 𝗔𝗟𝗟𝗢𝗪𝗘𝗗!\n\n"
        f"👤 @{username}\n\n"
        f"⚠️ 𝗥𝗘𝗘𝗟𝗦 / 𝗩𝗜𝗗𝗘𝗢𝗦 𝗔𝗥𝗘 𝗡𝗢𝗧 𝗔𝗟𝗟𝗢𝗪𝗘𝗗 𝗛𝗘𝗥𝗘.\n\n"
        f"🛑 𝗣𝗟𝗘𝗔𝗦𝗘 𝗗𝗢𝗡'𝗧 𝗥𝗘𝗣𝗘𝗔𝗧!\n\n"
        f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
        f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
    )


def moderation_card(username, admin):
    return (
        f"🚨🛡️ 𝗠𝗢𝗗𝗘𝗥𝗔𝗧𝗜𝗢𝗡 𝗔𝗟𝗘𝗥𝗧!\n\n"
        f"👤 𝗨𝗦𝗘𝗥 ➜ @{username}\n"
        f"🚫 𝗜𝗡𝗔𝗣𝗣𝗥𝗢𝗣𝗥𝗜𝗔𝗧𝗘 𝗖𝗢𝗡𝗧𝗘𝗡𝗧 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗!\n\n"
        f"⚠️ 𝗧𝗛𝗜𝗦 𝗖𝗢𝗡𝗧𝗘𝗡𝗧 𝗜𝗦 𝗡𝗢𝗧 𝗔𝗟𝗟𝗢𝗪𝗘𝗗 𝗜𝗡 𝗧𝗛𝗜𝗦 𝗚𝗖.\n"
        f"👑 𝗔𝗗𝗠𝗜𝗡 ➜ {admin}\n"
        f"🔎 𝗣𝗟𝗘𝗔𝗦𝗘 𝗥𝗘𝗩𝗜𝗘𝗪 & 𝗧𝗔𝗞𝗘 𝗔𝗖𝗧𝗜𝗢𝗡.\n\n"
        f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
        f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
    )


def tag_card(username):
    return (
        f"👋 𝗛𝗘𝗟𝗟𝗢 @{username}!\n\n"
        f"🤖 𝗕𝗢𝗧 𝗜𝗦 𝗔𝗖𝗧𝗜𝗩𝗘 𝗔𝗡𝗗 𝗠𝗔𝗡𝗔𝗚𝗜𝗡𝗚 𝗧𝗛𝗘 𝗚𝗖 𝗦𝗠𝗢𝗢𝗧𝗛𝗟𝗬. 🚀\n\n"
        f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
        f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
    )


# ============================================================
# MEMBER TRACKING
# ============================================================

class MemberTracker:
    def __init__(self):
        self.groups = {}
        self.ever_seen = {}
        self.lock = threading.RLock()

    def first_snapshot(self, thread_id, current):
        tid = str(thread_id)

        with self.lock:
            if tid not in self.groups:
                self.groups[tid] = set(current)
                self.ever_seen.setdefault(tid, set()).update(current)
                return True

        return False

    def update(self, thread_id, current):
        tid = str(thread_id)

        with self.lock:
            old = self.groups.get(tid, set())
            current = set(current)

            joined = current - old
            left = old - current

            self.groups[tid] = current
            self.ever_seen.setdefault(tid, set()).update(current)

            return joined, left

    def was_seen(self, thread_id, user_id):
        tid = str(thread_id)

        with self.lock:
            return str(user_id) in self.ever_seen.get(
                tid,
                set()
            )


# ============================================================
# MEMBER PROCESSING
# ============================================================

def process_members(
    cl,
    thread,
    users,
    tracker,
    bot_id
):
    thread_id = str(thread.id)

    current = {
        str(getattr(user, "pk", ""))
        for user in users
        if getattr(user, "pk", None)
    }

    # First observation = snapshot only.
    # Existing users ko welcome nahi.
    if tracker.first_snapshot(
        thread_id,
        current
    ):
        return

    joined, _ = tracker.update(
        thread_id,
        current
    )

    for user_id in joined:

        if user_id == str(bot_id):
            continue

        user = find_user(
            users,
            user_id
        )

        if not user:
            continue

        username = username_of(user)

        # Database deduplication final protection hai.
        # Repeated polling / repeated member list ke bawajood
        # same join event par second send nahi hoga.

        was_before = tracker.was_seen(
            thread_id,
            user_id
        )

        if was_before:
            text = welcome_back_card(username)
            event_type = "WELCOME_BACK"
        else:
            text = welcome_card(username)
            event_type = "WELCOME"

        send_deduplicated(
            cl=cl,
            thread_id=thread_id,
            user_id=user_id,
            event_type=event_type,
            text=text,
            extra="member_event"
        )


# ============================================================
# MESSAGE PROCESSING
# ============================================================

def process_latest_message(
    cl,
    thread,
    users,
    admin_ids,
    bot_id
):
    messages = list(
        getattr(thread, "messages", []) or []
    )

    if not messages:
        return

    msg = messages[0]

    message_id = str(
        getattr(msg, "id", "")
    )

    if not message_id:
        return

    sender_id = str(
        getattr(msg, "user_id", "")
    )

    if not sender_id:
        return

    # Never answer itself
    if sender_id == str(bot_id):
        return

    user = find_user(
        users,
        sender_id
    )

    username = (
        username_of(user)
        if user
        else "User"
    )

    try:
        msg_user = getattr(
            msg,
            "user",
            None
        )

        if msg_user:
            username = username_of(
                msg_user
            )
    except Exception:
        pass

    text = str(
        getattr(msg, "text", "") or ""
    ).strip()

    text_lower = text.lower()

    item_type = str(
        getattr(msg, "item_type", "") or ""
    ).lower()

    is_admin = (
        sender_id in admin_ids
    )

    # --------------------------------------------------------
    # MODERATION
    # --------------------------------------------------------

    if not is_admin:

        if has_link(text):

            send_deduplicated(
                cl=cl,
                thread_id=str(thread.id),
                user_id=sender_id,
                event_type="LINK_WARNING",
                text=link_card(username),
                message_id=message_id
            )

            return

        if is_video(
            item_type,
            text
        ):

            send_deduplicated(
                cl=cl,
                thread_id=str(thread.id),
                user_id=sender_id,
                event_type="VIDEO_WARNING",
                text=video_card(username),
                message_id=message_id
            )

            return

        if has_restricted_word(text):

            admin = admin_tag(
                users,
                admin_ids,
                bot_id
            )

            send_deduplicated(
                cl=cl,
                thread_id=str(thread.id),
                user_id=sender_id,
                event_type="CONTENT_WARNING",
                text=moderation_card(
                    username,
                    admin
                ),
                message_id=message_id
            )

            return

    # --------------------------------------------------------
    # BOT TAG
    # --------------------------------------------------------

    bot_tag = f"@{BOT_USERNAME.lower()}"

    if (
        "@everyone" in text_lower
        or bot_tag in text_lower
    ):

        send_deduplicated(
            cl=cl,
            thread_id=str(thread.id),
            user_id=sender_id,
            event_type="BOT_TAG_REPLY",
            text=tag_card(username),
            message_id=message_id
        )


# ============================================================
# MAIN
# ============================================================

def start_bot():

    init_db()

    tracker = MemberTracker()

    while True:

        try:
            print(
                "[*] Connecting to Instagram..."
            )

            cl = Client()

            cl.login_by_sessionid(
                SESSION_ID
            )

            bot_id = str(
                cl.user_id
            )

            print(
                f"[+] Logged in as @{BOT_USERNAME}"
            )

            first_cycle = True

            while True:

                try:

                    threads = cl.direct_threads(
                        amount=3
                    )

                    for thread in threads:

                        try:

                            if not getattr(
                                thread,
                                "is_group",
                                False
                            ):
                                continue

                            thread_id = str(
                                thread.id
                            )

                            users = list(
                                getattr(
                                    thread,
                                    "users",
                                    []
                                ) or []
                            )

                            admin_ids = (
                                get_admin_ids(
                                    thread
                                )
                            )

                            # Member handling
                            #
                            # First cycle only creates a snapshot.
                            # Isliye bot start hote hi existing members
                            # ko welcome nahi bhejega.

                            process_members(
                                cl=cl,
                                thread=thread,
                                users=users,
                                tracker=tracker,
                                bot_id=bot_id
                            )

                            # Message handling
                            process_latest_message(
                                cl=cl,
                                thread=thread,
                                users=users,
                                admin_ids=admin_ids,
                                bot_id=bot_id
                            )

                        except Exception as thread_error:

                            print(
                                "[THREAD ERROR]",
                                thread_error
                            )

                            continue

                    first_cycle = False

                    # Periodic database cleanup
                    if int(time.time()) % 300 < 2:
                        cleanup_db()

                except Exception as loop_error:

                    print(
                        "[LOOP ERROR]",
                        loop_error
                    )

                time.sleep(
                    POLL_SECONDS
                )

        except Exception as connection_error:

            print(
                "[CONNECTION ERROR]",
                connection_error
            )

            print(
                f"[*] Reconnecting after "
                f"{RECONNECT_SECONDS} seconds..."
            )

            time.sleep(
                RECONNECT_SECONDS
            )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    start_bot()

