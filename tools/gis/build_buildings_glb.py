#!/usr/bin/env python3
"""Extrusión de BuildingPart de Catastro a GLB (glTF 2.0) para el visor.

Entrada: `data/processed/catastro_building_parts.geojson` (salida de extract_catastro_buildings.py),
ya en coordenadas métricas locales (x=E-E0, y=N-N0), anillos exterior CCW / interiores CW,
con `height_m` calculado según el contrato del agente 01.

Salida: `data/export/almensilla_buildings.glb`
  * Un nodo por Building catastral: `COL_<localId>` (contrato: prefijo COL_ = colisionable),
    cuya malla fusiona las extrusiones de sus BuildingPart.
  * Pretiles de azotea (0.9 m, salvo naves) en nodos decorativos `PARAPET_<i>_<j>` por tesela de 500 m
    (no colisionables, sin cara inferior), material `MAT_parapet`.
  * Ejes glTF (Y arriba, dextrógiro): X = Este, Y = altura, Z = -Norte. Asentados sobre el MDT (`dem.py`): cada
    parte arranca 0.3 m bajo el punto más bajo del terreno en su contorno y su cubierta queda a la cota mediana
    del terreno + `height_m`.
  * Un material PBR compartido por `currentUse`.
  * extras de malla: localId, currentUse, nº de partes, altura máxima. Atributo de vértice `_floors`: plantas de
    Catastro de la parte a la que pertenece cada vértice (para repartir las ventanas en el visor).

Uso:
    python -P tools/gis/build_buildings_glb.py
    python -P tools/gis/build_buildings_glb.py --input data/processed/catastro_building_parts.geojson \
        --output data/export/almensilla_buildings.glb --zero-floor-height 0.3
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import geopandas as gpd
import numpy as np
import shapely
import trimesh
from shapely.geometry import MultiPolygon, Polygon

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dem import LocalDEM  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "data/processed/catastro_building_parts.geojson"
DEFAULT_OUTPUT = ROOT / "data/export/almensilla_buildings.glb"
DEFAULT_META = ROOT / "data/processed/catastro_buildings.meta.json"
COLLISION_PREFIX = "COL_"

# Local (x=E, y=N, z=arriba) -> glTF (X=E, Y=arriba, Z=-N). Rotación de -90° sobre X.
LOCAL_TO_GLTF = np.array([
    [1.0, 0.0, 0.0, 0.0],
    [0.0, 0.0, 1.0, 0.0],
    [0.0, -1.0, 0.0, 0.0],
    [0.0, 0.0, 0.0, 1.0],
])

# RGBA base por currentUse (valores observados en building.gml)
USE_COLORS = {
    "1_residential": (236, 226, 208, 255),
    "2_agriculture": (196, 178, 140, 255),
    "3_industrial": (176, 180, 186, 255),
    "4_1_office": (210, 214, 222, 255),
    "4_2_retail": (230, 200, 170, 255),
    "4_3_publicServices": (214, 190, 196, 255),
    None: (220, 220, 220, 255),
}


def material_for(use: str | None, cache: dict) -> trimesh.visual.material.PBRMaterial:
    key = use if use in USE_COLORS else None
    if key not in cache:
        cache[key] = trimesh.visual.material.PBRMaterial(
            name=f"MAT_{key or 'unknown'}", baseColorFactor=USE_COLORS[key],
            metallicFactor=0.0, roughnessFactor=0.9)
    return cache[key]


PINCH_EROSION_M = 0.001


def separate_pinched_holes(poly: Polygon) -> list[Polygon]:
    """Patio que toca el contorno exterior en un punto (válido OGC, 3 casos en 41010):
    la extrusión deja un vértice no-manifold. Una erosión de 1 mm abre el contacto."""
    if not any(poly.exterior.intersects(hole) for hole in poly.interiors):
        return [poly]
    eroded = poly.buffer(-PINCH_EROSION_M, join_style="mitre")
    return list(eroded.geoms) if isinstance(eroded, MultiPolygon) else [eroded]


def extrude(geom: Polygon | MultiPolygon, height: float) -> list[trimesh.Trimesh]:
    polys = geom.geoms if isinstance(geom, MultiPolygon) else [geom]
    meshes = []
    for p in polys:
        for q in separate_pinched_holes(p):
            if q.is_empty:
                continue
            # earcut deja algunos triángulos de área ~0 (vértices alineados); no se eliminan
            # porque cierran la topología y quitarlos rompe la estanqueidad.
            meshes.append(trimesh.creation.extrude_polygon(q, height))
    return meshes


# Pretil de azotea (casa andaluza): anillo sobre el borde de la cubierta. Las naves no llevan.
PARAPET_HEIGHT_M = 0.9
PARAPET_THICKNESS_M = 0.2
PARAPET_MIN_AREA_M2 = 6.0
NO_PARAPET_USES = {"3_industrial", "2_agriculture"}
PARAPET_PREFIX = "PARAPET_"
PARAPET_COLOR = (244, 242, 234, 255)
TILE_M = 500.0  # mismas teselas que terreno, viales y árboles


FOUNDATION_SINK_M = 0.3  # los muros arrancan bajo el punto más bajo del terreno: nada flota en ladera


def part_levels(geom: Polygon, height: float, dem) -> tuple[float, float]:
    """(arranque, cubierta) de una parte: arranca bajo el punto más bajo del terreno en su contorno y la cubierta
    queda a la cota mediana del terreno + su altura (altura sobre el suelo, como el LiDAR y el Catastro)."""
    if dem is None:
        return 0.0, height
    ring = np.asarray(shapely.segmentize(geom.exterior, 3.0).coords)
    ground = dem.sample_mesh(np.r_[ring[:, 0], geom.centroid.x], np.r_[ring[:, 1], geom.centroid.y])
    return float(ground.min()) - FOUNDATION_SINK_M, float(np.median(ground)) + height


# Tejado de teja a cuatro aguas (chalés de las urbanizaciones; tipo de cubierta en classify_roofs.py)
ROOF_PREFIX = "ROOF_"
ROOF_COLOR = (178, 96, 66, 255)  # teja árabe envejecida
ROOF_SLOPE = 0.30  # 30 % (~17°)
ROOF_MAX_RISE_M = 3.0
ROOF_OVERHANG_M = 0.30
HIP_MIN_AREA_M2 = 20.0
HIP_MIN_RECTANGULARITY = 0.85  # área / área del rectángulo mínimo
HIP_SHORT_SIDE_M = (4.0, 20.0)
HIP_EAVE_FACTOR = 0.4  # la altura LiDAR (mediana) de un tejado inclinado cae a ~40 % de la subida sobre el alero


def hip_frame(geom: Polygon):
    """(esquinas CCW del rectángulo mínimo con el lado largo primero, lado corto W, lado largo L) o None si la parte
    no es casi rectangular o su tamaño no encaja con un tejado a cuatro aguas."""
    if geom.area < HIP_MIN_AREA_M2:
        return None
    rect = shapely.orient_polygons(geom.minimum_rotated_rectangle)
    if geom.area / rect.area < HIP_MIN_RECTANGULARITY:
        return None
    c = np.asarray(rect.exterior.coords)[:4]
    sides = np.linalg.norm(np.roll(c, -1, axis=0) - c, axis=1)
    if sides[0] < sides[1]:  # que c0→c1 sea un lado largo
        c = np.roll(c, -1, axis=0)
        sides = np.roll(sides, -1)
    long_, short = float(sides[0]), float(sides[1])
    if not (HIP_SHORT_SIDE_M[0] <= short <= HIP_SHORT_SIDE_M[1]):
        return None
    return c, short, long_


def hip_roof(corners: np.ndarray, short: float, long_: float, eave: float, rise: float) -> trimesh.Trimesh:
    """Tejado a cuatro aguas sobre el rectángulo (z = arriba): cumbrera a lo largo del lado largo, alero volado."""
    center = corners.mean(axis=0)
    u = (corners[1] - corners[0]) / long_  # eje largo
    v = (corners[3] - corners[0]) / short  # eje corto
    hl, hs = long_ / 2 + ROOF_OVERHANG_M, short / 2 + ROOF_OVERHANG_M
    drop = ROOF_OVERHANG_M * ROOF_SLOPE  # el alero volado baja con la pendiente
    eaves = [center + a * hl * u + b * hs * v for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    ridge_half = max(0.0, long_ / 2 - short / 2)  # cuadrado: pirámide (cumbrera de longitud 0)
    r0, r1 = center - ridge_half * u, center + ridge_half * u
    vz = [eave - drop] * 4 + [eave + rise] * 2
    verts = np.c_[np.vstack(eaves + [r0, r1]), vz]
    faces = np.array([[0, 1, 5], [0, 5, 4],  # faldón largo (lado c0-c1)
                      [2, 3, 4], [2, 4, 5],  # faldón largo opuesto
                      [1, 2, 5],             # faldón corto
                      [3, 0, 4],             # faldón corto opuesto
                      [0, 3, 2], [0, 2, 1]])  # cara inferior del alero (hacia abajo)
    mesh = trimesh.Trimesh(verts, faces, process=False)
    # orientación: faldones hacia arriba, cara inferior hacia abajo
    n = mesh.face_normals
    flip = np.r_[n[:6, 2] < 0, n[6:, 2] > 0]
    mesh.faces[flip] = mesh.faces[flip][:, ::-1]
    return mesh


# Puertas en los portales del fichero de direcciones del Catastro (AD)
DEFAULT_AD_ZIP = ROOT / "data/raw/catastro/A.ES.SDGC.AD.41010.zip"
DEFAULT_BUILDINGS = ROOT / "data/processed/catastro_buildings.geojson"
DOOR_PREFIX = "DOOR_"
DOOR_COLOR = (92, 60, 38, 255)  # madera
DOOR_W, DOOR_H, DOOR_T = 1.0, 2.15, 0.06
DOOR_MIN_WALL_M = 1.6


def load_entrances(ad_zip: Path, origin) -> gpd.GeoDataFrame:
    """Portales (Address con specification=Entrance) en coordenadas locales con la referencia catastral del edificio.
    Inspección: el punto marca la entrada a la parcela (mediana a 4.2 m de la fachada), no la puerta del edificio."""
    ad = gpd.read_file(f"/vsizip/{ad_zip.as_posix()}/{ad_zip.stem}.gml", layer="Address")
    ad = ad[ad["specification"] == "Entrance"]
    x = ad.geometry.x.to_numpy() - origin[0]
    y = ad.geometry.y.to_numpy() - origin[1]
    refcat = ad["localId"].str.split(".").str[-1]  # 41.010.<vía>.<número>.<refcat14>
    return gpd.GeoDataFrame({"refcat": refcat.to_numpy()}, geometry=shapely.points(x, y))


def door_meshes(entrances, footprints: gpd.GeoDataFrame, dem) -> tuple[dict, Counter]:
    """Una puerta por portal en la fachada exterior del edificio más cercana al portal (descartando medianeras)."""
    by_ref = {r: g for r, g in zip(footprints["localId"], footprints.geometry)}
    tree = shapely.STRtree(footprints.geometry.values)
    doors_by_tile: dict[tuple[int, int], list[trimesh.Trimesh]] = {}
    placed: dict[str, list[np.ndarray]] = {}
    stats = Counter()
    for ref, pt in zip(entrances["refcat"], entrances.geometry):
        geom = by_ref.get(ref)
        if geom is None:
            stats["no_building"] += 1
            continue
        best = None
        for poly in getattr(geom, "geoms", [geom]):
            ring = np.asarray(shapely.orient_polygons(poly).exterior.coords)
            for a, b in zip(ring[:-1], ring[1:]):
                seg = b - a
                length = float(np.hypot(*seg))
                if length < DOOR_MIN_WALL_M:
                    continue
                d = seg / length
                normal = np.array([d[1], -d[0]])  # exterior CCW: hacia fuera
                t = float(np.clip(np.dot(np.array([pt.x, pt.y]) - a, d), 0.8, length - 0.8))
                center = a + d * t
                probe = shapely.Point(*(center + normal * 0.6))
                if len(tree.query(probe, predicate="within")):  # al otro lado hay otro edificio: medianera
                    continue
                dist = float(np.hypot(pt.x - center[0], pt.y - center[1]))
                if best is None or dist < best[0]:
                    best = (dist, center, d, normal)
        if best is None:
            stats["no_free_wall"] += 1
            continue
        _, center, d, normal = best
        if any(np.hypot(*(center - c)) < 2.0 for c in placed.get(ref, [])):
            stats["duplicate"] += 1
            continue
        placed.setdefault(ref, []).append(center)
        ground = float(dem.sample_mesh(center[0], center[1])) if dem is not None else 0.0
        box = trimesh.creation.box(extents=[DOOR_W, DOOR_T, DOOR_H])
        frame = np.eye(4)
        frame[:3, 0] = [d[0], d[1], 0.0]
        frame[:3, 1] = [normal[0], normal[1], 0.0]
        frame[:3, 3] = [center[0] + normal[0] * 0.01, center[1] + normal[1] * 0.01, ground + DOOR_H / 2]
        box.apply_transform(frame)
        doors_by_tile.setdefault((int(center[0] // TILE_M), int(center[1] // TILE_M)), []).append(box)
        stats["doors"] += 1
    return doors_by_tile, stats


def parapets(group: gpd.GeoDataFrame, tops: list[float], skip: list[bool] | None = None) -> list[trimesh.Trimesh]:
    """Pretiles de las partes de un edificio, en coordenadas locales (z = arriba), sobre la cota de su cubierta.

    El tramo de borde que linda con otra parte del mismo edificio igual o más alta se quita: ahí la cubierta
    continúa (o sube un muro), no hay pretil. `skip`: partes sin pretil (cubierta de teja).
    """
    meshes = []
    geoms, heights = list(group.geometry), tops
    for i, (geom, h) in enumerate(zip(geoms, heights)):
        if geom.area < PARAPET_MIN_AREA_M2 or (skip and skip[i]):
            continue
        ring = geom.difference(geom.buffer(-PARAPET_THICKNESS_M, join_style="mitre"))
        neighbours = [g for j, (g, hj) in enumerate(zip(geoms, heights)) if j != i and hj >= h]
        if neighbours:
            ring = ring.difference(shapely.union_all(neighbours).buffer(PARAPET_THICKNESS_M + 0.05))
        # limpia astillas de las operaciones booleanas y quita vértices redundantes (pretil de 20 cm: 10 cm no se nota)
        ring = ring.buffer(0).simplify(0.1)
        polys = [p for p in getattr(ring, "geoms", [ring]) if isinstance(p, Polygon) and p.area > 0.05]
        for poly in polys:
            for m in extrude(poly, PARAPET_HEIGHT_M):
                m.apply_translation([0.0, 0.0, float(h)])
                meshes.append(m)
    return meshes


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--zero-floor-height", type=float, default=0.0,
                    help="Altura para partes con 0 plantas sobre rasante; 0 = omitirlas (por defecto)")
    ap.add_argument("--no-parapets", action="store_true", help="No generar pretiles en las azoteas")
    ap.add_argument("--flat", action="store_true", help="Sin relieve (no usar dem_local.tif)")
    ap.add_argument("--no-hip-roofs", action="store_true", help="Sin tejados a cuatro aguas (solo color de teja)")
    ap.add_argument("--no-doors", action="store_true", help="Sin puertas en los portales")
    ap.add_argument("--ad-zip", type=Path, default=DEFAULT_AD_ZIP, help="Direcciones del Catastro (portales)")
    ap.add_argument("--buildings", type=Path, default=DEFAULT_BUILDINGS, help="Huellas de Building")
    args = ap.parse_args(argv)
    dem = None if args.flat else LocalDEM.load()

    parts = gpd.read_file(args.input)
    required = {"localId", "buildingId", "currentUse", "height_m", "height_source"}
    missing = required - set(parts.columns)
    if missing:
        sys.exit(f"[ERROR] {args.input}: faltan columnas {sorted(missing)}")

    zero = parts["height_source"] == "catastro_zero_floors"
    parts.loc[zero, "height_m"] = args.zero_floor_height
    skipped = int((parts["height_m"] <= 0).sum())
    parts = parts[parts["height_m"] > 0]

    scene = trimesh.Scene()
    materials: dict = {}
    stats = Counter()
    parapets_by_tile: dict[tuple[int, int], list[trimesh.Trimesh]] = {}
    roofs_by_tile: dict[tuple[int, int], list[trimesh.Trimesh]] = {}
    for building_id, group in parts.groupby("buildingId", sort=True):
        levels = [part_levels(geom, float(h), dem) for geom, h in zip(group.geometry, group["height_m"])]
        meshes, floors, roof_attr = [], [], []
        part_floors = [max(1, int(f)) if f == f and f is not None else 1
                       for f in group["numberOfFloorsAboveGround"]]
        use = group["currentUse"].iloc[0]
        tiled = [rt == "tile" and use not in NO_PARAPET_USES
                 for rt in (group["roof_type"] if "roof_type" in group else ["flat"] * len(group))]
        c = group.geometry.union_all().centroid
        tile_key = (int(c.x // TILE_M), int(c.y // TILE_M))
        for geom, (base, top), nf, is_tile in zip(group.geometry, levels, part_floors, tiled):
            frame = hip_frame(geom) if is_tile and not args.no_hip_roofs else None
            if frame is not None:
                corners, short, long_ = frame
                rise = min(ROOF_MAX_RISE_M, ROOF_SLOPE * short / 2)
                eave = max(top - HIP_EAVE_FACTOR * rise, base + FOUNDATION_SINK_M + 2.2)
                roofs_by_tile.setdefault(tile_key, []).append(hip_roof(corners, short, long_, eave, rise))
                stats["hip_roofs"] += 1
                top = eave  # los muros llegan al alero; el tejado va aparte (ROOF_*)
            for m in extrude(geom, top - base):
                m.apply_translation([0.0, 0.0, base])
                meshes.append(m)
                floors.append(np.full(len(m.vertices), nf, dtype=np.float32))
                roof_attr.append(np.full(len(m.vertices), 1.0 if is_tile else 0.0, dtype=np.float32))
        if not meshes:
            stats["empty_buildings"] += 1
            continue
        if not args.no_parapets and use not in NO_PARAPET_USES:
            rails = parapets(group, [top for _, top in levels], skip=tiled)
            if rails:
                stats["parapet_pieces"] += len(rails)
                parapets_by_tile.setdefault(tile_key, []).extend(rails)
        mesh = trimesh.util.concatenate(meshes)
        # plantas de Catastro por vértice (concatenate apila los vértices en el mismo orden): el visor reparte las
        # ventanas con altura de planta = altura del muro / plantas. Se exporta como atributo glTF `_floors`.
        mesh.vertex_attributes["floors"] = np.concatenate(floors)
        # 1 = cubierta de teja (el shader pinta de teja la cubierta plana de las partes que no llevan tejado ROOF_)
        mesh.vertex_attributes["roof"] = np.concatenate(roof_attr)
        mesh.apply_transform(LOCAL_TO_GLTF)
        mesh.visual = trimesh.visual.TextureVisuals(material=material_for(use, materials))
        mesh.metadata = {"localId": building_id, "currentUse": use, "parts": len(group),
                         "max_height_m": float(group["height_m"].max())}
        name = f"{COLLISION_PREFIX}{building_id}"
        scene.add_geometry(mesh, node_name=name, geom_name=name)
        stats["buildings"] += 1
        stats["parts"] += len(group)

    # Pretiles: decoración, fuera de las mallas COL_ (no colisionan) y agrupados por tesela para que el visor
    # pueda quitarles la sombra y ocultarlos a distancia. Sin cara inferior: apoya en la azotea y no se ve.
    parapet_material = trimesh.visual.material.PBRMaterial(
        name="MAT_parapet", baseColorFactor=PARAPET_COLOR, metallicFactor=0.0, roughnessFactor=0.9)
    for (i, j), rails in sorted(parapets_by_tile.items()):
        mesh = trimesh.util.concatenate(rails)
        mesh.update_faces(mesh.face_normals[:, 2] > -0.9)
        mesh.remove_unreferenced_vertices()
        mesh.apply_transform(LOCAL_TO_GLTF)
        mesh.visual = trimesh.visual.TextureVisuals(material=parapet_material)
        name = f"{PARAPET_PREFIX}{i}_{j}"
        mesh.metadata = {"tile": [i, j], "tile_m": TILE_M, "pieces": len(rails)}
        scene.add_geometry(mesh, node_name=name, geom_name=name)

    # Tejados de teja y puertas: decoración por tesela, como los pretiles (no colisionan)
    decor = [(ROOF_PREFIX, roofs_by_tile, "MAT_roof_tile", ROOF_COLOR)]
    if not args.no_doors and args.ad_zip.exists() and args.buildings.exists():
        origin = json.loads(DEFAULT_META.read_text(encoding="utf-8"))["origin_epsg25829"]
        footprints = gpd.read_file(args.buildings)
        footprints = footprints[footprints["localId"].isin(parts["buildingId"])]  # solo edificios con volumen
        doors_by_tile, door_stats = door_meshes(load_entrances(args.ad_zip, origin), footprints, dem)
        stats.update({f"doors_{k}": v for k, v in door_stats.items()})
        decor.append((DOOR_PREFIX, doors_by_tile, "MAT_door", DOOR_COLOR))
    for prefix, by_tile, mat_name, color in decor:
        material = trimesh.visual.material.PBRMaterial(name=mat_name, baseColorFactor=color,
                                                       metallicFactor=0.0, roughnessFactor=0.85)
        for (i, j), pieces in sorted(by_tile.items()):
            mesh = trimesh.util.concatenate(pieces)
            mesh.apply_transform(LOCAL_TO_GLTF)
            mesh.visual = trimesh.visual.TextureVisuals(material=material)
            name = f"{prefix}{i}_{j}"
            mesh.metadata = {"tile": [i, j], "tile_m": TILE_M, "pieces": len(pieces)}
            scene.add_geometry(mesh, node_name=name, geom_name=name)

    scene.metadata = {"source": args.input.name, "axes": "X=East, Y=Up, Z=-North", "units": "m",
                      "collision_prefix": COLLISION_PREFIX, "decor_prefixes": [PARAPET_PREFIX, ROOF_PREFIX, DOOR_PREFIX]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(scene.export(file_type="glb"))

    summary = {
        "output": str(args.output.relative_to(ROOT) if args.output.is_relative_to(ROOT) else args.output),
        "nodes": stats["buildings"], "parts_extruded": stats["parts"], "parts_skipped_zero_height": skipped,
        "empty_buildings": stats["empty_buildings"], "materials": len(materials),
        "parapet_pieces": stats["parapet_pieces"], "hip_roofs": stats["hip_roofs"],
        "doors": {k[6:]: v for k, v in stats.items() if k.startswith("doors_")},
        "vertices": int(sum(len(g.vertices) for g in scene.geometry.values())),
        "triangles": int(sum(len(g.faces) for g in scene.geometry.values())),
        "bounds_gltf": np.round(scene.bounds, 3).tolist(),
        "size_mb": round(args.output.stat().st_size / 2**20, 2),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
