import os
import json
import logging
import threading
import time
from datetime import datetime, time, timedelta
from flask import Flask, request, jsonify, session
from flask_cors import CORS
from database import get_db, init_db

# ---------- CONFIGURACIÓN ----------
app = Flask(__name__)
app.secret_key = 'barberia_secret_key_2026'  # Cambia esto en producción
CORS(app, supports_credentials=True)

# Configurar logging para notificaciones
logging.basicConfig(
    filename='notificaciones.log',
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)

# Variables de entorno para simulación
SIMULAR_FALLO_NOTIFICACION = os.environ.get('SIMULAR_FALLO', 'False').lower() == 'true'
TIEMPO_ESPERA_FALLO_MIN = int(os.environ.get('TIEMPO_ESPERA', '20'))  # minutos

# NÚMERO DE PRUEBA PARA VENEZUELA (cámbialo por el tuyo)
NUMERO_PRUEBA_VENEZUELA = "+584241234567"  # Formato Venezuela

# Inicializar base de datos al arrancar
init_db()

# ---------- FUNCIONES AUXILIARES ----------
def es_dia_habil(fecha_str):
    """Verifica si la fecha es lunes a sábado."""
    fecha = datetime.strptime(fecha_str, '%Y-%m-%d')
    return fecha.weekday() < 6  # 0=lunes, 5=sábado, 6=domingo

def calcular_huecos_libres(fecha_str, barbero_id=1):
    """Devuelve lista de horas libres para un barbero en una fecha (formato HH:MM)."""
    conn = get_db()
    cursor = conn.cursor()

    # Verificar día hábil
    try:
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
    except ValueError:
        conn.close()
        return []
    if fecha.weekday() == 6:  # domingo
        conn.close()
        return []

    # Obtener horario del barbero
    barbero = cursor.execute(
        'SELECT hora_inicio, hora_fin FROM barberos WHERE id = ?',
        (barbero_id,)
    ).fetchone()
    if not barbero:
        conn.close()
        return []

    # Convertir horario a objetos time
    inicio = datetime.strptime(barbero['hora_inicio'], '%H:%M').time()
    fin = datetime.strptime(barbero['hora_fin'], '%H:%M').time()

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

    # Generar franjas de 30 minutos usando datetime
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

def enviar_notificacion(cita_id, mensaje, tipo='whatsapp'):
    """Simula envío de notificación. Retorna True si fue 'entregada'."""
    logging.info(f"CITA {cita_id} - {tipo.upper()} a {NUMERO_PRUEBA_VENEZUELA}: {mensaje}")
    print(f"📨 [NOTIFICACIÓN] {tipo} a {NUMERO_PRUEBA_VENEZUELA}: {mensaje} (Cita {cita_id})")

    conn = get_db()
    cursor = conn.cursor()
    estado = 'fallido' if SIMULAR_FALLO_NOTIFICACION else 'entregado'
    cursor.execute(
        'INSERT INTO logs_notificaciones (cita_id, tipo, estado_envio) VALUES (?, ?, ?)',
        (cita_id, tipo, estado)
    )
    conn.commit()
    conn.close()

    if SIMULAR_FALLO_NOTIFICACION:
        print("⚠️ [SIMULACIÓN] Notificación marcada como FALLIDA")
        return False
    return True

