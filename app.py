import os
import json
import logging
import threading
import time
import jwt
from datetime import datetime, timedelta, date
from flask import Flask, request, jsonify, session
from flask_cors import CORS
from database import get_db, init_db
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('JWT_SECRET', 'mi_clave_secreta_por_defecto')
CORS(app, supports_credentials=True)

# Configurar logging
logging.basicConfig(
    filename='notificaciones.log',
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)

# Variables de entorno
SIMULAR_FALLO_NOTIFICACION = os.environ.get('SIMULAR_FALLO', 'False').lower() == 'true'
TIEMPO_ESPERA_FALLO_MIN = int(os.environ.get('TIEMPO_ESPERA', '20'))
NUMERO_PRUEBA_VENEZUELA = os.environ.get('NUMERO_PRUEBA', '+584241234567')

# Inicializar base de datos
init_db()

# ---------- FUNCIONES AUXILIARES ----------
def es_dia_habil(fecha_str):
    try:
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        return fecha.weekday() < 6  # Lunes(0) a Sábado(5)
    except:
        return False

def calcular_huecos_libres(fecha_str, barbero_id=1):
    conn = get_db()
    cursor = conn.cursor()

    if not es_dia_habil(fecha_str):
        conn.close()
        return []

    barbero = cursor.execute(
        'SELECT hora_inicio, hora_fin FROM barberos WHERE id = ?',
        (barbero_id,)
    ).fetchone()
    if not barbero:
        conn.close()
        return []

    inicio = datetime.strptime(barbero['hora_inicio'], '%H:%M').time()
    fin = datetime.strptime(barbero['hora_fin'], '%H:%M').time()
    fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()

    # Verificar bloqueos
    bloqueo = cursor.execute('''
        SELECT 1 FROM bloqueos 
        WHERE barbero_id = ? AND activo = 1 
        AND fecha_inicio <= ? AND fecha_fin >= ?
    ''', (barbero_id, fecha_str, fecha_str)).fetchone()
    if bloqueo:
        conn.close()
        return []

    # Obtener citas ocupadas
    citas = cursor.execute('''
        SELECT hora_inicio FROM citas 
        WHERE barbero_id = ? AND fecha = ? 
        AND estado IN ('confirmada', 'pendiente_confirmacion')
    ''', (barbero_id, fecha_str)).fetchall()
    ocupados = {c['hora_inicio'] for c in citas}

    disponibles = []
    hora_actual = datetime.combine(fecha, inicio)
    hora_fin = datetime.combine(fecha, fin)

    while hora_actual < hora_fin:
        hora_str = hora_actual.strftime('%H:%M')
        if hora_str not in ocupados:
            disponibles.append(hora_str)
        hora_actual += timedelta(minutes=30)

    conn.close()
    return disponibles

def generar_token(barbero_id):
    """Genera un token JWT para el barbero."""
    payload = {
        'barbero_id': barbero_id,
        'exp': datetime.utcnow() + timedelta(hours=24)  # Expira en 24h
    }
    return jwt.encode(payload, app.secret_key, algorithm='HS256')

def verificar_token(token):
    """Verifica el token JWT y devuelve el barbero_id si es válido."""
    try:
        payload = jwt.decode(token, app.secret_key, algorithms=['HS256'])
        return payload.get('barbero_id')
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

# ---------- ENDPOINTS ----------
@app.route('/')
def home():
    return jsonify({'mensaje': 'API Barbería funcionando', 'status': 'ok'})

