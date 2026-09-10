import os
import json
import psycopg2
import psycopg2.extras
import sqlite3
from werkzeug.security import generate_password_hash
import unicodedata

def normalizar_username(nombre):
    """Convierte un nombre en un username válido: minúsculas, sin acentos, sin espacios."""
    if not nombre:
        return 'barbero'
    # Quitar acentos
    nfkd = unicodedata.normalize('NFKD', nombre)
    solo_ascii = nfkd.encode('ASCII', 'ignore').decode('ASCII')
    # Minúsculas, solo letras y números
    username = ''.join(c for c in solo_ascii.lower() if c.isalnum())
    if not username:
        username = 'barbero'
    return username
    
DATABASE_URL = os.getenv('DATABASE_URL')
USING_POSTGRES = DATABASE_URL is not None and DATABASE_URL.startswith('postgres')

def get_db():
    """Devuelve una conexión a la base de datos (PostgreSQL en producción, SQLite local)."""
    if USING_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL)
        conn.cursor_factory = psycopg2.extras.RealDictCursor
        return conn
    else:
        db_path = os.path.join(os.path.dirname(__file__), 'barberia.db')
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

def init_db():
    """Crea las tablas, índices, y usuarios por defecto."""
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

    # ===== ÍNDICES =====
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

    # ===== TABLA LOGS NOTIFICACIONES =====
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

    # ===== DATOS DE PRUEBA (BARBERO PRINCIPAL Y SERVICIOS) =====
    if is_postgres:
        cursor.execute("SELECT 1 FROM barberos LIMIT 1")
        existe = cursor.fetchone()
    else:
        cursor.execute("SELECT COUNT(*) as cnt FROM barberos")
        existe = cursor.fetchone()['cnt'] > 0

    if not existe:
        cursor.execute('''
            INSERT INTO barberos (nombre, telefono, email) 
            VALUES ('Barbero Principal', '123456789', 'barbero@barberia.com')
            RETURNING id
        ''') if is_postgres else cursor.execute('''
            INSERT INTO barberos (nombre, telefono, email) 
            VALUES ('Barbero Principal', '123456789', 'barbero@barberia.com')
        ''')
        
        if is_postgres:
            barbero_id = cursor.fetchone()['id']
        else:
            barbero_id = cursor.lastrowid
        
        cursor.execute('''
            INSERT INTO servicios (nombre, duracion_minutos, precio) VALUES
            ('Corte', 45, 25000),
            ('Barba', 30, 15000),
            ('Combo (Corte + Barba)', 75, 30000)
        ''')
        print("✅ Datos de prueba insertados (1 barbero, 3 servicios)")

    # ===== CREAR USUARIO ADMIN SI NO EXISTE =====
    cursor.execute("SELECT 1 FROM usuarios WHERE username = 'admin'")
    admin_existe = cursor.fetchone()
    if not admin_existe:
        admin_hash = generate_password_hash('barberia2026')
        cursor.execute('''
            INSERT INTO usuarios (username, password_hash, rol, barbero_id)
            VALUES ('admin', %s, 'admin', NULL)
        ''' if is_postgres else '''
            INSERT INTO usuarios (username, password_hash, rol, barbero_id)
            VALUES ('admin', ?, 'admin', NULL)
        ''', (admin_hash,))
        print("✅ Usuario admin creado: admin / barberia2026")

    # ===== CREAR USUARIOS PARA BARBEROS EXISTENTES QUE NO TENGAN =====
    cursor.execute('SELECT id, nombre FROM barberos WHERE activo = 1')
    barberos = cursor.fetchall()
    
    for b in barberos:
        barbero_id = b['id']
        nombre = b['nombre']
        
        cursor.execute('SELECT 1 FROM usuarios WHERE barbero_id = %s', (barbero_id,))
        if cursor.fetchone():
            continue
        
        # Generar username y password
        username = normalizar_username(nombre)
        password = f"{username}123"
        
        # Verificar colisión y agregar número
        base_username = username
        contador = 2
        while True:
            cursor.execute('SELECT 1 FROM usuarios WHERE username = %s', (username,))
            if not cursor.fetchone():
                break
            username = f"{base_username}{contador}"
            contador += 1
        
        pwd_hash = generate_password_hash(password)
        cursor.execute('''
            INSERT INTO usuarios (username, password_hash, rol, barbero_id)
            VALUES (%s, %s, 'barbero', %s)
        ''', (username, pwd_hash, barbero_id))
        print(f"✅ Usuario creado: {username} / {password}")

    conn.commit()
    conn.close()