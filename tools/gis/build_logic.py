#!/usr/bin/env python3
"""Capa lógica del mapa para el motor de simulación WorldOpen (agente 01).

Entradas (ya generadas por el pipeline): data/processed/catastro_buildings.geojson, catastro_building_parts.geojson,
osm_roads.geojson, dem_local.tif (+ .json) y las direcciones de Catastro (A.ES.SDGC.AD.41010.zip).

Salidas en data/export/logic/ (ejes del motor: x = Este, z = −Norte, metros, mismo origen local que los GLB):
  buildings.json   edificios: uso, viviendas, plantas, altura, cota de la base, huella, portal y nodo de calle
  streets.json     grafo peatonal (nodos con cota, tramos con longitud) — solo la mayor componente conexa
  heights.json     rejilla de cotas de la malla del terreno (para apoyar agentes y edificios al dibujar)
Y, privada, data/processed/logic_id_map.json (refcat → id): no se publica (WorldOpen, ADR-0007).

Los ids y nombres que salen de aquí aún NO son los del map-pack: pack_map.py les pone prefijo de región, inventa los
nombres de calle y comprueba que no quede nada real identificable.

Uso:  python -P tools/gis/build_logic.py
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
from collections import defaultdict
from pathlib import Path

import geopandas as gpd
import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dem import MESH_CELL_M, LocalDEM  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data/processed"
OUT = ROOT / "data/export/logic"
AD_ZIP = ROOT / "data/raw/catastro/A.ES.SDGC.AD.41010.zip"

USES = {
    "1_residential": "residential",
    "2_agriculture": "agriculture",
    "3_industrial": "industrial",
    "4_1_office": "office",
    "4_2_retail": "retail",
    "4_3_publicServices": "publicServices",
}
# Vías por las que no se camina.
NOT_WALKABLE = {"motorway", "motorway_link"}
SIMPLIFY_M = 1.5
SNAP_M = 0.5
FOOTPRINT_SIMPLIFY_M = 0.2
ADDRESS_MATCH_M = 25.0


def xz(x: float, y: float) -> tuple[float, float]:
    """Local (x=E, y=N) → motor (x=E, z=−N)."""
    return round(float(x), 2), round(float(-y), 2)


def load_buildings(dem: LocalDEM) -> tuple[list[dict], dict[str, int]]:
    b = gpd.read_file(PROCESSED / "catastro_buildings.geojson")
    parts = gpd.read_file(PROCESSED / "catastro_building_parts.geojson")
    parts = parts[parts["numberOfFloorsAboveGround"].fillna(0) > 0]
    per = parts.groupby("buildingId").agg(floors=("numberOfFloorsAboveGround", "max"), height=("height_m", "max"))
    b = b[b["localId"].isin(per.index)].sort_values("localId").reset_index(drop=True)
    out: list[dict] = []
    index: dict[str, int] = {}
    for i, row in b.iterrows():
        geom = row.geometry.buffer(0)
        polys = [geom] if isinstance(geom, Polygon) else list(geom.geoms)
        footprint = []
        verts = []
        for p in polys:
            ring = p.simplify(FOOTPRINT_SIMPLIFY_M).exterior.coords[:-1]
            flat = []
            for x, y in ring:
                fx, fz = xz(x, y)
                flat += [fx, fz]
                verts.append((x, y))
            if len(flat) >= 6:
                footprint.append(flat)
        vx, vy = np.array(verts).T
        base = float(dem.sample_mesh(vx, vy).min())
        c = geom.centroid
        cx, cz = xz(c.x, c.y)
        p = per.loc[row["localId"]]
        index[row["localId"]] = i
        out.append({
            "use": USES.get(row["currentUse"], "unknown"),
            "dwellings": int(row["numberOfDwellings"] or 0),
            "floorsAboveGround": int(p["floors"]),
            "grossFloorAreaM2": float(row["grossFloorArea_m2"] or 0),
            "footprintAreaM2": round(float(geom.area), 1),
            "centroid": {"x": cx, "z": cz},
            "baseY": round(base, 2),
            "heightM": round(float(p["height"]), 2),
            "footprint": footprint,
            "_geom": geom,
        })
    return out, index


def build_graph(dem: LocalDEM):
    roads = gpd.read_file(PROCESSED / "osm_roads.geojson")
    roads = roads[(~roads["is_area"]) & (~roads["highway"].isin(NOT_WALKABLE))]
    key_to_node: dict[tuple[int, int], int] = {}
    coords: list[tuple[float, float]] = []
    edges: dict[tuple[int, int], dict] = {}
    way_names: list[str | None] = []

    def node(x: float, y: float) -> int:
        k = (round(x / SNAP_M), round(y / SNAP_M))
        if k not in key_to_node:
            key_to_node[k] = len(coords)
            coords.append((x, y))
        return key_to_node[k]

    # Vértices de cruce: compartidos por varias vías o extremos. Simplificar a través de ellos desconecta el grafo
    # (una vía que pasa por un cruce en T pierde el vértice común), así que cada vía se parte en ellos primero.
    def key(x: float, y: float) -> tuple[int, int]:
        return (round(x / SNAP_M), round(y / SNAP_M))

    uses: dict[tuple[int, int], int] = defaultdict(int)
    for geom in roads.geometry:
        cs = list(geom.coords)
        for k in {key(x, y) for x, y in cs}:
            uses[k] += 1
        uses[key(*cs[0])] += 1
        uses[key(*cs[-1])] += 1

    for _, r in roads.iterrows():
        way = len(way_names)
        way_names.append(r["name"] if isinstance(r["name"], str) else None)
        cs = list(r.geometry.coords)
        pieces, current = [], [cs[0]]
        for c in cs[1:]:
            current.append(c)
            if uses[key(*c)] > 1:
                pieces.append(current)
                current = [c]
        if len(current) > 1:
            pieces.append(current)
        pts: list[int] = []
        for piece in pieces:
            simple = LineString(piece).simplify(SIMPLIFY_M).coords
            ids = [node(x, y) for x, y in simple]
            pts += ids if not pts else ids[1:]
        for a, b in zip(pts, pts[1:]):
            if a == b:
                continue
            k = (min(a, b), max(a, b))
            ax, ay = coords[a]
            bx, by = coords[b]
            edges.setdefault(k, {"kind": r["group"], "way": way, "length": float(np.hypot(bx - ax, by - ay))})

    # Mayor componente conexa (union-find).
    parent = list(range(len(coords)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a, b in edges:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    sizes: dict[int, int] = defaultdict(int)
    for i in range(len(coords)):
        sizes[find(i)] += 1
    main = max(sizes, key=sizes.get)
    keep = [i for i in range(len(coords)) if find(i) == main]
    remap = {old: new for new, old in enumerate(keep)}
    xs = np.array([coords[i][0] for i in keep])
    ys = np.array([coords[i][1] for i in keep])
    hs = dem.sample_mesh(xs, ys)
    nodes = []
    for new, old in enumerate(keep):
        x, z = xz(*coords[old])
        nodes.append({"id": new, "x": x, "z": z, "y": round(float(hs[new]), 2)})
    out_edges = []
    for (a, b), e in sorted(edges.items()):
        if a in remap and b in remap:
            out_edges.append({
                "id": len(out_edges), "from": remap[a], "to": remap[b], "lengthM": round(e["length"], 2),
                "kind": e["kind"], "oneway": False, "way": e["way"],
            })
    stats = {"components": len(sizes), "nodes_total": len(coords), "nodes_kept": len(keep), "edges": len(out_edges)}
    return nodes, out_edges, way_names, stats


def attach_entrances(buildings: list[dict], index: dict[str, int], nodes: list[dict]) -> dict:
    tree = shapely.STRtree([Point(n["x"], -n["z"]) for n in nodes])
    ad = gpd.read_file(f"zip://{AD_ZIP}!A.ES.SDGC.AD.41010.gml", layer="Address")
    origin = json.loads((PROCESSED / "catastro_buildings.meta.json").read_text(encoding="utf-8"))["origin_epsg25829"]
    portals: dict[int, list[tuple[float, float]]] = defaultdict(list)
    matched = by_ref = 0
    geoms = [b["_geom"] for b in buildings]
    btree = shapely.STRtree(geoms)
    for _, a in ad.iterrows():
        px, py = a.geometry.x - origin[0], a.geometry.y - origin[1]
        ref = str(a["localId"]).split(".")[-1][:14]
        i = index.get(ref)
        if i is None:
            j = btree.query_nearest(Point(px, py), max_distance=ADDRESS_MATCH_M)
            if len(j) == 0:
                continue
            i = int(j[0])
        else:
            by_ref += 1
        matched += 1
        portals[i].append((px, py))
    with_portal = 0
    for i, b in enumerate(buildings):
        geom = b["_geom"]
        if portals.get(i):
            with_portal += 1
            px, py = portals[i][0]
            p = shapely.ops.nearest_points(geom.boundary, Point(px, py))[0]
        else:
            # Sin portal: el punto de la fachada más cercano a la calle.
            n = nodes[int(tree.query_nearest(geom.centroid)[0])]
            p = shapely.ops.nearest_points(geom.boundary, Point(n["x"], -n["z"]))[0]
        node = nodes[int(tree.query_nearest(p)[0])]
        ex, ez = xz(p.x, p.y)
        b["entrances"] = [{"x": ex, "z": ez, "streetNodeId": node["id"]}]
    return {"addresses": len(ad), "matched": matched, "by_refcat": by_ref, "buildings_with_portal": with_portal}


def height_grid(dem: LocalDEM, bounds) -> dict:
    cell = MESH_CELL_M
    minx, miny, maxx, maxy = bounds
    x0 = np.floor(minx / cell) * cell
    y0 = np.floor(miny / cell) * cell
    cols = int(np.ceil((maxx - x0) / cell)) + 1
    rows = int(np.ceil((maxy - y0) / cell)) + 1
    xs = x0 + np.arange(cols) * cell
    ys = y0 + np.arange(rows) * cell
    gx, gy = np.meshgrid(xs, ys)
    h = dem.sample_mesh(gx.ravel(), gy.ravel()).astype(np.float32)
    # Fila 0 = z mínima del motor (= y local máxima): se invierten las filas.
    h = h.reshape(rows, cols)[::-1].copy()
    return {
        "cellSizeM": cell, "origin": {"x": float(x0), "z": float(-(y0 + (rows - 1) * cell))},
        "cols": cols, "rows": rows, "encoding": "float32-le-base64", "heights": base64.b64encode(h.tobytes()).decode(),
    }


def main(argv=None):
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args(argv)
    dem = LocalDEM.load()
    buildings, index = load_buildings(dem)
    nodes, edges, way_names, gstats = build_graph(dem)
    estats = attach_entrances(buildings, index, nodes)
    all_x = [n["x"] for n in nodes] + [b["centroid"]["x"] for b in buildings]
    all_z = [n["z"] for n in nodes] + [b["centroid"]["z"] for b in buildings]
    bounds = {"minX": min(all_x), "minZ": min(all_z), "maxX": max(all_x), "maxZ": max(all_z)}
    heights = height_grid(dem, (bounds["minX"] - 100, -bounds["maxZ"] - 100, bounds["maxX"] + 100, -bounds["minZ"] + 100))

    OUT.mkdir(parents=True, exist_ok=True)
    id_map = {}
    for ref, i in index.items():
        id_map[ref] = i
    for b in buildings:
        b.pop("_geom")
    (OUT / "buildings.json").write_text(json.dumps(buildings, separators=(",", ":")), encoding="utf-8")
    (OUT / "streets.json").write_text(json.dumps({"nodes": nodes, "edges": edges, "wayNames": way_names}, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    (OUT / "heights.json").write_text(json.dumps(heights), encoding="utf-8")
    (OUT / "bounds.json").write_text(json.dumps(bounds), encoding="utf-8")
    (PROCESSED / "logic_id_map.json").write_text(json.dumps(id_map, indent=0), encoding="utf-8")
    uses = defaultdict(int)
    for b in buildings:
        uses[b["use"]] += 1
    print(json.dumps({"buildings": len(buildings), "uses": uses, "graph": gstats, "entrances": estats,
                      "heights": {k: heights[k] for k in ("cols", "rows", "cellSizeM")}, "bounds": bounds}, indent=2))


if __name__ == "__main__":
    main()
