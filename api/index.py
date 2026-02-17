"""
NEVOX FARMA - Sistema de Control de Asistencia
Aplicacion Flask para Vercel con Supabase.
Archivo unico con toda la logica (database, QR, rutas).
"""

import os
import hashlib
import hmac
import secrets
import time
import io
import base64
import traceback
from io import BytesIO
from functools import wraps
from datetime import datetime, date, timedelta

from flask import (
    Flask, request, render_template, jsonify, session,
    redirect, url_for, send_file,
)
from supabase import create_client
import qrcode
from PIL import Image

# ============================================================
# CONFIG
# ============================================================

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
BASE_URL = os.environ.get("BASE_URL", "http://localhost:5000").rstrip("/")
QR_ROTATION_INTERVAL = 30

_sb_client = None

def _get_sb():
    global _sb_client
    if _sb_client is None:
        _sb_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _sb_client

# ============================================================
# DATABASE FUNCTIONS
# ============================================================

def db_get_config(clave):
    sb = _get_sb()
    result = sb.table("configuracion").select("valor").eq("clave", clave).execute()
    if result.data:
        return result.data[0]["valor"]
    return None

def db_set_config(clave, valor):
    sb = _get_sb()
    sb.table("configuracion").upsert({"clave": clave, "valor": valor}).execute()

def db_verificar_password(password):
    hashed = hashlib.sha256(password.encode()).hexdigest()
    return hashed == db_get_config("admin_password")

def db_cambiar_password(nuevo):
    hashed = hashlib.sha256(nuevo.encode()).hexdigest()
    db_set_config("admin_password", hashed)

def db_crear_empleado(nombre, departamento="", hora_entrada="09:00", hora_salida="18:00"):
    sb = _get_sb()
    result = sb.table("empleados").insert({
        "nombre": nombre, "departamento": departamento,
        "hora_entrada": hora_entrada, "hora_salida": hora_salida,
    }).execute()
    return result.data[0]["id"]

def _fix_activo(row):
    row["activo"] = 1 if row.get("activo") else 0
    return row

def db_obtener_empleado(empleado_id):
    sb = _get_sb()
    result = sb.table("empleados").select("*").eq("id", empleado_id).execute()
    return _fix_activo(result.data[0]) if result.data else None

def db_obtener_empleado_por_token(token):
    sb = _get_sb()
    result = sb.table("empleados").select("*").eq("token_dispositivo", token).eq("activo", True).execute()
    return _fix_activo(result.data[0]) if result.data else None

def db_listar_empleados(solo_activos=True):
    sb = _get_sb()
    q = sb.table("empleados").select("*")
    if solo_activos:
        q = q.eq("activo", True)
    result = q.order("nombre").execute()
    return [_fix_activo(r) for r in result.data]

def db_actualizar_empleado(emp_id, **kwargs):
    campos = {}
    for k in ["nombre", "departamento", "hora_entrada", "hora_salida"]:
        if k in kwargs and kwargs[k] is not None:
            campos[k] = kwargs[k]
    if "activo" in kwargs and kwargs["activo"] is not None:
        campos["activo"] = bool(kwargs["activo"])
    if campos:
        sb = _get_sb()
        sb.table("empleados").update(campos).eq("id", emp_id).execute()

def db_vincular(emp_id, token):
    sb = _get_sb()
    sb.table("empleados").update({"token_dispositivo": token}).eq("id", emp_id).execute()

def db_desvincular(emp_id):
    sb = _get_sb()
    sb.table("empleados").update({"token_dispositivo": None}).eq("id", emp_id).execute()

def db_registrar_asistencia(emp_id, tipo, token_usado=None):
    sb = _get_sb()
    sb.table("registros").insert({"empleado_id": emp_id, "tipo": tipo, "token_usado": token_usado}).execute()

def db_ultimo_registro(emp_id, fecha=None):
    if not fecha:
        fecha = date.today().isoformat()
    sb = _get_sb()
    result = sb.table("registros").select("*").eq("empleado_id", emp_id) \
        .gte("fecha_hora", f"{fecha}T00:00:00").lte("fecha_hora", f"{fecha}T23:59:59") \
        .order("fecha_hora", desc=True).limit(1).execute()
    return result.data[0] if result.data else None

def db_siguiente_tipo(emp_id):
    ultimo = db_ultimo_registro(emp_id)
    return "entrada" if (ultimo is None or ultimo["tipo"] == "salida") else "salida"

def _flatten_registros(data):
    registros = []
    for r in data:
        emp = r.pop("empleados", {}) or {}
        r["nombre"] = emp.get("nombre", "")
        r["departamento"] = emp.get("departamento", "")
        registros.append(r)
    return registros

def db_registros_dia(fecha=None):
    if not fecha:
        fecha = date.today().isoformat()
    sb = _get_sb()
    result = sb.table("registros").select("*, empleados(nombre, departamento)") \
        .gte("fecha_hora", f"{fecha}T00:00:00").lte("fecha_hora", f"{fecha}T23:59:59") \
        .order("fecha_hora", desc=True).execute()
    return _flatten_registros(result.data)

def db_registros_rango(desde, hasta, emp_id=None):
    sb = _get_sb()
    q = sb.table("registros").select("*, empleados(nombre, departamento)") \
        .gte("fecha_hora", f"{desde}T00:00:00").lte("fecha_hora", f"{hasta}T23:59:59")
    if emp_id:
        q = q.eq("empleado_id", emp_id)
    result = q.order("fecha_hora").execute()
    return _flatten_registros(result.data)

def db_horas_trabajadas(emp_id, desde, hasta):
    registros = db_registros_rango(desde, hasta, emp_id)
    total = 0
    entrada = None
    for r in registros:
        dt = datetime.fromisoformat(r["fecha_hora"])
        if r["tipo"] == "entrada":
            entrada = dt
        elif r["tipo"] == "salida" and entrada:
            total += (dt - entrada).total_seconds()
            entrada = None
    return round(total / 3600, 2)

def db_retardos(desde, hasta):
    sb = _get_sb()
    empleados = db_listar_empleados()
    try:
        result = sb.rpc("obtener_primera_entrada_por_dia", {"p_fecha_inicio": desde, "p_fecha_fin": hasta}).execute()
        entradas = result.data or []
    except Exception:
        entradas = []
    emp_map = {e["id"]: e for e in empleados}
    retardos = []
    for entry in entradas:
        emp = emp_map.get(entry["empleado_id"])
        if not emp:
            continue
        hora_limite = emp["hora_entrada"]
        hora_reg = entry["primera_hora"]
        if hora_reg > hora_limite:
            tol = int(db_get_config("tolerancia_minutos") or "15")
            h, m = map(int, hora_limite.split(":"))
            lim = (datetime.combine(date.today(), datetime.min.time().replace(hour=h, minute=m)) + timedelta(minutes=tol)).strftime("%H:%M")
            retardos.append({
                "empleado_id": emp["id"], "nombre": emp["nombre"],
                "departamento": emp["departamento"], "fecha": entry["fecha"],
                "hora_programada": hora_limite, "hora_registro": hora_reg,
                "con_tolerancia": hora_reg <= lim,
            })
    return retardos

def db_limpiar_registros():
    sb = _get_sb()
    sb.table("registros").delete().neq("id", 0).execute()

def db_limpiar_todo():
    sb = _get_sb()
    sb.table("registros").delete().neq("id", 0).execute()
    sb.table("empleados").delete().neq("id", 0).execute()

# ============================================================
# QR / TOKEN FUNCTIONS
# ============================================================

def _secret():
    return db_get_config("secret_key")

def qr_token():
    secret = _secret()
    slot = int(time.time()) // QR_ROTATION_INTERVAL
    firma = hmac.new(secret.encode(), f"qr:{slot}".encode(), hashlib.sha256).hexdigest()
    return f"{slot}:{firma}"

def qr_validar(token):
    try:
        slot_str, firma = token.split(":")
        slot_r = int(slot_str)
    except (ValueError, AttributeError):
        return False
    secret = _secret()
    slot_now = int(time.time()) // QR_ROTATION_INTERVAL
    for s in [slot_now, slot_now - 1]:
        expected = hmac.new(secret.encode(), f"qr:{s}".encode(), hashlib.sha256).hexdigest()
        if s == slot_r and hmac.compare_digest(firma, expected):
            return True
    return False

def device_token(emp_id):
    secret = _secret()
    rand = secrets.token_hex(16)
    firma = hmac.new(secret.encode(), f"device:{emp_id}:{rand}".encode(), hashlib.sha256).hexdigest()
    return f"dev:{emp_id}:{rand}:{firma}"

def device_validar(token):
    try:
        prefix, emp_id, rand, firma = token.split(":")
        if prefix != "dev": return None
    except (ValueError, AttributeError):
        return None
    secret = _secret()
    expected = hmac.new(secret.encode(), f"device:{emp_id}:{rand}".encode(), hashlib.sha256).hexdigest()
    return int(emp_id) if hmac.compare_digest(firma, expected) else None

def reg_token(emp_id):
    secret = _secret()
    rand = secrets.token_hex(16)
    firma = hmac.new(secret.encode(), f"reg:{emp_id}:{rand}".encode(), hashlib.sha256).hexdigest()
    return f"reg:{emp_id}:{rand}:{firma}"

def reg_validar(token):
    try:
        prefix, emp_id, rand, firma = token.split(":")
        if prefix != "reg": return None
    except (ValueError, AttributeError):
        return None
    secret = _secret()
    expected = hmac.new(secret.encode(), f"reg:{emp_id}:{rand}".encode(), hashlib.sha256).hexdigest()
    return int(emp_id) if hmac.compare_digest(firma, expected) else None

def qr_base64(data, size=8):
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=size, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")

def qr_checkin_url():
    return f"{BASE_URL}/checkin?token={qr_token()}"

def qr_registro_url(emp_id):
    return f"{BASE_URL}/registro-dispositivo?token={reg_token(emp_id)}"

# ============================================================
# FLASK APP
# ============================================================

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "templates")

app = Flask(__name__, template_folder=TEMPLATE_DIR)
app.secret_key = os.environ.get("SECRET_KEY", "dev-fallback-change-me")

@app.errorhandler(Exception)
def handle_error(e):
    return jsonify({"error": str(e), "type": type(e).__name__, "trace": traceback.format_exc()}), 500

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin"):
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"ok": False, "mensaje": "No autorizado."}), 401
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated

# --- DASHBOARD ---
@app.route("/")
def index():
    return render_template("dashboard.html")

@app.route("/api/qr")
def api_qr():
    url = qr_checkin_url()
    b64 = qr_base64(url)
    rem = QR_ROTATION_INTERVAL - (int(time.time()) % QR_ROTATION_INTERVAL)
    return jsonify({"qr_base64": b64, "remaining_seconds": rem, "timestamp": datetime.now().strftime("%H:%M:%S")})

@app.route("/api/registros-hoy")
def api_registros_hoy():
    regs = db_registros_dia()
    ent = sum(1 for r in regs if r["tipo"] == "entrada")
    sal = sum(1 for r in regs if r["tipo"] == "salida")
    return jsonify({"registros": regs, "total": len(regs), "entradas": ent, "salidas": sal, "fecha": date.today().strftime("%d/%m/%Y")})

# --- CHECK-IN ---
@app.route("/checkin")
def checkin():
    t = request.args.get("token", "")
    if not qr_validar(t):
        return render_template("confirmacion.html", exito=False, mensaje="El codigo QR ha expirado. Escanea el QR actual.")
    return render_template("checkin.html", token_qr=t)

@app.route("/api/checkin", methods=["POST"])
def api_checkin():
    data = request.get_json()
    if not data: return jsonify({"ok": False, "mensaje": "Datos invalidos."}), 400
    tqr = data.get("token_qr", "")
    tdev = data.get("token_dispositivo", "")
    if not qr_validar(tqr): return jsonify({"ok": False, "mensaje": "QR expirado."}), 400
    if not tdev: return jsonify({"ok": False, "mensaje": "Dispositivo no registrado."}), 400
    emp_id = device_validar(tdev)
    if not emp_id: return jsonify({"ok": False, "mensaje": "Token invalido."}), 400
    emp = db_obtener_empleado(emp_id)
    if not emp or not emp["activo"]: return jsonify({"ok": False, "mensaje": "Empleado no encontrado o inactivo."}), 400
    if emp["token_dispositivo"] != tdev: return jsonify({"ok": False, "mensaje": "Dispositivo no vinculado."}), 400
    tipo = db_siguiente_tipo(emp_id)
    db_registrar_asistencia(emp_id, tipo, tqr)
    return jsonify({"ok": True, "mensaje": f"{tipo.capitalize()} registrada.", "nombre": emp["nombre"], "tipo": tipo})

# --- DEVICE REGISTRATION ---
@app.route("/registro-dispositivo")
def registro_dispositivo():
    t = request.args.get("token", "")
    emp_id = reg_validar(t)
    if not emp_id: return render_template("confirmacion.html", exito=False, mensaje="Enlace invalido o expirado.")
    emp = db_obtener_empleado(emp_id)
    if not emp: return render_template("confirmacion.html", exito=False, mensaje="Empleado no encontrado.")
    return render_template("registro_dispositivo.html", empleado=emp, token_reg=t)

