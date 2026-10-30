import express from "express";
import { GoogleGenAI } from "@google/genai";

const app = express();
app.use(express.json({ limit: "20kb" }));

const PORT = process.env.PORT || 3000;
const GEMINI_API_KEY = process.env.GEMINI_API_KEY;

const ai = new GoogleGenAI({ apiKey: GEMINI_API_KEY });

app.get("/", (req, res) => {
    res.json({
        app: "SHIVAM AI OFFICIAL SDK",
        status: "ONLINE",
        developer: "SMW"
    });
});

app.post("/chat", async (req, res) => {
    try {
        if (!GEMINI_API_KEY) {
            return res.status(500).json({ 
                error: "GEMINI_API_KEY is missing in environment variables." 
            });
        }

        const message = req.body.message || req.body.prompt;

        if (!message || typeof message !== "string" || !message.trim()) {
            return res.status(400).json({ 
                error: "Please send a valid message." 
            });
        }

        // यहाँ मॉडल का नाम बदलकर 'gemini-2.5-flash' या 'gemini-1.5' कर दिया है जो नया SDK सपोर्ट करता है
        const response = await ai.models.generateContent({
            model: 'gemini-2.5-flash',
            contents: message.trim(),
        });

        const reply = response.text;

        if (!reply) {
            return res.status(502).json({ 
                error: "No response text received from Gemini SDK." 
            });
        }

        res.json({
            success: true,
            reply: reply.trim()
        });

    } catch (error) {
        console.error("Gemini SDK Error:", error);
        res.status(500).json({ 
            error: "Internal server error during AI processing: " + error.message 
        });
    }
});

app.listen(PORT, "0.0.0.0", () => {
    console.log(`SHIVAM AI SDK Server running on port ${PORT}`);
});
