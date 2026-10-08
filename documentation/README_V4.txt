SAF LINK PLANNER V4 — ARBORIZACIÓN TIPO LINKPLANNER
===================================================

OBJETIVO
--------
V4 mejora de forma importante la representación de arborización/obstáculos.
La V3 dependía principalmente de muestras GEDI dispersas y, al unirlas en el
perfil, podía producir huecos y polígonos artificiales. V4 usa como fuente
principal un modelo global de altura de copa de 10 m derivado de Sentinel-2 +
GEDI y dibuja cada tramo de vegetación como un parche independiente.

FUENTES DE DATOS
----------------
1. Terreno: Google Elevation API.
2. Arborización principal: ETH Global Canopy Height 2020, 10 m:
   users/nlang/ETH_GlobalCanopyHeight_2020_10m_v1
3. Incertidumbre opcional:
   users/nlang/ETH_GlobalCanopyHeightSD_2020_10m_v1
4. Respaldo si el modelo ETH no puede consultarse:
   LARSE/GEDI/GEDI02_A_002_MONTHLY, RH98.

NOTA SOBRE "DATOS REALES"
--------------------------
La fuente ETH es un modelo de altura de copa estimada a 10 m, entrenado con
Sentinel-2 y datos GEDI. Es mucho más denso y visualmente apropiado para un
perfil de enlace que las huellas GEDI dispersas, pero NO es un inventario en
campo de cada árbol ni representa la situación exacta de cada árbol en la
fecha de hoy. Para diseño definitivo se debe validar en campo.

CAMBIOS IMPORTANTES DE V4
--------------------------
1. Arborización continua/por parches en vez de un relleno único.
2. Se elimina el defecto visual triangular que podía aparecer en V3 cuando
   había muestras GEDI faltantes.
3. Verde = vegetación/arborización, marrón = terreno, rojo = LOS,
   azul = Fresnel 60%, gris = peor caso/K.
4. Incertidumbre de canopy opcional como línea punteada.
5. Exclusiones locales por intervalo: puedes quitar vegetación entre X y Y km.
6. Obstáculos manuales: puedes agregar árboles, edificios, postes, muros u
   otros objetos indicando distancia, altura y ancho.
7. Los obstáculos manuales se pueden desactivar o eliminar desde la tabla.
8. KML actualizado con puntos críticos y obstáculos manuales.
9. Se cambiaron llamadas antiguas use_container_width por width='stretch'.
10. Los scripts de inicio usan python -m pip para evitar problemas cuando
    Windows bloquea pip.exe mediante una directiva de Control de aplicaciones.

COMO QUITAR VEGETACIÓN
----------------------
Pestaña 3 · Arborización / edición
- En "Quitar vegetación del cálculo", agrega Inicio (km) y Fin (km).
- Pulsa "Aplicar exclusiones".
- Esto NO modifica Earth Engine; solamente excluye ese tramo del proyecto.

COMO AGREGAR UN OBSTÁCULO
-------------------------
Pestaña 3 · Arborización / edición
- En la tabla de obstáculos manuales agrega una fila.
- Nombre: por ejemplo Árbol 01.
- Tipo: Árbol / Edificio / Poste / Muro / Otro.
- Distancia desde A: posición del obstáculo en km.
- Altura sobre terreno: altura del objeto en metros.
- Ancho: ancho aproximado en metros.
- Activo: debe estar marcado para afectar el cálculo.
- Pulsa "Aplicar obstáculos manuales".

INSTALACIÓN / ACTUALIZACIÓN
---------------------------
1. Cierra la V3 anterior.
2. Extrae este ZIP en una carpeta nueva.
3. Abre PowerShell en la carpeta.
4. Crea el entorno virtual:
      python -m venv .venv
5. Si PowerShell bloquea la activación:
      Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
      .\.venv\Scripts\Activate.ps1
6. Instala dependencias:
      python -m pip install -r requirements.txt
7. Autentica Earth Engine si no está autenticado:
      earthengine authenticate
8. Configura el proyecto:
      earthengine set_project saf-link-planner
9. Ejecuta:
      python -m streamlit run app.py

GOOGLE ELEVATION
----------------
La aplicación necesita una Google Maps Platform API Key con Elevation API
habilitada. Se introduce en la barra lateral y no se guarda en el proyecto.

PROYECTO GOOGLE EARTH ENGINE
----------------------------
El valor recomendado para este proyecto es:
      saf-link-planner

DIFERENCIA V3 vs V4
-------------------
V3: perfil de terreno + puntos/muestras GEDI. GEDI tiene huellas de unos 25 m
y muestreo espacial a lo largo de las órbitas; no cubre cada píxel del camino.
Esto puede dejar grandes huecos en un perfil de enlace.

V4: perfil de terreno + modelo de altura de copa ETH a 10 m, que fue producido
fusionando Sentinel-2 y GEDI. Por ello la arborización puede verse como una
superficie mucho más continua y parecida al concepto de clutter/vegetación
que se observa en LINKPlanner.

LICENCIA / ATRIBUCIÓN
---------------------
El producto ETH Global Canopy Height 2020 está publicado con licencia
Creative Commons Attribution 4.0. Debe conservarse la atribución al producto
y a su publicación científica.
