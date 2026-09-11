from datetime import datetime, timedelta
from flask import request, jsonify
from config import ZONA_HORARIA_VE, DIAS_ES
from database import get_db

def ahora_ve():
    """Devuelve la hora actual en Venezuela (UTC-4)."""
    return datetime.now(ZONA_HORARIA_VE)

def es_dia_habil(fecha_str):
    """Verifica si la fecha es Lunes a Sábado."""
    try:
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d')
        return fecha.weekday() < 6
    except ValueError:
        return False

def obtener_usuario_actual():
    """Obtiene el usuario autenticado desde el header X-Username."""
    username = request.headers.get('X-Username')
    if not username:
        return None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT id, username, rol, barbero_id, activo FROM usuarios WHERE username = %s AND activo = 1', (username,))
        user = cursor.fetchone()
        conn.close()
        return dict(user) if user else None
    except Exception:
        return None

def requiere_autenticacion():
    """Verifica que el usuario esté autenticado."""
    user = obtener_usuario_actual()
    if not user:
        return None, jsonify({'error': 'No autenticado'}), 401
    return user, None, None

def requiere_admin():
    """Verifica que el usuario sea admin."""
    user = obtener_usuario_actual()
    if not user:
        return None, jsonify({'error': 'No autenticado'}), 401
    if user['rol'] != 'admin':
        return None, jsonify({'error': 'Requiere permisos de administrador'}), 403
    return user, None, None

def actualizar_citas_pasadas():
    """Marca citas pasadas como realizadas/expiradas."""
    try:
        conn = get_db()
        cursor = conn.cursor()
        hoy = ahora_ve().strftime('%Y-%m-%d')
        cursor.execute("UPDATE citas SET estado = 'realizada' WHERE fecha < %s AND estado = 'confirmada'", (hoy,))
        cursor.execute("UPDATE citas SET estado = 'expirada' WHERE fecha < %s AND estado = 'pendiente_confirmacion'", (hoy,))
        conn.commit()
        conn.close()
    except Exception:
        pass