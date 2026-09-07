import asyncio
import json
import logging
import os
import signal
from pathlib import Path
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from instagrapi import Client

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("gc-bot")

SESSION_FILE = os.getenv("IG_SESSION_FILE", "session.json")
STATE_FILE = "state.json"
WATCH_INTERVAL = max(3, int(os.getenv("WATCH_INTERVAL", "5")))
TIMEZONE = os.getenv("TIMEZONE", "Asia/Kolkata")
BOT_USERNAME = os.getenv("BOT_USERNAME", "@bot222703")
DEVELOPER_USERNAME = os.getenv("DEVELOPER_USERNAME", "@fx_smw")

WELCOME = """🌸✨ 𝗪𝗘𝗟𝗖𝗢𝗠𝗘 𝗧𝗢 𝗚𝗖 ✨🌸

👋 𝗛𝗘𝗬 {mention}, 𝗪𝗘𝗟𝗖𝗢𝗠𝗘! 💗

🔥 𝗚𝗟𝗔𝗗 𝗧𝗢 𝗛𝗔𝗩𝗘 𝗬𝗢𝗨 𝗛𝗘𝗥𝗘!
🤝 𝗝𝗢𝗜𝗡 𝗧𝗛𝗘 𝗩𝗜𝗕𝗘 • 𝗠𝗘𝗘𝗧 𝗡𝗘𝗪 𝗣𝗘𝗢𝗣𝗟𝗘 • 𝗘𝗡𝗝𝗢𝗬 ✨

⚠️ 𝗥𝗘𝗦𝗣𝗘𝗖𝗧 𝗧𝗛𝗘 𝗚𝗖 • 𝗦𝗧𝗔𝗬 𝗔𝗖𝗧𝗜𝗩𝗘 • 𝗞𝗘𝗘𝗣 𝗧𝗛𝗘 𝗩𝗜𝗕𝗘 𝗚𝗢𝗜𝗡𝗚! ❤️‍🔥

🌸 𝗛𝗔𝗩𝗘 𝗙𝗨𝗡 & 𝗘𝗡𝗝𝗢𝗬 𝗧𝗛𝗘 𝗚𝗖! 💫

👑 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ {developer}
🤖 𝗕𝗢𝗧 ➜ {bot}"""

