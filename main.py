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
from instagrapi.exceptions import ChallengeRequired, BadPassword, TwoFactorRequired

APP_DIR = Path(__file__).resolve().parent
STATE_FILE = APP_DIR / "state.json"
SESSION_FILE = APP_DIR / "session.json"

# Credentials directly set
IG_USERNAME = "bot222703"
IG_PASSWORD = "SIDHU295"

TIMEZONE = os.getenv("TIMEZONE", "Asia/Kolkata")
WATCH_INTERVAL = max(15, int(os.getenv("WATCH_INTERVAL", "20")))
MAX_THREADS = max(10, int(os.getenv("MAX_THREADS", "100")))
SEND_DELAY = max(2.0, float(os.getenv("SEND_DELAY", "3.0")))
TZ = ZoneInfo(TIMEZONE)

DEVELOPER = "👑 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ @fx_smw"
BOT = "🤖 𝗕𝗢𝗧 ➜ @bot222703"

WELCOME = f'''🌸✨ 𝗪𝗘𝗟𝗖𝗢𝗠𝗘 𝗧𝗢 𝗚𝗖 ✨🌸

👋 𝗛𝗘𝗬 {{mention}}, 𝗪𝗘𝗟𝗖𝗢𝗠𝗘! 💗

🔥 𝗚𝗟𝗔𝗗 𝗧𝗢 HAVE 𝗬𝗢𝗨 𝗛𝗘𝗥𝗘!
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
log = logging.getLogger("SMW-STABLE-BOT")


def load_state():
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("state.json read failed: %s", e)
    return {"welcomed": {}, "threads": {}}


def save_state(state):
    try:
        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(STATE_FILE)
    except Exception as e:
        log.warning("state.json save failed: %s", e)


class Bot:
    def __init__(self):
        self.cl = Client()
        # Realistic delays to prevent rate limits
        self.cl.delay_range = [3.0, 6.0]
        self.state = load_state()
        self.lock = threading.RLock()
        self.stop = asyncio.Event()
        self.broadcast_lock = asyncio.Lock()
        self.scheduler = AsyncIOScheduler(timezone=TZ)

    def login(self):
        try:
            # First try loading saved session
            if SESSION_FILE.exists():
                log.info("Loading session from session.json...")
                try:
                    self.cl.load_settings(SESSION_FILE)
                    self.cl.get_timeline_feed()
                    log.info("Successfully authenticated via session file!")
                    return True
                except Exception as ex:
                    log.warning("Saved session is invalid or expired: %s", ex)

            # Fallback to direct credentials login
            log.info("Performing fresh login with username: %s", IG_USERNAME)
            self.cl.login(IG_USERNAME, IG_PASSWORD)
            self.cl.dump_settings(SESSION_FILE)
            log.info("Login successful and session saved!")
            return True

        except BadPassword:
            log.error("❌ Invalid password! Please verify your password.")
            return False
        except TwoFactorRequired:
            log.error("❌ 2FA Required! Instagram is asking for verification code.")
            return False
        except ChallengeRequired:
            log.error("❌ Security Challenge Required! Instagram blocked the IP/Login. Open your Instagram app on phone, log in normally, and tap 'This was me' or solve the captcha.")
            return False
        except Exception as e:
            log.error("❌ Login exception: %s", e)
            return False

    def threads_sync(self):
        try:
            return list(self.cl.direct_threads(amount=MAX_THREADS) or [])
        except Exception as e:
            log.warning("direct_threads fetch warning: %s", e)
            return []

    def send_sync(self, thread_id, text):
        try:
            self.cl.direct_send(text, thread_ids=[thread_id])
            return True
        except Exception as e:
            log.warning("Send message failed [%s]: %s", thread_id, e)
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
            log.info("Welcome sent to @%s in GC: %s", uname, thread_id)
            await asyncio.sleep(SEND_DELAY)

    async def scan(self):
        try:
            threads = await asyncio.to_thread(self.threads_sync)
            for thread in threads:
                tid = self.tid(thread)
                if not tid or not self.is_group(thread):
                    continue
                with self.lock:
                    self.state.setdefault("threads", {})[tid] = int(time.time())
                for item in list(getattr(thread, "items", None) or [])[:25]:
                    if self.join_event(item):
                        for user in self.users_from(item):
                            await self.welcome(tid, user)
            with self.lock:
                save_state(self.state)
        except Exception as e:
            log.warning("Scan loop warning: %s", e)

    async def watcher(self):
        log.info("GC Watcher running | interval=%ss", WATCH_INTERVAL)
        while not self.stop.is_set():
            start = time.monotonic()
            try:
                await self.scan()
            except Exception as e:
                log.error("Watcher error: %s", e)
            
            wait = max(2, WATCH_INTERVAL - (time.monotonic() - start))
            try:
                await asyncio.wait_for(self.stop.wait(), timeout=wait)
            except asyncio.TimeoutError:
                pass

    async def broadcast(self, name):
        if self.broadcast_lock.locked():
            log.warning("%s broadcast skipped: previous one still running", name)
            return
        async with self.broadcast_lock:
            try:
                threads = await asyncio.to_thread(self.threads_sync)
                groups = list(dict.fromkeys(self.tid(t) for t in threads if self.tid(t) and self.is_group(t)))
                log.info("Broadcasting %s to %d GCs...", name, len(groups))
                sent = 0
                for tid in groups:
                    if await asyncio.to_thread(self.send_sync, tid, DAILY[name]):
                        sent += 1
                    await asyncio.sleep(SEND_DELAY)
                log.info("Broadcast %s finished: %d/%d sent.", name, sent, len(groups))
            except Exception as e:
                log.error("Broadcast failed safely: %s", e)

    def schedule(self):
        common = dict(replace_existing=True, coalesce=True, max_instances=1, misfire_grace_time=10)
        jobs = [("morning", 6), ("afternoon", 12), ("evening", 19), ("night", 23)]
        for name, hour in jobs:
            self.scheduler.add_job(self.broadcast, CronTrigger(hour=hour, minute=0, timezone=TZ), args=[name], id=f"daily_{name}", **common)
        self.scheduler.start()

    async def shutdown(self):
        if self.stop.is_set():
            return
        self.stop.set()
        with contextlib.suppress(Exception): 
            self.scheduler.shutdown(wait=False)
        with contextlib.suppress(Exception): 
            save_state(self.state)
        log.info("Bot shut down gracefully.")

    async def run(self):
        while not self.stop.is_set():
            if self.login():
                break
            log.error("Login failed. Retrying login in 60 seconds...")
            await asyncio.sleep(60)

        self.schedule()
        log.info("🔥 STABLE BOT IS 100% ONLINE | %s", TIMEZONE)
        
        watcher_task = asyncio.create_task(self.watcher())
        try:
            await self.stop.wait()
        finally:
            watcher_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watcher_task
            await self.shutdown()


async def main():
    bot = Bot()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(bot.shutdown()))
    
    try:
        await bot.run()
    except Exception as e:
        log.critical("Critical crash prevented: %s", e)


ip __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

