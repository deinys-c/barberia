import json
from datetime import datetime, timedelta
from config import DIAS_ES
from database import get_db
from helpers import es_dia_habil

def obtener_duracion_servicio(servicio_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT duracion_minutos FROM servicios WHERE id = %s AND activo = 1', (servicio_id,))
    row = cursor.fetchone()
    conn.close()
    return row['duracion_minutos'] if row else 30

def _parse_hora(valor, default):
    """Parsea una hora de forma segura."""
    if not valor:
        return default
    s = str(valor).strip()
    try:
        return datetime.strptime(s, '%H:%M')
    except ValueError:
        # Intentar con segundos (ej. '13:00:00')
        try:
            return datetime.strptime(s[:5], '%H:%M')
        except ValueError:
            return default

def _generar_horas_barbero(barbero):
    """Genera las horas candidatas (cada 30 min) respetando horario y pausa."""
    h_inicio = _parse_hora(barbero.get('hora_inicio'), datetime.strptime('08:00', '%H:%M'))
    h_fin = _parse_hora(barbero.get('hora_fin'), datetime.strptime('17:00', '%H:%M'))
    
    pausa_ini = None
    pausa_fin = None
    p_ini_raw = barbero.get('pausa_inicio')
    p_fin_raw = barbero.get('pausa_fin')
    if p_ini_raw and p_fin_raw:
        try:
            pausa_ini = _parse_hora(p_ini_raw, None)
            pausa_fin = _parse_hora(p_fin_raw, None)
        except Exception:
            pausa_ini = None
            pausa_fin = None
    
    horas = []
    actual = h_inicio
    while actual < h_fin:
        # ¿Estamos en el bloque de pausa?
        if pausa_ini and pausa_fin and pausa_ini <= actual < pausa_fin:
            actual = pausa_fin
            continue
        # Solo agregar si cabe un bloque completo de 30 min
        if actual + timedelta(minutes=30) <= h_fin:
            horas.append(actual.strftime('%H:%M'))
        actual += timedelta(minutes=30)
    
    return horas

def _horas_ocupadas(cursor, barbero_id, fecha_str):
    cursor.execute('''
        SELECT hora_inicio, hora_fin FROM citas 
        WHERE barbero_id = %s AND fecha = %s 
        AND estado IN ('confirmada', 'pendiente_confirmacion')
    ''', (barbero_id, fecha_str))
    ocupadas = set()
    for c in cursor.fetchall():
        ini = datetime.strptime(c['hora_inicio'], '%H:%M')
        fin = datetime.strptime(c['hora_fin'], '%H:%M')
        actual = ini
        while actual < fin:
            ocupadas.add(actual.strftime('%H:%M'))
            actual += timedelta(minutes=30)
    return ocupadas

def _esta_libre(hora_inicio_str, bloques_necesarios, horas_ocupadas, horas_validas):
    base = datetime.strptime(hora_inicio_str, '%H:%M')
    for i in range(bloques_necesarios):
        bloque = (base + timedelta(minutes=30*i)).strftime('%H:%M')
        if bloque not in horas_validas or bloque in horas_ocupadas:
            return False
    return True

def calcular_huecos_libres(fecha_str, barbero_id=0, servicio_id=0):
    conn = get_db()
    cursor = conn.cursor()

    if not es_dia_habil(fecha_str):
        conn.close()
        return []

    fecha = datetime.strptime(fecha_str, '%Y-%m-%d')
    dia_semana = fecha.weekday()
    dia_actual_nombre = DIAS_ES[dia_semana]

    duracion_nuevo = obtener_duracion_servicio(servicio_id) if servicio_id > 0 else 30
    bloques_necesarios = (duracion_nuevo + 29) // 30

    def procesar_barbero(b):
        try:
            dias = json.loads(b['dias_trabajo'])
        except (json.JSONDecodeError, TypeError):
            dias = DIAS_ES[:6]
        if dia_actual_nombre not in dias:
            return []

        cursor.execute('''
            SELECT 1 FROM bloqueos 
            WHERE barbero_id = %s AND activo = 1 
            AND fecha_inicio <= %s AND fecha_fin >= %s
        ''', (b['id'], fecha_str, fecha_str))
        if cursor.fetchone():
            return []

        # Convertir a dict normal para acceder con .get()
        b_dict = dict(b)
        horas_validas = set(_generar_horas_barbero(b_dict))
        horas_ocupadas = _horas_ocupadas(cursor, b['id'], fecha_str)

        disponibles = []
        for h in sorted(horas_validas):
            if _esta_libre(h, bloques_necesarios, horas_ocupadas, horas_validas):
                disponibles.append(h)
        return disponibles

    if barbero_id > 0:
        cursor.execute('''
            SELECT id, hora_inicio, hora_fin, pausa_inicio, pausa_fin, dias_trabajo 
            FROM barberos WHERE id = %s AND activo = 1
        ''', (barbero_id,))
        barbero = cursor.fetchone()
        if not barbero:
            conn.close()
            return []
        resultado = procesar_barbero(barbero)
    else:
        cursor.execute('''
            SELECT id, hora_inicio, hora_fin, pausa_inicio, pausa_fin, dias_trabajo 
            FROM barberos WHERE activo = 1
        ''')
        barberos = cursor.fetchall()
        resultado = []
        for b in barberos:
            for h in procesar_barbero(b):
                if h not in resultado:
                    resultado.append(h)

    conn.close()
    return sorted(set(resultado))