@app.route("/api/registro-dispositivo", methods=["POST"])
def api_registro_dispositivo():
    data = request.get_json()
    if not data: return jsonify({"ok": False, "mensaje": "Datos invalidos."}), 400
    t = data.get("token_reg", "")
    emp_id = reg_validar(t)
    if not emp_id: return jsonify({"ok": False, "mensaje": "Token invalido."}), 400
    emp = db_obtener_empleado(emp_id)
    if not emp: return jsonify({"ok": False, "mensaje": "Empleado no encontrado."}), 400
    tok = device_token(emp_id)
    db_vincular(emp_id, tok)
    return jsonify({"ok": True, "mensaje": f"Vinculado para {emp['nombre']}.", "token_dispositivo": tok, "nombre": emp["nombre"]})

# --- ADMIN ---
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if db_verificar_password(request.form.get("password", "")):
            session["admin"] = True
            return redirect(url_for("admin_panel"))
        return render_template("admin_login.html", error="Contrasena incorrecta.")
    return render_template("admin_login.html")

@app.route("/admin")
@admin_required
def admin_panel():
    return render_template("admin.html")

@app.route("/admin/logout", methods=["POST"])
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("index"))

@app.route("/api/admin/empleados")
@admin_required
def api_admin_empleados():
    return jsonify({"empleados": db_listar_empleados(solo_activos=False)})

@app.route("/api/admin/empleados", methods=["POST"])
@admin_required
def api_admin_crear():
    data = request.get_json()
    if not data or not data.get("nombre", "").strip(): return jsonify({"ok": False, "mensaje": "Nombre obligatorio."}), 400
    eid = db_crear_empleado(data["nombre"].strip(), data.get("departamento", "").strip(), data.get("hora_entrada", "09:00").strip(), data.get("hora_salida", "18:00").strip())
    return jsonify({"ok": True, "id": eid})

@app.route("/api/admin/empleados/<int:eid>", methods=["PUT"])
@admin_required
def api_admin_editar(eid):
    data = request.get_json()
    if not data: return jsonify({"ok": False, "mensaje": "Datos invalidos."}), 400
    db_actualizar_empleado(eid, nombre=data.get("nombre"), departamento=data.get("departamento"), hora_entrada=data.get("hora_entrada"), hora_salida=data.get("hora_salida"))
    return jsonify({"ok": True})

@app.route("/api/admin/empleados/<int:eid>/toggle", methods=["POST"])
@admin_required
def api_admin_toggle(eid):
    emp = db_obtener_empleado(eid)
    if not emp: return jsonify({"ok": False, "mensaje": "No encontrado."}), 404
    new = 0 if emp["activo"] else 1
    db_actualizar_empleado(eid, activo=new)
    return jsonify({"ok": True, "activo": new})

@app.route("/api/admin/empleados/<int:eid>/qr-registro")
@admin_required
def api_admin_qr(eid):
    emp = db_obtener_empleado(eid)
    if not emp: return jsonify({"ok": False, "mensaje": "No encontrado."}), 404
    url = qr_registro_url(eid)
    return jsonify({"ok": True, "qr_base64": qr_base64(url), "nombre": emp["nombre"]})

@app.route("/api/admin/empleados/<int:eid>/desvincular", methods=["POST"])
@admin_required
def api_admin_desvincular(eid):
    emp = db_obtener_empleado(eid)
    if not emp: return jsonify({"ok": False, "mensaje": "No encontrado."}), 404
    db_desvincular(eid)
    return jsonify({"ok": True})

@app.route("/api/admin/config", methods=["GET"])
@admin_required
def api_admin_get_config():
    return jsonify({"nombre_empresa": db_get_config("nombre_empresa") or "NEVOX FARMA", "tolerancia_minutos": db_get_config("tolerancia_minutos") or "15"})

