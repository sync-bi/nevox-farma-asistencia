"""
Ventana principal del sistema. Muestra el QR rotativo y el panel de estado en tiempo real.
Tema claro profesional - Paleta: Naranja #ea8511, Negro #1d120e, Gris #afaeb3
"""

import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
from datetime import datetime

import database
import qr_manager
from web_server import get_local_ip, SERVER_PORT
from gui.admin_panel import AdminPanel
from gui.reports_panel import ReportsPanel

# --- Paleta NEVOX FARMA (tema claro) ---
NARANJA = "#ea8511"
NARANJA_HOVER = "#d47610"
NARANJA_LIGHT = "#fef7ed"
NARANJA_BORDER = "#fcd9a8"
NEGRO = "#1d120e"
TEXTO = "#1d120e"
TEXTO_SEC = "#6b6b70"
GRIS = "#afaeb3"
GRIS_BORDER = "#e0e0e2"
GRIS_BG = "#f5f5f6"
BLANCO = "#ffffff"
VERDE = "#16a34a"
VERDE_LIGHT = "#f0fdf4"
VERDE_BORDER = "#bbf7d0"
SALIDA_COLOR = "#b45309"
SALIDA_LIGHT = "#fffbeb"
SALIDA_BORDER = "#fde68a"

QR_REFRESH_MS = 5000
STATUS_REFRESH_MS = 10000


