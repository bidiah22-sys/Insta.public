import os
import time
import json
import threading
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from instagrapi import Client


# =========================================================
# CONFIG
# =========================================================

BOT_USERNAME = os.getenv("BOT_USERNAME") or "smw_bot0.1"
OWNER_USERNAME = os.getenv("OWNER_USERNAME") or "fx_smw"

# Session ID Railway Variable से लेना बेहतर है.
# Code में अपना real session ID public मत डालना.
SESSION_ID = os.getenv("IG_SESSION_ID") or "YAHAN_APNI_SESSION_ID_DAL"

TIMEZONE = "Asia/Kolkata"
TZ = ZoneInfo(TIMEZONE)

POLL_SECONDS = max(3, int(os.getenv("POLL_SECONDS", "5")))
THREAD_LIMIT = max(3, int(os.getenv("THREAD_LIMIT", "20")))
SEND_DELAY = max(1.0, float(os.getenv("SEND_DELAY", "1.5")))

BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "state.json"


# =========================================================
# MESSAGES
# =========================================================

DEV_LINE = f"👑 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ @{OWNER_USERNAME}"
BOT_LINE = f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}"


def welcome_message(username):
    return (
        f"🌸✨ 𝗪𝗘𝗟𝗖𝗢𝗠𝗘 𝗧𝗢 𝗚𝗖 ✨🌸\n\n"
        f"👋 𝗛𝗘𝗬 @{username}, 𝗪𝗘𝗟𝗖𝗢𝗠𝗘! 💗\n\n"
        f"🔥 𝗚𝗟𝗔𝗗 𝗧𝗢 𝗛𝗔𝗩𝗘 𝗬𝗢𝗨 𝗛𝗘𝗥𝗘!\n"
        f"🤝 𝗝𝗢𝗜𝗡 𝗧𝗛𝗘 𝗩𝗜𝗕𝗘 • 𝗠𝗘𝗘𝗧 𝗡𝗘𝗪 𝗣𝗘𝗢𝗣𝗟𝗘 • 𝗘𝗡𝗝𝗢𝗬 ✨\n\n"
        f"⚠️ 𝗥𝗘𝗦𝗣𝗘𝗖𝗧 𝗧𝗛𝗘 𝗚𝗖 • 𝗦𝗧𝗔𝗬 𝗔𝗖𝗧𝗜𝗩𝗘 • 𝗞𝗘𝗘𝗣 𝗧𝗛𝗘 𝗩𝗜𝗕𝗘 𝗚𝗢𝗜𝗡𝗚! ❤️‍🔥\n\n"
        f"🌸 𝗛𝗔𝗩𝗘 𝗙𝗨𝗡 & 𝗘𝗡𝗝𝗢𝗬 𝗧𝗛𝗘 𝗚𝗖! 💫\n\n"
        f"{DEV_LINE}\n"
        f"{BOT_LINE}"
    )


