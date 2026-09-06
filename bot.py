import os
import time
from datetime import datetime
from instagrapi import Client

# API & Credentials Configuration
BOT_USERNAME = os.getenv("BOT_USERNAME") or os.getenv("INSTA_USERNAME") or "bot222703"
BOT_PASSWORD = os.getenv("BOT_PASSWORD") or os.getenv("INSTA_PASSWORD") or "ananya295"
OWNER_USERNAME = "fx_smw"
CREATION_DATE = "28/08/2007"

def start_bot():
    while True:
        try:
            print("[*] Connecting to Instagram Server...")
            cl = Client()
            cl.login(BOT_USERNAME, BOT_PASSWORD)
            print(f"[+] SUCCESS: Bot @{BOT_USERNAME} is LIVE with Custom Styled Font Wishes! 🚀")

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

                        # 1. AUTO TIME-BASED WISHES (EXACT CUSTOM FONT FORMAT)
                        if 5 <= current_hour < 6 and last_morning_wish_date != current_date:
                            morning_msg = (
                                f"☀️ 𝕲𝕺𝕺𝕯 𝕸𝕺𝕽𝕹𝕴𝕹𝕲 @everyone! 🌅\n\n"
                                f"👤 @everyone\n\n"
                                f"⚠️ 𝕲𝕺𝕺𝕯 𝕸𝕺𝕽𝕹𝕴𝕹𝕲 𝕰𝖁𝕰𝕽𝚈𝙾𝗡𝗘! 𝕬 𝕹𝙴𝚆 𝕯𝙰𝚈, 𝙰 𝕹𝙴𝚆 𝙱𝙴𝙶𝙸𝙽𝙽𝙸𝙽𝙶...\n"
                                f"💪 𝕾𝚃𝙰𝚈 𝙴𝙽𝙴𝚁𝙶𝙴𝚃𝙸𝙲 𝙰𝙽𝙳 𝙼𝙰𝙺𝙴 𝚃𝙷𝙸𝚂 𝙳𝙰𝚈 𝙰𝚆𝙴𝚂𝙾𝙼𝙴!\n\n"
                                f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
                                f"👨‍💻 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ @{OWNER_USERNAME}"
                            )
                            cl.direct_send(morning_msg, thread_ids=[thread_id])
                            last_morning_wish_date = current_date
                            time.sleep(2)

                        elif current_hour == 12 and 0 <= current_minute <= 15 and last_noon_wish_date != current_date:
                            noon_msg = (
                                f"🕛 𝕲𝕺𝕺𝕯 𝕬𝕱𝕿𝕰𝕽𝕹𝕺𝕺𝕹 @everyone! ☀️\n\n"
                                f"👤 @everyone\n\n"
                                f"⚠️ 𝕲𝕺𝕺𝕯 𝕬𝙵𝚃𝙴𝚁𝙽𝙾𝙾𝙽 𝙴𝚅𝙴𝚁𝚈𝙾𝙽𝙴! 𝚂𝚃𝙰𝚈 𝙷𝚈𝙳𝚁𝙰𝚃𝙴𝙳, 𝚃𝙰𝙺𝙴 𝙰 𝙱𝚁𝙴𝙰𝙺,\n"
                                f"𝙰𝙽𝙳 𝚃𝙴𝙻𝙻 𝙼𝙴 𝙷𝙾𝚆'𝚂 𝚃𝙷𝙴 𝙶𝙲 𝚅𝙸𝙱𝙸𝙽𝙶?\n\n"
                                f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
                                f"👨‍💻 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ @{OWNER_USERNAME}"
                            )
                            cl.direct_send(noon_msg, thread_ids=[thread_id])
                            last_noon_wish_date = current_date
                            time.sleep(2)

                        elif current_hour == 22 and 0 <= current_minute <= 30 and last_night_wish_date != current_date:
                            night_msg = (
                                f"🌙 𝕲𝕺𝕺𝕯 𝕹𝕴𝕲𝕳𝕿 @everyone! 💤\n\n"
                                f"👤 @everyone\n\n"
                                f"⚠️ 𝕲𝕺𝕺𝕯 𝕅𝙸𝙶𝙷𝚃 𝙴𝚅𝙴𝚁𝚈𝙾𝙽𝙴! 𝚁𝙴𝚂𝚃 𝚆𝙴𝙻𝙻, 𝚁𝙴𝙲𝙷𝙰𝚁𝙶𝙴 𝚈𝙾𝚄𝚁 𝙴𝙽𝙴𝚁𝙶𝙸𝙴𝚂...\n"
                                f"𝚂𝙴𝙴 𝚈𝙾𝚄 𝙰𝙻𝙻 𝚃𝙾𝙼𝙾𝚁𝚁𝙾𝚆!\n\n"
                                f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
                                f"👨‍💻 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ @{OWNER_USERNAME}"
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
                                                f"👤 @{user_obj.username}\n\n"
                                                f"⚠️ 𝕲𝙻𝙰𝙳 𝚃𝙾 𝙷𝙰𝚅𝙴 𝚈𝙾𝚄 𝙸𝙽 𝚃𝙷𝙸𝚂 𝙶𝙲! 𝚂𝚃𝙰𝚈 𝚁𝙴𝚂𝙿𝙴𝙲𝚃𝙵𝚄𝙻 & 𝙵𝙾𝙻𝙻𝙾𝚆 𝚃𝙷𝙴 𝚁𝚄𝙻𝙴𝚂.\n\n"
                                                f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
                                                f"👨‍💻 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ @{OWNER_USERNAME}"
                                            )
                                            cl.direct_send(welcome_card, thread_ids=[thread_id])
                                            time.sleep(1)
                        else:
                            ever_seen_members.update(current_members)

                        group_members_state[thread_id] = current_members

                        # 3. MESSAGE SCANNER, MODERATION & @everyone / @bot REPLY
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

                                # नॉन-एडमिन मॉडेशन (लिंक, रील्स, वीडियो, 18+ ब्लॉक - हूबहू तुम्हारे फॉर्मेट में)
                                if not is_sender_admin:
                                    if any(domain in text_lower for domain in ['http://', 'https://', 'www.', '.com', 't.me', 'instagram.com/']):
                                        link_msg = (
                                            f"🚨🔗 𝕃𝕀ℕ𝕂 𝔻𝔼𝕋𝔼ℂ𝕋𝔼𝔻!\n\n"
                                            f"👤 @{sender_username}\n\n"
                                            f"⚠️ 𝕌ℕ𝔸𝕌𝕋ℍ𝕆ℝ𝕀𝚉𝙴𝙳 𝙻𝙸𝙽𝙺𝚂 𝙰𝚁𝙴 𝙽𝙾𝚃 𝙰𝙻𝙻𝙾𝚆𝙴𝙳 𝙷𝙴𝚁𝙴.\n\n"
                                            f"🛑 𝙿𝙻𝙴𝙰𝚂𝙴 𝙳𝙾𝙽'𝚃 𝚁𝙴𝙿𝙴𝙰𝚃!\n\n"
                                            f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
                                            f"👨‍💻 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ @{OWNER_USERNAME}"
                                        )
                                        cl.direct_send(link_msg, thread_ids=[thread_id])
                                        time.sleep(1)
                                        continue

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

                                    restricted_words = ['18+', 'adult', 'sex', 'xxx', 'porn', 'nude', 'gali', 'bhadve', 'chutiya', 'madarchod', 'behenchod']
                                    if any(word in text_lower for word in restricted_words):
                                        adult_msg = (
                                            f"🚨🛡️ 𝗔𝗕𝗨𝗦𝗘 / 𝟭𝟴+ 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗!\n\n"
                                            f"👤 @{sender_username}\n\n"
                                            f"⚠️ 𝗔𝗕𝗨𝗦𝗘 𝗢𝗥 𝗔𝗗𝗨𝙻𝚃 𝙲𝙾𝙽𝚃𝙴𝙽𝚃 𝙸𝚂 𝙽𝙾𝚃 𝙰𝙻𝙻𝙾𝚆𝙴𝙳 𝙷𝙴𝚁𝙴.\n\n"
                                            f"🛑 𝙿𝙻𝙴𝙰𝚂𝙴 𝙳𝙾𝙽'𝚃 𝚁𝙴𝙿𝙴𝙰𝚃!\n\n"
                                            f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
                                            f"👨‍💻 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ @{OWNER_USERNAME}"
                                        )
                                        cl.direct_send(adult_msg, thread_ids=[thread_id])
                                        time.sleep(1)
                                        continue

                                # 4. RESPOND TO @everyone OR @bot TAGS
                                if "@everyone" in text_lower or bot_tag in text_lower:
                                    response_msg = (
                                        f"👋 𝙷𝙴𝙻𝙻𝙾 @{sender_username}!\n\n"
                                        f"🤖 𝙱𝙾𝚃 𝙸𝚂 𝙰𝙲𝚃𝙸𝚅𝙴 𝙰𝙽𝙳 𝙼𝙰𝙽𝙰𝙶𝙸𝙽𝙶 𝚃𝙷𝙴 𝙶𝙲 𝚂𝙼𝙾𝙾𝚃𝙷𝙻𝚈. 🚀\n\n"
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
