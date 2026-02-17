"""
Aplicacion Flask principal para Vercel.
Maneja dashboard, admin, reportes, check-in y registro de dispositivos.
"""

import os
import sys
import traceback
import time
from io import BytesIO
from functools import wraps
from datetime import datetime, date

from flask import (
    Flask, request, render_template, jsonify, session,
    redirect, url_for, send_file,
)

# Import local modules from same directory
from api import database, qr_manager

TEMPLATE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "templates"))

app = Flask(
    __name__,
    template_folder=TEMPLATE_DIR,
)
app.secret_key = os.environ.get("SECRET_KEY", "dev-fallback-change-me")


@app.errorhandler(Exception)
def handle_error(e):
    return jsonify({
        "error": str(e),
        "type": type(e).__name__,
        "trace": traceback.format_exc(),
    }), 500


# --- Auth decorator ---

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin"):
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"ok": False, "mensaje": "No autorizado."}), 401
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/")
def index():
    return render_template("dashboard.html")


@app.route("/api/qr")
def api_qr():
    url = qr_manager.generar_qr_rotativo_url()
    qr_b64 = qr_manager.generar_qr_base64(url)
    remaining = qr_manager.QR_ROTATION_INTERVAL - (
        int(time.time()) % qr_manager.QR_ROTATION_INTERVAL
    )
    return jsonify({
        "qr_base64": qr_b64,
        "remaining_seconds": remaining,
        "timestamp": datetime.now().strftime("%H:%M:%S"),
    })


@app.route("/api/registros-hoy")
def api_registros_hoy():
    registros = database.obtener_registros_dia()
    entradas = sum(1 for r in registros if r["tipo"] == "entrada")
    salidas = sum(1 for r in registros if r["tipo"] == "salida")
    return jsonify({
        "registros": registros,
        "total": len(registros),
        "entradas": entradas,
        "salidas": salidas,
        "fecha": date.today().strftime("%d/%m/%Y"),
    })


# ============================================================
# CHECK-IN (MOBILE)
# ============================================================

@app.route("/checkin")
def checkin():
    token_qr = request.args.get("token", "")
    if not qr_manager.validar_token_qr(token_qr):
        return render_template(
            "confirmacion.html", exito=False,
            mensaje="El codigo QR ha expirado. Escanea el QR actual de la pantalla.",
        )
    return render_template("checkin.html", token_qr=token_qr)


@app.route("/api/checkin", methods=["POST"])
def api_checkin():
    data = request.get_json()
    if not data:
        return jsonify({"ok": False, "mensaje": "Datos invalidos."}), 400

    token_qr = data.get("token_qr", "")
    token_dispositivo = data.get("token_dispositivo", "")

    if not qr_manager.validar_token_qr(token_qr):
        return jsonify({"ok": False, "mensaje": "El codigo QR ha expirado. Escanea de nuevo."}), 400

    if not token_dispositivo:
        return jsonify({"ok": False, "mensaje": "Dispositivo no registrado."}), 400

    emp_id = qr_manager.validar_token_dispositivo(token_dispositivo)
    if emp_id is None:
        return jsonify({"ok": False, "mensaje": "Token de dispositivo invalido."}), 400

    empleado = database.obtener_empleado(emp_id)
    if not empleado or not empleado["activo"]:
        return jsonify({"ok": False, "mensaje": "Empleado no encontrado o inactivo."}), 400

    if empleado["token_dispositivo"] != token_dispositivo:
        return jsonify({"ok": False, "mensaje": "Este dispositivo no esta vinculado a tu cuenta."}), 400

    tipo = database.obtener_siguiente_tipo(emp_id)
    database.registrar_asistencia(emp_id, tipo, token_qr)

    return jsonify({
        "ok": True,
        "mensaje": f"{tipo.capitalize()} registrada correctamente.",
        "nombre": empleado["nombre"],
        "tipo": tipo,
    })


