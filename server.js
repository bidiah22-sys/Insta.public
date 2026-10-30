import express from "express";

const app = express();

app.use(express.json({ limit: "20kb" }));

const PORT = process.env.PORT || 3000;
const GEMINI_API_KEY = process.env.GEMINI_API_KEY;
const MODEL = "gemini-2.5-flash";

app.get("/", (req, res) => {
    res.json({
        app: "SHIVAM AI",
        status: "ONLINE",
        developer: "SMW"
    });
});

app.post("/chat", async (req, res) => {
    try {
        if (!GEMINI_API_KEY) {
            return res.status(500).json({
                error: "AI backend is not configured."
            });
        }

        const message = req.body.message;

        if (
            typeof message !== "string" ||
            !message.trim() ||
            message.length > 8000
        ) {
            return res.status(400).json({
                error: "Please send a valid message."
            });
        }

        const response = await fetch(
            `https://generativelanguage.googleapis.com/v1beta/models/${MODEL}:generateContent`,
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "x-goog-api-key": GEMINI_API_KEY
                },
                body: JSON.stringify({
                    systemInstruction: {
                        parts: [{
                            text: "You are SHIVAM AI, a helpful personal AI assistant created by SMW. Reply naturally, accurately and respectfully. Support Hindi, English and Hinglish."
                        }]
                    },
                    contents: [{
                        role: "user",
                        parts: [{ text: message.trim() }]
                    }],
                    generationConfig: {
                        temperature: 0.7,
                        maxOutputTokens: 1200
                    }
                })
            }
        );

        const data = await response.json();

        if (!response.ok) {
            console.error("Gemini API error:", data);
            return res.status(502).json({
                error: "AI service could not process the request."
            });
        }

        const answer =
            data.candidates?.[0]?.content?.parts
                ?.map(part => part.text || "")
                .join("")
                .trim();

        if (!answer) {
            return res.status(502).json({
                error: "No AI response received."
            });
        }

        res.json({
            success: true,
            reply: answer
        });

    } catch (error) {
        console.error("Server error:", error);

        res.status(500).json({
            error: "Internal server error."
        });
    }
});

app.listen(PORT, "0.0.0.0", () => {
    console.log(`SHIVAM AI backend running on port ${PORT}`);
});