DAILY = {
    "morning": """🌸✨ 𝗚𝗢𝗢𝗗 𝗠𝗢𝗥𝗡𝗜𝗡𝗚, 𝗚𝗖! ✨🌸

👋 𝗛𝗘𝗬 𝗘𝗩𝗘𝗥𝗬𝗢𝗡𝗘, 𝗥𝗜𝗦𝗘 & 𝗦𝗛𝗜𝗡𝗘! ☀️💗
🚩 𝗝𝗔𝗜 𝗦𝗛𝗥𝗘𝗘 𝗥𝗔𝗠 🙏

🔥 𝗡𝗘𝗪 𝗗𝗔𝗬 • 𝗡𝗘𝗪 𝗘𝗡𝗘𝗥𝗚𝗬 • 𝗡𝗘𝗪 𝗩𝗜𝗕𝗘! ✨

👑 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ {developer}
🤖 𝗕𝗢𝗧 ➜ {bot}""",
    "afternoon": """☀️✨ 𝗚𝗢𝗢𝗗 𝗔𝗙𝗧𝗘𝗥𝗡𝗢𝗢𝗡, 𝗚𝗖! ✨☀️

🌸 𝗛𝗘𝗬 𝗘𝗩𝗘𝗥𝗬𝗢𝗡𝗘, 𝗛𝗢𝗪'𝗦 𝗧𝗛𝗘 𝗗𝗔𝗬 𝗚𝗢𝗜𝗡𝗚? 💗
🙏 𝗥𝗔𝗗𝗛𝗘 𝗥𝗔𝗗𝗛𝗘!

✨ 𝗞𝗘𝗘𝗣 𝗧𝗛𝗘 𝗘𝗡𝗘𝗥𝗚𝗬 𝗛𝗜𝗚𝗛 & 𝗧𝗛𝗘 𝗩𝗜𝗕𝗘 𝗔𝗟𝗜𝗩𝗘! 🔥

👑 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ {developer}
🤖 𝗕𝗢𝗧 ➜ {bot}""",
    "evening": """🌆✨ 𝗚𝗢𝗢𝗗 𝗘𝗩𝗘𝗡𝗜𝗡𝗚, 𝗚𝗖! ✨🌆

👋 𝗛𝗘𝗬 𝗘𝗩𝗘𝗥𝗬𝗢𝗡𝗘! 💗
🌸 𝗧𝗜𝗠𝗘 𝗧𝗢 𝗨𝗡𝗪𝗜𝗡𝗗 & 𝗘𝗡𝗝𝗢𝗬 𝗧𝗛𝗘 𝗩𝗜𝗕𝗘! ✨
🙏 𝗥𝗔𝗗𝗛𝗘 𝗥𝗔𝗗𝗛𝗘!

🔥 𝗞𝗘𝗘𝗣 𝗧𝗛𝗘 𝗚𝗖 𝗟𝗜𝗩𝗘 • 𝗞𝗘𝗘𝗣 𝗧𝗛𝗘 𝗩𝗜𝗕𝗘 𝗚𝗢𝗜𝗡𝗚! ❤️‍🔥

👑 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ {developer}
🤖 𝗕𝗢𝗧 ➜ {bot}""",
    "night": """🌙✨ 𝗚𝗢𝗢𝗗 𝗡𝗜𝗚𝗛𝗧, 𝗚𝗖! ✨🌙

💗 𝗛𝗘𝗬 𝗘𝗩𝗘𝗥𝗬𝗢𝗡𝗘, 𝗧𝗜𝗠𝗘 𝗧𝗢 𝗥𝗘𝗦𝗧!
🚩 𝗝𝗔𝗜 𝗦𝗛𝗥𝗘𝗘 𝗥𝗔𝗠 🙏

✨ 𝗧𝗛𝗔𝗡𝗞𝗦 𝗙𝗢𝗥 𝗔𝗡𝗢𝗧𝗛𝗘𝗥 𝗚𝗥𝗘𝗔𝗧 𝗗𝗔𝗬!
🌸 𝗥𝗘𝗦𝗧 𝗪𝗘𝗟𝗟 • 𝗦𝗧𝗔𝗬 𝗕𝗟𝗘𝗦𝗦𝗘𝗗 • 𝗦𝗘𝗘 𝗬𝗢𝗨 𝗧𝗢𝗠𝗢𝗥𝗥𝗢𝗪! 💫

👑 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ {developer}
🤖 𝗕𝗢𝗧 ➜ {bot}""",
}

