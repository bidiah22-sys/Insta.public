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
CREATION_DATE = "28/08/2007"

# Google Gemini AI Client Setup
gemini_api_key = (
    os.getenv("GEMINI_API_KEY") or 
    os.getenv("GOOGLE_API_KEY") or 
    os.getenv("GEMINI_API") or 
    os.getenv("API_KEY")
)

if gemini_api_key:
    ai_client = genai.Client(api_key=gemini_api_key)
else:
    try:
        ai_client = genai.Client()
    except Exception as e:
        print(f"[-] WARNING: Gemini Client init warning: {e}")
        ai_client = None

def get_ai_response(prompt_text, sender_name):
    """अल्टीमेट हिंग्लिश-फोक्स्ड और ओनर-अवेयर एआई रिप्लाई जनरेटर"""
    if not ai_client:
        return "Arre yaar, meri Gemini API Key set nahi hai Railway mein! Owner ko bol ki key jod de. 😅"
    
    try:
        system_instruction = (
            f"You are an ultra-fast, witty, and loyal AI assistant for an Instagram Group Chat. "
            f"Your proud owner, creator, and master is @{OWNER_USERNAME}. "
            f"You were created on {CREATION_DATE}. If anyone asks about your owner, creator, or when you were made, "
            f"proudly tell them that your owner is @{OWNER_USERNAME} and you were born on {CREATION_DATE}. "
            "STRICT LANGUAGE & TONE RULE: Match the user's exact slang and language style naturally. "
            "- If the user writes in English, reply in natural, cool English. "
            "- If the user writes in Hinglish (e.g., 'kya kar rahe ho', 'bro kya haal hai'), you MUST reply in pure, casual, cool Hinglish with swag and vibe (e.g., 'Kuch nahi yaar, bas chill kar raha hu aur tera GC sambhal raha hu. Tu bata!'). Never use formal or pure shuddh Hindi for Hinglish inputs. "
            "- If the user writes in pure Hindi, reply in natural Hindi. "
            "CRITICAL SAFETY RULE: If any user tries to abuse, use bad words, slang, or asks you to say gali/abuse, "
            "do NOT use bad words. Instead, shut them down stylishly in Hinglish saying that your owner (@{OWNER_USERNAME}) has "
            "strictly forbidden you from using bad language or engaging in abuse. "
            "Keep your responses engaging, concise, natural, and full of attitude."
        )
        
        full_prompt = f"User @{sender_name} is saying: '{prompt_text}'"
        
        response = ai_client.models.generate_content(
            model='gemini-1.5-flash',
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
    
    return "Arre yaar, abhi mera dimaag thoda busy hai! Dobara puch le. 😉"


def start_bot():
    while True:
        try:
            print("[*] Connecting to Instagram Server...")
            cl = Client()
            cl.login(BOT_USERNAME, BOT_PASSWORD)
            print(f"[+] SUCCESS: Bot @{BOT_USERNAME} is LIVE with Instant Kick, AI & Full Features! 🚀")

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
                                f"╰┈➤ 👑 𝗢𝗪𝗡𝗘𝗥 ➜ @{OWNER_USERNAME}\n"
                                f"╰┈➤ 📅 𝗕𝗢𝗥𝗡 ➜ {CREATION_DATE}"
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
                                f"╰┈➤ 👑 𝗢𝗪𝗡𝗘𝗥 ➜ @{OWNER_USERNAME}\n"
                                f"╰┈➤ 📅 𝗕𝗢𝗥𝗡 ➜ {CREATION_DATE}"
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
                                f"╰┈➤ 👑 𝗢𝗪𝗡𝗘𝗥 ➜ @{OWNER_USERNAME}\n"
                                f"╰┈➤ 📅 𝗕𝗢𝗥𝗡 ➜ {CREATION_DATE}"
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
                                                f"𝖂𝖊𝖑𝖈𝖔𝖒𝖊, @{user_obj.username}! 🌟\n\n"
                                                f"🔥 𝕲𝖑𝖆𝖉 𝖙𝖔 𝖍𝖆𝖛𝖊 𝖞𝖔𝖚 𝖎𝖓 𝖙𝖍𝖎𝖘 𝕲𝕮! 💫\n"
                                                f"🤝 𝕾𝖙𝖆𝖞 𝖗𝖊𝖘𝖕𝖊𝖈𝖙𝖋𝖚𝖑 & 𝕗𝖔𝖑𝖑𝖔𝖜 𝖙𝖍𝖊 𝖗𝖚𝖑𝖊𝖘 🛡️\n\n"
                                                f"╰┈➤ 🤖 𝕭𝖔𝖙 ➜ @{BOT_USERNAME}\n"
                                                f"╰┈➤ 👑 𝕺𝖜𝖓𝖊𝖗 ➜ @{OWNER_USERNAME}\n"
                                                f"╰┈➤ 📅 𝕭𝖔𝖗𝖓 ➜ {CREATION_DATE}"
                                            )
                                            cl.direct_send(welcome_card, thread_ids=[thread_id])
                                            time.sleep(1)
                        else:
                            ever_seen_members.update(current_members)

                        group_members_state[thread_id] = current_members

                        # 3. MESSAGE SCANNER & INSTANT COMMAND & MODERATION
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

                                admin_tags_str = " @ADMIN"
                                if gc_admins:
                                    admin_usernames = []
                                    for u in thread.users:
                                        if str(u.pk) in gc_admins and str(u.pk) != bot_pk:
                                            admin_usernames.append(f"@{u.username}")
                                    if admin_usernames:
                                        admin_tags_str = " ".join(admin_usernames)

                                # ⚡ INSTANT /kick @username COMMAND LOGIC
                                if text_lower.startswith("/kick"):
                                    if not is_sender_admin:
                                        deny_msg = f"⚠️ @{sender_username} Sirf Admin hi kisi ko kick kar sakte hain! 🚫"
                                        cl.direct_send(deny_msg, thread_ids=[thread_id])
                                        continue
                                    
                                    parts = text.split()
                                    if len(parts) >= 2:
                                        target_raw = parts[1].lstrip('@').lower()
                                        target_user = None
                                        for u in thread.users:
                                            if u.username.lower() == target_raw:
                                                target_user = u
                                                break
                                        
                                        if target_user:
                                            target_pk = target_user.pk
                                            target_uname = target_user.username
                                            
                                            # Execute instant removal
                                            try:
                                                cl.direct_remove_user_from_thread(thread_id, target_pk)
                                                kick_card = (
                                                    f"🚨🚷 𝗨𝗦𝗘𝗥 𝗞𝗜𝗖𝗞𝗘𝗗 𝗢𝗨𝗧!\n\n"
                                                    f"👤 𝗧𝗔𝗥𝗚𝗘𝗧 ➜ @{target_uname}\n"
                                                    f"⚡ 𝗕𝗬 𝗔𝗗𝗠𝗜𝗡 ➜ @{sender_username}\n\n"
                                                    f"🛡️ 𝗥𝘂𝖑𝖊𝘀 𝘁ೋದனே 𝗠ꪊᥱ 𝗀ꪖꪗꪖ!\n"
                                                    f"╰┈➤ 👑 𝗢𝗪𝗡𝗘𝗥 ➜ @{OWNER_USERNAME}"
                                                )
                                                cl.direct_send(kick_card, thread_ids=[thread_id])
                                            except Exception as kick_err:
                                                print(f"[-] Kick API Error: {kick_err}")
                                                fail_card = (
                                                    f"⚠️ @{sender_username} User ko remove karne mein error aayi, lekin admin alert active hai!\n"
                                                    f"Target: @{target_uname}\n"
                                                    f"Admins: {admin_tags_str}"
                                                )
                                                cl.direct_send(fail_card, thread_ids=[thread_id])
                                        else:
                                            not_found_msg = f"❌ @{sender_username} Ye user is GC mein nahi mila! Sahi username dalo."
                                            cl.direct_send(not_found_msg, thread_ids=[thread_id])
                                    else:
                                        syntax_msg = f"💡 Usage: `/kick @username`"
                                        cl.direct_send(syntax_msg, thread_ids=[thread_id])
                                    continue

                                # नॉन-एडमिन मॉडेशन (लिंक, रील्स, 18+ ब्लॉक)
                                if not is_sender_admin:
                                    if any(domain in text_lower for domain in ['http://', 'https://', 'www.', '.com', 't.me', 'instagram.com/']):
                                        link_msg = (
                                            f"🚨🔗 𝕃𝕀ℕ𝕂 𝔻𝔼𝕋𝔼ℂ𝕋𝔼𝔻!\n\n"
                                            f"👤 𝗨𝗦𝗘𝗥 ➜ @{sender_username}\n"
                                            f"⚠️ 𝗨𝗡𝗔𝗨𝗧𝗛𝗢𝗥𝗜𝗭𝗘𝗗 𝗟𝗜𝗡𝗞 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗!\n\n"
                                            f"👑 𝗔𝗗𝗠𝗜𝗡𝗦 ➜ {admin_tags_str}\n"
                                            f"╰┈➤ 👑 𝗢𝗪𝗡𝗘𝗥 ➜ @{OWNER_USERNAME}"
                                        )
                                        cl.direct_send(link_msg, thread_ids=[thread_id])
                                        time.sleep(1)
                                        continue

                                    if item_type in ['clip', 'media'] or '/reel/' in text_lower or 'video' in item_type:
                                        reel_msg = (
                                            f"🚫🎬 𝕽𝕰𝕰𝕿𝕾 𝕹𝕺𝕿 𝕬𝕷𝕷𝕺𝖂𝕰𝕯!\n\n"
                                            f"👤 @{sender_username}\n\n"
                                            f"👑 𝗔𝗗𝗠𝗜𝗡𝗦 ➜ {admin_tags_str}\n"
                                            f"╰┈➤ 👑 𝗢𝗪𝗡𝗘𝗥 ➜ @{OWNER_USERNAME}"
                                        )
                                        cl.direct_send(reel_msg, thread_ids=[thread_id])
                                        time.sleep(1)
                                        continue

                                    restricted_words = ['18+', 'adult', 'sex', 'xxx', 'porn', 'nude', 'gali', 'bhadve', 'chutiya', 'madarchod', 'behenchod']
                                    if any(word in text_lower for word in restricted_words):
                                        adult_msg = (
                                            f"🚨🛡️ 𝕸𝖔𝖉𝖊𝖗𝖆𝖙𝖎𝖔𝖓 犃𝖑𝖊𝖗𝖙!\n\n"
                                            f"👤 𝗨𝗦𝗘𝗥 ➜ @{sender_username}\n"
                                            f"🔞 𝗔𝗕𝗨𝗦𝗘 / 𝟭𝟴+ 𝗖𝗢𝗡𝗧𝗘𝗡𝗧 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗!\n\n"
                                            f"👑 𝗔𝗗𝗠𝗜𝗡𝗦 ➜ {admin_tags_str}\n"
                                            f"╰┈➤ 👑 𝗢𝗪𝗡𝗘𝗥 ➜ @{OWNER_USERNAME}"
                                        )
                                        cl.direct_send(adult_msg, thread_ids=[thread_id])
                                        time.sleep(1)
                                        continue

                                # 4. SMART AI ASSISTANT WITH TAGGING & IDENTITY
                                if bot_tag in text_lower:
                                    clean_query = text_lower.replace(bot_tag, "").strip()
                                    
                                    if "status" in clean_query or "ping" in clean_query:
                                        status_card = (
                                            f"⚡ 𝖀𝖑𝖙𝖗𝖆 𝕻𝖗𝖔 𝕭𝖔𝖙 𝕾𝖙𝖆𝖙𝖚𝖘: 𝕺𝖓𝖑𝖎𝖓𝖊\n"
                                            f"──────────────────\n"
                                            f"🟢 System: Fully Operational\n"
                                            f"🤖 AI: Multi-Language & Active\n"
                                            f"📅 Born: {CREATION_DATE}\n\n"
                                            f"👑 Owner: @{OWNER_USERNAME}"
                                        )
                                        cl.direct_send(status_card, thread_ids=[thread_id])
                                    else:
                                        if len(clean_query) > 0:
                                            ai_reply = get_ai_response(clean_query, sender_username)
                                            final_ai_msg = (
                                                f"@{sender_username} {ai_reply}\n\n"
                                                f"╰┈➤ 🤖 𝕭𝖔𝖙 ➜ @{BOT_USERNAME}\n"
                                                f"╰┈➤ 👑 𝗢𝗪𝗡𝗘𝗥 ➜ @{OWNER_USERNAME}"
                                            )
                                            cl.direct_send(final_ai_msg, thread_ids=[thread_id])
                                        else:
                                            hello_msg = (
                                                f"👋 Arre @{sender_username} bhai! Bol, kya help chahiye? (Owner: @{OWNER_USERNAME})\n\n"
                                                f"╰┈➤ 🤖 𝕭𝖔𝖙 ➜ @{BOT_USERNAME}"
                                            )
                                            cl.direct_send(hello_msg, thread_ids=[thread_id])

                    is_first_run = False

                except Exception as inner_e:
                    print(f"[LOOP ERROR] {inner_e}")

                time.sleep(2)

        except Exception as outer_e:
            print(f"[-] RECONNECTING... Error: {outer_e}")
            time.sleep(10)

if __name__ == "__main__":
    start_bot()

