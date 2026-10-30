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

        let response;
        let attempts = 3;
        
        // हाई डिमांड (503) आने पर खुद से 3 बार कोशिश करने वाला लूप
        for (let i = 0; i < attempts; i++) {
            try {
                response = await ai.models.generateContent({
                    model: 'gemini-1.5-flash',
                    contents: message.trim(),
                });
                break; // अगर सफलता मिल गई तो लूप से बाहर आ जाओ
            } catch (err) {
                if (i === attempts - 1) throw err; // अगर आखिरी कोशिश भी फेल हो, तो एरर फेंको
                await new Promise(resolve => setTimeout(resolve, 1500)); // 1.5 सेकंड रुककर दोबारा ट्राई करो
            }
        }

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
            error: "AI service is busy right now. Please try again in a moment." 
        });
    }
});

app.listen(PORT, "0.0.0.0", () => {
    console.log(`SHIVAM AI SDK Server running on port ${PORT}`);
});
