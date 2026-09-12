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
    """Elimina un barbero permanentemente (solo si no tiene citas futuras).
       Si tiene citas históricas, solo se desactiva."""
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
        
        # Verificar citas futuras activas
        hoy = ahora_ve().strftime('%Y-%m-%d')
        cursor.execute('''
            SELECT COUNT(*) as cnt FROM citas 
            WHERE barbero_id = %s AND fecha >= %s 
            AND estado IN ('confirmada', 'pendiente_confirmacion')
        ''', (barbero_id, hoy))
        citas_futuras = cursor.fetchone()['cnt']
        if citas_futuras > 0:
            conn.close()
            return jsonify({
                'error': f'Tiene {citas_futuras} citas activas. Cancélalas primero.'
            }), 400
        
        # Verificar si tiene citas históricas
        cursor.execute('SELECT COUNT(*) as cnt FROM citas WHERE barbero_id = %s', (barbero_id,))
        citas_historicas = cursor.fetchone()['cnt']
        
        if citas_historicas > 0:
            # Tiene historial: solo desactivar (no borrar)
            cursor.execute('UPDATE barberos SET activo = 0 WHERE id = %s', (barbero_id,))
            cursor.execute('UPDATE usuarios SET activo = 0 WHERE barbero_id = %s', (barbero_id,))
            # Desactivar sus servicios (no borrar)
            cursor.execute('UPDATE servicios SET activo = 0 WHERE barbero_id = %s', (barbero_id,))
            conn.commit()
            conn.close()
            enviar_telegram(f"🚫 <b>Barbero desactivado (tenía historial)</b>\n{barbero['nombre']}")
            return jsonify({
                'mensaje': f'Barbero "{barbero["nombre"]}" desactivado. No se puede eliminar permanentemente porque tiene {citas_historicas} citas en el historial.',
                'accion': 'desactivado'
            })
        else:
            # Sin historial: borrar todo
            # Borrar de barbero_servicios (tabla vieja)
            try:
                cursor.execute('DELETE FROM barbero_servicios WHERE barbero_id = %s', (barbero_id,))
            except Exception:
                pass
            
            # Borrar servicios del barbero
            try:
                cursor.execute('DELETE FROM servicios WHERE barbero_id = %s', (barbero_id,))
            except Exception:
                pass
            
            # Borrar de otras tablas relacionadas
            try:
                cursor.execute('DELETE FROM usuarios WHERE barbero_id = %s', (barbero_id,))
            except Exception:
                pass
            
            try:
                cursor.execute('DELETE FROM bloqueos WHERE barbero_id = %s', (barbero_id,))
            except Exception:
                pass
            
            try:
                cursor.execute('DELETE FROM barberos WHERE id = %s', (barbero_id,))
            except Exception:
                pass

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

# ========== BACKUP ==========
@admin_bp.route('/api/admin/backup', methods=['GET'])
def backup_db():
    """Genera un backup completo de la base de datos en JSON."""
    import os
    token = request.args.get('token', '')
    TOKEN_BACKUP = os.environ.get('BACKUP_TOKEN', 'backup2026')
    # Token especial para cron jobs, o sesión de admin
    user, _, _ = requiere_autenticacion()
    if token != TOKEN_BACKUP and not (user and user['rol'] == 'admin'):
        return jsonify({'error': 'No autorizado'}), 403
    try:
        from datetime import datetime
        conn = get_db()
        cursor = conn.cursor()
        
        backup = {
            'fecha_backup': ahora_ve().isoformat(),
            'version': '1.0',
            'datos': {}
        }
        
        tablas = ['barberos', 'servicios', 'clientes', 'citas', 'bloqueos', 
                  'usuarios', 'catalogo', 'logs_notificaciones']
        
        for tabla in tablas:
            try:
                cursor.execute(f'SELECT * FROM {tabla}')
                rows = cursor.fetchall()
                backup['datos'][tabla] = [dict(r) for r in rows]
            except Exception as e:
                backup['datos'][tabla] = []
                backup['datos'][f'{tabla}_error'] = str(e)
        
        conn.close()
        
        from flask import Response
        import json as json_lib
        
        json_str = json_lib.dumps(backup, indent=2, default=str, ensure_ascii=False)
        fecha = ahora_ve().strftime('%Y-%m-%d_%H-%M-%S')
        
        if request.args.get('descargar') == 'si':
            return Response(
                json_str,
                mimetype='application/json',
                headers={
                    'Content-Disposition': f'attachment; filename=backup_barberia_{fecha}.json'
                }
            )
        
        return jsonify({
            'mensaje': '✅ Backup generado',
            'fecha': fecha,
            'tablas': {k: len(v) if isinstance(v, list) else 0 for k, v in backup['datos'].items() if not k.endswith('_error')}
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/api/admin/backup-telegram', methods=['GET'])
def backup_telegram():
    """Genera backup y lo envía por Telegram."""
    import os
    token = request.args.get('token', '')
    TOKEN_BACKUP = os.environ.get('BACKUP_TOKEN', 'backup2026')
    if token != TOKEN_BACKUP:
        return jsonify({'error': 'Token inválido'}), 403
    try:
        from datetime import datetime
        from notificaciones import enviar_telegram_documento
        import json as json_lib
        
        conn = get_db()
        cursor = conn.cursor()
        
        backup = {
            'fecha_backup': ahora_ve().isoformat(),
            'version': '1.0',
            'datos': {}
        }
        
        tablas = ['barberos', 'servicios', 'clientes', 'citas', 'bloqueos', 
                  'usuarios', 'catalogo', 'logs_notificaciones']
        
        totales = {}
        for tabla in tablas:
            try:
                cursor.execute(f'SELECT * FROM {tabla}')
                rows = cursor.fetchall()
                backup['datos'][tabla] = [dict(r) for r in rows]
                totales[tabla] = len(rows)
            except Exception as e:
                backup['datos'][tabla] = []
                totales[tabla] = f"error: {e}"
        
        conn.close()
        
        json_str = json_lib.dumps(backup, indent=2, default=str, ensure_ascii=False)
        fecha = ahora_ve().strftime('%Y-%m-%d_%H-%M')
        nombre_archivo = f'backup_barberia_{fecha}.json'
        
        caption = (
            f"📦 <b>Backup Gocho Barber</b>\n"
            f"📅 {ahora_ve().strftime('%d/%m/%Y %H:%M')}\n\n"
            + "\n".join([f"• {k}: {v}" for k, v in totales.items()])
        )
        enviado = enviar_telegram_documento(nombre_archivo, json_str, caption)
        
        return jsonify({
            'mensaje': '✅ Backup enviado por Telegram' if enviado else '❌ Error enviando',
            'enviado': enviado,
            'archivo': nombre_archivo,
            'totales': totales
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
# ========== ESTADÍSTICAS ==========
@admin_bp.route('/api/admin/estadisticas', methods=['GET'])
def estadisticas():
    """Devuelve estadísticas para el dashboard."""
    user, error, code = requiere_admin()
    if error: return error, code
    try:
        from datetime import datetime, timedelta
        from config import DIAS_ES
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Fecha actual en Venezuela
        hoy = ahora_ve()
        
        # ========== 1. CITAS E INGRESOS POR MES (últimos 6 meses) ==========
        citas_mes = []
        ingresos_mes = []
        etiquetas_mes = []
        
        meses_es = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 
                    'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
        
        for i in range(5, -1, -1):
            # Calcular el mes
            mes_actual = hoy.month - i
            anio_actual = hoy.year
            while mes_actual <= 0:
                mes_actual += 12
                anio_actual -= 1
            
            primer_dia = f"{anio_actual}-{mes_actual:02d}-01"
            if mes_actual == 12:
                ultimo_dia = f"{anio_actual}-12-31"
            else:
                ultimo_dia = f"{anio_actual}-{mes_actual+1:02d}-01"
            
            # Contar citas del mes (cualquier estado excepto canceladas)
            cursor.execute('''
                SELECT COUNT(*) as cnt 
                FROM citas 
                WHERE fecha >= %s AND fecha < %s
                AND estado != 'cancelada_por_cliente' 
                AND estado != 'cancelada_por_barbero'
                AND estado != 'cancelada_por_sistema'
                AND estado != 'expirada'
            ''', (primer_dia, ultimo_dia))
            cantidad = cursor.fetchone()['cnt']
            citas_mes.append(cantidad)
            
            # Sumar ingresos estimados (precio de servicios de esas citas)
            cursor.execute('''
                SELECT COALESCE(SUM(s.precio), 0) as total
                FROM citas c
                JOIN servicios s ON c.servicio_id = s.id
                WHERE c.fecha >= %s AND c.fecha < %s
                AND c.estado NOT IN ('cancelada_por_cliente', 'cancelada_por_barbero', 
                                     'cancelada_por_sistema', 'expirada')
            ''', (primer_dia, ultimo_dia))
            ingresos = float(cursor.fetchone()['total'])
            ingresos_mes.append(ingresos)
            
            etiquetas_mes.append(f"{meses_es[mes_actual-1]} {anio_actual}")
        
        # ========== 2. CITAS POR BARBERO (todos los tiempos) ==========
        cursor.execute('''
            SELECT b.nombre, COUNT(c.id) as total
            FROM barberos b
            LEFT JOIN citas c ON c.barbero_id = b.id
            WHERE b.activo = 1
            GROUP BY b.id, b.nombre
            ORDER BY total DESC
        ''')
        barberos_data = cursor.fetchall()
        barberos_nombres = [b['nombre'] for b in barberos_data]
        barberos_cantidades = [b['total'] for b in barberos_data]
        
        # ========== 3. TOP 5 CLIENTES FRECUENTES ==========
        cursor.execute('''
            SELECT cl.nombre, cl.telefono, COUNT(c.id) as total_citas
            FROM clientes cl
            JOIN citas c ON c.cliente_id = cl.id
            WHERE c.estado NOT IN ('cancelada_por_cliente', 'cancelada_por_barbero', 
                                   'cancelada_por_sistema', 'expirada')
            GROUP BY cl.id, cl.nombre, cl.telefono
            ORDER BY total_citas DESC
            LIMIT 5
        ''')
        clientes_top = [dict(c) for c in cursor.fetchall()]
        
        # ========== 4. RESUMEN GENERAL ==========
        # Total citas del mes actual
        primer_dia_mes = f"{hoy.year}-{hoy.month:02d}-01"
        cursor.execute('''
            SELECT COUNT(*) as cnt FROM citas 
            WHERE fecha >= %s
            AND estado NOT IN ('cancelada_por_cliente', 'cancelada_por_barbero', 
                               'cancelada_por_sistema', 'expirada')
        ''', (primer_dia_mes,))
        citas_mes_actual = cursor.fetchone()['cnt']
        
        # Total citas históricas
        cursor.execute('''
            SELECT COUNT(*) as cnt FROM citas 
            WHERE estado NOT IN ('cancelada_por_cliente', 'cancelada_por_barbero', 
                                 'cancelada_por_sistema', 'expirada')
        ''')
        citas_totales = cursor.fetchone()['cnt']
        
        # Total clientes
        cursor.execute('SELECT COUNT(*) as cnt FROM clientes')
        total_clientes = cursor.fetchone()['cnt']
        
        # Total ingresos históricos
        cursor.execute('''
            SELECT COALESCE(SUM(s.precio), 0) as total
            FROM citas c
            JOIN servicios s ON c.servicio_id = s.id
            WHERE c.estado NOT IN ('cancelada_por_cliente', 'cancelada_por_barbero', 
                                   'cancelada_por_sistema', 'expirada')
        ''')
        ingresos_totales = float(cursor.fetchone()['total'])
        
        conn.close()
        
        return jsonify({
            'citas_mes': {
                'etiquetas': etiquetas_mes,
                'valores': citas_mes
            },
            'ingresos_mes': {
                'etiquetas': etiquetas_mes,
                'valores': ingresos_mes
            },
            'barberos': {
                'nombres': barberos_nombres,
                'cantidades': barberos_cantidades
            },
            'clientes_top': clientes_top,
            'resumen': {
                'citas_mes_actual': citas_mes_actual,
                'citas_totales': citas_totales,
                'total_clientes': total_clientes,
                'ingresos_totales': ingresos_totales
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500