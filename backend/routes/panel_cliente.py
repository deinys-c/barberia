from flask import Blueprint, request, jsonify
from datetime import datetime
from database import get_db
from helpers import requiere_autenticacion, ahora_ve, actualizar_citas_pasadas
from notificaciones import enviar_telegram
from config import ZONA_HORARIA_VE

panel_bp = Blueprint('panel', __name__)

# ========== PANEL BARBERO ==========

@panel_bp.route('/api/panel/pendientes', methods=['GET'])
def listar_pendientes():
    user, error, code = requiere_autenticacion()
    if error: return error, code
    try:
        actualizar_citas_pasadas()
        conn = get_db()
        cursor = conn.cursor()
        hoy = ahora_ve().strftime('%Y-%m-%d')
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
        if user['rol'] == 'barbero' and user['barbero_id']:
            query += ' AND c.barbero_id = %s'
            params.append(user['barbero_id'])
        query += ' ORDER BY c.fecha, c.hora_inicio'
        cursor.execute(query, params)
        citas = cursor.fetchall()
        conn.close()
        return jsonify([dict(c) for c in citas])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@panel_bp.route('/api/panel/historial', methods=['GET'])
def historial_citas():
    user, error, code = requiere_autenticacion()
    if error: return error, code
    try:
        actualizar_citas_pasadas()
        conn = get_db()
        cursor = conn.cursor()
        query = '''
            SELECT c.id, c.fecha, c.hora_inicio, c.estado, c.tipo_reserva,
                   cl.nombre as cliente, s.nombre as servicio, b.nombre as barbero
            FROM citas c
            JOIN clientes cl ON c.cliente_id = cl.id
            JOIN servicios s ON c.servicio_id = s.id
            JOIN barberos b ON c.barbero_id = b.id
        '''
        params = []
        if user['rol'] == 'barbero' and user['barbero_id']:
            query += ' WHERE c.barbero_id = %s'
            params.append(user['barbero_id'])
        query += ' ORDER BY c.fecha DESC, c.hora_inicio DESC LIMIT 200'
        cursor.execute(query, params)
        citas = cursor.fetchall()
        conn.close()
        return jsonify([dict(c) for c in citas])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@panel_bp.route('/api/panel/confirmar-cita', methods=['POST'])
