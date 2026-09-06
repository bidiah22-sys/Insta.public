import time
from instagrapi import Client

# ==========================================
# ⚙️ BOT CREDENTIALS
# ==========================================
BOT_USERNAME = "bot222703"  # ⚠️ बोट का यूजरनेम (बिना @)
BOT_PASSWORD = "ananya295"  # ⚠️ बोट का पासवर्ड

# ==========================================
# 👑 OWNER INSTAGRAM ID
# ==========================================
OWNER_USERNAME = "fx_smw"

cl = Client()

print("[*] Connecting to Instagram Server...")

login_success = False
try:
    cl.login(BOT_USERNAME, BOT_PASSWORD)
    print(f"[+] SUCCESS: Bot @{BOT_USERNAME} is LIVE and Powered Up in Ultra Mode! 🚀")
    login_success = True
except Exception as e:
    print(f"[-] LOGIN ERROR: {e}")

seen_message_ids = set()
group_members_state = {}
ever_seen_members = set()

if login_success:
    print("[*] Bot Active & Scanning GC at High Speed...")
    while True:
        try:
            threads = cl.direct_threads(amount=5)

            for thread in threads:
                if not thread.is_group:
                    continue

                thread_id = thread.id
                bot_tag = f"@{BOT_USERNAME.lower()}"

                # 1. Real-time Admins Verification
                gc_admins = []
                try:
                    if hasattr(thread, 'admin_user_ids') and thread.admin_user_ids:
                        gc_admins = [str(uid) for uid in thread.admin_user_ids]
                    elif hasattr(thread, 'admin_users') and thread.admin_users:
                        gc_admins = [str(getattr(admin, 'pk', admin)) for admin in thread.admin_users]
                except Exception:
                    gc_admins = []

                bot_pk = str(cl.user_id)
                
                # बोट खुद एडमिन है या नहीं, इसका कड़ा चेक
                is_bot_admin = (bot_pk in gc_admins) if gc_admins else True

                # 2. WELCOME & WELCOME BACK LOGIC (अगर बोट एडमिन है)
                current_members = {user.pk for user in thread.users}

                if thread_id in group_members_state:
                    old_members = group_members_state[thread_id]
                    newly_joined = current_members - old_members

                    if newly_joined and is_bot_admin:
                        for joined_pk in newly_joined:
                            user_obj = next((u for u in thread.users if u.pk == joined_pk), None)
                            if user_obj:
                                if joined_pk in ever_seen_members:
                                    welcome_card = (
                                        f"🦋✨ 𝗪𝗘𝗟𝗖𝗢𝗠𝗘 𝗕𝗔𝗖𝗞, @{user_obj.username}! ✨🦋\n\n"
                                        f"🌷 𝗡𝗜𝗖𝗘 𝗧𝗢 𝗦𝗘𝗘 𝗬𝗢𝗨 𝗕𝗔𝗖𝗞!\n"
                                        f"🔥 𝗦𝗧𝗔𝗬 𝗔𝗖𝗧𝗜𝗩𝗘 • 𝗙𝗢𝗟𝗟𝗢𝗪 𝗧𝗛𝗘 𝗥𝗨𝗟𝗘𝗦\n"
                                        f"✨ 𝗘𝗡𝗝𝗢𝗬 𝗧𝗛𝗘 𝗚𝗖 & 𝗞𝗘𝗘𝗣 𝗧𝗛𝗘 𝗩𝗜𝗕𝗘 𝗚𝗢𝗢𝗗!\n\n"
                                        f"╰┈➤ 🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
                                        f"╰┈➤ 👨‍💻 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ @{OWNER_USERNAME}"
                                    )
                                else:
                                    welcome_card = (
                                        f"🦋✨ 𝗪𝗘𝗟𝗖𝗢𝗠𝗘, @{user_obj.username}! ✨🦋\n\n"
                                        f"🌸 𝗛𝗘𝗬! 𝗚𝗟𝗔𝗗 𝗧𝗢 𝗛𝗔𝗩𝗘 𝗬𝗢𝗨 𝗛𝗘𝗥𝗘 💫\n"
                                        f"🤝 𝗦𝗧𝗔𝗬 𝗥𝗘𝗦𝗣𝗘𝗖𝗧𝗙𝗨𝗟 • 𝗙𝗢𝗟𝗟𝗢𝗪 𝗧𝗛𝗘 𝗥𝗨𝗟𝗘𝗦\n"
                                        f"🔥 𝗘𝗡𝗝𝗢𝗬 𝗧𝗛𝗘 𝗚𝗖 • 𝗦𝗧𝗔𝗬 𝗔𝗖𝗧𝗜𝗩𝗘!\n\n"
                                        f"╰┈➤ 🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
                                        f"╰┈➤ 👨‍💻 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ @{OWNER_USERNAME}"
                                    )
                                    ever_seen_members.add(joined_pk)

                                cl.direct_send(welcome_card, thread_ids=[thread_id])
                else:
                    ever_seen_members.update(current_members)

                group_members_state[thread_id] = current_members

                # 3. MESSAGE & ULTRA SECURITY SCANNER
                if thread.messages:
                    last_msg = thread.messages[0]
                    if last_msg.id not in seen_message_ids:
                        seen_message_ids.add(last_msg.id)

                        text = str(last_msg.text or "").lower()
                        sender_id = str(last_msg.user_id)
                        item_type = getattr(last_msg, 'item_type', '')

                        # अपने खुद के मैसेज इग्नोर करें
                        if sender_id == bot_pk:
                            continue

                        # एडमिन टैग स्ट्रिंग तैयार करना
                        admin_tags_str = " @ADMIN"
                        if gc_admins:
                            admin_usernames = []
                            for u in thread.users:
                                if str(u.pk) in gc_admins and str(u.pk) != bot_pk:
                                    admin_usernames.append(f"@{u.username}")
                            if admin_usernames:
                                admin_tags_str = " ".join(admin_usernames)

                        # अगर बोट एडमिन नहीं है, तो सिक्योरिटी एक्शन ब्लॉक रहेंगे
                        if is_bot_admin:
                            # --- A. LINK BLOCKER ---
                            if any(domain in text for domain in ['http://', 'https://', 'www.', '.com', 't.me', 'instagram.com/']):
                                link_msg = (
                                    f"🚨🔗 𝗟𝗜𝗡𝗞 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗!\n\n"
                                    f"👤 𝗨𝗦𝗘𝗥 ➜ @{last_msg.user.username if hasattr(last_msg, 'user') else 'User'}\n"
                                    f"⚠️ 𝗨𝗡𝗔𝗨𝗧𝗛𝗢𝗥𝗜𝗭𝗘𝗗 𝗟𝗜𝗡𝗞 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗!\n"
                                    f"🛑 𝗣𝗟𝗘𝗔𝗦𝗘 𝗗𝗢𝗡'𝗧 𝗦𝗘𝗡𝗗 𝗨𝗡𝗔𝗨𝗧𝗛𝗢𝗥𝗜𝗭𝗘𝗗 𝗟𝗜𝗡𝗞𝗦 𝗜𝗡 𝗧𝗛𝗘 𝗚𝗖.\n\n"
                                    f"⚡ 𝗥𝗘𝗣𝗘𝗔𝗧𝗘𝗗 𝗩𝗜𝗢𝗟𝗔𝗧𝗜𝗢𝗡𝗦 𝗠𝗔𝗬 𝗟𝗘𝗔𝗗 𝗧𝗢 𝗔𝗖𝗧𝗜𝗢𝗡 🚫\n\n"
                                    f"👑 𝗔𝗗𝗠𝗜𝗡𝗦 ➜ {admin_tags_str}\n\n"
                                    f"╰┈➤ 🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
                                    f"╰┈➤ 👨‍💻 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ @{OWNER_USERNAME}"
                                )
                                cl.direct_send(link_msg, thread_ids=[thread_id])
                                continue

                            # --- B. REELS / VIDEO BLOCKER ---
                            if item_type in ['clip', 'media'] or '/reel/' in text or 'video' in item_type:
                                reel_msg = (
                                    f"🚫🎬 𝗥𝗘𝗘𝗟𝗦 𝗡𝗢𝗧 𝗔𝗟𝗟𝗢𝗪𝗘𝗗!\n\n"
                                    f"👤 @{last_msg.user.username if hasattr(last_msg, 'user') else 'User'}\n\n"
                                    f"⚠️ 𝗥𝗘𝗘𝗟𝗦 / 𝗩𝗜𝗗𝗘𝗢𝗦 𝗔𝗥𝗘 𝗡𝗢𝗧 𝗔𝗟𝗟𝗢𝗪𝗘𝗗 𝗛𝗘𝗥𝗘.\n\n"
                                    f"🛑 𝗣𝗟𝗘𝗔𝗦𝗘 𝗗𝗢𝗡'𝗧 𝗥𝗘𝗣𝗘𝗔𝗧!\n\n"
                                    f"👑 𝗔𝗗𝗠𝗜𝗡𝗦 ➜ {admin_tags_str}\n\n"
                                    f"🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
                                    f"╰┈➤ 👨‍💻 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ @{OWNER_USERNAME}"
                                )
                                cl.direct_send(reel_msg, thread_ids=[thread_id])
                                continue

                            # --- C. 18+ CONTENT / ABUSE ALERT ---
                            restricted_words = ['18+', 'adult', 'sex', 'xxx', 'porn', 'nude', 'gali', 'bhadve']
                            if any(word in text for word in restricted_words):
                                adult_msg = (
                                    f"🚨🛡️ 𝗠𝗢𝗗𝗘𝗥𝗔𝗧𝗜𝗢𝗡 𝗔𝗟𝗘𝗥𝗧!\n\n"
                                    f"👤 𝗨𝗦𝗘𝗥 ➜ @{last_msg.user.username if hasattr(last_msg, 'user') else 'User'}\n"
                                    f"🔞 𝟭𝟴+ / 𝗔𝗚𝗘-𝗥𝗘𝗦𝗧𝗥𝗜𝗖𝗧𝗘𝗗 𝗖𝗢𝗡𝗧𝗘𝗡𝗧 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗!\n\n"
                                    f"⚠️ 𝗨𝗡𝗔𝗣𝗣𝗥𝗢𝗣𝗥𝗜𝗔𝗧𝗘 𝗖𝗢𝗡𝗧𝗘𝗡𝗧 𝗜𝗦 𝗡𝗢𝗧 𝗔𝗟𝗟𝗢𝗪𝗘𝗗 𝗜𝗡 𝗧𝗛𝗜𝗦 𝗚𝗖.\n"
                                    f"🗑️ 𝗣𝗟𝗘𝗔𝗦𝗘 𝗥𝗘𝗩𝗜𝗘𝗪 & 𝗥𝗘𝗠𝗢𝗩𝗘 𝗧𝗛𝗘 𝗖𝗢𝗡𝗧𝗘𝗡𝗧.\n\n"
                                    f"👑 𝗔𝗗𝗠𝗜𝗡𝗦 ➜ {admin_tags_str}\n\n"
                                    f"╰┈➤ 🤖 𝗕𝗢𝗧 ➜ @{BOT_USERNAME}\n"
                                    f"╰┈➤ 👨‍💻 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ @{OWNER_USERNAME}"
                                )
                                cl.direct_send(adult_msg, thread_ids=[thread_id])
                                continue

                        # 4. COMMANDS LISTEN (KICK, STATUS, HELP)
                        if bot_tag in text:
                            if gc_admins and sender_id not in gc_admins:
                                cl.direct_send(
                                    f"⚠️ Access Denied! Only Group Admins can execute commands.\n👑 Owner: @{OWNER_USERNAME}",
                                    thread_ids=[thread_id]
                                )
                                continue

                            if "kick" in text or "remove" in text:
                                target_user = None
                                for part in text.split():
                                    if part.startswith("@") and part != bot_tag:
                                        target_user = part.replace("@", "")
                                        break

                                if target_user:
                                    for u in thread.users:
                                        if u.username.lower() == target_user.lower():
                                            try:
                                                cl.direct_thread_remove_user(thread_id, u.pk)
                                                kick_card = (
                                                    f"🚫 @{u.username} HAS BEEN KICKED OUT FROM THE GC!\n\n"
                                                    f"👑 Admin Action By Order | Owner: @{OWNER_USERNAME}"
                                                )
                                                cl.direct_send(kick_card, thread_ids=[thread_id])
                                            except Exception:
                                                cl.direct_send(f"❌ Execution Failed: Make sure Bot is Group Admin.", thread_ids=[thread_id])

                            elif "status" in text or "ping" in text:
                                status_card = (
                                    f"⚡ BOT STATUS: ONLINE (ULTRA MODE)\n"
                                    f"───────────────\n"
                                    f"🟢 System: Fully Operational\n"
                                    f"🛡️ Security: Active\n\n"
                                    f"👑 Owner: @{OWNER_USERNAME}"
                                )
                                cl.direct_send(status_card, thread_ids=[thread_id])

                            elif "help" in text:
                                help_card = (
                                    f"⚙️ ADMIN COMMANDS\n"
                                    f"───────────────\n"
                                    f"▫️ `@{BOT_USERNAME} kick @user` - Remove member\n"
                                    f"▫️ `@{BOT_USERNAME} status` - Check bot status\n"
                                    f"▫️ `@{BOT_USERNAME} help` - Show this menu\n\n"
                                    f"👑 Owner: @{OWNER_USERNAME}"
                                )
                                cl.direct_send(help_card, thread_ids=[thread_id])

        except Exception as e:
            print(f"[ERROR] {e}")

        time.sleep(3)  # 3 सेकंड का सुपर-फास्ट स्कैनिंग लूप




