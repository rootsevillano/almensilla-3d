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
- Zoning: `levelName` (MANZANA/POLIGONO, con espacio final en el dato), `nationalCadastalZoningReference` (sic, errata INSPIRE), `originalMapScaleDenominator`.
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

### 2026-10-25 · Triangulador para extrusión
- Instalado `mapbox-earcut` 2.1.0 (añadido a `requirements.txt`); `trimesh.creation.extrude_polygon` ya funciona.
- Verificado: caja 10×10×3 → 8 vértices / 12 caras, estanca, winding consistente, volumen 300 m³ exacto.
  Parte real `41010A00200003_part1` (2 patios interiores, 1 planta → 3 m): 40 vértices / 84 caras, estanca,
  volumen = área × altura (5048.015 m³), z ∈ [0, 3]. Volumen positivo → normales hacia fuera con la orientación CCW del extractor.

### 2026-10-25 · Git
- Commit `561c61b` en la rama `gis/catastro-buildings-glb` (local). El push falló: «Repository not found»
  (repo privado `rootsevillano/almensilla-3d`; credenciales sin acceso). No hay `gh` instalado.
- `.gitignore`: `data/processed/*` (salvo `.gitkeep`) y `__pycache__/`.
- **Desde 2026-10-26 el usuario gestiona Git/GitHub a mano**: los agentes no hacen commit, push, ramas ni PR.

### 2026-10-26 · GLB de viales (`data/export/almensilla_roads.glb`)
- Script: `tools/gis/build_roads_glb.py`. Entradas: OSM, `A.ES.SDGC.CP.41010.zip` (zoning + parcelas),
  `data/processed/catastro_buildings.geojson` (huellas) y `catastro_buildings.meta.json` (origen local compartido).
  Salidas: `data/processed/osm_roads.geojson` (ejes con `width_m`, `width_source`) y el GLB.
- **Inspección OSM (viales):** 614 ways; ninguna relación con highway; 0 referencias a nodos ausentes.
  `area=yes` solo en 6 `pedestrian` (plazas → polígono). 14 rotondas cerradas (`junction=roundabout`).
  `tunnel=yes` 2 (omitidos). `bridge=*` 30 (aplanados a rasante: todavía no hay terreno).
  `width` solo 1 vez y erróneo (`0.6` en carril bici, descartado por el rango de clase).
  **8 `highway=construction` sin subtipo** (IDs 1391792120–138, 968 m): están dentro de manzanas catastrales,
  miden 8.1 m → calles del sector F; se tratan como `residential`.
- **Trampa CP:** `CadastralZoning.levelName` (columna GDAL `LocalisedCharacterString`) lleva **espacio final**:
  `'MANZANA '`, `'POLIGONO '`. Comparar con `.str.strip()`.
- **Término municipal** = unión de CadastralZoning: 1 polígono sin huecos, 14.035 km² (sustituye al límite OSM incompleto).
- **Anchuras reales medidas** (rayos perpendiculares cada 10 m hasta el borde de parcela, en manzanas + 40 m;
  en suelo urbano el Catastro no parcela las calles → hueco = fachada a fachada):
  residential mediana 9.4 m (p25 8.1, p75 12.3); tertiary 13.3; construction 8.1; pedestrian 4.7; living_street 9.3.
  Avenidas con mediana/zonas verdes dan valores altos (Miró 41 m, Tolerancia 33 m) → se acota por clase.
- **Regla de anchura** (por vía): `width` OSM si está en rango > mediana medida acotada a [mín, máx] de la clase >
  motorway por `lanes`×3.5+3 > valor por defecto de la clase. Tabla `CLASSES` en el script.
  Resultado: 144 medidas, 90 medidas acotadas, 9 por lanes, 369 por defecto (rurales/sin muestras).
- **Geometría:** buffer redondo de los ejes, unión por grupo (`carriageway` > `track` > `pedestrian`, cada grupo recortado
  con los anteriores → disjuntos), simplificación 5 cm **antes** de recortar, recorte al término y **resta de huellas
  de Building** (sin ella, 5123 m² = 0.87 % de la calzada caía bajo edificios por desalineación OSM–Catastro).
- **GLB:** superficies planas en Y = 0.02 m, teselas de 500 m, nodos `ROAD_<grupo>_<i>_<j>` (102), sin `COL_`
  (caminable). 3 materiales `MAT_road_<grupo>`. Mismos ejes que edificios (X=E, Y=arriba, Z=−N).
  Área: calzada 586 947 m², pistas 72 474 m², peatonal 21 444 m². 8859 triángulos, 0.26 MB.
- **Trampa float32:** el GLB guarda vértices en float32 (~0.2 mm de resolución a 3 km del origen) y astillas de
  <0.002 m² se voltean al cuantizar (6 caras con normal −Y). Se orienta tras redondear a float32 y se descartan las
  caras de área nula en float32. Verificar siempre releyendo con `trimesh.load(..., process=False)`.
- **Validación:** `validate_glb.py` → passed. QA: 0 NaN, 0 caras sin normal +Y, Y = 0.02 en todos los vértices,
  0 m² de solape entre grupos, 0 m² fuera del término, 0 m² bajo edificios, nombres únicos `ROAD_`.
- **Criterio QA 3 (6–10 m en calles principales):** mediana 9.11 m; el 76.6 % de la longitud principal
  (secondary/tertiary/residential/construction) está en 6–10 m; 18 km superan 10 m porque son **medidas reales**
  (Alisma 10.2, Solidaridad 10.2, Andalucía, Miró…), y 1.5 km quedan por debajo de 6 m. Lo debe valorar el agente 04.

### 2026-10-26 · GLB de terreno (`data/export/almensilla_terrain.glb`)
- Script: `tools/gis/build_terrain_glb.py`; reutiliza `build_roads_glb.py` (origen, término municipal,
  `build_surfaces`, `flat_mesh`) para que límite, origen y superficies sean idénticos. Requiere ejecutar antes
  `build_roads_glb.py` (lee `data/processed/osm_roads.geojson`); `--no-cut-roads` lo evita.
- **Plano en Y=0** (no hay MDT) con la forma del término municipal (unión de CadastralZoning, 14.0346 km²),
  **menos las superficies de vial**, para que terreno (Y=0) y viales (Y=0.02) no se solapen y no haya z-fighting.
  Las huellas de edificio sí forman parte del terreno (los edificios apoyan en Y=0).
- Teselas de 500 m (las mismas que los viales), 85 nodos `TERRAIN_<i>_<j>` (caminable, sin `COL_`), 1 material
  `MAT_terrain`. 9187 triángulos, 0.27 MB. Bounds glTF X [−3108.02, 3108.11], Z [−2114.70, 2113.87].
