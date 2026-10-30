import express from "express";

const app = express();
app.use(express.json({ limit: "20kb" }));

const PORT = process.env.PORT || 3000;
const GROQ_API_KEY = process.env.GROQ_API_KEY || process.env.GEMINI_API_KEY;

app.get("/", (req, res) => {
    res.json({
        app: "SHIVAM AI ULTIMATE ENGINE",
        status: "ONLINE",
        developer: "SMW"
    });
});

app.post("/chat", async (req, res) => {
    try {
        const message = req.body.message || req.body.prompt;

        if (!message || typeof message !== "string" || !message.trim()) {
            return res.status(400).json({ 
                error: "Please send a valid message." 
            });
        }

        const response = await fetch("https://api.groq.com/openai/v1/chat/completions", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${GROQ_API_KEY}`
            },
            body: JSON.stringify({
                model: "llama-3.1-8b-instant",
                messages: [
                    { role: "system", content: "You are SHIVAM AI, an ultra-fast personal assistant created by SMW. Reply quickly and naturally in Hindi, English or Hinglish." },
                    { role: "user", content: message.trim() }
                ],
                temperature: 0.7,
                max_tokens: 1024
            })
        });

        const data = await response.json();

        if (!response.ok) {
            console.error("Groq API error:", data);
            return res.status(502).json({ 
                error: data.error?.message || "AI service could not process the request." 
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
            error: "Internal server error: " + error.message 
        });
    }
});

app.listen(PORT, "0.0.0.0", () => {
    console.log(`SHIVAM AI Ultimate Server running on port ${PORT}`);
});
