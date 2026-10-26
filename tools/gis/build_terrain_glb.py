#!/usr/bin/env python3
"""Terreno del término municipal con relieve real (MDT05 del IGN) a GLB (glTF 2.0).

Relieve: `data/processed/dem_local.tif` (`dem.py`: MDT05 reproyectado a EPSG:25829, suavizado, cotas relativas a
la del origen local). Forma: término municipal (unión de CadastralZoning, 14.035 km²).

El terreno es **continuo** (sin recortar viales ni piscinas): con relieve, recortar dejaría grietas en las costuras
porque las mallas se triangulan distinto. Viales y piscinas se dibujan encima, unos centímetros más altos, y el visor
les añade un desfase de profundidad (polygonOffset).

Salida: `data/export/almensilla_terrain.glb`
  * Teselas de TILE_M (las mismas que los viales), nodos `TERRAIN_<i>_<j>` (caminable, sin `COL_`): malla regular de
    CELL_M con cotas del MDT; las celdas del borde del término se recortan y triangulan.
  * Piscinas de Catastro (912 openAirPool, fuera de los viales): `POOL_water_<i>_<j>` (lámina **horizontal** a la cota
    máxima del terreno bajo la piscina + 3 cm) y `POOL_coping_<i>_<j>` (borde de 0.35 m que baja hasta el terreno).
  * Ejes glTF: X = Este, Y = arriba, Z = -Norte; mismo origen local que edificios y viales.

Uso:
    python -P tools/gis/build_terrain_glb.py
    python -P tools/gis/build_terrain_glb.py --no-pools
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import geopandas as gpd
import numpy as np
import shapely
import trimesh

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_roads_glb as roads_glb  # noqa: E402
from dem import MESH_CELL_M, LocalDEM  # noqa: E402

ROOT = roads_glb.ROOT
DEFAULT_OUTPUT = ROOT / "data/export/almensilla_terrain.glb"
DEFAULT_POOLS = ROOT / "data/processed/catastro_other_constructions.geojson"
TERRAIN_COLOR = (150, 156, 112, 255)  # tierra/vegetación seca del Aljarafe
CELL_M = MESH_CELL_M  # ver dem.py: debe coincidir con la partición de los viales
POOL_COPING_M = 0.35  # borde de piedra alrededor de la lámina de agua
POOL_WATER_ABOVE_M = 0.03
POOL_COPING_ABOVE_WATER_M = 0.06
POOL_COPING_BELOW_GROUND_M = 0.15
POOL_COLORS = {"water": (52, 160, 206, 255), "coping": (226, 220, 206, 255)}


def terrain_tile(municipality, i: int, j: int, tile: float, cell: float, dem: LocalDEM) -> trimesh.Trimesh | None:
    """Malla de la tesela (i, j): celdas interiores como cuadrícula compartida; las del borde, recortadas."""
    n = int(round(tile / cell))
    xs = i * tile + np.arange(n + 1) * cell
    ys = j * tile + np.arange(n + 1) * cell
    cx, cy = np.meshgrid(np.arange(n), np.arange(n))  # índice de celda (columna, fila desde el sur)
    cx, cy = cx.ravel(), cy.ravel()
    cells = shapely.box(xs[cx], ys[cy], xs[cx + 1], ys[cy + 1])
    inside = shapely.contains(municipality, cells)
    edge = ~inside & shapely.intersects(municipality, cells)
    if not inside.any() and not edge.any():
        return None

    meshes = []
    if inside.any():
        gx, gy = np.meshgrid(xs, ys)  # vértices de la cuadrícula, fila r = ys[r]
        verts = np.c_[gx.ravel(), gy.ravel(), dem.sample(gx.ravel(), gy.ravel())]
        a = cy[inside] * (n + 1) + cx[inside]
        b, c, d = a + 1, a + n + 2, a + n + 1  # (c+1,r), (c+1,r+1), (c,r+1)
        faces = np.r_[np.c_[a, b, c], np.c_[a, c, d]]  # CCW visto desde arriba
        grid = trimesh.Trimesh(verts, faces, process=False)
        grid.remove_unreferenced_vertices()
        grid.apply_transform(roads_glb.LOCAL_TO_GLTF)
        meshes.append(grid)
    if edge.any():
        pieces = [p for g in shapely.intersection(cells[edge], municipality) for p in roads_glb.polygons_of(g)]
        # sin densificar: los vértices quedan en las esquinas y cortes de celda, igual que la cuadrícula
        border = roads_glb.flat_mesh(pieces, 0.0, dem, segment=False)
        if border is not None:
            meshes.append(border)
    mesh = trimesh.util.concatenate(meshes)
    mesh.merge_vertices()
    return mesh


def pool_meshes(pools_path: Path, allowed, dem: LocalDEM, tile: float):
    """Piscinas por tesela: lámina horizontal (el agua no sigue la ladera) y borde hasta el terreno."""
    pools = gpd.read_file(pools_path)
    pools = pools[pools["constructionNature"] == "openAirPool"]
    by_tile = defaultdict(lambda: {"water": [], "coping": []})
    water_area = coping_area = 0.0
    count = 0
    for geom in pools.geometry:
        for pool in roads_glb.polygons_of(geom.intersection(allowed)):
            if pool.area < 1.0:
                continue
            ring = np.asarray(shapely.segmentize(pool.exterior, 2.0).coords)
            ground = dem.sample_mesh(np.r_[ring[:, 0], pool.centroid.x], np.r_[ring[:, 1], pool.centroid.y])
            level = float(ground.max()) + POOL_WATER_ABOVE_M
            bottom = float(ground.min()) - POOL_COPING_BELOW_GROUND_M
            water = pool.buffer(-POOL_COPING_M, join_style="mitre")
            coping = pool.difference(water)
            key = (int(pool.centroid.x // tile), int(pool.centroid.y // tile))
            w = roads_glb.flat_mesh(roads_glb.polygons_of(water), level)
            c = roads_glb.curb_mesh(roads_glb.polygons_of(coping), bottom,
                                    level + POOL_COPING_ABOVE_WATER_M - bottom)
            if w is not None:
                by_tile[key]["water"].append(w)
                water_area += water.area
            if c is not None:
                by_tile[key]["coping"].append(c)
                coping_area += coping.area
            count += 1
    return by_tile, count, water_area, coping_area


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--cp-zip", type=Path, default=roads_glb.DEFAULT_CP_ZIP)
    ap.add_argument("--meta", type=Path, default=roads_glb.DEFAULT_META, help="meta.json con el origen local")
    ap.add_argument("--lines", type=Path, default=roads_glb.DEFAULT_LINES, help="Ejes de vial (osm_roads.geojson)")
    ap.add_argument("--buildings", type=Path, default=roads_glb.DEFAULT_BUILDINGS)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--tile", type=float, default=roads_glb.TILE_M, help="Lado de tesela en metros")
    ap.add_argument("--pools", type=Path, default=DEFAULT_POOLS, help="OtherConstruction de Catastro (piscinas)")
    ap.add_argument("--no-pools", action="store_true", help="No añadir piscinas")
    args = ap.parse_args(argv)

    origin = roads_glb.load_origin(args.meta)
    municipality, _, _ = roads_glb.load_cadastre(args.cp_zip, origin)
    shapely.prepare(municipality)
    dem = LocalDEM.load()

    by_tile, pool_count, water_area, coping_area = {}, 0, 0.0, 0.0
    if not args.no_pools:
        if not args.pools.exists():
            sys.exit(f"[ERROR] {args.pools} no existe: ejecuta antes extract_catastro_buildings.py (o usa --no-pools)")
        allowed = municipality
        if args.lines.exists():  # las piscinas nunca encima de un vial
            footprints = gpd.read_file(args.buildings).union_all() if args.buildings.exists() else None
            roads = roads_glb.build_surfaces(gpd.read_file(args.lines), municipality, footprints)
            allowed = municipality.difference(shapely.union_all(list(roads.values())))
        by_tile, pool_count, water_area, coping_area = pool_meshes(args.pools, allowed, dem, args.tile)

    material = trimesh.visual.material.PBRMaterial(name="MAT_terrain", baseColorFactor=TERRAIN_COLOR,
                                                   metallicFactor=0.0, roughnessFactor=1.0)
    pool_materials = {k: trimesh.visual.material.PBRMaterial(name=f"MAT_pool_{k}", baseColorFactor=c,
                                                             metallicFactor=0.0, roughnessFactor=0.9)
                      for k, c in POOL_COLORS.items()}
    scene = trimesh.Scene()
    terrain_area = 0.0
    minx, miny, maxx, maxy = municipality.bounds
    for i in range(int(np.floor(minx / args.tile)), int(np.floor(maxx / args.tile)) + 1):
        for j in range(int(np.floor(miny / args.tile)), int(np.floor(maxy / args.tile)) + 1):
            mesh = terrain_tile(municipality, i, j, args.tile, CELL_M, dem)
            if mesh is not None:
                mesh.visual = trimesh.visual.TextureVisuals(material=material)
                name = f"TERRAIN_{i}_{j}"
                mesh.metadata = {"tile": [i, j], "tile_m": args.tile, "cell_m": CELL_M}
                scene.add_geometry(mesh, node_name=name, geom_name=name)
                terrain_area += float(mesh.area)
            for kind, parts in by_tile.get((i, j), {}).items():
                if not parts:
                    continue
                pm = trimesh.util.concatenate(parts)
                pm.visual = trimesh.visual.TextureVisuals(material=pool_materials[kind])
                name = f"POOL_{kind}_{i}_{j}"
                pm.metadata = {"tile": [i, j], "tile_m": args.tile}
                scene.add_geometry(pm, node_name=name, geom_name=name)
    scene.metadata = {"source": args.cp_zip.name, "axes": "X=East, Y=Up, Z=-North", "units": "m",
                      "relief": "MDT05 IGN, dem_local.tif", "z0_m": dem.z0, "cell_m": CELL_M,
                      "roads_cut": False, "walkable_prefix": "TERRAIN_"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(scene.export(file_type="glb"))

    terrain_nodes = [g for n, g in scene.geometry.items() if n.startswith("TERRAIN_")]
    summary = {
        "output": args.output.name, "origin_epsg25829": list(origin), "z0_m": dem.z0,
        "municipality_km2": round(municipality.area / 1e6, 4),
        "terrain_surface_m2_3d": round(terrain_area), "terrain_nodes": len(terrain_nodes),
        "terrain_triangles": int(sum(len(g.faces) for g in terrain_nodes)),
        "pools": pool_count, "pool_water_m2": round(water_area), "pool_coping_m2": round(coping_area),
        "nodes": len(scene.geometry),
        "triangles": int(sum(len(g.faces) for g in scene.geometry.values())),
        "bounds_gltf": np.round(scene.bounds, 3).tolist(),
        "size_mb": round(args.output.stat().st_size / 2**20, 2),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