- Áreas: terreno 13 353 688 m² + viales 680 865 m² = 14 034 553 m² = término municipal.
- **Validación:** `validate_glb.py` → passed. QA del GLB releído (`process=False`): 0 NaN, 0 caras sin normal +Y,
  todos los vértices en Y=0, 0 triángulos de área 0, nombres únicos `TERRAIN_`; edificios dentro de los bounds.
- Costura terreno–viales: en float64, solape y huecos = 0 m². En los GLB (float32) salen ~15 m² de cada uno, que
  equivalen a 0.09 mm de desplazamiento medio en 165 km de borde (resolución float32 a 3.1 km: 0.24 mm) → despreciable.
- Escena completa: edificios + viales + terreno = 0.26 + 0.27 + 5.01 MB, todo en el mismo sistema (X=E, Y=arriba, Z=−N).

### 2026-10-26 · Visor mínimo (agente 02) — `app/`
- Vite 8.3.5 + three 0.186.1 (versiones exactas en `app/package.json`), Node 24.14.1 / npm 11.11.0.
  `.gitignore`: `node_modules/`, `app/dist/`.
- `npm --prefix app run dev` → http://localhost:5173 (`predev` ejecuta `sync-models`).
  `app/scripts/sync-models.mjs` valida los 3 GLB con `tests/contracts/validate_glb.py` (regla 4) y solo entonces
  los copia de `data/export/` a `app/public/models/` (único directorio que lee el visor, contrato 02↔01).
  Los GLB quedan duplicados en `app/public/models/` (~5.5 MB): valorar si ignorarlos en Git.
- Módulos: `src/scene.js` (renderer ACES/sRGB, cielo `#bcd6ec`, niebla lineal 700–3600 m que oculta el borde sin
  suelo, HemisphereLight + sol direccional desde el SO, OrbitControls con amortiguación y sin bajar del horizonte,
  cámara near 1 m / far 8000 m), `src/models.js` (GLTFLoader, fusión de edificios, centro del casco = mediana de los
  centros de los edificios), `src/stats.js` (FPS en HUD + benchmark), `src/main.js`.
- Los GLB no llevan normales (solo POSITION): el GLTFLoader activa `flatShading` solo, que es lo correcto para extrusiones.
- **Fusión de edificios** (regla 2): las 2793 mallas `COL_` se fusionan en 7 (una por material) para el render;
  las originales quedan fuera de la escena en `window.__almensilla.collisionMeshes` para el agente 03.
  Terreno y viales se mantienen por teselas (frustum culling). `?merge=0` desactiva la fusión.
- **Benchmark** `?bench=20`: 2 s de calentamiento + 20 s de órbita automática (r=900 m, h=420 m) alrededor del casco;
  resultado en `window.__bench` y en consola. rAF está limitado por el refresco del monitor (aquí 144 Hz).
- **Medidas** (panel de navegador integrado de Claude, visible, viewport emulado de 1920×1080, DPR 1.25 → lienzo 2400×1350):
  - Con fusión: **141 FPS de media**, 1 % low 71.9, p50 6.9 ms, p95 7.1 ms, p99 13.9 ms, ~105 draw calls,
    231 k triángulos, carga 0.21 s. Cumple el criterio QA 2 (≥60 FPS a 1080p) en esta máquina.
  - Sin fusión: ~2180 draw calls, p50 7.0 ms, p95 14 ms (las medias de las 2 tandas no valen: hubo pausas de
    1–15 s porque la página dejó de estar a la vista).
  - Lienzo pequeño (462×298): 144 FPS (tope del monitor), p99 7.1 ms.
  - Pendiente: medir en un navegador normal a pantalla completa en el "equipo estándar" del criterio (agente 04).
- El panel de navegador busca `.claude/launch.json` en la carpeta raíz de la sesión; si la sesión se abre en
  `C:\Github\almensilla-3d`, sirve `.claude/launch.json` (config `viewer`).

### 2026-10-26 · Personaje en tercera persona (agente 03) — `app/src/character/`
- **Estilo pedido por el usuario:** monigote 3D blanco tipo maniquí (referencia: imagen de stock «hombre negando con el
  dedo» de magnific.com, solo vista; no se descargó ni copió). Modelado **procedural** con primitivas de Three.js
  (`Monigote.js`): cabeza de huevo sin cara (esfera r=0.26 escalada 1.12 en Y), torso de cápsula aplanado, brazos
  cortos con manos esféricas, piernas rechonchas con pies esféricos alargados. Altura ~1.8 m, origen en los pies,
  mira a +Z local. Material blanco satinado con algo de emisión (sin ella, a contraluz se veía gris).
  Sombra difusa bajo los pies (textura radial en un canvas), porque la escena no tiene mapas de sombra.
- **Animación por código:** fase de paso ligada a la distancia recorrida (zancada 1.35 m), balanceo opuesto de
  piernas y brazos con más amplitud al correr, rebote vertical, inclinación hacia delante, contoneo de hombros y
  respiración en reposo.
- **Controlador** (`controller.js`): WASD/flechas relativas a la cámara, Mayús para correr (3 → 8 m/s),
  aceleración de 14 m/s² y frenado de 18 m/s², giro suave hacia la dirección de marcha, Espacio para saltar
  (gravedad 18 m/s², ~0.84 m). Raycast hacia abajo contra `TERRAIN_*`/`ROAD_*`: si no hay suelo (fuera del término),
  no avanza. Aparece en el punto de calle libre más cercano al centro del casco (búsqueda en espiral sobre `ROAD_*`).
- **Colisión** (`collision.js`, `FootprintCollider`): se extraen de las mallas `COL_` las aristas inferiores de sus
  caras verticales (64 754 segmentos = contorno exacto de las huellas, patios incluidos; ~80–110 ms al cargar) en una
  rejilla de 8 m; el personaje es un círculo de r=0.32 m en planta que se empuja fuera de los muros (3 iteraciones).
  Válido porque los edificios son extrusiones desde Y=0 y el personaje siempre está por debajo de las cubiertas.
- **Cámara de persecución:** órbita con arrastre del ratón y zoom con la rueda (1.2–14 m), amortiguada; un rayo desde
  la altura de los ojos contra las mallas `COL_` la acerca **al instante** si hay muro (margen de 0.3 m) y la aleja
  despacio. No baja del suelo. `camera.near` = 0.2 m en modo personaje y 1 m en vista aérea.
- `main.js`: modo personaje por defecto; tecla **C** alterna con la vista aérea orbital; `?bench` sigue midiendo
  solo la escena con cámara orbital (no crea personaje). `window.__almensilla.player` / `.character` para pruebas.
