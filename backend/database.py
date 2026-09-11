import os
import json
import unicodedata
import psycopg2
import psycopg2.extras
import sqlite3
from werkzeug.security import generate_password_hash

DATABASE_URL = os.getenv('DATABASE_URL')
USING_POSTGRES = DATABASE_URL is not None and DATABASE_URL.startswith('postgres')

def get_db():
    if USING_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL)
        conn.cursor_factory = psycopg2.extras.RealDictCursor
        return conn
    else:
        db_path = os.path.join(os.path.dirname(__file__), 'barberia.db')
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

def normalizar_username(nombre):
    if not nombre:
        return 'barbero'
    nfkd = unicodedata.normalize('NFKD', nombre)
    solo_ascii = nfkd.encode('ASCII', 'ignore').decode('ASCII')
    username = ''.join(c for c in solo_ascii.lower() if c.isalnum())
    return username or 'barbero'

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    is_postgres = USING_POSTGRES
    id_def = "SERIAL PRIMARY KEY" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"

    # ===== TABLA BARBEROS =====
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS barberos (
            id {id_def},
            nombre TEXT NOT NULL,
            telefono TEXT,
            email TEXT,
            hora_inicio TEXT DEFAULT '08:00',
            hora_fin TEXT DEFAULT '17:00',
            dias_trabajo TEXT DEFAULT '["lunes","martes","miercoles","jueves","viernes","sabado"]',
            activo INTEGER DEFAULT 1
        )
    ''')

    # ===== TABLA SERVICIOS =====
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS servicios (
            id {id_def},
            nombre TEXT NOT NULL,
            duracion_minutos INTEGER NOT NULL,
            precio REAL NOT NULL,
            descripcion TEXT,
            activo INTEGER DEFAULT 1
        )
    ''')

    # ===== TABLA BARBERO_SERVICIOS (NUEVA) =====
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS barbero_servicios (
            id {id_def},
            barbero_id INTEGER NOT NULL,
            servicio_id INTEGER NOT NULL,
            activo INTEGER DEFAULT 1,
            UNIQUE (barbero_id, servicio_id),
            FOREIGN KEY (barbero_id) REFERENCES barberos(id),
            FOREIGN KEY (servicio_id) REFERENCES servicios(id)
        )
    ''')

    # ===== TABLA CLIENTES =====
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS clientes (
            id {id_def},
            nombre TEXT NOT NULL,
            telefono TEXT,
            email TEXT,
            notas_habituales TEXT
        )
    ''')

    # ===== TABLA CITAS =====
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS citas (
            id {id_def},
            barbero_id INTEGER NOT NULL,
            cliente_id INTEGER NOT NULL,
            servicio_id INTEGER NOT NULL,
            fecha TEXT NOT NULL,
            hora_inicio TEXT NOT NULL,
            hora_fin TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'confirmada',
            tipo_reserva TEXT NOT NULL DEFAULT 'normal',
            alerta_cierre INTEGER DEFAULT 0,
            cita_original_id INTEGER,
            notas_cliente TEXT,
            fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (barbero_id) REFERENCES barberos(id),
            FOREIGN KEY (cliente_id) REFERENCES clientes(id),
            FOREIGN KEY (servicio_id) REFERENCES servicios(id)
        )
    ''')

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_citas_fecha ON citas(fecha)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_citas_estado ON citas(estado)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_citas_barbero ON citas(barbero_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_citas_cliente ON citas(cliente_id)')

    # ===== TABLA BLOQUEOS =====
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS bloqueos (
            id {id_def},
            barbero_id INTEGER NOT NULL,
            fecha_inicio TEXT NOT NULL,
            fecha_fin TEXT NOT NULL,
            motivo TEXT,
            activo INTEGER DEFAULT 1,
            FOREIGN KEY (barbero_id) REFERENCES barberos(id)
        )
    ''')

    # ===== TABLA LOGS =====
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS logs_notificaciones (
            id {id_def},
            cita_id INTEGER NOT NULL,
            tipo TEXT NOT NULL,
            estado_envio TEXT NOT NULL,
            fecha_envio TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            intentos INTEGER DEFAULT 0,
            FOREIGN KEY (cita_id) REFERENCES citas(id)
        )
    ''')

    # ===== TABLA USUARIOS =====
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS usuarios (
            id {id_def},
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            rol TEXT NOT NULL DEFAULT 'barbero',
            barbero_id INTEGER,
            activo INTEGER DEFAULT 1,
            FOREIGN KEY (barbero_id) REFERENCES barberos(id)
        )
    ''')

    # ===== TABLA CATALOGO =====
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS catalogo (
            id {id_def},
            tipo TEXT NOT NULL,
            archivo TEXT NOT NULL,
            nombre TEXT NOT NULL,
            descripcion TEXT,
            precio TEXT,
            orden INTEGER DEFAULT 0,
            activo INTEGER DEFAULT 1,
            fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # ===== DATOS DE PRUEBA =====
    if is_postgres:
        cursor.execute("SELECT 1 FROM barberos LIMIT 1")
        existe = cursor.fetchone()
    else:
        cursor.execute("SELECT COUNT(*) as cnt FROM barberos")
        existe = cursor.fetchone()['cnt'] > 0

    if not existe:
        if is_postgres:
            cursor.execute('''
                INSERT INTO barberos (nombre, telefono, email) 
                VALUES ('Barbero Principal', '123456789', 'barbero@barberia.com')
                RETURNING id
            ''')
            barbero_id = cursor.fetchone()['id']
        else:
            cursor.execute('''
                INSERT INTO barberos (nombre, telefono, email) 
                VALUES ('Barbero Principal', '123456789', 'barbero@barberia.com')
            ''')
            barbero_id = cursor.lastrowid
        
        cursor.execute('''
            INSERT INTO servicios (nombre, duracion_minutos, precio) VALUES
            ('Corte', 45, 25000),
            ('Barba', 30, 15000),
            ('Combo (Corte + Barba)', 75, 30000)
        ''')
        print("✅ Datos de prueba insertados")

    # ===== ADMIN USER =====
    cursor.execute("SELECT 1 FROM usuarios WHERE username = 'admin'")
    if not cursor.fetchone():
        admin_hash = generate_password_hash('barberia2026')
        if is_postgres:
            cursor.execute('''
                INSERT INTO usuarios (username, password_hash, rol, barbero_id)
                VALUES ('admin', %s, 'admin', NULL)
            ''', (admin_hash,))
        else:
            cursor.execute('''
                INSERT INTO usuarios (username, password_hash, rol, barbero_id)
                VALUES ('admin', ?, 'admin', NULL)
            ''', (admin_hash,))
        print("✅ Admin: admin / barberia2026")

    # ===== USUARIOS PARA BARBEROS =====
    cursor.execute('SELECT id, nombre FROM barberos WHERE activo = 1')
    barberos = cursor.fetchall()
    
    for b in barberos:
        barbero_id = b['id']
        nombre = b['nombre']
        
        cursor.execute('SELECT 1 FROM usuarios WHERE barbero_id = %s', (barbero_id,))
        if cursor.fetchone():
            continue
        
        username = normalizar_username(nombre)
        base_username = username
        contador = 2
        while True:
            cursor.execute('SELECT 1 FROM usuarios WHERE username = %s', (username,))
            if not cursor.fetchone():
                break
            username = f"{base_username}{contador}"
            contador += 1
        
        password = f"{username}123"
        pwd_hash = generate_password_hash(password)
        cursor.execute('''
            INSERT INTO usuarios (username, password_hash, rol, barbero_id)
            VALUES (%s, %s, 'barbero', %s)
        ''', (username, pwd_hash, barbero_id))
        print(f"✅ Usuario: {username} / {password}")

    # ===== CATALOGO POR DEFECTO =====
    cursor.execute('SELECT COUNT(*) as cnt FROM catalogo')
    if cursor.fetchone()['cnt'] == 0:
        items = [
            ('producto', 'producto1.jpg', 'Producto 1', 'Descripcion del producto 1', '$20.000 COP', 1),
            ('producto', 'producto2.jpg', 'Producto 2', 'Descripcion del producto 2', '$20.000 COP', 2),
            ('producto', 'producto3.jpg', 'Producto 3', 'Descripcion del producto 3', '$20.000 COP', 3),
            ('producto', 'producto4.jpg', 'Producto 4', 'Descripcion del producto 4', '$20.000 COP', 4),
            ('producto', 'producto5.jpg', 'Producto 5', 'Descripcion del producto 5', '$20.000 COP', 5),
            ('producto', 'producto6.jpg', 'Producto 6', 'Descripcion del producto 6', '$20.000 COP', 6),
            ('producto', 'producto7.jpg', 'Producto 7', 'Descripcion del producto 7', '$20.000 COP', 7),
            ('producto', 'producto8.jpg', 'Producto 8', 'Descripcion del producto 8', '$20.000 COP', 8),
            ('producto', 'producto9.jpg', 'Producto 9', 'Descripcion del producto 9', '$20.000 COP', 9),
            ('producto', 'producto10.jpg', 'Producto 10', 'Descripcion del producto 10', '$20.000 COP', 10),
            ('producto', 'producto11.jpg', 'Producto 11', 'Descripcion del producto 11', '$20.000 COP', 11),
            ('producto', 'producto12.jpg', 'Producto 12', 'Descripcion del producto 12', '$20.000 COP', 12),
            ('producto', 'producto13.jpg', 'Producto 13', 'Descripcion del producto 13', '$20.000 COP', 13),
            ('producto', 'producto14.jpg', 'Producto 14', 'Descripcion del producto 14', '$20.000 COP', 14),
            ('producto', 'producto15.jpg', 'Producto 15', 'Descripcion del producto 15', '$20.000 COP', 15),
            ('producto', 'producto16.jpg', 'Producto 16', 'Descripcion del producto 16', '$20.000 COP', 16),
            ('producto', 'producto17.jpg', 'Producto 17', 'Descripcion del producto 17', '$20.000 COP', 17),
            ('producto', 'producto18.jpg', 'Producto 18', 'Descripcion del producto 18', '$20.000 COP', 18),
            ('producto', 'producto19.jpg', 'Producto 19', 'Descripcion del producto 19', '$20.000 COP', 19),
            ('producto', 'producto20.jpg', 'Producto 20', 'Descripcion del producto 20', '$20.000 COP', 20),
            ('estilo', 'corte1.jpg', 'Corte 1', '', '', 1),
            ('estilo', 'corte2.jpg', 'Corte 2', '', '', 2),
            ('estilo', 'corte3.jpg', 'Corte 3', '', '', 3),
            ('estilo', 'corte4.jpg', 'Corte 4', '', '', 4),
            ('estilo', 'corte5.jpg', 'Corte 5', '', '', 5),
            ('estilo', 'corte6.jpg', 'Corte 6', '', '', 6),
        ]
        for tipo, archivo, nombre, descripcion, precio, orden in items:
            cursor.execute('''
                INSERT INTO catalogo (tipo, archivo, nombre, descripcion, precio, orden, activo)
                VALUES (%s, %s, %s, %s, %s, %s, 1)
            ''', (tipo, archivo, nombre, descripcion, precio, orden))
        print(f"✅ Catalogo por defecto creado ({len(items)} items)")

    # ===== VINCULAR SERVICIOS A BARBEROS (por defecto) =====
    cursor.execute('SELECT COUNT(*) as cnt FROM barbero_servicios')
    if cursor.fetchone()['cnt'] == 0:
        cursor.execute('SELECT id FROM barberos WHERE activo = 1')
        barberos_ids = [r['id'] for r in cursor.fetchall()]
        cursor.execute('SELECT id FROM servicios WHERE activo = 1')
        servicios_ids = [r['id'] for r in cursor.fetchall()]
        for barbero_id in barberos_ids:
            for servicio_id in servicios_ids:
                cursor.execute('''
                    INSERT INTO barbero_servicios (barbero_id, servicio_id, activo)
                    VALUES (%s, %s, 1)
                ''', (barbero_id, servicio_id))
        print(f"✅ Servicios vinculados a {len(barberos_ids)} barberos")

    conn.commit()
    conn.close()