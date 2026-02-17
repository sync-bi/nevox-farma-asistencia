"""
Panel de administracion. Gestion de empleados, vinculacion de dispositivos y configuracion.
Tema claro profesional - Paleta: Naranja #ea8511, Negro #1d120e, Gris #afaeb3
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from PIL import Image, ImageTk

import database
import qr_manager
from web_server import SERVER_PORT

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


class AdminPanel(tk.Toplevel):
    def __init__(self, parent, local_ip):
        super().__init__(parent)
        self.local_ip = local_ip
        self.title("Administracion - NEVOX FARMA")
        self.geometry("960x680")
        self.minsize(800, 550)
        self.configure(bg=BLANCO)
        self.transient(parent)

        if not self._autenticar():
            self.destroy()
            return

        self._build_ui()
        self._cargar_empleados()

    def _autenticar(self):
        password = simpledialog.askstring("Acceso Administrador",
                                           "Ingresa la contrasena de administrador:",
                                           show="*", parent=self)
        if password is None:
            return False
        if not database.verificar_password_admin(password):
            messagebox.showerror("Error", "Contrasena incorrecta.", parent=self)
            return False
        return True

    def _build_ui(self):
        # Brand bar
        tk.Frame(self, bg=NARANJA, height=4).pack(fill=tk.X)

        # Header
        header = tk.Frame(self, bg=BLANCO, padx=24, pady=16)
        header.pack(fill=tk.X)
        tk.Label(header, text="Panel de Administracion", bg=BLANCO, fg=NEGRO,
                  font=("Segoe UI", 18, "bold")).pack(side=tk.LEFT)

        tk.Frame(self, bg=GRIS_BORDER, height=1).pack(fill=tk.X)

        # Notebook
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=24, pady=(12, 24))

        self.emp_frame = tk.Frame(self.notebook, bg=BLANCO)
        self.notebook.add(self.emp_frame, text="  Empleados  ")
        self._build_empleados_tab()

        self.config_frame = tk.Frame(self.notebook, bg=BLANCO)
        self.notebook.add(self.config_frame, text="  Configuracion  ")
        self._build_config_tab()

    def _build_empleados_tab(self):
        toolbar = tk.Frame(self.emp_frame, bg=GRIS_BG, padx=10, pady=8)
        toolbar.pack(fill=tk.X, pady=(0, 0))

        ttk.Button(toolbar, text="+ Nuevo Empleado", command=self._nuevo_empleado,
                    style="Accent.TButton").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(toolbar, text="Editar", command=self._editar_empleado,
                    style="Secondary.TButton").pack(side=tk.LEFT, padx=3)
        ttk.Button(toolbar, text="Activar / Desactivar", command=self._toggle_activo,
                    style="Secondary.TButton").pack(side=tk.LEFT, padx=3)
        ttk.Button(toolbar, text="QR Registro", command=self._mostrar_qr_registro,
                    style="Secondary.TButton").pack(side=tk.LEFT, padx=3)
        ttk.Button(toolbar, text="Desvincular", command=self._desvincular,
                    style="Secondary.TButton").pack(side=tk.LEFT, padx=3)
        ttk.Button(toolbar, text="Actualizar", command=self._cargar_empleados,
                    style="Secondary.TButton").pack(side=tk.RIGHT)

        # Treeview
        tree_frame = tk.Frame(self.emp_frame, bg=BLANCO)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("id", "nombre", "departamento", "hora_entrada", "hora_salida", "dispositivo", "activo")
        self.emp_tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="browse")
        self.emp_tree.heading("id", text="ID")
        self.emp_tree.heading("nombre", text="NOMBRE")
        self.emp_tree.heading("departamento", text="DEPARTAMENTO")
        self.emp_tree.heading("hora_entrada", text="H. ENTRADA")
        self.emp_tree.heading("hora_salida", text="H. SALIDA")
        self.emp_tree.heading("dispositivo", text="DISPOSITIVO")
        self.emp_tree.heading("activo", text="ACTIVO")
        self.emp_tree.column("id", width=40, anchor="center")
        self.emp_tree.column("nombre", width=180)
        self.emp_tree.column("departamento", width=130)
        self.emp_tree.column("hora_entrada", width=85, anchor="center")
        self.emp_tree.column("hora_salida", width=85, anchor="center")
        self.emp_tree.column("dispositivo", width=100, anchor="center")
        self.emp_tree.column("activo", width=60, anchor="center")

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.emp_tree.yview)
        self.emp_tree.configure(yscrollcommand=scrollbar.set)
        self.emp_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def _cargar_empleados(self):
        for item in self.emp_tree.get_children():
            self.emp_tree.delete(item)

        empleados = database.listar_empleados(solo_activos=False)
        for emp in empleados:
            disp = "Vinculado" if emp["token_dispositivo"] else "\u2014"
            activo = "Si" if emp["activo"] else "No"
            tag = "activo" if emp["activo"] else "inactivo"
            self.emp_tree.insert("", tk.END, values=(
                emp["id"], emp["nombre"], emp["departamento"],
                emp["hora_entrada"], emp["hora_salida"], disp, activo
            ), tags=(tag,))

        self.emp_tree.tag_configure("activo", foreground=TEXTO)
        self.emp_tree.tag_configure("inactivo", foreground=GRIS)

    def _get_selected_id(self):
        sel = self.emp_tree.selection()
        if not sel:
            messagebox.showwarning("Atencion", "Selecciona un empleado.", parent=self)
            return None
        return self.emp_tree.item(sel[0])["values"][0]

    def _nuevo_empleado(self):
        dialog = EmpleadoDialog(self, "Nuevo Empleado")
        self.wait_window(dialog)
        if dialog.resultado:
            d = dialog.resultado
            database.crear_empleado(d["nombre"], d["departamento"], d["hora_entrada"], d["hora_salida"])
            self._cargar_empleados()

    def _editar_empleado(self):
        emp_id = self._get_selected_id()
        if emp_id is None:
            return
        emp = database.obtener_empleado(emp_id)
        dialog = EmpleadoDialog(self, "Editar Empleado", emp)
        self.wait_window(dialog)
        if dialog.resultado:
            d = dialog.resultado
            database.actualizar_empleado(emp_id, nombre=d["nombre"], departamento=d["departamento"],
                                          hora_entrada=d["hora_entrada"], hora_salida=d["hora_salida"])
            self._cargar_empleados()

    def _toggle_activo(self):
        emp_id = self._get_selected_id()
        if emp_id is None:
            return
        emp = database.obtener_empleado(emp_id)
        nuevo_estado = 0 if emp["activo"] else 1
        accion = "desactivar" if emp["activo"] else "activar"
        if messagebox.askyesno("Confirmar", f"Deseas {accion} a {emp['nombre']}?", parent=self):
            database.actualizar_empleado(emp_id, activo=nuevo_estado)
            self._cargar_empleados()

    def _mostrar_qr_registro(self):
        emp_id = self._get_selected_id()
        if emp_id is None:
            return
        emp = database.obtener_empleado(emp_id)

        url = qr_manager.generar_qr_registro_url(self.local_ip, SERVER_PORT, emp_id)
        img = qr_manager.generar_qr_image(url, size=8)
        img = img.resize((300, 300), Image.NEAREST)

        qr_win = tk.Toplevel(self)
        qr_win.title(f"QR de Registro - {emp['nombre']}")
        qr_win.geometry("400x500")
        qr_win.configure(bg=BLANCO)
        qr_win.transient(self)

        tk.Frame(qr_win, bg=NARANJA, height=4).pack(fill=tk.X)

        tk.Label(qr_win, text="QR de Registro", bg=BLANCO, fg=GRIS,
                  font=("Segoe UI", 11)).pack(pady=(20, 4))
        tk.Label(qr_win, text=emp["nombre"], bg=BLANCO, fg=NEGRO,
                  font=("Segoe UI", 18, "bold")).pack(pady=(0, 16))

        qr_outer = tk.Frame(qr_win, bg=GRIS_BORDER, padx=1, pady=1)
        qr_outer.pack()
        qr_inner = tk.Frame(qr_outer, bg=BLANCO, padx=10, pady=10)
        qr_inner.pack()

        photo = ImageTk.PhotoImage(img)
        qr_label = tk.Label(qr_inner, image=photo, bg=BLANCO)
        qr_label.image = photo
        qr_label.pack()

        tk.Label(qr_win, text="El empleado debe escanear este QR\ncon su celular para vincular su dispositivo.",
                  bg=BLANCO, fg=TEXTO_SEC, font=("Segoe UI", 10), justify=tk.CENTER).pack(pady=(16, 20))

    def _desvincular(self):
        emp_id = self._get_selected_id()
        if emp_id is None:
            return
        emp = database.obtener_empleado(emp_id)
        if not emp["token_dispositivo"]:
            messagebox.showinfo("Info", "Este empleado no tiene un dispositivo vinculado.", parent=self)
            return
        if messagebox.askyesno("Confirmar",
                                f"Desvincular el dispositivo de {emp['nombre']}?\n"
                                "Tendra que volver a escanear un QR de registro.",
                                parent=self):
            database.desvincular_dispositivo(emp_id)
            self._cargar_empleados()

    def _build_config_tab(self):
        frame = tk.Frame(self.config_frame, bg=BLANCO, padx=32, pady=32)
        frame.pack(fill=tk.BOTH, expand=True)

        lbl_kw = {"bg": BLANCO, "fg": TEXTO_SEC, "font": ("Segoe UI", 11), "anchor": "w"}
        entry_kw = {"font": ("Segoe UI", 11), "bg": BLANCO, "fg": TEXTO,
                      "insertbackground": NARANJA, "relief": "flat", "highlightthickness": 1,
                      "highlightbackground": GRIS_BORDER, "highlightcolor": NARANJA}

        tk.Label(frame, text="Nombre de la empresa:", **lbl_kw).grid(row=0, column=0, sticky="w", pady=10)
        self.var_empresa = tk.StringVar(value=database.get_config("nombre_empresa") or "NEVOX FARMA")
        tk.Entry(frame, textvariable=self.var_empresa, width=30, **entry_kw).grid(row=0, column=1, pady=10, padx=(12, 0))

        tk.Label(frame, text="Tolerancia de retardo (min):", **lbl_kw).grid(row=1, column=0, sticky="w", pady=10)
        self.var_tolerancia = tk.StringVar(value=database.get_config("tolerancia_minutos") or "15")
        tk.Entry(frame, textvariable=self.var_tolerancia, width=10, **entry_kw).grid(row=1, column=1, pady=10, padx=(12, 0), sticky="w")

        tk.Frame(frame, bg=GRIS_BORDER, height=1).grid(row=2, column=0, columnspan=2, sticky="ew", pady=16)

        tk.Label(frame, text="Nueva contrasena admin:", **lbl_kw).grid(row=3, column=0, sticky="w", pady=10)
        self.var_new_pass = tk.StringVar()
        tk.Entry(frame, textvariable=self.var_new_pass, show="\u2022", width=30, **entry_kw).grid(row=3, column=1, pady=10, padx=(12, 0))

        tk.Label(frame, text="Confirmar contrasena:", **lbl_kw).grid(row=4, column=0, sticky="w", pady=10)
        self.var_confirm_pass = tk.StringVar()
        tk.Entry(frame, textvariable=self.var_confirm_pass, show="\u2022", width=30, **entry_kw).grid(row=4, column=1, pady=10, padx=(12, 0))

        ttk.Button(frame, text="Guardar Configuracion", command=self._guardar_config,
                    style="Accent.TButton").grid(row=5, column=0, columnspan=2, pady=28)

        # Info servidor
        info_frame = tk.Frame(frame, bg=GRIS_BG, padx=16, pady=14,
                               highlightbackground=GRIS_BORDER, highlightthickness=1)
        info_frame.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        tk.Label(info_frame, text=f"IP del servidor:  {self.local_ip}",
                  bg=GRIS_BG, fg=TEXTO_SEC, font=("Segoe UI", 10)).pack(anchor="w")
        tk.Label(info_frame, text=f"Puerto:  {SERVER_PORT}",
                  bg=GRIS_BG, fg=TEXTO_SEC, font=("Segoe UI", 10)).pack(anchor="w")
        tk.Label(info_frame, text="Los celulares deben estar en la misma red WiFi.",
                  bg=GRIS_BG, fg=NARANJA, font=("Segoe UI", 10)).pack(anchor="w", pady=(8, 0))

        # --- Seccion Limpiar Base de Datos ---
        tk.Frame(frame, bg=GRIS_BORDER, height=1).grid(row=7, column=0, columnspan=2, sticky="ew", pady=(20, 8))

        tk.Label(frame, text="Limpiar Base de Datos", bg=BLANCO, fg="#dc2626",
                  font=("Segoe UI", 12, "bold")).grid(row=8, column=0, columnspan=2, sticky="w", pady=(4, 8))

        btn_limpiar_frame = tk.Frame(frame, bg=BLANCO)
        btn_limpiar_frame.grid(row=9, column=0, columnspan=2, sticky="w")

        ttk.Button(btn_limpiar_frame, text="Eliminar Registros",
                    command=self._limpiar_registros,
                    style="Secondary.TButton").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_limpiar_frame, text="Eliminar Registros y Empleados",
                    command=self._limpiar_registros_y_empleados,
                    style="Secondary.TButton").pack(side=tk.LEFT)

    def _limpiar_registros(self):
        if not messagebox.askyesno("Confirmar",
                "Se eliminaran TODOS los registros de entradas y salidas.\n\n"
                "Los empleados se mantendran.\n\n"
                "Esta accion no se puede deshacer. Continuar?",
                parent=self):
            return
        database.limpiar_registros()
        messagebox.showinfo("Exito", "Todos los registros fueron eliminados.", parent=self)

    def _limpiar_registros_y_empleados(self):
        if not messagebox.askyesno("Confirmar",
                "Se eliminaran TODOS los registros y TODOS los empleados.\n\n"
                "Solo se mantendra la configuracion del sistema.\n\n"
                "Esta accion no se puede deshacer. Continuar?",
                parent=self):
            return
        database.limpiar_registros_y_empleados()
        self._cargar_empleados()
        messagebox.showinfo("Exito", "Registros y empleados fueron eliminados.", parent=self)

    def _guardar_config(self):
        database.set_config("nombre_empresa", self.var_empresa.get())

        try:
            tol = int(self.var_tolerancia.get())
            if tol < 0:
                raise ValueError
            database.set_config("tolerancia_minutos", str(tol))
        except ValueError:
            messagebox.showerror("Error", "La tolerancia debe ser un numero positivo.", parent=self)
            return

        new_pass = self.var_new_pass.get()
        if new_pass:
            if new_pass != self.var_confirm_pass.get():
                messagebox.showerror("Error", "Las contrasenas no coinciden.", parent=self)
                return
            if len(new_pass) < 4:
                messagebox.showerror("Error", "La contrasena debe tener al menos 4 caracteres.", parent=self)
                return
            database.cambiar_password_admin(new_pass)

        self.var_new_pass.set("")
        self.var_confirm_pass.set("")
        messagebox.showinfo("Exito", "Configuracion guardada correctamente.", parent=self)


class EmpleadoDialog(tk.Toplevel):

    def __init__(self, parent, titulo, empleado=None):
        super().__init__(parent)
        self.title(titulo)
        self.geometry("440x340")
        self.configure(bg=BLANCO)
        self.transient(parent)
        self.grab_set()
        self.resultado = None

        tk.Frame(self, bg=NARANJA, height=4).pack(fill=tk.X)

        tk.Label(self, text=titulo, bg=BLANCO, fg=NEGRO,
                  font=("Segoe UI", 14, "bold")).pack(pady=(16, 4))

        tk.Frame(self, bg=GRIS_BORDER, height=1).pack(fill=tk.X, padx=28, pady=(0, 12))

        frame = tk.Frame(self, bg=BLANCO, padx=28, pady=4)
        frame.pack(fill=tk.BOTH, expand=True)

        lbl_kw = {"bg": BLANCO, "fg": TEXTO_SEC, "font": ("Segoe UI", 11), "anchor": "w"}
        entry_kw = {"font": ("Segoe UI", 11), "bg": BLANCO, "fg": TEXTO,
                      "insertbackground": NARANJA, "relief": "flat", "highlightthickness": 1,
                      "highlightbackground": GRIS_BORDER, "highlightcolor": NARANJA}

        tk.Label(frame, text="Nombre:", **lbl_kw).grid(row=0, column=0, sticky="w", pady=6)
        self.var_nombre = tk.StringVar(value=empleado["nombre"] if empleado else "")
        tk.Entry(frame, textvariable=self.var_nombre, width=26, **entry_kw).grid(row=0, column=1, pady=6, padx=(8, 0))

        tk.Label(frame, text="Departamento:", **lbl_kw).grid(row=1, column=0, sticky="w", pady=6)
        self.var_depto = tk.StringVar(value=empleado["departamento"] if empleado else "")
        tk.Entry(frame, textvariable=self.var_depto, width=26, **entry_kw).grid(row=1, column=1, pady=6, padx=(8, 0))

        tk.Label(frame, text="Hora Entrada:", **lbl_kw).grid(row=2, column=0, sticky="w", pady=6)
        self.var_he = tk.StringVar(value=empleado["hora_entrada"] if empleado else "09:00")
        tk.Entry(frame, textvariable=self.var_he, width=10, **entry_kw).grid(row=2, column=1, pady=6, padx=(8, 0), sticky="w")

        tk.Label(frame, text="Hora Salida:", **lbl_kw).grid(row=3, column=0, sticky="w", pady=6)
        self.var_hs = tk.StringVar(value=empleado["hora_salida"] if empleado else "18:00")
        tk.Entry(frame, textvariable=self.var_hs, width=10, **entry_kw).grid(row=3, column=1, pady=6, padx=(8, 0), sticky="w")

        btn_frame = tk.Frame(frame, bg=BLANCO)
        btn_frame.grid(row=4, column=0, columnspan=2, pady=16)

        ttk.Button(btn_frame, text="Guardar", command=self._guardar,
                    style="Accent.TButton").pack(side=tk.LEFT, padx=6)
        ttk.Button(btn_frame, text="Cancelar", command=self.destroy,
                    style="Secondary.TButton").pack(side=tk.LEFT, padx=6)

    def _guardar(self):
        nombre = self.var_nombre.get().strip()
        if not nombre:
            messagebox.showerror("Error", "El nombre es obligatorio.", parent=self)
            return
        self.resultado = {
            "nombre": nombre,
            "departamento": self.var_depto.get().strip(),
            "hora_entrada": self.var_he.get().strip(),
            "hora_salida": self.var_hs.get().strip(),
        }
        self.destroy()
