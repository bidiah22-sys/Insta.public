import os
import time
from instagrapi import Client

# ==========================================
# ⚙️ RAILWAY ENV CONFIGURATION & SAFETY CHECK
# ==========================================
BOT_USERNAME = os.getenv("BOT_USERNAME")
BOT_PASSWORD = os.getenv("BOT_PASSWORD")
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "fx_smw")

# सेफ्टी चेक: अगर रेलवे में डिटेल्स नहीं डाली हैं तो साफ़ एरर दिखेगा
if not BOT_USERNAME or not BOT_PASSWORD:
    print("[-] CRITICAL ERROR: BOT_USERNAME or BOT_PASSWORD is missing in Railway Variables!")
    exit(1)

cl = Client()
cl.delay_range = [1, 2]  # सुपर-फास्ट रिस्पॉन्स के लिए अल्ट्रा-लो डिले रेंज

print(f"[*] Connecting to Instagram as @{BOT_USERNAME}...")

login_success = False
try:
    cl.login(BOT_USERNAME, BOT_PASSWORD)
    print(f"[+] SUCCESS: Bot @{BOT_USERNAME} is LIVE at Maximum Speed! 🚀")
    login_success = True
except Exception as e:
    print(f"[-] LOGIN ERROR: {e}")

seen_message_ids = set()
group_members_state = {}
ever_seen_members = set()

if login_success:
    print("[*] Bot Active & Monitoring 100+ GC Network at Lightning Speed...")
    while True:
        try:
            # एक बार में ज्यादा चैट्स स्कैन करेंगे ताकि कोई ग्रुप छूटे नहीं
            threads = cl.direct_threads(amount=20)

            for thread in threads:
                if not thread.is_group:
                    continue

                thread_id = thread.id
                bot_tag = f"@{BOT_USERNAME.lower()}"

                # Admins Fetching
                gc_admins = []
                try:
                    if hasattr(thread, 'admin_user_ids') and thread.admin_user_ids:
                        gc_admins = [str(uid) for uid in thread.admin_user_ids]
                    elif hasattr(thread, 'admin_users') and thread.admin_users:
                        gc_admins = [str(getattr(admin, 'pk', admin)) for admin in thread.admin_users]
                except Exception:
                    gc_admins = []

                # INSTANT WELCOME & WELCOME BACK LOGIC
                try:
                    current_members = {user.pk for user in thread.users}

                    if thread_id in group_members_state:
                        old_members = group_members_state[thread_id]
                        newly_joined = current_members - old_members

                        for joined_pk in newly_joined:
                            user_obj = next((u for u in thread.users if u.pk == joined_pk), None)
                            if user_obj:
                                if joined_pk in ever_seen_members:
                                    welcome_card = (
                                        f"╭─ 🦋 𝗪𝗘𝗟𝗖𝗢𝗠𝗘 𝗕𝗔𝗖𝗞 @{user_obj.username} 🦋 ─╮\n\n"
                                        f"✨ 𝗕𝗔𝗖𝗞 𝗜𝗡 𝗧𝗛𝗘 𝗚𝗖! 💫\n"
                                        f"𝗠𝗜𝗦𝗦𝗘𝗗 𝗬𝗢𝗨, 𝗡𝗢𝗪 𝗟𝗘𝗧'𝗦 𝗩𝗜𝗕𝗘 😌🔥\n\n"
                                        f"📜 𝗙𝗢𝗟𝗟𝗢𝗪 𝗧𝗛𝗘 𝗥𝗨𝗟𝗘𝗦\n"
                                        f"🤝 𝗞𝗘𝗘𝗣 𝗜𝗧 𝗥𝗘𝗦𝗣𝗘𝗖𝗧𝗙𝗨𝗟\n\n"
                                        f"🦋 𝗚𝗟𝗔𝗗 𝗧𝗢 𝗛𝗔𝗩𝗘 𝗬𝗢𝗨 𝗕𝗔𝗖𝗞! ✨\n\n"
                                        f"🤖 Bot: @{BOT_USERNAME} | 👑 Owner: @{OWNER_USERNAME}"
                                    )
                                else:
                                    welcome_card = (
                                        f"╭─ 🦋 𝗪𝗘𝗟𝗖𝗢𝗠𝗘 @{user_obj.username} 🦋 ─╮\n\n"
                                        f"✨ 𝗚𝗟𝗔𝗗 𝗧𝗢 𝗛𝗔𝗩𝗘 𝗬𝗢𝗨 𝗛𝗘𝗥𝗘! 💫\n\n"
                                        f"📜 𝗙𝗢𝗟𝗟𝗢𝗪 𝗧𝗛𝗘 𝗚𝗖 𝗥𝗨𝗟𝗘𝗦\n"
                                        f"🤝 𝗞𝗘𝗘𝗣 𝗜𝗧 𝗥𝗘𝗦𝗣𝗘𝗖𝗧𝗙𝗨𝗟\n"
                                        f"⚡ 𝗡𝗢 𝗥𝗨𝗟𝗘 𝗕𝗥𝗘𝗔𝗞𝗜𝗡𝗚!\n\n"
                                        f"🚨 𝗥𝗨𝗟𝗘𝗦 𝗕𝗥𝗢𝗞𝗘𝗡 ➜ 𝗞𝗜𝗖𝗞 𝗢𝗨𝗧 🚪\n\n"
                                        f"💙 𝗦𝗧𝗔𝗬 𝗔𝗖𝗧𝗜𝗩𝗘 • 𝗘𝗡𝗝𝗢𝗬 • 𝗩𝗜𝗕𝗘 ✨\n\n"
                                        f"🤖 Bot: @{BOT_USERNAME} | 👑 Owner: @{OWNER_USERNAME}"
                                    )
                                    ever_seen_members.add(joined_pk)

                                cl.direct_send(welcome_card, thread_ids=[thread_id])
                    else:
                        ever_seen_members.update(current_members)

                    group_members_state[thread_id] = current_members
                except Exception:
                    pass

                # INSTANT MESSAGE SCANNER & COMMANDS
                try:
                    if thread.messages:
                        last_msg = thread.messages[0]
                        if last_msg.id not in seen_message_ids:
                            seen_message_ids.add(last_msg.id)
                            
                            if len(seen_message_ids) > 600:
                                seen_message_ids.pop()

                            text = str(last_msg.text or "").lower()
                            sender_id = str(last_msg.user_id)

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
                                        f"⚡ BOT STATUS: ULTRA-FAST ONLINE\n"
                                        f"───────────────\n"
                                        f"🟢 System: Maximum Speed Mode\n"
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
                except Exception:
                    pass

        except Exception as e:
            err_str = str(e)
            print(f"[LOOP ERROR] {err_str}")
            if "403" in err_str or "feedback_required" in err_str or "item_ack" in err_str:
                print("[!] Rate limit hit. Quick recovery in 6 seconds...")
                time.sleep(6)
            else:
                time.sleep(2)

        time.sleep(1)