class MainWindow:
    def __init__(self, root):
        self.root = root
        self.root.title("NEVOX FARMA - Control de Asistencia")
        self.root.geometry("1150x720")
        self.root.minsize(950, 620)
        self.root.configure(bg=BLANCO)

        self.local_ip = get_local_ip()
        self._setup_styles()
        self._build_ui()
        self._refresh_qr()
        self._refresh_registros()

    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")

        style.configure(".", background=BLANCO, foreground=TEXTO, font=("Segoe UI", 10))

        # Botones
        style.configure("Accent.TButton",
                         background=NARANJA, foreground="#ffffff",
                         font=("Segoe UI", 11, "bold"),
                         padding=(20, 12), borderwidth=0, focuscolor=NARANJA)
        style.map("Accent.TButton",
                   background=[("active", NARANJA_HOVER), ("pressed", NARANJA_HOVER)])

        style.configure("Secondary.TButton",
                         background=BLANCO, foreground=TEXTO,
                         font=("Segoe UI", 10),
                         padding=(16, 10), borderwidth=1, focuscolor=GRIS_BORDER)
        style.map("Secondary.TButton",
                   background=[("active", GRIS_BG)],
                   foreground=[("active", TEXTO)])

        # Treeview
        style.configure("Treeview",
                         background=BLANCO, foreground=TEXTO,
                         fieldbackground=BLANCO,
                         font=("Segoe UI", 10), rowheight=32,
                         borderwidth=0)
        style.configure("Treeview.Heading",
                         background=GRIS_BG, foreground=TEXTO_SEC,
                         font=("Segoe UI", 9, "bold"),
                         borderwidth=0, relief="flat", padding=(8, 6))
        style.map("Treeview",
                   background=[("selected", NARANJA_LIGHT)],
                   foreground=[("selected", NEGRO)])
        style.map("Treeview.Heading",
                   background=[("active", GRIS_BORDER)])

        # Notebook
        style.configure("TNotebook", background=BLANCO, borderwidth=0)
        style.configure("TNotebook.Tab",
                         background=GRIS_BG, foreground=TEXTO_SEC,
                         font=("Segoe UI", 10),
                         padding=(18, 8), borderwidth=0)
        style.map("TNotebook.Tab",
                   background=[("selected", BLANCO), ("active", GRIS_BORDER)],
                   foreground=[("selected", NARANJA), ("active", TEXTO)])

        # Scrollbar
        style.configure("Vertical.TScrollbar",
                         background=GRIS_BG, troughcolor=BLANCO,
                         arrowcolor=GRIS, borderwidth=0, width=10)

    def _build_ui(self):
        # Barra superior naranja (brand strip)
        brand_bar = tk.Frame(self.root, bg=NARANJA, height=4)
        brand_bar.pack(fill=tk.X)

        main_frame = tk.Frame(self.root, bg=BLANCO)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=24, pady=20)

        # --- Columna izquierda: QR ---
        left_frame = tk.Frame(main_frame, bg=BLANCO, width=360)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 24))
        left_frame.pack_propagate(False)

        # Logo
        logo_frame = tk.Frame(left_frame, bg=BLANCO)
        logo_frame.pack(fill=tk.X, pady=(0, 4))
        tk.Label(logo_frame, text="NEVOX ", bg=BLANCO, fg=NEGRO,
                  font=("Segoe UI", 22, "bold")).pack(side=tk.LEFT)
        tk.Label(logo_frame, text="FARMA", bg=BLANCO, fg=NARANJA,
                  font=("Segoe UI", 22, "bold")).pack(side=tk.LEFT)

        tk.Label(left_frame, text="Control de Asistencia", bg=BLANCO, fg=GRIS,
                  font=("Segoe UI", 11)).pack(anchor="w", pady=(0, 16))

        # QR Container
        qr_outer = tk.Frame(left_frame, bg=GRIS_BORDER, padx=1, pady=1)
        qr_outer.pack(pady=(0, 8))
        qr_container = tk.Frame(qr_outer, bg=BLANCO, padx=12, pady=12)
        qr_container.pack()

        self.qr_label = tk.Label(qr_container, bg=BLANCO)
        self.qr_label.pack()

        # QR status
        self.qr_status_label = tk.Label(left_frame, text="", bg=BLANCO, fg=GRIS,
                                          font=("Segoe UI", 9))
        self.qr_status_label.pack(pady=(4, 2))

        self.ip_label = tk.Label(left_frame, text=f"Red: {self.local_ip}:{SERVER_PORT}",
                                   bg=BLANCO, fg=GRIS_BORDER, font=("Segoe UI", 8))
        self.ip_label.pack(pady=(0, 14))

        # Ultimo registro panel
        self.last_event_frame = tk.Frame(left_frame, bg=GRIS_BG, padx=14, pady=10,
                                          highlightbackground=GRIS_BORDER, highlightthickness=1)
        self.last_event_frame.pack(fill=tk.X, pady=(0, 20))

        self.last_event_title = tk.Label(self.last_event_frame, text="ULTIMO REGISTRO",
                                          bg=GRIS_BG, fg=GRIS,
                                          font=("Segoe UI", 8, "bold"), anchor="w")
        self.last_event_title.pack(fill=tk.X)

        self.last_event_label = tk.Label(self.last_event_frame, text="Esperando registros...",
                                          bg=GRIS_BG, fg=TEXTO_SEC,
                                          font=("Segoe UI", 12, "bold"), wraplength=300, anchor="w")
        self.last_event_label.pack(fill=tk.X, pady=(2, 0))

        # Botones
        btn_frame = tk.Frame(left_frame, bg=BLANCO)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)

        ttk.Button(btn_frame, text="Panel de Administracion",
                    style="Accent.TButton", command=self._abrir_admin).pack(fill=tk.X, pady=(0, 6))
        ttk.Button(btn_frame, text="Reportes",
                    style="Secondary.TButton", command=self._abrir_reportes).pack(fill=tk.X)

        # --- Columna derecha: Registros del dia ---
        right_frame = tk.Frame(main_frame, bg=BLANCO)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        header_frame = tk.Frame(right_frame, bg=BLANCO)
        header_frame.pack(fill=tk.X, pady=(0, 12))

        tk.Label(header_frame, text="Registros del dia", bg=BLANCO, fg=NEGRO,
                  font=("Segoe UI", 16, "bold")).pack(side=tk.LEFT)
        self.fecha_label = tk.Label(header_frame, text="", bg=BLANCO, fg=GRIS,
                                      font=("Segoe UI", 11))
        self.fecha_label.pack(side=tk.RIGHT)

        # Separador
        tk.Frame(right_frame, bg=GRIS_BORDER, height=1).pack(fill=tk.X, pady=(0, 0))

        # Treeview
        tree_frame = tk.Frame(right_frame, bg=BLANCO)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("hora", "nombre", "tipo", "departamento")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="none")
        self.tree.heading("hora", text="HORA")
        self.tree.heading("nombre", text="EMPLEADO")
        self.tree.heading("tipo", text="TIPO")
        self.tree.heading("departamento", text="DEPARTAMENTO")
        self.tree.column("hora", width=90, anchor="center")
        self.tree.column("nombre", width=200)
        self.tree.column("tipo", width=90, anchor="center")
        self.tree.column("departamento", width=140)

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Contador
        counter_frame = tk.Frame(right_frame, bg=GRIS_BG, padx=14, pady=8)
        counter_frame.pack(fill=tk.X, pady=(0, 0))
        self.counter_label = tk.Label(counter_frame, text="", bg=GRIS_BG, fg=TEXTO_SEC,
                                        font=("Segoe UI", 10))
        self.counter_label.pack()

    def _refresh_qr(self):
        try:
            url = qr_manager.generar_qr_rotativo_url(self.local_ip, SERVER_PORT)
            img = qr_manager.generar_qr_image(url, size=8)
            img = img.resize((280, 280), Image.NEAREST)
            self._qr_photo = ImageTk.PhotoImage(img)
            self.qr_label.configure(image=self._qr_photo)

            ahora = datetime.now()
            seg = qr_manager.QR_ROTATION_INTERVAL - (int(ahora.timestamp()) % qr_manager.QR_ROTATION_INTERVAL)
            self.qr_status_label.configure(text=f"Actualiza en {seg}s  \u2022  {ahora.strftime('%H:%M:%S')}")
        except Exception as e:
            self.qr_status_label.configure(text=f"Error QR: {e}")

        self.root.after(QR_REFRESH_MS, self._refresh_qr)

    def _refresh_registros(self):
        self._actualizar_tabla()
        self.root.after(STATUS_REFRESH_MS, self._refresh_registros)

    def _actualizar_tabla(self):
        try:
            registros = database.obtener_registros_dia()
            self.fecha_label.configure(text=datetime.now().strftime("%d/%m/%Y"))

            for item in self.tree.get_children():
                self.tree.delete(item)

            entradas = 0
            salidas = 0
            for reg in registros:
                dt = datetime.fromisoformat(reg["fecha_hora"])
                hora = dt.strftime("%H:%M:%S")
                tipo_display = reg["tipo"].upper()
                tag = "entrada" if reg["tipo"] == "entrada" else "salida"
                self.tree.insert("", tk.END,
                                  values=(hora, reg["nombre"], tipo_display, reg["departamento"]),
                                  tags=(tag,))
                if reg["tipo"] == "entrada":
                    entradas += 1
                else:
                    salidas += 1

            self.tree.tag_configure("entrada", foreground=VERDE)
            self.tree.tag_configure("salida", foreground=SALIDA_COLOR)

            self.counter_label.configure(
                text=f"Total: {len(registros)}  \u2022  Entradas: {entradas}  \u2022  Salidas: {salidas}")
        except Exception:
            pass

    def on_nuevo_registro(self, nombre, tipo):
        ahora = datetime.now().strftime("%H:%M:%S")
        tipo_texto = "ENTRADA" if tipo == "entrada" else "SALIDA"

        if tipo == "entrada":
            self.last_event_frame.configure(bg=VERDE_LIGHT, highlightbackground=VERDE_BORDER)
            self.last_event_title.configure(bg=VERDE_LIGHT, fg=VERDE)
            self.last_event_label.configure(bg=VERDE_LIGHT, fg=VERDE)
        else:
            self.last_event_frame.configure(bg=SALIDA_LIGHT, highlightbackground=SALIDA_BORDER)
            self.last_event_title.configure(bg=SALIDA_LIGHT, fg=SALIDA_COLOR)
            self.last_event_label.configure(bg=SALIDA_LIGHT, fg=SALIDA_COLOR)

        self.last_event_label.configure(text=f"{tipo_texto}  \u2022  {nombre}  \u2022  {ahora}")
        self._actualizar_tabla()

    def _abrir_admin(self):
        AdminPanel(self.root, self.local_ip)

    def _abrir_reportes(self):
        ReportsPanel(self.root)
