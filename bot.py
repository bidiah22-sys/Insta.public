import os
import re
import json
import time
import threading
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from instagrapi import Client


# ============================================================
# CONFIG
# ============================================================

BOT_USERNAME = os.getenv("BOT_USERNAME", "bot222703").lstrip("@").strip()
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "fx_smw").lstrip("@").strip()

# IMPORTANT:
# Put your Instagram session ID in the environment variable:
# IG_SESSION_ID
SESSION_ID = os.getenv("IG_SESSION_ID", "").strip()

STATE_FILE = Path(
    os.getenv("BOT_STATE_FILE", "gc_bot_state.json")
)

TIMEZONE = ZoneInfo("Asia/Kolkata")

# Large inbox scanning
THREAD_BATCH_SIZE = int(
    os.getenv("THREAD_BATCH_SIZE", "300")
)

MESSAGES_PER_THREAD = int(
    os.getenv("MESSAGES_PER_THREAD", "10")
)

# Poll interval
POLL_SECONDS = float(
    os.getenv("POLL_SECONDS", "6")
)

RECONNECT_SECONDS = int(
    os.getenv("RECONNECT_SECONDS", "15")
)


# ============================================================
# MESSAGE TEMPLATES
# ============================================================

WELCOME = (
    "🌸✨ 𝗪𝗘𝗟𝗖𝗢𝗠𝗘 𝗧𝗢 𝗚𝗖 ✨🌸\n\n"
    "👋 𝗛𝗘𝗬 {mention}, 𝗪𝗘𝗟𝗖𝗢𝗠𝗘! 💗\n\n"
    "🔥 𝗚𝗟𝗔𝗗 𝗧𝗢 𝗛𝗔𝗩𝗘 𝗬𝗢𝗨 𝗛𝗘𝗥𝗘!\n"
    "🤝 𝗝𝗢𝗜𝗡 𝗧𝗛𝗘 𝗩𝗜𝗕𝗘 • 𝗠𝗘𝗘𝗧 𝗡𝗘𝗪 𝗣𝗘𝗢𝗣𝗟𝗘 • 𝗘𝗡𝗝𝗢𝗬 ✨\n\n"
    "⚠️ 𝗥𝗘𝗦𝗣𝗘𝗖𝗧 𝗧𝗛𝗘 𝗚𝗖 • 𝗦𝗧𝗔𝗬 𝗔𝗖𝗧𝗜𝗩𝗘 • 𝗞𝗘𝗘𝗣 𝗧𝗛𝗘 𝗩𝗜𝗕𝗘 𝗚𝗢𝗜𝗡𝗚! ❤️‍🔥\n\n"
    "🌸 𝗛𝗔𝗩𝗘 𝗙𝗨𝗡 & 𝗘𝗡𝗝𝗢𝗬 𝗧𝗛𝗘 𝗚𝗖! 💫\n\n"
    "👑 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ @{owner}\n"
    "🤖 𝗕𝗢𝗧 ➜ @{bot}"
)

MORNING = (
    "🌸✨ 𝗚𝗢𝗢𝗗 𝗠𝗢𝗥𝗡𝗜𝗡𝗚, 𝗚𝗖! ✨🌸\n\n"
    "👋 𝗛𝗘𝗬 𝗘𝗩𝗘𝗥𝗬𝗢𝗡𝗘, 𝗥𝗜𝗦𝗘 & 𝗦𝗛𝗜𝗡𝗘! ☀️💗\n\n"
    "🚩 𝗝𝗔𝗜 𝗦𝗛𝗥𝗘𝗘 𝗥𝗔𝗠 🙏\n"
    "✨ 𝗡𝗘𝗪 𝗗𝗔𝗬 • 𝗡𝗘𝗪 𝗘𝗡𝗘𝗥𝗚𝗬 • 𝗡𝗘𝗪 𝗩𝗜𝗕𝗘!\n\n"
    "🔥 𝗦𝗧𝗔𝗬 𝗣𝗢𝗦𝗜𝗧𝗜𝗩𝗘 & 𝗠𝗔𝗞𝗘 𝗜𝗧 𝗖𝗢𝗨𝗡𝗧! 💫\n\n"
    "👑 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ @{owner}\n"
    "🤖 𝗕𝗢𝗧 ➜ @{bot}"
)

AFTERNOON = (
    "☀️✨ 𝗚𝗢𝗢𝗗 𝗔𝗙𝗧𝗘𝗥𝗡𝗢𝗢𝗡, 𝗚𝗖! ✨☀️\n\n"
    "🌸 𝗛𝗘𝗬 𝗘𝗩𝗘𝗥𝗬𝗢𝗡𝗘, 𝗛𝗢𝗪'𝗦 𝗧𝗛𝗘 𝗗𝗔𝗬 𝗚𝗢𝗜𝗡𝗚? 💗\n\n"
    "🙏 𝗥𝗔𝗗𝗛𝗘 𝗥𝗔𝗗𝗛𝗘!\n"
    "✨ 𝗞𝗘𝗘𝗣 𝗧𝗛𝗘 𝗘𝗡𝗘𝗥𝗚𝗬 𝗛𝗜𝗚𝗛 & 𝗧𝗛𝗘 𝗩𝗜𝗕𝗘 𝗔𝗟𝗜𝗩𝗘! 🔥\n\n"
    "💫 𝗘𝗡𝗝𝗢𝗬 𝗧𝗛𝗘 𝗥𝗘𝗦𝗧 𝗢𝗙 𝗬𝗢𝗨𝗥 𝗗𝗔𝗬!\n\n"
    "👑 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ @{owner}\n"
    "🤖 𝗕𝗢𝗧 ➜ @{bot}"
)

EVENING = (
    "🌆✨ 𝗚𝗢𝗢𝗗 𝗘𝗩𝗘𝗡𝗜𝗡𝗚, 𝗚𝗖! ✨🌆\n\n"
    "👋 𝗛𝗘𝗬 𝗘𝗩𝗘𝗥𝗬𝗢𝗡𝗘! 💗\n"
    "🌸 𝗧𝗜𝗠𝗘 𝗧𝗢 𝗨𝗡𝗪𝗜𝗡𝗗 & 𝗘𝗡𝗝𝗢𝗬 𝗧𝗛𝗘 𝗩𝗜𝗕𝗘! ✨\n\n"
    "🙏 𝗥𝗔𝗗𝗛𝗘 𝗥𝗔𝗗𝗛𝗘!\n"
    "🔥 𝗞𝗘𝗘𝗣 𝗧𝗛𝗘 𝗚𝗖 𝗟𝗜𝗩𝗘 • 𝗞𝗘𝗘𝗣 𝗧𝗛𝗘 𝗩𝗜𝗕𝗘 𝗚𝗢𝗜𝗡𝗚! ❤️‍🔥\n\n"
    "💫 𝗛𝗔𝗩𝗘 𝗔 𝗚𝗥𝗘𝗔𝗧 𝗘𝗩𝗘𝗡𝗜𝗡𝗚!\n\n"
    "👑 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ @{owner}\n"
    "🤖 𝗕𝗢𝗧 ➜ @{bot}"
)

NIGHT = (
    "🌙✨ 𝗚𝗢𝗢𝗗 𝗡𝗜𝗚𝗛𝗧, 𝗚𝗖! ✨🌙\n\n"
    "💗 𝗛𝗘𝗬 𝗘𝗩𝗘𝗥𝗬𝗢𝗡𝗘, 𝗧𝗜𝗠𝗘 𝗧𝗢 𝗥𝗘𝗦𝗧!\n\n"
    "🚩 𝗝𝗔𝗜 𝗦𝗛𝗥𝗘𝗘 𝗥𝗔𝗠 🙏\n"
    "✨ 𝗧𝗛𝗔𝗡𝗞𝗦 𝗙𝗢𝗥 𝗔𝗡𝗢𝗧𝗛𝗘𝗥 𝗚𝗥𝗘𝗔𝗧 𝗗𝗔𝗬!\n\n"
    "🌸 𝗥𝗘𝗦𝗧 𝗪𝗘𝗟𝗟 • 𝗦𝗧𝗔𝗬 𝗕𝗟𝗘𝗦𝗦𝗘𝗗 • 𝗦𝗘𝗘 𝗬𝗢𝗨 𝗧𝗢𝗠𝗢𝗥𝗥𝗢𝗪! 💫\n\n"
    "👑 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ @{owner}\n"
    "🤖 𝗕𝗢𝗧 ➜ @{bot}"
)