- **Pruebas** (en el navegador, automatizadas con JS):
  - Andar 2 s → 5.95 m; correr 1 s → 7.55 m (incluyen aceleración y frenado); salto 0.82 m (teórico 0.84), aterriza.
  - Correr 2 s contra un muro de 10.7 m: se detiene a 0.320 m (= radio), sin penetrar.
  - Paseo aleatorio de 20 000 pasos a velocidad de carrera (2.56 km, 245 contactos): distancia mínima a muro 0.320 m,
    0 penetraciones. (5000 puntos aleatorios a ±0.3 m de muros dan "penetraciones", pero son puntos dentro de edificios
    o en medianeras compartidas, inalcanzables desde la calle.)
  - Cámara con el muro a 1.01 m: se coloca a 0.71 m, por delante del muro.
  - Límite del término: corriendo hacia fuera se detiene a 5 cm del borde.
  - Coste de CPU por fotograma: `player.update` 0.57 ms (raycast de cámara 0.26 ms, suelo 0.10 ms, colisión <0.01 ms).
  - FPS en modo personaje (1080p emulado, lienzo 2400×1350, panel visible): 144 media, 1 % low 140.8, máx 7.4 ms.
    Con el panel oculto salen 48 FPS (= 144/3): es estrangulamiento del navegador, no coste real.
- La captura de pantalla del panel con viewport emulado puede mostrar el lienzo sin redimensionar; la página informa
  de tamaños correctos (artefacto de la captura).

### 2026-10-26 · Sombras del sol (agente 02) — `app/src/shadows.js`
- Un único mapa de sombras de 2048² (`PCFShadowMap`) de la luz direccional, con la cámara ortográfica **centrada en
  el foco**: el personaje en modo a pie, `controls.target` en la vista aérea y el centro del casco en `?bench`.
  Radio = 1.1 × distancia cámara–foco, por escalones de potencias de 2 entre 32 y 512 m (texel de 3.1 cm a pie,
  25 cm a 256 m). El centro se ajusta a la rejilla de texels en el espacio de la luz para que la sombra no tiemble.
  `?shadows=0` las desactiva.
- Proyectan sombra: edificios y monigote (su sombra difusa se oculta). Reciben: terreno, viales y edificios.
- Los GLB no traen normales: `enableShadows` las genera (geometría no indexada → normales planas) para que
  `normalBias` funcione. bias −0.0004, normalBias 0.03; sin acné ni peter-panning visibles.
- **Edificios fusionados por material y tesela de 500 m** (106 mallas en vez de 7): con una sola malla por material,
  la pasada de sombras dibujaba el pueblo entero (217 k triángulos) aunque el mapa cubriera 64 m.
- `GpuTimer` en `stats.js` (`EXT_disjoint_timer_query_webgl2`): tiempo de GPU por fotograma, que no depende del tope de
  refresco; aparece en el HUD y en `window.__bench` (gpu_ms_p50/p95/p99).
- **Medidas** (1080p emulado, lienzo 2400×1350, panel visible, monitor de 144 Hz; GPU ms p50 / p99):

  | Escena | Sin sombras | Con sombras | Coste |
  |---|---|---|---|
  | Personaje andando/corriendo (teselas) | 2.10 / 3.51 ms | 2.99 / 4.13 ms | +0.9 ms |
  | Bench orbital r=900 m (teselas) | 3.10 / 4.41 ms | 3.93 / 5.28 ms | +0.8 ms |
  | Personaje, edificios sin teselas (antes) | 3.02 / 3.85 ms | 4.36 / 5.04 ms | +1.3 ms |
  | Bench orbital, sin teselas (antes) | 2.86 / 3.96 ms | 3.80 / 5.15 ms | +0.9 ms |

  FPS: 143.4–144 de media y 1 % low 140.8 en todos los casos (tope del monitor). Draw calls con sombras:
  104 a pie y 188 en el bench orbital. Las teselas encarecen un poco la vista aérea lejana sin sombras
  (155 frente a 105 draw calls, +0.24 ms) y abaratan mucho la vista a pie.

### 2026-10-26 · Git (estado comprobado)
- El usuario subió la rama y fusionó el PR #1 en `main` (solo el primer commit del pipeline). La aplicación completa
  (visor, monigote, sombras) está en `origin/gis/catastro-buildings-glb` (commit `fdbab44`), aún no en `main`.

### 2026-10-26 · Fase 1 de realismo
Hoja de ruta acordada: (1) con datos actuales: fachadas, azoteas, aceras, piscinas y árboles; (2) datos abiertos del
IGN/CNIG (ortofoto PNOA, LiDAR, MDT05; CC BY 4.0); (3) edificios singulares, mobiliario, LOD.
- **Pretiles** (`build_buildings_glb.py`, agente 01): anillo de 0.2 m × 0.9 m sobre el borde de cada parte; se quita el
  tramo que linda con otra parte del mismo edificio igual o más alta; sin pretil en naves (`3_industrial`,
  `2_agriculture`) ni en partes de menos de 6 m². Anillo simplificado 10 cm. 9281 piezas. Edificios: 217 k → 525 k
  triángulos, 5.0 → 10.3 MB (sin simplificar eran 668 k y 13.3 MB). QA: 0 NaN, 0 volumen negativo, winding consistente.
  La colisión del personaje no cambia (64 754 muros: los pretiles no arrancan en Y=0).
- **Aceras con bordillo** (`build_roads_glb.py`): `sidewalk_m` por lado según la anchura total (≥9 m → 1.5; ≥7.5 → 1.2;
  ≥6.5 → 0.9; menos → sin acera, casco estrecho) solo en calles urbanas de secondary/tertiary/unclassified/residential/
  construction/living_street. Calzada = buffer de (anchura − 2·acera)/2; acera = superficie de calzada − calzada (en los
  cruces gana la calzada → esquinas solas), sin astillas de menos de 20 cm. Aceras = losas de 15 cm (`ROAD_sidewalk_*`,
  tapa a Y=0.17). 207 vías con acera; calzada 491 105 m² + aceras 95 842 m² = calzada anterior. Viales: 0.80 MB.
- **Piscinas** (`build_terrain_glb.py`): 912 `openAirPool` de Catastro recortadas del terreno; `POOL_water_*` (lámina a
  ras, 28 141 m²) y `POOL_coping_*` (borde de 0.35 m y 6 cm, 7948 m²). Terreno + piscinas = terreno anterior.
  Terreno: 9 k → 106 k triángulos (los 912 huecos), 2.08 MB. OSM solo tiene 550 `leisure=swimming_pool`.
- **Árboles** (`tools/gis/build_trees.py` → `data/export/almensilla_trees.json`, nuevo artefacto del agente 01):
  inspección OSM: 11 `natural=tree`, 29 parques, 10 jardines, 19 `landuse=orchard` (9 `trees=olive_trees`), 5 `wood`,
  12 `heath`, 1 `scrub`. Árboles sueltos en su sitio; parques/jardines → árbol de sombra en rejilla con jitter;
  huertos → olivos en hileras alineadas con el rectángulo mínimo de la parcela (7 m); bosques → pino piñonero;
  matorral disperso. Se descartan puntos sobre edificios (+1.5 m), viales (+1 m), piscinas (+1 m) o fuera del término.
  Resultado: 29 936 (28 342 olivos, 517 de sombra, 481 pinos, 596 matorrales), semilla fija 41010, 724 KB.
  Formato `{types, fields, trees: [[x, z, tipo, escala]]}` en coordenadas glTF. `sync-models` comprueba su estructura.
