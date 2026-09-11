import os
from datetime import timezone, timedelta

# Zona horaria Venezuela
ZONA_HORARIA_VE = timezone(timedelta(hours=-4))

# Telegram
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')

# Secret
SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-key-123')

# Constantes
DIAS_ES = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo']