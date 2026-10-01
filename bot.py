import os
import time
import threading
from datetime import datetime
from itertools import cycle

# ==========================================
#          SMW GC TEST AUTOMATION
# ==========================================

BOT_NAME = "GC TARGET BY SMW"
DEVELOPER = "SMW"

# SESSION ID CONFIGURATION
SESSION_ID = os.getenv("INSTAGRAM_SESSION_ID", "").strip()

if SESSION_ID:
    print("✅ Session credential configured")
else:
    print("⚠️ Session ID not configured")

# 20 NAME VARIATIONS
GROUP_NAMES = [
    "SMW",
    "SMW 🚩",
    "SMW OFFICIAL",
    "SMW ⚡",
    "SMW DEVELOPER",
    "SMW GC",
    "SMW TEAM",
    "SMW WORLD",
    "SMW ACTIVE",
    "SMW SYSTEM",
    "SMW NETWORK",
    "SMW PROJECT",
    "SMW FOREVER",
    "SMW COMMUNITY",
    "SMW ORIGINAL",
    "SMW ENTERPRISE",
    "SMW LEGEND",
    "SMW ZONE",
    "SMW UNITED",
    "SMW FINAL"
]

# CUSTOM MESSAGE
CUSTOM_MESSAGE = """
╔══════════════════════════════════════════╗

          ⚡ 𝗚𝗖 𝗧𝗔𝗥𝗚𝗘𝗧 𝗕𝗬 𝗦𝗠𝗪 ⚡

╚══════════════════════════════════════════╝























































































       𝗡𝗘𝗩𝗘𝗥 𝗠𝗘𝗘𝗧 𝗠𝗘 𝗔𝗚𝗔𝗜𝗡.

























          👨‍💻 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 : 𝗦𝗠𝗪

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

# SETTINGS
INTERVAL = max(1, int(os.getenv("INTERVAL_SECONDS", "10")))
MAX_MESSAGES = max(1, int(os.getenv("MAX_MESSAGES", "20")))

stop_event = threading.Event()
name_cycle = cycle(GROUP_NAMES)


def show_banner():
    print("=" * 50)
    print("        SMW GC TEST RUNNER")
    print("=" * 50)
    print(f"BOT       : {BOT_NAME}")
    print(f"DEVELOPER : {DEVELOPER}")
    print(f"NAMES     : {len(GROUP_NAMES)}")
    print(f"INTERVAL  : {INTERVAL}s")
    print(f"LIMIT     : {MAX_MESSAGES}")
    print("MODE      : SIMULATION")
    print("=" * 50)


def start_bot():
    show_banner()

    for count in range(1, MAX_MESSAGES + 1):

        if stop_event.is_set():
            break

        current_name = next(name_cycle)

        print(f"\n[{datetime.now()}]")
        print(f"NAME PREVIEW: {current_name}")
        print(f"MESSAGE PREVIEW: {count}/{MAX_MESSAGES}")
        print(CUSTOM_MESSAGE, flush=True)

        if count < MAX_MESSAGES:
            stop_event.wait(INTERVAL)

    print("\nSMW TEST RUNNER STOPPED")


def main():
    print("1. START")
    print("2. STOP")
    print("3. EXIT")

    choice = input("Select: ").strip()

    if choice == "1":
        stop_event.clear()
        start_bot()

    elif choice == "2":
        stop_event.set()
        print("STOP REQUESTED")

    else:
        print("EXIT")


if __name__ == "__main__":
    main()
