import os
import json
import logging
import re
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from flask_cors import CORS
from database import get_db, init_db

# ---------- CONFIGURACIÓN ----------
app = Flask(__name__)
CORS(app)

# Autenticación simple (token fijo para el barbero)
TOKEN_BARBERO = "mi_token_secreto_123"  # Cámbialo por uno más seguro

# Configurar logging (solo para notificaciones, sin datos sensibles)
logging.basicConfig(
    filename='notificaciones.log',
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)

SIMULAR_FALLO_NOTIFICACION = os.environ.get('SIMULAR_FALLO', 'False').lower() == 'true'
TIEMPO_ESPERA_FALLO_MIN = int(os.environ.get('TIEMPO_ESPERA', '20'))

init_db()

# ---------- FUNCIONES AUXILIARES ----------
def validar_fecha(fecha):
    """Valida formato YYYY-MM-DD y que sea hoy o futuro."""
    try:
        fecha_obj = datetime.strptime(fecha, '%Y-%m-%d')
        hoy = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        return fecha_obj >= hoy
    except ValueError:
        return False

def validar_hora(hora):
    """Valida formato HH:MM y que esté dentro de 08:00 a 17:00."""
    if not re.match(r'^([0-1][0-9]|2[0-3]):[0-5][0-9]$', hora):
        return False
    h, m = map(int, hora.split(':'))
    return 8 <= h < 17

def calcular_huecos_libres(fecha, barbero_id=1):
    conn = get_db()
    cursor = conn.cursor()

    barbero = cursor.execute(
        'SELECT hora_inicio, hora_fin FROM barberos WHERE id = ?', (barbero_id,)
    ).fetchone()
    if not barbero:
        conn.close()
        return []

    inicio = int(barbero['hora_inicio'].split(':')[0])
    fin = int(barbero['hora_fin'].split(':')[0])

    bloqueo = cursor.execute('''
        SELECT 1 FROM bloqueos 
        WHERE barbero_id = ? AND activo = 1 
        AND fecha_inicio <= ? AND fecha_fin >= ?
    ''', (barbero_id, fecha, fecha)).fetchone()
    if bloqueo:
        conn.close()
        return []

    citas = cursor.execute('''
        SELECT hora_inicio, hora_fin FROM citas 
        WHERE barbero_id = ? AND fecha = ? 
        AND estado IN ('confirmada', 'pendiente_confirmacion')
    ''', (barbero_id, fecha)).fetchall()

    ocupados = [c['hora_inicio'] for c in citas]

    disponibles = []
    hora = inicio
    while hora < fin:
        hora_str = f"{hora:02d}:00"
        if hora_str not in ocupados:
            disponibles.append(hora_str)
        hora += 0.5

    conn.close()
    return disponibles

def enviar_notificacion(cita_id, mensaje, tipo='whatsapp'):
    logging.info(f"CITA {cita_id} - {tipo.upper()}: {mensaje[:50]}...")
    print(f"📨 [NOTIFICACIÓN] {tipo}: {mensaje[:50]}... (Cita {cita_id})")

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
        print(f"⏰ [SISTEMA] Cita ID {cita_id} cancelada automáticamente por fallo en notificación.")
        logging.info(f"CITA {cita_id} - CANCELADA POR SISTEMA")
        return True
    return False

# ---------- ENDPOINTS ----------

@app.route('/')
def home():
    return jsonify({'mensaje': 'API Barbería funcionando', 'status': 'ok'})

@app.route('/api/disponibilidad', methods=['GET'])
def disponibilidad():
    fecha = request.args.get('fecha')
    if not fecha:
        return jsonify({'error': 'Falta parámetro fecha'}), 400
    if not validar_fecha(fecha):
        return jsonify({'error': 'Fecha inválida o pasada'}), 400
    try:
        disponibles = calcular_huecos_libres(fecha)
        return jsonify({'disponibles': disponibles})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/reservar', methods=['POST'])
