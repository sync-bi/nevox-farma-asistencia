"""
Servidor Flask para recibir escaneos de QR desde los celulares de los empleados.
Maneja registro de dispositivos y check-in/check-out.
"""

import logging
import socket
from flask import Flask, request, render_template, jsonify

import database
import qr_manager

log = logging.getLogger("werkzeug")
log.setLevel(logging.WARNING)

app = Flask(
    __name__,
    template_folder="templates",
)
app.secret_key = "nevox-farma-internal"

# Referencia al callback para notificar la GUI de nuevos registros
_on_registro_callback = None
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 5000


def set_on_registro_callback(callback):
    global _on_registro_callback
    _on_registro_callback = callback


def get_local_ip():
    """Obtiene la IP local de la maquina en la red."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# --- Rutas ---

@app.route("/")
def index():
    return render_template("checkin.html", mensaje="Escanea el QR de la entrada para registrar tu asistencia.")


@app.route("/checkin")
def checkin():
    """Pagina que se abre al escanear el QR rotativo."""
    token_qr = request.args.get("token", "")

    if not qr_manager.validar_token_qr(token_qr):
        return render_template("confirmacion.html",
                               exito=False,
                               mensaje="El codigo QR ha expirado. Escanea el QR actual de la pantalla.")

    return render_template("checkin.html", token_qr=token_qr)


@app.route("/api/checkin", methods=["POST"])
def api_checkin():
    """Endpoint API para registrar entrada/salida."""
    data = request.get_json()
    if not data:
        return jsonify({"ok": False, "mensaje": "Datos invalidos."}), 400

    token_qr = data.get("token_qr", "")
    token_dispositivo = data.get("token_dispositivo", "")

    # Validar token QR
    if not qr_manager.validar_token_qr(token_qr):
        return jsonify({"ok": False, "mensaje": "El codigo QR ha expirado. Escanea de nuevo."}), 400

    # Validar token de dispositivo
    if not token_dispositivo:
        return jsonify({"ok": False, "mensaje": "Dispositivo no registrado. Pide a tu administrador el QR de registro."}), 400

    emp_id = qr_manager.validar_token_dispositivo(token_dispositivo)
    if emp_id is None:
        return jsonify({"ok": False, "mensaje": "Token de dispositivo invalido."}), 400

    empleado = database.obtener_empleado(emp_id)
    if not empleado or not empleado["activo"]:
        return jsonify({"ok": False, "mensaje": "Empleado no encontrado o inactivo."}), 400

    # Verificar que el token coincide con el registrado
    if empleado["token_dispositivo"] != token_dispositivo:
        return jsonify({"ok": False, "mensaje": "Este dispositivo no esta vinculado a tu cuenta."}), 400

    # Determinar tipo (entrada o salida)
    tipo = database.obtener_siguiente_tipo(emp_id)
    database.registrar_asistencia(emp_id, tipo, token_qr)

    # Notificar a la GUI
    if _on_registro_callback:
        try:
            _on_registro_callback(empleado["nombre"], tipo)
        except Exception:
            pass

    return jsonify({
        "ok": True,
        "mensaje": f"{tipo.capitalize()} registrada correctamente.",
        "nombre": empleado["nombre"],
        "tipo": tipo,
    })


@app.route("/registro-dispositivo")
def registro_dispositivo():
    """Pagina para vincular el dispositivo del empleado."""
    token_reg = request.args.get("token", "")

    emp_id = qr_manager.validar_token_registro(token_reg)
    if emp_id is None:
        return render_template("confirmacion.html",
                               exito=False,
                               mensaje="El enlace de registro es invalido o ha expirado. Solicita uno nuevo al administrador.")

    empleado = database.obtener_empleado(emp_id)
    if not empleado:
        return render_template("confirmacion.html",
                               exito=False,
                               mensaje="Empleado no encontrado.")

    return render_template("registro_dispositivo.html",
                           empleado=empleado,
                           token_reg=token_reg)


@app.route("/api/registro-dispositivo", methods=["POST"])
def api_registro_dispositivo():
    """Endpoint API para vincular un dispositivo."""
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

    # Generar token de dispositivo
    token_dispositivo = qr_manager.generar_token_dispositivo(emp_id)
    database.vincular_dispositivo(emp_id, token_dispositivo)

    return jsonify({
        "ok": True,
        "mensaje": f"Dispositivo vinculado correctamente para {empleado['nombre']}.",
        "token_dispositivo": token_dispositivo,
        "nombre": empleado["nombre"],
    })


def run_server():
    """Inicia el servidor Flask."""
    app.run(host=SERVER_HOST, port=SERVER_PORT, debug=False, use_reloader=False)