# ============================================================
# DEVICE REGISTRATION (MOBILE)
# ============================================================

@app.route("/registro-dispositivo")
def registro_dispositivo():
    token_reg = request.args.get("token", "")
    emp_id = qr_manager.validar_token_registro(token_reg)
    if emp_id is None:
        return render_template(
            "confirmacion.html", exito=False,
            mensaje="El enlace de registro es invalido o ha expirado.",
        )

    empleado = database.obtener_empleado(emp_id)
    if not empleado:
        return render_template(
            "confirmacion.html", exito=False, mensaje="Empleado no encontrado.",
        )

    return render_template(
        "registro_dispositivo.html", empleado=empleado, token_reg=token_reg,
    )


@app.route("/api/registro-dispositivo", methods=["POST"])
def api_registro_dispositivo():
    data = request.get_json()
    if not data:
        return jsonify({"ok": False, "mensaje": "Datos invalidos."}), 400

    token_reg = data.get("token_reg", "")
    emp_id = qr_manager.validar_token_registro(token_reg)
    if emp_id is None:
        return jsonify({"ok": False, "mensaje": "Token de registro invalido."}), 400

    empleado = database.obtener_empleado(emp_id)
    if not empleado:
        return jsonify({"ok": False, "mensaje": "Empleado no encontrado."}), 400

    token_dispositivo = qr_manager.generar_token_dispositivo(emp_id)
    database.vincular_dispositivo(emp_id, token_dispositivo)

    return jsonify({
        "ok": True,
        "mensaje": f"Dispositivo vinculado para {empleado['nombre']}.",
        "token_dispositivo": token_dispositivo,
        "nombre": empleado["nombre"],
    })


# ============================================================
# ADMIN
# ============================================================

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        password = request.form.get("password", "")
        if database.verificar_password_admin(password):
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
    empleados = database.listar_empleados(solo_activos=False)
    return jsonify({"empleados": empleados})


@app.route("/api/admin/empleados", methods=["POST"])
@admin_required
def api_admin_crear_empleado():
    data = request.get_json()
    if not data or not data.get("nombre", "").strip():
        return jsonify({"ok": False, "mensaje": "El nombre es obligatorio."}), 400

    emp_id = database.crear_empleado(
        nombre=data["nombre"].strip(),
        departamento=data.get("departamento", "").strip(),
        hora_entrada=data.get("hora_entrada", "09:00").strip(),
        hora_salida=data.get("hora_salida", "18:00").strip(),
    )
    return jsonify({"ok": True, "id": emp_id})


@app.route("/api/admin/empleados/<int:emp_id>", methods=["PUT"])
@admin_required
def api_admin_editar_empleado(emp_id):
    data = request.get_json()
    if not data:
        return jsonify({"ok": False, "mensaje": "Datos invalidos."}), 400

    database.actualizar_empleado(
        emp_id,
        nombre=data.get("nombre"),
        departamento=data.get("departamento"),
        hora_entrada=data.get("hora_entrada"),
        hora_salida=data.get("hora_salida"),
    )
    return jsonify({"ok": True})


@app.route("/api/admin/empleados/<int:emp_id>/toggle", methods=["POST"])
@admin_required
def api_admin_toggle_empleado(emp_id):
    emp = database.obtener_empleado(emp_id)
    if not emp:
        return jsonify({"ok": False, "mensaje": "Empleado no encontrado."}), 404
    nuevo_estado = 0 if emp["activo"] else 1
    database.actualizar_empleado(emp_id, activo=nuevo_estado)
    return jsonify({"ok": True, "activo": nuevo_estado})


@app.route("/api/admin/empleados/<int:emp_id>/qr-registro")
@admin_required
def api_admin_qr_registro(emp_id):
    emp = database.obtener_empleado(emp_id)
    if not emp:
        return jsonify({"ok": False, "mensaje": "Empleado no encontrado."}), 404

    url = qr_manager.generar_qr_registro_url(emp_id)
    qr_b64 = qr_manager.generar_qr_base64(url)
    return jsonify({"ok": True, "qr_base64": qr_b64, "nombre": emp["nombre"]})


