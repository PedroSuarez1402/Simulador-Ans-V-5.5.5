SAF LINK PLANNER V5.3
=====================

NOVEDADES V5.3
- Proyectos guardables localmente en data/projects/.
- Lista de proyectos trabajados en la barra lateral.
- Abrir y eliminar proyectos desde la aplicación.
- Los proyectos conservan sitios, equipos seleccionados, parámetros RF, perfil de terreno, arborización, alturas manuales, exclusiones y obstáculos.
- No se guardan las credenciales de Google Maps API ni las credenciales de Google Earth Engine.
- Exportación KMZ profesional con resumen del enlace, sitios, alturas de antena, radios, antenas, trayectoria y obstáculos importantes.

COMO USAR PROYECTOS
1. Escribe el nombre del proyecto en la barra lateral.
2. Configura sitios, radios, antenas y obstáculos.
3. Genera el perfil y realiza las modificaciones.
4. Abre "Guardar / administrar proyecto" y pulsa "Guardar proyecto".
5. El proyecto queda en data/projects/ como archivo .slp.json.
6. Para abrirlo posteriormente, selecciónalo en "Proyectos guardados" y pulsa "Abrir".

Los archivos .slp.json son archivos JSON de proyecto y pueden copiarse junto con la carpeta de la aplicación para trasladar proyectos entre instalaciones.

EXPORTACION KMZ
En la pestaña "5 · Resultado", cuando exista un perfil, aparece "Descargar KMZ del proyecto".
El KMZ contiene:
- Resumen del enlace y distancia.
- Altura de antenas A y B sobre terreno.
- Frecuencia, ancho de canal y potencia TX.
- Radio y antena de cada extremo.
- Ganancia, beamwidth, diámetro, peso, blindaje y polarización de las antenas cuando están registrados.
- Trayectoria del enlace.
- Vegetación/obstáculos importantes.
- Obstáculos manuales con tipo, distancia, altura y ancho.

IMPORTANTE
La API key de Google Maps y las credenciales de Earth Engine no se copian al proyecto por seguridad. En otro PC deben configurarse allí.
