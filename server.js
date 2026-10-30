import express from "express";

const app = express();
app.use(express.json({ limit: "20kb" }));

const PORT = process.env.PORT || 3000;
const OPENROUTER_API_KEY = process.env.OPENROUTER_API_KEY
;

let cachedModel = null;
let modelCacheTime = 0;

app.get("/", (req, res) => {
    res.json({
        app: "SHIVAM AI",
        status: "ONLINE",
        developer: "SMW"
    });
});

app.get("/health", (req, res) => {
    res.json({
        status: "OK",
        app: "SHIVAM AI",
        aiConfigured: Boolean(OPENROUTER_API_KEY)
    });
});

async function getAvailableModel() {
    if (cachedModel && Date.now() - modelCacheTime < 30 * 60 * 1000) {
        return cachedModel;
    }

    const response = await fetch(
        "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000",
        {
            headers: {
                "x-goog-api-key": OPENROUTER_API_KEY
            }
        }
    );

    const data = await response.json();

    if (!response.ok) {
        console.error("Gemini model-list error:", data);
        throw new Error("Unable to retrieve available Gemini models.");
    }

    const models = (data.models || []).filter(model =>
        (model.supportedGenerationMethods || []).includes("generateContent") &&
        /flash/i.test(model.name) &&
        !/image|tts|live|transcribe/i.test(model.name)
    );

    if (models.length === 0) {
        console.error("Available models:", data.models);
        throw new Error("No compatible Gemini Flash model is available.");
    }

    // Prefer the newest-looking model name from the API response.
    models.sort((a, b) => b.name.localeCompare(a.name));

    cachedModel = models[0].name.replace(/^models\//, "");
    modelCacheTime = Date.now();

    console.log("Selected Gemini model:", cachedModel);

    return cachedModel;
}

app.post("/chat", async (req, res) => {
    try {
        if (!OPENROUTER_API_KEY) {
            return res.status(500).json({
                error: "OPENROUTER_API_KEY is missing in Voroa environment variables."
            });
        }

        const message = req.body?.message;

        if (
            typeof message !== "string" ||
            !message.trim() ||
            message.length > 8000
        ) {
            return res.status(400).json({
                error: "Please send a valid message."
            });
        }

        const model = await getAvailableModel();

        const response = await fetch(
            `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`,
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "x-goog-api-key":OPENROUTER_API_KEY 
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

            if (response.status === 404 || response.status === 403) {
                cachedModel = null;
                modelCacheTime = 0;
            }

            return res.status(502).json({
                error: "Gemini could not process the request. Check server logs."
            });
        }

        const answer = data.candidates?.[0]?.content?.parts
            ?.map(part => part.text || "")
            .join("")
            .trim();

        if (!answer) {
            console.error("Empty Gemini response:", data);

            return res.status(502).json({
                error: "Gemini returned an empty response."
            });
        }

        return res.json({
            success: true,
            reply: answer,
            model: model
        });

    } catch (error) {
        console.error("SHIVAM AI error:", error);

        return res.status(502).json({
            error: error.message || "AI service is temporarily unavailable."
        });
    }
});

app.listen(PORT, "0.0.0.0", () => {
    console.log(`SHIVAM AI backend running on port ${PORT}`);
});
