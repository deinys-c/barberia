from flask import Blueprint, request, jsonify
from werkzeug.security import check_password_hash
from database import get_db

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/api/login', methods=['POST'])
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
        return jsonify({
            'mensaje': 'Login exitoso',
            'username': user['username'],
            'rol': user['rol'],
            'barbero_id': user['barbero_id']
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500