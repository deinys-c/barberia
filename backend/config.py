import os
from datetime import timezone, timedelta

# Zona horaria Venezuela
ZONA_HORARIA_VE = timezone(timedelta(hours=-4))

# Telegram
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')  # string, puede tener varios separados por coma
TELEGRAM_CHAT_IDS = [x.strip() for x in TELEGRAM_CHAT_ID.split(',') if x.strip()]  # lista parseada

# Secret
SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-key-123')

# Constantes
DIAS_ES = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo']