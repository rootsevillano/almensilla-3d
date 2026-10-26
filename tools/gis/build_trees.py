#!/usr/bin/env python3
"""Árboles desde OpenStreetMap a una lista de instancias para el visor.

Basado en la inspección del fichero real (ver `.claude/MEMORY.md`, sección Fase 1):
  * 11 nodos `natural=tree`                     -> árbol de sombra en su posición exacta.
  * 29 `leisure=park`, 10 `leisure=garden`        -> árboles de sombra repartidos (rejilla con jitter).
  * 19 `landuse=orchard` (9 con `trees=olive_trees`) -> olivos en hileras alineadas con la parcela (el
    Aljarafe es tierra de olivar; los huertos sin `trees` también se tratan como olivar).
  * 5 `natural=wood`                             -> pinos (pino piñonero, típico de la comarca).
  * 12 `natural=heath`, 1 `natural=scrub`        -> matorral disperso.
Se descartan los puntos dentro de edificios (+1.5 m), viales (+1 m) o piscinas (+1 m), y fuera del término.

Salida: `data/export/almensilla_trees.json`
  {"types": [...], "axes": "X=East, Y=Up, Z=-North", "trees": [[x, z, tipo, escala], ...]}
  en coordenadas glTF (Z = -Norte), mismo origen local que los GLB; los árboles apoyan en Y=0.

Uso:
    python -P tools/gis/build_trees.py
    python -P tools/gis/build_trees.py --seed 7
"""
from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import geopandas as gpd
import numpy as np
import shapely
from pyproj import Transformer
from shapely import affinity
from shapely.geometry import MultiPolygon, Point, Polygon

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_roads_glb as roads_glb  # noqa: E402

ROOT = roads_glb.ROOT
DEFAULT_OSM = roads_glb.DEFAULT_OSM
DEFAULT_POOLS = ROOT / "data/processed/catastro_other_constructions.geojson"
DEFAULT_OUTPUT = ROOT / "data/export/almensilla_trees.json"

TYPES = ["broadleaf", "olive", "pine", "shrub"]
# área OSM -> (tipo, separación m, fracción que se conserva, hileras alineadas)
AREA_RULES = {
    ("leisure", "park"): ("broadleaf", 9.0, 0.6, False),
    ("leisure", "garden"): ("broadleaf", 8.0, 0.5, False),
    ("landuse", "orchard"): ("olive", 7.0, 0.95, True),
    ("natural", "wood"): ("pine", 7.0, 0.8, False),
    ("natural", "heath"): ("shrub", 10.0, 0.3, False),
    ("natural", "scrub"): ("shrub", 8.0, 0.4, False),
}
SCALE_RANGE = {"broadleaf": (0.8, 1.25), "olive": (0.85, 1.15), "pine": (0.85, 1.3), "shrub": (0.6, 1.1)}


def load_osm(osm_path: Path, origin):
    """Nodos natural=tree y polígonos (ways cerrados y multipolígonos) de AREA_RULES, en coordenadas locales."""
    nodes, ways, rels, tags, nds, members = {}, {}, [], {}, [], []
    tree_nodes = []
    for _, el in ET.iterparse(osm_path, events=("end",)):
        if el.tag == "tag":
            tags[el.get("k")] = el.get("v")
            continue
        if el.tag == "nd":
            nds.append(el.get("ref"))
            continue
        if el.tag == "member":
            members.append((el.get("type"), el.get("ref"), el.get("role")))
            continue
        if el.tag == "node":
            nodes[el.get("id")] = (float(el.get("lon")), float(el.get("lat")))
            if tags.get("natural") == "tree":
                tree_nodes.append(el.get("id"))
        elif el.tag == "way":
            ways[el.get("id")] = (dict(tags), list(nds))
        elif el.tag == "relation" and tags.get("type") == "multipolygon":
            rels.append((dict(tags), list(members)))
        if el.tag in ("node", "way", "relation"):
            tags, nds, members = {}, [], []
            el.clear()

    to_utm = Transformer.from_crs("EPSG:4326", "EPSG:25829", always_xy=True)

    def local(refs):
        lon, lat = np.array([nodes[r] for r in refs]).T
        e, n = to_utm.transform(lon, lat)
        return np.c_[e - origin[0], n - origin[1]]

    def rule_of(tg):
        return next((k for k in AREA_RULES if tg.get(k[0]) == k[1]), None)

    areas = []
    for tg, refs in ways.values():
        key = rule_of(tg)
        if key and len(refs) >= 4 and refs[0] == refs[-1]:
            areas.append((key, shapely.make_valid(Polygon(local(refs)))))
    for tg, mem in rels:
        key = rule_of(tg)
        if not key:
            continue
        outers = [Polygon(local(ways[r][1])) for t, r, role in mem
                  if t == "way" and role == "outer" and r in ways and ways[r][1][0] == ways[r][1][-1]]
        if outers:
            areas.append((key, shapely.make_valid(shapely.union_all(outers))))
    points = [Point(*local([n])[0]) for n in tree_nodes]
    return points, areas


