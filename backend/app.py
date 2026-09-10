import os
import json
import logging
from datetime import datetime, timedelta, timezone
from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_db, init_db, normalizar_username
import requests

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-key-123')
CORS(app, supports_credentials=True)

logging.basicConfig(
    filename='notificaciones.log',
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)

# ===== ZONA HORARIA VENEZUELA =====
ZONA_HORARIA_VE = timezone(timedelta(hours=-4))

def ahora_ve():
    return datetime.now(ZONA_HORARIA_VE)

# ===== CONFIG TELEGRAM =====
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')

init_db()

DIAS_ES = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado', 'domingo']

# ========== AUXILIARES ==========

def es_dia_habil(fecha_str):
    try:
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d')
        return fecha.weekday() < 6
    except ValueError:
        return False

def obtener_usuario_actual():
    username = request.headers.get('X-Username')
    if not username:
        return None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT id, username, rol, barbero_id, activo FROM usuarios WHERE username = %s AND activo = 1', (username,))
        user = cursor.fetchone()
        conn.close()
        if user:
            return dict(user)
        return None
    except Exception:
        return None

def requiere_autenticacion():
    user = obtener_usuario_actual()
    if not user:
        return None, jsonify({'error': 'No autenticado'}), 401
    return user, None, None

def requiere_admin():
    user = obtener_usuario_actual()
    if not user:
        return None, jsonify({'error': 'No autenticado'}), 401
    if user['rol'] != 'admin':
        return None, jsonify({'error': 'Requiere permisos de administrador'}), 403
    return user, None, None

def actualizar_citas_pasadas():
    try:
        conn = get_db()
        cursor = conn.cursor()
        hoy = ahora_ve().strftime('%Y-%m-%d')
        cursor.execute("UPDATE citas SET estado = 'realizada' WHERE fecha < %s AND estado = 'confirmada'", (hoy,))
        cursor.execute("UPDATE citas SET estado = 'expirada' WHERE fecha < %s AND estado = 'pendiente_confirmacion'", (hoy,))
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"Error actualizando citas pasadas: {e}")

def enviar_telegram(mensaje, chat_id=None):
    if not TELEGRAM_TOKEN:
        return False
    destinatario = chat_id or TELEGRAM_CHAT_ID
    if not destinatario:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": str(destinatario), "text": mensaje, "parse_mode": "HTML"}
    try:
        response = requests.post(url, json=data, timeout=10)
        response.raise_for_status()
        return True
    except Exception as e:
        logging.error(f"Error Telegram: {e}")
        return False

