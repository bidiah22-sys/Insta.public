const { IgApiClient } = require('instagram-private-api');

const ig = new IgApiClient();

async function startBot() {
    try {
        console.log("Starting bot login...");
        
        const username = process.env.INSTA_USERNAME;
        const password = process.env.INSTA_PASSWORD;

        if (!username || !password) {
            console.error("ERROR: Username or Password not found in Environment Variables!");
            return;
        }

        ig.state.generateDevice(username);
        
        await ig.account.login(username, password);
        console.log("Logged in successfully to Instagram!");

        // बोट चालू रहेगा
        setInterval(() => {
            console.log("Bot is running smoothly...");
        }, 60000);

    } catch (error) {
        console.error("LOGIN FAILED:", error.message);
    }
}

startBot();


