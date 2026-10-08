@echo off
cd /d "%~dp0"
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo ERROR: No se encontro .venv\Scripts\python.exe
  pause
  exit /b 1
)

echo Verificando dependencias...
%PY% -c "import pypdf" >nul 2>&1
if errorlevel 1 (
  echo Instalando pypdf para lectura de datasheets PDF...
  %PY% -m pip install "pypdf>=5,<7"
  if errorlevel 1 (
    echo ERROR instalando pypdf.
    echo Intente ejecutar este archivo con conexion a Internet.
    pause
    exit /b 1
  )
)

%PY% -m streamlit run app.py
pause
