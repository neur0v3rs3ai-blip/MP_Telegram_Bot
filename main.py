from flask import Flask, request, jsonify
import os, uuid, time, requests

app = Flask(__name__)

MP_ACCESS_TOKEN = os.environ.get('MP_ACCESS_TOKEN')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
TELEGRAM_GROUP_ID = os.environ.get('TELEGRAM_GROUP_ID')  # ex: -1001234567890
BASE_MP = "https://api.mercadopago.com"
BASE_TG = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

def create_mp_payment(amount, description, external_reference, notification_url, payer_email="no-reply@example.com"):
    headers = {
        "Authorization": f"Bearer {MP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
        "X-Idempotency-Key": uuid.uuid4().hex
    }
    payload = {
        "transaction_amount": float(amount),
        "description": description,
        "payment_method_id": "pix",
        "payer": {"email": payer_email},
        "external_reference": external_reference,
        "notification_url": notification_url
    }
    r = requests.post(f"{BASE_MP}/v1/payments", json=payload, headers=headers)
    r.raise_for_status()
    return r.json()

def create_invite_link(expire_seconds=86400, member_limit=1):
    expire_date = int(time.time()) + expire_seconds
    resp = requests.post(f"{BASE_TG}/createChatInviteLink", json={
        "chat_id": TELEGRAM_GROUP_ID,
        "expire_date": expire_date,
        "member_limit": member_limit
    })
    resp.raise_for_status()
    return resp.json()["result"]["invite_link"]

def send_telegram_message(chat_id, text):
    r = requests.post(f"{BASE_TG}/sendMessage", json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True})
    r.raise_for_status()
    return r.json()

@app.route('/telegram_webhook', methods=['POST'])
def telegram_webhook():
    data = request.json
    message = data.get('message') or data.get('edited_message')
    if not message: return jsonify({}), 200
    chat_id = message['from']['id']
    text = message.get('text','')
    if text and text.startswith('/comprar'):
        amount = 20.0  # ajuste aqui ou parseie o comando
        description = "Acesso ao grupo VIP"
        external_reference = f"tg:{chat_id}:{uuid.uuid4().hex}"
        notification_url = os.environ.get('WEBHOOK_MP')  # setado nas envs do Render
        mp = create_mp_payment(amount, description, external_reference, notification_url, payer_email="no-reply@example.com")
        ticket = mp.get("point_of_interaction", {}).get("transaction_data", {}).get("ticket_url")
        if ticket:
            send_telegram_message(chat_id, f"Pague com Pix aqui: {ticket}\nApós o pagamento o link será enviado automaticamente.")
        else:
            send_telegram_message(chat_id, "Erro ao gerar link de pagamento. Tente novamente.")
    return jsonify({}), 200

@app.route('/webhook/mp', methods=['POST'])
def mp_webhook():
    event = request.json
    payment_id = event.get('data', {}).get('id')
    if not payment_id: return jsonify({}), 400
    headers = {"Authorization": f"Bearer {MP_ACCESS_TOKEN}"}
    r = requests.get(f"{BASE_MP}/v1/payments/{payment_id}", headers=headers)
    r.raise_for_status()
    payment = r.json()
    status = payment.get('status')
    external_reference = payment.get('external_reference')
    if status == 'approved' and external_reference and external_reference.startswith('tg:'):
        parts = external_reference.split(':')
        chat_id = parts[1]
        try:
            link = create_invite_link(expire_seconds=24*3600, member_limit=1)
            send_telegram_message(chat_id, f"Pagamento confirmado ✅\nAqui está seu link de entrada: {link}")
        except Exception:
            send_telegram_message(chat_id, "Pagamento confirmado, mas houve erro ao gerar convite. Contate o administrador.")
    return jsonify({}), 200

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
