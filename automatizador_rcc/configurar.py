"""Formulario local. Las credenciales no pasan por SIGAP ni por argumentos CLI."""
import tkinter as tk
from tkinter import messagebox
from urllib.parse import urlsplit
from rcc_vault import load, save


def main():
    root = tk.Tk()
    root.title('Configurar SIGAP RCC')
    root.resizable(False, False)
    try:
        old = load()
    except (OSError, RuntimeError):
        old = {}
    fields = {}
    for index, (key, label, value) in enumerate([
        ('sigap_url', 'URL de SIGAP (incluido /Sigap o /SigapTesting)', old.get('sigap_url', '')),
        ('usuario', 'Usuario RCC', old.get('usuario', '')),
        ('password', 'Contrasena RCC', '')]):
        tk.Label(root, text=label).grid(row=index * 2, column=0, padx=16, pady=(12, 0), sticky='w')
        entry = tk.Entry(root, width=64, show='*' if key == 'password' else '')
        entry.insert(0, value)
        entry.grid(row=index * 2 + 1, column=0, padx=16, sticky='ew')
        fields[key] = entry

    def guardar():
        data = {k: v.get().strip() if k != 'password' else v.get() for k, v in fields.items()}
        u = urlsplit(data['sigap_url'])
        if u.scheme not in ('http', 'https') or not u.hostname or u.username or u.query or u.fragment:
            messagebox.showerror('Configuracion', 'Ingrese la URL completa de su SIGAP.'); return
        data['sigap_url'] = data['sigap_url'].rstrip('/')
        data['password'] = data['password'] or old.get('password', '')
        if not data['usuario'] or not data['password']:
            messagebox.showerror('Configuracion', 'Complete usuario y contrasena RCC.'); return
        try:
            save(data)
        except Exception:
            messagebox.showerror('Configuracion', 'No se pudo guardar la configuracion protegida.'); return
        messagebox.showinfo('Configuracion', 'Guardada para esta cuenta Windows. Inicie o reinicie el automatizador.')
        root.destroy()

    tk.Label(root, text='Contrasena vacia conserva la anterior. Nunca se envia a SIGAP.').grid(row=6, column=0, padx=16, pady=12)
    tk.Button(root, text='Guardar', command=guardar).grid(row=7, column=0, pady=(0, 16))
    root.mainloop()


if __name__ == '__main__':
    main()
