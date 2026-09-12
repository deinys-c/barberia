from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
from database import get_db
from helpers import ahora_ve, obtener_usuario_actual
from notificaciones import enviar_telegram
from disponibilidad import calcular_huecos_libres, obtener_duracion_servicio
from config import ZONA_HORARIA_VE, DIAS_ES
import json

public_bp = Blueprint('public', __name__)

@public_bp.route('/')
def home():
    return jsonify({'mensaje': 'API Gocho Barber funcionando', 'status': 'ok'})

@public_bp.route('/api/barberos', methods=['GET'])
def listar_barberos_publico():
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT id, nombre FROM barberos WHERE activo = 1 ORDER BY nombre')
        barberos = cursor.fetchall()
        conn.close()
        return jsonify([dict(b) for b in barberos])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@public_bp.route('/api/servicios', methods=['GET'])
def listar_servicios_publico():
    barbero_id = request.args.get('barbero_id', 0, type=int)
    try:
        conn = get_db()
        cursor = conn.cursor()
        if barbero_id > 0:
            # Servicios de un barbero específico
            cursor.execute('''
                SELECT id, nombre, duracion_minutos, precio, descripcion, barbero_id
                FROM servicios WHERE activo = 1 AND barbero_id = %s
                ORDER BY id
            ''', (barbero_id,))
            servicios = [dict(s) for s in cursor.fetchall()]
        else:
            # Cuando es "Cualquiera": usar servicios de UN barbero representativo
            # (el que tenga más servicios, o el primero alfabéticamente)
            cursor.execute('''
                SELECT barbero_id, COUNT(*) as cnt
                FROM servicios WHERE activo = 1
                GROUP BY barbero_id
                ORDER BY cnt DESC, barbero_id ASC
                LIMIT 1
            ''')
            row = cursor.fetchone()
            if row:
                bid_ref = row['barbero_id']
                cursor.execute('''
                    SELECT id, nombre, duracion_minutos, precio, descripcion, barbero_id
                    FROM servicios WHERE activo = 1 AND barbero_id = %s
                    ORDER BY id
                ''', (bid_ref,))
                servicios = [dict(s) for s in cursor.fetchall()]
            else:
                servicios = []
        conn.close()
        return jsonify(servicios)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@public_bp.route('/api/catalogo', methods=['GET'])
