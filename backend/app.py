import os
import json
import logging
import threading
import time
import requests
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from database import get_db, init_db

# Cargar variables de entorno desde .env (local)
load_dotenv()

app = Flask(__name__)
CORS(app)

# Configurar logging
logging.basicConfig(
    filename='notificaciones.log',
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)

# ========== CONFIGURACIÓN DE WHATSAPP ==========
# Obtener variables de entorno (definidas en Render o en .env local)
WHATSAPP_PHONE_NUMBER_ID = os.environ.get('WHATSAPP_PHONE_NUMBER_ID')
WHATSAPP_ACCESS_TOKEN = os.environ.get('WHATSAPP_ACCESS_TOKEN')
WHATSAPP_RECIPIENT_NUMBER = os.environ.get('WHATSAPP_RECIPIENT_NUMBER')

# Verificar que las variables estén configuradas
if not WHATSAPP_PHONE_NUMBER_ID or not WHATSAPP_ACCESS_TOKEN or not WHATSAPP_RECIPIENT_NUMBER:
    print("⚠️ ADVERTENCIA: Variables de WhatsApp no configuradas. Se usará simulación.")
    WHATSAPP_CONFIGURED = False
else:
    WHATSAPP_CONFIGURED = True
    print("✅ WhatsApp configurado correctamente.")

# ========== VARIABLES DE SIMULACIÓN ==========
# Si SIMULAR_FALLO=True, la notificación se marcará como fallida (para probar Escenario B)
SIMULAR_FALLO = os.environ.get('SIMULAR_FALLO', 'False').lower() == 'true'
TIEMPO_ESPERA_FALLO_MIN = int(os.environ.get('TIEMPO_ESPERA', '20'))

# Inicializar base de datos
init_db()

# ---------- FUNCIONES AUXILIARES ----------
def es_dia_habil(fecha_str):
    fecha = datetime.strptime(fecha_str, '%Y-%m-%d')
    return fecha.weekday() < 6

def calcular_huecos_libres(fecha_str, barbero_id=1):
    """
    Devuelve lista de horas libres para un barbero en una fecha,
    considerando el horario según el día de la semana y descanso.
    """
    conn = get_db()
    cursor = conn.cursor()

    # Convertir fecha a objeto datetime para saber día de la semana
    fecha = datetime.strptime(fecha_str, '%Y-%m-%d')
    dia_semana = fecha.weekday()  # 0=lunes, 5=sábado, 6=domingo

    if dia_semana == 6:  # Domingo
        conn.close()
        return []

    # Obtener horario base del barbero (puede ser custom, pero usamos el fijo)
    # Para simplificar, definimos bloques según día
    if dia_semana < 5:  # Lunes a viernes
        bloques = [('08:00', '12:00'), ('14:00', '17:00')]
    else:  # Sábado
        bloques = [('08:00', '12:00'), ('14:00', '19:00')]

    # Obtener citas ocupadas para esa fecha (confirmadas o pendientes)
    citas = cursor.execute('''
        SELECT hora_inicio, hora_fin FROM citas 
        WHERE barbero_id = ? AND fecha = ? 
        AND estado IN ('confirmada', 'pendiente_confirmacion')
    ''', (barbero_id, fecha_str)).fetchall()
    ocupados = {c['hora_inicio'] for c in citas}

    # Generar todas las horas de 30 minutos en cada bloque
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
    # Eliminar duplicados (por si acaso) y ordenar
    disponibles = sorted(set(disponibles))
    return disponibles

# ---------- FUNCIÓN PARA ENVIAR NOTIFICACIONES REALES ----------
def enviar_notificacion_whatsapp(cita_id, mensaje):
    """Envía un mensaje de WhatsApp usando la Cloud API de Meta."""
    if not WHATSAPP_CONFIGURED or SIMULAR_FALLO:
        # Si no está configurado o estamos simulando fallo, logueamos y retornamos False
        logging.info(f"CITA {cita_id} - NOTIFICACIÓN SIMULADA: {mensaje}")
        print(f"📨 [SIMULACIÓN] WhatsApp a {WHATSAPP_RECIPIENT_NUMBER}: {mensaje}")
        # Guardar en logs_notificaciones como fallido si SIMULAR_FALLO es True
        conn = get_db()
        cursor = conn.cursor()
        estado = 'fallido' if SIMULAR_FALLO else 'entregado'
        cursor.execute(
            'INSERT INTO logs_notificaciones (cita_id, tipo, estado_envio) VALUES (?, ?, ?)',
            (cita_id, 'whatsapp', estado)
        )
        conn.commit()
        conn.close()
        return not SIMULAR_FALLO  # Si SIMULAR_FALLO=False, simula éxito

    try:
        url = f"https://graph.facebook.com/v18.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
        headers = {
            "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }
        data = {
            "messaging_product": "whatsapp",
            "to": WHATSAPP_RECIPIENT_NUMBER,
            "type": "text",
            "text": {"body": mensaje}
        }
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 200:
            # Éxito
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO logs_notificaciones (cita_id, tipo, estado_envio) VALUES (?, ?, ?)',
                (cita_id, 'whatsapp', 'entregado')
            )
            conn.commit()
            conn.close()
            print(f"✅ WhatsApp enviado a {WHATSAPP_RECIPIENT_NUMBER}")
            logging.info(f"CITA {cita_id} - WhatsApp entregado")
            return True
        else:
            # Fallo en la API
            error_msg = response.json().get('error', {}).get('message', 'Error desconocido')
            print(f"❌ Error WhatsApp: {error_msg}")
            logging.error(f"CITA {cita_id} - Error WhatsApp: {error_msg}")
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO logs_notificaciones (cita_id, tipo, estado_envio, intentos) VALUES (?, ?, ?, ?)',
                (cita_id, 'whatsapp', 'fallido', 1)
            )
            conn.commit()
            conn.close()
            return False
    except Exception as e:
        print(f"❌ Excepción al enviar WhatsApp: {str(e)}")
        logging.error(f"CITA {cita_id} - Excepción WhatsApp: {str(e)}")
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO logs_notificaciones (cita_id, tipo, estado_envio, intentos) VALUES (?, ?, ?, ?)',
            (cita_id, 'whatsapp', 'fallido', 1)
        )
        conn.commit()
        conn.close()
        return False

# ---------- FUNCIÓN PARA PROGRAMAR CANCELACIÓN AUTOMÁTICA ----------
def programar_cancelacion(cita_id):
    """Espera TIEMPO_ESPERA_FALLO_MIN minutos y si la cita sigue pendiente, la cancela."""
    time.sleep(TIEMPO_ESPERA_FALLO_MIN * 60)
    conn = get_db()
    cursor = conn.cursor()
    cita = cursor.execute('SELECT estado FROM citas WHERE id = ?', (cita_id,)).fetchone()
    conn.close()
    if cita and cita['estado'] == 'pendiente_confirmacion':
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('UPDATE citas SET estado = ? WHERE id = ?', ('cancelada_por_sistema', cita_id))
        conn.commit()
        conn.close()
        print(f"⏰ [SISTEMA] Cita ID {cita_id} cancelada automáticamente por falta de confirmación.")
        logging.info(f"CITA {cita_id} - CANCELADA POR SISTEMA (falta confirmación)")

