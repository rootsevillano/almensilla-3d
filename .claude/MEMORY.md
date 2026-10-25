# MEMORY — almensilla-3d

## 2026-10-25 · Inspección forense de datos brutos (agente 01_gis_pipeline)

### Entorno
- Python 3.12.9 (sistema). Stack GIS instalado con pip en el site-packages **de usuario** (2026-10-25),
  fijado en `tools/gis/requirements.txt`: geopandas 1.2.0, pyogrio 0.13.0 (GDAL 3.12.4 embebido),
  shapely 2.2.0, pyproj 3.8.0 (PROJ 9.8.1), trimesh 5.2.0, mapbox-earcut 2.1.0 (triangulador de trimesh), numpy 2.4.4.
  No hay `ogrinfo` en el PATH (GDAL solo vía pyogrio), ni osmnx/osmium/pygltflib.
- ⚠️ Ejecutar con `python -P`, no con `python -I`: `-I` desactiva el site-packages de usuario y no encuentra el stack.
- Huellas SHA-256 de los datos inspeccionados (si cambian, repetir la inspección):
  - `A.ES.SDGC.AD.41010.zip` 304cec2787a21c24b51e0712ac4b0a0a4f868a444542a08fbfba688069940a30
  - `A.ES.SDGC.BU.41010.zip` 6deeb02406609b572048fc9b53e33fff82fe8f5b3cc50473800a89402f4a8801
  - `A.ES.SDGC.CP.41010.zip` ea7033f6a6fc4fbcdc67fc3dd0ad14d3c5336a6a1325371434b173cfdb0c0036
  - `almensilla con sector f.osm` a993e995452e2e7e3f152ac97ebd252d195f4f0d5fcb56daed639c7d2dbc0c97

### CRS y extensión
| Fuente | CRS | Notas |
|---|---|---|
| Catastro AD, BU | `urn:ogc:def:crs:EPSG::25829` | ETRS89 / UTM 29N. Orden de ejes **Este, Norte** en `posList` (`srsDimension="2"`). |
| Catastro CP | `http://www.opengis.net/def/crs/EPSG/0/25829` | Mismo CRS, distinta forma de URI: comparar por código EPSG, no por cadena. |
| OSM | WGS84 (lat/lon) | |

- Almensilla está entera al oeste del meridiano −6° → huso 29 (aunque gran parte de Sevilla es huso 30).
- **Origen local adoptado** (centro del extent de CadastralParcel, redondeado): `E0=755870, N0=4132708`
  (EPSG:25829) ≈ `37.305823, −6.113005`. `x = E − E0`, `y = N − N0`, `z = 0` a rasante.

Bounding boxes:
| Ámbito | EPSG:25829 (minE minN maxE maxN) | WGS84 (minlat, minlon → maxlat, maxlon) |
|---|---|---|
| Término municipal (CP parcel/zoning) | 752761.976 4130594.132 758978.105 4134822.699 | 37.28764, −6.14875 → 37.32400, −6.07724 |
| Edificaciones (BU) | 754061.92 4130683.79 758896.08 4134436.18 | 37.28810, −6.13407 → 37.32054, −6.07830 |
| Direcciones (AD) | 755095.18 4130815.44 758732.37 4134368.21 | — |
| OSM `<bounds>` | — | 37.29140, −6.12462 → 37.32062, −6.06797 |
| OSM extensión real de nodos | — | 37.16109, −6.19784 → 37.37070, −6.03538 (incluye nodos de relaciones completas que salen del bounds) |

El `<bounds>` de OSM coincide con el extent BU (validación cruzada de la inversa UTM).

### Catastro — contenido de los ZIP (INE 41010)
Todos los GML de AD y BU van en **ISO-8859-1**; los de CP en **UTF-8** (lo gestiona el parser XML vía la declaración).

**A.ES.SDGC.BU.41010.zip**
- `A.ES.SDGC.BU.41010.building.gml` — 2798 `bu-ext2d:Building`
- `A.ES.SDGC.BU.41010.buildingpart.gml` — 10574 `bu-ext2d:BuildingPart`
- `A.ES.SDGC.BU.41010.otherconstruction.gml` — 912 `bu-ext2d:OtherConstruction`
- `A.ES.SDGC.BU.MD.41010.xml` — metadatos ISO