def reservar():
    data = request.json
    required = ['fecha', 'hora_inicio', 'servicio_id', 'nombre']
    if not all(k in data for k in required):
        return jsonify({'error': 'Faltan datos obligatorios'}), 400

    fecha = data['fecha']
    hora_inicio = data['hora_inicio']
    servicio_id = data['servicio_id']
    nombre = data['nombre'].strip()
    telefono = data.get('telefono', '').strip()
    notas = data.get('notas', '').strip()

    # Validaciones
    if len(nombre) < 2 or len(nombre) > 50:
        return jsonify({'error': 'El nombre debe tener entre 2 y 50 caracteres'}), 400
    if not validar_fecha(fecha):
        return jsonify({'error': 'Fecha inválida o pasada'}), 400
    if not validar_hora(hora_inicio):
        return jsonify({'error': 'Hora inválida (debe estar entre 08:00 y 16:59)'}), 400

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

    # Verificar que el hueco no esté ocupado
    ocupado = cursor.execute('''
        SELECT 1 FROM citas 
        WHERE barbero_id = 1 AND fecha = ? AND hora_inicio = ? 
        AND estado IN ('confirmada', 'pendiente_confirmacion')
    ''', (fecha, hora_inicio)).fetchone()
    if ocupado:
        conn.close()
        return jsonify({'error': 'El hueco ya no está disponible'}), 409

    # Guardar cliente
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
        mensaje = f"Solicitud URGENTE para el {fecha} a las {hora_inicio}. Cliente: {nombre}"
        entregado = enviar_notificacion(cita_id, mensaje, 'whatsapp')

        if not entregado:
            def programar_cancelacion():
                import threading
                import time
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
            'mensaje': '¡Cita agendada exitosamente!',
            'citaId': cita_id,
            'estado': 'confirmada'
        })

# --- PANEL (con autenticación por token) ---
def verificar_token():
    token = request.headers.get('Authorization')
    if not token or token != f"Bearer {TOKEN_BARBERO}":
        return False
    return True

@app.route('/api/panel/confirmar-cita', methods=['POST'])
def confirmar_cita():
    if not verificar_token():
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
        logging.info(f"CITA ORIGINAL {cita['cita_original_id']} cancelada por modificación confirmada")

    conn.commit()
    conn.close()
    return jsonify({'mensaje': 'Cita confirmada exitosamente'})

@app.route('/api/panel/rechazar-cita', methods=['POST'])
def rechazar_cita():
    if not verificar_token():
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
    return jsonify({'mensaje': 'Cita rechazada. Cliente notificado.'})

@app.route('/api/panel/bloquear', methods=['POST'])
def bloquear():
    if not verificar_token():
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
    return jsonify({'mensaje': 'Bloqueo agregado correctamente'})

@app.route('/api/panel/cancelar-citas-masivo', methods=['POST'])
def cancelar_masivo():
    if not verificar_token():
        return jsonify({'error': 'No autorizado'}), 401

    data = request.json
    ids = data.get('cita_ids', [])
    if not ids:
        return jsonify({'error': 'No se proporcionaron IDs'}), 400

    # Usar parámetros con placeholders dinámicos
    placeholders = ','.join('?' * len(ids))
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(f'''
        UPDATE citas SET estado = ? WHERE id IN ({placeholders})
    ''', ('cancelada_por_barbero', *ids))
    afectadas = cursor.rowcount
    conn.commit()
    conn.close()

    logging.info(f"CANCELACIÓN MASIVA: {afectadas} citas canceladas por bloqueo")
    return jsonify({'mensaje': f'{afectadas} citas canceladas. Clientes notificados.'})

# --- Cliente ---
@app.route('/api/mis-citas', methods=['GET'])
def mis_citas():
    telefono = request.args.get('telefono')
    if not telefono:
        return jsonify({'error': 'Falta teléfono'}), 400

    conn = get_db()
    cursor = conn.cursor()
    citas = cursor.execute('''
        SELECT c.id, c.fecha, c.hora_inicio, c.hora_fin, c.estado, s.nombre as servicio
        FROM citas c
        JOIN clientes cl ON c.cliente_id = cl.id
        JOIN servicios s ON c.servicio_id = s.id
        WHERE cl.telefono = ? AND c.estado IN ('confirmada', 'pendiente_confirmacion')
        ORDER BY c.fecha, c.hora_inicio
    ''', (telefono,)).fetchall()
    conn.close()
    return jsonify([dict(c) for c in citas])

@app.route('/api/cancelar-cita', methods=['POST'])
def cancelar_cita():
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
    return jsonify({'mensaje': 'Cita cancelada exitosamente. Hueco liberado.'})

@app.route('/api/solicitar-modificacion', methods=['POST'])
def solicitar_modificacion():
    data = request.json
    cita_original_id = data.get('cita_original_id')
    nueva_fecha = data.get('nueva_fecha')
    nueva_hora = data.get('nueva_hora')
    if not all([cita_original_id, nueva_fecha, nueva_hora]):
        return jsonify({'error': 'Faltan datos'}), 400

    if not validar_fecha(nueva_fecha):
        return jsonify({'error': 'Nueva fecha inválida o pasada'}), 400
    if not validar_hora(nueva_hora):
        return jsonify({'error': 'Nueva hora inválida'}), 400

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

if __name__ == '__main__':
    app.run(debug=True, port=5000)