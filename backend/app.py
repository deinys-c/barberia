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

logging.basicConfig(
    filename='notificaciones.log',
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)

SIMULAR_FALLO_NOTIFICACION = os.environ.get('SIMULAR_FALLO', 'False').lower() == 'true'
TIEMPO_ESPERA_FALLO_MIN = int(os.environ.get('TIEMPO_ESPERA', '20'))
BARBERO_PASSWORD = os.environ.get('BARBERO_PASSWORD', 'barberia2026')

init_db()

# ========== FUNCIONES AUXILIARES ==========
DIAS_ES = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo']

def es_dia_habil(fecha_str):
    try:
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d')
        return fecha.weekday() < 6
    except ValueError:
        return False

def verificar_barbero():
    password = request.headers.get('X-Password')
    return password == BARBERO_PASSWORD

def actualizar_citas_pasadas():
    """Marca citas pasadas como realizadas/expiradas."""
    try:
        conn = get_db()
        cursor = conn.cursor()
        hoy = datetime.now().strftime('%Y-%m-%d')
        cursor.execute("UPDATE citas SET estado = 'realizada' WHERE fecha < %s AND estado = 'confirmada'", (hoy,))
        cursor.execute("UPDATE citas SET estado = 'expirada' WHERE fecha < %s AND estado = 'pendiente_confirmacion'", (hoy,))
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"Error actualizando citas pasadas: {e}")

def calcular_huecos_libres(fecha_str, barbero_id=0):
    """
    Genera horas disponibles.
    - barbero_id > 0: solo ese barbero.
    - barbero_id = 0: cualquier barbero activo.
    """
    conn = get_db()
    cursor = conn.cursor()

    if not es_dia_habil(fecha_str):
        conn.close()
        return []

    fecha = datetime.strptime(fecha_str, '%Y-%m-%d')
    dia_semana = fecha.weekday()

    if dia_semana < 5:
        bloques = [('08:00', '12:00'), ('14:00', '17:00')]
    else:
        bloques = [('08:00', '12:00'), ('14:00', '19:00')]

    todas_las_horas = []
    for inicio_str, fin_str in bloques:
        inicio = datetime.strptime(inicio_str, '%H:%M')
        fin = datetime.strptime(fin_str, '%H:%M')
        hora_actual = inicio
        while hora_actual <= fin:
            todas_las_horas.append(hora_actual.strftime('%H:%M'))
            hora_actual += timedelta(minutes=30)

    if barbero_id > 0:
                # Verificar bloqueos
        cursor.execute('''
            SELECT 1 FROM bloqueos 
            WHERE barbero_id = %s AND activo = 1 
            AND fecha_inicio <= %s AND fecha_fin >= %s
        ''', (barbero_id, fecha_str, fecha_str))
        if cursor.fetchone():
            conn.close()
            return []
        cursor.execute('SELECT dias_trabajo FROM barberos WHERE id = %s AND activo = 1', (barbero_id,))
        barbero = cursor.fetchone()
        if not barbero:
            conn.close()
            return []
        try:
            dias = json.loads(barbero['dias_trabajo'])
        except (json.JSONDecodeError, TypeError):
            dias = DIAS_ES[:6]
        if DIAS_ES[dia_semana] not in dias:
            conn.close()
            return []
        cursor.execute('''
            SELECT hora_inicio FROM citas 
            WHERE barbero_id = %s AND fecha = %s 
            AND estado IN ('confirmada', 'pendiente_confirmacion')
        ''', (barbero_id, fecha_str))
        ocupados = {row['hora_inicio'] for row in cursor.fetchall()}
        disponibles = [h for h in todas_las_horas if h not in ocupados]
        else:
        cursor.execute('SELECT id, dias_trabajo FROM barberos WHERE activo = 1')
        barberos = cursor.fetchall()
        if not barberos:
            conn.close()
            return []
        dia_actual = DIAS_ES[dia_semana]
        barberos_hoy = []
        for b in barberos:
            try:
                dias = json.loads(b['dias_trabajo'])
            except (json.JSONDecodeError, TypeError):
                dias = DIAS_ES[:6]
            if dia_actual not in dias:
                continue
            # Verificar si el barbero está bloqueado ese día
            cursor.execute('''
                SELECT 1 FROM bloqueos 
                WHERE barbero_id = %s AND activo = 1 
                AND fecha_inicio <= %s AND fecha_fin >= %s
            ''', (b['id'], fecha_str, fecha_str))
            if cursor.fetchone():
                continue  # Barbero bloqueado, saltar
            barberos_hoy.append(b['id'])
        if not barberos_hoy:
            conn.close()
            return []
        disponibles = []
        for hora in todas_las_horas:
            for bid in barberos_hoy:
                cursor.execute('''
                    SELECT 1 FROM citas 
                    WHERE barbero_id = %s AND fecha = %s AND hora_inicio = %s
                    AND estado IN ('confirmada', 'pendiente_confirmacion')
                ''', (bid, fecha_str, hora))
                if not cursor.fetchone():
                    disponibles.append(hora)
                    break
    conn.close()
    return sorted(set(disponibles))

# ========== ENDPOINTS PÚBLICOS ==========

@app.route('/')
def home():
    return jsonify({'mensaje': 'API Gocho Barber funcionando', 'status': 'ok'})

@app.route('/api/barberos', methods=['GET'])
def listar_barberos_publico():
    """Lista barberos activos (para el selector de reserva)."""
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT id, nombre FROM barberos WHERE activo = 1 ORDER BY nombre')
        barberos = cursor.fetchall()
        conn.close()
        return jsonify([dict(b) for b in barberos])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/disponibilidad', methods=['GET'])
def disponibilidad():
    fecha = request.args.get('fecha')
    barbero_id = request.args.get('barbero_id', 0, type=int)
    if not fecha:
        return jsonify({'error': 'Falta parámetro fecha'}), 400
    try:
        disponibles = calcular_huecos_libres(fecha, barbero_id)
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
        fecha_cita = datetime.strptime(f"{data['fecha']} {data['hora_inicio']}", "%Y-%m-%d %H:%M")
        if fecha_cita < datetime.now():
            return jsonify({'error': 'No se pueden hacer reservas en el pasado'}), 400
    except ValueError:
        return jsonify({'error': 'Formato de fecha u hora inválido'}), 400

    try:
        fecha = data['fecha']
        hora_inicio = data['hora_inicio']
        servicio_id = int(data['servicio_id'])
        barbero_id = int(data.get('barbero_id', 0))
        nombre = data['nombre'].strip()
        telefono = data.get('telefono', '').strip()
        notas = data.get('notas', '').strip()

        if not nombre:
            return jsonify({'error': 'El nombre es obligatorio'}), 400

        conn = get_db()
        cursor = conn.cursor()

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
        diff_min = (fecha_cita - ahora).total_seconds() / 60
        tipo_reserva = 'urgente' if diff_min < 60 else 'normal'
        estado = 'confirmada' if tipo_reserva == 'normal' else 'pendiente_confirmacion'

        # Asignar barbero si es 0 (cualquiera disponible)
        if barbero_id == 0:
            cursor.execute('SELECT id, dias_trabajo FROM barberos WHERE activo = 1')
            barberos = cursor.fetchall()
            fecha_obj = datetime.strptime(fecha, '%Y-%m-%d')
            dia_actual = DIAS_ES[fecha_obj.weekday()]
            for b in barberos:
                try:
                    dias = json.loads(b['dias_trabajo'])
                except (json.JSONDecodeError, TypeError):
                    dias = DIAS_ES[:6]
                if dia_actual not in dias:
                    continue
                cursor.execute('''
                    SELECT 1 FROM citas 
                    WHERE barbero_id = %s AND fecha = %s AND hora_inicio = %s
                    AND estado IN ('confirmada', 'pendiente_confirmacion')
                ''', (b['id'], fecha, hora_inicio))
                if not cursor.fetchone():
                    barbero_id = b['id']
                    break
            if barbero_id == 0:
                conn.close()
                return jsonify({'error': 'No hay barberos disponibles en ese horario'}), 409
        else:
            # Verificar que el barbero exista y esté activo
            cursor.execute('SELECT dias_trabajo FROM barberos WHERE id = %s AND activo = 1', (barbero_id,))
            b = cursor.fetchone()
            if not b:
                conn.close()
                return jsonify({'error': 'Barbero no válido'}), 400
            fecha_obj = datetime.strptime(fecha, '%Y-%m-%d')
            dia_actual = DIAS_ES[fecha_obj.weekday()]
            try:
                dias = json.loads(b['dias_trabajo'])
            except (json.JSONDecodeError, TypeError):
                dias = DIAS_ES[:6]
            if dia_actual not in dias:
                conn.close()
                return jsonify({'error': 'El barbero no trabaja ese día'}), 400
            # Verificar que el hueco esté libre para ese barbero
            cursor.execute('''
                SELECT 1 FROM citas 
                WHERE barbero_id = %s AND fecha = %s AND hora_inicio = %s
                AND estado IN ('confirmada', 'pendiente_confirmacion')
            ''', (barbero_id, fecha, hora_inicio))
            if cursor.fetchone():
                conn.close()
                return jsonify({'error': 'El hueco ya no está disponible'}), 409

        # Crear o buscar cliente
        cursor.execute('SELECT id FROM clientes WHERE nombre = %s AND telefono = %s', (nombre, telefono))
        cliente = cursor.fetchone()
        if cliente:
            cliente_id = cliente['id']
        else:
                    cursor.execute('''
            INSERT INTO clientes (nombre, telefono, notas_habituales) 
            VALUES (%s, %s, %s)
            RETURNING id
        ''', (nombre, telefono, notas))
        cliente_id = cursor.fetchone()['id']

                cursor.execute('''
            INSERT INTO citas 
            (barbero_id, cliente_id, servicio_id, fecha, hora_inicio, hora_fin, 
             estado, tipo_reserva, alerta_cierre, notas_cliente)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (barbero_id, cliente_id, servicio_id, fecha, hora_inicio, hora_fin,
              estado, tipo_reserva, alerta_cierre, notas))
        cita_id = cursor.fetchone()['id']
        conn.commit()
        conn.close()

        if tipo_reserva == 'urgente':
            logging.info(f"CITA {cita_id} - Reserva urgente: {nombre} - {fecha} {hora_inicio}")
            return jsonify({'mensaje': 'Solicitud urgente enviada. Esperando confirmación del barbero.',
                            'citaId': cita_id, 'estado': 'pendiente_confirmacion'})
        else:
            return jsonify({'mensaje': '¡Cita agendada exitosamente!', 'citaId': cita_id, 'estado': 'confirmada'})
    except Exception as e:
        logging.error(f"Error en reservar: {e}")
        return jsonify({'error': str(e)}), 500

# ========== PANEL BARBERO (ADMIN) ==========

@app.route('/api/panel/login', methods=['POST'])
def login_barbero():
    data = request.json
    password = data.get('password', '')
    if password == BARBERO_PASSWORD:
        return jsonify({'mensaje': 'Login exitoso', 'autenticado': True})
    return jsonify({'error': 'Contraseña incorrecta'}), 401

# ----- GESTIÓN DE BARBEROS (ADMIN) -----

@app.route('/api/admin/barberos', methods=['GET'])
def listar_barberos():
    if not verificar_barbero():
        return jsonify({'error': 'No autorizado'}), 401
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT id, nombre, telefono, email, dias_trabajo, activo FROM barberos ORDER BY activo DESC, nombre')
        barberos = cursor.fetchall()
        conn.close()
        return jsonify([dict(b) for b in barberos])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/barberos', methods=['POST'])
def crear_barbero():
    if not verificar_barbero():
        return jsonify({'error': 'No autorizado'}), 401
    data = request.json
    if not data.get('nombre'):
        return jsonify({'error': 'El nombre es obligatorio'}), 400
    try:
        conn = get_db()
        cursor = conn.cursor()
        dias = data.get('dias_trabajo', ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado'])
        # ✅ USAR RETURNING id PARA POSTGRESQL
        cursor.execute('''
            INSERT INTO barberos (nombre, telefono, email, dias_trabajo)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        ''', (data['nombre'].strip(), data.get('telefono', '').strip(),
              data.get('email', '').strip(), json.dumps(dias)))
        nuevo_id = cursor.fetchone()['id']
        conn.commit()
        conn.close()
        return jsonify({'mensaje': 'Barbero creado exitosamente', 'id': nuevo_id})
    except Exception as e:
        logging.error(f"Error creando barbero: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/barberos/<int:barbero_id>', methods=['PUT'])
def actualizar_barbero(barbero_id):
    if not verificar_barbero():
        return jsonify({'error': 'No autorizado'}), 401
    data = request.json
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM barberos WHERE id = %s', (barbero_id,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({'error': 'Barbero no encontrado'}), 404
        campos, valores = [], []
        if 'nombre' in data:
            campos.append('nombre = %s'); valores.append(data['nombre'].strip())
        if 'telefono' in data:
            campos.append('telefono = %s'); valores.append(data['telefono'].strip())
        if 'email' in data:
            campos.append('email = %s'); valores.append(data['email'].strip())
        if 'dias_trabajo' in data:
            campos.append('dias_trabajo = %s'); valores.append(json.dumps(data['dias_trabajo']))
        if 'activo' in data:
            campos.append('activo = %s'); valores.append(1 if data['activo'] else 0)
        if not campos:
            conn.close()
            return jsonify({'error': 'No hay campos para actualizar'}), 400
        valores.append(barbero_id)
        cursor.execute(f"UPDATE barberos SET {', '.join(campos)} WHERE id = %s", valores)
        conn.commit()
        conn.close()
        return jsonify({'mensaje': 'Barbero actualizado exitosamente'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/barberos/<int:barbero_id>', methods=['DELETE'])
def eliminar_barbero(barbero_id):
    if not verificar_barbero():
        return jsonify({'error': 'No autorizado'}), 401
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Verificar que existe
        cursor.execute('SELECT nombre FROM barberos WHERE id = %s AND activo = 1', (barbero_id,))
        barbero = cursor.fetchone()
        if not barbero:
            conn.close()
            return jsonify({'error': 'Barbero no encontrado o ya desactivado'}), 404
        
        # Desactivar barbero
        cursor.execute('UPDATE barberos SET activo = 0 WHERE id = %s', (barbero_id,))
        
        # Cancelar sus citas futuras
        hoy = datetime.now().strftime('%Y-%m-%d')
        cursor.execute('''
            UPDATE citas SET estado = 'cancelada_por_barbero'
            WHERE barbero_id = %s AND fecha >= %s
            AND estado IN ('confirmada', 'pendiente_confirmacion')
        ''', (barbero_id, hoy))
        canceladas = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'mensaje': f'Barbero "{barbero["nombre"]}" desactivado. {canceladas} citas canceladas.',
            'citas_canceladas': canceladas
        })
    except Exception as e:
        logging.error(f"Error desactivando barbero: {e}")
        return jsonify({'error': str(e)}), 500

# ----- PANEL: CITAS -----

@app.route('/api/panel/pendientes', methods=['GET'])
def listar_pendientes():
    if not verificar_barbero():
        return jsonify({'error': 'No autorizado'}), 401
    barbero_id = request.args.get('barbero_id', 0, type=int)
    try:
        actualizar_citas_pasadas()
        conn = get_db()
        cursor = conn.cursor()
        hoy = datetime.now().strftime('%Y-%m-%d')
        query = '''
            SELECT c.id, c.fecha, c.hora_inicio, c.hora_fin, c.estado, c.tipo_reserva,
                   cl.nombre as cliente, cl.telefono, s.nombre as servicio,
                   b.nombre as barbero, b.id as barbero_id,
                   c.alerta_cierre, c.notas_cliente
            FROM citas c
            JOIN clientes cl ON c.cliente_id = cl.id
            JOIN servicios s ON c.servicio_id = s.id
            JOIN barberos b ON c.barbero_id = b.id
            WHERE c.estado = 'pendiente_confirmacion' AND c.fecha >= %s
        '''
        params = [hoy]
        if barbero_id > 0:
            query += ' AND c.barbero_id = %s'
            params.append(barbero_id)
        query += ' ORDER BY c.fecha, c.hora_inicio'
        cursor.execute(query, params)
        citas = cursor.fetchall()
        conn.close()
        return jsonify([dict(c) for c in citas])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/panel/historial', methods=['GET'])
def historial_citas():
    if not verificar_barbero():
        return jsonify({'error': 'No autorizado'}), 401
    barbero_id = request.args.get('barbero_id', 0, type=int)
    try:
        actualizar_citas_pasadas()
        conn = get_db()
        cursor = conn.cursor()
        query = '''
            SELECT c.id, c.fecha, c.hora_inicio, c.estado, c.tipo_reserva,
                   cl.nombre as cliente, s.nombre as servicio,
                   b.nombre as barbero
            FROM citas c
            JOIN clientes cl ON c.cliente_id = cl.id
            JOIN servicios s ON c.servicio_id = s.id
            JOIN barberos b ON c.barbero_id = b.id
        '''
        params = []
        if barbero_id > 0:
            query += ' WHERE c.barbero_id = %s'
            params.append(barbero_id)
        query += ' ORDER BY c.fecha DESC, c.hora_inicio DESC LIMIT 100'
        cursor.execute(query, params)
        citas = cursor.fetchall()
        conn.close()
        return jsonify([dict(c) for c in citas])
    except Exception as e:
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
        cursor.execute("UPDATE citas SET estado = 'confirmada' WHERE id = %s", (cita_id,))
        if cita['cita_original_id']:
            cursor.execute("UPDATE citas SET estado = 'cancelada_por_barbero' WHERE id = %s", (cita['cita_original_id'],))
        conn.commit()
        conn.close()
        return jsonify({'mensaje': 'Cita confirmada exitosamente'})
    except Exception as e:
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
        cursor.execute("UPDATE citas SET estado = 'cancelada_por_barbero' WHERE id = %s", (cita_id,))
        conn.commit()
        conn.close()
        return jsonify({'mensaje': 'Cita rechazada'})
    except Exception as e:
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
        cursor.execute('SELECT estado, fecha FROM citas WHERE id = %s', (cita_id,))
        cita = cursor.fetchone()
        if not cita:
            conn.close()
            return jsonify({'error': 'Cita no encontrada'}), 404
        if cita['estado'] != 'confirmada':
            conn.close()
            return jsonify({'error': 'Solo se pueden cancelar citas confirmadas'}), 400
        if cita['fecha'] < datetime.now().strftime('%Y-%m-%d'):
            conn.close()
            return jsonify({'error': 'No se pueden cancelar citas pasadas'}), 400
        cursor.execute("UPDATE citas SET estado = 'cancelada_por_barbero' WHERE id = %s", (cita_id,))
        conn.commit()
        conn.close()
        return jsonify({'mensaje': 'Cita cancelada exitosamente'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/panel/bloquear', methods=['POST'])
def bloquear_dias():
    if not verificar_barbero():
        return jsonify({'error': 'No autorizado'}), 401
    data = request.json
    fecha_inicio = data.get('fecha_inicio')
    fecha_fin = data.get('fecha_fin')
    motivo = data.get('motivo', 'Descanso')
    barbero_id = int(data.get('barbero_id', 1))
    if not fecha_inicio or not fecha_fin:
        return jsonify({'error': 'Faltan fechas'}), 400
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, fecha, hora_inicio FROM citas 
            WHERE barbero_id = %s AND fecha BETWEEN %s AND %s AND estado = 'confirmada'
        ''', (barbero_id, fecha_inicio, fecha_fin))
        citas_afectadas = cursor.fetchall()
        if citas_afectadas:
            conn.close()
            return jsonify({'citas_afectadas': [dict(c) for c in citas_afectadas],
                            'mensaje': 'Hay citas confirmadas. ¿Mantener o cancelar todas?'}), 409
        cursor.execute('''
            INSERT INTO bloqueos (barbero_id, fecha_inicio, fecha_fin, motivo)
            VALUES (%s, %s, %s, %s)
        ''', (barbero_id, fecha_inicio, fecha_fin, motivo))
        conn.commit()
        conn.close()
        return jsonify({'mensaje': 'Bloqueo agregado correctamente'})
    except Exception as e:
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
        cursor.execute(f"UPDATE citas SET estado = 'cancelada_por_barbero' WHERE id IN ({placeholders})", ids)
        afectadas = cursor.rowcount
        conn.commit()
        conn.close()
        return jsonify({'mensaje': f'{afectadas} citas canceladas'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ========== CLIENTE ==========

@app.route('/api/mis-citas', methods=['GET'])
def mis_citas():
    telefono = request.args.get('telefono')
    if not telefono:
        return jsonify({'error': 'Falta teléfono'}), 400
    try:
        actualizar_citas_pasadas()
        conn = get_db()
        cursor = conn.cursor()
        hoy = datetime.now().strftime('%Y-%m-%d')
        cursor.execute('''
            SELECT c.id, c.fecha, c.hora_inicio, c.hora_fin, c.estado, s.nombre as servicio,
                   b.nombre as barbero, c.alerta_cierre
            FROM citas c
            JOIN clientes cl ON c.cliente_id = cl.id
            JOIN servicios s ON c.servicio_id = s.id
            JOIN barberos b ON c.barbero_id = b.id
            WHERE cl.telefono = %s AND c.fecha >= %s
            AND c.estado IN ('confirmada', 'pendiente_confirmacion')
            ORDER BY c.fecha, c.hora_inicio
        ''', (telefono, hoy))
        citas = cursor.fetchall()
        conn.close()
        return jsonify([dict(c) for c in citas])
    except Exception as e:
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
        cursor.execute('SELECT estado, fecha FROM citas WHERE id = %s', (cita_id,))
        cita = cursor.fetchone()
        if not cita:
            conn.close()
            return jsonify({'error': 'Cita no encontrada'}), 404
        if cita['estado'] not in ('confirmada', 'pendiente_confirmacion'):
            conn.close()
            return jsonify({'error': 'No se puede cancelar esta cita'}), 400
        if cita['fecha'] < datetime.now().strftime('%Y-%m-%d'):
            conn.close()
            return jsonify({'error': 'No se pueden cancelar citas pasadas'}), 400
        cursor.execute("UPDATE citas SET estado = 'cancelada_por_cliente' WHERE id = %s", (cita_id,))
        conn.commit()
        conn.close()
        return jsonify({'mensaje': 'Cita cancelada exitosamente'})
    except Exception as e:
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
        # Validar que la nueva fecha no sea pasada
        try:
            fecha_cita = datetime.strptime(f"{nueva_fecha} {nueva_hora}", "%Y-%m-%d %H:%M")
            if fecha_cita < datetime.now():
                return jsonify({'error': 'No se puede modificar a una fecha pasada'}), 400
        except ValueError:
            return jsonify({'error': 'Formato de fecha u hora inválido'}), 400

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT cliente_id, servicio_id, barbero_id, notas_cliente FROM citas WHERE id = %s', (cita_original_id,))
        original = cursor.fetchone()
        if not original:
            conn.close()
            return jsonify({'error': 'Cita original no encontrada'}), 404

        # Verificar que el nuevo hueco esté libre para ese barbero
        cursor.execute('''
            SELECT 1 FROM citas 
            WHERE barbero_id = %s AND fecha = %s AND hora_inicio = %s 
            AND estado IN ('confirmada', 'pendiente_confirmacion')
        ''', (original['barbero_id'], nueva_fecha, nueva_hora))
        if cursor.fetchone():
            conn.close()
            return jsonify({'error': 'El nuevo hueco no está disponible'}), 409

        # Calcular hora de fin según duración del servicio
        cursor.execute('SELECT duracion_minutos FROM servicios WHERE id = %s', (original['servicio_id'],))
        servicio = cursor.fetchone()
        duracion = servicio['duracion_minutos']
        h, m = map(int, nueva_hora.split(':'))
        total_min = h * 60 + m + duracion
        nueva_hora_fin = f"{total_min // 60:02d}:{total_min % 60:02d}"

        # ✅ USAR RETURNING id PARA POSTGRESQL
        cursor.execute('''
            INSERT INTO citas 
            (barbero_id, cliente_id, servicio_id, fecha, hora_inicio, hora_fin, 
             estado, tipo_reserva, alerta_cierre, cita_original_id, notas_cliente)
            VALUES (%s, %s, %s, %s, %s, %s, 'pendiente_confirmacion', 'modificacion', %s, %s, %s)
            RETURNING id
        ''', (original['barbero_id'], original['cliente_id'], original['servicio_id'],
              nueva_fecha, nueva_hora, nueva_hora_fin,
              1 if total_min > 17*60 else 0, cita_original_id, original['notas_cliente']))
        nueva_cita_id = cursor.fetchone()['id']
        conn.commit()
        conn.close()
        return jsonify({
            'mensaje': 'Solicitud de modificación enviada. Espera confirmación del barbero.',
            'nueva_cita_id': nueva_cita_id
        })
    except Exception as e:
        logging.error(f"Error en solicitar_modificacion: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)