DAILY_MESSAGES = {
    "morning": (
        "🌸✨ 𝗚𝗢𝗢𝗗 𝗠𝗢𝗥𝗡𝗜𝗡𝗚, 𝗚𝗖! ✨🌸\n\n"
        "👋 𝗛𝗘𝗬 𝗘𝗩𝗘𝗥𝗬𝗢𝗡𝗘, 𝗥𝗜𝗦𝗘 & 𝗦𝗛𝗜𝗡𝗘! ☀️💗\n\n"
        "🚩 𝗝𝗔𝗜 𝗦𝗛𝗥𝗘𝗘 𝗥𝗔𝗠 🙏\n"
        "✨ 𝗡𝗘𝗪 𝗗𝗔𝗬 • 𝗡𝗘𝗪 𝗘𝗡𝗘𝗥𝗚𝗬 • 𝗡𝗘𝗪 𝗩𝗜𝗕𝗘!\n\n"
        "🔥 𝗦𝗧𝗔𝗬 𝗣𝗢𝗦𝗜𝗧𝗜𝗩𝗘 & 𝗠𝗔𝗞𝗘 𝗜𝗧 𝗖𝗢𝗨𝗡𝗧! 💫\n\n"
        f"{DEV_LINE}\n{BOT_LINE}"
    ),

    "afternoon": (
        "☀️✨ 𝗚𝗢𝗢𝗗 𝗔𝗙𝗧𝗘𝗥𝗡𝗢𝗢𝗡, 𝗚𝗖! ✨☀️\n\n"
        "🌸 𝗛𝗘𝗬 𝗘𝗩𝗘𝗥𝗬𝗢𝗡𝗘, 𝗛𝗢𝗪'𝗦 𝗧𝗛𝗘 𝗗𝗔𝗬 𝗚𝗢𝗜𝗡𝗚? 💗\n\n"
        "🙏 𝗥𝗔𝗗𝗛𝗘 𝗥𝗔𝗗𝗛𝗘!\n"
        "✨ 𝗞𝗘𝗘𝗣 𝗧𝗛𝗘 𝗘𝗡𝗘𝗥𝗚𝗬 𝗛𝗜𝗚𝗛 & 𝗧𝗛𝗘 𝗩𝗜𝗕𝗘 𝗔𝗟𝗜𝗩𝗘! 🔥\n\n"
        "💫 𝗘𝗡𝗝𝗢𝗬 𝗧𝗛𝗘 𝗥𝗘𝗦𝗧 𝗢𝗙 𝗬𝗢𝗨𝗥 𝗗𝗔𝗬!\n\n"
        f"{DEV_LINE}\n{BOT_LINE}"
    ),

    "evening": (
        "🌆✨ 𝗚𝗢𝗢𝗗 𝗘𝗩𝗘𝗡𝗜𝗡𝗚, 𝗚𝗖! ✨🌆\n\n"
        "👋 𝗛𝗘𝗬 𝗘𝗩𝗘𝗥𝗬𝗢𝗡𝗘! 💗\n"
        "🌸 𝗧𝗜𝗠𝗘 𝗧𝗢 𝗨𝗡𝗪𝗜𝗡𝗗 & 𝗘𝗡𝗝𝗢𝗬 𝗧𝗛𝗘 𝗩𝗜𝗕𝗘! ✨\n\n"
        "🙏 𝗥𝗔𝗗𝗛𝗘 𝗥𝗔𝗗𝗛𝗘!\n"
        "🔥 𝗞𝗘𝗘𝗣 𝗧𝗛𝗘 𝗚𝗖 𝗟𝗜𝗩𝗘 • 𝗞𝗘𝗘𝗣 𝗧𝗛𝗘 𝗩𝗜𝗕𝗘 𝗚𝗢𝗜𝗡𝗚! ❤️‍🔥\n\n"
        "💫 𝗛𝗔𝗩𝗘 𝗔 𝗚𝗥𝗘𝗔𝗧 𝗘𝗩𝗘𝗡𝗜𝗡𝗚!\n\n"
        f"{DEV_LINE}\n{BOT_LINE}"
    ),

    "night": (
        "🌙✨ 𝗚𝗢𝗢𝗗 𝗡𝗜𝗚𝗛𝗧, 𝗚𝗖! ✨🌙\n\n"
        "💗 𝗛𝗘𝗬 𝗘𝗩𝗘𝗥𝗬𝗢𝗡𝗘, 𝗧𝗜𝗠𝗘 𝗧𝗢 𝗥𝗘𝗦𝗧!\n\n"
        "🚩 𝗝𝗔𝗜 𝗦𝗛𝗥𝗘𝗘 𝗥𝗔𝗠 🙏\n"
        "✨ 𝗧𝗛𝗔𝗡𝗞𝗦 𝗙𝗢𝗥 𝗔𝗡𝗢𝗧𝗛𝗘𝗥 𝗚𝗥𝗘𝗔𝗧 𝗗𝗔𝗬!\n\n"
        "🌸 𝗥𝗘𝗦𝗧 𝗪𝗘𝗟𝗟 • 𝗦𝗧𝗔𝗬 𝗕𝗟𝗘𝗦𝗦𝗘𝗗 • 𝗦𝗘𝗘 𝗬𝗢𝗨 𝗧𝗢𝗠𝗢𝗥𝗥𝗢𝗪! 💫\n\n"
        f"{DEV_LINE}\n{BOT_LINE}"
    ),
}


