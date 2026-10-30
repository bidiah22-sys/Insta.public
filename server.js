const express = require('express');
const app = express();

app.use(express.json({ limit: "20kb" }));

const PORT = process.env.PORT || 3000;
const OPENROUTER_API_KEY = process.env.OPENROUTER_API_KEY;
const MODEL = "google/gemini-flash-1.5";

// In-memory storage for Smart Memory module
let smartMemories = [];

app.get("/", (req, res) => {
    res.json({
        app: "SHIVAM AI CONTROL CENTER",
        status: "ONLINE",
        developer: "SMW",
        activeModules: [
            "AI Chat", 
            "Voice AI", 
            "Smart Memory", 
            "Internet", 
            "AI Coding", 
            "Call Assist"
        ]
    });
});

// Unified Handler for OpenRouter AI requests
async function handleAIRequest(req, res, systemPrompt) {
    try {
        if (!OPENROUTER_API_KEY) {
            return res.status(500).json({ error: "OpenRouter API key is not configured on the server." });
        }

        const message = req.body.message || req.body.query;

        if (!message || typeof message !== "string" || !message.trim()) {
            return res.status(400).json({ error: "Please send a valid message." });
        }

        const response = await fetch("https://openrouter.ai/api/v1/chat/completions", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${OPENROUTER_API_KEY}`,
                "HTTP-Referer": "https://github.com/shivam",
                "X-Title": "SHIVAM AI"
            },
            body: JSON.stringify({
                model: MODEL,
                messages: [
                    { role: "system", content: systemPrompt },
                    { role: "user", content: message.trim() }
                ],
                temperature: 0.7,
                max_tokens: 1200
            })
        });

        const data = await response.json();

        if (!response.ok) {
            console.error("OpenRouter API error:", data);
            return res.status(502).json({ error: "AI service could not process the request." });
        }

        const answer = data.choices?.[0]?.message?.content?.trim();

        if (!answer) {
            return res.status(502).json({ error: "No AI response received." });
        }

        res.json({
            success: true,
            reply: answer
        });

    } catch (error) {
        console.error("Server error:", error);
        res.status(500).json({ error: "Internal server error." });
    }
}

// 1. AI Chat Module
app.post("/chat", async (req, res) => {
    await handleAIRequest(req, res, "You are SHIVAM AI, a helpful personal assistant created by SMW. Reply naturally in Hindi, English or Hinglish.");
});

// 2. Voice AI Module
app.post("/voice", async (req, res) => {
    await handleAIRequest(req, res, "You are Voice AI inside SHIVAM AI app. Give concise, direct, speech-friendly replies.");
});

// 3. Smart Memory Module (Save Memory)
app.post("/memory/save", (req, res) => {
    const { memory } = req.body;
    if (memory && memory.trim()) {
        smartMemories.push({ text: memory.trim(), time: new Date() });
        res.json({ success: true, message: "Memory saved successfully!" });
    } else {
        res.status(400).json({ error: "Memory text is required." });
    }
});

// Smart Memory Module (List Memories)
app.get("/memory/list", (req, res) => {
    res.json({ success: true, memories: smartMemories });
});

// 4. Internet Search / Lookup Module
app.post("/internet", async (req, res) => {
    const query = req.body.message || req.body.query;
    await handleAIRequest(req, res, `You are Internet search assistant for SHIVAM AI. Provide up-to-date and factual info for: ${query}`);
});

// 5. AI Coding Module
app.post("/coding", async (req, res) => {
    await handleAIRequest(req, res, "You are an expert AI Coding assistant for SHIVAM AI. Write clean, bug-free code snippets and explanations.");
});

// 6. Call Assist Module
app.post("/call-assist", async (req, res) => {
    await handleAIRequest(req, res, "You are Call Assist expert for SHIVAM AI. Provide professional call scripts and summaries.");
});

app.listen(PORT, "0.0.0.0", () => {
    console.log(`SHIVAM AI Master Control Center running on port ${PORT}`);
});
