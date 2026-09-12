from flask import Blueprint, request, jsonify
import json
from database import get_db
from helpers import requiere_admin, requiere_autenticacion, ahora_ve
from notificaciones import enviar_telegram

admin_bp = Blueprint('admin', __name__)

# ========== BARBEROS ==========

@admin_bp.route('/api/admin/barberos', methods=['GET'])
def listar_barberos():
    """Lista todos los barberos (activos e inactivos)."""
    user, error, code = requiere_autenticacion()
    if error: return error, code
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, nombre, telefono, email, hora_inicio, hora_fin, 
                   pausa_inicio, pausa_fin, dias_trabajo, activo 
            FROM barberos 
            ORDER BY activo DESC, nombre
        ''')
        barberos = cursor.fetchall()
        conn.close()
        return jsonify([dict(b) for b in barberos])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/api/admin/barberos', methods=['POST'])
def crear_barbero():
    """Crea un nuevo barbero."""
    user, error, code = requiere_admin()
    if error: return error, code
    data = request.json
    if not data.get('nombre'):
        return jsonify({'error': 'El nombre es obligatorio'}), 400
    try:
        from werkzeug.security import generate_password_hash
        from database import normalizar_username
        conn = get_db()
        cursor = conn.cursor()
        dias = data.get('dias_trabajo', ['lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado'])
        hora_inicio = data.get('hora_inicio', '08:00')
        hora_fin = data.get('hora_fin', '17:00')
        pausa_inicio = data.get('pausa_inicio') or None
        pausa_fin = data.get('pausa_fin') or None
        
        cursor.execute('''
            INSERT INTO barberos (nombre, telefono, email, hora_inicio, hora_fin, pausa_inicio, pausa_fin, dias_trabajo)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
        ''', (data['nombre'].strip(), data.get('telefono', '').strip(),
              data.get('email', '').strip(), hora_inicio, hora_fin,
              pausa_inicio, pausa_fin, json.dumps(dias)))
        nuevo_id = cursor.fetchone()['id']
        
        # Generar usuario automático
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
        
        # Crear servicios por defecto para este barbero
        cursor.execute('''
            INSERT INTO servicios (barbero_id, nombre, duracion_minutos, precio) VALUES
            (%s, 'Corte', 45, 25000),
            (%s, 'Barba', 30, 15000),
            (%s, 'Combo (Corte + Barba)', 75, 30000)
        ''', (nuevo_id, nuevo_id, nuevo_id))
        
        conn.commit()
        conn.close()

        enviar_telegram(f"👨‍🦱 <b>Nuevo barbero</b>\n{data['nombre']}\nUsuario: <code>{username}</code>\nContraseña: <code>{password}</code>")

        return jsonify({
            'mensaje': f'Barbero creado. Usuario: {username} / Contraseña: {password}',
            'id': nuevo_id, 'username': username, 'password': password
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/api/admin/barberos/<int:barbero_id>', methods=['PUT'])
def actualizar_barbero(barbero_id):
    """Actualiza un barbero existente."""
    user, error, code = requiere_admin()
    if error: return error, code
    data = request.json
    try:
        from werkzeug.security import generate_password_hash
        from database import normalizar_username
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
        if 'hora_inicio' in data:
            campos.append('hora_inicio = %s'); valores.append(data['hora_inicio'])
        if 'hora_fin' in data:
            campos.append('hora_fin = %s'); valores.append(data['hora_fin'])
        if 'pausa_inicio' in data:
            campos.append('pausa_inicio = %s')
            valores.append(data['pausa_inicio'] if data['pausa_inicio'] else None)
        if 'pausa_fin' in data:
            campos.append('pausa_fin = %s')
            valores.append(data['pausa_fin'] if data['pausa_fin'] else None)
        if 'dias_trabajo' in data:
            campos.append('dias_trabajo = %s'); valores.append(json.dumps(data['dias_trabajo']))
        if 'activo' in data:
            campos.append('activo = %s'); valores.append(1 if data['activo'] else 0)
        
        if campos:
            valores.append(barbero_id)
            cursor.execute(f"UPDATE barberos SET {', '.join(campos)} WHERE id = %s", valores)
        
        # Regenerar usuario si cambió el nombre
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

@admin_bp.route('/api/admin/barberos/<int:barbero_id>', methods=['DELETE'])
def eliminar_barbero(barbero_id):
    """Desactiva un barbero (soft delete). Cancela sus citas futuras."""
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

@admin_bp.route('/api/admin/barberos/<int:barbero_id>/reactivar', methods=['PUT'])
def reactivar_barbero(barbero_id):
    """Reactiva un barbero desactivado."""
    user, error, code = requiere_admin()
    if error: return error, code
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT nombre, activo FROM barberos WHERE id = %s', (barbero_id,))
        barbero = cursor.fetchone()
        if not barbero:
            conn.close()
            return jsonify({'error': 'Barbero no encontrado'}), 404
        if barbero['activo'] == 1:
            conn.close()
            return jsonify({'error': 'El barbero ya está activo'}), 400
        
        # Reactivar barbero y su usuario
        cursor.execute('UPDATE barberos SET activo = 1 WHERE id = %s', (barbero_id,))
        cursor.execute('UPDATE usuarios SET activo = 1 WHERE barbero_id = %s', (barbero_id,))
        conn.commit()
        conn.close()
        
        enviar_telegram(f"✅ <b>Barbero reactivado</b>\n{barbero['nombre']}")
        
        return jsonify({
            'mensaje': f'Barbero "{barbero["nombre"]}" reactivado exitosamente'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/api/admin/barberos/<int:barbero_id>/permanente', methods=['DELETE'])
def eliminar_barbero_permanente(barbero_id):
    """Elimina un barbero permanentemente (solo si no tiene citas futuras)."""
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
        
        cursor.execute('DELETE FROM servicios WHERE barbero_id = %s', (barbero_id,))
        cursor.execute('DELETE FROM usuarios WHERE barbero_id = %s', (barbero_id,))
        cursor.execute('DELETE FROM bloqueos WHERE barbero_id = %s', (barbero_id,))
        cursor.execute('DELETE FROM barberos WHERE id = %s', (barbero_id,))
        conn.commit()
        conn.close()
        
        enviar_telegram(f"🗑️ <b>Barbero eliminado permanentemente</b>\n{barbero['nombre']}")
        return jsonify({'mensaje': f'Barbero "{barbero["nombre"]}" eliminado permanentemente'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ========== SERVICIOS (por barbero) ==========

@admin_bp.route('/api/admin/servicios', methods=['GET'])
def servicios_admin():
    """Lista servicios de un barbero específico o de todos."""
    user, error, code = requiere_autenticacion()
    if error: return error, code
    barbero_id = request.args.get('barbero_id', 0, type=int)
    
    # Si es barbero, solo puede ver los suyos
    if user['rol'] == 'barbero' and user['barbero_id']:
        barbero_id = user['barbero_id']
    try:
        conn = get_db()
        cursor = conn.cursor()
        if barbero_id > 0:
            cursor.execute('''
                SELECT id, barbero_id, nombre, duracion_minutos, precio, descripcion, activo 
                FROM servicios WHERE barbero_id = %s ORDER BY id
            ''', (barbero_id,))
        else:
            cursor.execute('''
                SELECT id, barbero_id, nombre, duracion_minutos, precio, descripcion, activo 
                FROM servicios ORDER BY barbero_id, id
            ''')
        servicios = cursor.fetchall()
        conn.close()
        return jsonify([dict(s) for s in servicios])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/api/admin/servicios', methods=['POST'])
def crear_servicio():
    """Crea un servicio para un barbero."""
    user, error, code = requiere_autenticacion()
    if error: return error, code
    data = request.json
    nombre = data.get('nombre', '').strip()
    duracion = int(data.get('duracion_minutos', 0))
    precio = float(data.get('precio', 0))
    barbero_id = int(data.get('barbero_id', 0))
    
    if user['rol'] == 'barbero' and user['barbero_id']:
        barbero_id = user['barbero_id']
    if barbero_id == 0:
        return jsonify({'error': 'Debe especificar un barbero'}), 400
    
    if not nombre:
        return jsonify({'error': 'El nombre es obligatorio'}), 400
    if duracion <= 0:
        return jsonify({'error': 'La duración debe ser mayor a 0'}), 400
    if precio < 0:
        return jsonify({'error': 'El precio no puede ser negativo'}), 400
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO servicios (barbero_id, nombre, duracion_minutos, precio, descripcion, activo)
            VALUES (%s, %s, %s, %s, %s, 1) RETURNING id
        ''', (barbero_id, nombre, duracion, precio, data.get('descripcion', '').strip()))
        nuevo_id = cursor.fetchone()['id']
        conn.commit()
        conn.close()
        return jsonify({'mensaje': 'Servicio creado', 'id': nuevo_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/api/admin/servicios/<int:servicio_id>', methods=['PUT'])
def actualizar_servicio(servicio_id):
    """Actualiza un servicio existente."""
    user, error, code = requiere_autenticacion()
    if error: return error, code
    data = request.json
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT barbero_id FROM servicios WHERE id = %s', (servicio_id,))
        srv = cursor.fetchone()
        if not srv:
            conn.close()
            return jsonify({'error': 'Servicio no encontrado'}), 404
        
        if user['rol'] == 'barbero' and srv['barbero_id'] != user['barbero_id']:
            conn.close()
            return jsonify({'error': 'No autorizado para editar este servicio'}), 403
        
        campos, valores = [], []
        if 'nombre' in data:
            campos.append('nombre = %s'); valores.append(str(data['nombre']).strip())
        if 'duracion_minutos' in data:
            dur = int(data['duracion_minutos'])
            if dur <= 0:
                conn.close()
                return jsonify({'error': 'Duración inválida'}), 400
            campos.append('duracion_minutos = %s'); valores.append(dur)
        if 'precio' in data:
            precio = float(data['precio'])
            if precio < 0:
                conn.close()
                return jsonify({'error': 'Precio inválido'}), 400
            campos.append('precio = %s'); valores.append(precio)
        if 'descripcion' in data:
            campos.append('descripcion = %s'); valores.append(str(data['descripcion']).strip())
        if 'activo' in data:
            campos.append('activo = %s'); valores.append(1 if data['activo'] else 0)
        
        if not campos:
            conn.close()
            return jsonify({'error': 'Sin campos para actualizar'}), 400
        
        valores.append(servicio_id)
        cursor.execute(f"UPDATE servicios SET {', '.join(campos)} WHERE id = %s", valores)
        conn.commit()
        conn.close()
        return jsonify({'mensaje': 'Servicio actualizado'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/api/admin/servicios/<int:servicio_id>', methods=['DELETE'])
def eliminar_servicio(servicio_id):
    """Elimina o desactiva un servicio."""
    user, error, code = requiere_autenticacion()
    if error: return error, code
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT barbero_id FROM servicios WHERE id = %s', (servicio_id,))
        srv = cursor.fetchone()
        if not srv:
            conn.close()
            return jsonify({'error': 'Servicio no encontrado'}), 404
        if user['rol'] == 'barbero' and srv['barbero_id'] != user['barbero_id']:
            conn.close()
            return jsonify({'error': 'No autorizado'}), 403
        
        cursor.execute('SELECT COUNT(*) as cnt FROM citas WHERE servicio_id = %s', (servicio_id,))
        cnt = cursor.fetchone()['cnt']
        if cnt > 0:
            cursor.execute('UPDATE servicios SET activo = 0 WHERE id = %s', (servicio_id,))
            conn.commit()
            conn.close()
            return jsonify({'mensaje': f'Servicio desactivado (tenía {cnt} citas)'})
        else:
            cursor.execute('DELETE FROM servicios WHERE id = %s', (servicio_id,))
            conn.commit()
            conn.close()
            return jsonify({'mensaje': 'Servicio eliminado'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ========== CATALOGO ==========

@admin_bp.route('/api/admin/catalogo', methods=['GET'])
def catalogo_admin():
    """Lista todos los items del catálogo."""
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

@admin_bp.route('/api/admin/catalogo', methods=['POST'])
def crear_item_catalogo():
    """Crea un nuevo item en el catálogo."""
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

@admin_bp.route('/api/admin/catalogo/<int:item_id>', methods=['PUT'])
def actualizar_item_catalogo(item_id):
    """Actualiza un item del catálogo."""
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
                campos.append(f'{campo} = %s'); valores.append(str(data[campo]).strip())
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

@admin_bp.route('/api/admin/catalogo/<int:item_id>', methods=['DELETE'])
def eliminar_item_catalogo(item_id):
    """Elimina un item del catálogo."""
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

# ========== MIGRACIÓN FORZADA (TEMPORAL) ==========

@admin_bp.route('/api/admin/forzar-migracion', methods=['GET'])
def forzar_migracion():
    """⚠️ TEMPORAL: Fuerza la migración de columnas."""
    token = request.args.get('token', '')
    if token != 'migrar2026':
        return jsonify({'error': 'Token inválido'}), 403
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Detectar si estamos en PostgreSQL
        from database import USING_POSTGRES
        is_postgres = USING_POSTGRES
        
        def col_existe(tabla, columna):
            if is_postgres:
                cursor.execute("""
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = %s AND column_name = %s
                """, (tabla, columna))
                return cursor.fetchone() is not None
            else:
                cursor.execute(f"PRAGMA table_info({tabla})")
                cols = [row[1] for row in cursor.fetchall()]
                return columna in cols
        
        resultados = []
        
        # Migrar barberos
        for col, defn in [
            ('hora_inicio', "TEXT DEFAULT '08:00'"),
            ('hora_fin', "TEXT DEFAULT '17:00'"),
            ('pausa_inicio', "TEXT"),
            ('pausa_fin', "TEXT"),
        ]:
            if not col_existe('barberos', col):
                cursor.execute(f"ALTER TABLE barberos ADD COLUMN {col} {defn}")
                resultados.append(f"✅ barberos.{col} agregada")
            else:
                resultados.append(f"⏭️ barberos.{col} ya existe")
        
        # Migrar servicios
        if not col_existe('servicios', 'barbero_id'):
            cursor.execute("ALTER TABLE servicios ADD COLUMN barbero_id INTEGER")
            cursor.execute("SELECT id FROM barberos WHERE activo = 1 LIMIT 1")
            b = cursor.fetchone()
            if b:
                bid = b['id'] if isinstance(b, dict) else b[0]
                cursor.execute("UPDATE servicios SET barbero_id = %s WHERE barbero_id IS NULL", (bid,))
            resultados.append("✅ servicios.barbero_id agregada")
        else:
            resultados.append("⏭️ servicios.barbero_id ya existe")
        
        conn.commit()
        
        # Actualizar valores por defecto en barberos existentes
        cursor.execute("UPDATE barberos SET hora_inicio = '08:00' WHERE hora_inicio IS NULL")
        cursor.execute("UPDATE barberos SET hora_fin = '17:00' WHERE hora_fin IS NULL")
        conn.commit()
        
        conn.close()
        
        return jsonify({
            'mensaje': '✅ Migración completada',
            'resultados': resultados
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500