def calcular_huecos_libres(fecha_str, barbero_id=0):
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
            SELECT 1 FROM bloqueos 
            WHERE barbero_id = %s AND activo = 1 
            AND fecha_inicio <= %s AND fecha_fin >= %s
        ''', (barbero_id, fecha_str, fecha_str))
        if cursor.fetchone():
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
            cursor.execute('''
                SELECT 1 FROM bloqueos 
                WHERE barbero_id = %s AND activo = 1 
                AND fecha_inicio <= %s AND fecha_fin >= %s
            ''', (b['id'], fecha_str, fecha_str))
            if cursor.fetchone():
                continue
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

# ========== PÚBLICOS ==========

@app.route('/')
def home():
    return jsonify({'mensaje': 'API Gocho Barber funcionando', 'status': 'ok'})

@app.route('/api/barberos', methods=['GET'])
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

@app.route('/api/catalogo', methods=['GET'])
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

@app.route('/api/disponibilidad', methods=['GET'])
def disponibilidad():
    fecha = request.args.get('fecha')
    barbero_id = request.args.get('barbero_id', 0, type=int)
    if not fecha:
        return jsonify({'error': 'Falta fecha'}), 400
    try:
        disponibles = calcular_huecos_libres(fecha, barbero_id)
        return jsonify({'disponibles': disponibles, 'fecha': fecha, 'total': len(disponibles)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/reservar', methods=['POST'])
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
        cursor.execute('SELECT duracion_minutos, nombre as servicio_nombre FROM servicios WHERE id = %s AND activo = 1', (servicio_id,))
        servicio = cursor.fetchone()
        if not servicio:
            conn.close()
            return jsonify({'error': 'Servicio no válido'}), 400

        duracion = servicio['duracion_minutos']
        servicio_nombre = servicio['servicio_nombre']
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
                cursor.execute('''
                    SELECT 1 FROM bloqueos 
                    WHERE barbero_id = %s AND activo = 1 
                    AND fecha_inicio <= %s AND fecha_fin >= %s
                ''', (b['id'], fecha, fecha))
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
            cursor.execute('''
                SELECT 1 FROM bloqueos 
                WHERE barbero_id = %s AND activo = 1 
                AND fecha_inicio <= %s AND fecha_fin >= %s
            ''', (barbero_id, fecha, fecha))
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
            logging.error(f"Error Telegram: {e}")

        if tipo_reserva == 'urgente':
            return jsonify({'mensaje': 'Solicitud urgente enviada', 'citaId': cita_id, 'estado': 'pendiente_confirmacion'})
        else:
            return jsonify({'mensaje': '¡Cita agendada!', 'citaId': cita_id, 'estado': 'confirmada'})
    except Exception as e:
        logging.error(f"Error en reservar: {e}")
        return jsonify({'error': str(e)}), 500

# ========== LOGIN ==========

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '')
    if not username or not password:
        return jsonify({'error': 'Usuario y contraseña requeridos'}), 400
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT id, username, password_hash, rol, barbero_id FROM usuarios WHERE username = %s AND activo = 1', (username,))
        user = cursor.fetchone()
        conn.close()
        if not user or not check_password_hash(user['password_hash'], password):
            return jsonify({'error': 'Usuario o contraseña incorrectos'}), 401
        return jsonify({
            'mensaje': 'Login exitoso',
            'username': user['username'],
            'rol': user['rol'],
            'barbero_id': user['barbero_id']
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ========== BARBEROS (ADMIN) ==========

@app.route('/api/admin/barberos', methods=['GET'])
def listar_barberos():
    user, error, code = requiere_autenticacion()
    if error: return error, code
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
    user, error, code = requiere_admin()
    if error: return error, code
    data = request.json
    if not data.get('nombre'):
        return jsonify({'error': 'El nombre es obligatorio'}), 400
    try:
        conn = get_db()
        cursor = conn.cursor()
        dias = data.get('dias_trabajo', ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado'])
        cursor.execute('''
            INSERT INTO barberos (nombre, telefono, email, dias_trabajo)
            VALUES (%s, %s, %s, %s) RETURNING id
        ''', (data['nombre'].strip(), data.get('telefono', '').strip(),
              data.get('email', '').strip(), json.dumps(dias)))
        nuevo_id = cursor.fetchone()['id']
        
        username_base = normalizar_username(data['nombre'])
        username = username_base
        contador = 2
        while True:
            cursor.execute('SELECT 1 FROM usuarios WHERE username = %s', (username,))
            if not cursor.fetchone():
                break
            username = f"{username_base}{contador}"
            contador += 1
        password = f"{username}123"
        pwd_hash = generate_password_hash(password)
        cursor.execute('''
            INSERT INTO usuarios (username, password_hash, rol, barbero_id)
            VALUES (%s, %s, 'barbero', %s)
        ''', (username, pwd_hash, nuevo_id))
        conn.commit()
        conn.close()

        enviar_telegram(f"👨‍🦱 <b>Nuevo barbero</b>\n{data['nombre']}\nUsuario: <code>{username}</code>\nContraseña: <code>{password}</code>")

        return jsonify({
            'mensaje': f'Barbero creado. Usuario: {username} / Contraseña: {password}',
            'id': nuevo_id, 'username': username, 'password': password
        })
    except Exception as e:
        logging.error(f"Error creando barbero: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/barberos/<int:barbero_id>', methods=['PUT'])
def actualizar_barbero(barbero_id):
    user, error, code = requiere_admin()
    if error: return error, code
    data = request.json
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT id, nombre FROM barberos WHERE id = %s', (barbero_id,))
        barbero_actual = cursor.fetchone()
        if not barbero_actual:
            conn.close()
            return jsonify({'error': 'Barbero no encontrado'}), 404
        
        nombre_anterior = barbero_actual['nombre']
        nombre_nuevo = data.get('nombre', nombre_anterior).strip()
        
        campos, valores = [], []
        if 'nombre' in data:
            campos.append('nombre = %s'); valores.append(nombre_nuevo)
        if 'telefono' in data:
            campos.append('telefono = %s'); valores.append(data['telefono'].strip())
        if 'email' in data:
            campos.append('email = %s'); valores.append(data['email'].strip())
        if 'dias_trabajo' in data:
            campos.append('dias_trabajo = %s'); valores.append(json.dumps(data['dias_trabajo']))
        if 'activo' in data:
            campos.append('activo = %s'); valores.append(1 if data['activo'] else 0)
        
        if campos:
            valores.append(barbero_id)
            cursor.execute(f"UPDATE barberos SET {', '.join(campos)} WHERE id = %s", valores)
        
        username_gen = password_gen = None
        if nombre_nuevo != nombre_anterior:
            username_base = normalizar_username(nombre_nuevo)
            username = username_base
            contador = 2
            while True:
                cursor.execute('SELECT 1 FROM usuarios WHERE username = %s AND barbero_id != %s', (username, barbero_id))
                if not cursor.fetchone():
                    break
                username = f"{username_base}{contador}"
                contador += 1
            password = f"{username}123"
            pwd_hash = generate_password_hash(password)
            cursor.execute('SELECT id FROM usuarios WHERE barbero_id = %s', (barbero_id,))
            if cursor.fetchone():
                cursor.execute('UPDATE usuarios SET username = %s, password_hash = %s WHERE barbero_id = %s',
                               (username, pwd_hash, barbero_id))
            else:
                cursor.execute('''
                    INSERT INTO usuarios (username, password_hash, rol, barbero_id)
                    VALUES (%s, %s, 'barbero', %s)
                ''', (username, pwd_hash, barbero_id))
            username_gen = username
            password_gen = password
        
        conn.commit()
        conn.close()
        
        respuesta = {'mensaje': 'Barbero actualizado'}
        if username_gen:
            respuesta['mensaje'] += f'. Usuario: {username_gen} / Contraseña: {password_gen}'
            respuesta['username'] = username_gen
            respuesta['password'] = password_gen
        return jsonify(respuesta)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/barberos/<int:barbero_id>', methods=['DELETE'])
def eliminar_barbero(barbero_id):
    user, error, code = requiere_admin()
    if error: return error, code
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT nombre FROM barberos WHERE id = %s AND activo = 1', (barbero_id,))
        barbero = cursor.fetchone()
        if not barbero:
            conn.close()
            return jsonify({'error': 'Barbero no encontrado o ya desactivado'}), 404
        
        cursor.execute('UPDATE barberos SET activo = 0 WHERE id = %s', (barbero_id,))
        cursor.execute('UPDATE usuarios SET activo = 0 WHERE barbero_id = %s', (barbero_id,))
        
        hoy = ahora_ve().strftime('%Y-%m-%d')
        cursor.execute('''
            UPDATE citas SET estado = 'cancelada_por_barbero'
            WHERE barbero_id = %s AND fecha >= %s
            AND estado IN ('confirmada', 'pendiente_confirmacion')
        ''', (barbero_id, hoy))
        canceladas = cursor.rowcount
        conn.commit()
        conn.close()
        
        enviar_telegram(f"🚫 <b>Barbero desactivado</b>\n{barbero['nombre']}\nCitas canceladas: {canceladas}")
        
        return jsonify({
            'mensaje': f'Barbero "{barbero["nombre"]}" desactivado. {canceladas} citas canceladas.',
            'citas_canceladas': canceladas
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/barberos/<int:barbero_id>/permanente', methods=['DELETE'])
def eliminar_barbero_permanente(barbero_id):
    user, error, code = requiere_admin()
    if error: return error, code
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT nombre FROM barberos WHERE id = %s', (barbero_id,))
        barbero = cursor.fetchone()
        if not barbero:
            conn.close()
            return jsonify({'error': 'Barbero no encontrado'}), 404
        
        hoy = ahora_ve().strftime('%Y-%m-%d')
        cursor.execute('''
            SELECT COUNT(*) as cnt FROM citas 
            WHERE barbero_id = %s AND fecha >= %s 
            AND estado IN ('confirmada', 'pendiente_confirmacion')
        ''', (barbero_id, hoy))
        cnt = cursor.fetchone()['cnt']
        if cnt > 0:
            conn.close()
            return jsonify({'error': f'Tiene {cnt} citas activas. Cancélalas primero.'}), 400
        
        cursor.execute('DELETE FROM usuarios WHERE barbero_id = %s', (barbero_id,))
        cursor.execute('DELETE FROM bloqueos WHERE barbero_id = %s', (barbero_id,))
        cursor.execute('DELETE FROM barberos WHERE id = %s', (barbero_id,))
        conn.commit()
        conn.close()
        
        enviar_telegram(f"🗑️ <b>Barbero eliminado permanentemente</b>\n{barbero['nombre']}")
        return jsonify({'mensaje': f'Barbero "{barbero["nombre"]}" eliminado permanentemente'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ========== CATALOGO (ADMIN) ==========

@app.route('/api/admin/catalogo', methods=['GET'])
def catalogo_admin():
    user, error, code = requiere_admin()
    if error: return error, code
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, tipo, archivo, nombre, descripcion, precio, orden, activo
            FROM catalogo ORDER BY tipo, orden, nombre
        ''')
        items = cursor.fetchall()
        conn.close()
        return jsonify([dict(i) for i in items])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/catalogo', methods=['POST'])
def crear_item_catalogo():
    user, error, code = requiere_admin()
    if error: return error, code
    data = request.json
    tipo = data.get('tipo', '').strip()
    archivo = data.get('archivo', '').strip()
    nombre = data.get('nombre', '').strip()
    if tipo not in ('producto', 'estilo'):
        return jsonify({'error': 'Tipo debe ser producto o estilo'}), 400
    if not archivo or not nombre:
        return jsonify({'error': 'Archivo y nombre obligatorios'}), 400
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO catalogo (tipo, archivo, nombre, descripcion, precio, orden, activo)
            VALUES (%s, %s, %s, %s, %s, %s, 1) RETURNING id
        ''', (tipo, archivo, nombre, data.get('descripcion', '').strip(),
              data.get('precio', '').strip(), int(data.get('orden', 0))))
        nuevo_id = cursor.fetchone()['id']
        conn.commit()
        conn.close()
        return jsonify({'mensaje': 'Item creado', 'id': nuevo_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/catalogo/<int:item_id>', methods=['PUT'])
def actualizar_item_catalogo(item_id):
    user, error, code = requiere_admin()
    if error: return error, code
    data = request.json
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM catalogo WHERE id = %s', (item_id,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({'error': 'Item no encontrado'}), 404
        campos, valores = [], []
        for campo in ['tipo', 'archivo', 'nombre', 'descripcion', 'precio']:
            if campo in data:
                campos.append(f'{campo} = %s')
                valores.append(str(data[campo]).strip())
        if 'orden' in data:
            campos.append('orden = %s'); valores.append(int(data['orden']))
        if 'activo' in data:
            campos.append('activo = %s'); valores.append(1 if data['activo'] else 0)
        if not campos:
            conn.close()
            return jsonify({'error': 'Sin campos'}), 400
        valores.append(item_id)
        cursor.execute(f"UPDATE catalogo SET {', '.join(campos)} WHERE id = %s", valores)
        conn.commit()
        conn.close()
        return jsonify({'mensaje': 'Item actualizado'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/catalogo/<int:item_id>', methods=['DELETE'])
def eliminar_item_catalogo(item_id):
    user, error, code = requiere_admin()
    if error: return error, code
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM catalogo WHERE id = %s', (item_id,))
        if cursor.rowcount == 0:
            conn.close()
            return jsonify({'error': 'Item no encontrado'}), 404
        conn.commit()
        conn.close()
        return jsonify({'mensaje': 'Item eliminado'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ========== PANEL ==========

@app.route('/api/panel/pendientes', methods=['GET'])
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

@app.route('/api/panel/historial', methods=['GET'])
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

@app.route('/api/panel/confirmar-cita', methods=['POST'])
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

@app.route('/api/panel/rechazar-cita', methods=['POST'])
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

@app.route('/api/panel/cancelar-cita-confirmada', methods=['POST'])
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

@app.route('/api/admin/citas/<int:cita_id>', methods=['DELETE'])
def eliminar_cita_permanente(cita_id):
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

@app.route('/api/panel/bloquear', methods=['POST'])
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

@app.route('/api/panel/cancelar-citas-masivo', methods=['POST'])
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

@app.route('/api/mis-citas', methods=['GET'])
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

@app.route('/api/solicitar-modificacion', methods=['POST'])
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
        logging.error(f"Error: {e}")
        return jsonify({'error': str(e)}), 500

# ========== LIMPIEZA (TEMPORAL) ==========

@app.route('/api/admin/reset-db', methods=['GET', 'POST'])
def reset_db():
    """⚠️ TEMPORAL: Limpia toda la BD y recrea datos por defecto."""
    # Token puede venir por query string (?token=...) o por JSON
    token = request.args.get('token', '')
    if not token and request.is_json:
        data = request.json or {}
        token = data.get('token', '')
    if token != 'reset2026':
        return jsonify({'error': 'Token inválido'}), 403
    
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Borrar en orden por FK
        cursor.execute('DELETE FROM logs_notificaciones')
        cursor.execute('DELETE FROM citas')
        cursor.execute('DELETE FROM bloqueos')
        cursor.execute('DELETE FROM usuarios')
        cursor.execute('DELETE FROM clientes')
        cursor.execute('DELETE FROM catalogo')
        cursor.execute('DELETE FROM servicios')
        cursor.execute('DELETE FROM barberos')
        conn.commit()
        conn.close()
        
        # Reiniciar secuencias (PostgreSQL)
        try:
            conn2 = get_db()
            cur2 = conn2.cursor()
            for tabla in ['logs_notificaciones', 'citas', 'bloqueos', 'usuarios',
                          'clientes', 'catalogo', 'servicios', 'barberos']:
                try:
                    cur2.execute(f"ALTER SEQUENCE {tabla}_id_seq RESTART WITH 1")
                except Exception:
                    pass
            conn2.commit()
            conn2.close()
        except Exception as seq_error:
            logging.warning(f"No se pudieron reiniciar secuencias: {seq_error}")
        
        # Recrear datos por defecto
        init_db()
        
        return jsonify({'mensaje': '✅ Base de datos reiniciada correctamente'})
    except Exception as e:
        logging.error(f"Error reset: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/force-reset', methods=['GET'])
def force_reset():
    """⚠️ TEMPORAL: Fuerza reset completo de la BD."""
    token = request.args.get('token', '')
    if token != 'reset2026':
        return jsonify({'error': 'Token inválido'}), 403
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Borrar todo en orden por FK
        for tabla in ['logs_notificaciones', 'citas', 'bloqueos', 'usuarios', 'clientes', 'catalogo', 'servicios', 'barberos']:
            cursor.execute(f'DELETE FROM {tabla}')
        conn.commit()
        
        # Reiniciar secuencias (PostgreSQL)
        try:
            for tabla in ['logs_notificaciones', 'citas', 'bloqueos', 'usuarios', 'clientes', 'catalogo', 'servicios', 'barberos']:
                try:
                    cursor.execute(f"ALTER SEQUENCE {tabla}_id_seq RESTART WITH 1")
                except Exception:
                    pass
            conn.commit()
        except Exception as seq_error:
            logging.warning(f"No se pudieron reiniciar secuencias: {seq_error}")
        
        conn.close()
        
        # Recrear datos por defecto
        init_db()
        
        # Verificar que se insertaron
        conn2 = get_db()
        cur2 = conn2.cursor()
        cur2.execute('SELECT COUNT(*) as cnt FROM catalogo')
        total_catalogo = cur2.fetchone()['cnt']
        cur2.execute('SELECT COUNT(*) as cnt FROM barberos')
        total_barberos = cur2.fetchone()['cnt']
        cur2.execute('SELECT COUNT(*) as cnt FROM usuarios')
        total_usuarios = cur2.fetchone()['cnt']
        cur2.execute('SELECT COUNT(*) as cnt FROM servicios')
        total_servicios = cur2.fetchone()['cnt']
        conn2.close()
        
        return jsonify({
            'mensaje': '✅ Reset forzado completado',
            'catalogo': total_catalogo,
            'barberos': total_barberos,
            'usuarios': total_usuarios,
            'servicios': total_servicios
        })
    except Exception as e:
        logging.error(f"Error force reset: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)