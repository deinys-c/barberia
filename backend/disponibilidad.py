import json
from datetime import datetime, timedelta
from config import DIAS_ES
from database import get_db
from helpers import es_dia_habil

def obtener_duracion_servicio(servicio_id):
    """Devuelve la duración en minutos del servicio."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT duracion_minutos FROM servicios WHERE id = %s AND activo = 1', (servicio_id,))
    row = cursor.fetchone()
    conn.close()
    return row['duracion_minutos'] if row else 30

def calcular_huecos_libres(fecha_str, barbero_id=0, servicio_id=0):
    """
    Calcula los huecos libres teniendo en cuenta:
    - El horario del barbero (hora_inicio, hora_fin)
    - Los días de trabajo del barbero
    - Los bloqueos del barbero
    - Las citas ya agendadas (con su duración real)
    - La duración del nuevo servicio a reservar
    """
    conn = get_db()
    cursor = conn.cursor()

    if not es_dia_habil(fecha_str):
        conn.close()
        return []

    fecha = datetime.strptime(fecha_str, '%Y-%m-%d')
    dia_semana = fecha.weekday()
    dia_actual_nombre = DIAS_ES[dia_semana]

    # Duración del servicio que se quiere reservar
    duracion_nuevo = obtener_duracion_servicio(servicio_id) if servicio_id > 0 else 30
    bloques_necesarios = (duracion_nuevo + 29) // 30  # Cuántos bloques de 30 min ocupa

    def generar_horas_barbero(b):
        """Genera todas las horas candidatas (cada 30 min) según el horario del barbero."""
        h_inicio = b.get('hora_inicio', '08:00') or '08:00'
        h_fin = b.get('hora_fin', '17:00') or '17:00'
        horas = []
        actual = datetime.strptime(h_inicio, '%H:%M')
        fin = datetime.strptime(h_fin, '%H:%M')
        # Bloques de la mañana y tarde
        while actual <= fin:
            horas.append(actual.strftime('%H:%M'))
            actual += timedelta(minutes=30)
        return horas

    def esta_libre(hora_inicio_str, barbero_id_local, horas_ocupadas):
        """
        Verifica si el hueco está libre por completo, considerando la duración.
        Se necesitan 'bloques_necesarios' bloques consecutivos libres.
        """
        # Convertir a datetime
        base = datetime.strptime(hora_inicio_str, '%H:%M')
        for i in range(bloques_necesarios):
            bloque = (base + timedelta(minutes=30*i)).strftime('%H:%M')
            if bloque in horas_ocupadas:
                return False
        return True

    if barbero_id > 0:
        # Barbero específico
        cursor.execute('SELECT hora_inicio, hora_fin, dias_trabajo FROM barberos WHERE id = %s AND activo = 1', (barbero_id,))
        barbero = cursor.fetchone()
        if not barbero:
            conn.close()
            return []
        try:
            dias = json.loads(barbero['dias_trabajo'])
        except (json.JSONDecodeError, TypeError):
            dias = DIAS_ES[:6]
        if dia_actual_nombre not in dias:
            conn.close()
            return []
        # Verificar bloqueos
        cursor.execute('''
            SELECT 1 FROM bloqueos 
            WHERE barbero_id = %s AND activo = 1 
            AND fecha_inicio <= %s AND fecha_fin >= %s
        ''', (barbero_id, fecha_str, fecha_str))
        if cursor.fetchone():
            conn.close()
            return []

        # Horas ocupadas por citas existentes (considerando su duración real)
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

        todas = generar_horas_barbero(dict(barbero))
        disponibles = [h for h in todas if esta_libre(h, barbero_id, ocupadas)]
    else:
        # Cualquier barbero
        cursor.execute('SELECT id, hora_inicio, hora_fin, dias_trabajo FROM barberos WHERE activo = 1')
        barberos = cursor.fetchall()
        if not barberos:
            conn.close()
            return []
        barberos_hoy = []
        for b in barberos:
            try:
                dias = json.loads(b['dias_trabajo'])
            except (json.JSONDecodeError, TypeError):
                dias = DIAS_ES[:6]
            if dia_actual_nombre not in dias:
                continue
            cursor.execute('''
                SELECT 1 FROM bloqueos 
                WHERE barbero_id = %s AND activo = 1 
                AND fecha_inicio <= %s AND fecha_fin >= %s
            ''', (b['id'], fecha_str, fecha_str))
            if cursor.fetchone():
                continue
            barberos_hoy.append(dict(b))

        if not barberos_hoy:
            conn.close()
            return []

        # Para cada barbero, calcular sus ocupadas
        disponibles = []
        for b in barberos_hoy:
            cursor.execute('''
                SELECT hora_inicio, hora_fin FROM citas 
                WHERE barbero_id = %s AND fecha = %s 
                AND estado IN ('confirmada', 'pendiente_confirmacion')
            ''', (b['id'], fecha_str))
            ocupadas = set()
            for c in cursor.fetchall():
                ini = datetime.strptime(c['hora_inicio'], '%H:%M')
                fin = datetime.strptime(c['hora_fin'], '%H:%M')
                actual = ini
                while actual < fin:
                    ocupadas.add(actual.strftime('%H:%M'))
                    actual += timedelta(minutes=30)
            todas = generar_horas_barbero(b)
            for h in todas:
                if esta_libre(h, b['id'], ocupadas):
                    if h not in disponibles:
                        disponibles.append(h)

    conn.close()
    return sorted(set(disponibles))