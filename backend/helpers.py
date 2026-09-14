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
    """Obtiene el usuario autenticado desde el header Authorization: Bearer <token>."""
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return None
    token = auth_header[7:].strip()
    if not token:
        return None
    try:
        import jwt
        from config import SECRET_KEY
        payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
        # Verificar que el usuario siga existiendo y activo
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT id, username, rol, barbero_id, activo FROM usuarios WHERE username = %s AND activo = 1', (payload.get('username'),))
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

def respuesta_error(e, contexto):
    """Registra el error real en logs y devuelve un mensaje genérico al cliente."""
    import traceback
    print(f"[ERROR] {contexto}: {type(e).__name__} - {e}")
    traceback.print_exc()
    return jsonify({'error': 'Error interno del servidor'}), 500

def validar_entero(valor, nombre, minimo=None, maximo=None):
    """Valida que un valor sea entero dentro de un rango. Devuelve (ok, valor_o_error)."""
    try:
        n = int(valor)
    except (ValueError, TypeError):
        return False, f'{nombre} debe ser un número entero'
    if minimo is not None and n < minimo:
        return False, f'{nombre} debe ser mayor o igual a {minimo}'
    if maximo is not None and n > maximo:
        return False, f'{nombre} debe ser menor o igual a {maximo}'
    return True, n


def validar_decimal(valor, nombre, minimo=None, maximo=None):
    """Valida que un valor sea decimal dentro de un rango."""
    try:
        n = float(valor)
    except (ValueError, TypeError):
        return False, f'{nombre} debe ser un número'
    if minimo is not None and n < minimo:
        return False, f'{nombre} debe ser mayor o igual a {minimo}'
    if maximo is not None and n > maximo:
        return False, f'{nombre} debe ser menor o igual a {maximo}'
    return True, n


def validar_hora(valor, nombre, opcional=False):
    """Valida que un valor sea una hora en formato HH:MM."""
    if not valor:
        if opcional:
            return True, None
        return False, f'{nombre} es obligatorio'
    s = str(valor).strip()
    try:
        partes = s.split(':')
        if len(partes) != 2:
            raise ValueError
        h, m = int(partes[0]), int(partes[1])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError
        return True, f'{h:02d}:{m:02d}'
    except (ValueError, TypeError):
        return False, f'{nombre} debe estar en formato HH:MM (ej: 08:30)'


def validar_fecha(valor, nombre, opcional=False):
    """Valida que un valor sea una fecha en formato YYYY-MM-DD."""
    if not valor:
        if opcional:
            return True, None
        return False, f'{nombre} es obligatorio'
    s = str(valor).strip()
    from datetime import datetime
    try:
        datetime.strptime(s, '%Y-%m-%d')
        return True, s
    except (ValueError, TypeError):
        return False, f'{nombre} debe estar en formato YYYY-MM-DD'


def validar_longitud(valor, nombre, minimo=0, maximo=255):
    """Valida la longitud de un texto."""
    if valor is None:
        valor = ''
    s = str(valor)
    if len(s) < minimo:
        return False, f'{nombre} debe tener al menos {minimo} caracteres'
    if len(s) > maximo:
        return False, f'{nombre} debe tener máximo {maximo} caracteres'
    return True, s