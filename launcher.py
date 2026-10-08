import os, sys, subprocess, time, webbrowser
from pathlib import Path

BASE = Path(__file__).resolve().parent
PYTHON = BASE / '.venv' / 'Scripts' / 'python.exe'
APP = BASE / 'app.py'

if not PYTHON.exists():
    raise SystemExit(f'No se encontró Python portable: {PYTHON}')
if not APP.exists():
    raise SystemExit(f'No se encontró app.py: {APP}')

cmd = [str(PYTHON), '-m', 'streamlit', 'run', str(APP),
       '--server.headless=true', '--browser.gatherUsageStats=false',
       '--server.address=127.0.0.1', '--server.port=8501']

p = subprocess.Popen(cmd, cwd=str(BASE), creationflags=getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0))
time.sleep(2.5)
webbrowser.open('http://127.0.0.1:8501')
try:
    p.wait()
except KeyboardInterrupt:
    p.terminate()
