#!/usr/bin/env python3
"""Terreno plano del término municipal a GLB (glTF 2.0).

No hay modelo digital del terreno en `data/raw` (ver `.claude/MEMORY.md`): el terreno es un plano en Y=0
con la forma del término municipal (unión de CadastralZoning, 14.035 km²).

Para evitar z-fighting con `almensilla_roads.glb` (viales a Y=0.02 m) se recortan del terreno las mismas
superficies de vial, reconstruidas con las funciones de `build_roads_glb.py` a partir de
`data/processed/osm_roads.geojson`: terreno y viales no se solapan.

Salida: `data/export/almensilla_terrain.glb`
  * Teselas de TILE_M (las mismas que los viales), nodos `TERRAIN_<i>_<j>` (caminable, sin `COL_`).
  * Ejes glTF: X = Este, Y = arriba, Z = -Norte; mismo origen local que edificios y viales.

Uso:
    python -P tools/gis/build_terrain_glb.py
    python -P tools/gis/build_terrain_glb.py --no-cut-roads
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import shapely
import trimesh
from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_roads_glb as roads_glb  # noqa: E402

ROOT = roads_glb.ROOT
DEFAULT_OUTPUT = ROOT / "data/export/almensilla_terrain.glb"
TERRAIN_Y = 0.0
TERRAIN_COLOR = (150, 156, 112, 255)  # tierra/vegetación seca del Aljarafe


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--cp-zip", type=Path, default=roads_glb.DEFAULT_CP_ZIP)
    ap.add_argument("--meta", type=Path, default=roads_glb.DEFAULT_META, help="meta.json con el origen local")
    ap.add_argument("--lines", type=Path, default=roads_glb.DEFAULT_LINES, help="Ejes de vial (osm_roads.geojson)")
    ap.add_argument("--buildings", type=Path, default=roads_glb.DEFAULT_BUILDINGS)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--tile", type=float, default=roads_glb.TILE_M, help="Lado de tesela en metros")
    ap.add_argument("--no-cut-roads", action="store_true", help="No recortar las superficies de vial")
    args = ap.parse_args(argv)

    origin = roads_glb.load_origin(args.meta)
    municipality, _, _ = roads_glb.load_cadastre(args.cp_zip, origin)
    ground = municipality
    road_area = 0.0
    if not args.no_cut_roads:
        if not args.lines.exists():
            sys.exit(f"[ERROR] {args.lines} no existe: ejecuta antes build_roads_glb.py (o usa --no-cut-roads)")
        lines = gpd.read_file(args.lines)
        footprints = gpd.read_file(args.buildings).union_all() if args.buildings.exists() else None
        surfaces = roads_glb.build_surfaces(lines, municipality, footprints)
        road_union = shapely.union_all(list(surfaces.values()))
        road_area = road_union.area
        ground = municipality.difference(road_union)

    material = trimesh.visual.material.PBRMaterial(name="MAT_terrain", baseColorFactor=TERRAIN_COLOR,
                                                   metallicFactor=0.0, roughnessFactor=1.0)
    scene = trimesh.Scene()
    minx, miny, maxx, maxy = municipality.bounds
    for i in range(int(np.floor(minx / args.tile)), int(np.floor(maxx / args.tile)) + 1):
        for j in range(int(np.floor(miny / args.tile)), int(np.floor(maxy / args.tile)) + 1):
            tile = box(i * args.tile, j * args.tile, (i + 1) * args.tile, (j + 1) * args.tile)
            mesh = roads_glb.flat_mesh(roads_glb.polygons_of(ground.intersection(tile)), TERRAIN_Y)
            if mesh is None:
                continue
            mesh.visual = trimesh.visual.TextureVisuals(material=material)
            name = f"TERRAIN_{i}_{j}"
            mesh.metadata = {"tile": [i, j], "tile_m": args.tile, "area_m2": round(float(mesh.area), 1)}
            scene.add_geometry(mesh, node_name=name, geom_name=name)
    scene.metadata = {"source": args.cp_zip.name, "axes": "X=East, Y=Up, Z=-North", "units": "m",
                      "terrain_y_m": TERRAIN_Y, "flat": True, "roads_cut": not args.no_cut_roads,
                      "walkable_prefix": "TERRAIN_"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(scene.export(file_type="glb"))

    mesh_area = sum(g.area for g in scene.geometry.values())
    summary = {
        "output": args.output.name, "origin_epsg25829": list(origin),
        "municipality_km2": round(municipality.area / 1e6, 4),
        "roads_cut_m2": round(road_area), "ground_m2": round(ground.area), "mesh_area_m2": round(mesh_area),
        "nodes": len(scene.geometry),
        "triangles": int(sum(len(g.faces) for g in scene.geometry.values())),
        "bounds_gltf": np.round(scene.bounds, 3).tolist(),
        "size_mb": round(args.output.stat().st_size / 2**20, 2),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