def load_state() -> dict[str, Any]:
    p = Path(STATE_FILE)
    if not p.exists():
        return {"welcomed": {}, "last_seen": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        log.warning("Could not read state.json; starting fresh.")
        return {"welcomed": {}, "last_seen": {}}

def save_state(state: dict[str, Any]) -> None:
    tmp = Path(STATE_FILE + ".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(STATE_FILE)

class GCBot:
    def __init__(self):
        self.cl = Client()
        self.cl.delay_range = [0.5, 1.5]
        self.state = load_state()
        self.stop_event = asyncio.Event()
        self.known_threads: set[str] = set()
        self.started = False

    def login(self):
        username = os.getenv("IG_USERNAME")
        password = os.getenv("IG_PASSWORD")
        if not username or not password:
            raise RuntimeError("IG_USERNAME and IG_PASSWORD are required unless a usable session is restored.")

        if Path(SESSION_FILE).exists():
            try:
                self.cl.load_settings(SESSION_FILE)
                self.cl.login(username, password)
                log.info("Instagram session restored and login completed.")
                return
            except Exception as exc:
                log.warning("Session restore failed: %s; trying fresh login.", exc)

        self.cl.login(username, password)
        self.cl.dump_settings(SESSION_FILE)
        log.info("Fresh login completed; session saved.")

    def threads(self):
        # Private/direct threads visible to the authenticated account.
        return self.cl.direct_threads(amount=100)

    def is_group(self, thread) -> bool:
        return bool(getattr(thread, "users", None)) and len(thread.users) > 2

    def thread_key(self, thread) -> str:
        return str(getattr(thread, "id", ""))

    def send(self, thread_id: str, text: str):
        self.cl.direct_send(text, thread_ids=[thread_id])

    def mention(self, user) -> str:
        username = getattr(user, "username", None) or "user"
        return "@" + username

    def detect_new_participants(self, thread):
        items = getattr(thread, "items", None) or []
        found = []
        for item in items[:30]:
            users = getattr(item, "users", None) or []
            item_type = str(getattr(item, "item_type", "")).lower()
            if not users:
                continue
            if any(k in item_type for k in ("add", "join", "participant")):
                for user in users:
                    uid = str(getattr(user, "pk", getattr(user, "id", "")))
                    if uid:
                        found.append((uid, user))
        return found

    def process_thread(self, thread):
        if not self.is_group(thread):
            return

        tid = self.thread_key(thread)
        if not tid:
            return

        # Fetch current thread data so system events are available.
        try:
            fresh = self.cl.direct_thread(tid)
        except Exception as exc:
            log.debug("Thread refresh failed %s: %s", tid, exc)
            return

        for uid, user in self.detect_new_participants(fresh):
            key = f"{tid}:{uid}"
            if key in self.state["welcomed"]:
                continue
            text = WELCOME.format(
                mention=self.mention(user),
                developer=DEVELOPER_USERNAME,
                bot=BOT_USERNAME,
            )
            try:
                self.send(tid, text)
                self.state["welcomed"][key] = True
                save_state(self.state)
                log.info("Welcomed %s in GC %s", uid, tid)
            except Exception as exc:
                log.warning("Welcome send failed in %s: %s", tid, exc)

    def broadcast_daily(self, name: str):
        text = DAILY[name].format(developer=DEVELOPER_USERNAME, bot=BOT_USERNAME)
        try:
            threads = self.threads()
        except Exception as exc:
            log.warning("Could not list threads for %s: %s", name, exc)
            return

        for thread in threads:
            if not self.is_group(thread):
                continue
            tid = self.thread_key(thread)
            if not tid:
                continue
            try:
                self.send(tid, text)
                log.info("Sent %s message to GC %s", name, tid)
            except Exception as exc:
                log.warning("Daily %s send failed in %s: %s", name, tid, exc)

    async def watcher(self):
        log.info("GC watcher started; interval=%ss", WATCH_INTERVAL)
        while not self.stop_event.is_set():
            try:
                threads = await asyncio.to_thread(self.threads)
                for thread in threads:
                    await asyncio.to_thread(self.process_thread, thread)
            except Exception as exc:
                log.warning("Watcher cycle error: %s", exc)
            try:
                await asyncio.wait_for(self.stop_event.wait(), timeout=WATCH_INTERVAL)
            except asyncio.TimeoutError:
                pass

    def setup_scheduler(self):
        scheduler = AsyncIOScheduler(timezone=TIMEZONE)
        scheduler.add_job(lambda: self.broadcast_daily("morning"),
                          CronTrigger(hour=6, minute=0, timezone=TIMEZONE),
                          id="morning", replace_existing=True, coalesce=True,
                          misfire_grace_time=30)
        scheduler.add_job(lambda: self.broadcast_daily("afternoon"),
                          CronTrigger(hour=12, minute=0, timezone=TIMEZONE),
                          id="afternoon", replace_existing=True, coalesce=True,
                          misfire_grace_time=30)
        scheduler.add_job(lambda: self.broadcast_daily("evening"),
                          CronTrigger(hour=19, minute=0, timezone=TIMEZONE),
                          id="evening", replace_existing=True, coalesce=True,
                          misfire_grace_time=30)
        scheduler.add_job(lambda: self.broadcast_daily("night"),
                          CronTrigger(hour=23, minute=0, timezone=TIMEZONE),
                          id="night", replace_existing=True, coalesce=True,
                          misfire_grace_time=30)
        scheduler.start()
        return scheduler

    async def run(self):
        self.login()
        scheduler = self.setup_scheduler()
        watcher_task = asyncio.create_task(self.watcher())
        self.started = True
        log.info("GC Bot is running.")
        try:
            await self.stop_event.wait()
        finally:
            scheduler.shutdown(wait=False)
            watcher_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watcher_task
            try:
                self.cl.logout()
            except Exception:
                pass

    def stop(self, *_):
        self.stop_event.set()

if __name__ == "__main__":
    import contextlib
    bot = GCBot()
    signal.signal(signal.SIGINT, bot.stop)
    signal.signal(signal.SIGTERM, bot.stop)
    asyncio.run(bot.run())

