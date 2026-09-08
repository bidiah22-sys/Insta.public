import os
import time
from datetime import datetime
from instagrapi import Client

# API & Credentials Configuration
BOT_USERNAME = os.getenv("BOT_USERNAME") or "bot222703"
OWNER_USERNAME = "fx_smw"

# ==========================================
# यहाँ अपनी लैपटॉप से निकाली हुई Session ID डाल
# ==========================================
SESSION_ID = "YAHAN_APNI_SESSION_ID_DAL"

def start_bot():
    while True:
        try:
            print("[*] Connecting to Instagram Server via Session ID...")
            cl = Client()
            
            # सेशन आईडी के जरिए डायरेक्ट लॉगिन
            cl.login_by_sessionid(SESSION_ID)
            
            print(f"[+] SUCCESS: Bot is LIVE with Session ID & Clean Logic! 🚀")

            seen_message_ids = set()  
            group_members_state = {}  
            ever_seen_members = set()  # लाइफटाइम ट्रैक रखने के लिए ताकि वेलकम बैक सही से काम करे  
            is_first_run = True  

            while True:  
                try:  
                    threads = cl.direct_threads(amount=3)  

                    for thread in threads:  
                        if not thread.is_group:  
                            continue  

                        thread_id = thread.id  
                        bot_tag = f"@{BOT_USERNAME.lower()}"  

                        # Admins List Fetching  
                        gc_admins = []  
                        try:  
                            if hasattr(thread, 'admin_user_ids') and thread.admin_user_ids:  
                                gc_admins = [str(uid) for uid in thread.admin_user_ids]  
                            elif hasattr(thread, 'admin_users') and thread.admin_users:  
                                gc_admins = [str(getattr(admin, 'pk', admin)) for admin in thread.admin_users]  
                        except Exception:  
                            gc_admins = []  

                        bot_pk = str(cl.user_id)  
                        current_members = {user.pk for user in thread.users}  

                        # 1. WELCOME & WELCOME BACK LOGIC (SINGLE MESSAGE FIX)  
                        if thread_id in group_members_state:  
                            old_members = group_members_state[thread_id]  
                            newly_joined = current_members - old_members  

                            if newly_joined and not is_first_run:  
                                for joined_pk in newly_joined:  
                                    user_obj = next((u for u in thread.users if u.pk == joined_pk), None)  
                                    if user_obj:  
                                        target_username = user_obj.username  
                                          
                                        # अगर बंदा GC में पहले कभी आ चुका है -> Welcome Back Card  
                                        if joined_pk in ever_seen_members:  
                                            welcome_back_card = (  
                                                f"💫🦋 𝗪𝗘𝗟𝗖𝗢𝗠𝗘 𝗕𝗔𝗖𝗞, @{target_username}! 🦋💫\n\n"  
                                                f"🌷 𝗧𝗛𝗘 𝗚𝗖 𝗙𝗘𝗟𝗧 𝗬𝗢𝗨𝗥 𝗔𝗕𝗦𝗘𝗡𝗖𝗘 😌\n"  
                                                f"🔥 𝗕𝗔𝗖𝗞 𝗔𝗚𝗔𝗜𝗡 • 𝗦𝗧𝗔𝗬 𝗔𝗖𝗧𝗜𝗩𝗘\n"  
                                                f"📜 𝗙𝗢𝗟𝗟𝗢𝗪 𝗧𝗛𝗘 𝗥𝗨𝗟𝗘𝗦 & 𝗘𝗡𝗝𝗢𝗬!\n\n"  
                                                f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"  
                                                f"👨‍💻 𝗗𝗘𝗩 ➜ @{OWNER_USERNAME}"  
                                            )  
                                            cl.direct_send(welcome_back_card, thread_ids=[thread_id])  
                                            time.sleep(1)  
                                          
                                        # अगर पहली बार आया है -> Fresh Welcome Card  
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
                                            cl.direct_send(welcome_card, thread_ids=[thread_id])  
                                            time.sleep(1)  
                        else:  
                            # पहली बार बोट शुरू होने पर पुराने मेंबर्स को एवर-सीन लिस्ट में डाल दो  
                            ever_seen_members.update(current_members)  

                        group_members_state[thread_id] = current_members  

                        # 2. MESSAGE SCANNER & MODERATION  
                        if thread.messages:  
                            last_msg = thread.messages[0]  
                              
                            if last_msg.id not in seen_message_ids:  
                                seen_message_ids.add(last_msg.id)  
                                  
                                if len(seen_message_ids) > 300:  
                                    seen_message_ids.pop()  

                                text = str(last_msg.text or "").strip()  
                                text_lower = text.lower()  
                                sender_id = str(last_msg.user_id)  
                                raw_username = last_msg.user.username if hasattr(last_msg, 'user') and last_msg.user and hasattr(last_msg.user, 'username') else 'User'  
                                sender_username = raw_username.lstrip('@')  
                                item_type = getattr(last_msg, 'item_type', '')  

                                if sender_id == bot_pk:  
                                    continue  

                                is_sender_admin = (sender_id in gc_admins) if gc_admins else False  

                                # नॉन-एडमिन मॉडेशन और प्रॉपर कार्ड ट्रिगर्स  
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
                                        cl.direct_send(link_msg, thread_ids=[thread_id])  
                                        time.sleep(1)  
                                        continue  

                                    # रील्स / वीडियो डिटेक्शन  
                                    if item_type in ['clip', 'media', 'video', 'visual_media'] or '/reel/' in text_lower or 'video' in item_type:  
                                        reel_msg = (  
                                            f"🚫🎬 𝗥𝗘𝗘𝗟𝗦 𝗡𝗢𝗧 𝗔𝗟𝗟𝗢𝗪𝗘𝗗!\n\n"  
                                            f"👤 @{sender_username}\n\n"  
                                            f"⚠️ 𝗥𝗘𝗘𝗟𝗦 / 𝗩𝗜𝗗𝗘𝗢𝗦 𝗔𝗥𝗘 𝗡𝗢𝗧 𝗔𝗟𝗟𝗢𝗪𝗘𝗗 𝗛𝗘𝗥𝗘.\n\n"  
                                            f"🛑 𝗣𝗟𝗘𝗔𝗦𝗘 𝗗𝗢𝗡'𝗧 𝗥𝗘𝗣𝗘𝗔𝗧!\n\n"  
                                            f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"  
                                            f"👨‍💻 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ @{OWNER_USERNAME}"  
                                        )  
                                        cl.direct_send(reel_msg, thread_ids=[thread_id])  
                                        time.sleep(1)  
                                        continue  

                                    # गाली / 18+ कंटेंट डिटेक्शन  
                                    restricted_words = ['18+', 'adult', 'sex', 'xxx', 'porn', 'nude', 'gali', 'bhadve', 'chutiya', 'madarchod', 'behenchod']  
                                    if any(word in text_lower for word in restricted_words):  
                                        # एडमिन यूजरनेम निकालना  
                                        admin_tag_str = "@ADMIN"  
                                        if gc_admins:  
                                            for u in thread.users:  
                                                if str(u.pk) in gc_admins and str(u.pk) != bot_pk:  
                                                    admin_tag_str = f"@{u.username}"  
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
                                        cl.direct_send(adult_msg, thread_ids=[thread_id])  
                                        time.sleep(1)  
                                        continue  

                                # 3. @everyone या @bot टैग करने पर रिप्लाई  
                                if "@everyone" in text_lower or bot_tag in text_lower:  
                                    response_msg = (  
                                        f"👋 𝗛𝗘𝗟𝗟𝗢 @{sender_username}!\n\n"  
                                        f"🤖 𝗕𝗢𝗧 𝗜𝗦 𝗔𝗖𝗧𝗜𝗩𝗘 𝗔𝗡𝗗 𝗠𝗔𝗡𝗔𝗚𝗜𝗡𝗚 𝗧𝗛𝗘 𝗚𝗖 𝗦𝗠𝗢𝗢𝗧𝗛𝗟𝚈. 🚀\n\n"  
                                        f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"  
                                        f"👨‍💻 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ @{OWNER_USERNAME}"  
                                    )  
                                    cl.direct_send(response_msg, thread_ids=[thread_id])  
                                    time.sleep(1)  

                    is_first_run = False  

                except Exception as inner_e:  
                    print(f"[LOOP ERROR] {inner_e}")  

                time.sleep(2)  

        except Exception as outer_e:  
            print(f"[-] RECONNECTING... Error: {outer_e}")  
            time.sleep(10)

if __name__ == "__main__":
    start_bot()

