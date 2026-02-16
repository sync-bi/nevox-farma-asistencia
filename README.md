# NEVOX FARMA - Sistema de Control de Entradas y Salidas

Sistema de registro de asistencia con QR dinámico para la empresa NEVOX FARMA (20-50 empleados). Garantiza que nadie pueda marcar asistencia por otra persona mediante 3 capas de seguridad.

---

## Seguridad (Anti-suplantación)

| Capa | Mecanismo | Descripción |
|------|-----------|-------------|
| 1 | **QR Rotativo** | Cambia cada 30 segundos. Necesitas estar físicamente frente a la pantalla. |
| 2 | **Vinculación de Dispositivo** | Cada empleado registra su celular UNA sola vez. Solo ESE celular puede registrar a ESE empleado. |
| 3 | **Token Criptográfico** | Tokens firmados con HMAC-SHA256. No se pueden falsificar ni reutilizar. |

**Resultado:** Para marcar asistencia necesitas: (a) estar presente físicamente, (b) tener el celular registrado del empleado.

---

## Requisitos

- **Python 3.10+**
- **Windows** (Tkinter incluido)
- Los celulares deben estar en la **misma red WiFi** que la PC

## Instalación

```bash
pip install -r requirements.txt
```

Dependencias: Flask, qrcode, Pillow, openpyxl

## Ejecución

```bash
python app.py
```

La aplicación inicia:
- **Servidor Flask** en el puerto 5000 (hilo secundario)
- **Ventana Tkinter** con el QR rotativo (hilo principal)

**Contraseña de administrador por defecto:** `admin123`

---

## Flujo de Uso

### 1. Registro Inicial del Empleado (una sola vez)
1. Admin abre **Panel de Administración** → ingresa contraseña
2. Clic en **+ Nuevo Empleado** → llena nombre, departamento, horarios
3. Selecciona el empleado → clic en **QR Registro**
4. El empleado escanea ese QR con su celular
5. Se abre una página web → clic en **"Vincular este dispositivo"**
6. El celular queda vinculado permanentemente a ese empleado

### 2. Registro Diario de Entrada/Salida
1. La PC muestra un **QR que cambia cada 30 segundos**
2. El empleado escanea el QR con la cámara de su celular
3. El sistema **identifica automáticamente** al empleado por el token del dispositivo
4. Registra **entrada** o **salida** (alterna automáticamente)
5. La pantalla de la PC muestra confirmación en tiempo real

---

## Estructura de Archivos

```
Sistema de entradas y salidas/
├── app.py                    # Punto de entrada principal
├── database.py               # Base de datos SQLite y operaciones CRUD
├── qr_manager.py             # QR rotativos y tokens criptográficos (HMAC-SHA256)
├── web_server.py             # Servidor Flask (puerto 5000)
├── requirements.txt          # Dependencias Python
├── .gitignore
│
├── gui/
│   ├── __init__.py
│   ├── main_window.py        # Ventana principal: QR + registros en vivo
│   ├── admin_panel.py        # Gestión de empleados y configuración
│   └── reports_panel.py      # Reportes: horas, retardos, exportar Excel
│
├── templates/
│   ├── checkin.html           # Página móvil de entrada/salida
│   ├── registro_dispositivo.html  # Página de vinculación de celular
│   └── confirmacion.html     # Página de mensajes
│
└── data/                     # Base de datos y exports (ignorado por git)
    └── nevox_farma.db        # SQLite (se crea automáticamente)
```

---

## Módulos

### `app.py`
Punto de entrada. Inicializa la base de datos, lanza Flask en un hilo daemon y ejecuta la GUI Tkinter en el hilo principal.

### `database.py`
Maneja SQLite con 3 tablas:

| Tabla | Campos principales |
|-------|-------------------|
| `empleados` | id, nombre, departamento, hora_entrada, hora_salida, token_dispositivo, activo |
| `registros` | id, empleado_id, tipo (entrada/salida), fecha_hora, token_usado |
| `configuracion` | clave, valor (admin_password, secret_key, tolerancia_minutos, etc.) |

Funciones principales:
- `crear_empleado()`, `actualizar_empleado()`, `listar_empleados()`
- `registrar_asistencia()`, `obtener_siguiente_tipo()` (alterna entrada/salida)
- `calcular_horas_trabajadas()`, `obtener_retardos()`
- `verificar_password_admin()`, `cambiar_password_admin()`

### `qr_manager.py`
Gestión de tokens criptográficos:

- **`generar_token_qr()`** → Token basado en time-slot de 30s, firmado con HMAC-SHA256
- **`validar_token_qr()`** → Acepta slot actual y anterior (tolerancia de timing)
- **`generar_token_dispositivo()`** → Token único por empleado para vincular celular
- **`generar_token_registro()`** → Token de un solo uso para el QR de vinculación
- **`generar_qr_image()`** → Genera imagen PIL del código QR

### `web_server.py`
Servidor Flask con las rutas:

| Ruta | Método | Descripción |
|------|--------|-------------|
| `/checkin` | GET | Página que se abre al escanear el QR rotativo |
| `/api/checkin` | POST | Registra entrada/salida (valida token QR + token dispositivo) |
| `/registro-dispositivo` | GET | Página de vinculación de celular |
| `/api/registro-dispositivo` | POST | Vincula dispositivo y retorna token |

### `gui/main_window.py`
Ventana principal con:
- QR rotativo (se actualiza cada 5 segundos)
- Panel "Último registro" en tiempo real (cambia color: verde entrada, amarillo salida)
- Tabla de registros del día con contador
- Botones de acceso a Admin y Reportes

### `gui/admin_panel.py`
Panel protegido con contraseña:
- **Tab Empleados**: Crear, editar, activar/desactivar, generar QR de registro, desvincular dispositivo
- **Tab Configuración**: Nombre empresa, tolerancia de retardo, cambiar contraseña admin

### `gui/reports_panel.py`
3 reportes con filtros de fecha:
- **Horas Trabajadas**: Total de horas por empleado en rango de fechas
- **Retardos**: Empleados que llegaron después de su hora programada (con/sin tolerancia)
- **Exportar a Excel**: Genera .xlsx con registros detallados + hoja resumen de horas

---

## Paleta de Colores

| Color | Hex | Uso |
|-------|-----|-----|
| Naranja | `#ea8511` | Botones principales, barra brand, acentos |
| Negro | `#1d120e` | Texto principal, títulos |
| Gris | `#afaeb3` | Texto secundario, subtítulos |
| Blanco | `#ffffff` | Fondo principal |
| Gris claro | `#f5f5f6` | Toolbars, fondos secundarios |
| Gris borde | `#e0e0e2` | Bordes, separadores |

---

## Base de Datos

La base de datos SQLite se crea automáticamente en `data/nevox_farma.db` al primer inicio.

**Valores por defecto:**
- Contraseña admin: `admin123` (hash SHA-256)
- Tolerancia de retardo: 15 minutos
- Clave secreta: generada aleatoriamente (32 bytes hex)

---

## Notas Importantes

- La PC y los celulares deben estar en la **misma red WiFi**
- El token del dispositivo se guarda en `localStorage` del navegador del celular
- Si un empleado cambia de celular, el admin debe **desvincular** y generar un nuevo QR de registro
- El QR rotativo tiene validez de 30-60 segundos (acepta slot actual y anterior)
- La base de datos usa WAL mode para permitir lecturas concurrentes desde Flask y Tkinter

---

## Pendiente: Subir a GitHub

El repositorio git ya está inicializado con el commit inicial. Para subir a GitHub:

```bash
gh auth login
gh repo create nevox-farma-asistencia --private --source=. --push
```
