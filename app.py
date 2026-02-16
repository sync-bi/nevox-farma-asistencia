"""
NEVOX FARMA - Sistema de Control de Entradas y Salidas
Punto de entrada principal.

Inicia el servidor Flask en un hilo secundario y la GUI de Tkinter en el hilo principal.

Uso:
    pip install -r requirements.txt
    python app.py

Contrasena de administrador por defecto: admin123
"""

import threading
import tkinter as tk

import database
import web_server
from gui.main_window import MainWindow


def main():
    # Inicializar base de datos
    database.init_db()

    # Crear ventana principal
    root = tk.Tk()
    app = MainWindow(root)

    # Configurar callback para notificaciones en tiempo real
    def on_registro(nombre, tipo):
        root.after(0, app.on_nuevo_registro, nombre, tipo)

    web_server.set_on_registro_callback(on_registro)

    # Iniciar servidor Flask en hilo secundario
    server_thread = threading.Thread(target=web_server.run_server, daemon=True)
    server_thread.start()

    # Iniciar GUI (hilo principal)
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()


if __name__ == "__main__":
    main()
