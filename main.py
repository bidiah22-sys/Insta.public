import asyncio, contextlib, json, logging, os, signal, time
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from instagrapi import Client

ROOT = Path(__file__).resolve().parent
USERNAME = os.getenv("IG_USERNAME", "").strip()
PASSWORD = os.getenv("IG_PASSWORD", "")
TIMEZONE = os.getenv("TIMEZONE", "Asia/Kolkata").strip() or "Asia/Kolkata"
WATCH_INTERVAL = max(5, int(os.getenv("WATCH_INTERVAL", "8")))
MAX_THREADS = max(10, int(os.getenv("MAX_THREADS", "100")))
SEND_DELAY = max(0.8, float(os.getenv("SEND_DELAY", "1.5")))
SESSION_FILE = ROOT / os.getenv("IG_SESSION_FILE", "session.json")
STATE_FILE = ROOT / "state.json"
try: TZ = ZoneInfo(TIMEZONE)
except Exception: TIMEZONE, TZ = "Asia/Kolkata", ZoneInfo("Asia/Kolkata")

DEV = "👑 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ @fx_smw"
BOT = "🤖 𝗕𝗢𝗧 ➜ @bot222703"
WELCOME = """🌸✨ 𝗪𝗘𝗟𝗖𝗢𝗠𝗘 𝗧𝗢 𝗚𝗖 ✨🌸

👋 𝗛𝗘𝗬 {mention}, 𝗪𝗘𝗟𝗖𝗢𝗠𝗘! 💗

🔥 𝗚𝗟𝗔𝗗 𝗧𝗢 𝗛𝗔𝗩𝗘 𝗬𝗢𝗨 𝗛𝗘𝗥𝗘!
🤝 𝗝𝗢𝗜𝗡 𝗧𝗛𝗘 𝗩𝗜𝗕𝗘 • 𝗠𝗘𝗘𝗧 𝗡𝗘𝗪 𝗣𝗘𝗢𝗣𝗟𝗘 • 𝗘𝗡𝗝𝗢𝗬 ✨

⚠️ 𝗥𝗘𝗦𝗣𝗘𝗖𝗧 𝗧𝗛𝗘 𝗚𝗖 • 𝗦𝗧𝗔𝗬 𝗔𝗖𝗧𝗜𝗩𝗘 • 𝗞𝗘𝗘𝗣 𝗧𝗛𝗘 𝗩𝗜𝗕𝗘 𝗚𝗢𝗜𝗡𝗚! ❤️‍🔥

🌸 𝗛𝗔𝗩𝗘 𝗙𝗨𝗡 & 𝗘𝗡𝗝𝗢𝗬 𝗧𝗛𝗘 𝗚𝗖! 💫

{dev}
{bot}"""
DAILY = {
"morning":"""🌸✨ 𝗚𝗢𝗢𝗗 𝗠𝗢𝗥𝗡𝗜𝗡𝗚, 𝗚𝗖! ✨🌸\n\n👋 𝗛𝗘𝗬 𝗘𝗩𝗘𝗥𝗬𝗢𝗡𝗘, 𝗥𝗜𝗦𝗘 & 𝗦𝗛𝗜𝗡𝗘! ☀️💗\n\n🚩 𝗝𝗔𝗜 𝗦𝗛𝗥𝗘𝗘 𝗥𝗔𝗠 🙏\n✨ 𝗡𝗘𝗪 𝗗𝗔𝗬 • 𝗡𝗘𝗪 𝗘𝗡𝗘𝗥𝗚𝗬 • 𝗡𝗘𝗪 𝗩𝗜𝗕𝗘!\n\n🔥 𝗦𝗧𝗔𝗬 𝗣𝗢𝗦𝗜𝗧𝗜𝗩𝗘 & 𝗠𝗔𝗞𝗘 𝗜𝗧 𝗖𝗢𝗨𝗡𝗧! 💫\n\n{dev}\n{bot}""",
"afternoon":"""☀️✨ 𝗚𝗢𝗢𝗗 𝗔𝗙𝗧𝗘𝗥𝗡𝗢𝗢𝗡, 𝗚𝗖! ✨☀️\n\n🌸 𝗛𝗘𝗬 𝗘𝗩𝗘𝗥𝗬𝗢𝗡𝗘, 𝗛𝗢𝗪'𝗦 𝗧𝗛𝗘 𝗗𝗔𝗬 𝗚𝗢𝗜𝗡𝗚? 💗\n\n🙏 𝗥𝗔𝗗𝗛𝗘 𝗥𝗔𝗗𝗛𝗘!\n✨ 𝗞𝗘𝗘𝗣 𝗧𝗛𝗘 𝗘𝗡𝗘𝗥𝗚𝗬 𝗛𝗜𝗚𝗛 & 𝗧𝗛𝗘 𝗩𝗜𝗕𝗘 𝗔𝗟𝗜𝗩𝗘! 🔥\n\n💫 𝗘𝗡𝗝𝗢𝗬 𝗧𝗛𝗘 𝗥𝗘𝗦𝗧 𝗢𝗙 𝗬𝗢𝗨𝗥 𝗗𝗔𝗬!\n\n{dev}\n{bot}""",
"evening":"""🌆✨ 𝗚𝗢𝗢𝗗 𝗘𝗩𝗘𝗡𝗜𝗡𝗚, 𝗚𝗖! ✨🌆\n\n👋 𝗛𝗘𝗬 𝗘𝗩𝗘𝗥𝗬𝗢𝗡𝗘! 💗\n🌸 𝗧𝗜𝗠𝗘 𝗧𝗢 𝗨𝗡𝗪𝗜𝗡𝗗 & 𝗘𝗡𝗝𝗢𝗬 𝗧𝗛𝗘 𝗩𝗜𝗕𝗘! ✨\n\n🙏 𝗥𝗔𝗗𝗛𝗘 𝗥𝗔𝗗𝗛𝗘!\n🔥 𝗞𝗘𝗘𝗣 𝗧𝗛𝗘 𝗚𝗖 𝗟𝗜𝗩𝗘 • 𝗞𝗘𝗘𝗣 𝗧𝗛𝗘 𝗩𝗜𝗕𝗘 𝗚𝗢𝗜𝗡𝗚! ❤️‍🔥\n\n💫 𝗛𝗔𝗩𝗘 𝗔 𝗚𝗥𝗘𝗔𝗧 𝗘𝗩𝗘𝗡𝗜𝗡𝗚!\n\n{dev}\n{bot}""",
"night":"""🌙✨ 𝗚𝗢𝗢𝗗 𝗡𝗜𝗚𝗛𝗧, 𝗚𝗖! ✨🌙\n\n💗 𝗛𝗘𝗬 𝗘𝗩𝗘𝗥𝗬𝗢𝗡𝗘, 𝗧𝗜𝗠𝗘 𝗧𝗢 𝗥𝗘𝗦𝗧!\n\n🚩 𝗝𝗔𝗜 𝗦𝗛𝗥𝗘𝗘 𝗥𝗔𝗠 🙏\n✨ 𝗧𝗛𝗔𝗡𝗞𝗦 𝗙𝗢𝗥 𝗔𝗡𝗢𝗧𝗛𝗘𝗥 𝗚𝗥𝗘𝗔𝗧 𝗗𝗔𝗬!\n\n🌸 𝗥𝗘𝗦𝗧 𝗪𝗘𝗟𝗟 • 𝗦𝗧𝗔𝗬 𝗕𝗟𝗘𝗦𝗦𝗘𝗗 • 𝗦𝗘𝗘 𝗬𝗢𝗨 𝗧𝗢𝗠𝗢𝗥𝗥𝗢𝗪! 💫\n\n{dev}\n{bot}"""
}
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("SMW-GC-BOT")

