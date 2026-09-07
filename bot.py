import os
from flask import Flask, request

app = Flask(__name__)


@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
  if request.method == 'GET':
    # Meta verification check
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')

    # Yahi token tera Railway variables wala token match karega
    verify_token = os.environ.get('VERIFY_TOKEN', 'bot123')

    if mode == 'subscribe' and token == verify_token:
      return challenge, 200
    else:
      return 'Verification failed', 403

  elif request.method == 'POST':
    data = request.json
    print(data)
    return 'EVENT_RECEIVED', 200


if __name__ == '__main__':
  port = int(os.environ.get('PORT', 3000))
  app.run(host='0.0.0.0', port=port)

