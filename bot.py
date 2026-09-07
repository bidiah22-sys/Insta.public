
import os
from flask import Flask, request

app = Flask(__name__)

VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "Instagram 123")

@app.route("/", methods=["GET"])
def home():
    return "Instagram Bot Server is Live and Running!", 200

@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")

        if mode and token:
            if mode == "subscribe" and token == VERIFY_TOKEN:
                print("WEBHOOK_VERIFIED: Successfully verified by Meta!")
                return challenge, 200
            else:
                print(f"VERIFICATION_FAILED: Expected token '{VERIFY_TOKEN}', got '{token}'")
                return "Verification failed", 403
        return "Hello World", 200

    elif request.method == "POST":
        data = request.json
        print("Incoming Webhook Data:", data)
        return "EVENT_RECEIVED", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