def cancelar_cita_por_sistema(cita_id):
    """Escenario B: cancelación automática por fallo en notificación."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE citas SET estado = ? WHERE id = ? AND estado = ?',
        ('cancelada_por_sistema', cita_id, 'pendiente_confirmacion')
    )
    conn.commit()
    afectadas = cursor.rowcount
    conn.close()
    if afectadas > 0:
        print(f"⏰ [SISTEMA] Cita ID {cita_id} cancelada automáticamente por fallo en notificación (20 min). Hueco liberado.")
        logging.info(f"CITA {cita_id} - CANCELADA POR SISTEMA (fallo notificación)")
        return True
    return False

# ---------- ENDPOINTS ----------

@app.route('/')
def home():
    return jsonify({
        'mensaje': 'API Barbería funcionando',
        'status': 'ok',
        'version': '1.0',
        'barbero': 'Barbería Venezuela'
    })

# 1. Disponibilidad
@app.route('/api/disponibilidad', methods=['GET'])
def disponibilidad():
    fecha = request.args.get('fecha')
    if not fecha:
        return jsonify({'error': 'Falta parámetro fecha'}), 400
    try:
        disponibles = calcular_huecos_libres(fecha)
        return jsonify({
            'disponibles': disponibles,
            'fecha': fecha,
            'total': len(disponibles)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# 2. Reservar cita
@app.route('/api/reservar', methods=['POST'])
def reservar():
    data = request.json
    required = ['fecha', 'hora_inicio', 'servicio_id', 'nombre']
    if not all(k in data for k in required):
        return jsonify({'error': 'Faltan datos obligatorios'}), 400

    fecha = data['fecha']
    hora_inicio = data['hora_inicio']
    servicio_id = data['servicio_id']
    nombre = data['nombre']
    telefono = data.get('telefono', '')
    notas = data.get('notas', '')

    conn = get_db()
    cursor = conn.cursor()

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

    ocupado = cursor.execute('''
        SELECT 1 FROM citas 
        WHERE barbero_id = 1 AND fecha = ? AND hora_inicio = ? 
        AND estado IN ('confirmada', 'pendiente_confirmacion')
    ''', (fecha, hora_inicio)).fetchone()
    if ocupado:
        conn.close()
        return jsonify({'error': 'El hueco ya no está disponible'}), 409

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

    if tipo_reserva == 'urgente':
        mensaje = f"⚠️ SOLICITUD URGENTE\nCliente: {nombre}\nFecha: {fecha}\nHora: {hora_inicio}\nServicio: {servicio_id}\nTeléfono: {telefono or 'No proporcionado'}"
        entregado = enviar_notificacion(cita_id, mensaje, 'whatsapp')

        if not entregado:
            def programar_cancelacion():
                time.sleep(TIEMPO_ESPERA_FALLO_MIN * 60)
                conn2 = get_db()
                cur2 = conn2.cursor()
                cita = cur2.execute(
                    'SELECT estado FROM citas WHERE id = ?', (cita_id,)
                ).fetchone()
                conn2.close()
                if cita and cita['estado'] == 'pendiente_confirmacion':
                    cancelar_cita_por_sistema(cita_id)

            threading.Thread(target=programar_cancelacion, daemon=True).start()
            return jsonify({
                'mensaje': 'Solicitud urgente enviada. El sistema intentará notificar al barbero.',
                'citaId': cita_id,
                'estado': 'pendiente_confirmacion'
            })
        else:
            return jsonify({
                'mensaje': 'Solicitud urgente enviada. Esperando confirmación del barbero.',
                'citaId': cita_id,
                'estado': 'pendiente_confirmacion'
            })
    else:
        return jsonify({
            'mensaje': '✅ ¡Cita agendada exitosamente!',
            'citaId': cita_id,
            'estado': 'confirmada'
        })

# 3. Panel - Login
@app.route('/api/panel/login', methods=['POST'])
def login_barbero():
    data = request.json
    password = data.get('password', '')
    if password == 'barberia2026':
        session['barbero'] = True
        return jsonify({'mensaje': 'Login exitoso', 'autenticado': True})
    return jsonify({'error': 'Contraseña incorrecta'}), 401

@app.route('/api/panel/verificar', methods=['GET'])
def verificar_sesion():
    return jsonify({'autenticado': session.get('barbero', False)})

@app.route('/api/panel/logout', methods=['POST'])
def logout_barbero():
    session.pop('barbero', None)
    return jsonify({'mensaje': 'Sesión cerrada'})

# 4. Panel - Ver citas pendientes
@app.route('/api/panel/pendientes', methods=['GET'])
def listar_pendientes():
    if not session.get('barbero'):
        return jsonify({'error': 'No autorizado'}), 401

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

# 5. Panel - Historial de citas
@app.route('/api/panel/historial', methods=['GET'])
def historial_citas():
    if not session.get('barbero'):
        return jsonify({'error': 'No autorizado'}), 401

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

# 6. Panel - Confirmar cita
@app.route('/api/panel/confirmar-cita', methods=['POST'])
def confirmar_cita():
    if not session.get('barbero'):
        return jsonify({'error': 'No autorizado'}), 401

    data = request.json
    cita_id = data.get('cita_id')
    if not cita_id:
        return jsonify({'error': 'Falta cita_id'}), 400

    conn = get_db()
    cursor = conn.cursor()
    cita = cursor.execute(
        'SELECT estado, cita_original_id FROM citas WHERE id = ?',
        (cita_id,)
    ).fetchone()
    if not cita:
        conn.close()
        return jsonify({'error': 'Cita no encontrada'}), 404

    if cita['estado'] != 'pendiente_confirmacion':
        conn.close()
        return jsonify({'error': 'La cita no está pendiente'}), 400

    cursor.execute('UPDATE citas SET estado = ? WHERE id = ?', ('confirmada', cita_id))

    if cita['cita_original_id']:
        cursor.execute(
            'UPDATE citas SET estado = ? WHERE id = ?',
            ('cancelada_por_barbero', cita['cita_original_id'])
        )
        logging.info(f"CITA {cita['cita_original_id']} - CANCELADA POR CONFIRMACIÓN DE MODIFICACIÓN")

    conn.commit()
    conn.close()
    return jsonify({'mensaje': '✅ Cita confirmada exitosamente'})

# 7. Panel - Rechazar cita
@app.route('/api/panel/rechazar-cita', methods=['POST'])
def rechazar_cita():
    if not session.get('barbero'):
        return jsonify({'error': 'No autorizado'}), 401

    data = request.json
    cita_id = data.get('cita_id')
    if not cita_id:
        return jsonify({'error': 'Falta cita_id'}), 400

    conn = get_db()
    cursor = conn.cursor()
    cita = cursor.execute(
        'SELECT estado, cita_original_id FROM citas WHERE id = ?',
        (cita_id,)
    ).fetchone()
    if not cita:
        conn.close()
        return jsonify({'error': 'Cita no encontrada'}), 404

    if cita['estado'] != 'pendiente_confirmacion':
        conn.close()
        return jsonify({'error': 'La cita no está pendiente'}), 400

    cursor.execute('UPDATE citas SET estado = ? WHERE id = ?', ('cancelada_por_barbero', cita_id))
    conn.commit()
    conn.close()
    return jsonify({'mensaje': '❌ Cita rechazada. Cliente notificado.'})

# 8. Panel - Bloquear días
@app.route('/api/panel/bloquear', methods=['POST'])
def bloquear_dias():
    if not session.get('barbero'):
        return jsonify({'error': 'No autorizado'}), 401

    data = request.json
    fecha_inicio = data.get('fecha_inicio')
    fecha_fin = data.get('fecha_fin')
    motivo = data.get('motivo', 'Descanso')
    if not fecha_inicio or not fecha_fin:
        return jsonify({'error': 'Faltan fechas'}), 400

    conn = get_db()
    cursor = conn.cursor()

    citas_afectadas = cursor.execute('''
        SELECT id, fecha, hora_inicio, cliente_id FROM citas 
        WHERE barbero_id = 1 AND fecha BETWEEN ? AND ? 
        AND estado = 'confirmada'
    ''', (fecha_inicio, fecha_fin)).fetchall()

    if citas_afectadas:
        conn.close()
        return jsonify({
            'citas_afectadas': [dict(c) for c in citas_afectadas],
            'mensaje': 'Hay citas confirmadas. ¿Mantener o cancelar todas?'
        }), 409

    cursor.execute('''
        INSERT INTO bloqueos (barbero_id, fecha_inicio, fecha_fin, motivo)
        VALUES (1, ?, ?, ?)
    ''', (fecha_inicio, fecha_fin, motivo))
    conn.commit()
    conn.close()
    return jsonify({'mensaje': '✅ Bloqueo agregado correctamente'})

# 9. Panel - Cancelación masiva
@app.route('/api/panel/cancelar-citas-masivo', methods=['POST'])
def cancelar_masivo():
    if not session.get('barbero'):
        return jsonify({'error': 'No autorizado'}), 401

    data = request.json
    ids = data.get('cita_ids', [])
    if not ids:
        return jsonify({'error': 'No se proporcionaron IDs'}), 400

    conn = get_db()
    cursor = conn.cursor()
    placeholders = ','.join('?' * len(ids))
    cursor.execute(f'''
        UPDATE citas SET estado = ? WHERE id IN ({placeholders})
    ''', ('cancelada_por_barbero', *ids))
    afectadas = cursor.rowcount
    conn.commit()
    conn.close()

    logging.info(f"CANCELACIÓN MASIVA: {afectadas} citas canceladas por bloqueo del barbero")
    return jsonify({'mensaje': f'{afectadas} citas canceladas. Clientes notificados.'})

# 10. Cliente - Consultar sus citas
@app.route('/api/mis-citas', methods=['GET'])
def mis_citas():
    telefono = request.args.get('telefono')
    if not telefono:
        return jsonify({'error': 'Falta teléfono'}), 400

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

# 11. Cliente - Cancelar cita
@app.route('/api/cancelar-cita', methods=['POST'])
def cancelar_cita_cliente():
    data = request.json
    cita_id = data.get('cita_id')
    if not cita_id:
        return jsonify({'error': 'Falta cita_id'}), 400

    conn = get_db()
    cursor = conn.cursor()
    cita = cursor.execute(
        'SELECT estado FROM citas WHERE id = ?',
        (cita_id,)
    ).fetchone()
    if not cita:
        conn.close()
        return jsonify({'error': 'Cita no encontrada'}), 404
    if cita['estado'] not in ('confirmada', 'pendiente_confirmacion'):
        conn.close()
        return jsonify({'error': 'No se puede cancelar esta cita'}), 400

    cursor.execute('UPDATE citas SET estado = ? WHERE id = ?', ('cancelada_por_cliente', cita_id))
    conn.commit()
    conn.close()
    return jsonify({'mensaje': '✅ Cita cancelada exitosamente. Hueco liberado.'})

# 12. Cliente - Solicitar modificación
@app.route('/api/solicitar-modificacion', methods=['POST'])
def solicitar_modificacion():
    data = request.json
    cita_original_id = data.get('cita_original_id')
    nueva_fecha = data.get('nueva_fecha')
    nueva_hora = data.get('nueva_hora')
    if not all([cita_original_id, nueva_fecha, nueva_hora]):
        return jsonify({'error': 'Faltan datos'}), 400

    conn = get_db()
    cursor = conn.cursor()

    original = cursor.execute(
        'SELECT cliente_id, servicio_id, notas_cliente FROM citas WHERE id = ?',
        (cita_original_id,)
    ).fetchone()
    if not original:
        conn.close()
        return jsonify({'error': 'Cita original no encontrada'}), 404

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

    enviar_notificacion(nueva_cita_id, f"SOLICITUD DE MODIFICACIÓN - Cita original {cita_original_id} → {nueva_fecha} {nueva_hora}", 'email')

    return jsonify({
        'mensaje': 'Solicitud de modificación enviada. Espera confirmación del barbero.',
        'nueva_cita_id': nueva_cita_id
    })

# ---------- ARRANQUE ----------
if __name__ == '__main__':
    app.run(debug=True, port=5000)