**A.ES.SDGC.AD.41010.zip**
- `A.ES.SDGC.AD.41010.gml` — 3368 `Address`, 115 `ThoroughfareName`, 1 `PostalDescriptor` (41111), 1 `AdminUnitName` (ALMENSILLA)
- `A.ES.SDGC.AD.MD.41010.xml`

**A.ES.SDGC.CP.41010.zip**
- `A.ES.SDGC.CP.41010.cadastralparcel.gml` — 3822 `CadastralParcel`
- `A.ES.SDGC.CP.41010.cadastralzoning.gml` — 174 `CadastralZoning` (166 MANZANA, 8 POLIGONO)
- `A.ES.SDGC.CP.MD..41010.xml` (sic, doble punto)

#### Esquema Building (`bu-ext2d:Building`)
- Geometría: `bu-ext2d:geometry/bu-core2d:BuildingGeometry/bu-core2d:geometry/gml:Surface/gml:patches/gml:PolygonPatch`
  (1–10 patches por edificio: 1937 con 1, 674 con 2, …; 46 anillos interiores). `horizontalGeometryReference=footPrint`.
- `bu-core2d:inspireId/base:Identifier/base:localId` = refcat de 14 caracteres (p. ej. `41010A00100001`).
- `bu-ext2d:currentUse` (**17 Building sin valor**, detectado al leer con GDAL): `1_residential`(2590), `3_industrial`(93), `2_agriculture`(41), `4_3_publicServices`(32), `4_2_retail`(24), `4_1_office`(1).
- `bu-core2d:conditionOfConstruction`: functional(2752), declined(18), `-`(15), ruin(13).
- `bu-ext2d:numberOfBuildingUnits`, `bu-ext2d:numberOfDwellings`, `bu-ext2d:officialArea/.../value` (grossFloorArea, m²),
  `bu-core2d:dateOfConstruction/bu-core2d:DateOfEvent/{beginning,end}`.
- ⚠️ `bu-ext2d:numberOfFloorsAboveGround` es **siempre `xsi:nil` (unpopulated)** en Building.

#### Esquema BuildingPart (`bu-ext2d:BuildingPart`) — **fuente de alturas**
- Misma ruta de geometría que Building (1 patch cada uno, 75 interiores).
- `localId` = `<refcat14>_part<N>` → enlace con `Building.localId` cortando por `_part` (0 huérfanos).
- `bu-ext2d:numberOfFloorsAboveGround`: 1(7238), 2(2873), 3(247), **0(184)**, 5(17), 4(15). Siempre poblado.
- `bu-ext2d:numberOfFloorsBelowGround`: 0(10351), 1(223). `bu-ext2d:heightBelowGround` (m): 0 / 3.
- Sin `currentUse` propio: se hereda del Building padre.

#### Orientación de anillos (⚠️ trampa)
- Catastro BU entrega **exteriores en sentido horario (CW)** e interiores CCW (3943/3943 exteriores en Building).
  RFC 7946 y la extrusión requieren lo contrario → el extractor normaliza (exterior CCW, interior CW).
  Sin esto, las normales de las mallas saldrían invertidas (criterio QA 1 del agente 04).

#### OtherConstruction
- `bu-ext2d:geometry/gml:Polygon` (no Surface). `constructionNature` = `openAirPool` en los 912 → piscinas.

#### CadastralParcel / CadastralZoning
- Geometría `geometry/gml:MultiSurface/gml:surfaceMember/gml:Surface/gml:patches/gml:PolygonPatch`.
- Parcel: `areaValue` (m²), `label`, `nationalCadastralReference`, `referencePoint/gml:Point/gml:pos`.
- Zoning: `levelName` (MANZANA/POLIGONO), `nationalCadastalZoningReference` (sic, errata INSPIRE), `originalMapScaleDenominator`.
- La unión de CadastralZoning/Parcel sirve como **límite municipal completo** (ver problema del límite OSM).

#### Address (AD)
- `position/GeographicPosition/geometry/gml:Point/gml:pos`, `specification` Entrance(3131)/Parcel(237),
  `locator/.../designator` (número de portal). Calle vía `component xlink:href` → `ThoroughfareName`.

