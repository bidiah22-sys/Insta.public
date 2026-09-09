import os
import time
import sqlite3
import hashlib
import threading
from datetime import datetime
from instagrapi import Client


# ============================================================
#                     CONFIGURATION
# ============================================================

SESSION_ID = "67689365007%3ArMwOlX83z4ytk1%3A18%3AAYhKN_qvfDT4KUMtuWF3aPD1Ppz5PmELC3IT4g8TVw"

BOT_USERNAME = "bot222703"
OWNER_USERNAME = "fx_smw"

DB_FILE = "instagram_bot_dedup.db"

POLL_SECONDS = 2
RECONNECT_SECONDS = 10

# Same user + same event type ke liye minimum cooldown
USER_EVENT_COOLDOWN = 15

# Same event ko database mein kitne din rakhein
EVENT_RETENTION_DAYS = 30

# ============================================================
#                     GLOBAL LOCKS
# ============================================================

db_lock = threading.RLock()
send_lock = threading.RLock()


# ============================================================
#                     DATABASE
# ============================================================

def get_db():
    conn = sqlite3.connect(
        DB_FILE,
        timeout=30,
        check_same_thread=False
    )

    conn.execute("""
        PRAGMA journal_mode=WAL
    """)

    conn.execute("""
        PRAGMA busy_timeout=30000
    """)

    return conn


def init_database():
    with db_lock:
        conn = get_db()

        conn.execute("""
            CREATE TABLE IF NOT EXISTS processed_events (
                event_key TEXT PRIMARY KEY,
                thread_id TEXT NOT NULL,
                user_id TEXT,
                event_type TEXT NOT NULL,
                message_id TEXT,
                created_at INTEGER NOT NULL
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_processed_thread
            ON processed_events(thread_id)
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_processed_user_event
            ON processed_events(user_id, event_type, created_at)
        """)

        conn.commit()
        conn.close()


def cleanup_database():
    cutoff = int(time.time()) - (EVENT_RETENTION_DAYS * 86400)

    with db_lock:
        conn = get_db()

        conn.execute(
            "DELETE FROM processed_events WHERE created_at < ?",
            (cutoff,)
        )

        conn.commit()
        conn.close()


# ============================================================
#                 EVENT FINGERPRINT
# ============================================================

def make_event_key(
    thread_id,
    user_id,
    event_type,
    message_id="",
    extra=""
):
    """
    Same event ke liye deterministic unique fingerprint.

    IMPORTANT:
    message_id available ho to usko priority milti hai.
    """

    raw = "|".join([
        str(thread_id),
        str(user_id),
        str(event_type),
        str(message_id),
        str(extra)
    ])

    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ============================================================
#             ATOMIC DUPLICATE CHECK
# ============================================================