@app.route("/api/admin/empleados/<int:emp_id>/desvincular", methods=["POST"])
@admin_required
def api_admin_desvincular(emp_id):
    emp = database.obtener_empleado(emp_id)
    if not emp:
        return jsonify({"ok": False, "mensaje": "Empleado no encontrado."}), 404
    database.desvincular_dispositivo(emp_id)
    return jsonify({"ok": True})


@app.route("/api/admin/config", methods=["GET"])
@admin_required
def api_admin_get_config():
    return jsonify({
        "nombre_empresa": database.get_config("nombre_empresa") or "NEVOX FARMA",
        "tolerancia_minutos": database.get_config("tolerancia_minutos") or "15",
    })


@app.route("/api/admin/config", methods=["POST"])
@admin_required
def api_admin_save_config():
    data = request.get_json()
    if not data:
        return jsonify({"ok": False, "mensaje": "Datos invalidos."}), 400

    if "nombre_empresa" in data:
        database.set_config("nombre_empresa", data["nombre_empresa"])

    if "tolerancia_minutos" in data:
        try:
            tol = int(data["tolerancia_minutos"])
            if tol < 0:
                raise ValueError
            database.set_config("tolerancia_minutos", str(tol))
        except ValueError:
            return jsonify({"ok": False, "mensaje": "Tolerancia debe ser un numero positivo."}), 400

    if data.get("nuevo_password"):
        if data["nuevo_password"] != data.get("confirmar_password"):
            return jsonify({"ok": False, "mensaje": "Las contrasenas no coinciden."}), 400
        if len(data["nuevo_password"]) < 4:
            return jsonify({"ok": False, "mensaje": "La contrasena debe tener al menos 4 caracteres."}), 400
        database.cambiar_password_admin(data["nuevo_password"])

    return jsonify({"ok": True, "mensaje": "Configuracion guardada."})


@app.route("/api/admin/limpiar-registros", methods=["POST"])
@admin_required
def api_admin_limpiar_registros():
    database.limpiar_registros()
    return jsonify({"ok": True, "mensaje": "Registros eliminados."})


@app.route("/api/admin/limpiar-todo", methods=["POST"])
@admin_required
def api_admin_limpiar_todo():
    database.limpiar_registros_y_empleados()
    return jsonify({"ok": True, "mensaje": "Registros y empleados eliminados."})


# ============================================================
# REPORTS
# ============================================================

@app.route("/reportes")
def reportes():
    return render_template("reports.html")


@app.route("/api/reportes/horas")
def api_reportes_horas():
    desde = request.args.get("desde", date.today().replace(day=1).isoformat())
    hasta = request.args.get("hasta", date.today().isoformat())
    empleados = database.listar_empleados()
    resultado = []
    for emp in empleados:
        horas = database.calcular_horas_trabajadas(emp["id"], desde, hasta)
        resultado.append({
            "nombre": emp["nombre"],
            "departamento": emp["departamento"],
            "horas": horas,
        })
    return jsonify({"datos": resultado, "desde": desde, "hasta": hasta})


@app.route("/api/reportes/retardos")
def api_reportes_retardos():
    desde = request.args.get("desde", date.today().replace(day=1).isoformat())
    hasta = request.args.get("hasta", date.today().isoformat())
    retardos = database.obtener_retardos(desde, hasta)
    return jsonify({"datos": retardos, "desde": desde, "hasta": hasta})