def confirmar_cita():
    user, error, code = requiere_autenticacion()
    if error: return error, code
    data = request.json
    cita_id = data.get('cita_id')
    if not cita_id:
        return jsonify({'error': 'Falta cita_id'}), 400
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT estado, cita_original_id, barbero_id FROM citas WHERE id = %s', (cita_id,))
        cita = cursor.fetchone()
        if not cita:
            conn.close()
            return jsonify({'error': 'No encontrada'}), 404
        if user['rol'] == 'barbero' and cita['barbero_id'] != user['barbero_id']:
            conn.close()
            return jsonify({'error': 'No autorizado'}), 403
        if cita['estado'] != 'pendiente_confirmacion':
            conn.close()
            return jsonify({'error': 'No está pendiente'}), 400
        cursor.execute("UPDATE citas SET estado = 'confirmada' WHERE id = %s", (cita_id,))
        if cita['cita_original_id']:
            cursor.execute("UPDATE citas SET estado = 'cancelada_por_barbero' WHERE id = %s", (cita['cita_original_id'],))
        conn.commit()
        conn.close()
        enviar_telegram(f"✅ Cita #{cita_id} confirmada por {user['username']}")
        return jsonify({'mensaje': 'Confirmada'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@panel_bp.route('/api/panel/rechazar-cita', methods=['POST'])
def rechazar_cita():
    user, error, code = requiere_autenticacion()
    if error: return error, code
    data = request.json
    cita_id = data.get('cita_id')
    if not cita_id:
        return jsonify({'error': 'Falta cita_id'}), 400
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT estado, barbero_id FROM citas WHERE id = %s', (cita_id,))
        cita = cursor.fetchone()
        if not cita:
            conn.close()
            return jsonify({'error': 'No encontrada'}), 404
        if user['rol'] == 'barbero' and cita['barbero_id'] != user['barbero_id']:
            conn.close()
            return jsonify({'error': 'No autorizado'}), 403
        if cita['estado'] != 'pendiente_confirmacion':
            conn.close()
            return jsonify({'error': 'No está pendiente'}), 400
        cursor.execute("UPDATE citas SET estado = 'cancelada_por_barbero' WHERE id = %s", (cita_id,))
        conn.commit()
        conn.close()
        enviar_telegram(f"❌ Cita #{cita_id} rechazada por {user['username']}")
        return jsonify({'mensaje': 'Rechazada'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@panel_bp.route('/api/panel/cancelar-cita-confirmada', methods=['POST'])
def cancelar_cita_confirmada():
    user, error, code = requiere_autenticacion()
    if error: return error, code
    data = request.json
    cita_id = data.get('cita_id')
    if not cita_id:
        return jsonify({'error': 'Falta cita_id'}), 400
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT estado, fecha, barbero_id FROM citas WHERE id = %s', (cita_id,))
        cita = cursor.fetchone()
        if not cita:
            conn.close()
            return jsonify({'error': 'No encontrada'}), 404
        if user['rol'] == 'barbero' and cita['barbero_id'] != user['barbero_id']:
            conn.close()
            return jsonify({'error': 'No autorizado'}), 403
        if cita['estado'] != 'confirmada':
            conn.close()
            return jsonify({'error': 'No confirmada'}), 400
        if cita['fecha'] < ahora_ve().strftime('%Y-%m-%d'):
            conn.close()
            return jsonify({'error': 'Es del pasado'}), 400
        cursor.execute("UPDATE citas SET estado = 'cancelada_por_barbero' WHERE id = %s", (cita_id,))
        conn.commit()
        conn.close()
        enviar_telegram(f"🚫 Cita #{cita_id} cancelada por {user['username']}")
        return jsonify({'mensaje': 'Cancelada'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@panel_bp.route('/api/admin/citas/<int:cita_id>', methods=['DELETE'])
def eliminar_cita_permanente(cita_id):
    from helpers import requiere_admin
    user, error, code = requiere_admin()
    if error: return error, code
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM citas WHERE id = %s', (cita_id,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({'error': 'No encontrada'}), 404
        cursor.execute('DELETE FROM logs_notificaciones WHERE cita_id = %s', (cita_id,))
        cursor.execute('DELETE FROM citas WHERE id = %s', (cita_id,))
        conn.commit()
        conn.close()
        return jsonify({'mensaje': 'Cita eliminada permanentemente'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@panel_bp.route('/api/panel/bloquear', methods=['POST'])
def bloquear_dias():
    user, error, code = requiere_autenticacion()
    if error: return error, code
    data = request.json
    fecha_inicio = data.get('fecha_inicio')
    fecha_fin = data.get('fecha_fin')
    motivo = data.get('motivo', 'Descanso')
    if not fecha_inicio or not fecha_fin:
        return jsonify({'error': 'Faltan fechas'}), 400
    
    if user['rol'] == 'admin':
        barbero_id = int(data.get('barbero_id', 1))
    else:
        barbero_id = user['barbero_id']
        if not barbero_id:
            return jsonify({'error': 'No tienes barbero asociado'}), 400
    
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
                            'mensaje': 'Hay citas confirmadas'}), 409
        cursor.execute('''
            INSERT INTO bloqueos (barbero_id, fecha_inicio, fecha_fin, motivo)
            VALUES (%s, %s, %s, %s)
        ''', (barbero_id, fecha_inicio, fecha_fin, motivo))
        conn.commit()
        conn.close()
        enviar_telegram(f"📅 Bloqueo: {fecha_inicio} → {fecha_fin}\nPor: {user['username']}")
        return jsonify({'mensaje': 'Bloqueo agregado'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@panel_bp.route('/api/panel/cancelar-citas-masivo', methods=['POST'])
def cancelar_masivo():
    user, error, code = requiere_autenticacion()
    if error: return error, code
    data = request.json
    ids = data.get('cita_ids', [])
    if not ids:
        return jsonify({'error': 'Sin IDs'}), 400
    try:
        conn = get_db()
        cursor = conn.cursor()
        placeholders = ','.join(['%s'] * len(ids))
        cursor.execute(f"UPDATE citas SET estado = 'cancelada_por_barbero' WHERE id IN ({placeholders})", ids)
        afectadas = cursor.rowcount
        conn.commit()
        conn.close()
        enviar_telegram(f"🚫 {afectadas} citas canceladas por {user['username']}")
        return jsonify({'mensaje': f'{afectadas} citas canceladas'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ========== CLIENTE ==========

@panel_bp.route('/api/mis-citas', methods=['GET'])
def mis_citas():
    telefono = request.args.get('telefono')
    if not telefono:
        return jsonify({'error': 'Falta teléfono'}), 400
    try:
        actualizar_citas_pasadas()
        conn = get_db()
        cursor = conn.cursor()
        hoy = ahora_ve().strftime('%Y-%m-%d')
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

@panel_bp.route('/api/cancelar-cita', methods=['POST'])
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
            return jsonify({'error': 'No encontrada'}), 404
        if cita['estado'] not in ('confirmada', 'pendiente_confirmacion'):
            conn.close()
            return jsonify({'error': 'No se puede cancelar'}), 400
        if cita['fecha'] < ahora_ve().strftime('%Y-%m-%d'):
            conn.close()
            return jsonify({'error': 'Es del pasado'}), 400
        cursor.execute("UPDATE citas SET estado = 'cancelada_por_cliente' WHERE id = %s", (cita_id,))
        conn.commit()
        conn.close()
        enviar_telegram(f"❌ Cita #{cita_id} cancelada por el cliente")
        return jsonify({'mensaje': 'Cancelada'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@panel_bp.route('/api/solicitar-modificacion', methods=['POST'])
def solicitar_modificacion():
    data = request.json
    cita_original_id = data.get('cita_original_id')
    nueva_fecha = data.get('nueva_fecha')
    nueva_hora = data.get('nueva_hora')
    if not all([cita_original_id, nueva_fecha, nueva_hora]):
        return jsonify({'error': 'Faltan datos'}), 400
    try:
        try:
            fecha_cita = datetime.strptime(f"{nueva_fecha} {nueva_hora}", "%Y-%m-%d %H:%M")
            fecha_cita = fecha_cita.replace(tzinfo=ZONA_HORARIA_VE)
            if fecha_cita < ahora_ve():
                return jsonify({'error': 'Fecha pasada'}), 400
        except ValueError:
            return jsonify({'error': 'Formato inválido'}), 400

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT cliente_id, servicio_id, barbero_id, notas_cliente FROM citas WHERE id = %s', (cita_original_id,))
        original = cursor.fetchone()
        if not original:
            conn.close()
            return jsonify({'error': 'Original no encontrada'}), 404

        cursor.execute('''
            SELECT 1 FROM citas 
            WHERE barbero_id = %s AND fecha = %s AND hora_inicio = %s 
            AND estado IN ('confirmada', 'pendiente_confirmacion')
        ''', (original['barbero_id'], nueva_fecha, nueva_hora))
        if cursor.fetchone():
            conn.close()
            return jsonify({'error': 'Hueco no disponible'}), 409

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
            VALUES (%s, %s, %s, %s, %s, %s, 'pendiente_confirmacion', 'modificacion', %s, %s, %s)
            RETURNING id
        ''', (original['barbero_id'], original['cliente_id'], original['servicio_id'],
              nueva_fecha, nueva_hora, nueva_hora_fin,
              1 if total_min > 17*60 else 0, cita_original_id, original['notas_cliente']))
        nueva_cita_id = cursor.fetchone()['id']
        conn.commit()
        conn.close()

        enviar_telegram(f"🔄 Modificación cita #{cita_original_id} → {nueva_fecha} {nueva_hora}")
        return jsonify({'mensaje': 'Solicitud enviada', 'nueva_cita_id': nueva_cita_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500