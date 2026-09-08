import os
import json
import logging
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, session
from flask_cors import CORS
from database import get_db, init_db

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-key-123')
CORS(app, supports_credentials=True)

# Configuración de logging
logging.basicConfig(
    filename='notificaciones.log',
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)

# Variables de entorno
SIMULAR_FALLO_NOTIFICACION = os.environ.get('SIMULAR_FALLO', 'False').lower() == 'true'
TIEMPO_ESPERA_FALLO_MIN = int(os.environ.get('TIEMPO_ESPERA', '20'))
BARBERO_PASSWORD = os.environ.get('BARBERO_PASSWORD', 'barberia2026')
NUMERO_PRUEBA_VENEZUELA = os.environ.get('WHATSAPP_RECIPIENT', '+584142623634')

# Inicializar base de datos
init_db()

# ========== FUNCIONES AUXILIARES ==========

def es_dia_habil(fecha_str):
    try:
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d')
        return fecha.weekday() < 6  # 0=lunes, 5=sábado, 6=domingo
    except ValueError:
        return False

def calcular_huecos_libres(fecha_str, barbero_id=1):
    """
    Genera horas disponibles según el día de la semana.
    Lunes a viernes: 8-12 y 14-17 (incluye hora de cierre)
    Sábado: 8-12 y 14-19 (incluye hora de cierre)
    """
    conn = get_db()
    cursor = conn.cursor()

    if not es_dia_habil(fecha_str):
        conn.close()
        return []

    # Obtener citas ocupadas
    cursor.execute('''
        SELECT hora_inicio FROM citas 
        WHERE barbero_id = %s AND fecha = %s 
        AND estado IN ('confirmada', 'pendiente_confirmacion')
    ''', (barbero_id, fecha_str))
    ocupados = {row['hora_inicio'] for row in cursor.fetchall()}

    # Definir bloques según día
    fecha = datetime.strptime(fecha_str, '%Y-%m-%d')
    dia_semana = fecha.weekday()  # 0=lunes, 5=sábado

    if dia_semana < 5:  # Lunes a viernes
        bloques = [('08:00', '12:00'), ('14:00', '17:00')]
    else:  # Sábado
        bloques = [('08:00', '12:00'), ('14:00', '19:00')]

    disponibles = []
    for inicio_str, fin_str in bloques:
        inicio = datetime.strptime(inicio_str, '%H:%M')
        fin = datetime.strptime(fin_str, '%H:%M')
        hora_actual = inicio
        while hora_actual <= fin:  # Incluye la hora de cierre
            hora_str = hora_actual.strftime('%H:%M')
            if hora_str not in ocupados:
                disponibles.append(hora_str)
            hora_actual += timedelta(minutes=30)

    conn.close()
    # Eliminar duplicados y ordenar
    return sorted(set(disponibles))

def verificar_barbero():
    """Verifica la contraseña del barbero desde el header X-Password."""
    password = request.headers.get('X-Password')
    return password == BARBERO_PASSWORD

# ========== ENDPOINTS ==========

@app.route('/')
def home():
    return jsonify({
        'mensaje': 'API Barbería funcionando',
        'status': 'ok',
        'version': '1.0',
        'barbero': 'Gocho Barber'
    })

