import asyncio
import contextlib
import json
import logging
import os
import signal
import time
from pathlib import Path
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from instagrapi import Client
from instagrapi.exceptions import BadPassword, ChallengeRequired, TwoFactorRequired

APP = Path(__file__).resolve().parent
STATE_FILE = APP / "state.json"
SESSION_FILE = APP / os.getenv("SESSION_FILE", "session.json")

# Set these ONLY in Railway Variables. Never hard-code the password.
IG_USERNAME = os.getenv("IG_USERNAME", "").strip()
IG_PASSWORD = os.getenv("IG_PASSWORD", "")
TIMEZONE = os.getenv("TIMEZONE", "Asia/Kolkata")
WATCH_INTERVAL = max(10, int(os.getenv("WATCH_INTERVAL", "15")))
MAX_THREADS = max(10, int(os.getenv("MAX_THREADS", "100")))
SEND_DELAY = max(1.5, float(os.getenv("SEND_DELAY", "2.5")))

try:
    TZ = ZoneInfo(TIMEZONE)
except Exception:
    TIMEZONE, TZ = "Asia/Kolkata", ZoneInfo("Asia/Kolkata")

DEVELOPER = "👑 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ @fx_smw"
BOT = "🤖 𝗕𝗢𝗧 ➜ @bot222703"

WELCOME = """🌸✨ 𝗪𝗘𝗟𝗖𝗢𝗠𝗘 𝗧𝗢 𝗚𝗖 ✨🌸

👋 𝗛𝗘𝗬 {mention}, 𝗪𝗘𝗟𝗖𝗢𝗠𝗘! 💗

🔥 𝗚𝗟𝗔𝗗 𝗧𝗢 𝗛𝗔𝗩𝗘 𝗬𝗢𝗨 𝗛𝗘𝗥𝗘!
🤝 𝗝𝗢𝗜𝗡 𝗧𝗛𝗘 𝗩𝗜𝗕𝗘 • 𝗠𝗘𝗘𝗧 𝗡𝗘𝗪 𝗣𝗘𝗢𝗣𝗟𝗘 • 𝗘𝗡𝗝𝗢𝗬 ✨

⚠️ 𝗥𝗘𝗦𝗣𝗘𝗖𝗧 𝗧𝗛𝗘 𝗚𝗖 • 𝗦𝗧𝗔𝗬 𝗔𝗖𝗧𝗜𝗩𝗘 • 𝗞𝗘𝗘𝗣 𝗧𝗛𝗘 𝗩𝗜𝗕𝗘 𝗚𝗢𝗜𝗡𝗚! ❤️‍🔥

🌸 𝗛𝗔𝗩𝗘 𝗙𝗨𝗡 & 𝗘𝗡𝗝𝗢𝗬 𝗧𝗛𝗘 𝗚𝗖! 💫

{developer}
{bot}"""

DAILY = {
    "morning": """🌸✨ 𝗚𝗢𝗢𝗗 𝗠𝗢𝗥𝗡𝗜𝗡𝗚, 𝗚𝗖! ✨🌸\n\n👋 𝗛𝗘𝗬 𝗘𝗩𝗘𝗥𝗬𝗢𝗡𝗘, 𝗥𝗜𝗦𝗘 & 𝗦𝗛𝗜𝗡𝗘! ☀️💗\n\n🚩 𝗝𝗔𝗜 𝗦𝗛𝗥𝗘𝗘 𝗥𝗔𝗠 🙏\n✨ 𝗡𝗘𝗪 𝗗𝗔𝗬 • 𝗡𝗘𝗪 𝗘𝗡𝗘𝗥𝗚𝗬 • 𝗡𝗘𝗪 𝗩𝗜𝗕𝗘!\n\n🔥 𝗦𝗧𝗔𝗬 𝗣𝗢𝗦𝗜𝗧𝗜𝗩𝗘 & 𝗠𝗔𝗞𝗘 𝗜𝗧 𝗖𝗢𝗨𝗡𝗧! 💫\n\n{developer}\n{bot}""",
    "afternoon": """☀️✨ 𝗚𝗢𝗢𝗗 𝗔𝗙𝗧𝗘𝗥𝗡𝗢𝗢𝗡, 𝗚𝗖! ✨☀️\n\n🌸 𝗛𝗘𝗬 𝗘𝗩𝗘𝗥𝗬𝗢𝗡𝗘, 𝗛𝗢𝗪'𝗦 𝗧𝗛𝗘 𝗗𝗔𝗬 𝗚𝗢𝗜𝗡𝗚? 💗\n\n🙏 𝗥𝗔𝗗𝗛𝗘 𝗥𝗔𝗗𝗛𝗘!\n✨ 𝗞𝗘𝗘𝗣 𝗧𝗛𝗘 𝗘𝗡𝗘𝗥𝗚𝗬 𝗛𝗜𝗚𝗛 & 𝗧𝗛𝗘 𝗩𝗜𝗕𝗘 𝗔𝗟𝗜𝗩𝗘! 🔥\n\n💫 𝗘𝗡𝗝𝗢𝗬 𝗧𝗛𝗘 𝗥𝗘𝗦𝗧 𝗢𝗙 𝗬𝗢𝗨𝗥 𝗗𝗔𝗬!\n\n{developer}\n{bot}""",
    "evening": """🌆✨ 𝗚𝗢𝗢𝗗 𝗘𝗩𝗘𝗡𝗜𝗡𝗚, 𝗚𝗖! ✨🌆\n\n👋 𝗛𝗘𝗬 𝗘𝗩𝗘𝗥𝗬𝗢𝗡𝗘! 💗\n🌸 𝗧𝗜𝗠𝗘 𝗧𝗢 𝗨𝗡𝗪𝗜𝗡𝗗 & 𝗘𝗡𝗝𝗢𝗬 𝗧𝗛𝗘 𝗩𝗜𝗕𝗘! ✨\n\n🙏 𝗥𝗔𝗗𝗛𝗘 𝗥𝗔𝗗𝗛𝗘!\n🔥 𝗞𝗘𝗘𝗣 𝗧𝗛𝗘 𝗚𝗖 𝗟𝗜𝗩𝗘 • 𝗞𝗘𝗘𝗣 𝗧𝗛𝗘 𝗩𝗜𝗕𝗘 𝗚𝗢𝗜𝗡𝗚! ❤️‍🔥\n\n💫 𝗛𝗔𝗩𝗘 𝗔 𝗚𝗥𝗘𝗔𝗧 𝗘𝗩𝗘𝗡𝗜𝗡𝗚!\n\n{developer}\n{bot}""",
    "night": """🌙✨ 𝗚𝗢𝗢𝗗 𝗡𝗜𝗚𝗛𝗧, 𝗚𝗖! ✨🌙\n\n💗 𝗛𝗘𝗬 𝗘𝗩𝗘𝗥𝗬𝗢𝗡𝗘, 𝗧𝗜𝗠𝗘 𝗧𝗢 𝗥𝗘𝗦𝗧!\n\n🚩 𝗝𝗔𝗜 𝗦𝗛𝗥𝗘𝗘 𝗥𝗔𝗠 🙏\n✨ 𝗧𝗛𝗔𝗡𝗞𝗦 𝗙𝗢𝗥 𝗔𝗡𝗢𝗧𝗛𝗘𝗥 𝗚𝗥𝗘𝗔𝗧 𝗗𝗔𝗬!\n\n🌸 𝗥𝗘𝗦𝗧 𝗪𝗘𝗟𝗟 • 𝗦𝗧𝗔𝗬 𝗕𝗟𝗘𝗦𝗦𝗘𝗗 • 𝗦𝗘𝗘 𝗬𝗢𝗨 𝗧𝗢𝗠𝗢𝗥𝗥𝗢𝗪! 💫\n\n{developer}\n{bot}""",
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("SMW-GC-BOT")


def load_state():
    try:
        if STATE_FILE.exists():
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("welcomed", {})
                data.setdefault("threads", {})
                return data
    except Exception as exc:
        log.warning("state.json read failed: %s", exc)
    return {"welcomed": {}, "threads": {}}


def save_state(state):
    try:
        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(STATE_FILE)
    except Exception as exc:
        log.warning("state.json save failed: %s", exc)


class Bot:
    def __init__(self):
        self.cl = Client()
        self.cl.delay_range = [2.0, 4.0]
        self.state = load_state()
        self.stop_event = asyncio.Event()
        self.broadcast_lock = asyncio.Lock()
        self.scheduler = AsyncIOScheduler(timezone=TZ)

    def check_config(self):
        if not IG_USERNAME or not IG_PASSWORD:
            missing = []
            if not IG_USERNAME: missing.append("IG_USERNAME")
            if not IG_PASSWORD: missing.append("IG_PASSWORD")
            raise RuntimeError("Missing Railway Variable(s): " + ", ".join(missing))

    def valid_session(self):
        if not SESSION_FILE.exists():
            return False
        try:
            self.cl.load_settings(SESSION_FILE)
            self.cl.get_timeline_feed()
            return True
        except Exception as exc:
            log.info("Saved session is invalid/expired: %s", exc)
            return False

    def login_once(self):
        self.check_config()
        if self.valid_session():
            log.info("✅ Existing session is valid; no password login needed.")
            return True
        self.cl = Client()
        self.cl.delay_range = [2.0, 4.0]
        try:
            log.info("Logging in as @%s...", IG_USERNAME)
            self.cl.login(IG_USERNAME, IG_PASSWORD)
            self.cl.dump_settings(SESSION_FILE)
            log.info("✅ Login successful; session saved.")
            return True
        except BadPassword:
            log.error("❌ Instagram rejected the password.")
        except TwoFactorRequired:
            log.error("⚠️ Instagram requires 2FA. Complete it normally.")
        except ChallengeRequired:
            log.error("⚠️ Instagram security checkpoint/challenge is required. Complete it normally in Instagram/browser.")
        except Exception as exc:
            log.error("❌ Login failed: %s", exc)
        return False

    async def authenticate(self):
        while not self.stop_event.is_set():
            try:
                if await asyncio.to_thread(self.login_once):
                    return True
            except RuntimeError as exc:
                log.error("%s", exc)
                return False
            log.warning("Login failed; waiting 60 seconds before retrying.")
            try:
                await asyncio.wait_for(self.stop_event.wait(), timeout=60)
            except asyncio.TimeoutError:
                pass
        return False

    def threads_sync(self):
        try:
            return list(self.cl.direct_threads(amount=MAX_THREADS) or [])
        except Exception as exc:
            log.warning("GC fetch failed: %s", exc)
            return []

    def send_sync(self, tid, text):
        try:
            self.cl.direct_send(text, thread_ids=[tid])
            return True
        except Exception as exc:
            log.warning("Send failed [%s]: %s", tid, exc)
            return False

    @staticmethod
    def tid(thread):
        value = getattr(thread, "id", None)
        return str(value) if value else None

    @staticmethod
    def is_group(thread):
        title = getattr(thread, "thread_title", None)
        users = getattr(thread, "users", None)
        try:
            return bool(title) or bool(users and len(users) >= 2)
        except Exception:
            return bool(title)

    @staticmethod
    def is_join_event(item):
        kind = str(getattr(item, "item_type", "") or "").lower()
        return any(x in kind for x in ("join", "add", "participant", "admin_add"))

    @staticmethod
    def event_users(item):
        users = getattr(item, "users", None)
        if users: return list(users)
        user = getattr(item, "user", None)
        return [user] if user else []

    async def welcome(self, tid, user):
        uid = getattr(user, "pk", None) or getattr(user, "id", None)
        username = getattr(user, "username", None)
        if not uid or not username: return
        key = f"{tid}:{uid}"
        if key in self.state["welcomed"]: return
        text = WELCOME.format(mention=f"@{username}", developer=DEVELOPER, bot=BOT)
        if await asyncio.to_thread(self.send_sync, tid, text):
            self.state["welcomed"][key] = int(time.time())
            save_state(self.state)
            log.info("Welcome sent to @%s | GC=%s", username, tid)
            await asyncio.sleep(SEND_DELAY)

    async def scan(self):
        for thread in await asyncio.to_thread(self.threads_sync):
            tid = self.tid(thread)
            if not tid or not self.is_group(thread): continue
            self.state["threads"][tid] = int(time.time())
            for item in list(getattr(thread, "items", None) or [])[:25]:
                if self.is_join_event(item):
                    for user in self.event_users(item):
                        await self.welcome(tid, user)
        save_state(self.state)

    async def watcher(self):
        log.info("🔥 GC watcher online | interval=%ss", WATCH_INTERVAL)
        while not self.stop_event.is_set():
            start = time.monotonic()
            try: await self.scan()
            except Exception as exc: log.warning("Watcher error: %s", exc)
            wait = max(2.0, WATCH_INTERVAL - (time.monotonic() - start))
            try: await asyncio.wait_for(self.stop_event.wait(), timeout=wait)
            except asyncio.TimeoutError: pass

    async def broadcast(self, name):
        if self.broadcast_lock.locked(): return
        async with self.broadcast_lock:
            groups = []
            for thread in await asyncio.to_thread(self.threads_sync):
                tid = self.tid(thread)
                if tid and self.is_group(thread): groups.append(tid)
            groups = list(dict.fromkeys(groups))
            text = DAILY[name].format(developer=DEVELOPER, bot=BOT)
            log.info("📢 %s broadcast → %d GC(s)", name.upper(), len(groups))
            sent = 0
            for tid in groups:
                if await asyncio.to_thread(self.send_sync, tid, text): sent += 1
                await asyncio.sleep(SEND_DELAY)
            log.info("Broadcast %s complete: %d/%d sent", name.upper(), sent, len(groups))

    def schedule(self):
        for name, hour in (("morning",6),("afternoon",12),("evening",19),("night",23)):
            self.scheduler.add_job(self.broadcast, CronTrigger(hour=hour, minute=0, timezone=TZ), args=[name], id=f"daily_{name}", replace_existing=True, coalesce=True, max_instances=1, misfire_grace_time=10)
        self.scheduler.start()

    async def shutdown(self):
        if self.stop_event.is_set(): return
        self.stop_event.set()
        with contextlib.suppress(Exception): self.scheduler.shutdown(wait=False)
        with contextlib.suppress(Exception): self.cl.dump_settings(SESSION_FILE)
        save_state(self.state)
        log.info("Bot shutdown complete.")

    async def run(self):
        if not await self.authenticate(): return
        self.schedule()
        log.info("========================================")
        log.info("🔥 SMW GC BOT ONLINE")
        log.info("👑 Developer: @fx_smw | 🤖 Bot: @bot222703")
        log.info("🇮🇳 Timezone: %s | ⏰ 06:00 / 12:00 / 19:00 / 23:00", TIMEZONE)
        log.info("========================================")
        watcher = asyncio.create_task(self.watcher())
        try: await self.stop_event.wait()
        finally:
            watcher.cancel()
            with contextlib.suppress(asyncio.CancelledError): await watcher
            await self.shutdown()


async def main():
    bot = Bot()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(bot.shutdown()))
    await bot.run()


if __name__ == "__main__":
    asyncio.run(main())

