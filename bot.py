import os
import time
from instagrapi import Client

# ==========================================
# ⚙️ RAILWAY ENV CONFIGURATION & SAFETY CHECK
# ==========================================
BOT_USERNAME = os.getenv("BOT_USERNAME") or os.getenv("INSTA_USERNAME")
BOT_PASSWORD = os.getenv("BOT_PASSWORD") or os.getenv("INSTA_PASSWORD")
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "fx_smw")

# सेफ्टी चेक: अगर रेलवे में डिटेल्स नहीं डाली हैं तो साफ़ एरर दिखेगा
if not BOT_USERNAME or not BOT_PASSWORD:
    print("[-] CRITICAL ERROR: BOT_USERNAME or BOT_PASSWORD is missing in Railway Variables!")
    exit(1)

cl = Client()
cl.delay_range = [1, 2]

print(f"[*] Connecting to Instagram as @{BOT_USERNAME}...")

login_success = False
try:
    cl.login(BOT_USERNAME, BOT_PASSWORD)
    print(f"[+] SUCCESS: Bot @{BOT_USERNAME} is LIVE at Maximum Speed! 🚀")
    login_success = True
except Exception as e:
    print(f"[-] LOGIN ERROR: {e}")
