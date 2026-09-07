from flask import Flask, request, jsonify

app = Flask(__name__)

# प्राइवेसी पॉलिसी का राउट (मेटा वेरिफिकेशन के लिए)
@app.route('/privacy.html')
def privacy_policy():
    return """
    <!DOCTYPE html>
    <html>
    <head><title>Privacy Policy</title></head>
    <body style="font-family: Arial; padding: 40px;">
        <h1>Privacy Policy</h1>
        <p>This application is used solely for testing and interacting with Instagram webhooks.</p>
    </body>
    </html>
    """

# होम पेज चेक करने के लिए
@app.route('/', methods=['GET'])
def home():
    return "Instagram Bot Server is Live and Running!", 200

# वेबहुक का फाइनल और फिक्स टोकन (Instagram 123)
VERIFY_TOKEN = "Instagram 123"

@app.route('/webhook', methods=['GET'])
def verify_webhook():
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')
    
    if mode and token:
        if mode == 'subscribe' and token == VERIFY_TOKEN:
            print("WEBHOOK_VERIFIED: Successfully verified by Meta!")
            return challenge, 200
        else:
            print(f"VERIFICATION_FAILED: Expected token '{VERIFY_TOKEN}', got '{token}'")
            return "Verification failed", 403
    return "Hello World", 200

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    data = request.get_json()
    print("Received webhook data:", data)
    return "EVENT_RECEIVED", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)