@app.route('/api/disponibilidad', methods=['GET'])
def disponibilidad():
    fecha = request.args.get('fecha')
    if not fecha:
        return jsonify({'error': 'Falta fecha'}), 400
    try:
        disponibles = calcular_huecos_libres(fecha)
        return jsonify({'disponibles': disponibles, 'fecha': fecha, 'total': len(disponibles)})
    except Exception as e:
        logging.error(f"Error en disponibilidad: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/reservar', methods=['POST'])
def reservar():
    data = request.json
    required = ['fecha', 'hora_inicio', 'servicio_id', 'nombre']
    if not all(k in data for k in required):
        return jsonify({'error': 'Faltan datos obligatorios'}), 400

    try:
        fecha = data['fecha']
        hora_inicio = data['hora_inicio']
        servicio_id = int(data['servicio_id'])
        nombre = data['nombre'].strip()
        telefono = data.get('telefono', '').strip()
        notas = data.get('notas', '').strip()

        conn = get_db()
        cursor = conn.cursor()

        # Obtener duración del servicio
        servicio = cursor.execute(
            'SELECT duracion_minutos FROM servicios WHERE id = ? AND activo = 1',
            (servicio_id,)
        ).fetchone()
        if not servicio:
            conn.close()
            return jsonify({'error': 'Servicio no válido'}), 400

        duracion = servicio['duracion_minutos']
        h, m = map(int, hora_inicio.split(':'))
        total_min = h * 60 + m + duracion
        hora_fin = f"{total_min // 60:02d}:{total_min % 60:02d}"
        alerta_cierre = 1 if total_min > 17 * 60 else 0

        ahora = datetime.now()
        fecha_hora_cita = datetime.strptime(f"{fecha} {hora_inicio}", "%Y-%m-%d %H:%M")
        diff_min = (fecha_hora_cita - ahora).total_seconds() / 60
        tipo_reserva = 'urgente' if diff_min < 60 else 'normal'
        estado = 'confirmada' if tipo_reserva == 'normal' else 'pendiente_confirmacion'

        # Verificar disponibilidad
        ocupado = cursor.execute('''
            SELECT 1 FROM citas 
            WHERE barbero_id = 1 AND fecha = ? AND hora_inicio = ? 
            AND estado IN ('confirmada', 'pendiente_confirmacion')
        ''', (fecha, hora_inicio)).fetchone()
        if ocupado:
            conn.close()
            return jsonify({'error': 'El hueco ya no está disponible'}), 409

        # Cliente
        cliente = cursor.execute(
            'SELECT id FROM clientes WHERE nombre = ? AND telefono = ?',
            (nombre, telefono)
        ).fetchone()
        if cliente:
            cliente_id = cliente['id']
        else:
            cursor.execute(
                'INSERT INTO clientes (nombre, telefono, notas_habituales) VALUES (?, ?, ?)',
                (nombre, telefono, notas)
            )
            cliente_id = cursor.lastrowid

        # Insertar cita
        cursor.execute('''
            INSERT INTO citas 
            (barbero_id, cliente_id, servicio_id, fecha, hora_inicio, hora_fin, 
             estado, tipo_reserva, alerta_cierre, notas_cliente)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (cliente_id, servicio_id, fecha, hora_inicio, hora_fin,
              estado, tipo_reserva, alerta_cierre, notas))
        cita_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Notificaciones (simuladas)
        if tipo_reserva == 'urgente':
            mensaje = f"Solicitud URGENTE de {nombre} para {fecha} a las {hora_inicio}"
            # Simular notificación
            logging.info(f"Notificación enviada a {NUMERO_PRUEBA_VENEZUELA}: {mensaje}")
            # Simular fallo si está activado
            if SIMULAR_FALLO_NOTIFICACION:
                # Programar cancelación automática
                def programar_cancelacion():
                    time.sleep(TIEMPO_ESPERA_FALLO_MIN * 60)
                    conn2 = get_db()
                    cur2 = conn2.cursor()
                    cita = cur2.execute('SELECT estado FROM citas WHERE id = ?', (cita_id,)).fetchone()
                    conn2.close()
                    if cita and cita['estado'] == 'pendiente_confirmacion':
                        cancelar_cita_por_sistema(cita_id)
                threading.Thread(target=programar_cancelacion, daemon=True).start()
                return jsonify({
                    'mensaje': 'Solicitud urgente enviada (simulación fallo)',
                    'citaId': cita_id,
                    'estado': 'pendiente_confirmacion'
                })
            else:
                return jsonify({
                    'mensaje': 'Solicitud urgente enviada. Esperando confirmación.',
                    'citaId': cita_id,
                    'estado': 'pendiente_confirmacion'
                })
        else:
            return jsonify({
                'mensaje': '✅ ¡Cita agendada exitosamente!',
                'citaId': cita_id,
                'estado': 'confirmada'
            })

    except Exception as e:
        logging.error(f"Error en reservar: {str(e)}")
        return jsonify({'error': f'Error interno: {str(e)}'}), 500

# ---------- AUTENTICACIÓN BARBERO ----------
@app.route('/api/panel/login', methods=['POST'])
def login_barbero():
    data = request.json
    password = data.get('password', '')
    # La contraseña se lee del .env o usa la default
    password_correcta = os.getenv('BARBERO_PASSWORD', 'barberia2026')
    if password == password_correcta:
        token = generar_token(1)  # barbero_id = 1
        return jsonify({'mensaje': 'Login exitoso', 'token': token, 'autenticado': True})
    return jsonify({'error': 'Contraseña incorrecta'}), 401

@app.route('/api/panel/verificar', methods=['GET'])
def verificar_sesion():
    token = request.headers.get('Authorization')
    if token and token.startswith('Bearer '):
        token = token[7:]
        barbero_id = verificar_token(token)
        if barbero_id:
            return jsonify({'autenticado': True})
    return jsonify({'autenticado': False}), 401

@app.route('/api/panel/logout', methods=['POST'])
def logout_barbero():
    # No necesitamos hacer nada especial con JWT, solo el frontend elimina el token
    return jsonify({'mensaje': 'Sesión cerrada'})

# ---------- ENDPOINTS DEL PANEL ----------
@app.route('/api/panel/pendientes', methods=['GET'])
def listar_pendientes():
    token = request.headers.get('Authorization')
    if not token or not token.startswith('Bearer '):
        return jsonify({'error': 'No autorizado'}), 401
    token = token[7:]
    if not verificar_token(token):
        return jsonify({'error': 'Token inválido o expirado'}), 401

    try:
        conn = get_db()
        cursor = conn.cursor()
        citas = cursor.execute('''
            SELECT c.id, c.fecha, c.hora_inicio, c.hora_fin, c.estado, c.tipo_reserva,
                   cl.nombre as cliente, cl.telefono, s.nombre as servicio,
                   c.alerta_cierre, c.notas_cliente
            FROM citas c
            JOIN clientes cl ON c.cliente_id = cl.id
            JOIN servicios s ON c.servicio_id = s.id
            WHERE c.estado = 'pendiente_confirmacion'
            ORDER BY c.fecha, c.hora_inicio
        ''').fetchall()
        conn.close()
        return jsonify([dict(c) for c in citas])
    except Exception as e:
        logging.error(f"Error en pendientes: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/panel/historial', methods=['GET'])
def historial_citas():
    token = request.headers.get('Authorization')
    if not token or not token.startswith('Bearer '):
        return jsonify({'error': 'No autorizado'}), 401
    token = token[7:]
    if not verificar_token(token):
        return jsonify({'error': 'Token inválido o expirado'}), 401

    try:
        conn = get_db()
        cursor = conn.cursor()
        citas = cursor.execute('''
            SELECT c.id, c.fecha, c.hora_inicio, c.estado, c.tipo_reserva,
                   cl.nombre as cliente, s.nombre as servicio
            FROM citas c
            JOIN clientes cl ON c.cliente_id = cl.id
            JOIN servicios s ON c.servicio_id = s.id
            ORDER BY c.fecha DESC, c.hora_inicio DESC
            LIMIT 50
        ''').fetchall()
        conn.close()
        return jsonify([dict(c) for c in citas])
    except Exception as e:
        logging.error(f"Error en historial: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/panel/confirmar-cita', methods=['POST'])
def confirmar_cita():
    token = request.headers.get('Authorization')
    if not token or not token.startswith('Bearer '):
        return jsonify({'error': 'No autorizado'}), 401
    token = token[7:]
    if not verificar_token(token):
        return jsonify({'error': 'Token inválido o expirado'}), 401

    data = request.json
    cita_id = data.get('cita_id')
    if not cita_id:
        return jsonify({'error': 'Falta cita_id'}), 400

    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('UPDATE citas SET estado = ? WHERE id = ?', ('confirmada', cita_id))
        conn.commit()
        conn.close()
        return jsonify({'mensaje': '✅ Cita confirmada'})
    except Exception as e:
        logging.error(f"Error al confirmar: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/panel/rechazar-cita', methods=['POST'])
def rechazar_cita():
    token = request.headers.get('Authorization')
    if not token or not token.startswith('Bearer '):
        return jsonify({'error': 'No autorizado'}), 401
    token = token[7:]
    if not verificar_token(token):
        return jsonify({'error': 'Token inválido o expirado'}), 401

    data = request.json
    cita_id = data.get('cita_id')
    if not cita_id:
        return jsonify({'error': 'Falta cita_id'}), 400

    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('UPDATE citas SET estado = ? WHERE id = ?', ('cancelada_por_barbero', cita_id))
        conn.commit()
        conn.close()
        return jsonify({'mensaje': '❌ Cita rechazada'})
    except Exception as e:
        logging.error(f"Error al rechazar: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/panel/bloquear', methods=['POST'])
def bloquear_dias():
    token = request.headers.get('Authorization')
    if not token or not token.startswith('Bearer '):
        return jsonify({'error': 'No autorizado'}), 401
    token = token[7:]
    if not verificar_token(token):
        return jsonify({'error': 'Token inválido o expirado'}), 401

    data = request.json
    fecha_inicio = data.get('fecha_inicio')
    fecha_fin = data.get('fecha_fin')
    motivo = data.get('motivo', 'Descanso')
    if not fecha_inicio or not fecha_fin:
        return jsonify({'error': 'Faltan fechas'}), 400

    try:
        conn = get_db()
        cursor = conn.cursor()
        # Verificar citas afectadas
        citas_afectadas = cursor.execute('''
            SELECT id FROM citas 
            WHERE barbero_id = 1 AND fecha BETWEEN ? AND ? 
            AND estado = 'confirmada'
        ''', (fecha_inicio, fecha_fin)).fetchall()
        if citas_afectadas:
            conn.close()
            return jsonify({
                'citas_afectadas': [dict(c) for c in citas_afectadas],
                'mensaje': 'Hay citas confirmadas. ¿Deseas cancelarlas?'
            }), 409

        cursor.execute('''
            INSERT INTO bloqueos (barbero_id, fecha_inicio, fecha_fin, motivo)
            VALUES (1, ?, ?, ?)
        ''', (fecha_inicio, fecha_fin, motivo))
        conn.commit()
        conn.close()
        return jsonify({'mensaje': '✅ Bloqueo agregado'})
    except Exception as e:
        logging.error(f"Error al bloquear: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/panel/cancelar-citas-masivo', methods=['POST'])
def cancelar_masivo():
    token = request.headers.get('Authorization')
    if not token or not token.startswith('Bearer '):
        return jsonify({'error': 'No autorizado'}), 401
    token = token[7:]
    if not verificar_token(token):
        return jsonify({'error': 'Token inválido o expirado'}), 401

    data = request.json
    ids = data.get('cita_ids', [])
    if not ids:
        return jsonify({'error': 'No se proporcionaron IDs'}), 400

    try:
        conn = get_db()
        cursor = conn.cursor()
        placeholders = ','.join('?' * len(ids))
        cursor.execute(f'''
            UPDATE citas SET estado = ? WHERE id IN ({placeholders})
        ''', ('cancelada_por_barbero', *ids))
        conn.commit()
        conn.close()
        return jsonify({'mensaje': f'{cursor.rowcount} citas canceladas'})
    except Exception as e:
        logging.error(f"Error en cancelación masiva: {str(e)}")
        return jsonify({'error': str(e)}), 500

# ---------- ENDPOINTS CLIENTE ----------
@app.route('/api/mis-citas', methods=['GET'])
def mis_citas():
    telefono = request.args.get('telefono')
    if not telefono:
        return jsonify({'error': 'Falta teléfono'}), 400

    try:
        conn = get_db()
        cursor = conn.cursor()
        citas = cursor.execute('''
            SELECT c.id, c.fecha, c.hora_inicio, c.hora_fin, c.estado, s.nombre as servicio,
                   c.alerta_cierre
            FROM citas c
            JOIN clientes cl ON c.cliente_id = cl.id
            JOIN servicios s ON c.servicio_id = s.id
            WHERE cl.telefono = ? AND c.estado IN ('confirmada', 'pendiente_confirmacion')
            ORDER BY c.fecha, c.hora_inicio
        ''', (telefono,)).fetchall()
        conn.close()
        return jsonify([dict(c) for c in citas])
    except Exception as e:
        logging.error(f"Error en mis-citas: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/cancelar-cita', methods=['POST'])
def cancelar_cita_cliente():
    data = request.json
    cita_id = data.get('cita_id')
    if not cita_id:
        return jsonify({'error': 'Falta cita_id'}), 400

    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('UPDATE citas SET estado = ? WHERE id = ?', ('cancelada_por_cliente', cita_id))
        conn.commit()
        conn.close()
        return jsonify({'mensaje': '✅ Cita cancelada'})
    except Exception as e:
        logging.error(f"Error al cancelar: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/solicitar-modificacion', methods=['POST'])
def solicitar_modificacion():
    data = request.json
    cita_original_id = data.get('cita_original_id')
    nueva_fecha = data.get('nueva_fecha')
    nueva_hora = data.get('nueva_hora')
    if not all([cita_original_id, nueva_fecha, nueva_hora]):
        return jsonify({'error': 'Faltan datos'}), 400

    try:
        conn = get_db()
        cursor = conn.cursor()
        # Obtener datos originales
        original = cursor.execute(
            'SELECT cliente_id, servicio_id, notas_cliente FROM citas WHERE id = ?',
            (cita_original_id,)
        ).fetchone()
        if not original:
            conn.close()
            return jsonify({'error': 'Cita original no encontrada'}), 404

        # Verificar disponibilidad del nuevo hueco
        ocupado = cursor.execute('''
            SELECT 1 FROM citas 
            WHERE barbero_id = 1 AND fecha = ? AND hora_inicio = ? 
            AND estado IN ('confirmada', 'pendiente_confirmacion')
        ''', (nueva_fecha, nueva_hora)).fetchone()
        if ocupado:
            conn.close()
            return jsonify({'error': 'El nuevo hueco no está disponible'}), 409

        servicio = cursor.execute(
            'SELECT duracion_minutos FROM servicios WHERE id = ?',
            (original['servicio_id'],)
        ).fetchone()
        duracion = servicio['duracion_minutos']
        h, m = map(int, nueva_hora.split(':'))
        total_min = h * 60 + m + duracion
        nueva_hora_fin = f"{total_min // 60:02d}:{total_min % 60:02d}"

        cursor.execute('''
            INSERT INTO citas 
            (barbero_id, cliente_id, servicio_id, fecha, hora_inicio, hora_fin, 
             estado, tipo_reserva, alerta_cierre, cita_original_id, notas_cliente)
            VALUES (1, ?, ?, ?, ?, ?, 'pendiente_confirmacion', 'modificacion', ?, ?, ?)
        ''', (original['cliente_id'], original['servicio_id'], nueva_fecha, nueva_hora,
              nueva_hora_fin, 1 if total_min > 17*60 else 0, cita_original_id, original['notas_cliente']))
        nueva_cita_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return jsonify({
            'mensaje': 'Solicitud de modificación enviada',
            'nueva_cita_id': nueva_cita_id
        })
    except Exception as e:
        logging.error(f"Error en modificación: {str(e)}")
        return jsonify({'error': str(e)}), 500

def cancelar_cita_por_sistema(cita_id):
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('UPDATE citas SET estado = ? WHERE id = ?', ('cancelada_por_sistema', cita_id))
        conn.commit()
        conn.close()
        logging.info(f"Cita {cita_id} cancelada automáticamente por fallo de notificación")
    except Exception as e:
        logging.error(f"Error en cancelación automática: {str(e)}")

if __name__ == '__main__':
    app.run(debug=True, port=5000)