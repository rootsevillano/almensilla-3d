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


def parapets(group: gpd.GeoDataFrame, tops: list[float]) -> list[trimesh.Trimesh]:
    """Pretiles de las partes de un edificio, en coordenadas locales (z = arriba), sobre la cota de su cubierta.

    El tramo de borde que linda con otra parte del mismo edificio igual o más alta se quita: ahí la cubierta
    continúa (o sube un muro), no hay pretil.
    """
    meshes = []
    geoms, heights = list(group.geometry), tops
    for i, (geom, h) in enumerate(zip(geoms, heights)):
        if geom.area < PARAPET_MIN_AREA_M2:
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
    for building_id, group in parts.groupby("buildingId", sort=True):
        levels = [part_levels(geom, float(h), dem) for geom, h in zip(group.geometry, group["height_m"])]
        meshes, floors = [], []
        part_floors = [max(1, int(f)) if f == f and f is not None else 1
                       for f in group["numberOfFloorsAboveGround"]]
        for geom, (base, top), nf in zip(group.geometry, levels, part_floors):
            for m in extrude(geom, top - base):
                m.apply_translation([0.0, 0.0, base])
                meshes.append(m)
                floors.append(np.full(len(m.vertices), nf, dtype=np.float32))
        if not meshes:
            stats["empty_buildings"] += 1
            continue
        use = group["currentUse"].iloc[0]
        if not args.no_parapets and use not in NO_PARAPET_USES:
            rails = parapets(group, [top for _, top in levels])
            if rails:
                stats["parapet_pieces"] += len(rails)
                c = group.geometry.union_all().centroid
                parapets_by_tile.setdefault((int(c.x // TILE_M), int(c.y // TILE_M)), []).extend(rails)
        mesh = trimesh.util.concatenate(meshes)
        # plantas de Catastro por vértice (concatenate apila los vértices en el mismo orden): el visor reparte las
        # ventanas con altura de planta = altura del muro / plantas. Se exporta como atributo glTF `_floors`.
        mesh.vertex_attributes["floors"] = np.concatenate(floors)
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

    scene.metadata = {"source": args.input.name, "axes": "X=East, Y=Up, Z=-North",
                      "units": "m", "collision_prefix": COLLISION_PREFIX, "decor_prefix": PARAPET_PREFIX}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(scene.export(file_type="glb"))

    summary = {
        "output": str(args.output.relative_to(ROOT) if args.output.is_relative_to(ROOT) else args.output),
        "nodes": stats["buildings"], "parts_extruded": stats["parts"], "parts_skipped_zero_height": skipped,
        "empty_buildings": stats["empty_buildings"], "materials": len(materials),
        "parapet_pieces": stats["parapet_pieces"],
        "vertices": int(sum(len(g.vertices) for g in scene.geometry.values())),
        "triangles": int(sum(len(g.faces) for g in scene.geometry.values())),
        "bounds_gltf": np.round(scene.bounds, 3).tolist(),
        "size_mb": round(args.output.stat().st_size / 2**20, 2),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
