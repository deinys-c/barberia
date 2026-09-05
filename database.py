import sqlite3
import json
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'barberia.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS barberos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            telefono TEXT,
            email TEXT,
            hora_inicio TEXT DEFAULT '08:00',
            hora_fin TEXT DEFAULT '17:00',
            dias_trabajo TEXT DEFAULT '["lunes","martes","miercoles","jueves","viernes","sabado"]',
            activo INTEGER DEFAULT 1
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS servicios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            duracion_minutos INTEGER NOT NULL,
            precio REAL NOT NULL,
            descripcion TEXT,
            activo INTEGER DEFAULT 1
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            telefono TEXT,
            email TEXT,
            notas_habituales TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS citas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            fecha_creacion TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (barbero_id) REFERENCES barberos(id),
            FOREIGN KEY (cliente_id) REFERENCES clientes(id),
            FOREIGN KEY (servicio_id) REFERENCES servicios(id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bloqueos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            barbero_id INTEGER NOT NULL,
            fecha_inicio TEXT NOT NULL,
            fecha_fin TEXT NOT NULL,
            motivo TEXT,
            activo INTEGER DEFAULT 1,
            FOREIGN KEY (barbero_id) REFERENCES barberos(id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS logs_notificaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cita_id INTEGER NOT NULL,
            tipo TEXT NOT NULL,
            estado_envio TEXT NOT NULL,
            fecha_envio TEXT DEFAULT CURRENT_TIMESTAMP,
            intentos INTEGER DEFAULT 0,
            FOREIGN KEY (cita_id) REFERENCES citas(id)
        )
    ''')

    barbero = cursor.execute('SELECT id FROM barberos LIMIT 1').fetchone()
    if not barbero:
        cursor.execute('''
            INSERT INTO barberos (nombre, telefono, email) 
            VALUES ('Barbero Principal', '123456789', 'barbero@barberia.com')
        ''')
        # Precios en COP (25.000 y 15.000)
        cursor.execute('''
            INSERT INTO servicios (nombre, duracion_minutos, precio) VALUES
            ('Corte', 60, 25000.00),
            ('Barba', 30, 15000.00),
            ('Combo (Corte + Barba)', 90, 38000.00)
        ''')
        print("✅ Datos de prueba insertados (1 barbero, 3 servicios con precios COP)")

    conn.commit()
    conn.close()