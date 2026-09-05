const { IgApiClient } = require('instagram-private-api');
const fs = require('fs');

const BOT_USERNAME = process.env.BOT_USERNAME || 'bot222703';
const BOT_PASSWORD = process.env.BOT_PASSWORD || 'ananya295';
const OWNER_USERNAME = 'fx_smw';
const SESSION_FILE = 'session.json';

const ig = new IgApiClient();
ig.state.generateDevice(BOT_USERNAME);

let seenMessageIds = new Set();
let groupMembersState = {};
let everSeenMembers = new Set();

async function runBot() {
    console.log('[*] Connecting to Instagram...');
    try {
        if (fs.existsSync(SESSION_FILE)) {
            const savedSession = JSON.parse(fs.readFileSync(SESSION_FILE, 'utf8'));
            await ig.state.deserialize(savedSession);
            console.log('[*] Session Loaded!');
        } else {
            await ig.simulate.preLoginFlow();
            await ig.account.login(BOT_USERNAME, BOT_PASSWORD);
            process.nextTick(async () => await ig.simulate.postLoginFlow());

            const serialized = await ig.state.serialize();
            delete serialized.constants;
            fs.writeFileSync(SESSION_FILE, JSON.stringify(serialized));
            console.log('[+] Login Successful & Session Saved!');
        }

        console.log(`\n====================================`);
        console.log(` SUCCESS! Bot @${BOT_USERNAME} is ONLINE`);
        console.log(`====================================\n`);

        setInterval(async () => {
            try {
                const inbox = ig.feed.directInbox();
                const threads = await inbox.records();

                for (const thread of threads) {
                    if (!thread.is_group) continue;

                    const threadId = thread.thread_id;
                    const botTag = `@${BOT_USERNAME.toLowerCase()}`;

                    const currentMembers = new Set(thread.users.map(u => u.pk));
                    if (groupMembersState[threadId]) {
                        const oldMembers = groupMembersState[threadId];
                        for (const memberPk of currentMembers) {
                            if (!oldMembers.has(memberPk)) {
                                const userObj = thread.users.find(u => u.pk === memberPk);
                                if (userObj) {
                                    let msg = everSeenMembers.has(memberPk) 
                                        ? `╭─ 🦋 WELCOME BACK @${userObj.username} 🦋 ─╮\n\nGlad to have you back! ✨\n\n🤖 Bot: @${BOT_USERNAME} | 👑 Owner: @${OWNER_USERNAME}`
                                        : `╭─ 🦋 WELCOME @${userObj.username} 🦋 ─╮\n\nWelcome to GC! Follow rules & vibe ✨\n\n🤖 Bot: @${BOT_USERNAME} | 👑 Owner: @${OWNER_USERNAME}`;
                                    
                                    if (!everSeenMembers.has(memberPk)) everSeenMembers.add(memberPk);
                                    await ig.entity.directThread(threadId).broadcastText(msg);
                                }
                            }
                        }
                    } else {
                        currentMembers.forEach(pk => everSeenMembers.add(pk));
                    }
                    groupMembersState[threadId] = currentMembers;

                    if (thread.items && thread.items.length > 0) {
                        const lastMsg = thread.items[0];
                        if (!seenMessageIds.has(lastMsg.item_id) && lastMsg.text) {
                            seenMessageIds.add(lastMsg.item_id);
                            const text = lastMsg.text.toLowerCase();

                            if (text.includes(botTag)) {
                                if (text.includes('status') || text.includes('ping')) {
                                    await ig.entity.directThread(threadId).broadcastText(`⚡ BOT STATUS: ONLINE\n🟢 System: Fully Operational\n👑 Owner: @${OWNER_USERNAME}`);
                                } else if (text.includes('help')) {
                                    await ig.entity.directThread(threadId).broadcastText(`⚙️ ADMIN COMMANDS\n▫️ @${BOT_USERNAME} kick @user\n▫️ @${BOT_USERNAME} status\n▫️ @${BOT_USERNAME} help`);
                                }
                            }
                        }
                    }
                }
            } catch (err) {
                console.log('[Poll Error]:', err.message);
            }
        }, 10000);

    } catch (error) {
        console.log('[-] LOGIN ERROR:', error.message);
    }
}

runBot();
