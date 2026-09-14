from flask import Blueprint, request, jsonify
from werkzeug.security import check_password_hash
from datetime import datetime, timedelta, timezone
import jwt
from database import get_db
from config import SECRET_KEY, JWT_EXPIRATION_HOURS
from extensions import limiter
from helpers import respuesta_error

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/api/login', methods=['POST'])
@limiter.limit("10 per minute")
def login():
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '')
    if not username or not password:
        return jsonify({'error': 'Usuario y contraseña requeridos'}), 400
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT id, username, password_hash, rol, barbero_id FROM usuarios WHERE username = %s AND activo = 1', (username,))
        user = cursor.fetchone()
        conn.close()
        if not user or not check_password_hash(user['password_hash'], password):
            return jsonify({'error': 'Usuario o contraseña incorrectos'}), 401

        # Generar token JWT
        payload = {
            'username': user['username'],
            'rol': user['rol'],
            'barbero_id': user['barbero_id'],
            'exp': datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS)
        }
        token = jwt.encode(payload, SECRET_KEY, algorithm='HS256')

        return jsonify({
            'mensaje': 'Login exitoso',
            'token': token,
            'username': user['username'],
            'rol': user['rol'],
            'barbero_id': user['barbero_id']
        })
    except Exception as e:
        return respuesta_error(e, 'Login')