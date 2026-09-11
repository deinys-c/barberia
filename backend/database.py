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

    # ===== BARBEROS (con horario propio) =====
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

    # ===== SERVICIOS (por barbero) =====
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS servicios (
            id {id_def},
            barbero_id INTEGER NOT NULL,
            nombre TEXT NOT NULL,
            duracion_minutos INTEGER NOT NULL,
            precio REAL NOT NULL,
            descripcion TEXT,
            activo INTEGER DEFAULT 1,
            FOREIGN KEY (barbero_id) REFERENCES barberos(id)
        )
    ''')

    # ===== CLIENTES =====
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS clientes (
            id {id_def},
            nombre TEXT NOT NULL,
            telefono TEXT,
            email TEXT,
            notas_habituales TEXT
        )
    ''')

    # ===== CITAS =====
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

    # ===== BLOQUEOS =====
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

    # ===== LOGS =====
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

    # ===== USUARIOS =====
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

    # ===== CATALOGO =====
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
                INSERT INTO barberos (nombre, telefono, email, hora_inicio, hora_fin) 
                VALUES ('Barbero Principal', '123456789', 'barbero@barberia.com', '08:00', '17:00')
                RETURNING id
            ''')
            barbero_id = cursor.fetchone()['id']
        else:
            cursor.execute('''
                INSERT INTO barberos (nombre, telefono, email, hora_inicio, hora_fin) 
                VALUES ('Barbero Principal', '123456789', 'barbero@barberia.com', '08:00', '17:00')
            ''')
            barbero_id = cursor.lastrowid
        
        # Servicios por defecto PARA ESE BARBERO
        cursor.execute('''
            INSERT INTO servicios (barbero_id, nombre, duracion_minutos, precio) VALUES
            (%s, 'Corte', 45, 25000),
            (%s, 'Barba', 30, 15000),
            (%s, 'Combo (Corte + Barba)', 75, 30000)
        ''', (barbero_id, barbero_id, barbero_id))
        print("✅ Datos de prueba insertados")

    # ===== ADMIN =====
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

    # ===== USUARIOS PARA BARBEROS + SERVICIOS POR DEFECTO =====
    cursor.execute('SELECT id, nombre FROM barberos WHERE activo = 1')
    barberos = cursor.fetchall()
    
    for b in barberos:
        barbero_id = b['id']
        nombre = b['nombre']
        
        cursor.execute('SELECT 1 FROM usuarios WHERE barbero_id = %s', (barbero_id,))
        if not cursor.fetchone():
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
        
        # Crear servicios por defecto si no tiene
        cursor.execute('SELECT COUNT(*) as cnt FROM servicios WHERE barbero_id = %s', (barbero_id,))
        if cursor.fetchone()['cnt'] == 0:
            cursor.execute('''
                INSERT INTO servicios (barbero_id, nombre, duracion_minutos, precio) VALUES
                (%s, 'Corte', 45, 25000),
                (%s, 'Barba', 30, 15000),
                (%s, 'Combo (Corte + Barba)', 75, 30000)
            ''', (barbero_id, barbero_id, barbero_id))
            print(f"✅ Servicios por defecto para {nombre}")

    # ===== CATALOGO POR DEFECTO =====
    cursor.execute('SELECT COUNT(*) as cnt FROM catalogo')
    if cursor.fetchone()['cnt'] == 0:
        items = []
        for i in range(1, 21):
            items.append(('producto', f'producto{i}.jpg', f'Producto {i}', f'Descripcion del producto {i}', '$20.000 COP', i))
        for i in range(1, 7):
            items.append(('estilo', f'corte{i}.jpg', f'Corte {i}', '', '', i))
        for tipo, archivo, nombre, descripcion, precio, orden in items:
            cursor.execute('''
                INSERT INTO catalogo (tipo, archivo, nombre, descripcion, precio, orden, activo)
                VALUES (%s, %s, %s, %s, %s, %s, 1)
            ''', (tipo, archivo, nombre, descripcion, precio, orden))
        print(f"✅ Catalogo por defecto creado ({len(items)} items)")

    conn.commit()
    conn.close()