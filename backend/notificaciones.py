import logging
import requests
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_IDS

logging.basicConfig(
    filename='notificaciones.log',
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)

def _obtener_destinatarios(chat_id=None):
    """Devuelve la lista de destinatarios. Si se pasa chat_id, solo ese."""
    if chat_id:
        return [str(chat_id)]
    return TELEGRAM_CHAT_IDS

def enviar_telegram(mensaje, chat_id=None):
    """Envía un mensaje de texto por Telegram a todos los destinatarios."""
    if not TELEGRAM_TOKEN:
        print("[TELEGRAM] ERROR: TELEGRAM_TOKEN vacío")
        return False
    destinatarios = _obtener_destinatarios(chat_id)
    if not destinatarios:
        print("[TELEGRAM] ERROR: No hay destinatarios configurados")
        return False
    print(f"[TELEGRAM] Enviando a {len(destinatarios)} destinatario(s): {destinatarios}")
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    exito = False
    for dest in destinatarios:
        try:
            data = {"chat_id": str(dest), "text": mensaje, "parse_mode": "HTML"}
            response = requests.post(url, json=data, timeout=10)
            if response.status_code == 200:
                print(f"[TELEGRAM] ✅ Enviado a {dest}")
                exito = True
            else:
                print(f"[TELEGRAM] ❌ Error a {dest}: HTTP {response.status_code} - {response.text}")
                logging.error(f"Error Telegram a {dest}: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"[TELEGRAM] ❌ Excepción a {dest}: {e}")
            logging.error(f"Error Telegram a {dest}: {e}")
    return exito

def enviar_telegram_documento(nombre_archivo, contenido_str, caption="", chat_id=None):
    """Envía un archivo por Telegram (como documento) a todos los destinatarios."""
    if not TELEGRAM_TOKEN:
        print("[TELEGRAM] ERROR: TELEGRAM_TOKEN vacío")
        return False
    destinatarios = _obtener_destinatarios(chat_id)
    if not destinatarios:
        print("[TELEGRAM] ERROR: No hay destinatarios configurados")
        return False
    print(f"[TELEGRAM] Enviando documento a {len(destinatarios)} destinatario(s): {destinatarios}")
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
    exito = False
    for dest in destinatarios:
        try:
            files = {
                'document': (nombre_archivo, contenido_str.encode('utf-8'), 'application/json')
            }
            data = {
                'chat_id': str(dest),
                'caption': caption,
                'parse_mode': 'HTML'
            }
            response = requests.post(url, data=data, files=files, timeout=30)
            if response.status_code == 200:
                print(f"[TELEGRAM] ✅ Documento enviado a {dest}")
                exito = True
            else:
                print(f"[TELEGRAM] ❌ Error documento a {dest}: HTTP {response.status_code} - {response.text}")
                logging.error(f"Error documento a {dest}: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"[TELEGRAM] ❌ Excepción documento a {dest}: {e}")
            logging.error(f"Error documento a {dest}: {e}")
    return exito