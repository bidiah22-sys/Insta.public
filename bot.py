import os
import time
from datetime import datetime
from instagrapi import Client
from instagrapi.exceptions import LoginRequired, ChallengeRequired

# ==================== CONFIGURATION ====================
SESSION_ID = os.getenv("INSTA_SESSION_ID") or "YAHAN_APNI_SESSION_ID_PASTE_KAR_DENA"

BOT_USERNAME = "smw_vyron_bot" # अपना बोट यूजरनेम यहाँ डालें
OWNER_USERNAME = "fx_smw & aat_nnk25"

# कॉल रिमाइंडर का समय: 1 घंटा (3600 सेकंड)
CALL_REMINDER_INTERVAL = 3600 
# =======================================================

def start_bot():
    while True:
        try:
            print("[*] Connecting to Instagram Server via Session ID...")
            cl = Client()
            
            # सेशन आईडी से सुरक्षित लॉगिन
            cl.login_by_sessionid(SESSION_ID)
            print(f"[+] SUCCESS: Bot @{BOT_USERNAME} is LIVE with Fixed Global Scope & 1-Hour Call Reminders! 🚀")

            seen_message_ids = set()  
            group_members_state = {}  
            ever_seen_members = set()  
            welcomed_recently = {}     
            recent_sent_texts = {}     
            last_call_broadcast = {}   
            
            # विशेस के लिए वेरिएबल्स
            last_morning_wish_date = ""
            last_night_wish_date = ""
            
            is_first_run = True  

            def safe_send_message(thread_id, text_content):
                current_time = time.time()
                if thread_id in recent_sent_texts:
                    last_text, last_time = recent_sent_texts[thread_id]
                    if last_text == text_content and (current_time - last_time < 10):
                        return 
                
                recent_sent_texts[thread_id] = (text_content, current_time)
                cl.direct_send(text_content, thread_ids=[thread_id])
                time.sleep(1)

            while True:  
                try:  
                    threads = cl.direct_threads(amount=2)  
                    current_time_loop = time.time()
                    
                    now = datetime.now()
                    current_hour = now.hour
                    current_date_str = now.strftime("%Y-%m-%d")

                    for thread in threads:  
                        if not getattr(thread, "is_group", False):  
                            continue  

                        thread_id = thread.id  
                        bot_tag = f"@{BOT_USERNAME.lower()}"  

                        # 1. Admins List Fetching
                        gc_admins = []  
                        try:  
                            if hasattr(thread, 'admin_user_ids') and thread.admin_user_ids:  
                                gc_admins = [str(uid) for uid in thread.admin_user_ids]  
                            elif hasattr(thread, 'admin_users') and thread.admin_users:  
                                gc_admins = [str(getattr(admin, 'pk', admin)) for admin in thread.admin_users]  
                        except Exception:  
                            gc_admins = []  

                        if not gc_admins:
                            continue

                        bot_pk = str(cl.user_id)  
                        users = list(getattr(thread, "users", []) or [])
                        current_members = {str(getattr(u, "pk", "")) for u in users if getattr(u, "pk", None)}  

                        # 2. MORNING & NIGHT WISH SYSTEM (एरर पूरी तरह फिक्स)
                        if current_hour == 6 and last_morning_wish_date != current_date_str:
                            last_morning_wish_date = current_date_str
                            morning_card = (
                                f"🌸✨ **𝗥𝗔𝗗𝗛𝗘 𝗥𝗔𝗗𝗛𝗘 • JAI SHRI RAM!** ✨🌸\n\n"
                                f"🌅 𝗚𝗢𝗢𝗗 𝗠𝗢𝗥𝗡𝗜𝗡𝗚 𝗚𝗖 𝗙𝗔𝗠𝗜𝗟𝗬! ☕💫\n"
                                f"🙏 𝗛𝗔𝗩𝗘 𝗔 𝗕𝗟𝗘𝗦𝗦𝗘𝗗, 𝗛𝗔𝗣𝗣𝗬 & 𝗔𝗖𝗧𝗜𝗩𝗘 𝗗𝗔𝗬 𝗔𝗛𝗘𝗔𝗗!\n"
                                f"🔥 𝗟𝗘𝗧'𝗦 𝗦𝗧𝗔𝗥𝗧 𝗧𝗛𝗘 𝗗𝗔𝗬 𝗪𝗜𝗧𝗛 𝗚𝗢𝗢𝗗 𝗩𝗜𝗕𝗦!\n\n"
                                f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
                                f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
                            )
                            safe_send_message(thread_id, morning_card)

                        elif current_hour == 23 and last_night_wish_date != current_date_str:
                            last_night_wish_date = current_date_str
                            night_card = (
                                f"🌙💤 **𝗚𝗢𝗢𝗗 𝗡𝗜𝗚𝗛𝗧, 𝗚𝗖 𝗙𝗔𝗠𝗜𝗟𝗬!** 🌌✨\n\n"
                                f"🛌 𝗧𝗜𝗠𝗘 𝗧𝗢 𝗥𝗘𝗦𝗧 & 𝗥𝗘𝗖𝗛𝗔𝗥𝗚𝗘 𝗙𝗢𝗥 𝗧𝗢𝗠𝗢𝗥𝗥𝗢𝗪!\n"
                                f"🌟 𝗦𝗟𝗘𝗘𝗣 𝗧𝗜𝗚𝗛𝗧, 𝗦𝗪𝗘𝗘𝗧 𝗗𝗥𝗘𝗔𝗠𝗦 𝗘𝗩𝗘𝗥𝗬𝗢𝗡𝗘!\n\n"
                                f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
                                f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
                            )
                            safe_send_message(thread_id, night_card)

                        # 3. AUTO CALL BROADCAST SYSTEM (हर 1 घंटे में)
                        if thread_id not in last_call_broadcast:
                            last_call_broadcast[thread_id] = current_time_loop
                        
                        if current_time_loop - last_call_broadcast[thread_id] > CALL_REMINDER_INTERVAL:
                            last_call_broadcast[thread_id] = current_time_loop
                            call_broadcast_card = (
                                f"🔥📞 **@EVERYONE • GC CALL ALERT!** 📞🔥\n\n"
                                f"👑 𝗛𝗘𝗬 𝗚𝗨𝗬𝗦, 𝗦𝗧𝗔𝗥𝗧 𝗔 𝗖𝗔𝗟𝗟 𝗢𝗥 𝗝𝗢𝗜𝗡 𝗡𝗢𝗪!\n"
                                f"💬 𝗟𝗘𝗧'𝗦 𝗖𝗛𝗔𝗧, 𝗩𝗜𝗕𝗘 & 𝗛𝗔𝗡𝗚𝗢𝗨𝗧 𝗧𝗢𝗚𝗘𝗧𝗛𝗘𝗥 💫\n\n"
                                f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
                                f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"
                            )
                            safe_send_message(thread_id, call_broadcast_card)

                        # 4. WELCOME & WELCOME BACK LOGIC  
                        if thread_id in group_members_state:  
                            old_members = group_members_state[thread_id]  
                            newly_joined = current_members - old_members  

                            if newly_joined and not is_first_run:  
                                for joined_pk in newly_joined:  
                                    if joined_pk in welcomed_recently and (current_time_loop - welcomed_recently[joined_pk] < 60):
                                        continue
                                    
                                    welcomed_recently[joined_pk] = current_time_loop
                                    user_obj = next((u for u in users if str(getattr(u, "pk", "")) == joined_pk), None)  
                                    if user_obj:  
                                        target_username = getattr(user_obj, "username", "User")  
                                          
                                        if joined_pk in ever_seen_members:  
                                            welcome_back_card = (  
                                                f"💫🦋 𝗪𝗘𝗟𝗖𝗢𝗠𝗘 𝗕𝗔𝗖𝗞, @{target_username}! 🦋💫\n\n"  
                                                f"🌷 𝗧𝗛𝗘 𝗚𝗖 𝗙𝗘𝗟𝗧 𝗬𝗢𝗨𝗥 𝗔𝗕𝗦𝗘𝗡𝗖𝗘 😌\n"  
                                                f"🔥 𝗕𝗔𝗖𝗞 𝗔𝗚𝗔𝗜𝗡 • 𝗦𝗧𝗔𝗬 𝗔𝗖𝗧𝗜𝗩𝗘\n"  
                                                f"📜 𝗙𝗢𝗟𝗟𝗢𝗪 𝗧𝗛𝗘 𝗥𝗨𝗟𝗘𝗦 & 𝗘𝗡𝗝𝗢𝗬!\n\n"  
                                                f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"  
                                                f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"  
                                            )  
                                            safe_send_message(thread_id, welcome_back_card)  
                                        else:  
                                            ever_seen_members.add(joined_pk)  
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

                        # 5. FAST MESSAGE SCANNER & MODERATION  
                        messages = list(getattr(thread, "messages", []) or [])
                        if messages:  
                            last_msg = messages[0]  
                            message_id = str(getattr(last_msg, "id", ""))
                              
                            if message_id and message_id not in seen_message_ids:  
                                seen_message_ids.add(message_id)  
                                  
                                if len(seen_message_ids) > 500:  
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
                                        link_msg = (  
                                            f"🚨🔗 𝗛𝗘𝗬 @{sender_username} — 𝗟𝗜𝗡𝗞 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗!\n\n"  
                                            f"⚠️ 𝗨𝗡𝗔𝗨𝗧𝗛𝗢𝗥𝗜𝗭𝗘𝗗 𝗟𝗜𝗡𝗞𝗦 𝗔𝗥𝗘 𝗡𝗢𝗧 𝗔𝗟𝗟𝗢𝗪𝗘𝗗 𝗛𝗘𝗥𝗘.\n"  
                                            f"🛑 𝗣𝗟𝗘𝗔𝗦𝗘 𝗥𝗘𝗠𝗢𝗩𝗘 𝗜𝗧 & 𝗗𝗢𝗡'𝗧 𝗥𝗘𝗣𝗘𝗔𝗧!\n\n"  
                                            f"⚡ 𝗥𝗘𝗣𝗘𝗔𝗧 𝗩𝗜𝗢𝗟𝗔𝗧𝗜𝗢𝗡𝗦 𝗠𝗔𝗬 𝗟𝗘𝗔𝗗 𝗧𝗢 𝗥𝗘𝗠𝗢𝗩𝗔𝗟 🚪\n"  
                                            f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"  
                                        )  
                                        safe_send_message(thread_id, link_msg)  
                                        continue  

                                    # रील्स / वीडियो डिटेक्शन  
                                    if item_type in ['clip', 'media', 'video', 'visual_media'] or '/reel/' in text_lower:  
                                        reel_msg = (  
                                            f"🚫🎬 𝗥𝗘𝗘𝗟𝗦 𝗡𝗢𝗧 𝗔𝗟𝗟𝗢𝗪𝗘𝗗!\n\n"  
                                            f"👤 @{sender_username}\n\n"  
                                            f"⚠️ 𝗥𝗘𝗘𝗟𝗦 / 𝗩𝗜𝗗𝗘𝗢𝗦 𝗔𝗥𝗘 𝗡𝗢𝗧 𝗔𝗟𝗟𝗢𝗪𝗘𝗗 𝗛𝗘𝗥𝗘.\n\n"  
                                            f"🛑 𝗣𝗟𝗘𝗔𝗦𝗘 𝗗𝗢𝗡'𝗧 𝗥𝗘𝗣𝗘𝗔𝗧!\n\n"  
                                            f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"  
                                            f"👨‍💻 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ @{OWNER_USERNAME}"  
                                        )  
                                        safe_send_message(thread_id, reel_msg)  
                                        continue  

                                    # गाली / 18+ कंटेंट डिटेक्शन  
                                    restricted_words = ['18+', 'adult', 'sex', 'xxx', 'porn', 'nude', 'gali', 'bhadve', 'chutiya', 'madarchod', 'behenchod']  
                                    if any(word in text_lower for word in restricted_words):  
                                        admin_tag_str = "@ADMIN"  
                                        if gc_admins:  
                                            for u in users:  
                                                if str(getattr(u, "pk", "")) in admin_ids_str and str(getattr(u, "pk", "")) != bot_pk:  
                                                    admin_tag_str = f"@{getattr(u, 'username', 'Admin')}"  
                                                    break  

                                        adult_msg = (  
                                            f"🚨🛡️ 𝗠𝗢𝗗𝗘𝗥𝗔𝗧𝗜𝗢𝗡 𝗔𝗟𝗘𝗥𝗧!\n\n"  
                                            f"👤 𝗨𝗦𝗘𝗥 ➜ @{sender_username}\n"  
                                            f"🚫 𝗜𝗡𝗔𝗣𝗣𝗥𝗢𝗣𝗥𝗜𝗔𝗧𝗘 𝗠𝗘𝗗𝗜𝗔 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗!\n\n"  
                                            f"⚠️ 𝗧𝗛𝗜𝗦 𝗖𝗢𝗡𝗧𝗘𝗡𝗧 𝗜𝗦 𝗡𝗢𝗧 𝗔𝗟𝗟𝗢𝗪𝗘𝗗 𝗜𝗡 𝗧𝗛𝗜𝗦 𝗚𝗖.\n"  
                                            f"👑 𝗔𝗗𝗠𝗜𝗡 ➜ {admin_tag_str}\n"  
                                            f"🔎 𝗣𝗟𝗘𝗔𝗦𝗘 𝗥𝗘𝗩𝗜𝗘𝗪 & 𝗧𝗔𝗞𝗘 𝗔𝗖𝗧𝗜𝗢𝗡.\n\n"  
                                            f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"  
                                            f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"  
                                        )  
                                        safe_send_message(thread_id, adult_msg)  
                                        continue  

                                # @everyone या @bot टैग करने पर तुरंत रिप्लाई  
                                if "@everyone" in text_lower or bot_tag in text_lower:  
                                    response_msg = (  
                                        f"👋 𝗛𝗘𝗟𝗟𝗢 @{sender_username}!\n\n"  
                                        f"🤖 𝗕𝗢𝗧 𝗜𝗦 𝗔𝗖𝗧𝗜𝗩𝗘 𝗔𝗡𝗗 𝗠𝗔𝗡𝗔𝗚𝗜𝗡𝗚 𝗧𝗛𝗘 𝗚𝗖 𝗦𝗠𝗢𝗢𝗧𝗛𝗟𝚈. 🚀\n\n"  
                                        f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"  
                                        f"👨‍💻 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ @{OWNER_USERNAME}"  
                                    )  
                                    safe_send_message(thread_id, response_msg)  

                    is_first_run = False  

                except (LoginRequired, ChallengeRequired) as session_err:
                    print(f"[-] SESSION EXPIRED / CHECKPOINT CAUGHT: {session_err}")  
                    raise session_err  

                except Exception as inner_e:  
                    error_str = str(inner_e).lower()
                    if "user_has_logged_out" in error_str or "403" in error_str:
                        print(f"[-] CRITICAL SESSION DROP DETECTED: {inner_e}")
                        raise inner_e
                    print(f"[LOOP ERROR] {inner_e}")  
                    time.sleep(10)  

                time.sleep(3)  

        except Exception as outer_e:  
            print(f"[-] RECONNECTING DUE TO SESSION/ERROR... Waiting 30 seconds: {outer_e}")  
            time.sleep(30)

if __name__ == "__main__":
    start_bot()