- **Visor** (agente 02):
  - `src/facades.js`: atributo `facade` por vértice (u a lo largo del muro, longitud del muro, tipo muro/cubierta/
    pretil, coronación) y shader sobre MeshStandardMaterial: cal `#f4f2ea`, zócalo albero `#e0c27f` hasta 0.65 m,
    cornisa, una ventana con marco y reja por hueco de ~3.2 m en cada planta de 3 m (que quepa bajo la coronación),
    escaparates en planta baja en `retail`, naves grises sin ventanas, azotea `#d8cfbf`. A distancia el patrón se funde
    con el color medio (`fwidth`) para evitar muaré.
  - `src/ground.js`: baldosa de 40 cm en aceras (shader en coordenadas de mundo) y agua para las piscinas.
  - `src/trees.js`: árboles low-poly (tronco + copa icosaédrica, colores por vértice, 32 triángulos el olivo) en una
    InstancedMesh por tipo y tesela de 500 m (culling y sombras).
  - Luz: HemisphereLight 1.1 → 1.7 y exposición 1.0 → 1.12 (la cal salía gris en las fachadas a la sombra).
- **Medidas** (GPU por fotograma a 1080p, lienzo 2400×1350, con sombras; benchmark sintético renderizando a mano porque
  la ventana de Claude no estaba a la vista y el navegador solo pintaba 2 FPS):
  - A pie: 4.80 ms p50 / 5.71 p99 (antes de la fase 1: 2.99), 179 draw calls, 0.91 M triángulos.
  - Órbita r=900 m: 7.36 ms p50 / 7.88 p99 (antes 3.93), 250 draw calls, 1.94 M triángulos.
  - Árboles en la órbita: ~0.75 ms (sin árboles 6.67 ms; árboles sin sombra 6.99 ms). El resto de la subida viene de
    los pretiles (también en la pasada de sombras) y del shader de fachadas.
  - **FPS reales** (ventana a la vista, panel pintando a 145 FPS, 1080p emulado, lienzo 2400×1350, monitor 144 Hz):

    | Escena | FPS medio | 1 % low | Fotograma p50 | GPU p50 / p99 | Draw calls | Triángulos |
    |---|---|---|---|---|---|---|
    | `?bench=20` órbita, con sombras | 90.9 | 70.9 | 13.8 ms | 8.00 / 9.95 ms | 260 | 2.00 M |
    | `?bench=20` órbita, sin sombras | 115.1 | 71.4 | 7.0 ms | 5.78 / 7.47 ms | 214 | 1.14 M |
    | Personaje (20 s andando/corriendo), con sombras | 132.4 | 71.4 | 7.0 ms | 4.72 / 6.78 ms | 251 | 1.15 M |
    | Personaje, sin sombras | 142.5 | 73.0 | 6.9 ms | 3.52 / 5.27 ms | 231 | 0.91 M |

    Cumple el criterio QA 2 (≥60 FPS a 1080p) en esta máquina en todos los casos. En la órbita con sombras la GPU
    (8 ms) supera el intervalo de 144 Hz (6.94 ms) y muchos fotogramas caen a la cadencia de 72 FPS; con vsync a 60 Hz
    no se notaría. Falta medir en un "equipo estándar" (agente 04): ahí la vista aérea con sombras es la más justa.

### 2026-10-26 · Optimización de la vista aérea (LOD)
- **Pretiles fuera de las mallas `COL_`** (`build_buildings_glb.py`): nodos decorativos `PARAPET_<i>_<j>` por tesela de
  500 m (39 nodos), material `MAT_parapet`, sin cara inferior (apoya en la azotea). Las `COL_` vuelven a ser solo los
  volúmenes: 217 744 triángulos, estancas. Pretiles: 237 597 triángulos (antes ~308 k con cara inferior). GLB 9.67 MB.
  El visor los añade al grupo fusionado tal cual (`mergeBuildings` devuelve `parapets`) con material de cal lisa.
- **`app/src/lod.js` (`LodManager`)**, por tesela y distancia de la cámara al borde de su bounding sphere, en cada
  fotograma: pretiles sin sombra nunca y ocultos a más de 700 m (~2 px de alto a 1080p); árboles con sombra solo a menos
  de 220 m, copa simple de 8 triángulos (octaedro, sin tronco) a más de 350 m y ocultos a más de 2200 m (la niebla ya
  los tapa). `?lod=0` lo desactiva para comparar. `window.__almensilla.lod.stats` cuenta teselas por estado.
- **Medidas** (FPS reales, ventana a la vista, 1080p emulado, lienzo 2400×1350, 144 Hz; misma sesión para comparar):

  | Escena | FPS medio | 1 % low | GPU p50 / p99 | Triángulos | Draw calls |
  |---|---|---|---|---|---|
  | `?bench=20` órbita con sombras, **sin LOD** | 75.5 | 47.8 | 9.26 / 11.64 ms | 1.90 M | 287 |
  | `?bench=20` órbita con sombras, **con LOD** | 96.8 | 71.4 | 6.42 / 8.53 ms | 0.68 M | 251 |
  | `?bench=20` órbita sin sombras, con LOD | 106.0 | 71.4 | 5.61 / 7.56 ms | 0.52 M | 218 |
  | Personaje con sombras, con LOD | 129.7 | 71.4 | 4.28 / 6.00 ms | 0.75 M | 252 |

  El LOD recorta un 31 % la GPU en la vista aérea con sombras y sube el 1 % low de 47.8 a 71.4 FPS. Ojo: la GPU de esta
  sesión iba más lenta que en la medida anterior (órbita con sombras sin LOD: 9.26 ms ahora, 8.0 ms antes); comparar
  siempre dentro de la misma sesión.
- Lo que queda en la vista aérea ya no son las sombras (~0.8 ms) sino la pasada principal (~5.6 ms: fachadas y terreno
  a 2400×1350). Si hiciera falta más: LOD de edificios lejanos (sin shader de ventanas o cajas simplificadas por
  tesela), bajar el pixel ratio en la vista aérea o reducir el radio de la niebla.

### 2026-10-26 · Fase 2 — fuentes IGN/CNIG verificadas (sin descargar nada todavía)
Comprobado leyendo GetCapabilities/DescribeCoverage de los propios servicios. Todos: Fees "No se aplican
condiciones", AccessConstraints **"CC BY 4.0 scne.es"** (atribución obligatoria: © Instituto Geográfico Nacional / scne.es).
- **Ortofoto PNOA máxima actualidad (WMS 1.3.0):** `https://www.ign.es/wms-inspire/pnoa-ma`, capa
  `OI.OrthoimageCoverage` (también `OI.MosaicElement` con fechas de vuelo), admite **EPSG:25829**, máx. 4096×4096 px,
  formatos jpeg/png/tiff. Mosaico de vuelos de distintas fechas a 25 y 50 cm. WMTS equivalente: `https://www.ign.es/wmts/pnoa-ma`.