@app.route("/api/admin/config", methods=["POST"])
@admin_required
def api_admin_save_config():
    data = request.get_json()
    if not data: return jsonify({"ok": False, "mensaje": "Datos invalidos."}), 400
    if "nombre_empresa" in data: db_set_config("nombre_empresa", data["nombre_empresa"])
    if "tolerancia_minutos" in data:
        try:
            t = int(data["tolerancia_minutos"])
            if t < 0: raise ValueError
            db_set_config("tolerancia_minutos", str(t))
        except ValueError:
            return jsonify({"ok": False, "mensaje": "Tolerancia invalida."}), 400
    if data.get("nuevo_password"):
        if data["nuevo_password"] != data.get("confirmar_password"): return jsonify({"ok": False, "mensaje": "No coinciden."}), 400
        if len(data["nuevo_password"]) < 4: return jsonify({"ok": False, "mensaje": "Min 4 caracteres."}), 400
        db_cambiar_password(data["nuevo_password"])
    return jsonify({"ok": True, "mensaje": "Configuracion guardada."})

@app.route("/api/admin/limpiar-registros", methods=["POST"])
@admin_required
def api_admin_limpiar_reg():
    db_limpiar_registros()
    return jsonify({"ok": True, "mensaje": "Registros eliminados."})

@app.route("/api/admin/limpiar-todo", methods=["POST"])
@admin_required
def api_admin_limpiar_todo():
    db_limpiar_todo()
    return jsonify({"ok": True, "mensaje": "Registros y empleados eliminados."})

# --- REPORTS ---
@app.route("/reportes")
def reportes():
    return render_template("reports.html")

@app.route("/api/reportes/horas")
def api_reportes_horas():
    desde = request.args.get("desde", date.today().replace(day=1).isoformat())
    hasta = request.args.get("hasta", date.today().isoformat())
    emps = db_listar_empleados()
    datos = [{"nombre": e["nombre"], "departamento": e["departamento"], "horas": db_horas_trabajadas(e["id"], desde, hasta)} for e in emps]
    return jsonify({"datos": datos, "desde": desde, "hasta": hasta})

@app.route("/api/reportes/retardos")
def api_reportes_retardos():
    desde = request.args.get("desde", date.today().replace(day=1).isoformat())
    hasta = request.args.get("hasta", date.today().isoformat())
    return jsonify({"datos": db_retardos(desde, hasta), "desde": desde, "hasta": hasta})

@app.route("/api/reportes/exportar-excel")
def api_exportar_excel():
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    desde = request.args.get("desde", date.today().replace(day=1).isoformat())
    hasta = request.args.get("hasta", date.today().isoformat())
    eid = request.args.get("empleado_id")
    if eid: eid = int(eid)
    regs = db_registros_rango(desde, hasta, eid)
    wb = Workbook(); ws = wb.active; ws.title = "Registros"
    hf = Font(bold=True, color="FFFFFF", size=11)
    hfill = PatternFill(start_color="ea8511", end_color="ea8511", fill_type="solid")
    tf = Font(bold=True, size=14, color="1d120e")
    c = Alignment(horizontal="center", vertical="center")
    b = Border(left=Side(style="thin", color="e0e0e2"), right=Side(style="thin", color="e0e0e2"), top=Side(style="thin", color="e0e0e2"), bottom=Side(style="thin", color="e0e0e2"))
    af = PatternFill(start_color="f7f7f8", end_color="f7f7f8", fill_type="solid")
    ws.merge_cells("A1:E1"); ws["A1"] = f"NEVOX FARMA - Registros {desde} al {hasta}"; ws["A1"].font = tf
    for col, h in enumerate(["Fecha", "Hora", "Empleado", "Departamento", "Tipo"], 1):
        cell = ws.cell(row=3, column=col, value=h); cell.font = hf; cell.fill = hfill; cell.alignment = c; cell.border = b
    for i, r in enumerate(regs, 4):
        dt = datetime.fromisoformat(r["fecha_hora"])
        cells = [ws.cell(row=i, column=1, value=dt.strftime("%Y-%m-%d")), ws.cell(row=i, column=2, value=dt.strftime("%H:%M:%S")), ws.cell(row=i, column=3, value=r["nombre"]), ws.cell(row=i, column=4, value=r["departamento"]), ws.cell(row=i, column=5, value=r["tipo"].upper())]
        for cell in cells:
            cell.border = b
            if i % 2 == 0: cell.fill = af
    ws.column_dimensions["A"].width = 14; ws.column_dimensions["B"].width = 12; ws.column_dimensions["C"].width = 28; ws.column_dimensions["D"].width = 22; ws.column_dimensions["E"].width = 12
    buf = BytesIO(); wb.save(buf); buf.seek(0)
    return send_file(buf, as_attachment=True, download_name=f"registros_{desde}_{hasta}.xlsx", mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
