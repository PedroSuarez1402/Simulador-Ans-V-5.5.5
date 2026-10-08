@echo off
setlocal
cd /d "%~dp0"

echo ===============================================
echo   SAF Link Planner - Crear EXE portable
echo ===============================================
echo.

if not exist ".venv\Scripts\python.exe" (
  echo ERROR: No se encontro .venv\Scripts\python.exe
  pause
  exit /b 1
)

.venv\Scripts\python.exe -m pip install pyinstaller
if errorlevel 1 (
  echo.
  echo ERROR instalando PyInstaller.
  pause
  exit /b 1
)

.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed --name SAF_Link_Planner launcher.py
if errorlevel 1 (
  echo.
  echo ERROR creando el EXE.
  pause
  exit /b 1
)

echo.
echo ===============================================
echo EXE creado en:
echo %CD%\dist\SAF_Link_Planner.exe
echo ===============================================
pause