def sample_area(poly, spacing: float, keep: float, aligned: bool, rng) -> list[Point]:
    """Rejilla dentro del polígono; en hileras alineadas con su rectángulo mínimo (olivar) o con jitter."""
    angle = 0.0
    if aligned:
        rect = np.array(poly.minimum_rotated_rectangle.exterior.coords)
        edges = np.diff(rect, axis=0)
        longest = edges[np.argmax(np.hypot(edges[:, 0], edges[:, 1]))]
        angle = float(np.degrees(np.arctan2(longest[1], longest[0])))
    c = poly.centroid
    rotated = affinity.rotate(poly, -angle, origin=c)
    minx, miny, maxx, maxy = rotated.bounds
    xs = np.arange(minx + spacing / 2, maxx, spacing)
    ys = np.arange(miny + spacing / 2, maxy, spacing)
    gx, gy = np.meshgrid(xs, ys)
    pts = np.c_[gx.ravel(), gy.ravel()]
    jitter = 0.15 if aligned else 0.4
    pts += rng.uniform(-jitter, jitter, pts.shape) * spacing
    pts = pts[rng.random(len(pts)) < keep]
    cand = shapely.points(pts)
    cand = cand[shapely.contains(rotated, cand)]
    return list(shapely.affinity.rotate(shapely.multipoints(cand), angle, origin=c).geoms) if len(cand) else []


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--osm", type=Path, default=DEFAULT_OSM)
    ap.add_argument("--cp-zip", type=Path, default=roads_glb.DEFAULT_CP_ZIP)
    ap.add_argument("--meta", type=Path, default=roads_glb.DEFAULT_META)
    ap.add_argument("--lines", type=Path, default=roads_glb.DEFAULT_LINES)
    ap.add_argument("--buildings", type=Path, default=roads_glb.DEFAULT_BUILDINGS)
    ap.add_argument("--pools", type=Path, default=DEFAULT_POOLS)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--seed", type=int, default=41010, help="Semilla (salida reproducible)")
    args = ap.parse_args(argv)
    for p in (args.lines, args.buildings, args.pools):
        if not p.exists():
            sys.exit(f"[ERROR] {p} no existe: ejecuta antes extract_catastro_buildings.py y build_roads_glb.py")

    rng = np.random.default_rng(args.seed)
    origin = roads_glb.load_origin(args.meta)
    municipality, _, _ = roads_glb.load_cadastre(args.cp_zip, origin)
    footprints = gpd.read_file(args.buildings).union_all()
    roads = roads_glb.build_surfaces(gpd.read_file(args.lines), municipality, footprints)
    pools = gpd.read_file(args.pools)
    blocked = shapely.union_all([
        footprints.buffer(1.5),
        shapely.union_all(list(roads.values())).buffer(1.0),
        shapely.union_all(list(pools.geometry)).buffer(1.0),
    ])
    allowed = municipality.difference(blocked)
    shapely.prepare(allowed)

    points, areas = load_osm(args.osm, origin)
    candidates = [(p, "broadleaf") for p in points]
    area_stats = Counter()
    for key, geom in areas:
        kind, spacing, keep, aligned = AREA_RULES[key]
        for poly in (geom.geoms if isinstance(geom, MultiPolygon) else [geom]):
            if not isinstance(poly, Polygon) or poly.is_empty:
                continue
            area_stats[f"{key[0]}={key[1]}"] += poly.intersection(municipality).area
            candidates += [(p, kind) for p in sample_area(poly, spacing, keep, aligned, rng)]

    trees, by_type, dropped = [], Counter(), 0
    for p, kind in candidates:
        if not allowed.contains(p):
            dropped += 1
            continue
        lo, hi = SCALE_RANGE[kind]
        # glTF: X = Este, Z = -Norte
        trees.append([round(p.x, 2), round(-p.y, 2), TYPES.index(kind), round(float(rng.uniform(lo, hi)), 2)])
        by_type[kind] += 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = {"source": args.osm.name, "axes": "X=East, Y=Up, Z=-North", "units": "m",
               "origin_epsg25829": list(origin), "types": TYPES, "fields": ["x", "z", "type", "scale"],
               "trees": trees}
    args.output.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({
        "output": args.output.name, "trees": len(trees), "by_type": dict(by_type),
        "osm_tree_nodes": len(points), "osm_areas": len(areas),
        "area_m2_by_rule": {k: round(v) for k, v in area_stats.items()},
        "candidates_dropped_blocked_or_outside": dropped,
        "size_kb": round(args.output.stat().st_size / 1024, 1),
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
