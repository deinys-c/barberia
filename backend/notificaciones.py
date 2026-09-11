import logging
import requests
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

logging.basicConfig(
    filename='notificaciones.log',
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)

def enviar_telegram(mensaje, chat_id=None):
    """Envía un mensaje por Telegram."""
    if not TELEGRAM_TOKEN:
        return False
    destinatario = chat_id or TELEGRAM_CHAT_ID
    if not destinatario:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": str(destinatario), "text": mensaje, "parse_mode": "HTML"}
    try:
        response = requests.post(url, json=data, timeout=10)
        response.raise_for_status()
        return True
    except Exception as e:
        logging.error(f"Error Telegram: {e}")
        return False