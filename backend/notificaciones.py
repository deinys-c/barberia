import logging
import requests
import json
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

logging.basicConfig(
    filename='notificaciones.log',
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)

def enviar_telegram(mensaje, chat_id=None):
    """Envía un mensaje de texto por Telegram."""
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

def enviar_telegram_documento(nombre_archivo, contenido_str, caption="", chat_id=None):
    """Envía un archivo por Telegram (como documento)."""
    if not TELEGRAM_TOKEN:
        return False
    destinatario = chat_id or TELEGRAM_CHAT_ID
    if not destinatario:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
    try:
        files = {
            'document': (nombre_archivo, contenido_str.encode('utf-8'), 'application/json')
        }
        data = {
            'chat_id': str(destinatario),
            'caption': caption,
            'parse_mode': 'HTML'
        }
        response = requests.post(url, data=data, files=files, timeout=30)
        response.raise_for_status()
        logging.info(f"Backup enviado a Telegram: {nombre_archivo}")
        return True
    except Exception as e:
        logging.error(f"Error enviando documento a Telegram: {e}")
        return False