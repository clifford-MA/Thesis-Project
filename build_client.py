import PyInstaller.__main__
import sys
import os

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

PyInstaller.__main__.run([
    'app/login.py',                 # your real entry file
    '--name=HospitalServer',
    '--onefile',
    '--windowed',                   # important for Tkinter (no black terminal)
    '--add-data=assets;assets',
    '--add-data=database;database',
    '--hidden-import=tkinter',
    '--hidden-import=sqlite3',
])