@app.route('/api/disponibilidad', methods=['GET'])
def disponibilidad():
    fecha = request.args.get('fecha')
    if not fecha:
        return jsonify({'error': 'Falta parámetro fecha'}), 400
    try:
        disponibles = calcular_huecos_libres(fecha)
        return jsonify({'disponibles': disponibles, 'fecha': fecha, 'total': len(disponibles)})
    except Exception as e:
        logging.error(f"Error en disponibilidad: {e}")
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

        if not nombre:
            return jsonify({'error': 'El nombre es obligatorio'}), 400

        conn = get_db()
        cursor = conn.cursor()

        # Obtener duración del servicio
        cursor.execute('SELECT duracion_minutos FROM servicios WHERE id = %s AND activo = 1', (servicio_id,))
        servicio = cursor.fetchone()
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

        # Verificar si el hueco está ocupado
        cursor.execute('''
            SELECT 1 FROM citas 
            WHERE barbero_id = 1 AND fecha = %s AND hora_inicio = %s 
            AND estado IN ('confirmada', 'pendiente_confirmacion')
        ''', (fecha, hora_inicio))
        if cursor.fetchone():
            conn.close()
            return jsonify({'error': 'El hueco ya no está disponible'}), 409

        # Crear o buscar cliente
        cursor.execute('SELECT id FROM clientes WHERE nombre = %s AND telefono = %s', (nombre, telefono))
        cliente = cursor.fetchone()
        if cliente:
            cliente_id = cliente['id']
        else:
            # Insertar cliente con RETURNING id (PostgreSQL)
            cursor.execute(
                'INSERT INTO clientes (nombre, telefono, notas_habituales) VALUES (%s, %s, %s) RETURNING id',
                (nombre, telefono, notas)
            )
            cliente_id = cursor.fetchone()['id']

        # Insertar cita
        cursor.execute('''
            INSERT INTO citas 
            (barbero_id, cliente_id, servicio_id, fecha, hora_inicio, hora_fin, 
             estado, tipo_reserva, alerta_cierre, notas_cliente)
            VALUES (1, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (cliente_id, servicio_id, fecha, hora_inicio, hora_fin,
              estado, tipo_reserva, alerta_cierre, notas))
        cita_id = cursor.lastrowid
        conn.commit()
        conn.close()

        if tipo_reserva == 'urgente':
            logging.info(f"CITA {cita_id} - Reserva urgente: {nombre} - {fecha} {hora_inicio}")
            return jsonify({
                'mensaje': 'Solicitud urgente enviada. Esperando confirmación del barbero.',
                'citaId': cita_id,
                'estado': 'pendiente_confirmacion'
            })
        else:
            return jsonify({
                'mensaje': '¡Cita agendada exitosamente!',
                'citaId': cita_id,
                'estado': 'confirmada'
            })
    except Exception as e:
        logging.error(f"Error en reservar: {e}")
        return jsonify({'error': str(e)}), 500

# ========== PANEL BARBERO ==========

@app.route('/api/panel/login', methods=['POST'])
def login_barbero():
    data = request.json
    password = data.get('password', '')
    if password == BARBERO_PASSWORD:
        return jsonify({'mensaje': 'Login exitoso', 'autenticado': True})
    return jsonify({'error': 'Contraseña incorrecta'}), 401

@app.route('/api/panel/pendientes', methods=['GET'])
def listar_pendientes():
    if not verificar_barbero():
        return jsonify({'error': 'No autorizado'}), 401
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT c.id, c.fecha, c.hora_inicio, c.hora_fin, c.estado, c.tipo_reserva,
                   cl.nombre as cliente, cl.telefono, s.nombre as servicio,
                   c.alerta_cierre, c.notas_cliente
            FROM citas c
            JOIN clientes cl ON c.cliente_id = cl.id
            JOIN servicios s ON c.servicio_id = s.id
            WHERE c.estado = 'pendiente_confirmacion'
            ORDER BY c.fecha, c.hora_inicio
        ''')
        citas = cursor.fetchall()
        conn.close()
        return jsonify([dict(c) for c in citas])
    except Exception as e:
        logging.error(f"Error en pendientes: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/panel/historial', methods=['GET'])
def historial_citas():
    if not verificar_barbero():
        return jsonify({'error': 'No autorizado'}), 401
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT c.id, c.fecha, c.hora_inicio, c.estado, c.tipo_reserva,
                   cl.nombre as cliente, s.nombre as servicio
            FROM citas c
            JOIN clientes cl ON c.cliente_id = cl.id
            JOIN servicios s ON c.servicio_id = s.id
            ORDER BY c.fecha DESC, c.hora_inicio DESC
            LIMIT 50
        ''')
        citas = cursor.fetchall()
        conn.close()
        return jsonify([dict(c) for c in citas])
    except Exception as e:
        logging.error(f"Error en historial: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/panel/confirmar-cita', methods=['POST'])
def confirmar_cita():
    if not verificar_barbero():
        return jsonify({'error': 'No autorizado'}), 401
    data = request.json
    cita_id = data.get('cita_id')
    if not cita_id:
        return jsonify({'error': 'Falta cita_id'}), 400
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT estado, cita_original_id FROM citas WHERE id = %s', (cita_id,))
        cita = cursor.fetchone()
        if not cita:
            conn.close()
            return jsonify({'error': 'Cita no encontrada'}), 404
        if cita['estado'] != 'pendiente_confirmacion':
            conn.close()
            return jsonify({'error': 'La cita no está pendiente'}), 400

        cursor.execute('UPDATE citas SET estado = %s WHERE id = %s', ('confirmada', cita_id))
        if cita['cita_original_id']:
            cursor.execute('UPDATE citas SET estado = %s WHERE id = %s', ('cancelada_por_barbero', cita['cita_original_id']))
        conn.commit()
        conn.close()
        return jsonify({'mensaje': 'Cita confirmada exitosamente'})
    except Exception as e:
        logging.error(f"Error confirmando cita: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/panel/rechazar-cita', methods=['POST'])
def rechazar_cita():
    if not verificar_barbero():
        return jsonify({'error': 'No autorizado'}), 401
    data = request.json
    cita_id = data.get('cita_id')
    if not cita_id:
        return jsonify({'error': 'Falta cita_id'}), 400
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT estado FROM citas WHERE id = %s', (cita_id,))
        cita = cursor.fetchone()
        if not cita:
            conn.close()
            return jsonify({'error': 'Cita no encontrada'}), 404
        if cita['estado'] != 'pendiente_confirmacion':
            conn.close()
            return jsonify({'error': 'La cita no está pendiente'}), 400
        cursor.execute('UPDATE citas SET estado = %s WHERE id = %s', ('cancelada_por_barbero', cita_id))
        conn.commit()
        conn.close()
        return jsonify({'mensaje': 'Cita rechazada. Cliente notificado.'})
    except Exception as e:
        logging.error(f"Error rechazando cita: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/panel/bloquear', methods=['POST'])
def bloquear_dias():
    if not verificar_barbero():
        return jsonify({'error': 'No autorizado'}), 401
    data = request.json
    fecha_inicio = data.get('fecha_inicio')
    fecha_fin = data.get('fecha_fin')
    motivo = data.get('motivo', 'Descanso')
    if not fecha_inicio or not fecha_fin:
        return jsonify({'error': 'Faltan fechas'}), 400
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, fecha, hora_inicio, cliente_id FROM citas 
            WHERE barbero_id = 1 AND fecha BETWEEN %s AND %s 
            AND estado = 'confirmada'
        ''', (fecha_inicio, fecha_fin))
        citas_afectadas = cursor.fetchall()
        if citas_afectadas:
            conn.close()
            return jsonify({
                'citas_afectadas': [dict(c) for c in citas_afectadas],
                'mensaje': 'Hay citas confirmadas. ¿Mantener o cancelar todas?'
            }), 409
        cursor.execute('''
            INSERT INTO bloqueos (barbero_id, fecha_inicio, fecha_fin, motivo)
            VALUES (1, %s, %s, %s)
        ''', (fecha_inicio, fecha_fin, motivo))
        conn.commit()
        conn.close()
        return jsonify({'mensaje': 'Bloqueo agregado correctamente'})
    except Exception as e:
        logging.error(f"Error bloqueando días: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/panel/cancelar-citas-masivo', methods=['POST'])
def cancelar_masivo():
    if not verificar_barbero():
        return jsonify({'error': 'No autorizado'}), 401
    data = request.json
    ids = data.get('cita_ids', [])
    if not ids:
        return jsonify({'error': 'No se proporcionaron IDs'}), 400
    try:
        conn = get_db()
        cursor = conn.cursor()
        placeholders = ','.join(['%s'] * len(ids))
        cursor.execute(f'''
            UPDATE citas SET estado = %s WHERE id IN ({placeholders})
        ''', ('cancelada_por_barbero', *ids))
        afectadas = cursor.rowcount
        conn.commit()
        conn.close()
        return jsonify({'mensaje': f'{afectadas} citas canceladas. Clientes notificados.'})
    except Exception as e:
        logging.error(f"Error en cancelación masiva: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/panel/cancelar-cita-confirmada', methods=['POST'])
def cancelar_cita_confirmada():
    if not verificar_barbero():
        return jsonify({'error': 'No autorizado'}), 401
    data = request.json
    cita_id = data.get('cita_id')
    if not cita_id:
        return jsonify({'error': 'Falta cita_id'}), 400
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT estado FROM citas WHERE id = %s', (cita_id,))
        cita = cursor.fetchone()
        if not cita:
            conn.close()
            return jsonify({'error': 'Cita no encontrada'}), 404
        if cita['estado'] != 'confirmada':
            conn.close()
            return jsonify({'error': 'Solo se pueden cancelar citas confirmadas'}), 400
        cursor.execute('UPDATE citas SET estado = %s WHERE id = %s', ('cancelada_por_barbero', cita_id))
        conn.commit()
        conn.close()
        return jsonify({'mensaje': 'Cita cancelada exitosamente. El cliente será notificado.'})
    except Exception as e:
        logging.error(f"Error cancelando cita confirmada: {e}")
        return jsonify({'error': str(e)}), 500

# ========== CLIENTE ==========

@app.route('/api/mis-citas', methods=['GET'])
def mis_citas():
    telefono = request.args.get('telefono')
    if not telefono:
        return jsonify({'error': 'Falta teléfono'}), 400
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT c.id, c.fecha, c.hora_inicio, c.hora_fin, c.estado, s.nombre as servicio,
                   c.alerta_cierre
            FROM citas c
            JOIN clientes cl ON c.cliente_id = cl.id
            JOIN servicios s ON c.servicio_id = s.id
            WHERE cl.telefono = %s AND c.estado IN ('confirmada', 'pendiente_confirmacion')
            ORDER BY c.fecha, c.hora_inicio
        ''', (telefono,))
        citas = cursor.fetchall()
        conn.close()
        return jsonify([dict(c) for c in citas])
    except Exception as e:
        logging.error(f"Error en mis-citas: {e}")
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
        cursor.execute('SELECT estado FROM citas WHERE id = %s', (cita_id,))
        cita = cursor.fetchone()
        if not cita:
            conn.close()
            return jsonify({'error': 'Cita no encontrada'}), 404
        if cita['estado'] not in ('confirmada', 'pendiente_confirmacion'):
            conn.close()
            return jsonify({'error': 'No se puede cancelar esta cita'}), 400
        cursor.execute('UPDATE citas SET estado = %s WHERE id = %s', ('cancelada_por_cliente', cita_id))
        conn.commit()
        conn.close()
        return jsonify({'mensaje': 'Cita cancelada exitosamente. Hueco liberado.'})
    except Exception as e:
        logging.error(f"Error cancelando cita: {e}")
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
        cursor.execute('SELECT cliente_id, servicio_id, notas_cliente FROM citas WHERE id = %s', (cita_original_id,))
        original = cursor.fetchone()
        if not original:
            conn.close()
            return jsonify({'error': 'Cita original no encontrada'}), 404

        cursor.execute('''
            SELECT 1 FROM citas 
            WHERE barbero_id = 1 AND fecha = %s AND hora_inicio = %s 
            AND estado IN ('confirmada', 'pendiente_confirmacion')
        ''', (nueva_fecha, nueva_hora))
        if cursor.fetchone():
            conn.close()
            return jsonify({'error': 'El nuevo hueco no está disponible'}), 409

        cursor.execute('SELECT duracion_minutos FROM servicios WHERE id = %s', (original['servicio_id'],))
        servicio = cursor.fetchone()
        duracion = servicio['duracion_minutos']
        h, m = map(int, nueva_hora.split(':'))
        total_min = h * 60 + m + duracion
        nueva_hora_fin = f"{total_min // 60:02d}:{total_min % 60:02d}"

        cursor.execute('''
            INSERT INTO citas 
            (barbero_id, cliente_id, servicio_id, fecha, hora_inicio, hora_fin, 
             estado, tipo_reserva, alerta_cierre, cita_original_id, notas_cliente)
            VALUES (1, %s, %s, %s, %s, %s, 'pendiente_confirmacion', 'modificacion', %s, %s, %s)
        ''', (original['cliente_id'], original['servicio_id'], nueva_fecha, nueva_hora,
              nueva_hora_fin, 1 if total_min > 17*60 else 0, cita_original_id, original['notas_cliente']))
        nueva_cita_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return jsonify({
            'mensaje': 'Solicitud de modificación enviada. Espera confirmación del barbero.',
            'nueva_cita_id': nueva_cita_id
        })
    except Exception as e:
        logging.error(f"Error en modificación: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)