def claim_event(
    thread_id,
    user_id,
    event_type,
    message_id="",
    extra=""
):
    """
    Ye function decide karta hai:

    True  -> event FIRST TIME mila, process karo
    False -> event duplicate hai, IGNORE karo

    SQLite PRIMARY KEY + transaction ki wajah se
    same event simultaneously do baar claim nahi hoga.
    """

    event_key = make_event_key(
        thread_id,
        user_id,
        event_type,
        message_id,
        extra
    )

    now = int(time.time())

    with db_lock:
        conn = get_db()

        try:
            conn.execute("BEGIN IMMEDIATE")

            # Exact same event already processed?
            row = conn.execute("""
                SELECT 1
                FROM processed_events
                WHERE event_key = ?
                LIMIT 1
            """, (event_key,)).fetchone()

            if row:
                conn.rollback()
                conn.close()
                return False

            # User + event type cooldown
            cooldown_cutoff = now - USER_EVENT_COOLDOWN

            if user_id:
                row = conn.execute("""
                    SELECT 1
                    FROM processed_events
                    WHERE thread_id = ?
                      AND user_id = ?
                      AND event_type = ?
                      AND created_at >= ?
                    LIMIT 1
                """, (
                    str(thread_id),
                    str(user_id),
                    event_type,
                    cooldown_cutoff
                )).fetchone()

                if row:
                    conn.rollback()
                    conn.close()
                    return False

            # Claim event BEFORE sending
            conn.execute("""
                INSERT INTO processed_events (
                    event_key,
                    thread_id,
                    user_id,
                    event_type,
                    message_id,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                event_key,
                str(thread_id),
                str(user_id),
                event_type,
                str(message_id),
                now
            ))

            conn.commit()
            conn.close()

            return True

        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass

            conn.close()
            return False


# ============================================================
#                       SAFE SEND
# ============================================================

def send_once(
    cl,
    thread_id,
    text,
    event_type,
    user_id="",
    message_id="",
    extra=""
):
    """
    Message send karne se PEHLE event claim hota hai.

    Isliye same event dobara aane par send nahi hoga.
    """

    # First atomic claim
    allowed = claim_event(
        thread_id=thread_id,
        user_id=user_id,
        event_type=event_type,
        message_id=message_id,
        extra=extra
    )

    if not allowed:
        print(
            f"[DEDUP] Ignored duplicate | "
            f"thread={thread_id} "
            f"user={user_id} "
            f"type={event_type}"
        )
        return False

    # Sending ko serialize karo
    with send_lock:
        try:
            cl.direct_send(
                text,
                thread_ids=[thread_id]
            )

            print(
                f"[SEND] {event_type} | "
                f"user={user_id} | "
                f"thread={thread_id}"
            )

            # Small pause to avoid rapid consecutive sends
            time.sleep(1)

            return True

        except Exception as e:
            print(
                f"[SEND ERROR] {event_type}: {e}"
            )

            # Event already claimed hai.
            # Failure par turant automatic duplicate retry nahi karenge.
            return False


# ============================================================
#                 USERNAME HELPER
# ============================================================

def get_username(user_obj):
    try:
        username = getattr(
            user_obj,
            "username",
            None
        )

        if username:
            return str(username).lstrip("@")

    except Exception:
        pass

    return "User"


def find_user(users, user_id):
    target = str(user_id)

    for user in users:
        try:
            if str(getattr(user, "pk", "")) == target:
                return user
        except Exception:
            continue

    return None


# ============================================================
#                    ADMIN HELPERS
# ============================================================

def get_admin_ids(thread):
    admin_ids = set()

    try:
        raw_ids = getattr(
            thread,
            "admin_user_ids",
            None
        )

        if raw_ids:
            admin_ids.update(
                str(x) for x in raw_ids
            )

    except Exception:
        pass

    try:
        admin_users = getattr(
            thread,
            "admin_users",
            None
        )

        if admin_users:
            for admin in admin_users:
                pk = getattr(
                    admin,
                    "pk",
                    None
                )

                if pk:
                    admin_ids.add(str(pk))

    except Exception:
        pass

    return admin_ids


def get_admin_tag(users, admin_ids, bot_id):
    for user in users:
        try:
            pk = str(getattr(user, "pk", ""))

            if (
                pk in admin_ids
                and pk != str(bot_id)
            ):
                username = get_username(user)

                if username != "User":
                    return f"@{username}"

        except Exception:
            continue

    return "@ADMIN"


# ============================================================
#                  WELCOME MESSAGES
# ============================================================

def make_welcome(username):
    return (
        f"🦋✨ 𝗪𝗘𝗟𝗖𝗢𝗠𝗘, @{username}! ✨🦋\n\n"
        f"🌸 𝗛𝗘𝗬! 𝗚𝗟𝗔𝗗 𝗧𝗢 𝗛𝗔𝗩𝗘 𝗬𝗢𝗨 𝗛𝗘𝗥𝗘 💫\n"
        f"🤝 𝗦𝗧𝗔𝗬 𝗥𝗘𝗦𝗣𝗘𝗖𝗧𝗙𝗨𝗟 • 𝗙𝗢𝗟𝗟𝗢𝗪 𝗧𝗛𝗘 𝗥𝗨𝗟𝗘𝗦\n"
        f"🔥 𝗘𝗡𝗝𝗢𝗬 𝗧𝗛𝗘 𝗚𝗖 & 𝗦𝗧𝗔𝗬 𝗔𝗖𝗧𝗜𝗩𝗘!\n\n"
        f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
        f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
    )


def make_welcome_back(username):
    return (
        f"💫🦋 𝗪𝗘𝗟𝗖𝗢𝗠𝗘 𝗕𝗔𝗖𝗞, @{username}! 🦋💫\n\n"
        f"🌷 𝗧𝗛𝗘 𝗚𝗖 𝗙𝗘𝗟𝗧 𝗬𝗢𝗨𝗥 𝗔𝗕𝗦𝗘𝗡𝗖𝗘 😌\n"
        f"🔥 𝗕𝗔𝗖𝗞 𝗔𝗚𝗔𝗜𝗡 • 𝗦𝗧𝗔𝗬 𝗔𝗖𝗧𝗜𝗩𝗘\n"
        f"📜 𝗙𝗢𝗟𝗟𝗢𝗪 𝗧𝗛𝗘 𝗥𝗨𝗟𝗘𝗦 & 𝗘𝗡𝗝𝗢𝗬!\n\n"
        f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
        f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
    )


# ============================================================
#                    MODERATION MESSAGES
# ============================================================

def make_link_warning(username):
    return (
        f"🚨🔗 𝗛𝗘𝗬 @{username} — 𝗟𝗜𝗡𝗞 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗!\n\n"
        f"⚠️ 𝗨𝗡𝗔𝗨𝗧𝗛𝗢𝗥𝗜𝗭𝗘𝗗 𝗟𝗜𝗡𝗞𝗦 𝗔𝗥𝗘 𝗡𝗢𝗧 𝗔𝗟𝗟𝗢𝗪𝗘𝗗 𝗛𝗘𝗥𝗘.\n"
        f"🛑 𝗣𝗟𝗘𝗔𝗦𝗘 𝗥𝗘𝗠𝗢𝗩𝗘 𝗜𝗧 & 𝗗𝗢𝗡'𝗧 𝗥𝗘𝗣𝗘𝗔𝗧!\n\n"
        f"⚡ 𝗥𝗘𝗣𝗘𝗔𝗧 𝗩𝗜𝗢𝗟𝗔𝗧𝗜𝗢𝗡𝗦 𝗠𝗔𝗬 𝗟𝗘𝗔𝗗 𝗧𝗢 𝗥𝗘𝗠𝗢𝗩𝗔𝗟 🚪\n"
        f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
    )


def make_reel_warning(username):
    return (
        f"🚫🎬 𝗥𝗘𝗘𝗟𝗦 𝗡𝗢𝗧 𝗔𝗟𝗟𝗢𝗪𝗘𝗗!\n\n"
        f"👤 @{username}\n\n"
        f"⚠️ 𝗥𝗘𝗘𝗟𝗦 / 𝗩𝗜𝗗𝗘𝗢𝗦 𝗔𝗥𝗘 𝗡𝗢𝗧 𝗔𝗟𝗟𝗢𝗪𝗘𝗗 𝗛𝗘𝗥𝗘.\n\n"
        f"🛑 𝗣𝗟𝗘𝗔𝗦𝗘 𝗗𝗢𝗡'𝗧 𝗥𝗘𝗣𝗘𝗔𝗧!\n\n"
        f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
        f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
    )


def make_moderation_warning(username, admin_tag):
    return (
        f"🚨🛡️ 𝗠𝗢𝗗𝗘𝗥𝗔𝗧𝗜𝗢𝗡 𝗔𝗟𝗘𝗥𝗧!\n\n"
        f"👤 𝗨𝗦𝗘𝗥 ➜ @{username}\n"
        f"🚫 𝗜𝗡𝗔𝗣𝗣𝗥𝗢𝗣𝗥𝗜𝗔𝗧𝗘 𝗖𝗢𝗡𝗧𝗘𝗡𝗧 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗!\n\n"
        f"⚠️ 𝗧𝗛𝗜𝗦 𝗖𝗢𝗡𝗧𝗘𝗡𝗧 𝗜𝗦 𝗡𝗢𝗧 𝗔𝗟𝗟𝗢𝗪𝗘𝗗 𝗜𝗡 𝗧𝗛𝗜𝗦 𝗚𝗖.\n"
        f"👑 𝗔𝗗𝗠𝗜𝗡 ➜ {admin_tag}\n"
        f"🔎 𝗣𝗟𝗘𝗔𝗦𝗘 𝗥𝗘𝗩𝗜𝗘𝗪 & 𝗧𝗔𝗞𝗘 𝗔𝗖𝗧𝗜𝗢𝗡.\n\n"
        f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
        f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
    )


def make_tag_reply(username):
    return (
        f"👋 𝗛𝗘𝗟𝗟𝗢 @{username}!\n\n"
        f"🤖 𝗕𝗢𝗧 𝗜𝗦 𝗔𝗖𝗧𝗜𝗩𝗘 𝗔𝗡𝗗 𝗠𝗔𝗡𝗔𝗚𝗜𝗡𝗚 𝗧𝗛𝗘 𝗚𝗖 𝗦𝗠𝗢𝗢𝗧𝗛𝗟𝗬. 🚀\n\n"
        f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
        f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
    )


# ============================================================
#                   DETECTION HELPERS
# ============================================================

LINK_PATTERNS = (
    "http://",
    "https://",
    "www.",
    ".com",
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


def contains_link(text):
    text_lower = text.lower()

    return any(
        pattern in text_lower
        for pattern in LINK_PATTERNS
    )


def contains_restricted(text):
    text_lower = text.lower()

    return any(
        word in text_lower
        for word in RESTRICTED_WORDS
    )


def is_video_message(item_type, text):
    item = str(item_type or "").lower()
    text_lower = text.lower()

    return (
        item in (
            "clip",
            "media",
            "video",
            "visual_media"
        )
        or "/reel/" in text_lower
        or "video" in item
    )


# ============================================================
#              MEMBER STATE MEMORY
# ============================================================

class MemberState:
    def __init__(self):
        self.groups = {}

        self.lock = threading.RLock()

    def get(self, thread_id):
        with self.lock:
            return set(
                self.groups.get(
                    str(thread_id),
                    set()
                )
            )

    def set(self, thread_id, members):
        with self.lock:
            self.groups[str(thread_id)] = set(members)

    def remove(self, thread_id, user_id):
        with self.lock:
            members = self.groups.get(
                str(thread_id),
                set()
            )

            members.discard(str(user_id))


# ============================================================
#                  PROCESS NEW MEMBERS
# ============================================================

def process_members(
    cl,
    thread,
    users,
    member_state,
    bot_pk,
    first_run
):
    thread_id = str(thread.id)

    current_members = {
        str(getattr(user, "pk", ""))
        for user in users
        if getattr(user, "pk", None)
    }

    old_members = member_state.get(thread_id)

    # First observation:
    # Existing members ko welcome nahi bhejna.
    if not old_members:
        member_state.set(
            thread_id,
            current_members
        )
        return

    newly_joined = current_members - old_members

    if newly_joined and not first_run:
        for joined_pk in newly_joined:

            if joined_pk == str(bot_pk):
                continue

            user_obj = find_user(
                users,
                joined_pk
            )

            if not user_obj:
                continue

            username = get_username(
                user_obj
            )

            # IMPORTANT:
            # Join event ka unique key user + thread + event.
            #
            # Same member list agar polling mein repeat ho,
            # database second welcome ko block karega.

            send_once(
                cl=cl,
                thread_id=thread_id,
                text=make_welcome(username),
                event_type="WELCOME",
                user_id=joined_pk,
                extra="member_join"
            )

    member_state.set(
        thread_id,
        current_members
    )


# ============================================================
#                 PROCESS LAST MESSAGE
# ============================================================

def process_message(
    cl,
    thread,
    users,
    admin_ids,
    bot_pk
):
    messages = list(
        getattr(thread, "messages", []) or []
    )

    if not messages:
        return

    # Most recent message
    last_msg = messages[0]

    message_id = str(
        getattr(last_msg, "id", "")
    )

    if not message_id:
        return

    sender_id = str(
        getattr(last_msg, "user_id", "")
    )

    if not sender_id:
        return

    # Bot ke own message ko ignore
    if sender_id == str(bot_pk):
        return

    user_obj = find_user(
        users,
        sender_id
    )

    username = "User"

    if user_obj:
        username = get_username(
            user_obj
        )

    try:
        msg_user = getattr(
            last_msg,
            "user",
            None
        )

        if msg_user:
            username = get_username(
                msg_user
            )

    except Exception:
        pass

    text = str(
        getattr(last_msg, "text", "") or ""
    ).strip()

    text_lower = text.lower()

    item_type = str(
        getattr(last_msg, "item_type", "") or ""
    ).lower()

    is_admin = sender_id in admin_ids

    # --------------------------------------------------------
    # NON ADMIN MODERATION
    # --------------------------------------------------------

    if not is_admin:

        # ================= LINK =================

        if contains_link(text):

            send_once(
                cl=cl,
                thread_id=str(thread.id),
                text=make_link_warning(username),
                event_type="LINK_WARNING",
                user_id=sender_id,
                message_id=message_id
            )

            return

        # ================= VIDEO / REEL =================

        if is_video_message(
            item_type,
            text
        ):

            send_once(
                cl=cl,
                thread_id=str(thread.id),
                text=make_reel_warning(username),
                event_type="VIDEO_WARNING",
                user_id=sender_id,
                message_id=message_id
            )

            return

        # ================= RESTRICTED =================

        if contains_restricted(text):

            admin_tag = get_admin_tag(
                users,
                admin_ids,
                bot_pk
            )

            send_once(
                cl=cl,
                thread_id=str(thread.id),
                text=make_moderation_warning(
                    username,
                    admin_tag
                ),
                event_type="CONTENT_WARNING",
                user_id=sender_id,
                message_id=message_id
            )

            return

    # --------------------------------------------------------
    # BOT TAG / EVERYONE
    # --------------------------------------------------------

    bot_tag = (
        f"@{BOT_USERNAME.lower()}"
    )

    if (
        "@everyone" in text_lower
        or bot_tag in text_lower
    ):

        send_once(
            cl=cl,
            thread_id=str(thread.id),
            text=make_tag_reply(username),
            event_type="BOT_TAG_REPLY",
            user_id=sender_id,
            message_id=message_id
        )


# ============================================================
#                     MAIN BOT
# ============================================================

def start_bot():

    init_database()

    cleanup_database()

    member_state = MemberState()

    first_run = True

    while True:

        cl = None

        try:
            print(
                "[*] Connecting to Instagram..."
            )

            cl = Client()

            # ------------------------------------------------
            # LOGIN
            # ------------------------------------------------

            cl.login_by_sessionid(
                SESSION_ID
            )

            bot_pk = str(
                cl.user_id
            )

            print(
                f"[+] LOGIN SUCCESS | "
                f"@{BOT_USERNAME}"
            )

            # ------------------------------------------------
            # MAIN LOOP
            # ------------------------------------------------

            while True:

                try:

                    threads = cl.direct_threads(
                        amount=3
                    )

                    if not threads:
                        time.sleep(
                            POLL_SECONDS
                        )
                        continue

                    for thread in threads:

                        try:

                            # --------------------------------
                            # GROUP CHECK
                            # --------------------------------

                            if not getattr(
                                thread,
                                "is_group",
                                False
                            ):
                                continue

                            thread_id = str(
                                thread.id
                            )

                            # --------------------------------
                            # USERS
                            # --------------------------------

                            users = list(
                                getattr(
                                    thread,
                                    "users",
                                    []
                                ) or []
                            )

                            # --------------------------------
                            # ADMINS
                            # --------------------------------

                            admin_ids = (
                                get_admin_ids(
                                    thread
                                )
                            )

                            # --------------------------------
                            # MEMBERS
                            # --------------------------------

                            process_members(
                                cl=cl,
                                thread=thread,
                                users=users,
                                member_state=member_state,
                                bot_pk=bot_pk,
                                first_run=first_run
                            )

                            # --------------------------------
                            # MESSAGE
                            # --------------------------------

                            process_message(
                                cl=cl,
                                thread=thread,
                                users=users,
                                admin_ids=admin_ids,
                                bot_pk=bot_pk
                            )

                        except Exception as thread_error:

                            print(
                                f"[THREAD ERROR] "
                                f"{thread_error}"
                            )

                            continue

                    first_run = False

                    # Periodic cleanup
                    if int(time.time()) % 300 < 3:
                        cleanup_database()

                except Exception as loop_error:

                    print(
                        f"[LOOP ERROR] "
                        f"{loop_error}"
                    )

                time.sleep(
                    POLL_SECONDS
                )

        except Exception as connection_error:

            print(
                f"[-] CONNECTION ERROR: "
                f"{connection_error}"
            )

            print(
                f"[*] Reconnecting in "
                f"{RECONNECT_SECONDS}s..."
            )

            time.sleep(
                RECONNECT_SECONDS
            )


# ============================================================
#                        START
# ============================================================

if __name__ == "__main__":
    start_bot()