# =========================================================
# BAD WORD FILTER
# =========================================================

BAD_WORDS = {
    "chutiya",
    "chutiyapa",
    "madarchod",
    "mc",
    "behenchod",
    "bc",
    "bhosdi",
    "bhosdike",
    "gandu",
    "gaand",
    "harami",
    "kamina",
    "kamine",
    "lavde",
    "lodu",
    "randi",
    "saala",
    "sala",
    "fuck",
    "fucking",
    "bitch",
    "asshole",
}


# =========================================================
# STATE
# =========================================================

def load_state():
    default = {
        "welcomed": {},
        "processed_messages": {},
        "threads": {},
    }

    try:
        if STATE_FILE.exists():
            data = json.loads(
                STATE_FILE.read_text(encoding="utf-8")
            )

            if not isinstance(data, dict):
                return default

            for key, value in default.items():
                if key not in data or not isinstance(data[key], dict):
                    data[key] = value

            return data

    except Exception as e:
        print(f"[STATE] Read error: {e}")

    return default


def save_state(state):
    try:
        temp = STATE_FILE.with_suffix(".tmp")

        temp.write_text(
            json.dumps(
                state,
                ensure_ascii=False,
                indent=2
            ),
            encoding="utf-8"
        )

        temp.replace(STATE_FILE)

    except Exception as e:
        print(f"[STATE] Save error: {e}")


# =========================================================
# BOT
# =========================================================

class GCBot:

    def __init__(self):
        self.cl = Client()

        self.cl.delay_range = [0.8, 1.8]

        self.state = load_state()

        self.lock = threading.RLock()

        self.welcome_processing = set()

        self.reply_processing = set()

        self.scheduler = BackgroundScheduler(
            timezone=TZ
        )

        self.running = True

        self.bot_pk = None


    # -----------------------------------------------------
    # LOGIN
    # -----------------------------------------------------

    def login(self):

        if not SESSION_ID or SESSION_ID == "YAHAN_APNI_SESSION_ID_DAL":
            print(
                "[LOGIN ERROR] IG_SESSION_ID Railway Variable "
                "missing hai."
            )
            return False

        try:

            print(
                "[*] Connecting to Instagram using Session ID..."
            )

            self.cl.login_by_sessionid(SESSION_ID)

            self.bot_pk = str(self.cl.user_id)

            print(
                f"[+] LOGIN SUCCESS | @{BOT_USERNAME} | "
                f"ID: {self.bot_pk}"
            )

            return True

        except Exception as e:

            print(
                f"[-] SESSION LOGIN FAILED: {e}"
            )

            return False


    # -----------------------------------------------------
    # GROUP CHECK
    # -----------------------------------------------------

    @staticmethod
    def is_group(thread):

        try:

            if getattr(thread, "is_group", False):
                return True

            users = getattr(thread, "users", None)

            if users and len(users) >= 2:
                return True

        except Exception:
            pass

        return False


    # -----------------------------------------------------
    # ADMIN LIST
    # -----------------------------------------------------

    def get_admins(self, thread):

        admins = []

        try:

            admin_ids = getattr(
                thread,
                "admin_user_ids",
                None
            )

            if admin_ids:

                admin_ids = {
                    str(x)
                    for x in admin_ids
                }

                for user in getattr(
                    thread,
                    "users",
                    []
                ):

                    uid = str(
                        getattr(user, "pk", "")
                    )

                    username = getattr(
                        user,
                        "username",
                        None
                    )

                    if (
                        uid in admin_ids
                        and username
                        and uid != str(self.bot_pk)
                    ):
                        admins.append(
                            f"@{username}"
                        )

        except Exception as e:
            print(f"[ADMIN] Error: {e}")

        # Duplicate usernames remove
        return list(dict.fromkeys(admins))


    def admin_tags(self, thread):

        admins = self.get_admins(thread)

        if not admins:
            return "👑 𝗔𝗗𝗠𝗜𝗡 ➜ @ADMIN"

        return (
            "👑 𝗔𝗗𝗠𝗜𝗡𝗦 ➜ "
            + " ".join(admins)
        )


    # -----------------------------------------------------
    # SAFE SEND
    # -----------------------------------------------------

    def send_once(
        self,
        thread_id,
        text,
        unique_key=None
    ):

        if unique_key:

            with self.lock:

                if unique_key in self.state[
                    "processed_messages"
                ]:
                    return False

                if unique_key in self.reply_processing:
                    return False

                self.reply_processing.add(
                    unique_key
                )

        try:

            self.cl.direct_send(
                text,
                thread_ids=[thread_id]
            )

            if unique_key:

                with self.lock:

                    self.state[
                        "processed_messages"
                    ][unique_key] = int(time.time())

                    # Keep state manageable
                    if len(
                        self.state[
                            "processed_messages"
                        ]
                    ) > 5000:

                        old = sorted(
                            self.state[
                                "processed_messages"
                            ].items(),
                            key=lambda x: x[1]
                        )[:1000]

                        for key, _ in old:
                            self.state[
                                "processed_messages"
                            ].pop(key, None)

                    save_state(self.state)

            return True

        except Exception as e:

            print(
                f"[SEND ERROR] {thread_id}: {e}"
            )

            return False

        finally:

            if unique_key:

                with self.lock:
                    self.reply_processing.discard(
                        unique_key
                    )


    # -----------------------------------------------------
    # WELCOME
    # -----------------------------------------------------

    def welcome_user(
        self,
        thread_id,
        user
    ):

        uid = getattr(
            user,
            "pk",
            None
        )

        username = getattr(
            user,
            "username",
            None
        )

        if not uid or not username:
            return

        uid = str(uid)

        unique_key = (
            f"welcome:{thread_id}:{uid}"
        )

        # Immediate memory lock
        # prevents double send before state saves
        with self.lock:

            if (
                unique_key
                in self.state["welcomed"]
            ):
                return

            if unique_key in self.welcome_processing:
                return

            self.welcome_processing.add(
                unique_key
            )

        try:

            text = welcome_message(
                username
            )

            try:

                self.cl.direct_send(
                    text,
                    thread_ids=[thread_id]
                )

            except Exception as e:

                print(
                    f"[WELCOME SEND ERROR] {e}"
                )

                return

            with self.lock:

                self.state[
                    "welcomed"
                ][unique_key] = int(time.time())

                save_state(self.state)

            print(
                f"[WELCOME] Sent once -> "
                f"@{username} | GC {thread_id}"
            )

            time.sleep(
                SEND_DELAY
            )

        finally:

            with self.lock:
                self.welcome_processing.discard(
                    unique_key
                )


    # -----------------------------------------------------
    # MESSAGE HELPERS
    # -----------------------------------------------------

    @staticmethod
    def get_username(message):

        try:

            user = getattr(
                message,
                "user",
                None
            )

            if user:

                username = getattr(
                    user,
                    "username",
                    None
                )

                if username:
                    return username

        except Exception:
            pass

        return "User"


    @staticmethod
    def get_text(message):

        try:
            return str(
                getattr(
                    message,
                    "text",
                    ""
                ) or ""
            ).strip()

        except Exception:
            return ""


    @staticmethod
    def message_type(message):

        try:
            return str(
                getattr(
                    message,
                    "item_type",
                    ""
                ) or ""
            ).lower()

        except Exception:
            return ""


    # -----------------------------------------------------
    # LINK DETECTION
    # -----------------------------------------------------

    @staticmethod
    def contains_link(text):

        text = text.lower()

        link_signatures = (
            "http://",
            "https://",
            "www.",
            "t.me/",
            "instagram.com/",
            "facebook.com/",
            "youtube.com/",
            "youtu.be/",
            "discord.gg/",
        )

        return any(
            x in text
            for x in link_signatures
        )


    # -----------------------------------------------------
    # REEL / VIDEO DETECTION
    # -----------------------------------------------------

    @staticmethod
    def contains_reel(message):

        text = GCBot.get_text(
            message
        ).lower()

        item_type = GCBot.message_type(
            message
        )

        reel_words = (
            "/reel/",
            "/reels/",
            "/p/",
            "reel",
            "video",
            "clip",
            "media",
            "visual_media",
        )

        return (
            any(
                x in text
                for x in reel_words
            )
            or any(
                x in item_type
                for x in (
                    "video",
                    "clip",
                    "media",
                    "reel",
                )
            )
        )


    # -----------------------------------------------------
    # BAD WORD DETECTION
    # -----------------------------------------------------

    @staticmethod
    def contains_bad_word(text):

        lowered = text.lower()

        words = (
            lowered
            .replace("\n", " ")
            .replace(",", " ")
            .replace(".", " ")
            .replace("!", " ")
            .replace("?", " ")
        ).split()

        for word in BAD_WORDS:

            if word in words:
                return True

        return False


    # -----------------------------------------------------
    # MODERATION ALERT
    # -----------------------------------------------------

    def moderation_alert(
        self,
        thread,
        message,
        reason
    ):

        thread_id = str(
            getattr(
                thread,
                "id",
                ""
            )
        )

        message_id = str(
            getattr(
                message,
                "id",
                ""
            )
        )

        if not thread_id or not message_id:
            return

        unique_key = (
            f"moderation:{message_id}:{reason}"
        )

        username = self.get_username(
            message
        )

        admins = self.admin_tags(
            thread
        )

        if reason == "link":

            title = (
                "🚨🔗 𝗟𝗜𝗡𝗞 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗!"
            )

            body = (
                "⚠️ 𝗨𝗡𝗔𝗨𝗧𝗛𝗢𝗥𝗜𝗭𝗘𝗗 𝗟𝗜𝗡𝗞 "
                "𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗 𝗜𝗡 𝗧𝗛𝗘 𝗚𝗖.\n"
                "🛑 𝗣𝗟𝗘𝗔𝗦𝗘 𝗥𝗘𝗩𝗜𝗘𝗪 𝗧𝗛𝗜𝗦 𝗠𝗘𝗦𝗦𝗔𝗚𝗘."
            )

        elif reason == "reel":

            title = (
                "🚫🎬 𝗥𝗘𝗘𝗟 / 𝗩𝗜𝗗𝗘𝗢 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗!"
            )

            body = (
                "⚠️ 𝗥𝗘𝗘𝗟𝗦 / 𝗩𝗜𝗗𝗘𝗢𝗦 𝗔𝗥𝗘 "
                "𝗡𝗢𝗧 𝗔𝗟𝗟𝗢𝗪𝗘𝗗 𝗛𝗘𝗥𝗘.\n"
                "🛑 𝗣𝗟𝗘𝗔𝗦𝗘 𝗥𝗘𝗩𝗜𝗘𝗪."
            )

        else:

            title = (
                "🚨🛡️ 𝗠𝗢𝗗𝗘𝗥𝗔𝗧𝗜𝗢𝗡 𝗔𝗟𝗘𝗥𝗧!"
            )

            body = (
                "⚠️ 𝗜𝗡𝗔𝗣𝗣𝗥𝗢𝗣𝗥𝗜𝗔𝗧𝗘 / 𝗔𝗕𝗨𝗦𝗜𝗩𝗘 "
                "𝗟𝗔𝗡𝗚𝗨𝗔𝗚𝗘 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗.\n"
                "🛑 𝗣𝗟𝗘𝗔𝗦𝗘 𝗥𝗘𝗩𝗜𝗘𝗪."
            )

        alert = (
            f"{title}\n\n"
            f"👤 𝗨𝗦𝗘𝗥 ➜ @{username}\n"
            f"{body}\n\n"
            f"{admins}\n\n"
            f"{BOT_LINE}\n"
            f"{DEV_LINE}"
        )

        if self.send_once(
            thread_id,
            alert,
            unique_key
        ):
            print(
                f"[MODERATION] {reason} -> "
                f"@{username} | GC {thread_id}"
            )

            time.sleep(
                SEND_DELAY
            )


    # -----------------------------------------------------
    # MESSAGE PROCESSOR
    # -----------------------------------------------------

    def process_message(
        self,
        thread,
        message
    ):

        message_id = getattr(
            message,
            "id",
            None
        )

        if not message_id:
            return

        message_id = str(
            message_id
        )

        # Bot's own message ignore
        sender_id = str(
            getattr(
                message,
                "user_id",
                ""
            )
        )

        if (
            self.bot_pk
            and sender_id == self.bot_pk
        ):
            return

        text = self.get_text(
            message
        )

        item_type = self.message_type(
            message
        )

        # Empty system message
        if not text and not item_type:
            return

        # -------------------------------------------------
        # LINK
        # -------------------------------------------------

        if self.contains_link(text):

            self.moderation_alert(
                thread,
                message,
                "link"
            )

            return

        # -------------------------------------------------
        # REEL / VIDEO
        # -------------------------------------------------

        if self.contains_reel(message):

            self.moderation_alert(
                thread,
                message,
                "reel"
            )

            return

        # -------------------------------------------------
        # BAD WORD
        # -------------------------------------------------

        if self.contains_bad_word(text):

            self.moderation_alert(
                thread,
                message,
                "badword"
            )

            return

        # -------------------------------------------------
        # BOT TAG / EVERYONE
        # -------------------------------------------------

        username = self.get_username(
            message
        )

        bot_tag = (
            f"@{BOT_USERNAME.lower()}"
        )

        if (
            "@everyone" in text.lower()
            or bot_tag in text.lower()
        ):

            unique_key = (
                f"botreply:{message_id}"
            )

            response = (
                f"👋 𝗛𝗘𝗟𝗟𝗢 @{username}!\n\n"
                "🤖 𝗕𝗢𝗧 𝗜𝗦 𝗔𝗖𝗧𝗜𝗩𝗘 "
                "𝗔𝗡𝗗 𝗠𝗔𝗡𝗔𝗚𝗜𝗡𝗚 𝗧𝗛𝗘 𝗚𝗖 "
                "𝗦𝗠𝗢𝗢𝗧𝗛𝗟𝗬. 🚀\n\n"
                f"{BOT_LINE}\n"
                f"{DEV_LINE}"
            )

            self.send_once(
                str(thread.id),
                response,
                unique_key
            )


    # -----------------------------------------------------
    # THREAD SCAN
    # -----------------------------------------------------

    def scan_groups(self):

        try:

            threads = self.cl.direct_threads(
                amount=THREAD_LIMIT
            )

            for thread in threads:

                if not self.is_group(thread):
                    continue

                thread_id = str(
                    getattr(
                        thread,
                        "id",
                        ""
                    )
                )

                if not thread_id:
                    continue

                # Save thread
                with self.lock:

                    self.state[
                        "threads"
                    ][thread_id] = int(
                        time.time()
                    )

                # -----------------------------------------
                # NEW MEMBER DETECTION
                # -----------------------------------------

                current_members = {
                    str(
                        getattr(
                            user,
                            "pk",
                            ""
                        )
                    )
                    for user in (
                        getattr(
                            thread,
                            "users",
                            []
                        ) or []
                    )
                }

                previous_members = set()

                with self.lock:

                    previous_raw = (
                        self.state[
                            "threads"
                        ].get(
                            f"members:{thread_id}",
                            []
                        )
                    )

                    if isinstance(
                        previous_raw,
                        list
                    ):
                        previous_members = {
                            str(x)
                            for x in previous_raw
                        }

                # First observation:
                # don't welcome old members
                if previous_members:

                    newly_joined = (
                        current_members
                        - previous_members
                    )

                    for joined_id in newly_joined:

                        user_obj = next(
                            (
                                u
                                for u in (
                                    getattr(
                                        thread,
                                        "users",
                                        []
                                    ) or []
                                )
                                if str(
                                    getattr(
                                        u,
                                        "pk",
                                        ""
                                    )
                                ) == joined_id
                            ),
                            None
                        )

                        if user_obj:

                            self.welcome_user(
                                thread_id,
                                user_obj
                            )

                with self.lock:

                    self.state[
                        "threads"
                    ][
                        f"members:{thread_id}"
                    ] = list(
                        current_members
                    )

                # -----------------------------------------
                # RECENT MESSAGE SCAN
                # -----------------------------------------

                messages = (
                    getattr(
                        thread,
                        "messages",
                        []
                    ) or []
                )

                # Recent messages scan
                for message in list(
                    messages
                )[:10]:

                    self.process_message(
                        thread,
                        message
                    )

            save_state(
                self.state
            )

        except Exception as e:

            print(
                f"[SCAN ERROR] {e}"
            )


    # -----------------------------------------------------
    # DAILY BROADCAST
    # -----------------------------------------------------

    def broadcast(self, name):

        try:

            message = DAILY_MESSAGES.get(
                name
            )

            if not message:
                return

            threads = self.cl.direct_threads(
                amount=THREAD_LIMIT
            )

            groups = []

            for thread in threads:

                if self.is_group(thread):

                    tid = getattr(
                        thread,
                        "id",
                        None
                    )

                    if tid:
                        groups.append(
                            str(tid)
                        )

            groups = list(
                dict.fromkeys(groups)
            )

            print(
                f"[SCHEDULE] {name.upper()} -> "
                f"{len(groups)} GCs"
            )

            for thread_id in groups:

                try:

                    self.cl.direct_send(
                        message,
                        thread_ids=[thread_id]
                    )

                    time.sleep(
                        SEND_DELAY
                    )

                except Exception as e:

                    print(
                        f"[BROADCAST ERROR] "
                        f"{thread_id}: {e}"
                    )

            print(
                f"[SCHEDULE] {name.upper()} DONE"
            )

        except Exception as e:

            print(
                f"[BROADCAST FAILED] {name}: {e}"
            )


    # -----------------------------------------------------
    # SCHEDULER
    # -----------------------------------------------------

    def start_scheduler(self):

        jobs = [
            ("morning", 6),
            ("afternoon", 12),
            ("evening", 19),
            ("night", 23),
        ]

        for name, hour in jobs:

            self.scheduler.add_job(
                self.broadcast,
                CronTrigger(
                    hour=hour,
                    minute=0,
                    timezone=TZ
                ),
                args=[name],
                id=f"daily_{name}",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
                misfire_grace_time=5,
            )

        self.scheduler.start()

        print(
            "⏰ SCHEDULE ACTIVE | "
            "06:00 / 12:00 / 19:00 / 23:00 "
            "| Asia/Kolkata"
        )


    # -----------------------------------------------------
    # MAIN LOOP
    # -----------------------------------------------------

    def run(self):

        while self.running:

            if self.login():
                break

            print(
                "[!] Login failed. "
                "Retrying in 30 seconds..."
            )

            time.sleep(30)

        self.start_scheduler()

        print(
            "🔥 SMW GC BOT IS LIVE!"
        )

        print(
            f"⚡ Poll interval: {POLL_SECONDS}s"
        )

        print(
            f"🤖 Bot: @{BOT_USERNAME}"
        )

        print(
            f"👑 Developer: @{OWNER_USERNAME}"
        )

        while self.running:

            try:

                self.scan_groups()

            except Exception as e:

                print(
                    f"[MAIN LOOP ERROR] {e}"
                )

            time.sleep(
                POLL_SECONDS
            )


# =========================================================
# START
# =========================================================

if __name__ == "__main__":

    bot = GCBot()

    try:
        bot.run()

    except KeyboardInterrupt:

        print(
            "\n[!] Bot stopped."
        )

    except Exception as e:

        print(
            f"[FATAL] {e}"
)
