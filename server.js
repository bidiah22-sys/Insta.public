import express from "express";

const app = express();
app.use(express.json({ limit: "50kb" }));

const PORT = process.env.PORT || 3000;
const GROQ_API_KEY = process.env.GROQ_API_KEY || process.env.GEMINI_API_KEY;

// सर्वर का हेल्थ चेक रूट
app.get("/", (req, res) => {
    res.json({
        app: "SHIVAM AI UNSTOPPABLE ENGINE",
        status: "ONLINE",
        developer: "SMW",
        timestamp: new Date().toISOString()
    });
});

// चैट एंडपॉइंट - सुपरफास्ट और स्टेबल
app.post("/chat", async (req, res) => {
    try {
        const message = req.body.message || req.body.prompt;

        if (!message || typeof message !== "string" || !message.trim()) {
            return res.status(400).json({ 
                success: false,
                error: "Please send a valid message string." 
            });
        }

        if (!GROQ_API_KEY) {
            return res.status(500).json({ 
                success: false,
                error: "API Key is missing in environment variables!" 
            });
        }

        // Groq API को डायरेक्ट और तेज कॉल
        const response = await fetch("https://api.groq.com/openai/v1/chat/completions", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${GROQ_API_KEY.trim()}`
            },
            body: JSON.stringify({
                model: "llama-3.1-8b-instant",
                messages: [
                    { 
                        role: "system", 
                        content: "You are SHIVAM AI, an ultra-advanced personal assistant created by SMW. Reply sharply, accurately, and naturally in Hindi, English, or Hinglish." 
                    },
                    { 
                        role: "user", 
                        content: message.trim() 
                    }
                ],
                temperature: 0.7,
                max_tokens: 2048
            })
        });

        const data = await response.json();

        if (!response.ok) {
            console.error("Groq API Error Response:", data);
            return res.status(502).json({ 
                success: false,
                error: data.error?.message || "Groq API rejected the request." 
            });
        }

        const reply = data.choices?.[0]?.message?.content?.trim();

        if (!reply) {
            return res.status(502).json({ 
                success: false,
                error: "Received empty response from AI model." 
            });
        }

        // सफलता का जवाब
        return res.json({
            success: true,
            reply: reply
        });

    } catch (error) {
        console.error("Critical Backend Error:", error);
        return res.status(500).json({ 
            success: false,
            error: "Internal Server Error: " + error.message 
        });
    }
});

app.listen(PORT, "0.0.0.0", () => {
    console.log(`🔥 SHIVAM AI Unstoppable Server running on port ${PORT}`);
});