@app.route("/api/reportes/exportar-excel")
def api_reportes_exportar_excel():
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    desde = request.args.get("desde", date.today().replace(day=1).isoformat())
    hasta = request.args.get("hasta", date.today().isoformat())
    emp_id = request.args.get("empleado_id")
    if emp_id:
        emp_id = int(emp_id)

    registros = database.obtener_registros_rango(desde, hasta, emp_id)

    wb = Workbook()
    ws = wb.active
    ws.title = "Registros"

    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_fill = PatternFill(start_color="ea8511", end_color="ea8511", fill_type="solid")
    title_font = Font(bold=True, size=14, color="1d120e")
    center = Alignment(horizontal="center", vertical="center")
    thin_border = Border(
        left=Side(style="thin", color="e0e0e2"),
        right=Side(style="thin", color="e0e0e2"),
        top=Side(style="thin", color="e0e0e2"),
        bottom=Side(style="thin", color="e0e0e2"),
    )
    alt_fill = PatternFill(start_color="f7f7f8", end_color="f7f7f8", fill_type="solid")

    ws.merge_cells("A1:E1")
    ws["A1"] = f"NEVOX FARMA - Registros del {desde} al {hasta}"
    ws["A1"].font = title_font
    ws["A1"].alignment = Alignment(vertical="center")
    ws.row_dimensions[1].height = 32

    headers = ["Fecha", "Hora", "Empleado", "Departamento", "Tipo"]
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=3, column=col, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center
        cell.border = thin_border
    ws.row_dimensions[3].height = 28

    for i, reg in enumerate(registros, 4):
        dt = datetime.fromisoformat(reg["fecha_hora"])
        row_fill = alt_fill if i % 2 == 0 else None
        cells = [
            ws.cell(row=i, column=1, value=dt.strftime("%Y-%m-%d")),
            ws.cell(row=i, column=2, value=dt.strftime("%H:%M:%S")),
            ws.cell(row=i, column=3, value=reg["nombre"]),
            ws.cell(row=i, column=4, value=reg["departamento"]),
            ws.cell(row=i, column=5, value=reg["tipo"].upper()),
        ]
        for cell in cells:
            cell.border = thin_border
            if row_fill:
                cell.fill = row_fill
        if reg["tipo"] == "entrada":
            cells[4].font = Font(color="16a34a", bold=True)
        else:
            cells[4].font = Font(color="ea8511", bold=True)

    ws.column_dimensions["A"].width = 14
    ws.column_dimensions["B"].width = 12
    ws.column_dimensions["C"].width = 28
    ws.column_dimensions["D"].width = 22
    ws.column_dimensions["E"].width = 12

    # Summary sheet
    ws2 = wb.create_sheet("Horas Trabajadas")
    ws2.merge_cells("A1:C1")
    ws2["A1"] = f"NEVOX FARMA - Resumen de Horas ({desde} al {hasta})"
    ws2["A1"].font = title_font
    ws2["A1"].alignment = Alignment(vertical="center")
    ws2.row_dimensions[1].height = 32

    for col, h in enumerate(["Empleado", "Departamento", "Horas Trabajadas"], 1):
        cell = ws2.cell(row=3, column=col, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center
        cell.border = thin_border
    ws2.row_dimensions[3].height = 28

    empleados = database.listar_empleados()
    for i, emp in enumerate(empleados, 4):
        horas = database.calcular_horas_trabajadas(emp["id"], desde, hasta)
        row_fill = alt_fill if i % 2 == 0 else None
        cells = [
            ws2.cell(row=i, column=1, value=emp["nombre"]),
            ws2.cell(row=i, column=2, value=emp["departamento"]),
            ws2.cell(row=i, column=3, value=f"{horas:.2f}"),
        ]
        for cell in cells:
            cell.border = thin_border
            if row_fill:
                cell.fill = row_fill

    ws2.column_dimensions["A"].width = 28
    ws2.column_dimensions["B"].width = 22
    ws2.column_dimensions["C"].width = 20

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = f"registros_{desde}_{hasta}.xlsx"
    return send_file(
        buffer, as_attachment=True, download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