### OSM — `data/raw/osm/almensilla con sector f.osm`
- XML OSM 0.6 (cgimap), 40152 nodos, 12250 vías, 111 relaciones.
- **Viales (`highway=*` en ways, 614)**: residential 281, footway 86, secondary 79, track 64, service 25, tertiary 14,
  path 9, cycleway 9, pedestrian 9, secondary_link 8, motorway 8, construction 8, unclassified 5, motorway_link 4,
  steps 3, living_street 2. Tags asociados útiles: `name`(318), `oneway`(230), `surface`(128), `ref`(96), `lanes`(67),
  `bridge`(15), `layer`(14), `tunnel`(2), `width`(1, casi inexistente → anchura por tipo de vía).
- **Edificios**: `building=*` house 1658, residential 1034, industrial 88, retail 31, public 25, yes 24, barn 4,
  school 3, roof 2, office 1 (+29 relaciones multipolígono: residential, house, apartments, industrial, retail).
  `building:part=yes` en 7909 elementos y `building:levels` en 10723 → es una **importación de Catastro**
  (mismo despiece en partes). Niveles: 1(6197), 2(4126), 3(435), 4(17), 5(21).
  `building:levels:underground` 217. **No** existen `height`, `min_height`, `roof:*`.
- **Límites**: relación `340652` `boundary=administrative`, `admin_level=8`, `name=Almensilla`, `ine:municipio=41010`.
  ⚠️ Incompleta: solo 4 de sus 5 vías `outer` están en el fichero → no se puede cerrar el anillo con OSM.
  También aparecen municipios vecinos (Mairena del Aljarafe 41059, Palomares del Río 41070, La Puebla del Río 41079,
  Coria del Río 41034) y la provincia (admin_level 6).
- `place=village` Almensilla (nodo 249482084), 18 `place=locality`, barrio `Urbanización Santa Iglesia`;
  `landuse=residential` con nombre: Vista del Aljarafe, La Señora, Ugena.

### Atributos útiles para alturas — decisión
1. **Fuente primaria: Catastro `BuildingPart.numberOfFloorsAboveGround`** × 3.0 m (contrato). Siempre poblado.
2. `Building.numberOfFloorsAboveGround` no sirve (nil). El fallback 3.5 m / 6.0 m del contrato se aplica solo si falta
   el dato en la parte; tipo "nave" = `currentUse ∈ {3_industrial, 2_agriculture}` del Building padre.
3. Partes con 0 plantas sobre rasante (184): se exportan con `height_m=0`, `height_source=catastro_zero_floors`.
   **Pendiente de decisión**: ¿omitir, extruir mínimo (p. ej. 0.3 m) o tratarlas como suelo/patio?
4. OSM `building:levels` es redundante (misma importación); útil solo como verificación cruzada.

### Scripts
- `tools/gis/extract_catastro_buildings.py` → `data/processed/catastro_buildings.geojson`,
  `catastro_building_parts.geojson`, `catastro_other_constructions.geojson`, `catastro_buildings.meta.json`
  (coordenadas locales respecto al origen indicado). Validado: 2798 / 10574 / 912 features, 0 geometrías nulas.

### 2026-10-25 · Re-ejecución bajo protocolo CLAUDE.md
- Inspección repetida: salida de esquemas de AD/BU/CP **idéntica** a la primera pasada; recuento OSM idéntico
  (614 highway, 2900 building, 7909 building:part). Hallazgos anteriores confirmados.
- QA de geometría sobre `data/processed/*.geojson`: 0 NaN/inf, 0 anillos abiertos, 0 degenerados;
  tras la corrección, 100 % exteriores CCW e interiores CW.
- Contratos (`tests/contracts/validate_glb.py`): solo valida GLB (existencia + presupuesto de 50 MB).
  Aún no aplica: no se ha generado ningún GLB. El extractor solo escribe en `data/processed/` (dominio del agente 01).

### 2026-10-25 · Migración del extractor al stack GIS
- Lectura de GDAL (driver GML) verificada sobre `/vsizip/…zip/<member>.gml`: CRS EPSG:25829 reconocido;
  capas `Building` (1937 Polygon + 861 MultiPolygon), `BuildingPart` (10574 Polygon), `OtherConstruction`
  (912 Polygon); todas válidas según shapely, sin nulas. GDAL aplana el esquema a nombres locales
  (`value` = officialArea, `end` = dateOfConstruction/end, `reference`, `lowerCorner`…). No escribe `.gfs` en `data/raw`.
- `extract_catastro_buildings.py` usa ahora geopandas/pyogrio (lectura y escritura GeoJSON), `shapely.orient_polygons`
  + `shapely.transform` (orientación y origen local) y pyproj (metadatos WGS84). Guarda de esquema `SCHEMA` que aborta
  si falta una columna verificada o cambia el CRS.