- **MDT (WCS 2.0.1):** `https://servicios.idee.es/wcs-inspire/mdt`. Coberturas `Elevacion25830_5` (MDT05, 5 m,
  EPSG:25830, COG), `Elevacion4258_5`, y mallas de 25/200/500/1000 m. **No hay EPSG:25829 ni 2 m** en este servicio:
  hay que reproyectar de 25830 a 25829.
- **MDS (WCS 2.0.1):** `https://wcs-mds.idee.es/mds`. Coberturas `mds05` (superficie 5 m, EPSG:25830),
  **`mdsn_e025`** (MDS normalizado de **edificación**, altura sobre el suelo, 2.5 m) y **`mdsn_v025`** (MDS normalizado de
  **vegetación**, 2.5 m), ambas en **EPSG:3042** (UTM 30 con orden de ejes N, E: cuidado al hacer SUBSET). TIFF.
  Según el catálogo, el MDSn procede de la **primera cobertura LiDAR (2008–2015)**: los edificios posteriores
  (p. ej. sector F) no tendrán altura → mantener las plantas de Catastro como respaldo.
- LiDAR en nube de puntos (LAZ, hojas de 2×2 km; en Andalucía la 2.ª cobertura se voló en 2020–2021) solo está en el
  Centro de Descargas del CNIG (descarga interactiva): no hace falta si se usan los MDSn.
- **Tamaños estimados** (bbox del término + 100 m en EPSG:25830: 220751 4130931 227437 4135759, 6685 × 4827 m):
  MDSn 2.5 m → 2674×1930 px, ~20 MB float32 cada uno; MDT05 → 1337×965 px, ~5 MB; ortofoto a 0.5 m → 85 teselas de
  500 m (las que tocan el término) de 1000×1000 px, ~30–45 MB en JPEG. Total ~70–90 MB en `data/raw/ign/`.
- **Memoria GPU de la ortofoto:** 85 × 1024² RGBA con mipmaps ≈ 475 MB → inviable entera; hará falta cargar a resolución
  completa solo las teselas cercanas y una versión de 256 px para el resto.
- Dependencia nueva necesaria: `rasterio` (leer y reproyectar GeoTIFF). Pillow ya está instalado.

### 2026-10-26 · Fase 2 — descargas (autorizadas por el usuario) e inspección
- Instalado `rasterio` 1.5.2 (GDAL 3.12.2; añadir a `requirements.txt` cuando se use en el pipeline).
- `tools/gis/download_ign.py`: descarga reproducible e idempotente (no repite ficheros existentes, comprueba que la
  respuesta es imagen y no un ExceptionReport, 3 reintentos, pausa de 0.25 s) y escribe `data/raw/ign/manifest.json`
  (URL, tipo, bytes, fecha UTC de cada fichero; licencia; bbox). `--only dem|ortho`.
- **Elevaciones** (bbox EPSG:25830 220751.4 4130931.2 227436.5 4135758.6, ~23 MB en total):
  - `mdt05_25830.tif`: 1337×965, **int16 en metros enteros** (cuantizado a 1 m: suavizar para evitar terrazas),
    sin nodata, sin compresión. Cota 11–81 m (mediana 44): ~70 m de desnivel en el término (cornisa del Aljarafe).
  - `mdsn_e025_3042.tif` / `mdsn_v025_3042.tif`: 2672×1929, 2.5 m, int16 en **metros enteros**, sin nodata;
    edificación 0–22 m (>0 en el 2.5 % del área); vegetación 0–30 m (>0 en el 33 %). Ficheros distintos (md5).
  - **Ejes de EPSG:3042**: GetCoverage con `SUBSET=y(N)&SUBSET=x(E)`; rasterio devuelve bounds en orden E,N correctamente.
- **Validación del MDSn de edificación contra el Catastro** (reproyectado a 1 m en EPSG:25829):
  IoU huellas / MDSn≥2 m = 0.45 sin desplazar, 0.47 en el mejor desplazamiento (1 m, menos de un píxel): bien
  georreferenciado. Mediana de altura LiDAR por plantas: 1 → 4.0 m, 2 → 7.0, 3 → 9.0, 4 → 15, 5 → 18; LiDAR / (plantas·3)
  = 1.17 (incluye pretil y cubierta). Hay altura LiDAR en edificios construidos hasta ~2020 (p99 del año), así que
  el MDSn servido parece del vuelo 2020–2021, más reciente de lo que dice el catálogo. 935 partes con plantas no
  tienen MDSn≥2 m (anexos bajos, tapados por árboles…): respaldo con plantas × 3 m.
- **Trampa:** los GeoJSON locales sin CRS se leen con CRS84 asignado por el driver; para pasarlos a EPSG:25829 hay que
  sumar el origen y usar `set_crs(25829, allow_override=True)`.
- **Ortofoto PNOA**: 85 teselas de 1000×1000 px (0.5 m) en `data/raw/ign/pnoa/pnoa_<i>_<j>.jpg`, 118–279 KB cada una.
  El servidor WMS es lento (~10 s por tesela, 16 min la primera pasada) y devuelve **502 Bad Gateway** de forma
  intermitente (18 de 85 en la primera pasada). **Trampa:** un proxy de caché del IGN guarda el 502 por URL exacta y lo
  sigue sirviendo; `download_ign.py` alterna en cada reintento la precisión del BBOX (2, 1 y 0 decimales: misma zona,
  otra clave de caché). Con eso entraron las dos últimas (`pnoa_0_3` con 1 decimal).
  **Completo: 85/85 teselas** (109–279 KB), ninguna en blanco ni de tamaño erróneo; `data/raw/ign/` = 39.7 MB
  (manifiesto con 88 entradas). Encaje con las huellas del Catastro comprobado visualmente (tesela `pnoa_1_0`):
  tejados y piscinas coinciden; se distinguen los olivos uno a uno.
- `rasterio==1.5.2` añadido a `tools/gis/requirements.txt`.
### 2026-10-26 · Ortofoto PNOA como textura del terreno
- `tools/gis/build_ortho_textures.py` (agente 01): de cada `pnoa_<i>_<j>.jpg` (1000 px) genera
  `data/export/ortho/hi/` (1024 px, ~0.49 m/px, JPEG q85, 23.7 MB en total) y `lo/` (256 px, ~1.95 m/px, q82, 1.7 MB),
  más `index.json` (teselas, tamaños, orientación fila 0 = norte, atribución). `sync-models` comprueba que el índice
  es coherente y que están las 170 texturas, y copia todo a `app/public/models/ortho/` (25.4 MB).
