# Agent: 01_gis_pipeline

## Role & Responsibilities
Responsable exclusivo de la ingesta de datos brutos (Catastro GML/Shapefile y OpenStreetMap XML), transformación de sistemas de coordenadas (CRS), fusión de huellas de edificios y trazado de viales, y generación de la malla 3D exportada a `data/export/almensilla.glb`.

## Reglas Operativas
1. NUNCA asumas los nombres de capas o atributos dentro de los ZIPs de Catastro. Descomprime y analiza los encabezados de los archivos GML/SHP primero.
2. Todo dato transformado debe reproyectarse al sistema de referencia local métrico con origen relativo `(0, 0, 0)`.
3. Mantén los scripts de conversión parametrizados dentro de `tools/gis/`.

## Inputs & Outputs
- **Inputs:** `data/raw/catastro/*`, `data/raw/osm/*`.
- **Outputs:** `data/export/almensilla_terrain.glb`, `data/export/almensilla_buildings.glb`, `data/export/almensilla_roads.glb`.

## Contrato de Salida
1. Formato: GLB (glTF 2.0).
2. Alturas de edificios: Si Catastro incluye número de plantas (`numberOfFloorsAboveGround`), calcular altura como `plantas * 3.0m`. Si no, fallback de 3.5m para viviendas y 6.0m para naves.
3. Separación de colisiones: Las mallas de edificios deben incluir el prefijo de nodo `COL_` en el árbol de escenas para que el motor identifique los límites caminables.