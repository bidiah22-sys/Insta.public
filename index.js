import os
import time
from instagrapi import Client

# Railway के वेरिएबल्स से यूजरनेम और पासवर्ड उठाएगा
USERNAME = os.getenv("INSTA_USERNAME")
PASSWORD = os.getenv("INSTA_PASSWORD")

def start_bot():
    print("Connecting to Instagram...")
    cl = Client()
    
    try:
        # सीधा लॉगिन करने की कोशिश करेगा
        cl.login(USERNAME, PASSWORD)
        print("Logged in successfully!")
        
        # यहाँ तेरा बोट का आगे का मॉडération वाला काम चलेगा
        while True:
            print("Bot is active and running smoothly...")
            time.sleep(60)
            
    except Exception as e:
        print(f"LOGIN ERROR: {e}")

if __name__ == "__main__":
    start_bot()