def catalogo_publico():
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, tipo, archivo, nombre, descripcion, precio, orden
            FROM catalogo WHERE activo = 1
            ORDER BY tipo, orden, nombre
        ''')
        items = cursor.fetchall()
        conn.close()
        return jsonify([dict(i) for i in items])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@public_bp.route('/api/disponibilidad', methods=['GET'])
def disponibilidad():
    fecha = request.args.get('fecha')
    barbero_id = request.args.get('barbero_id', 0, type=int)
    servicio_id = request.args.get('servicio_id', 0, type=int)
    if not fecha:
        return jsonify({'error': 'Falta fecha'}), 400
    try:
        disponibles = calcular_huecos_libres(fecha, barbero_id, servicio_id)
        return jsonify({'disponibles': disponibles, 'fecha': fecha, 'total': len(disponibles)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@public_bp.route('/api/reservar', methods=['POST'])
def reservar():
    data = request.json
    required = ['fecha', 'hora_inicio', 'servicio_id', 'nombre']
    if not all(k in data for k in required):
        return jsonify({'error': 'Faltan datos obligatorios'}), 400

    try:
        fecha_cita = datetime.strptime(f"{data['fecha']} {data['hora_inicio']}", "%Y-%m-%d %H:%M")
        fecha_cita = fecha_cita.replace(tzinfo=ZONA_HORARIA_VE)
        if fecha_cita < ahora_ve():
            return jsonify({'error': 'No se pueden hacer reservas en el pasado'}), 400
    except ValueError:
        return jsonify({'error': 'Formato inválido'}), 400

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
        cursor.execute('SELECT duracion_minutos, nombre as servicio_nombre, barbero_id FROM servicios WHERE id = %s AND activo = 1', (servicio_id,))
        servicio = cursor.fetchone()
        if not servicio:
            conn.close()
            return jsonify({'error': 'Servicio no válido'}), 400

        duracion = servicio['duracion_minutos']
        servicio_nombre = servicio['servicio_nombre']
        # Si el servicio pertenece a un barbero y no se especificó barbero, usar ese
        if barbero_id == 0 and servicio['barbero_id']:
            barbero_id = servicio['barbero_id']

        h, m = map(int, hora_inicio.split(':'))
        total_min = h * 60 + m + duracion
        hora_fin = f"{total_min // 60:02d}:{total_min % 60:02d}"
        alerta_cierre = 1 if total_min > 17 * 60 else 0

        diff_min = (fecha_cita - ahora_ve()).total_seconds() / 60
        tipo_reserva = 'urgente' if diff_min < 60 else 'normal'
        estado = 'confirmada' if tipo_reserva == 'normal' else 'pendiente_confirmacion'

        if barbero_id == 0:
            cursor.execute('SELECT id, nombre, dias_trabajo FROM barberos WHERE activo = 1')
            barberos = cursor.fetchall()
            fecha_obj = datetime.strptime(fecha, '%Y-%m-%d')
            dia_actual = DIAS_ES[fecha_obj.weekday()]
            barbero_nombre = "Por asignar"
            for b in barberos:
                try:
                    dias = json.loads(b['dias_trabajo'])
                except (json.JSONDecodeError, TypeError):
                    dias = DIAS_ES[:6]
                if dia_actual not in dias:
                    continue
                cursor.execute('SELECT 1 FROM bloqueos WHERE barbero_id = %s AND activo = 1 AND fecha_inicio <= %s AND fecha_fin >= %s', (b['id'], fecha, fecha))
                if cursor.fetchone():
                    continue
                cursor.execute('''
                    SELECT 1 FROM citas 
                    WHERE barbero_id = %s AND fecha = %s AND hora_inicio = %s
                    AND estado IN ('confirmada', 'pendiente_confirmacion')
                ''', (b['id'], fecha, hora_inicio))
                if not cursor.fetchone():
                    barbero_id = b['id']
                    barbero_nombre = b['nombre']
                    break
            if barbero_id == 0:
                conn.close()
                return jsonify({'error': 'No hay barberos disponibles'}), 409
        else:
            cursor.execute('SELECT dias_trabajo, nombre FROM barberos WHERE id = %s AND activo = 1', (barbero_id,))
            b = cursor.fetchone()
            if not b:
                conn.close()
                return jsonify({'error': 'Barbero no válido'}), 400
            barbero_nombre = b['nombre']
            fecha_obj = datetime.strptime(fecha, '%Y-%m-%d')
            dia_actual = DIAS_ES[fecha_obj.weekday()]
            try:
                dias = json.loads(b['dias_trabajo'])
            except (json.JSONDecodeError, TypeError):
                dias = DIAS_ES[:6]
            if dia_actual not in dias:
                conn.close()
                return jsonify({'error': 'El barbero no trabaja ese día'}), 400
            cursor.execute('SELECT 1 FROM bloqueos WHERE barbero_id = %s AND activo = 1 AND fecha_inicio <= %s AND fecha_fin >= %s', (barbero_id, fecha, fecha))
            if cursor.fetchone():
                conn.close()
                return jsonify({'error': 'El barbero no está disponible'}), 409
            cursor.execute('''
                SELECT 1 FROM citas 
                WHERE barbero_id = %s AND fecha = %s AND hora_inicio = %s
                AND estado IN ('confirmada', 'pendiente_confirmacion')
            ''', (barbero_id, fecha, hora_inicio))
            if cursor.fetchone():
                conn.close()
                return jsonify({'error': 'El hueco ya no está disponible'}), 409

        cursor.execute('SELECT id FROM clientes WHERE nombre = %s AND telefono = %s', (nombre, telefono))
        cliente = cursor.fetchone()
        if cliente:
            cliente_id = cliente['id']
        else:
            cursor.execute('''
                INSERT INTO clientes (nombre, telefono, notas_habituales) 
                VALUES (%s, %s, %s) RETURNING id
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

        try:
            emoji = "⚠️ URGENTE" if tipo_reserva == 'urgente' else "✅ Confirmada"
            enviar_telegram(
                f"🔔 <b>NUEVA CITA #{cita_id}</b>\n\n"
                f"👤 {nombre}\n📱 {telefono or 'N/A'}\n"
                f"✂️ {servicio_nombre}\n📅 {fecha}\n⏰ {hora_inicio}\n"
                f"💈 {barbero_nombre}\n\n{emoji}"
            )
        except Exception as e:
            pass

        if tipo_reserva == 'urgente':
            return jsonify({'mensaje': 'Solicitud urgente enviada', 'citaId': cita_id, 'estado': 'pendiente_confirmacion'})
        else:
            return jsonify({'mensaje': '¡Cita agendada!', 'citaId': cita_id, 'estado': 'confirmada'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500