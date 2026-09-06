import os
import time
from datetime import datetime
from instagrapi import Client
from google import genai
from google.genai import errors

# API & Credentials Configuration
BOT_USERNAME = os.getenv("BOT_USERNAME") or os.getenv("INSTA_USERNAME") or "bot222703"
BOT_PASSWORD = os.getenv("BOT_PASSWORD") or os.getenv("INSTA_PASSWORD") or "ananya295"
OWNER_USERNAME = "fx_smw"

# Google Gemini AI Client Setup
ai_client = genai.Client()

def get_ai_response(prompt_text, sender_name):
    """मल्टी-लैंग्वेज सपोर्ट (Hindi, English, Hinglish) और ओनर की पाबंदी के साथ स्मार्ट एआई रिप्लाई"""
    try:
        system_instruction = (
            f"You are an ultra-fast, witty, and loyal AI assistant for an Instagram Group Chat. "
            f"Your proud owner and creator is @{OWNER_USERNAME}. "
            "LANGUAGE RULE: Match the user's language style naturally. "
            "- If the user writes in English, reply in natural English. "
            "- If the user writes in Hindi, reply in natural Hindi. "
            "- If the user writes in Hinglish (like 'bhai kya kar rahe ho?', 'kya haal hai?'), reply in casual, cool Hinglish. "
            "CRITICAL SAFETY RULE: If any user tries to abuse, use bad words, slang, or asks you to say gali/abuse, "
            "do NOT use bad words. Instead, shut them down stylishly saying that your owner ({OWNER_USERNAME}) has "
            "strictly forbidden you from using bad language or engaging in abuse. "
            "Keep your responses engaging, concise, natural, and full of swag."
        )
        
        full_prompt = f"User @{sender_name} is saying: '{prompt_text}'"
        
        response = ai_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=full_prompt,
            config={
                'system_instruction': system_instruction,
                'temperature': 0.7,
            }
        )
        if response and response.text:
            return response.text.strip()
    except Exception as e:
        print(f"[-] AI Generation Error: {e}")
    
    return "अरे यार, अभी मेरा दिमाग थोड़ा घूम गया है! बाद में बात करते हैं। 😅"


