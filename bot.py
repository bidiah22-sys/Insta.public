import os
import sys
import time
import signal
import logging
import threading

from datetime import datetime
from itertools import cycle


# =====================================================
#                  SMW GC AUTOMATION
# =====================================================

BOT_NAME = "GC TARGET BY SMW"
DEVELOPER = "SMW"
VERSION = "2.0"


# =====================================================
#                  CONFIGURATION
# =====================================================

# Credential presence check only.
# This test runner does not authenticate to Instagram.
SESSION_ID = os.getenv("INSTAGRAM_SESSION_ID", "10291668651%3Atlp22DycYZhkIs%3A6%3AAYm32I7ZQR3u8kcB5Qt961mSyaUNCG9bMDLYGxcnRw").strip()

INTERVAL = max(
    1,
    int(os.getenv("INTERVAL_SECONDS", "10"))
)

MAX_MESSAGES = max(
    1,
    int(os.getenv("MAX_MESSAGES", "20"))
)


# =====================================================
#                  LOGGING SYSTEM
# =====================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger("SMW")


# =====================================================
#                  NAME VARIATIONS
# =====================================================

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


# =====================================================
#                  CUSTOM MESSAGE
# =====================================================

CUSTOM_MESSAGE = """
╔══════════════════════════════════════════╗

          ⚡ 𝗚𝗖 𝗧𝗔𝗥𝗚𝗘𝗧 𝗕𝗬 𝗦𝗠𝗪 ⚡

╚══════════════════════════════════════════╝























































































       𝗡𝗘𝗩𝗘𝗥 𝗠𝗘𝗘𝗧 𝗠𝗘 𝗔𝗚𝗔𝗜𝗡.

























          👨‍💻 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 : 𝗦𝗠𝗪

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""


# =====================================================
#                  GLOBAL STATE
# =====================================================

stop_event = threading.Event()

name_cycle = cycle(GROUP_NAMES)

message_count = 0


# =====================================================
#                  STARTUP BANNER
# =====================================================

def show_banner():

    print("\n")
    print("=" * 55)
    print("              SMW GC TEST RUNNER")
    print("=" * 55)

    print(f"BOT NAME       : {BOT_NAME}")
    print(f"DEVELOPER      : {DEVELOPER}")
    print(f"VERSION        : {VERSION}")
    print(f"NAME VARIANTS  : {len(GROUP_NAMES)}")
    print(f"INTERVAL       : {INTERVAL} seconds")
    print(f"MAX MESSAGES   : {MAX_MESSAGES}")
    print(f"SESSION CONFIG : {'PRESENT' if SESSION_ID else 'NOT SET'}")
    print("MODE           : SIMULATION")

    print("=" * 55)
    print("\n")


# =====================================================
#                  MESSAGE PREVIEW
# =====================================================

def show_message(number):

    global message_count

    if stop_event.is_set():
        return

    current_name = next(name_cycle)

    message_count += 1

    logger.info(
        "Preview %s/%s",
        number,
        MAX_MESSAGES
    )

    logger.info(
        "Name variation: %s",
        current_name
    )

    print("\n")
    print(CUSTOM_MESSAGE)
    print("\n")

    logger.info("Preview completed")


# =====================================================
#                  MAIN RUNNER
# =====================================================

def start_bot():

    show_banner()

    logger.info("SMW runner started")

    try:

        for count in range(1, MAX_MESSAGES + 1):

            if stop_event.is_set():
                break

            show_message(count)

            if count < MAX_MESSAGES:

                logger.info(
                    "Waiting %s seconds",
                    INTERVAL
                )

                stop_event.wait(INTERVAL)

    except KeyboardInterrupt:

        logger.warning("Manual shutdown requested")

    except Exception:

        logger.exception("Unexpected runner error")

    finally:

        logger.info("SMW runner stopped")

        logger.info(
            "Total previews: %s",
            message_count
        )


# =====================================================
#                  SHUTDOWN HANDLER
# =====================================================

def shutdown_handler(signum, frame):

    logger.warning(
        "Shutdown signal received: %s",
        signum
    )

    stop_event.set()


# =====================================================
#                  APPLICATION ENTRY
# =====================================================

def main():

    signal.signal(
        signal.SIGTERM,
        shutdown_handler
    )

    signal.signal(
        signal.SIGINT,
        shutdown_handler
    )

    start_bot()


if __name__ == "__main__":

    main()