# ============================================================
# DETECTION
# ============================================================

URL_RE = re.compile(
    r"(?:"
    r"https?://"
    r"|www\."
    r"|t\.me/"
    r"|instagram\.com/"
    r"|youtu\.be/"
    r"|youtube\.com/"
    r"|discord\.gg/"
    r")",
    re.I
)

DOMAIN_RE = re.compile(
    r"\b[a-z0-9-]+\.(?:com|net|org|co|in|io|me|gg|ly|xyz|info|site|online)\b",
    re.I
)

RESTRICTED_RE = re.compile(
    r"\b(?:18\+|nsfw|adult\s*content|explicit\s*content)\b",
    re.I
)


def render(text):
    return (
        text
        .replace("{owner}", OWNER_USERNAME)
        .replace("{bot}", BOT_USERNAME)
    )


# ============================================================
# USER HELPERS
# ============================================================

def user_pk(user):
    return str(
        getattr(
            user,
            "pk",
            getattr(user, "id", "")
        )
    )


def clean_username(value):
    value = str(value or "").strip().lstrip("@").strip()

    if not value:
        return "unknown_user"

    if value.lower() == "none":
        return "unknown_user"

    return value


def get_sender_username(cl, message, user_cache):

    sender_id = str(
        getattr(message, "user_id", "")
    )

    # First: message's own user object
    user = getattr(message, "user", None)

    username = clean_username(
        getattr(user, "username", "")
    )

    if username != "unknown_user":
        user_cache[sender_id] = username
        return username

    # Second: local cache
    if sender_id in user_cache:
        return user_cache[sender_id]

    # Third: Instagram lookup
    try:
        if sender_id:
            info = cl.user_info(int(sender_id))

            username = clean_username(
                getattr(info, "username", "")
            )

            if username != "unknown_user":
                user_cache[sender_id] = username
                return username

    except Exception as exc:
        print(
            f"[USER LOOKUP ERROR] "
            f"{sender_id}: {exc}"
        )

    return "unknown_user"


# ============================================================
# ADMIN SYSTEM
# ============================================================

def get_admin_ids(thread):

    ids = set()

    try:
        raw = getattr(
            thread,
            "admin_user_ids",
            None
        ) or []

        ids.update(
            str(x)
            for x in raw
        )

    except Exception:
        pass

    # Fallback
    if not ids:

        try:
            admins = getattr(
                thread,
                "admin_users",
                None
            ) or []

            for admin in admins:

                pk = getattr(
                    admin,
                    "pk",
                    getattr(
                        admin,
                        "id",
                        admin
                    )
                )

                ids.add(str(pk))

        except Exception:
            pass

    return ids


def get_admin_names(thread, bot_pk):

    admin_ids = get_admin_ids(thread)

    names = []

    for user in getattr(
        thread,
        "users",
        []
    ) or []:

        pk = user_pk(user)

        if (
            pk in admin_ids
            and pk != str(bot_pk)
        ):

            username = clean_username(
                getattr(
                    user,
                    "username",
                    ""
                )
            )

            if username != "unknown_user":
                names.append(username)

    # Remove duplicates
    return list(
        dict.fromkeys(names)
    )


def bot_is_admin(thread, bot_pk):

    admin_ids = get_admin_ids(thread)

    # HARD ADMIN GATE:
    # If admin status is unknown, bot does nothing.
    if not admin_ids:
        return False

    return str(bot_pk) in admin_ids


# ============================================================
# MEDIA / LINK DETECTION
# ============================================================

def extract_xma_url(message):

    xma = getattr(
        message,
        "xma_share",
        None
    )

    if xma:

        target = getattr(
            xma,
            "target_url",
            None
        )

        if target:
            return str(target)

    raw = getattr(
        message,
        "raw_xma",
        None
    )

    if raw:

        try:

            blob = json.dumps(
                raw,
                ensure_ascii=False
            )

            match = re.search(
                r'"target_url"\s*:\s*"([^"]+)"',
                blob
            )

            if match:
                return match.group(1)

        except Exception:
            pass

    return ""


def has_link(message, text):

    if URL_RE.search(text):
        return True

    if DOMAIN_RE.search(text):
        return True

    if extract_xma_url(message):
        return True

    return False


def is_reel_or_video(message, text):

    item_type = str(
        getattr(
            message,
            "item_type",
            ""
        ) or ""
    ).lower()

    # Different Instagram DM payloads
    for attr in (
        "reel_share",
        "clip",
        "media_share",
        "felix_share"
    ):

        if getattr(
            message,
            attr,
            None
        ) is not None:

            return True

    lower_text = text.lower()

    if "/reel/" in lower_text:
        return True

    if "/reels/" in lower_text:
        return True

    if any(
        value in item_type
        for value in (
            "clip",
            "video",
            "media_share",
            "felix"
        )
    ):
        return True

    return False


def is_restricted(text):

    return bool(
        RESTRICTED_RE.search(text)
    )


# ============================================================
# PERSISTENT STATE
# ============================================================

state_lock = threading.RLock()

state = {

    # thread_id:user_id
    "welcomed": {},

    # thread_id:message_id
    "processed": {},

    # thread_id:date:hour
    "scheduled": {},

    # thread_id -> member ids
    "members": {},
}


def load_state():

    global state

    with state_lock:

        try:

            if not STATE_FILE.exists():
                return

            loaded = json.loads(
                STATE_FILE.read_text(
                    encoding="utf-8"
                )
            )

            if not isinstance(
                loaded,
                dict
            ):
                return

            for key in state:

                if isinstance(
                    loaded.get(key),
                    dict
                ):

                    state[key] = loaded[key]

            print(
                "[STATE] Loaded successfully."
            )

        except Exception as exc:

            print(
                f"[STATE LOAD ERROR] {exc}"
            )


def save_state():

    with state_lock:

        tmp = STATE_FILE.with_suffix(
            ".tmp"
        )

        try:

            STATE_FILE.parent.mkdir(
                parents=True,
                exist_ok=True
            )

            tmp.write_text(
                json.dumps(
                    state,
                    ensure_ascii=False,
                    separators=(",", ":")
                ),
                encoding="utf-8"
            )

            tmp.replace(
                STATE_FILE
            )

        except Exception as exc:

            print(
                f"[STATE SAVE ERROR] {exc}"
            )


def reserve_once(
    bucket,
    key,
    value="reserved"
):

    with state_lock:

        mapping = state[bucket]

        if key in mapping:
            return False

        # Reserve BEFORE sending.
        mapping[key] = value

        save_state()

        return True


def trim_state():

    with state_lock:

        limits = {
            "processed": 12000,
            "scheduled": 5000,
            "welcomed": 10000,
        }

        for bucket, limit in limits.items():

            mapping = state[bucket]

            if len(mapping) > limit:

                items = list(
                    mapping.items()
                )[-limit:]

                state[bucket] = dict(
                    items
                )

        if len(state["members"]) > 500:

            items = list(
                state["members"].items()
            )[-500:]

            state["members"] = dict(
                items
            )


# ============================================================
# ONE-SEND ENGINE
# ============================================================

