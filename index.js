const { IgApiClient } = require('instagram-private-api');

const ig = new IgApiClient();

async function startBot() {
    try {
        console.log("Starting smart bot login with admin check...");
        
        const username = process.env.INSTA_USERNAME;
        const password = process.env.INSTA_PASSWORD;

        if (!username || !password) {
            console.error("ERROR: Username or Password not found in Environment Variables!");
            return;
        }

        ig.state.generateDevice(username);
        await ig.account.login(username, password);
        console.log("Logged in successfully to Instagram!");

        const processedItems = new Set();
        const botUserId = ig.state.cookieUserId; // बोट की खुद की यूजर आईडी

        // सुपर-फास्ट स्कैनिंग लूप (हर 3 सेकंड)
        setInterval(async () => {
            try {
                const inbox = await ig.feed.directInbox().items();
                
                for (const thread of inbox) {
                    if (!thread.items || thread.items.length === 0) continue;
                    
                    const lastItem = thread.items[0];
                    const itemId = lastItem.item_id;

                    if (processedItems.has(itemId)) continue;
                    processedItems.add(itemId);

                    if (processedItems.size > 200) {
                        const firstKey = processedItems.keys().next().value;
                        processedItems.delete(firstKey);
                    }

                    const senderId = lastItem.user_id;
                    const text = lastItem.text || '';
                    const itemType = lastItem.item_type;

                    // अपने खुद के मैसेज इग्नोर करें
                    if (senderId === botUserId) continue;

                    // --- चेक करें कि क्या बोट इस ग्रुप का एडमिन है या नहीं ---
                    let isAdmin = false;
                    let adminTags = "@ADMIN";

                    try {
                        // थ्रेड के एडमिन यूजर आईडी की लिस्ट चेक करें
                        if (thread.admin_user_ids && thread.admin_user_ids.length > 0) {
                            if (thread.admin_user_ids.includes(botUserId)) {
                                isAdmin = true; // बोट एडमिन है
                            }
                            adminTags = thread.admin_user_ids.map(id => `@admin`).join(' ');
                        }
                    } catch (e) {
                        // अगर चेक करने में दिक्कत आए तो आगे बढ़ें
                    }

                    // अगर बोट ग्रुप का एडमिन नहीं है, तो यह ग्रुप मॉडरेट नहीं होगा (कोई एक्शन नहीं लेगा)
                    if (!isAdmin) {
                        continue; 
                    }

                    // --- 1. WELCOME / WELCOME BACK ---
                    if (itemType === 'user_joined' || text.toLowerCase().includes('/welcome')) {
                        const welcomeMsg = `🦋✨ 𝗪𝗘𝗟𝗖𝗢𝗠𝗘, @USER! ✨🦋\n\n🌸 𝗛𝗘𝗬! 𝗚𝗟𝗔𝗗 𝗧𝗢 𝗛𝗔𝗩𝗘 𝗬𝗢𝗨 𝗛𝗘𝗥𝗘 💫\n🤝 𝗦𝗧𝗔𝗬 𝗥𝗘𝗦𝗣𝗘𝗖𝗧𝗙𝗨𝗟 • 𝗙𝗢𝗟𝗟𝗢𝗪 𝗧𝗛𝗘 𝗥𝗨𝗟𝗘𝗦\n🔥 𝗘𝗡𝗝𝗢𝗬 𝗧𝗛𝗘 𝗚𝗖 • 𝗦𝗧𝗔𝗬 𝗔𝗖𝗧𝗜𝗩𝗘!\n\n╰┈➤ 🤖 𝗕𝗢𝗧 ➜ @bot222703\n╰┈➤ 👨‍💻 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ @fx_smw`;
                        await thread.broadcastText(welcomeMsg);
                        continue;
                    }

                    // --- 2. LINK BLOCKER ---
                    if (text.includes('http://') || text.includes('https://') || text.includes('www.') || text.includes('.com') || text.includes('t.me')) {
                        const linkMsg = `🚨🔗 𝗟𝗜𝗡𝗞 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗!\n\n👤 𝗨𝗦𝗘𝗥 ➜ @USER\n⚠️ 𝗨𝗡𝗔𝗨𝗧𝗛𝗢𝗥𝗜𝗭𝗘𝗗 𝗟𝗜𝗡𝗞 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗!\n🛑 𝗣𝗟𝗘𝗔𝗦𝗘 𝗗𝗢𝗡'𝗧 𝗦𝗘𝗡𝗗 𝗨𝗡𝗔𝗨𝗧𝗛𝗢𝗥𝗜𝗭𝗘𝗗 𝗟𝗜𝗡𝗞𝗦 𝗜𝗡 𝗧𝗛𝗘 𝗚𝗖.\n\n⚡ 𝗥𝗘𝗣𝗘𝗔𝗧𝗘𝗗 𝗩𝗜𝗢𝗟𝗔𝗧𝗜𝗢𝗡𝗦 𝗠𝗔𝗬 𝗟𝗘𝗔𝗗 𝗧𝗢 𝗔𝗖𝗧𝗜𝗢𝗡 🚫\n\n👑 𝗔𝗗𝗠𝗜𝗡𝗦 ➜ ${adminTags}\n\n╰┈➤ 🤖 𝗕𝗢𝗧 ➜ @bot222703\n╰┈➤ 👨‍💻 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ @fx_smw`;
                        await thread.broadcastText(linkMsg);
                        continue;
                    }

                    // --- 3. REELS / VIDEO BLOCKER ---
                    if (itemType === 'clip' || itemType === 'media' && lastItem.media?.media_type === 2 || text.includes('/reel/')) {
                        const reelMsg = `🚫🎬 𝗥𝗘𝗘𝗟𝗦 𝗡𝗢𝗧 𝗔𝗟𝗟𝗢𝗪𝗘𝗗!\n\n👤 @USER\n\n⚠️ 𝗥𝗘𝗘𝗟𝗦 / 𝗩𝗜𝗗𝗘𝗢𝗦 𝗔𝗥𝗘 𝗡𝗢𝗧 𝗔𝗟𝗟𝗢𝗪𝗘𝗗 𝗛𝗘𝗥𝗘.\n\n🛑 𝗣𝗟𝗘𝗔𝗦𝗘 𝗗𝗢𝗡'𝗧 𝗥𝗘𝗣𝗘𝗔𝗧!\n\n👑 𝗔𝗗𝗠𝗜𝗡𝗦 ➜ ${adminTags}\n\n🤖 𝗕𝗢𝗧 ➜ @bot222703\n👨‍💻 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ @fx_smw`;
                        await thread.broadcastText(reelMsg);
                        continue;
                    }

                    // --- 4. 18+ CONTENT / ABUSE ALERT ---
                    const restrictedWords = ['18+', 'adult', 'sex', 'xxx', 'porn', 'nude', 'gali'];
                    if (restrictedWords.some(word => text.toLowerCase().includes(word))) {
                        const adultMsg = `🚨🛡️ 𝗠𝗢𝗗𝗘𝗥𝗔𝗧𝗜𝗢𝗡 𝗔𝗟𝗘𝗥𝗧!\n\n👤 𝗨𝗦𝗘𝗥 ➜ @USER\n🔞 𝟭𝟴+ / 𝗔𝗚𝗘-𝗥𝗘𝗦𝗧𝗥𝗜𝗖𝗧𝗘𝗗 𝗖𝗢𝗡𝗧𝗘𝗡𝗧 𝗗𝗘𝗧𝗘𝗖𝗧𝗘𝗗!\n\n⚠️ 𝗨𝗡𝗔𝗣𝗣𝗥𝗢𝗣𝗥𝗜𝗔𝗧𝗘 𝗖𝗢𝗡𝗧𝗘𝗡𝗧 𝗜𝗦 𝗡𝗢𝗧 𝗔𝗟𝗟𝗢𝗪𝗘𝗗 𝗜𝗡 𝗧𝗛𝗜𝗦 𝗚𝗖.\n🗑️ 𝗣𝗟𝗘𝗔𝗦𝗘 𝗥𝗘𝗩𝗜𝗘𝗪 & 𝗥𝗘𝗠𝗢𝗩𝗘 𝗧𝗛𝗘 𝗖𝗢𝗡𝗧𝗘𝗡𝗧.\n\n👑 𝗔𝗗𝗠𝗜𝗡𝗦 ➜ ${adminTags}\n\n╰┈➤ 🤖 𝗕𝗢𝗧 ➜ @bot222703\n╰┈➤ 👨‍💻 𝗗𝗘𝗩𝗘𝗟𝗢𝗣𝗘𝗥 ➜ @fx_smw`;
                        await thread.broadcastText(adultMsg);
                        continue;
                    }
                }
            } catch (err) {
                // Background scan error ignore
            }
        }, 3000);

        setInterval(() => {
            console.log("Admin-verified security bot is running smoothly...");
        }, 60000);

    } catch (error) {
        console.error("LOGIN FAILED:", error.message);
    }
}

startBot();