# ---------- ENDPOINTS ----------
@app.route('/')
def home():
    return jsonify({
        'mensaje': 'API Gocho Barber funcionando',
        'status': 'ok',
        'whatsapp': 'configurado' if WHATSAPP_CONFIGURED else 'no configurado'
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

    # Si es reserva urgente, enviar notificación y programar cancelación
    if tipo_reserva == 'urgente':
        mensaje = f"⚠️ SOLICITUD URGENTE\nCliente: {nombre}\nFecha: {fecha}\nHora: {hora_inicio}\nTeléfono: {telefono or 'No proporcionado'}"
        entregado = enviar_notificacion_whatsapp(cita_id, mensaje)

        if not entregado:
            # Si la notificación falló, programar cancelación automática
            threading.Thread(target=programar_cancelacion, args=(cita_id,), daemon=True).start()
            return jsonify({
                'mensaje': 'Solicitud urgente enviada. El sistema notificará al barbero.',
                'citaId': cita_id,
                'estado': 'pendiente_confirmacion'
            })
        else:
            return jsonify({
                'mensaje': '✅ Solicitud urgente enviada. Esperando confirmación del barbero.',
                'citaId': cita_id,
                'estado': 'pendiente_confirmacion'
            })
    else:
        return jsonify({
            'mensaje': '✅ ¡Cita agendada exitosamente!',
            'citaId': cita_id,
            'estado': 'confirmada'
        })

# ========== PANEL BARBERO (sin sesiones) ==========
BARBERO_PASSWORD = os.environ.get('BARBERO_PASSWORD', 'barberia2026')

def verificar_barbero():
    password = request.headers.get('X-Password')
    return password == BARBERO_PASSWORD

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

@app.route('/api/panel/historial', methods=['GET'])
def historial_citas():
    if not verificar_barbero():
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

@app.route('/api/panel/confirmar-cita', methods=['POST'])
def confirmar_cita():
    if not verificar_barbero():
        return jsonify({'error': 'No autorizado'}), 401
    data = request.json
    cita_id = data.get('cita_id')
    if not cita_id:
        return jsonify({'error': 'Falta cita_id'}), 400
    conn = get_db()
    cursor = conn.cursor()
    cita = cursor.execute('SELECT estado, cita_original_id FROM citas WHERE id = ?', (cita_id,)).fetchone()
    if not cita:
        conn.close()
        return jsonify({'error': 'Cita no encontrada'}), 404
    if cita['estado'] != 'pendiente_confirmacion':
        conn.close()
        return jsonify({'error': 'La cita no está pendiente'}), 400
    cursor.execute('UPDATE citas SET estado = ? WHERE id = ?', ('confirmada', cita_id))
    if cita['cita_original_id']:
        cursor.execute('UPDATE citas SET estado = ? WHERE id = ?', ('cancelada_por_barbero', cita['cita_original_id']))
    conn.commit()
    conn.close()
    # Notificar al cliente que su cita fue confirmada (opcional)
    return jsonify({'mensaje': '✅ Cita confirmada'})

@app.route('/api/panel/rechazar-cita', methods=['POST'])
def rechazar_cita():
    if not verificar_barbero():
        return jsonify({'error': 'No autorizado'}), 401
    data = request.json
    cita_id = data.get('cita_id')
    if not cita_id:
        return jsonify({'error': 'Falta cita_id'}), 400
    conn = get_db()
    cursor = conn.cursor()
    cita = cursor.execute('SELECT estado FROM citas WHERE id = ?', (cita_id,)).fetchone()
    if not cita:
        conn.close()
        return jsonify({'error': 'Cita no encontrada'}), 404
    if cita['estado'] != 'pendiente_confirmacion':
        conn.close()
        return jsonify({'error': 'La cita no está pendiente'}), 400
    cursor.execute('UPDATE citas SET estado = ? WHERE id = ?', ('cancelada_por_barbero', cita_id))
    conn.commit()
    conn.close()
    return jsonify({'mensaje': '❌ Cita rechazada'})

@app.route('/api/panel/cancelar-cita-confirmada', methods=['POST'])
def cancelar_cita_confirmada():
    if not verificar_barbero():
        return jsonify({'error': 'No autorizado'}), 401
    data = request.json
    cita_id = data.get('cita_id')
    if not cita_id:
        return jsonify({'error': 'Falta cita_id'}), 400
    conn = get_db()
    cursor = conn.cursor()
    cita = cursor.execute('SELECT estado FROM citas WHERE id = ?', (cita_id,)).fetchone()
    if not cita:
        conn.close()
        return jsonify({'error': 'Cita no encontrada'}), 404
    if cita['estado'] != 'confirmada':
        conn.close()
        return jsonify({'error': 'Solo se pueden cancelar citas confirmadas'}), 400
    cursor.execute('UPDATE citas SET estado = ? WHERE id = ?', ('cancelada_por_barbero', cita_id))
    conn.commit()
    conn.close()
    return jsonify({'mensaje': '✅ Cita cancelada'})

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
    conn = get_db()
    cursor = conn.cursor()
    citas_afectadas = cursor.execute('''
        SELECT id, fecha, hora_inicio, cliente_id FROM citas 
        WHERE barbero_id = 1 AND fecha BETWEEN ? AND ? AND estado = 'confirmada'
    ''', (fecha_inicio, fecha_fin)).fetchall()
    if citas_afectadas:
        conn.close()
        return jsonify({
            'citas_afectadas': [dict(c) for c in citas_afectadas],
            'mensaje': 'Hay citas confirmadas. ¿Mantener o cancelar todas?'
        }), 409
    cursor.execute('INSERT INTO bloqueos (barbero_id, fecha_inicio, fecha_fin, motivo) VALUES (1, ?, ?, ?)',
                   (fecha_inicio, fecha_fin, motivo))
    conn.commit()
    conn.close()
    return jsonify({'mensaje': '✅ Bloqueo agregado correctamente'})

@app.route('/api/panel/cancelar-citas-masivo', methods=['POST'])
def cancelar_masivo():
    if not verificar_barbero():
        return jsonify({'error': 'No autorizado'}), 401
    data = request.json
    ids = data.get('cita_ids', [])
    if not ids:
        return jsonify({'error': 'No se proporcionaron IDs'}), 400
    conn = get_db()
    cursor = conn.cursor()
    placeholders = ','.join('?' * len(ids))
    cursor.execute(f'UPDATE citas SET estado = ? WHERE id IN ({placeholders})', ('cancelada_por_barbero', *ids))
    afectadas = cursor.rowcount
    conn.commit()
    conn.close()
    return jsonify({'mensaje': f'{afectadas} citas canceladas.'})

@app.route('/api/mis-citas', methods=['GET'])
def mis_citas():
    telefono = request.args.get('telefono')
    if not telefono:
        return jsonify({'error': 'Falta teléfono'}), 400
    conn = get_db()
    cursor = conn.cursor()
    citas = cursor.execute('''
        SELECT c.id, c.fecha, c.hora_inicio, c.hora_fin, c.estado, s.nombre as servicio, c.alerta_cierre
        FROM citas c
        JOIN clientes cl ON c.cliente_id = cl.id
        JOIN servicios s ON c.servicio_id = s.id
        WHERE cl.telefono = ? AND c.estado IN ('confirmada', 'pendiente_confirmacion')
        ORDER BY c.fecha, c.hora_inicio
    ''', (telefono,)).fetchall()
    conn.close()
    return jsonify([dict(c) for c in citas])

@app.route('/api/cancelar-cita', methods=['POST'])
def cancelar_cita_cliente():
    data = request.json
    cita_id = data.get('cita_id')
    if not cita_id:
        return jsonify({'error': 'Falta cita_id'}), 400
    conn = get_db()
    cursor = conn.cursor()
    cita = cursor.execute('SELECT estado FROM citas WHERE id = ?', (cita_id,)).fetchone()
    if not cita:
        conn.close()
        return jsonify({'error': 'Cita no encontrada'}), 404
    if cita['estado'] not in ('confirmada', 'pendiente_confirmacion'):
        conn.close()
        return jsonify({'error': 'No se puede cancelar'}), 400
    cursor.execute('UPDATE citas SET estado = ? WHERE id = ?', ('cancelada_por_cliente', cita_id))
    conn.commit()
    conn.close()
    return jsonify({'mensaje': '✅ Cita cancelada'})

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
    servicio = cursor.execute('SELECT duracion_minutos FROM servicios WHERE id = ?', (original['servicio_id'],)).fetchone()
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
        'mensaje': 'Solicitud de modificación enviada. Espera confirmación.',
        'nueva_cita_id': nueva_cita_id
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)