def send_once(
    cl,
    thread_id,
    text,
    event_key,
    reply_to=None
):

    # If this event was already handled,
    # NEVER send again.
    if not reserve_once(
        "processed",
        event_key
    ):
        return False

    try:

        kwargs = {
            "thread_ids": [
                thread_id
            ]
        }

        # User-targeted action:
        # reply directly to the user's message.
        if reply_to is not None:

            kwargs[
                "reply_to_message"
            ] = reply_to

        # EXACTLY ONE send attempt.
        #
        # IMPORTANT:
        # There is deliberately NO fallback
        # send here. A fallback can create
        # duplicate messages when Instagram
        # accepted the first request but the
        # response was lost.
        cl.direct_send(
            text,
            **kwargs
        )

        with state_lock:

            state[
                "processed"
            ][event_key] = "sent"

            save_state()

        print(
            f"[SENT] {event_key}"
        )

        return True

    except Exception as exc:

        with state_lock:

            state[
                "processed"
            ][event_key] = (
                "send_error_no_retry"
            )

            save_state()

        print(
            f"[SEND ERROR] "
            f"{event_key}: {exc}"
        )

        return False


# ============================================================
# DAILY SCHEDULE
# ============================================================

SCHEDULES = {

    6: MORNING,

    12: AFTERNOON,

    19: EVENING,

    23: NIGHT,
}


def send_scheduled_message(
    cl,
    thread
):

    now = datetime.now(
        TIMEZONE
    )

    template = SCHEDULES.get(
        now.hour
    )

    # Only within first 2 minutes
    # of the scheduled hour.
    if (
        template is None
        or now.minute >= 2
    ):
        return

    thread_id = str(
        getattr(
            thread,
            "id",
            ""
        )
    )

    key = (
        f"{thread_id}:"
        f"{now:%Y-%m-%d}:"
        f"{now.hour:02d}"
    )

    if not reserve_once(
        "scheduled",
        key
    ):
        return

    try:

        cl.direct_send(
            render(template),
            thread_ids=[
                thread.id
            ]
        )

        with state_lock:

            state[
                "scheduled"
            ][key] = "sent"

            save_state()

        print(
            f"[SCHEDULED] "
            f"{thread_id} "
            f"{now.hour}:00"
        )

    except Exception as exc:

        # No automatic resend.
        with state_lock:

            state[
                "scheduled"
            ][key] = (
                "send_error_no_retry"
            )

            save_state()

        print(
            f"[SCHEDULE ERROR] "
            f"{thread_id}: {exc}"
        )


# ============================================================
# WELCOME SYSTEM
# ============================================================

def handle_new_members(
    cl,
    thread,
    current_members,
    previous_members,
    initialized,
    user_cache
):

    if not initialized:
        return

    newly_joined = (
        current_members
        - previous_members
    )

    if not newly_joined:
        return

    for user_id in newly_joined:

        welcome_key = (
            f"{thread.id}:{user_id}"
        )

        # Only FIRST EVER welcome.
        if not reserve_once(
            "welcomed",
            welcome_key
        ):
            continue

        username = user_cache.get(
            user_id,
            "unknown_user"
        )

        welcome_text = (
            WELCOME
            .replace(
                "{mention}",
                f"@{username}"
            )
            .replace(
                "{owner}",
                OWNER_USERNAME
            )
            .replace(
                "{bot}",
                BOT_USERNAME
            )
        )

        try:

            # One welcome only.
            cl.direct_send(
                welcome_text,
                thread_ids=[
                    thread.id
                ]
            )

            with state_lock:

                state[
                    "welcomed"
                ][welcome_key] = "sent"

                save_state()

            print(
                f"[WELCOME] "
                f"@{username} "
                f"in {thread.id}"
            )

        except Exception as exc:

            # DO NOT retry automatically.
            with state_lock:

                state[
                    "welcomed"
                ][welcome_key] = (
                    "send_error_no_retry"
                )

                save_state()

            print(
                f"[WELCOME ERROR] "
                f"{thread.id}: {exc}"
            )


# ============================================================
# THREAD PROCESSOR
# ============================================================

def process_thread(
    cl,
    thread,
    bot_pk,
    user_cache
):

    # --------------------------------------------------------
    # ONLY GROUP CHATS
    # --------------------------------------------------------

    if not getattr(
        thread,
        "is_group",
        False
    ):
        return

    thread_id = str(
        getattr(
            thread,
            "id",
            ""
        )
    )

    if not thread_id:
        return

    # --------------------------------------------------------
    # ADMIN GATE
    # --------------------------------------------------------

    if not bot_is_admin(
        thread,
        bot_pk
    ):

        print(
            f"[SKIP] Bot is NOT admin "
            f"in GC {thread_id}"
        )

        return

    # --------------------------------------------------------
    # MEMBERS
    # --------------------------------------------------------

    users = list(
        getattr(
            thread,
            "users",
            []
        ) or []
    )

    current_members = {
        user_pk(user)
        for user in users
        if user_pk(user)
    }

    # Cache usernames
    for user in users:

        pk = user_pk(user)

        username = clean_username(
            getattr(
                user,
                "username",
                ""
            )
        )

        if (
            pk
            and username != "unknown_user"
        ):

            user_cache[pk] = username

    # --------------------------------------------------------
    # MEMBER STATE
    # --------------------------------------------------------

    with state_lock:

        initialized = (
            thread_id
            in state["members"]
        )

        previous_members = set(
            state[
                "members"
            ].get(
                thread_id,
                []
            )
        )

        state[
            "members"
        ][thread_id] = sorted(
            current_members
        )

        save_state()

    # First scan = baseline only.
    # This prevents welcome spam for
    # existing members.
    handle_new_members(
        cl,
        thread,
        current_members,
        previous_members,
        initialized,
        user_cache
    )

    # --------------------------------------------------------
    # DAILY MESSAGE
    # --------------------------------------------------------

    send_scheduled_message(
        cl,
        thread
    )

    # --------------------------------------------------------
    # MESSAGE SCAN
    # --------------------------------------------------------

    messages = list(
        getattr(
            thread,
            "messages",
            []
        ) or []
    )

    if not messages:
        return

    # Process multiple recent messages,
    # not just messages[0].
    for message in messages[
        :MESSAGES_PER_THREAD
    ]:

        message_id = str(
            getattr(
                message,
                "id",
                ""
            )
        )

        if not message_id:
            continue

        sender_id = str(
            getattr(
                message,
                "user_id",
                ""
            )
        )

        if not sender_id:
            continue

        # Ignore bot messages
        if sender_id == str(
            bot_pk
        ):
            continue

        event_key = (
            f"{thread_id}:"
            f"{message_id}"
        )

        # Persistent dedup check
        with state_lock:

            if (
                event_key
                in state[
                    "processed"
                ]
            ):
                continue

        text = str(
            getattr(
                message,
                "text",
                ""
            ) or ""
        ).strip()

        lower = text.lower()

        username = (
            get_sender_username(
                cl,
                message,
                user_cache
            )
        )

        mention = (
            f"@{username}"
        )

        # ----------------------------------------------------
        # ADMIN CHECK
        # ----------------------------------------------------

        admin_ids = get_admin_ids(
            thread
        )

        # Admin messages are never moderated.
        if sender_id in admin_ids:
            continue

        # ----------------------------------------------------
        # ALL ADMINS
        # ----------------------------------------------------

        admins = get_admin_names(
            thread,
            bot_pk
        )

        if admins:

            admin_text = " ".join(
                f"@{name}"
                for name in admins
            )

        else:

            admin_text = (
                "GC ADMINS"
            )

        # ----------------------------------------------------
        # 1. LINK DETECTION
        # ----------------------------------------------------

        if has_link(
            message,
            text
        ):

            alert = (
                "🚨🔗 "
                "𝗟𝗜𝗡𝗞 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗!\n\n"

                f"👤 𝗨𝗦𝗘𝗥 ➜ "
                f"{mention}\n"

                "⚠️ 𝗨𝗡𝗔𝗨𝗧𝗛𝗢𝗥𝗜𝗭𝗘𝗗 "
                "𝗟𝗜𝗡𝗞𝗦 𝗔𝗥𝗘 𝗡𝗢𝗧 "
                "𝗔𝗟𝗟𝗢𝗪𝗘𝗗 𝗛𝗘𝗥𝗘.\n"

                "🛑 𝗣𝗟𝗘𝗔𝗦𝗘 𝗥𝗘𝗠𝗢𝗩𝗘 "
                "𝗜𝗧 & 𝗗𝗢𝗡'𝗧 𝗥𝗘𝗣𝗘𝗔𝗧!\n\n"

                f"👑 𝗔𝗗𝗠𝗜𝗡𝗦 ➜ "
                f"{admin_text}\n\n"

                f"👑 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ "
                f"@{OWNER_USERNAME}\n"

                f"🤖 𝗕𝗢𝗧 ➜ "
                f"@{BOT_USERNAME}"
            )

            send_once(
                cl,
                thread.id,
                alert,
                event_key,
                reply_to=message
            )

            continue

        # ----------------------------------------------------
        # 2. REEL / VIDEO
        # ----------------------------------------------------

        if is_reel_or_video(
            message,
            text
        ):

            alert = (
                "🚫🎬 "
                "𝗥𝗘𝗘𝗟 / 𝗩𝗜𝗗𝗘𝗢 "
                "𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗!\n\n"

                f"👤 𝗨𝗦𝗘𝗥 ➜ "
                f"{mention}\n"

                "⚠️ 𝗥𝗘𝗘𝗟𝗦 / 𝗩𝗜𝗗𝗘𝗢𝗦 "
                "𝗔𝗥𝗘 𝗡𝗢𝗧 "
                "𝗔𝗟𝗟𝗢𝗪𝗘𝗗 𝗛𝗘𝗥𝗘.\n\n"

                "🛑 𝗣𝗟𝗘𝗔𝗦𝗘 "
                "𝗗𝗢𝗡'𝗧 𝗥𝗘𝗣𝗘𝗔𝗧!\n\n"

                f"👑 𝗔𝗗𝗠𝗜𝗡𝗦 ➜ "
                f"{admin_text}\n\n"

                f"👑 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ "
                f"@{OWNER_USERNAME}\n"

                f"🤖 𝗕𝗢𝗧 ➜ "
                f"@{BOT_USERNAME}"
            )

            send_once(
                cl,
                thread.id,
                alert,
                event_key,
                reply_to=message
            )

            continue

        # ----------------------------------------------------
        # 3. RESTRICTED CONTENT
        # ----------------------------------------------------

        if is_restricted(
            text
        ):

            alert = (
                "🚨🛡️ "
                "𝗠𝗢𝗗𝗘𝗥𝗔𝗧𝗜𝗢𝗡 "
                "𝗔𝗟𝗘𝗥𝗧!\n\n"

                f"👤 𝗨𝗦𝗘𝗥 ➜ "
                f"{mention}\n"

                "🚫 𝗜𝗡𝗔𝗣𝗣𝗥𝗢𝗣𝗥𝗜𝗔𝗧𝗘 "
                "𝗖𝗢𝗡𝗧𝗘𝗡𝗧 "
                "𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗!\n\n"

                "⚠️ 𝗧𝗛𝗜𝗦 𝗖𝗢𝗡𝗧𝗘𝗡𝗧 "
                "𝗜𝗦 𝗡𝗢𝗧 𝗔𝗟𝗟𝗢𝗪𝗘𝗗 "
                "𝗜𝗡 𝗧𝗛𝗜𝗦 𝗚𝗖.\n"

                f"👑 𝗔𝗗𝗠𝗜𝗡𝗦 ➜ "
                f"{admin_text}\n"

                "🔎 𝗣𝗟𝗘𝗔𝗦𝗘 "
                "𝗥𝗘𝗩𝗜𝗘𝗪 & 𝗧𝗔𝗞𝗘 "
                "𝗔𝗖𝗧𝗜𝗢𝗡.\n\n"

                f"👑 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ "
                f"@{OWNER_USERNAME}\n"

                f"🤖 𝗕𝗢𝗧 ➜ "
                f"@{BOT_USERNAME}"
            )

            send_once(
                cl,
                thread.id,
                alert,
                event_key,
                reply_to=message
            )

            continue

        # ----------------------------------------------------
        # 4. BOT / EVERYONE TAG
        # ----------------------------------------------------

        bot_tag = (
            f"@{BOT_USERNAME.lower()}"
        )

        if (
            "@everyone" in lower
            or bot_tag in lower
        ):

            response = (
                f"👋 𝗛𝗘𝗟𝗟𝗢 "
                f"{mention}!\n\n"

                "🤖 𝗕𝗢𝗧 𝗜𝗦 "
                "𝗔𝗖𝗧𝗜𝗩𝗘 𝗔𝗡𝗗 "
                "𝗠𝗔𝗡𝗔𝗚𝗜𝗡𝗚 "
                "𝗧𝗛𝗘 𝗚𝗖 "
                "𝗦𝗠𝗢𝗢𝗧𝗛𝗟𝗬. 🚀\n\n"

                f"👑 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ "
                f"@{OWNER_USERNAME}\n"

                f"🤖 𝗕𝗢𝗧 ➜ "
                f"@{BOT_USERNAME}"
            )

            send_once(
                cl,
                thread.id,
                response,
                event_key,
                reply_to=message
            )


