"""
Modulo de gestion de QR rotativos y tokens criptograficos.
Implementa las 3 capas de seguridad: QR rotativo, vinculacion de dispositivo, tokens firmados.
"""

import hmac
import hashlib
import secrets
import time
import io
import qrcode
from PIL import Image

import database

# Intervalo de rotacion del QR en segundos
QR_ROTATION_INTERVAL = 30


def _get_secret_key():
    return database.get_config("secret_key")


def generar_token_qr():
    """Genera un token QR basado en el tiempo actual. Valido por QR_ROTATION_INTERVAL segundos."""
    secret = _get_secret_key()
    slot = int(time.time()) // QR_ROTATION_INTERVAL
    mensaje = f"qr:{slot}".encode()
    firma = hmac.new(secret.encode(), mensaje, hashlib.sha256).hexdigest()
    return f"{slot}:{firma}"


def validar_token_qr(token):
    """Valida que un token QR sea reciente (slot actual o anterior)."""
    try:
        slot_str, firma = token.split(":")
        slot_recibido = int(slot_str)
    except (ValueError, AttributeError):
        return False

    secret = _get_secret_key()
    slot_actual = int(time.time()) // QR_ROTATION_INTERVAL

    # Aceptar el slot actual y el anterior (para evitar problemas de timing)
    for slot in [slot_actual, slot_actual - 1]:
        mensaje = f"qr:{slot}".encode()
        firma_esperada = hmac.new(secret.encode(), mensaje, hashlib.sha256).hexdigest()
        if slot == slot_recibido and hmac.compare_digest(firma, firma_esperada):
            return True
    return False


def generar_token_dispositivo(empleado_id):
    """Genera un token unico para vincular un dispositivo a un empleado."""
    secret = _get_secret_key()
    aleatorio = secrets.token_hex(16)
    mensaje = f"device:{empleado_id}:{aleatorio}".encode()
    firma = hmac.new(secret.encode(), mensaje, hashlib.sha256).hexdigest()
    return f"dev:{empleado_id}:{aleatorio}:{firma}"


def validar_token_dispositivo(token):
    """Valida la integridad de un token de dispositivo. Retorna empleado_id o None."""
    try:
        prefix, emp_id, aleatorio, firma = token.split(":")
        if prefix != "dev":
            return None
    except (ValueError, AttributeError):
        return None

    secret = _get_secret_key()
    mensaje = f"device:{emp_id}:{aleatorio}".encode()
    firma_esperada = hmac.new(secret.encode(), mensaje, hashlib.sha256).hexdigest()

    if hmac.compare_digest(firma, firma_esperada):
        return int(emp_id)
    return None


def generar_token_registro(empleado_id):
    """
    Genera un token unico de registro para vincular el dispositivo de un empleado.
    Este token se incluye en un QR que el empleado escanea una sola vez.
    """
    secret = _get_secret_key()
    aleatorio = secrets.token_hex(16)
    mensaje = f"reg:{empleado_id}:{aleatorio}".encode()
    firma = hmac.new(secret.encode(), mensaje, hashlib.sha256).hexdigest()
    return f"reg:{empleado_id}:{aleatorio}:{firma}"


def validar_token_registro(token):
    """Valida un token de registro. Retorna empleado_id o None."""
    try:
        prefix, emp_id, aleatorio, firma = token.split(":")
        if prefix != "reg":
            return None
    except (ValueError, AttributeError):
        return None

    secret = _get_secret_key()
    mensaje = f"reg:{emp_id}:{aleatorio}".encode()
    firma_esperada = hmac.new(secret.encode(), mensaje, hashlib.sha256).hexdigest()

    if hmac.compare_digest(firma, firma_esperada):
        return int(emp_id)
    return None


def generar_qr_image(data, size=10):
    """Genera una imagen PIL de un codigo QR con los datos proporcionados."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=size,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("RGB")


def generar_qr_rotativo_url(server_host, server_port):
    """Genera la URL completa que se codifica en el QR rotativo."""
    token = generar_token_qr()
    return f"http://{server_host}:{server_port}/checkin?token={token}"


def generar_qr_registro_url(server_host, server_port, empleado_id):
    """Genera la URL para el QR de registro de dispositivo de un empleado."""
    token = generar_token_registro(empleado_id)
    return f"http://{server_host}:{server_port}/registro-dispositivo?token={token}"
