"""
Modulo de base de datos SQLite para el sistema de entradas y salidas.
Maneja empleados, registros de asistencia y configuracion.
"""

import sqlite3
import os
import hashlib
import secrets
from datetime import datetime, date, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "nevox_farma.db")


def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS empleados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            departamento TEXT NOT NULL DEFAULT '',
            hora_entrada TEXT NOT NULL DEFAULT '09:00',
            hora_salida TEXT NOT NULL DEFAULT '18:00',
            token_dispositivo TEXT,
            activo INTEGER NOT NULL DEFAULT 1,
            fecha_registro TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS registros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empleado_id INTEGER NOT NULL,
            tipo TEXT NOT NULL CHECK(tipo IN ('entrada', 'salida')),
            fecha_hora TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            token_usado TEXT,
            FOREIGN KEY (empleado_id) REFERENCES empleados(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS configuracion (
            clave TEXT PRIMARY KEY,
            valor TEXT NOT NULL
        )
    """)

    # Inicializar configuracion por defecto
    defaults = {
        "admin_password": hashlib.sha256("admin123".encode()).hexdigest(),
        "secret_key": secrets.token_hex(32),
        "nombre_empresa": "NEVOX FARMA",
        "tolerancia_minutos": "15",
    }
    for clave, valor in defaults.items():
        cursor.execute(
            "INSERT OR IGNORE INTO configuracion (clave, valor) VALUES (?, ?)",
            (clave, valor),
        )

    conn.commit()
    conn.close()


# --- Configuracion ---

def get_config(clave):
    conn = get_connection()
    row = conn.execute("SELECT valor FROM configuracion WHERE clave = ?", (clave,)).fetchone()
    conn.close()
    return row["valor"] if row else None


def set_config(clave, valor):
    conn = get_connection()
    conn.execute(
        "INSERT INTO configuracion (clave, valor) VALUES (?, ?) "
        "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
        (clave, valor),
    )
    conn.commit()
    conn.close()


def verificar_password_admin(password):
    hashed = hashlib.sha256(password.encode()).hexdigest()
    return hashed == get_config("admin_password")


def cambiar_password_admin(nuevo_password):
    hashed = hashlib.sha256(nuevo_password.encode()).hexdigest()
    set_config("admin_password", hashed)


# --- Empleados ---

def crear_empleado(nombre, departamento="", hora_entrada="09:00", hora_salida="18:00"):
    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO empleados (nombre, departamento, hora_entrada, hora_salida) VALUES (?, ?, ?, ?)",
        (nombre, departamento, hora_entrada, hora_salida),
    )
    empleado_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return empleado_id


def obtener_empleado(empleado_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM empleados WHERE id = ?", (empleado_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def obtener_empleado_por_token(token_dispositivo):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM empleados WHERE token_dispositivo = ? AND activo = 1",
        (token_dispositivo,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def listar_empleados(solo_activos=True):
    conn = get_connection()
    if solo_activos:
        rows = conn.execute("SELECT * FROM empleados WHERE activo = 1 ORDER BY nombre").fetchall()
    else:
        rows = conn.execute("SELECT * FROM empleados ORDER BY nombre").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def actualizar_empleado(empleado_id, nombre=None, departamento=None, hora_entrada=None, hora_salida=None, activo=None):
    conn = get_connection()
    campos = []
    valores = []
    if nombre is not None:
        campos.append("nombre = ?")
        valores.append(nombre)
    if departamento is not None:
        campos.append("departamento = ?")
        valores.append(departamento)
    if hora_entrada is not None:
        campos.append("hora_entrada = ?")
        valores.append(hora_entrada)
    if hora_salida is not None:
        campos.append("hora_salida = ?")
        valores.append(hora_salida)
    if activo is not None:
        campos.append("activo = ?")
        valores.append(activo)
    if campos:
        valores.append(empleado_id)
        conn.execute(f"UPDATE empleados SET {', '.join(campos)} WHERE id = ?", valores)
        conn.commit()
    conn.close()


def vincular_dispositivo(empleado_id, token_dispositivo):
    conn = get_connection()
    conn.execute(
        "UPDATE empleados SET token_dispositivo = ? WHERE id = ?",
        (token_dispositivo, empleado_id),
    )
    conn.commit()
    conn.close()


def desvincular_dispositivo(empleado_id):
    conn = get_connection()
    conn.execute("UPDATE empleados SET token_dispositivo = NULL WHERE id = ?", (empleado_id,))
    conn.commit()
    conn.close()


# --- Registros ---

def registrar_asistencia(empleado_id, tipo, token_usado=None):
    conn = get_connection()
    conn.execute(
        "INSERT INTO registros (empleado_id, tipo, token_usado) VALUES (?, ?, ?)",
        (empleado_id, tipo, token_usado),
    )
    conn.commit()
    conn.close()


def obtener_ultimo_registro(empleado_id, fecha=None):
    if fecha is None:
        fecha = date.today().isoformat()
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM registros WHERE empleado_id = ? AND date(fecha_hora) = ? ORDER BY fecha_hora DESC LIMIT 1",
        (empleado_id, fecha),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def obtener_siguiente_tipo(empleado_id):
    ultimo = obtener_ultimo_registro(empleado_id)
    if ultimo is None or ultimo["tipo"] == "salida":
        return "entrada"
    return "salida"


def obtener_registros_dia(fecha=None):
    if fecha is None:
        fecha = date.today().isoformat()
    conn = get_connection()
    rows = conn.execute(
        """SELECT r.*, e.nombre, e.departamento
           FROM registros r
           JOIN empleados e ON r.empleado_id = e.id
           WHERE date(r.fecha_hora) = ?
           ORDER BY r.fecha_hora DESC""",
        (fecha,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def obtener_registros_rango(fecha_inicio, fecha_fin, empleado_id=None):
    conn = get_connection()
    if empleado_id:
        rows = conn.execute(
            """SELECT r.*, e.nombre, e.departamento
               FROM registros r
               JOIN empleados e ON r.empleado_id = e.id
               WHERE date(r.fecha_hora) BETWEEN ? AND ? AND r.empleado_id = ?
               ORDER BY r.fecha_hora""",
            (fecha_inicio, fecha_fin, empleado_id),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT r.*, e.nombre, e.departamento
               FROM registros r
               JOIN empleados e ON r.empleado_id = e.id
               WHERE date(r.fecha_hora) BETWEEN ? AND ?
               ORDER BY r.fecha_hora""",
            (fecha_inicio, fecha_fin),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def calcular_horas_trabajadas(empleado_id, fecha_inicio, fecha_fin):
    registros = obtener_registros_rango(fecha_inicio, fecha_fin, empleado_id)
    total_segundos = 0
    entrada_actual = None

    for reg in registros:
        dt = datetime.fromisoformat(reg["fecha_hora"])
        if reg["tipo"] == "entrada":
            entrada_actual = dt
        elif reg["tipo"] == "salida" and entrada_actual is not None:
            total_segundos += (dt - entrada_actual).total_seconds()
            entrada_actual = None

    horas = total_segundos / 3600
    return round(horas, 2)


def limpiar_registros():
    """Elimina todos los registros de asistencia."""
    conn = get_connection()
    conn.execute("DELETE FROM registros")
    conn.execute("DELETE FROM sqlite_sequence WHERE name = 'registros'")
    conn.commit()
    conn.close()


def limpiar_registros_y_empleados():
    """Elimina todos los registros de asistencia y todos los empleados."""
    conn = get_connection()
    conn.execute("DELETE FROM registros")
    conn.execute("DELETE FROM empleados")
    conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('registros', 'empleados')")
    conn.commit()
    conn.close()


def obtener_retardos(fecha_inicio, fecha_fin):
    conn = get_connection()
    empleados = listar_empleados()
    retardos = []

    for emp in empleados:
        rows = conn.execute(
            """SELECT fecha_hora FROM registros
               WHERE empleado_id = ? AND tipo = 'entrada' AND date(fecha_hora) BETWEEN ? AND ?
               ORDER BY fecha_hora""",
            (emp["id"], fecha_inicio, fecha_fin),
        ).fetchall()

        hora_limite = emp["hora_entrada"]
        for row in rows:
            dt = datetime.fromisoformat(row["fecha_hora"])
            fecha_str = dt.date().isoformat()
            # Primera entrada del dia
            primera_del_dia = conn.execute(
                """SELECT MIN(fecha_hora) as primera FROM registros
                   WHERE empleado_id = ? AND tipo = 'entrada' AND date(fecha_hora) = ?""",
                (emp["id"], fecha_str),
            ).fetchone()
            if primera_del_dia and primera_del_dia["primera"] == row["fecha_hora"]:
                hora_registro = dt.strftime("%H:%M")
                if hora_registro > hora_limite:
                    tolerancia = int(get_config("tolerancia_minutos") or "15")
                    h, m = map(int, hora_limite.split(":"))
                    limite_con_tolerancia = (datetime.combine(dt.date(), datetime.min.time().replace(hour=h, minute=m))
                                             + timedelta(minutes=tolerancia)).strftime("%H:%M")
                    retardos.append({
                        "empleado_id": emp["id"],
                        "nombre": emp["nombre"],
                        "departamento": emp["departamento"],
                        "fecha": fecha_str,
                        "hora_programada": hora_limite,
                        "hora_registro": hora_registro,
                        "con_tolerancia": hora_registro <= limite_con_tolerancia,
                    })

    conn.close()
    return retardos