def start_bot():
    while True:
        try:
            print("[*] Connecting to Instagram Server...")
            cl = Client()
            cl.login(BOT_USERNAME, BOT_PASSWORD)
            print(f"[+] SUCCESS: Bot @{BOT_USERNAME} is LIVE with Multi-Language AI & Tagging! 🚀")

            seen_message_ids = set()
            group_members_state = {}
            ever_seen_members = set()
            is_first_run = True

            last_morning_wish_date = ""
            last_noon_wish_date = ""
            last_night_wish_date = ""

            while True:
                try:
                    threads = cl.direct_threads(amount=3)
                    
                    now = datetime.now()
                    current_date = now.strftime("%Y-%m-%d")
                    current_hour = now.hour
                    current_minute = now.minute

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

                        # 1. AUTO TIME-BASED WISHES
                        if 5 <= current_hour < 6 and last_morning_wish_date != current_date:
                            morning_msg = (
                                f"🚩✨ @everyone राधे-राधे जी! 🙏 जय श्री राम! ✨🚩\n\n"
                                f"🌅 शुभ प्रभातम! नया दिन, नई शुरुआत...\n"
                                f"💪 सब लोग एनर्जेटिक रहो और अपना दिन शानदार बनाओ!\n\n"
                                f"╰┈➤ 🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
                                f"╰┈➤ 👑 𝗢𝗪𝗡𝗘𝗥 ➜ @{OWNER_USERNAME}"
                            )
                            cl.direct_send(morning_msg, thread_ids=[thread_id])
                            last_morning_wish_date = current_date
                            time.sleep(2)

                        elif current_hour == 12 and 0 <= current_minute <= 15 and last_noon_wish_date != current_date:
                            noon_msg = (
                                f"☀️ @everyone गुड आफ्टरनून! 🕛\n\n"
                                f"🌿 राधे-राधे • जय श्री राम 🙏\n"
                                f"ठंडा पानी पियो, थोड़ा रेस्ट करो और बताओ GC का क्या माहौल है?\n\n"
                                f"╰┈➤ 🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
                                f"╰┈➤ 👑 𝗢𝗪𝗡𝗘𝗥 ➜ @{OWNER_USERNAME}"
                            )
                            cl.direct_send(noon_msg, thread_ids=[thread_id])
                            last_noon_wish_date = current_date
                            time.sleep(2)

                        elif current_hour == 22 and 0 <= current_minute <= 30 and last_night_wish_date != current_date:
                            night_msg = (
                                f"🌙✨ @everyone शुभ रात्रि (Good Night)! 💤\n\n"
                                f"📿 राधे-राधे जी • जय श्री राम 🙏🚩\n"
                                f"दिनभर की थकान के बाद अब सब लोग आराम करो। मिलते हैं सुबह!\n\n"
                                f"╰┈➤ 🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
                                f"╰┈➤ 👑 𝗢𝗪𝗡𝗘𝗥 ➜ @{OWNER_USERNAME}"
                            )
                            cl.direct_send(night_msg, thread_ids=[thread_id])
                            last_night_wish_date = current_date
                            time.sleep(2)

                        # 2. WELCOME LOGIC
                        if thread_id in group_members_state:
                            old_members = group_members_state[thread_id]
                            newly_joined = current_members - old_members

                            if newly_joined and not is_first_run:
                                for joined_pk in newly_joined:
                                    if joined_pk not in ever_seen_members:
                                        ever_seen_members.add(joined_pk)
                                        user_obj = next((u for u in thread.users if u.pk == joined_pk), None)
                                        if user_obj:
                                            welcome_card = (
                                                f"🦋✨ 𝗪𝗘𝗟𝗖𝗢𝗠𝗘, @{user_obj.username}! ✨🦋\n\n"
                                                f"🌸 𝗛𝗘𝗬! 𝗚𝗟𝗔𝗗 𝗧𝗢 𝗛𝗔𝗩𝗘 𝗬𝗢𝗨 𝗛𝗘𝗥𝗘 💫\n"
                                                f"🤝 𝗦𝗧𝗔𝗬 𝗥𝗘𝗦𝗣𝗘𝗖𝗧𝗙𝗨𝗟 • 𝗙𝗢𝗟𝗟𝗢𝗪 𝗧𝗛𝗘 𝗥𝗨𝗟𝗘𝗦\n"
                                                f"🔥 𝗘𝗡𝗝𝗢𝗬 𝗧𝗛𝗘 𝗚𝗖 • 𝗦𝗧𝗔𝗬 𝗔𝗖𝗧𝗜𝗩𝗘!\n\n"
                                                f"╰┈➤ 🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
                                                f"╰┈➤ 👑 𝗢𝗪𝗡𝗘𝗥 ➜ @{OWNER_USERNAME}"
                                            )
                                            cl.direct_send(welcome_card, thread_ids=[thread_id])
                                            time.sleep(1)
                        else:
                            ever_seen_members.update(current_members)

                        group_members_state[thread_id] = current_members

                        # 3. MESSAGE SCANNER & MODERATION
                        if thread.messages:
                            last_msg = thread.messages[0]
                            
                            if last_msg.id not in seen_message_ids:
                                seen_message_ids.add(last_msg.id)
                                
                                if len(seen_message_ids) > 300:
                                    seen_message_ids.pop()

                                text = str(last_msg.text or "").lower()
                                sender_id = str(last_msg.user_id)
                                sender_username = last_msg.user.username if hasattr(last_msg, 'user') else 'User'
                                item_type = getattr(last_msg, 'item_type', '')

                                if sender_id == bot_pk:
                                    continue

                                is_sender_admin = (sender_id in gc_admins) if gc_admins else False

                                admin_tags_str = " @ADMIN"
                                if gc_admins:
                                    admin_usernames = []
                                    for u in thread.users:
                                        if str(u.pk) in gc_admins and str(u.pk) != bot_pk:
                                            admin_usernames.append(f"@{u.username}")
                                    if admin_usernames:
                                        admin_tags_str = " ".join(admin_usernames)

                                # नॉन-एडमिन मॉडेशन (लिंक, रील्स, 18+ ब्लॉक)
                                if not is_sender_admin:
                                    if any(domain in text for domain in ['http://', 'https://', 'www.', '.com', 't.me', 'instagram.com/']):
                                        link_msg = (
                                            f"🚨🔗 𝗟𝗜𝗡𝗞 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗!\n\n"
                                            f"👤 𝗨𝗦𝗘𝗥 ➜ @{sender_username}\n"
                                            f"⚠️ 𝗨𝗡𝗔𝗨𝗧𝗛𝗢𝗥𝗜𝗭𝗘𝗗 𝗟𝗜𝗡𝗞 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗!\n"
                                            f"🛑 𝗣𝗟𝗘𝗔𝗦𝗘 𝗗𝗢𝗡'𝗧 𝗦𝗘𝗡𝗗 𝗨𝗡𝗔𝗨𝗧𝗛𝗢𝗥𝗜𝗭𝗘𝗗 𝗟𝗜𝗡𝗞𝗦 𝗜𝗡 𝗧𝗛𝗘 𝗚𝗖.\n\n"
                                            f"👑 𝗔𝗗𝗠𝗜𝗡𝗦 ➜ {admin_tags_str}\n\n"
                                            f"╰┈➤ 🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
                                            f"╰┈➤ 👑 𝗢𝗪𝗡𝗘𝗥 ➜ @{OWNER_USERNAME}"
                                        )
                                        cl.direct_send(link_msg, thread_ids=[thread_id])
                                        time.sleep(1)
                                        continue

                                    if item_type in ['clip', 'media'] or '/reel/' in text or 'video' in item_type:
                                        reel_msg = (
                                            f"🚫🎬 𝗥𝗘𝗘𝗟𝗦 𝗡𝗢𝗧 𝗔𝗟𝗟𝗢𝗪𝗘𝗗!\n\n"
                                            f"👤 @{sender_username}\n\n"
                                            f"⚠️ 𝗥𝗘𝗘𝗟𝗦 / 𝗩𝗜ДЕО𝗦 𝗔𝗥𝗘 𝗡𝗢𝗧 𝗔𝗟𝗟𝗢𝗪𝗘𝗗 𝗛𝗘𝗥𝗘.\n\n"
                                            f"👑 𝗔𝗗𝗠𝗜𝗡𝗦 ➜ {admin_tags_str}\n\n"
                                            f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
                                            f"╰┈➤ 👑 𝗢𝗪𝗡𝗘𝗥 ➜ @{OWNER_USERNAME}"
                                        )
                                        cl.direct_send(reel_msg, thread_ids=[thread_id])
                                        time.sleep(1)
                                        continue

                                    restricted_words = ['18+', 'adult', 'sex', 'xxx', 'porn', 'nude', 'gali', 'bhadve', 'chutiya', 'madarchod', 'behenchod']
                                    if any(word in text for word in restricted_words):
                                        adult_msg = (
                                            f"🚨🛡️ 𝗠𝗢𝗗𝗘𝗥𝗔𝗧𝗜𝗢𝗡 𝗔𝗟𝗘𝗥𝗧!\n\n"
                                            f"👤 𝗨𝗦𝗘𝗥 ➜ @{sender_username}\n"
                                            f"🔞 𝗔𝗕𝗨𝗦𝗘 / 𝟭𝟴+ 𝗖𝗢𝗡𝗧𝗘𝗡𝗧 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗!\n\n"
                                            f"👑 𝗔𝗗𝗠𝗜𝗡𝗦 ➜ {admin_tags_str}\n\n"
                                            f"╰┈➤ 🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
                                            f"╰┈➤ 👑 𝗢𝗪𝗡𝗘𝗥 ➜ @{OWNER_USERNAME}"
                                        )
                                        cl.direct_send(adult_msg, thread_ids=[thread_id])
                                        time.sleep(1)
                                        continue

                                # 4. SMART AI ASSISTANT WITH USER TAGGING & MULTI-LANGUAGE
                                if bot_tag in text:
                                    clean_query = text.replace(bot_tag, "").strip()
                                    
                                    if "status" in clean_query or "ping" in clean_query:
                                        status_card = (
                                            f"⚡ ULTRA PRO BOT STATUS: ONLINE\n"
                                            f"───────────────\n"
                                            f"🟢 System: Fully Operational\n"
                                            f"🤖 AI: Multi-Language & Tagging Active\n\n"
                                            f"👑 Owner: @{OWNER_USERNAME}"
                                        )
                                        cl.direct_send(status_card, thread_ids=[thread_id])
                                    else:
                                        if len(clean_query) > 0:
                                            # सीधे यूजर को टैग करते हुए एआई से रिप्लाई मंगाओ
                                            ai_reply = get_ai_response(clean_query, sender_username)
                                            final_ai_msg = (
                                                f"@{sender_username} {ai_reply}\n\n"
                                                f"╰┈➤ 🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}"
                                            )
                                            cl.direct_send(final_ai_msg, thread_ids=[thread_id])
                                        else:
                                            hello_msg = (
                                                f"👋 अरे @{sender_username} भाई! बताओ, क्या चल रहा है?\n\n"
                                                f"╰┈➤ 🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}"
                                            )
                                            cl.direct_send(hello_msg, thread_ids=[thread_id])

                    is_first_run = False

                except Exception as inner_e:
                    print(f"[LOOP ERROR] {inner_e}")

                time.sleep(3)

        except Exception as outer_e:
            print(f"[-] RECONNECTING... Error: {outer_e}")
            time.sleep(10)

if __name__ == "__main__":
    start_bot()