- `app/src/ortho.js` (`OrthoGround`, agente 02): genera UV en cada `TERRAIN_<i>_<j>` a partir de su posición
  (u = (X − i·500)/500, v = (−Z − j·500)/500), un material por tesela con la textura de 256 px al arrancar; carga la de
  1024 px si la cámara está a menos de 300 m de la tesela y la libera (dispose) a más de 550 m; máx. 3 cargas
  simultáneas, por cercanía. Filtrado anisótropo al máximo. Grano procedural en coordenadas de mundo (dos octavas de
  ruido, ±14 %) que se desvanece con la distancia: un único programa (`ortho-detail`) para las 85 teselas.
  `?ortho=0` lo desactiva. Memoria GPU estimada: 6 teselas en alta (~34 MB) + 85 en baja (~30 MB).
- Atribución obligatoria en `index.html` (`#attribution`, abajo a la derecha): IGN (CC BY 4.0 scne.es), Catastro y
  OpenStreetMap (ODbL).
- **Limitaciones vistas:** a pie la ortofoto se ve borrosa de cerca (0.5 m/px) y trae "horneados" sombras, coches y algún
  tejado desplazado por el relieve de la foto. Desde el aire el salto de realismo es grande (campos, jardines, olivar).
- **Medidas** (FPS reales, 1080p emulado, lienzo 2400×1350, misma sesión):

  | Escena | FPS medio | 1 % low | GPU p50 / p99 |
  |---|---|---|---|
  | `?bench=20` órbita, con ortofoto (0 teselas en alta: la cámara está a >420 m) | 95.9 | 71.4 | 7.08 / 9.48 ms |
  | `?bench=20` órbita, `?ortho=0` | 104.8 | 71.4 | 6.80 / 9.31 ms |
  | Personaje, con ortofoto (6 teselas en alta) | 141.3 | 71.9 | 4.13 / 5.65 ms |
  | Personaje, `?ortho=0` | 139.5 | 71.9 | 4.41 / 6.26 ms |

  Coste de la ortofoto: ~0.3 ms de GPU en la órbita y nada medible a pie. La diferencia de FPS medios en la órbita es
  mayor porque la GPU está justo en el umbral de 6.94 ms (144 Hz). La GPU de esta sesión rinde distinto a la anterior:
  comparar siempre dentro de la misma sesión.
### 2026-10-26 · Alturas reales de edificios (MDSn de edificación)
- **Cambio de regla de altura pedido por el usuario:** prioridad a la altura LiDAR; plantas × 3 m solo como respaldo.
  Esto se aparta del "Contrato de Salida" 2 de `.claude/agents/01_gis_pipeline.md` (que solo habla de plantas × 3 m):
  conviene que el usuario actualice ese contrato.
- `tools/gis/apply_lidar_heights.py` (agente 01), entre `extract_catastro_buildings.py` y `build_buildings_glb.py`.
  Actualiza `catastro_building_parts.geojson` en su sitio (idempotente: guarda `height_catastro_m` y
  `height_source_catastro`; dos pasadas dan lo mismo). Por parte: huella erosionada 0.5 m rasterizada sobre la malla de
  2.5 m (centro de píxel), mediana de los píxeles ≥1.5 m. Se acepta si hay ≥1 píxel, ≥50 % son de edificación y la
  altura está entre 0.6·(plantas·3) − 1 y 2·(plantas·3) + 3 m. Las partes sin muestra propia toman la mediana LiDAR de
  las partes del mismo edificio con las mismas plantas (`lidar_building`). Columnas nuevas: `lidar_height_m`,
  `lidar_pixels`, `lidar_building_share`, `lidar_status`.
  (Con erosión 0.75 m y ≥2 píxeles, el 52 % de las partes quedaba sin muestra: el Catastro las divide mucho.)
- **Resultado** (10 574 partes): `lidar` 6639, `lidar_building` 2696 (90 % de las partes con plantas), `catastro_floors`
  1055 (respaldo), `catastro_zero_floors` 184. Estados: ok 6639, too_small 692, no_building_in_lidar 337,
  implausible 26, zero_floors 184. Diferencia LiDAR − Catastro: p5 −1, p50 +1, p95 +4 m. Mediana por plantas:
  1 → 4.0, 2 → 7.0, 3 → 9.0, 4 → 15, 5 → 18 m. Altura máxima 19 m (19.9 con pretil).
  Los rechazos "implausible" son casi todos de `5540801QB5354S` (residencial de 2009, 127 viviendas): partes bajas de
  1 planta pegadas a las torres, cuyos píxeles recogen la altura de la torre vecina → se quedan en 3 m (correcto).
  84 de 2565 grupos edificio+plantas con varias partes tienen más de 3 m de rango (escalones reales).
- GLB de edificios: 9.78 MB, 461 k triángulos, 9135 piezas de pretil. Contrato OK; 0 NaN, 0 volumen negativo, todas
  estancas. Sin cambios en la colisión (las huellas no cambian).
- El shader de fachadas sigue suponiendo plantas de 3 m: en edificios de 4 plantas con 15 m de LiDAR dibuja 5 filas
  de ventanas. Mejora posible: pasar el nº de plantas por vértice.
- **Medidas** (1080p emulado, lienzo 2400×1350): `?bench=20` órbita 111.2 FPS medio, 1 % low 71.4, GPU 6.33 ms p50;
  a pie 141.4 FPS, 1 % low 71.9, GPU 4.14 ms p50 (antes de las alturas LiDAR: 4.13 ms) → sin coste.
### 2026-10-26 · Relieve real (MDT05)
- **`tools/gis/dem.py`** (agente 01): reproyección bilineal del MDT05 a una malla local de 5 m en EPSG:25829 alineada
  con el origen (x0 = −3190, y1 = 2195, 1276×878), 80 m de margen (el MDT se descargó con 100 m; con 250 m faltaban
  datos), suavizado gaussiano separable en numpy (no hay scipy; sigma 3 celdas = 15 m) y **cota cero = 43 m** (terreno
  en el origen). Salida `data/processed/dem_local.tif` (float32, relativo) + `dem_local.json`. Relativo −28.9 … +36.2 m.
  El suavizado mueve el MDT p50 0.19 m, p99 0.87 m, máx 3.8 m (cornisa); el sombreado confirma que desaparecen las
  terrazas de la cuantización entera sin perder valles ni terraplenes.
  `LocalDEM.sample(x, y)` (bilineal) y **`LocalDEM.sample_mesh(x, y)`**: altura de la malla del terreno tal como se
  dibuja (lineal por triángulos). **`MESH_CELL_M = 20`** en `dem.py` es la única fuente del tamaño de celda.
