@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Creando entorno virtual...
  python -m venv .venv
  if errorlevel 1 pause & exit /b 1
  echo Instalando dependencias...
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  if errorlevel 1 pause & exit /b 1
)
.venv\Scripts\python.exe -m streamlit run app.py
pause
