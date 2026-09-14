from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Instancia global del limiter. Se inicializa en app.py
# Límite por defecto: 200 peticiones por minuto por IP
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per minute"],
    storage_uri="memory://"
)