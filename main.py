import asyncio
import contextlib
import json
import logging
import os
import signal
import threading
import time
from pathlib import Path
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from instagrapi import Client

APP_DIR = Path(__file__).resolve().parent
SESSION_FILE = APP_DIR / os.getenv("IG_SESSION_FILE", "session.json")
STATE_FILE = APP_DIR / "state.json"

USERNAME = os.getenv("IG_USERNAME", "").strip()
PASSWORD = os.getenv("IG_PASSWORD", "").strip()
TIMEZONE = os.getenv("TIMEZONE", "Asia/Kolkata")
WATCH_INTERVAL = max(8, int(os.getenv("WATCH_INTERVAL", "10")))
MAX_THREADS = max(10, int(os.getenv("MAX_THREADS", "100")))
SEND_DELAY = max(1.0, float(os.getenv("SEND_DELAY", "2.0")))
TZ = ZoneInfo(TIMEZONE)

DEVELOPER = "👑 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ @fx_smw"
BOT = "🤖 𝗕𝗢𝗧 ➜ @bot222703"

WELCOME = f'''🌸✨ 𝗪𝗘𝗟𝗖𝗢𝗠𝗘 𝗧𝗢 𝗚𝗖 ✨🌸

👋 𝗛𝗘𝗬 {{mention}}, 𝗪𝗘𝗟𝗖𝗢𝗠𝗘! 💗

🔥 𝗚𝗟𝗔𝗗 𝗧𝗢 𝗛𝗔𝗩𝗘 𝗬𝗢𝗨 𝗛𝗘𝗥𝗘!
🤝 𝗝𝗢𝗜𝗡 𝗧𝗛𝗘 𝗩𝗜𝗕𝗘 • 𝗠𝗘𝗘𝗧 𝗡𝗘𝗪 𝗣𝗘𝗢𝗣𝗟𝗘 • 𝗘𝗡𝗝𝗢𝗬 ✨

⚠️ 𝗥𝗘𝗦𝗣𝗘𝗖𝗧 𝗧𝗛𝗘 𝗚𝗖 • 𝗦𝗧𝗔𝗬 𝗔𝗖𝗧𝗜𝗩𝗘 • 𝗞𝗘𝗘𝗣 𝗧𝗛𝗘 𝗩𝗜𝗕𝗘 𝗚𝗢𝗜𝗡𝗚! ❤️‍🔥

🌸 𝗛𝗔𝗩𝗘 𝗙𝗨𝗡 & 𝗘𝗡𝗝𝗢𝗬 𝗧𝗛𝗘 𝗚𝗖! 💫

{DEVELOPER}
{BOT}'''

DAILY = {
    "morning": f'''🌸✨ 𝗚𝗢𝗢𝗗 𝗠𝗢𝗥𝗡𝗜𝗡𝗚, 𝗚𝗖! ✨🌸

👋 𝗛𝗘𝗬 𝗘𝗩𝗘𝗥𝗬𝗢𝗡𝗘, 𝗥𝗜𝗦𝗘 & 𝗦𝗛𝗜𝗡𝗘! ☀️💗

🚩 𝗝𝗔𝗜 𝗦𝗛𝗥𝗘𝗘 𝗥𝗔𝗠 🙏
✨ 𝗡𝗘𝗪 𝗗𝗔𝗬 • 𝗡𝗘𝗪 𝗘𝗡𝗘𝗥𝗚𝗬 • 𝗡𝗘𝗪 𝗩𝗜𝗕𝗘!

🔥 𝗦𝗧𝗔𝗬 𝗣𝗢𝗦𝗜𝗧𝗜𝗩𝗘 & 𝗠𝗔𝗞𝗘 𝗜𝗧 𝗖𝗢𝗨𝗡𝗧! 💫

{DEVELOPER}
{BOT}''',
    "afternoon": f'''☀️✨ 𝗚𝗢𝗢𝗗 𝗔𝗙𝗧𝗘𝗥𝗡𝗢𝗢𝗡, 𝗚𝗖! ✨☀️

🌸 𝗛𝗘𝗬 𝗘𝗩𝗘𝗥𝗬𝗢𝗡𝗘, 𝗛𝗢𝗪'𝗦 𝗧𝗛𝗘 𝗗𝗔𝗬 𝗚𝗢𝗜𝗡𝗚? 💗

🙏 𝗥𝗔𝗗𝗛𝗘 𝗥𝗔𝗗𝗛𝗘!
✨ 𝗞𝗘𝗘𝗣 𝗧𝗛𝗘 𝗘𝗡𝗘𝗥𝗚𝗬 𝗛𝗜𝗚𝗛 & 𝗧𝗛𝗘 𝗩𝗜𝗕𝗘 𝗔𝗟𝗜𝗩𝗘! 🔥

💫 𝗘𝗡𝗝𝗢𝗬 𝗧𝗛𝗘 𝗥𝗘𝗦𝗧 𝗢𝗙 𝗬𝗢𝗨𝗥 𝗗𝗔𝗬!

{DEVELOPER}
{BOT}''',
    "evening": f'''🌆✨ 𝗚𝗢𝗢𝗗 𝗘𝗩𝗘𝗡𝗜𝗡𝗚, 𝗚𝗖! ✨🌆

👋 𝗛𝗘𝗬 𝗘𝗩𝗘𝗥𝗬𝗢𝗡𝗘! 💗
🌸 𝗧𝗜𝗠𝗘 𝗧𝗢 𝗨𝗡𝗪𝗜𝗡𝗗 & 𝗘𝗡𝗝𝗢𝗬 𝗧𝗛𝗘 𝗩𝗜𝗕𝗘! ✨

🙏 𝗥𝗔𝗗𝗛𝗘 𝗥𝗔𝗗𝗛𝗘!
🔥 𝗞𝗘𝗘𝗣 𝗧𝗛𝗘 𝗚𝗖 𝗟𝗜𝗩𝗘 • 𝗞𝗘𝗘𝗣 𝗧𝗛𝗘 𝗩𝗜𝗕𝗘 𝗚𝗢𝗜𝗡𝗚! ❤️‍🔥

💫 𝗛𝗔𝗩𝗘 𝗔 𝗚𝗥𝗘𝗔𝗧 𝗘𝗩𝗘𝗡𝗜𝗡𝗚!

{DEVELOPER}
{BOT}''',
    "night": f'''🌙✨ 𝗚𝗢𝗢𝗗 𝗡𝗜𝗚𝗛𝗧, 𝗚𝗖! ✨🌙

💗 𝗛𝗘𝗬 𝗘𝗩𝗘𝗥𝗬𝗢𝗡𝗘, 𝗧𝗜𝗠𝗘 𝗧𝗢 𝗥𝗘𝗦𝗧!

🚩 𝗝𝗔𝗜 𝗦𝗛𝗥𝗘𝗘 𝗥𝗔𝗠 🙏
✨ 𝗧𝗛𝗔𝗡𝗞𝗦 𝗙𝗢𝗥 𝗔𝗡𝗢𝗧𝗛𝗘𝗥 𝗚𝗥𝗘𝗔𝗧 𝗗𝗔𝗬!

🌸 𝗥𝗘𝗦𝗧 𝗪𝗘𝗟𝗟 • 𝗦𝗧𝗔𝗬 𝗕𝗟𝗘𝗦𝗦𝗘𝗗 • 𝗦𝗘𝗘 𝗬𝗢𝗨 𝗧𝗢𝗠𝗢𝗥𝗥𝗢𝗪! 💫

{DEVELOPER}
{BOT}''',
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("SMW-GC-BOT")


def load_state():
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("state.json read failed: %s", e)
    return {"welcomed": {}, "threads": {}}


def save_state(state):
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE_FILE)


class Bot:
    def __init__(self):
        self.cl = Client()
        self.cl.delay_range = [1.0, 2.0]
        self.state = load_state()
        self.lock = threading.RLock()
        self.stop = asyncio.Event()
        self.broadcast_lock = asyncio.Lock()
        self.scheduler = AsyncIOScheduler(timezone=TZ)

    def login(self):
        if not USERNAME or not PASSWORD:
            raise RuntimeError("Railway Variables में IG_USERNAME और IG_PASSWORD सही से add करो.")
        if SESSION_FILE.exists():
            try:
                self.cl.load_settings(SESSION_FILE)
                log.info("Existing session settings loaded.")
            except Exception as e:
                log.warning("Session load failed, trying fresh login: %s", e)
        try:
            if self.cl.user_id:
                log.info("Using active session for @%s", USERNAME)
            else:
                self.cl.login(USERNAME, PASSWORD)
                self.cl.dump_settings(SESSION_FILE)
                log.info("Logged in successfully as @%s", USERNAME)
        except Exception as e:
            log.error("Login failed! Check credentials or 2FA/Checkpoint on Instagram app: %s", e)
            raise e

    def threads_sync(self):
        try:
            try:
                return list(self.cl.direct_threads(amount=MAX_THREADS, selected_filter="") or [])
            except TypeError:
                return list(self.cl.direct_threads(amount=MAX_THREADS) or [])
        except Exception as e:
            log.warning("direct_threads failed: %s", e)
            return []

    def send_sync(self, thread_id, text):
        try:
            self.cl.direct_send(text, thread_ids=[thread_id])
            return True
        except Exception as e:
            log.warning("Send failed [%s]: %s", thread_id, e)
            return False

    @staticmethod
    def tid(thread):
        value = getattr(thread, "id", None)
        return str(value) if value else None

    @staticmethod
    def is_group(thread):
        users = getattr(thread, "users", None)
        title = getattr(thread, "thread_title", None)
        return bool(title) or bool(users and len(users) >= 2)

    @staticmethod
    def join_event(item):
        kind = str(getattr(item, "item_type", "") or "").lower()
        return any(x in kind for x in ("join", "add", "participant", "admin_add"))

    @staticmethod
    def users_from(item):
        users = getattr(item, "users", None)
        if users:
            return list(users)
        user = getattr(item, "user", None)
        return [user] if user else []

    async def welcome(self, thread_id, user):
        uid = getattr(user, "pk", None) or getattr(user, "id", None)
        uname = getattr(user, "username", None)
        if not uid or not uname:
            return
        key = f"{thread_id}:{uid}"
        with self.lock:
            if key in self.state.setdefault("welcomed", {}):
                return
        text = WELCOME.format(mention=f"@{uname}")
        if await asyncio.to_thread(self.send_sync, thread_id, text):
            with self.lock:
                self.state["welcomed"][key] = int(time.time())
                if len(self.state["welcomed"]) > 5000:
                    old = sorted(self.state["welcomed"].items(), key=lambda x: x[1])[:1000]
                    for k, _ in old:
                        self.state["welcomed"].pop(k, None)
                save_state(self.state)
            log.info("Welcome sent to @%s in %s", uname, thread_id)
            await asyncio.sleep(SEND_DELAY)

    async def scan(self):
        threads = await asyncio.to_thread(self.threads_sync)
        for thread in threads:
            tid = self.tid(thread)
            if not tid or not self.is_group(thread):
                continue
            with self.lock:
                self.state.setdefault("threads", {})[tid] = int(time.time())
            for item in list(getattr(thread, "items", None) or [])[:30]:
                if self.join_event(item):
                    for user in self.users_from(item):
                        await self.welcome(tid, user)
        with self.lock:
            save_state(self.state)

    async def watcher(self):
        log.info("GC watcher ON | interval=%ss", WATCH_INTERVAL)
        while not self.stop.is_set():
            start = time.monotonic()
            try:
                await self.scan()
            except Exception as e:
                log.exception("Watcher error: %s", e)
            wait = max(1, WATCH_INTERVAL - (time.monotonic() - start))
            try:
                await asyncio.wait_for(self.stop.wait(), timeout=wait)
            except asyncio.TimeoutError:
                pass

    async def broadcast(self, name):
        if self.broadcast_lock.locked():
            log.warning("%s broadcast skipped: previous broadcast still running", name)
            return
        async with self.broadcast_lock:
            threads = await asyncio.to_thread(self.threads_sync)
            groups = list(dict.fromkeys(self.tid(t) for t in threads if self.tid(t) and self.is_group(t)))
            log.info("%s broadcast: %d GC(s)", name, len(groups))
            sent = 0
            for tid in groups:
                if await asyncio.to_thread(self.send_sync, tid, DAILY[name]):
                    sent += 1
                await asyncio.sleep(SEND_DELAY)
            log.info("%s broadcast complete: %d/%d", name, sent, len(groups))

    def schedule(self):
        common = dict(replace_existing=True, coalesce=True, max_instances=1, misfire_grace_time=5)
        jobs = [("morning", 6), ("afternoon", 12), ("evening", 19), ("night", 23)]
        for name, hour in jobs:
            self.scheduler.add_job(self.broadcast, CronTrigger(hour=hour, minute=0, timezone=TZ), args=[name], id=f"daily_{name}", **common)
        self.scheduler.start()

    async def shutdown(self):
        if self.stop.is_set():
            return
        self.stop.set()
        with contextlib.suppress(Exception): self.scheduler.shutdown(wait=False)
        with contextlib.suppress(Exception): self.cl.dump_settings(SESSION_FILE)
        with contextlib.suppress(Exception): save_state(self.state)
        log.info("Bot stopped.")

    async def run(self):
        self.login()
        self.schedule()
        log.info("SMW GC BOT ONLINE | 06:00 / 12:00 / 19:00 / 23:00 | %s", TIMEZONE)
        task = asyncio.create_task(self.watcher())
        try:
            await self.stop.wait()
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            await self.shutdown()


async def main():
    bot = Bot()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, lambda: asyncio.create_target(bot.shutdown()) if hasattr(asyncio, 'create_target') else asyncio.create_task(bot.shutdown()))
    await bot.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