# ============================================================
# CLIENT
# ============================================================

def build_client():

    if not SESSION_ID:

        raise RuntimeError(
            "IG_SESSION_ID environment "
            "variable is missing."
        )

    cl = Client()

    cl.delay_range = [
        1,
        2
    ]

    cl.request_timeout = 15

    cl.session_retry_total = 2

    cl.session_retry_backoff_factor = 2

    # SESSION-ID LOGIN ONLY
    cl.login_by_sessionid(
        SESSION_ID
    )

    return cl


# ============================================================
# MAIN 24/7 LOOP
# ============================================================

def run_forever():

    load_state()

    user_cache = {}

    while True:

        cl = None

        try:

            print(
                "[*] Connecting "
                "with Session-ID..."
            )

            cl = build_client()

            bot_pk = str(
                cl.user_id
            )

            print(
                f"[+] @{BOT_USERNAME} "
                f"is LIVE"
            )

            print(
                f"[+] BOT ID: {bot_pk}"
            )

            while True:

                cycle_started = (
                    time.monotonic()
                )

                try:

                    threads = (
                        cl.direct_threads(
                            amount=(
                                THREAD_BATCH_SIZE
                            ),
                            thread_message_limit=(
                                MESSAGES_PER_THREAD
                            )
                        )
                    )

                    print(
                        f"[SCAN] "
                        f"GCs={len(threads)}"
                    )

                    for thread in threads:

                        try:

                            process_thread(
                                cl,
                                thread,
                                bot_pk,
                                user_cache
                            )

                        except Exception as exc:

                            print(
                                "[THREAD ERROR] "
                                f"{getattr(thread, 'id', '?')}: "
                                f"{exc}"
                            )

                    trim_state()

                    save_state()

                except Exception as exc:

                    print(
                        f"[SCAN ERROR] "
                        f"{exc}"
                    )

                    time.sleep(5)

                elapsed = (
                    time.monotonic()
                    - cycle_started
                )

                sleep_for = max(
                    0.5,
                    POLL_SECONDS
                    - elapsed
                )

                time.sleep(
                    sleep_for
                )

        except KeyboardInterrupt:

            print(
                "[STOP] "
                "Bot stopped."
            )

            break

        except Exception as exc:

            print(
                "[RECONNECT] "
                f"{exc}"
            )

            time.sleep(
                RECONNECT_SECONDS
            )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    run_forever()
