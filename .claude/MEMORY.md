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

### Pendiente / bloqueos
- Push/PR de `gis/catastro-buildings-glb` y de los cambios de viales, terreno, visor, personaje y sombras: lo hace el usuario a mano.
- Sombras: fuera del radio del mapa (≤512 m del foco) no hay sombra; en vista aérea muy lejana se nota el corte
  (lo suaviza la niebla). Si hiciera falta: cascadas (CSM) o desvanecer la sombra en el borde del mapa.
- Personaje: la cámara muy cerca (contra un muro) queda dentro de la cabeza; se podría atenuar el monigote cuando la
  cámara está a menos de ~1 m. Huecos entre edificios más estrechos que 0.64 m no son transitables (es lo deseado).
- Controles solo de teclado y ratón (sin táctil ni mando).
- Decidir qué hacer con las 184 partes de 0 plantas: provisionalmente se omiten en el GLB de edificios.
- Relieve: el terreno es plano. Para cota real haría falta el MDT05 del CNIG/IGN (lo descarga el usuario); entonces
  habrá que asentar edificios y viales sobre el MDT y resolver los puentes (`bridge=*`, `layer`).
- Fuera del término municipal no hay suelo: de momento lo tapa la niebla (700–3600 m); con zoom lejano se ve el borde.
- Aceras/calzada no se distinguen: la superficie de vial es de fachada a fachada.
- trimesh no tiene `networkx` (algunas utilidades de `trimesh.repair` fallan); no hace falta para la extrusión.
