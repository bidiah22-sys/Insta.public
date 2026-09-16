import os
import time
from datetime import datetime
from instagrapi import Client
from instagrapi.exceptions import LoginRequired, ChallengeRequired

# ==================== CONFIGURATION ====================
SESSION_ID = "7207590267%3AaNryD9DukXgCVM%3A17%3AAYl7m4aWJssZGS5RfI22nGseXujfYNcvTPpG4tNWpQ"

BOT_USERNAME = "smw_vyron_bot" # अपना बोट यूजरनेम यहाँ डालें
OWNER_USERNAME = "fx_smw & aat_nnk25"
# =======================================================

def start_bot():
    while True:
        try:
            print("[*] Connecting to Instagram Server via Session ID...")
            cl = Client()
            
            # सेशन आईडी से सुरक्षित लॉगिन
            cl.login_by_sessionid(SESSION_ID)
            print(f"[+] SUCCESS: Bot @{BOT_USERNAME} is LIVE with Ultra Session Safeguard! 🚀")

            seen_message_ids = set()  
            group_members_state = {}  
            ever_seen_members = set()  
            welcomed_recently = {}     
            recent_sent_texts = {}     
            is_first_run = True  

            def safe_send_message(thread_id, text_content):
                current_time = time.time()
                if thread_id in recent_sent_texts:
                    last_text, last_time = recent_sent_texts[thread_id]
                    if last_text == text_content and (current_time - last_time < 20):
                        return 
                
                recent_sent_texts[thread_id] = (text_content, current_time)
                cl.direct_send(text_content, thread_ids=[thread_id])
                time.sleep(3) # सुरक्षित डिले ताकि 403 न आए

            while True:  
                try:  
                    # कम थ्रेड्स फैच करना ताकि लोड कम पड़े
                    threads = cl.direct_threads(amount=2)  

                    for thread in threads:  
                        if not getattr(thread, "is_group", False):  
                            continue  

                        thread_id = thread.id  
                        bot_tag = f"@{BOT_USERNAME.lower()}"  

                        # 1. Admins List Fetching (Strict Verification)
                        gc_admins = []  
                        try:  
                            if hasattr(thread, 'admin_user_ids') and thread.admin_user_ids:  
                                gc_admins = [str(uid) for uid in thread.admin_user_ids]  
                            elif hasattr(thread, 'admin_users') and thread.admin_users:  
                                gc_admins = [str(getattr(admin, 'pk', admin)) for admin in thread.admin_users]  
                        except Exception:  
                            gc_admins = []  

                        # 🛑 अगर जीसी में एडमिन नहीं मिला, तो बोट कोई काम नहीं करेगा!
                        if not gc_admins:
                            continue

                        bot_pk = str(cl.user_id)  
                        users = list(getattr(thread, "users", []) or [])
                        current_members = {str(getattr(u, "pk", "")) for u in users if getattr(u, "pk", None)}  

                        # 2. WELCOME LOGIC  
                        if thread_id in group_members_state:  
                            old_members = group_members_state[thread_id]  
                            newly_joined = current_members - old_members  

                            if newly_joined and not is_first_run:  
                                current_time = time.time()
                                for joined_pk in newly_joined:  
                                    if joined_pk in welcomed_recently and (current_time - welcomed_recently[joined_pk] < 120):
                                        continue
                                    
                                    welcomed_recently[joined_pk] = current_time
                                    user_obj = next((u for u in users if str(getattr(u, "pk", "")) == joined_pk), None)  
                                    if user_obj:  
                                        target_username = getattr(user_obj, "username", "User")  
                                          
                                        welcome_card = (  
                                            f"🦋✨ 𝗪𝗘𝗟𝗖𝗢𝗠𝗘, @{target_username}! ✨🦋\n\n"  
                                            f"🌸 𝗛𝗘𝗬! 𝗚𝗟𝗔𝗗 𝗧𝗢 𝗛𝗔𝗩𝗘 𝗬𝗢𝗨 𝗛𝗘𝗥𝗘 💫\n"  
                                            f"🤝 𝗦𝗧𝗔𝗬 𝗥𝗘𝗦𝗣𝗘𝗖𝗧𝗙𝗨𝗟 • 𝗙𝗢𝗟𝗟𝗢𝗪 𝗧𝗛𝗘 𝗥𝗨𝗟𝗘𝗦\n"  
                                            f"🔥 𝗘𝗡𝗝𝗢𝗬 𝗧𝗛𝗘 𝗚𝗖 & 𝗦𝗧𝗔𝗬 𝗔𝗖𝗧𝗜𝗩𝗘!\n\n"  
                                            f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"  
                                            f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"  
                                        )  
                                        safe_send_message(thread_id, welcome_card)  
                        else:  
                            ever_seen_members.update(current_members)  

                        group_members_state[thread_id] = current_members  

                        # 3. MESSAGE SCANNER & MODERATION  
                        messages = list(getattr(thread, "messages", []) or [])
                        if messages:  
                            last_msg = messages[0]  
                            message_id = str(getattr(last_msg, "id", ""))
                              
                            if message_id and message_id not in seen_message_ids:  
                                seen_message_ids.add(message_id)  
                                  
                                if len(seen_message_ids) > 300:  
                                    seen_message_ids.pop()  

                                text = str(getattr(last_msg, "text", "") or "").strip()  
                                text_lower = text.lower()  
                                sender_id = str(getattr(last_msg, "user_id", ""))  
                                
                                raw_username = "User"
                                try:
                                    if hasattr(last_msg, 'user') and last_msg.user and hasattr(last_msg.user, 'username'):
                                        raw_username = last_msg.user.username
                                    else:
                                        for u in users:
                                            if str(getattr(u, "pk", "")) == sender_id:
                                                raw_username = getattr(u, "username", "User")
                                                break
                                except Exception:
                                    pass

                                sender_username = str(raw_username).lstrip('@')  
                                item_type = str(getattr(last_msg, 'item_type', '') or '')  

                                if sender_id == bot_pk:  
                                    continue  

                                admin_ids_str = {str(x) for x in gc_admins}
                                is_sender_admin = sender_id in admin_ids_str  

                                if not is_sender_admin:  
                                    # लिंक डिटेक्शन  
                                    if any(domain in text_lower for domain in ['http://', 'https://', 'www.', '.com', 't.me', 'instagram.com/']):  
                                        link_msg = f"🚨🔗 𝗛𝗘𝗬 @{sender_username} — 𝗟𝗜𝗡𝗞 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗! 𝗣𝗟𝗘𝗔𝗦𝗘 𝗥𝗘𝗠𝗢𝗩𝗘 𝗜𝗧."  
                                        safe_send_message(thread_id, link_msg)  
                                        continue  

                                    # रील्स डिटेक्शन  
                                    if item_type in ['clip', 'media', 'video', 'visual_media'] or '/reel/' in text_lower:  
                                        reel_msg = f"🚫🎬 𝗥𝗘𝗘𝗟𝗦 / 𝗩𝗜𝗗𝗘𝗢𝗦 𝗔𝗥𝗘 𝗡𝗢𝗧 𝗔𝗟𝗟𝗢𝗪𝗘𝗗 𝗛𝗘𝗥𝗘, @{sender_username}!"  
                                        safe_send_message(thread_id, reel_msg)  
                                        continue  

                                # टैग रिप्लाई  
                                if "@everyone" in text_lower or bot_tag in text_lower:  
                                    response_msg = f"👋 𝗛𝗘𝗟𝗟𝗢 @{sender_username}! 🤖 𝗕𝗢𝗧 𝗜𝗦 𝗔𝗖𝗧𝗜𝗩𝗘 🚀"  
                                    safe_send_message(thread_id, response_msg)  

                    is_first_run = False  

                except (LoginRequired, ChallengeRequired) as session_err:
                    print(f"[-] SESSION EXPIRED / CHECKPOINT CAUGHT: {session_err}")
                    raise session_err # बाहर वाले लूप में भेजकर नया कनेक्शन ट्राई करेगा

                except Exception as inner_e:  
                    error_str = str(inner_e).lower()
                    if "user_has_logged_out" in error_str or "403" in error_str:
                        print(f"[-] CRITICAL SESSION DROP DETECTED: {inner_e}")
                        raise inner_e
                    print(f"[LOOP ERROR] {inner_e}")  
                    time.sleep(25)  

                time.sleep(15)  # लूप गैप ताकि इंस्टाग्राम सेफ रहे

        except Exception as outer_e:  
            print(f"[-] RECONNECTING DUE TO SESSION/ERROR... Waiting 60 seconds: {outer_e}")  
            time.sleep(60)

if __name__ == "__main__":
    start_bot()