- Regresión frente a la versión stdlib: **0 diferencias** de propiedades y geometría (tolerancia 1 mm) en las
  14 284 features; la inversa UTM manual y pyproj coinciden con una diferencia de ~1e-9°.
- `tests/contracts/validate_glb.py` falla con "no existe", como se esperaba: todavía no hay ningún GLB.

### 2026-10-25 · GLB de edificios (`data/export/almensilla_buildings.glb`)
- Script: `tools/gis/build_buildings_glb.py` (entrada: `data/processed/catastro_building_parts.geojson`).
- **Estructura:** un nodo por Building catastral, `COL_<localId>` (2793 nodos/mallas), con su malla fusionando las
  extrusiones de sus BuildingPart. 7 materiales PBR compartidos por `currentUse` (`MAT_<uso>`, `MAT_unknown` para los 17 sin uso).
  extras de malla: `localId`, `currentUse`, `parts`, `max_height_m`. extras de escena: `axes`, `units`, `collision_prefix`.
- **Ejes glTF:** X = Este, Y = arriba, Z = −Norte (rotación −90° sobre X del sistema local; conserva el winding).
  Base en Y=0 (rasante, sin terreno todavía). Bounds: X [−1808.08, 3010.68], Y [0, 15], Z [−1728.18, 2024.21].
- **Cifras:** 10390 partes extruidas, 129 508 vértices, 217 744 triángulos, 5.01 MB. `validate_glb.py` → **passed**.
- **Partes de 0 plantas:** se omiten por defecto (`--zero-floor-height 0`); 184 partes. Por eso 5 edificios
  quedan fuera del GLB (solo tienen partes de 0 plantas): 5736024QB5353N, 5834051QB5353S, 6134013QB5363S,
  7832764QB5373S, 8425962QB5382N. Con `--zero-floor-height 0.3` se convierten en losas.
- **Trampas encontradas:**
  1. 3 BuildingPart (6433004QB5363S_part2, 6833610QB5363S_part1, 8022901QB5382S_part3) tienen un patio que toca el
     contorno exterior en un único punto (válido OGC) → vértice no-manifold al extruir. Se corrige con una erosión de 1 mm
     solo en esos casos (`separate_pinched_holes`).
  2. earcut genera triángulos de área ~0 (vértices alineados; queda 1 malla con alguno). **No eliminarlos**: quitarlos
     rompe la estanqueidad (probado: 3 mallas pasaron a no estancas).
- **QA (criterio 1 del agente 04) sobre el GLB releído:** 0 NaN/inf, 0 winding inconsistente, 0 no estancas,
  0 volumen negativo (normales hacia fuera), nombres de nodo únicos y todos con `COL_`.
- Para el agente 02: 2793 mallas implican ~2793 draw calls; conviene fusionarlas por material en tiempo de carga
  (regla 2 del agente 02), conservando los nombres `COL_` para las colisiones.

### Pendiente / bloqueos

### 2026-10-25 · Triangulador para extrusión
- Instalado `mapbox-earcut` 2.1.0 (añadido a `requirements.txt`); `trimesh.creation.extrude_polygon` ya funciona.
- Verificado: caja 10×10×3 → 8 vértices / 12 caras, estanca, winding consistente, volumen 300 m³ exacto.
  Parte real `41010A00200003_part1` (2 patios interiores, 1 planta → 3 m): 40 vértices / 84 caras, estanca,
  volumen = área × altura (5048.015 m³), z ∈ [0, 3]. Volumen positivo → normales hacia fuera con la orientación CCW del extractor.
- Decidir qué hacer con las 184 partes de 0 plantas: provisionalmente se omiten en el GLB (ver sección GLB).
- `almensilla_terrain.glb` y `almensilla_roads.glb` aún no existen. Al añadir terreno con cota, habrá que asentar los edificios sobre él.
- trimesh no tiene `networkx` (algunas utilidades de `trimesh.repair` fallan); no hace falta para la extrusión.
- Extractor OSM de viales (`highway=*` → polilíneas + anchura por tipo; QA exige 6–10 m en calles principales)
  y límite municipal desde CP.
- Decidir si `data/processed/` se versiona (≈7 MB de GeoJSON) o se añade a `.gitignore`.