def load_state():
    d={"welcomed":{},"known_threads":{},"last_scan":0}
    try:
        if STATE_FILE.exists(): d.update(json.loads(STATE_FILE.read_text(encoding="utf-8")))
    except Exception as e: log.warning("state.json read failed: %s", e)
    return d

def save_state(s):
    try:
        t=STATE_FILE.with_suffix(".tmp"); t.write_text(json.dumps(s,ensure_ascii=False,indent=2),encoding="utf-8"); t.replace(STATE_FILE)
    except Exception as e: log.warning("state.json save failed: %s", e)

class Bot:
    def __init__(self):
        self.cl=Client(); self.cl.delay_range=[0.5,1.5]; self.state=load_state(); self.stop=asyncio.Event(); self.broadcast_lock=asyncio.Lock(); self.scheduler=AsyncIOScheduler(timezone=TZ)

    def login(self):
        if not USERNAME: raise RuntimeError("IG_USERNAME is missing. Railway → Variables → add IG_USERNAME.")
        if not PASSWORD: raise RuntimeError("IG_PASSWORD is missing. Railway → Variables → add IG_PASSWORD.")
        log.info("IG_USERNAME: OK | IG_PASSWORD: OK")
        if SESSION_FILE.exists():
            try: self.cl.load_settings(SESSION_FILE); log.info("Saved session settings loaded.")
            except Exception as e: log.warning("Session load failed: %s",e)
        try: self.cl.login(USERNAME,PASSWORD)
        except Exception as e: raise RuntimeError("Instagram login failed. Check Railway credentials or Instagram verification/challenge.") from e
        try: self.cl.dump_settings(SESSION_FILE)
        except Exception as e: log.warning("Session save failed: %s",e)
        log.info("Instagram login successful: @%s",USERNAME)

    @staticmethod
    def oid(x):
        v=getattr(x,"id",None) or getattr(x,"pk",None); return str(v) if v is not None else None
    @staticmethod
    def group(t):
        u=getattr(t,"users",None); title=getattr(t,"thread_title",None)
        try:
            if u is not None and len(u)>=2: return True
        except Exception: pass
        return bool(title)
    def threads(self):
        try: return list(self.cl.direct_threads(amount=MAX_THREADS) or [])
        except Exception as e: log.warning("GC fetch failed: %s",e); return []
    def send(self,tid,text):
        try: self.cl.direct_send(text,thread_ids=[tid]); return True
        except Exception as e: log.warning("Send failed | %s | %s",tid,e); return False
    @staticmethod
    def is_event(item):
        typ=str(getattr(item,"item_type","") or "").lower()
        return any(x in typ for x in ("join","add","participant","admin_add"))
    @staticmethod
    def users(item):
        u=getattr(item,"users",None)
        if u: return list(u)
        u=getattr(item,"user",None)
        return [u] if u else []
    async def welcome(self,tid,user):
        uid=self.oid(user); name=getattr(user,"username",None)
        if not uid or not name: return
        key=f"{tid}:{uid}"
        if key in self.state["welcomed"]: return
        text=WELCOME.format(mention=f"@{name}",dev=DEV,bot=BOT)
        if await asyncio.to_thread(self.send,tid,text):
            self.state["welcomed"][key]=int(time.time()); save_state(self.state); log.info("Welcome sent: @%s -> %s",name,tid); await asyncio.sleep(SEND_DELAY)
    async def scan(self):
        ts=await asyncio.to_thread(self.threads)
        self.state["last_scan"]=int(time.time())
        for t in ts:
            tid=self.oid(t)
            if not tid or not self.group(t): continue
            self.state["known_threads"][tid]=int(time.time())
            for item in list(getattr(t,"items",None) or [])[:30]:
                if self.is_event(item):
                    for u in self.users(item): await self.welcome(tid,u)
        save_state(self.state)
    async def watcher(self):
        log.info("GC watcher ONLINE | interval=%ss | max_threads=%s",WATCH_INTERVAL,MAX_THREADS)
        while not self.stop.is_set():
            started=time.monotonic()
            try: await self.scan()
            except Exception as e: log.exception("Watcher error: %s",e)
            wait=max(1,WATCH_INTERVAL-(time.monotonic()-started))
            try: await asyncio.wait_for(self.stop.wait(),timeout=wait)
            except asyncio.TimeoutError: pass
    async def broadcast(self,name):
        if self.broadcast_lock.locked(): log.warning("%s skipped: another broadcast is running",name); return
        async with self.broadcast_lock:
            text=DAILY[name].format(dev=DEV,bot=BOT); ids=[]
            for t in await asyncio.to_thread(self.threads):
                tid=self.oid(t)
                if tid and self.group(t) and tid not in ids: ids.append(tid)
            log.info("%s broadcast started | GCs=%d",name.upper(),len(ids))
            ok=0
            for tid in ids:
                if await asyncio.to_thread(self.send,tid,text): ok+=1
                await asyncio.sleep(SEND_DELAY)
            log.info("%s broadcast finished | sent=%d/%d",name.upper(),ok,len(ids))
    def jobs(self):
        common={"replace_existing":True,"coalesce":True,"max_instances":1,"misfire_grace_time":5}
        for name,h in (("morning",6),("afternoon",12),("evening",19),("night",23)):
            self.scheduler.add_job(self.broadcast,CronTrigger(hour=h,minute=0,timezone=TZ),args=[name],id=name,**common)
    async def status(self):
        while not self.stop.is_set():
            log.info("BOT ONLINE | India time=%s | watcher=%ss",datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S"),WATCH_INTERVAL)
            try: await asyncio.wait_for(self.stop.wait(),timeout=300)
            except asyncio.TimeoutError: pass
    async def shutdown(self):
        if self.stop.is_set(): return
        self.stop.set()
        with contextlib.suppress(Exception): self.scheduler.shutdown(wait=False)
        with contextlib.suppress(Exception): self.cl.dump_settings(SESSION_FILE)
        save_state(self.state)
    async def run(self):
        self.login(); self.jobs(); self.scheduler.start()
        log.info("========================================"); log.info("SMW GC BOT — ONLINE"); log.info("Developer: @fx_smw | Bot: @bot222703"); log.info("Timezone: %s",TIMEZONE); log.info("Daily: 06:00 / 12:00 / 19:00 / 23:00"); log.info("========================================")
        a=asyncio.create_task(self.watcher()); b=asyncio.create_task(self.status())
        try: await self.stop.wait()
        finally:
            a.cancel(); b.cancel(); await asyncio.gather(a,b,return_exceptions=True); await self.shutdown()

async def main():
    bot=Bot(); loop=asyncio.get_running_loop()
    def stop(): asyncio.create_task(bot.shutdown())
    for sig in (signal.SIGINT,signal.SIGTERM):
        with contextlib.suppress(NotImplementedError): loop.add_signal_handler(sig,stop)
    await bot.run()

if __name__=="__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass

