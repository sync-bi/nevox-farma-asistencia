"""
Modulo de base de datos para el sistema de entradas y salidas.
Usa Supabase (PostgreSQL) como backend.
"""

import os
import hashlib
from datetime import datetime, date, timedelta
from supabase import create_client

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


# --- Configuracion ---

def get_config(clave):
    sb = _get_client()
    result = sb.table("configuracion").select("valor").eq("clave", clave).execute()
    if result.data:
        return result.data[0]["valor"]
    return None


def set_config(clave, valor):
    sb = _get_client()
    sb.table("configuracion").upsert({"clave": clave, "valor": valor}).execute()


def verificar_password_admin(password):
    hashed = hashlib.sha256(password.encode()).hexdigest()
    return hashed == get_config("admin_password")


def cambiar_password_admin(nuevo_password):
    hashed = hashlib.sha256(nuevo_password.encode()).hexdigest()
    set_config("admin_password", hashed)


# --- Empleados ---

def crear_empleado(nombre, departamento="", hora_entrada="09:00", hora_salida="18:00"):
    sb = _get_client()
    result = sb.table("empleados").insert({
        "nombre": nombre,
        "departamento": departamento,
        "hora_entrada": hora_entrada,
        "hora_salida": hora_salida,
    }).execute()
    return result.data[0]["id"]


def obtener_empleado(empleado_id):
    sb = _get_client()
    result = sb.table("empleados").select("*").eq("id", empleado_id).execute()
    if result.data:
        row = result.data[0]
        row["activo"] = 1 if row["activo"] else 0
        return row
    return None


def obtener_empleado_por_token(token_dispositivo):
    sb = _get_client()
    result = (
        sb.table("empleados")
        .select("*")
        .eq("token_dispositivo", token_dispositivo)
        .eq("activo", True)
        .execute()
    )
    if result.data:
        row = result.data[0]
        row["activo"] = 1 if row["activo"] else 0
        return row
    return None


def listar_empleados(solo_activos=True):
    sb = _get_client()
    query = sb.table("empleados").select("*")
    if solo_activos:
        query = query.eq("activo", True)
    result = query.order("nombre").execute()
    for row in result.data:
        row["activo"] = 1 if row["activo"] else 0
    return result.data


def actualizar_empleado(empleado_id, nombre=None, departamento=None,
                        hora_entrada=None, hora_salida=None, activo=None):
    campos = {}
    if nombre is not None:
        campos["nombre"] = nombre
    if departamento is not None:
        campos["departamento"] = departamento
    if hora_entrada is not None:
        campos["hora_entrada"] = hora_entrada
    if hora_salida is not None:
        campos["hora_salida"] = hora_salida
    if activo is not None:
        campos["activo"] = bool(activo)
    if campos:
        sb = _get_client()
        sb.table("empleados").update(campos).eq("id", empleado_id).execute()


def vincular_dispositivo(empleado_id, token_dispositivo):
    sb = _get_client()
    sb.table("empleados").update(
        {"token_dispositivo": token_dispositivo}
    ).eq("id", empleado_id).execute()


def desvincular_dispositivo(empleado_id):
    sb = _get_client()
    sb.table("empleados").update(
        {"token_dispositivo": None}
    ).eq("id", empleado_id).execute()


# --- Registros ---

def registrar_asistencia(empleado_id, tipo, token_usado=None):
    sb = _get_client()
    sb.table("registros").insert({
        "empleado_id": empleado_id,
        "tipo": tipo,
        "token_usado": token_usado,
    }).execute()


def obtener_ultimo_registro(empleado_id, fecha=None):
    if fecha is None:
        fecha = date.today().isoformat()
    fecha_inicio = f"{fecha}T00:00:00"
    fecha_fin = f"{fecha}T23:59:59"
    sb = _get_client()
    result = (
        sb.table("registros")
        .select("*")
        .eq("empleado_id", empleado_id)
        .gte("fecha_hora", fecha_inicio)
        .lte("fecha_hora", fecha_fin)
        .order("fecha_hora", desc=True)
        .limit(1)
        .execute()
    )
    if result.data:
        return result.data[0]
    return None


def obtener_siguiente_tipo(empleado_id):
    ultimo = obtener_ultimo_registro(empleado_id)
    if ultimo is None or ultimo["tipo"] == "salida":
        return "entrada"
    return "salida"


def obtener_registros_dia(fecha=None):
    if fecha is None:
        fecha = date.today().isoformat()
    fecha_inicio = f"{fecha}T00:00:00"
    fecha_fin = f"{fecha}T23:59:59"
    sb = _get_client()
    result = (
        sb.table("registros")
        .select("*, empleados(nombre, departamento)")
        .gte("fecha_hora", fecha_inicio)
        .lte("fecha_hora", fecha_fin)
        .order("fecha_hora", desc=True)
        .execute()
    )
    registros = []
    for r in result.data:
        emp = r.pop("empleados", {}) or {}
        r["nombre"] = emp.get("nombre", "")
        r["departamento"] = emp.get("departamento", "")
        registros.append(r)
    return registros


def obtener_registros_rango(fecha_inicio, fecha_fin, empleado_id=None):
    sb = _get_client()
    query = (
        sb.table("registros")
        .select("*, empleados(nombre, departamento)")
        .gte("fecha_hora", f"{fecha_inicio}T00:00:00")
        .lte("fecha_hora", f"{fecha_fin}T23:59:59")
    )
    if empleado_id:
        query = query.eq("empleado_id", empleado_id)
    result = query.order("fecha_hora").execute()
    registros = []
    for r in result.data:
        emp = r.pop("empleados", {}) or {}
        r["nombre"] = emp.get("nombre", "")
        r["departamento"] = emp.get("departamento", "")
        registros.append(r)
    return registros


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


def obtener_retardos(fecha_inicio, fecha_fin):
    sb = _get_client()
    empleados = listar_empleados()

    try:
        result = sb.rpc("obtener_primera_entrada_por_dia", {
            "p_fecha_inicio": fecha_inicio,
            "p_fecha_fin": fecha_fin,
        }).execute()
        entradas_por_dia = result.data or []
    except Exception:
        entradas_por_dia = []

    emp_map = {e["id"]: e for e in empleados}
    retardos = []

    for entry in entradas_por_dia:
        emp = emp_map.get(entry["empleado_id"])
        if not emp:
            continue
        hora_limite = emp["hora_entrada"]
        hora_registro = entry["primera_hora"]

        if hora_registro > hora_limite:
            tolerancia = int(get_config("tolerancia_minutos") or "15")
            h, m = map(int, hora_limite.split(":"))
            limite_dt = datetime.combine(date.today(), datetime.min.time().replace(hour=h, minute=m))
            limite_con_tolerancia = (limite_dt + timedelta(minutes=tolerancia)).strftime("%H:%M")
            retardos.append({
                "empleado_id": emp["id"],
                "nombre": emp["nombre"],
                "departamento": emp["departamento"],
                "fecha": entry["fecha"],
                "hora_programada": hora_limite,
                "hora_registro": hora_registro,
                "con_tolerancia": hora_registro <= limite_con_tolerancia,
            })

    return retardos


def limpiar_registros():
    sb = _get_client()
    sb.table("registros").delete().neq("id", 0).execute()


def limpiar_registros_y_empleados():
    sb = _get_client()
    sb.table("registros").delete().neq("id", 0).execute()
    sb.table("empleados").delete().neq("id", 0).execute()
