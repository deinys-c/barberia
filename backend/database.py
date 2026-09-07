import os
import json
import sqlite3

# Intentar importar psycopg2 (solo estará disponible en producción si está instalado)
try:
    import psycopg2
    import psycopg2.extras
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False

# Determinar qué motor de base de datos usar
DATABASE_URL = os.getenv('DATABASE_URL')
USING_POSTGRES = DATABASE_URL is not None and DATABASE_URL.startswith('postgres')

def get_db():
    """Devuelve una conexión a la base de datos (SQLite local o PostgreSQL en producción)."""
    if USING_POSTGRES and PSYCOPG2_AVAILABLE:
        # Conexión a PostgreSQL
        conn = psycopg2.connect(DATABASE_URL)
        # Usar RealDictCursor para que los resultados sean diccionarios (como sqlite3.Row)
        conn.cursor_factory = psycopg2.extras.RealDictCursor
        return conn
    else:
        # Conexión a SQLite (local o fallback)
        db_path = os.path.join(os.path.dirname(__file__), 'barberia.db')
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

def init_db():
    """Crea las tablas si no existen (compatible con SQLite y PostgreSQL)."""
    conn = get_db()
    cursor = conn.cursor()

    # ===== DETECTAR TIPO DE BASE DE DATOS =====
    is_postgres = USING_POSTGRES and PSYCOPG2_AVAILABLE

    # ===== DEFINICIÓN DE TABLAS =====
    # Usamos sintaxis estándar compatible con ambos motores.
    # Para IDs, usamos INTEGER PRIMARY KEY en SQLite, y SERIAL en PostgreSQL.
    if is_postgres:
        id_def = "SERIAL PRIMARY KEY"
        # PostgreSQL usa TEXT por defecto, pero podemos definir todo como TEXT
    else:
        id_def = "INTEGER PRIMARY KEY AUTOINCREMENT"

    # Tabla barberos
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

    # Tabla servicios
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

    # Tabla clientes
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS clientes (
            id {id_def},
            nombre TEXT NOT NULL,
            telefono TEXT,
            email TEXT,
            notas_habituales TEXT
        )
    ''')

    # Tabla citas (la más importante)
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

    # Tabla bloqueos
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

    # Tabla logs_notificaciones
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

    # ===== INSERTAR DATOS DE PRUEBA (SI NO EXISTEN) =====
    if is_postgres:
        # PostgreSQL: usar SELECT EXISTS para verificar si hay datos
        cursor.execute("SELECT 1 FROM barberos LIMIT 1")
        barbero_existe = cursor.fetchone()
    else:
        # SQLite: usar SELECT COUNT
        cursor.execute("SELECT COUNT(*) as cnt FROM barberos")
        barbero_existe = cursor.fetchone()
        barbero_existe = barbero_existe and barbero_existe['cnt'] > 0

    if not barbero_existe:
        # Insertar barbero por defecto
        cursor.execute('''
            INSERT INTO barberos (nombre, telefono, email) 
            VALUES ('Barbero Principal', '123456789', 'barbero@barberia.com')
        ''')
        # Insertar servicios por defecto
        cursor.execute('''
            INSERT INTO servicios (nombre, duracion_minutos, precio) VALUES
            ('Corte', 60, 15.00),
            ('Barba', 30, 10.00),
            ('Combo (Corte + Barba)', 90, 22.00)
        ''')
        print("✅ Datos de prueba insertados (1 barbero, 3 servicios)")

    conn.commit()
    conn.close()