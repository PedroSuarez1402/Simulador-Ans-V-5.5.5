SAF LINK PLANNER - VERSION PORTABLE

Esta carpeta contiene el entorno Python (.venv) necesario para ejecutar la aplicacion.

PRUEBA RAPIDA:
1. Doble clic en INICIAR_SAF_LINK_PLANNER.bat
2. Se abrira el navegador en http://127.0.0.1:8501

CREAR EXE:
1. En este mismo PC, con Internet disponible, doble clic en BUILD_PORTABLE_EXE.bat
2. Se instalara PyInstaller dentro del entorno local.
3. El EXE quedara en la carpeta dist:
   dist\SAF_Link_Planner.exe

IMPORTANTE:
El EXE es un lanzador. Para que sea portable y conserve Earth Engine y las dependencias,
se debe copiar junto con la carpeta .venv y app.py. La carpeta completa se puede copiar
a otro PC Windows de 64 bits.