- **Terreno** (`build_terrain_glb.py`): **continuo, sin recortar viales ni piscinas** (recortar con relieve deja grietas
  en las costuras); malla regular de 20 m por tesela (celdas interiores como cuadrícula compartida, las del borde
  recortadas y trianguladas sin densificar para compartir vértices). 72.6 k triángulos (con 10 m eran 284 k), 2.39 MB.
  Piscinas: lámina **horizontal** a la cota máxima de la malla bajo la piscina + 3 cm; borde extruido desde 15 cm bajo
  el terreno hasta 6 cm sobre el agua.
- **Viales** (`build_roads_glb.py`): a 0.06 m sobre la malla del terreno. **Trampa:** drapear solo los vértices no
  basta: earcut une vértices lejanos de una franja larga y en ladera el triángulo atravesaba el terreno (hasta 4.6 m
  bajo él en el centroide); y muestrear el MDT bilineal en vez de la malla dejaba la calzada hasta 22 cm bajo el
  terreno en los terraplenes. Solución: `split_by_terrain_triangles` recorta cada superficie con los triángulos de la
  malla del terreno (cada trozo en un único plano) y se muestrea con `sample_mesh` → paralelo al terreno en todos sus
  puntos. Aceras: tapa recortada igual a +0.21 m y bordillos levantados tramo a tramo (cada 4 m; con 1 m eran 317 k
  triángulos solo de bordillo). Viales: 132 k triángulos, 3.1 MB.
- **Edificios** (`build_buildings_glb.py`): cada parte arranca 0.3 m bajo el punto más bajo de la malla del terreno en su
  contorno y su cubierta queda a la cota mediana del terreno + `height_m`; pretiles sobre esa cubierta. 10.03 MB.
- **Árboles** (`build_trees.py`): quinto campo `y` = cota de la malla del terreno (formato `[x, z, tipo, escala, y]`;
  `sync-models` acepta 4 o 5 campos); el visor los hunde 10 cm.
- **Visor** (agente 02/03):
  - `facades.js`: atributos `facade` (u, longitud, tipo, cota del suelo = arranque + 0.3) y `facadeTop` (coronación
    sobre el suelo); ventanas, zócalo y cornisa se miden desde el suelo del muro, no desde Y = 0.
  - `collision.js`: la arista inferior de cada muro se toma por la cota mínima del triángulo (antes Y < 0.05).
  - **`character/groundIndex.js` (`GroundIndex`)**: rejilla en planta de 5 m con los triángulos de TERRAIN_/ROAD_/
    POOL_; altura por baricéntricas, la superficie más alta bajo `fromY`. **Trampa:** el Raycaster de Three.js tardaba
    4.3 ms por consulta (el rayo vertical cruza las esferas de 11 teselas y prueba todos sus triángulos) y
    `player.update` subía a 9.5 ms → 82 FPS a pie con la GPU en 5 ms. Con el índice: 0.3 ms. Además el rayo tenía
    `far = fromY + 5`, que con cotas negativas (zonas bajas) daba alcance negativo y dejaba sin suelo al personaje.
  - `controller.js`: aparición buscando suelo desde Y = 300. `ortho.js`: caja de distancia con las cotas reales.
  - `ground.js`: materiales de viales y piscinas con `polygonOffset` (−2, −4), porque van encima del terreno continuo.
- **QA** (`qa_relief`, muestreando la malla del terreno exacta): vértices y centroides de calzada, aceras, caminos y
  peatonal a +0.060 m en todos los puntos (0 bajo el terreno); agua de piscinas ≥ +0.030 m; ningún edificio con vértice
  inferior sobre el terreno (mín. 0.10 m enterrado). Contratos OK; 0 NaN; edificios estancos; 11 astillas casi
  verticales (<0.12 m²) en el borde del término, no invertidas. Personaje: sigue el terreno (26.8 m corriendo, Y de
  3.08 a 2.00 y apoyado), colisión intacta (64 754 muros, se detiene a 0.320 m del muro).
- **Medidas** (1080p emulado, lienzo 2400×1350): a pie 142.1 FPS, 1 % low 72.5, GPU 4.51 ms (sin relieve 4.14);
  `?bench=20` órbita 90.9 FPS, 1 % low 70.9, GPU 8.37 ms (sin relieve 6.33; el terreno continuo se dibuja también bajo
  los viales). Cumple ≥60 FPS.
### 2026-10-26 · Árboles reales (MDSn de vegetación)
- **`tools/gis/lidar_trees.py`** (agente 01): MDSn de vegetación reproyectado (vecino más próximo, para no rebajar
  cimas) a malla local de 2.5 m; cima = píxel ≥ 2 m que es máximo de su ventana 3×3 (5×5 si supera 7 m), ordenando por
  `altura + 0.01·gaussiana(σ 0.7 px)` para desempatar las mesetas de valores enteros. Radio de copa por alometría
  `clip(0.35·h + 0.5, 1.2, 6)`. 141 987 cimas en el rectángulo del término.
  **Trampa:** umbralizar la altura suavizada (versión inicial, 2.5 m) borraba casi todos los olivos: dan 2–3 m en el
  dato entero y un píxel aislado de 3 m rodeado de ceros queda en ~1 m tras el gaussiano. Validado dibujando las cimas
  sobre la ortofoto: en el casco caen sobre las copas de los jardines; en el olivar salen casi todos los olivos de las
  hileras; de los árboles dispersos de algunas parcelas de secano salen pocos (bajos o posteriores al vuelo).
- **`build_trees.py --source lidar`** (por defecto; `--source osm` conserva el método de la fase 1): se descartan los
  que caen en edificios (+0.5 m), calzada, caminos, piscinas o fuera del término; los de acera se mantienen (alcorques).
  Tipo por contexto: huerto OSM → olivo, bosque → pino, parque/jardín → sombra, matorral ≤3 m → arbusto, casco urbano →
  sombra, campo → olivo hasta 5 m y sombra si es más alto. Escala vertical = altura / altura del modelo y horizontal =
  radio / radio del modelo (constantes `MODEL_TOP_M` / `MODEL_RADIUS_M`, que deben seguir a `SHAPES` de `trees.js`).
  Resultado: **72 464 árboles** (61 246 olivos, 11 006 de sombra, 142 pinos, 70 arbustos), altura p50 3 m, p95 5 m,
  máx. 30 m. JSON con 6 campos `[x, z, tipo, escala, y, ancho]`, 2.4 MB; `sync-models` acepta de 4 a 6 campos.
- Visor: `trees.js` compone cada instancia con escala (ancho, escala, ancho). LOD sin cambios (sombra < 220 m, copa
  simple > 350 m, ocultos > 2200 m): 163 mallas, a pie ~11 teselas en alta y 6 con sombra.
- **Medidas** (1080p emulado): `?bench=20` órbita 83.9 FPS medio, 1 % low 69.4, GPU 8.97 ms (con los árboles de OSM:
  8.37); a pie 135.9 FPS, 1 % low 71.9, GPU 5.15 ms (antes 4.51). Cumple ≥60 FPS; coste ~0.6 ms por pasar de 30 k a 72 k
  árboles.
### 2026-10-26 · Ventanas por planta real
- `build_buildings_glb.py`: atributo de vértice con las plantas de Catastro de cada parte (`mesh.vertex_attributes
  ["floors"]`, concatenado en el mismo orden que los vértices). trimesh lo exporta como atributo glTF **`_floors`**
  (minúsculas, no `_FLOORS`) y el GLTFLoader lo carga como `geometry.attributes._floors`. Partes con plantas nulas → 1.
  Valores: 1–5 plantas en las 2793 mallas `COL_`. GLB de edificios 10.46 MB.
- `facades.js`: `facadeTop` pasa a vec2 (coronación sobre el suelo, plantas). Altura de planta =
  `clamp(coronación / plantas, 2.4, 6)`; se dibujan tantas filas como plantas; alféizar a 0.32·planta y hueco
  `min(1.3, 0.45·planta)` (en 3 m: 0.96–2.26, igual que antes); escaparates de planta baja a 0.12–0.87·planta. Sin
  `_floors` (GLB antiguo) las plantas se estiman como coronación / 3 m.
- Comprobado en el visor: el bloque de 4 plantas y 15 m de `5540801QB5354S` muestra 4 filas de ventanas (antes 5) y las
  casas de una planta (≈4 m) una sola fila. Los tres programas de fachada (house, shop, shed) compilan.
- **Trampa de depuración:** la consola del panel conserva errores de recargas en caliente antiguas (misma marca `?t=`);
  comprobar con `renderer.info.programs` o con un error nuevo antes de buscar fallos. `window.__almensilla.controls`
  expuesto para colocar la cámara en vista aérea (OrbitControls reorienta la cámara a su objetivo en cada fotograma).
- FPS no vuelto a medir: el cambio solo añade un float por vértice y unas operaciones en el shader.
- Orden del pipeline: extract_catastro_buildings → apply_lidar_heights → dem → build_buildings → build_roads →
  build_terrain → build_trees → build_ortho_textures (descargas con download_ign.py).

### 2026-10-26 · Pipeline reproducible y pruebas automáticas
- Git: el usuario commiteó todo como «Fase 2» (`1a28562`) antes de empezar.
- **`tools/gis/run_pipeline.py`**: ejecuta los pasos en orden con `python -P` y se para en el primer fallo;
  `--download` (incluye download_ign, idempotente), `--from <paso>`, `--only <pasos…>`, `--sync` (npm run sync-models)
  y `--test` (pytest). Pasos: download, extract, lidar, dem, buildings, roads, terrain, trees, ortho.
  Ejecución completa con sync y test: **95 s** (edificios 24 s, viales 32 s).
- **Reproducibilidad comprobada:** regenerando todo desde cero, los 182 ficheros de `data/export` y `data/processed`
  salen idénticos byte a byte (SHA-256) a los anteriores; Git no ve cambios en los datos versionados.
- **Pruebas** (`tests/`, pytest 9.0.3, añadido a requirements junto a pillow 12.2.0; `python -P -m pytest tests`,
  30 pruebas en ~5 s):
  - `conftest.py`: fixtures de sesión (GLB con trimesh, árboles, DEM) y **`TerrainSurface`**, que calcula la altura
    con los triángulos del GLB de terreno (no con la función de muestreo del pipeline, para no ser tautológico).
    Si falta una salida, la prueba se salta indicando que hay que ejecutar run_pipeline.
  - `test_contracts.py`: contrato `validate_glb.py` (importado del script), cabecera GLB, estructura del JSON de
    árboles, índice y tamaños de la ortofoto (con atribución CC BY 4.0), cobertura de ortofoto de todas las teselas de
    terreno, y que `app/public/models` coincida con `data/export` (SHA-256).
  - `test_geometry.py`: sin NaN/inf, nombres de nodo (`COL_`, `PARAPET_`, `ROAD_*`, `TERRAIN_`, `POOL_*`) únicos,
    edificios estancos con volumen positivo, atributo `_floors` 1–10, suelos sin caras invertidas, aceras sin caras hacia
    abajo, extensión y cotas comunes.
  - `test_seams.py`: vértices y centroides de calzada/caminos/peatonal, tapas de acera (>0.1 m) y agua de piscinas sobre
    el terreno; base de todos los edificios bajo él; árboles a <5 cm del terreno.
  - `test_qa_criteria.py`: criterio 3 (mediana de calles principales en 6–10 m y ≥70 % de su longitud), alturas
    verosímiles (≤25 m, ≥80 % LiDAR), metadatos del DEM, recuento y tipos de árboles. El criterio 2 (FPS) sigue siendo
    manual con `?bench=20`.
  - Comprobado que las pruebas fallan cuando deben: bajando la calzada 20 cm en memoria, los 800 puntos de muestra
    quedan bajo el terreno.
- `README.md` (antes vacío): requisitos, visor, regenerar datos, pruebas y atribución.

### Pendiente / bloqueos
- Git: todo subido (2026-10-26). PR #2 fusionó `gis/catastro-buildings-glb` en `main`; la fase 1 y el LOD están en
  `main` (commit `19be153`). El usuario sigue gestionando Git a mano.
- Fase 1, cosas que faltan: puertas (se podrían colocar en las 3131 entradas de portal de AD), pasos de cebra
  (93 nodos `crossing`), árboles de alineación en aceras (no están en OSM), colisión con árboles, el personaje
  "flota" sobre el agua de las piscinas, tejados de teja.
- Sombras: fuera del radio del mapa (≤512 m del foco) no hay sombra; en vista aérea muy lejana se nota el corte
  (lo suaviza la niebla). Si hiciera falta: cascadas (CSM) o desvanecer la sombra en el borde del mapa.
- Personaje: la cámara muy cerca (contra un muro) queda dentro de la cabeza; se podría atenuar el monigote cuando la
  cámara está a menos de ~1 m. Huecos entre edificios más estrechos que 0.64 m no son transitables (es lo deseado).
- Controles solo de teclado y ratón (sin táctil ni mando).
- Decidir qué hacer con las 184 partes de 0 plantas: provisionalmente se omiten en el GLB de edificios.
- Relieve: el terreno es plano. Para cota real haría falta el MDT05 del CNIG/IGN (lo descarga el usuario); entonces
  habrá que asentar edificios y viales sobre el MDT y resolver los puentes (`bridge=*`, `layer`).
- Fuera del término municipal no hay suelo: de momento lo tapa la niebla (700–3600 m); con zoom lejano se ve el borde.
- trimesh no tiene `networkx` (algunas utilidades de `trimesh.repair` fallan); no hace falta para la extrusión.
