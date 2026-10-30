import express from "express";

const app = express();
app.use(express.json({ limit: "20kb" }));

const PORT = process.env.PORT || 3000;
const OPENROUTER_API_KEY = process.env.OPENROUTER_API_KEY;
const MODEL = "google/gemini-flash-1.5";

app.get("/", (req, res) => {
    res.json({
        app: "SHIVAM AI",
        status: "ONLINE",
        developer: "SMW"
    });
});

app.post("/chat", async (req, res) => {
    try {
        if (!OPENROUTER_API_KEY) {
            return res.status(500).json({ 
                error: "OpenRouter API key is not configured on the server." 
            });
        }

        const message = req.body.message || req.body.prompt;

        if (!message || typeof message !== "string" || !message.trim()) {
            return res.status(400).json({ 
                error: "Please send a valid message." 
            });
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
                    { 
                        role: "system", 
                        content: "You are SHIVAM AI, a personal assistant created by SMW. Reply naturally in Hindi, English or Hinglish." 
                    },
                    { 
                        role: "user", 
                        content: message.trim() 
                    }
                ],
                temperature: 0.7,
                max_tokens: 1000
            })
        });

        const data = await response.json();

        if (!response.ok) {
            console.error("OpenRouter API error:", data);
            return res.status(502).json({ 
                error: "AI service could not process the request." 
            });
        }

        const reply = data.choices?.[0]?.message?.content?.trim();

        if (!reply) {
            return res.status(502).json({ 
                error: "No response received from AI." 
            });
        }

        res.json({
            success: true,
            reply: reply
        });

    } catch (error) {
        console.error("Server error:", error);
        res.status(500).json({ 
            error: "Internal server error." 
        });
    }
});

app.listen(PORT, "0.0.0.0", () => {
    console.log(`SHIVAM AI server running on port ${PORT}`);
});
