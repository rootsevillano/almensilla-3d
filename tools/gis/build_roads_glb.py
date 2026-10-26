#!/usr/bin/env python3
"""Viales de OpenStreetMap a GLB (glTF 2.0) con anchura calibrada contra el Catastro.

Basado en la inspección del fichero real (ver `.claude/MEMORY.md`, secciones OSM y Viales):
  * 614 ways `highway=*`; 6 `highway=pedestrian` + `area=yes` (plazas, se usan como polígono).
  * 8 `highway=construction` sin subtipo: calles del sector F dentro de manzanas catastrales -> residential.
  * `width` casi inexistente (1 caso, 0.6 m en un carril bici) -> anchura por medición o por clase.
  * `tunnel=yes` (2) se omiten; `bridge=*` se aplanan a rasante (todavía no hay terreno).

Anchura: en suelo urbano el Catastro no parcela las calles, así que la distancia entre las parcelas
a ambos lados del eje es la anchura de fachada a fachada. Se mide cada 10 m (rayos perpendiculares)
y se usa la mediana por vía, acotada al rango de su clase. Fuera del casco: valor por defecto de la clase.

Salidas:
  * `data/processed/osm_roads.geojson`  ejes en coordenadas locales con `width_m` y `width_source`.
  * `data/export/almensilla_roads.glb`   superficies planas en Y=ROAD_Y, recortadas al término municipal
    (unión de CadastralZoning) y sin las huellas de Building, en teselas de TILE_M; nodos `ROAD_<grupo>_<i>_<j>` (caminable, sin `COL_`).
    Ejes glTF: X = Este, Y = arriba, Z = -Norte (igual que almensilla_buildings.glb).

Uso:
    python -P tools/gis/build_roads_glb.py
    python -P tools/gis/build_roads_glb.py --tile 250 --no-measure
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import geopandas as gpd
import numpy as np
import shapely
import trimesh
from pyproj import Transformer
from shapely.geometry import LineString, MultiPolygon, Polygon, box

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OSM = ROOT / "data/raw/osm/almensilla con sector f.osm"
DEFAULT_CP_ZIP = ROOT / "data/raw/catastro/A.ES.SDGC.CP.41010.zip"
DEFAULT_META = ROOT / "data/processed/catastro_buildings.meta.json"
DEFAULT_LINES = ROOT / "data/processed/osm_roads.geojson"
DEFAULT_BUILDINGS = ROOT / "data/processed/catastro_buildings.geojson"
DEFAULT_OUTPUT = ROOT / "data/export/almensilla_roads.glb"
DEFAULT_ORIGIN = (755870.0, 4132708.0)

TILE_M = 500.0
ROAD_Y = 0.02  # por encima de la rasante para evitar z-fighting con el futuro terreno
SAMPLE_STEP_M = 10.0
RAY_MAX_M = 40.0
URBAN_PAD_M = 40.0  # manzanas + margen = envolvente del casco (las calles quedan entre manzanas)

# clase OSM -> (grupo, anchura por defecto, mínima, máxima) en metros, fachada a fachada.
# Defaults urbanos ~ medianas medidas (residential 9.4, tertiary 13.3, construction 8.1, pedestrian 4.7).
CLASSES = {
    "motorway": ("carriageway", 14.0, 10.0, 16.0),
    "motorway_link": ("carriageway", 6.0, 5.0, 8.0),
    "secondary": ("carriageway", 10.0, 7.0, 14.0),
    "secondary_link": ("carriageway", 6.0, 5.0, 8.0),
    "tertiary": ("carriageway", 9.0, 6.0, 12.0),
    "unclassified": ("carriageway", 6.0, 5.0, 10.0),
    "residential": ("carriageway", 8.0, 5.0, 12.0),
    "construction": ("carriageway", 8.0, 5.0, 12.0),
    "living_street": ("carriageway", 7.0, 5.0, 10.0),
    "service": ("carriageway", 4.0, 3.0, 6.0),
    "track": ("track", 4.0, 3.0, 5.0),
    "pedestrian": ("pedestrian", 4.5, 3.0, 6.0),
    "footway": ("pedestrian", 2.0, 1.5, 5.0),
    "path": ("pedestrian", 1.5, 1.0, 3.0),
    "cycleway": ("pedestrian", 2.5, 2.0, 3.0),
    "steps": ("pedestrian", 2.0, 1.5, 4.0),
}
# Orden de prioridad: un grupo posterior se recorta con los anteriores (sin solapes ni z-fighting)
GROUPS = ["carriageway", "track", "pedestrian"]
COLORS = {
    "carriageway": (92, 94, 98, 255),
    "track": (168, 142, 104, 255),
    "pedestrian": (196, 186, 170, 255),
}
PRINCIPAL = {"secondary", "tertiary", "residential", "construction"}  # criterio QA 3 del agente 04

# Local (x=E, y=N, z=arriba) -> glTF (X=E, Y=arriba, Z=-N)
LOCAL_TO_GLTF = np.array([[1, 0, 0, 0], [0, 0, 1, 0], [0, -1, 0, 0], [0, 0, 0, 1]], dtype=float)


def load_origin(meta_path: Path) -> tuple[float, float]:
    if meta_path.exists():
        return tuple(json.loads(meta_path.read_text(encoding="utf-8"))["origin_epsg25829"])
    return DEFAULT_ORIGIN


def load_osm_roads(osm_path: Path, origin) -> gpd.GeoDataFrame:
    nodes, ways, tags, nds = {}, [], {}, []
    for _, el in ET.iterparse(osm_path, events=("end",)):
        if el.tag == "tag":
            tags[el.get("k")] = el.get("v")
            continue
        if el.tag == "nd":
            nds.append(el.get("ref"))
            continue
        if el.tag == "node":
            nodes[el.get("id")] = (float(el.get("lon")), float(el.get("lat")))
        elif el.tag == "way" and "highway" in tags:
            ways.append((el.get("id"), tags, nds))
        if el.tag in ("node", "way", "relation"):
            tags, nds = {}, []
            el.clear()

    to_utm = Transformer.from_crs("EPSG:4326", "EPSG:25829", always_xy=True)
    rows, skipped = [], Counter()
    for wid, tg, refs in ways:
        hw = tg["highway"]
        if hw not in CLASSES:
            skipped[f"class:{hw}"] += 1
            continue
        if tg.get("tunnel") in ("yes", "culvert", "building_passage"):
            skipped["tunnel"] += 1
            continue
        lon, lat = np.array([nodes[r] for r in refs]).T
        e, n = to_utm.transform(lon, lat)
        xy = np.c_[e - origin[0], n - origin[1]]
        is_area = tg.get("area") == "yes" and refs[0] == refs[-1]
        rows.append({
            "osm_id": int(wid), "highway": hw, "group": CLASSES[hw][0], "name": tg.get("name"),
            "is_area": is_area, "bridge": tg.get("bridge"), "lanes": tg.get("lanes"),
            "width_tag": tg.get("width"),
            "geometry": shapely.make_valid(Polygon(xy)) if is_area else LineString(xy),
        })
    if skipped:
        print(f"[info] omitidas: {dict(skipped)}", file=sys.stderr)
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=None)


def load_cadastre(cp_zip: Path, origin):
    """Término municipal (unión de CadastralZoning), envolvente del casco y bordes de parcela."""
    base = f"/vsizip/{cp_zip.as_posix()}/{cp_zip.stem}"
    zoning = gpd.read_file(f"{base}.cadastralzoning.gml")
    parcels = gpd.read_file(f"{base}.cadastralparcel.gml")
    shift = lambda c: c - np.asarray(origin)  # noqa: E731
    zoning["geometry"] = shapely.transform(zoning.geometry.values, shift)
    parcels["geometry"] = shapely.transform(parcels.geometry.values, shift)
    municipality = zoning.union_all()
    # Observado: levelName lleva espacio final ('MANZANA ', 'POLIGONO ')
    blocks = zoning[zoning["LocalisedCharacterString"].str.strip() == "MANZANA"].union_all()
    urban = blocks.buffer(URBAN_PAD_M).buffer(-(URBAN_PAD_M - 10.0))
    return municipality, urban, parcels


def measure_widths(roads: gpd.GeoDataFrame, urban, parcels) -> list[float | None]:
    """Mediana de la anchura fachada-a-fachada por vía (None si no hay muestras válidas)."""
    edges = parcels.boundary.union_all()
    tree = shapely.STRtree(parcels.geometry.values)
    out = []
    for geom, is_area in zip(roads.geometry, roads["is_area"]):
        samples = []
        if not is_area and geom.length >= 2 * SAMPLE_STEP_M:
            for d in np.arange(SAMPLE_STEP_M / 2, geom.length - SAMPLE_STEP_M / 2, SAMPLE_STEP_M):
                p = geom.interpolate(d)
                if not urban.contains(p) or tree.query(p, predicate="within").size:
                    continue  # fuera del casco, o eje sobre una parcela (vía privada / rural)
                a, b = geom.interpolate(d - 1.0), geom.interpolate(d + 1.0)
                t = np.array([b.x - a.x, b.y - a.y])
                t /= np.linalg.norm(t) or 1.0
                normal = np.array([-t[1], t[0]])
                hits = []
                for s in (1.0, -1.0):
                    end = (p.x + s * normal[0] * RAY_MAX_M, p.y + s * normal[1] * RAY_MAX_M)
                    hit = LineString([(p.x, p.y), end]).intersection(edges)
                    if hit.is_empty:
                        break
                    hits.append(p.distance(hit))
                if len(hits) == 2:
                    samples.append(sum(hits))
        out.append(float(np.median(samples)) if samples else None)
    return out


def assign_widths(roads: gpd.GeoDataFrame, measured: list[float | None]) -> None:
    widths, sources = [], []
    for hw, tag, lanes, m in zip(roads["highway"], roads["width_tag"], roads["lanes"], measured):
        _, default, lo, hi = CLASSES[hw]
        try:
            tagged = float(tag) if tag else None
        except ValueError:
            tagged = None
        if tagged is not None and lo <= tagged <= hi:
            w, src = tagged, "osm_width"
        elif m is not None:
            w, src = float(np.clip(m, lo, hi)), "measured" if lo <= m <= hi else "measured_clamped"
        elif hw.startswith("motorway") and lanes and lanes.isdigit():
            w, src = float(np.clip(int(lanes) * 3.5 + 3.0, lo, hi)), "osm_lanes"
        else:
            w, src = default, "class_default"
        widths.append(round(w, 2))
        sources.append(src)
    roads["width_m"] = widths
    roads["width_source"] = sources


def build_surfaces(roads: gpd.GeoDataFrame, municipality, footprints=None) -> dict[str, shapely.Geometry]:
    """Superficies por grupo, disjuntas entre sí, dentro del municipio y fuera de las huellas de edificio
    (OSM y Catastro no están perfectamente alineados: sin recorte ~0.9 % de la calzada caía bajo edificios)."""
    surfaces, taken = {}, footprints
    for group in GROUPS:
        sel = roads[roads["group"] == group]
        if sel.empty:
            continue
        geoms = [g if a else g.buffer(w / 2.0, cap_style="round", join_style="round", quad_segs=4)
                 for g, a, w in zip(sel.geometry, sel["is_area"], sel["width_m"])]
        # simplificar antes de recortar: hacerlo después reintroduce solapes en los bordes
        surf = shapely.union_all(geoms).simplify(0.05).intersection(municipality)
        if taken is not None:
            surf = surf.difference(taken)
        surfaces[group] = surf
        taken = surf if taken is None else taken.union(surf)
    return surfaces


def polygons_of(geom) -> list[Polygon]:
    if geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    if isinstance(geom, MultiPolygon):
        return list(geom.geoms)
    return [g for part in getattr(geom, "geoms", []) for g in polygons_of(part)]


def flat_mesh(polys: list[Polygon], y: float) -> trimesh.Trimesh | None:
    meshes = []
    for poly in polys:
        if poly.area < 0.01:
            continue
        v2, faces = trimesh.creation.triangulate_polygon(poly, engine="earcut")
        v3 = np.c_[v2, np.full(len(v2), y)]  # local x, y, z=altura
        meshes.append(trimesh.Trimesh(v3, faces, process=False))
    if not meshes:
        return None
    mesh = trimesh.util.concatenate(meshes)
    mesh.merge_vertices()
    mesh.apply_transform(LOCAL_TO_GLTF)
    # earcut no garantiza el sentido de giro, y el GLB guarda float32 (~0.2 mm de resolución a 3 km del
    # origen), lo que puede voltear astillas. Se orienta sobre los vértices ya redondeados a float32:
    # todas las caras hacia +Y, y se descartan las de área nula en float32 (normal indefinida).
    v = mesh.vertices.astype(np.float32).astype(np.float64)
    f = mesh.faces.copy()
    ny = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])[:, 1]
    f[ny < 0] = f[ny < 0][:, ::-1]
    mesh = trimesh.Trimesh(v, f[ny != 0], process=False)
    mesh.remove_unreferenced_vertices()
    return mesh


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--osm", type=Path, default=DEFAULT_OSM)
    ap.add_argument("--cp-zip", type=Path, default=DEFAULT_CP_ZIP)
    ap.add_argument("--meta", type=Path, default=DEFAULT_META, help="meta.json con el origen local")
    ap.add_argument("--lines", type=Path, default=DEFAULT_LINES)
    ap.add_argument("--buildings", type=Path, default=DEFAULT_BUILDINGS,
                    help="Huellas de Building (se restan de las superficies de vial)")
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--tile", type=float, default=TILE_M, help="Lado de tesela en metros")
    ap.add_argument("--no-measure", action="store_true", help="No medir con Catastro: anchura por clase")
    args = ap.parse_args(argv)

    origin = load_origin(args.meta)
    roads = load_osm_roads(args.osm, origin)
    municipality, urban, parcels = load_cadastre(args.cp_zip, origin)
    measured = [None] * len(roads) if args.no_measure else measure_widths(roads, urban, parcels)
    assign_widths(roads, measured)

    args.lines.parent.mkdir(parents=True, exist_ok=True)
    args.lines.unlink(missing_ok=True)
    with warnings.catch_warnings():
        # El CRS local (origen desplazado) no tiene código EPSG; se documenta en el resumen
        warnings.filterwarnings("ignore", message="'crs' was not provided")
        roads.drop(columns=["width_tag"]).to_file(args.lines, driver="GeoJSON", engine="pyogrio",
                                                  layer_options={"COORDINATE_PRECISION": 3, "RFC7946": "NO"})

    footprints = None
    if args.buildings.exists():
        footprints = gpd.read_file(args.buildings).union_all()
    else:
        print(f"[aviso] {args.buildings} no existe: no se recortan las huellas de edificio", file=sys.stderr)
    surfaces = build_surfaces(roads, municipality, footprints)
    scene = trimesh.Scene()
    minx, miny, maxx, maxy = municipality.bounds
    i0, j0 = int(np.floor(minx / args.tile)), int(np.floor(miny / args.tile))
    i1, j1 = int(np.floor(maxx / args.tile)), int(np.floor(maxy / args.tile))
    materials = {g: trimesh.visual.material.PBRMaterial(name=f"MAT_road_{g}", baseColorFactor=COLORS[g],
                                                        metallicFactor=0.0, roughnessFactor=0.95)
                 for g in GROUPS}
    area_by_group = Counter()
    for group, surf in surfaces.items():
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                tile = box(i * args.tile, j * args.tile, (i + 1) * args.tile, (j + 1) * args.tile)
                mesh = flat_mesh(polygons_of(surf.intersection(tile)), ROAD_Y)
                if mesh is None:
                    continue
                mesh.visual = trimesh.visual.TextureVisuals(material=materials[group])
                name = f"ROAD_{group}_{i}_{j}"
                mesh.metadata = {"group": group, "tile": [i, j], "tile_m": args.tile,
                                 "area_m2": round(float(mesh.area), 1)}
                scene.add_geometry(mesh, node_name=name, geom_name=name)
                area_by_group[group] += mesh.area
    scene.metadata = {"source": args.osm.name, "axes": "X=East, Y=Up, Z=-North", "units": "m",
                      "road_y_m": ROAD_Y, "walkable_prefix": "ROAD_"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(scene.export(file_type="glb"))

    principal = roads[roads["highway"].isin(PRINCIPAL) & ~roads["is_area"]]
    length = principal.length
    in_range = float(length[(principal["width_m"] >= 6) & (principal["width_m"] <= 10)].sum() / length.sum())
    summary = {
        "output": args.output.name, "lines": args.lines.name, "origin_epsg25829": list(origin),
        "ways": len(roads), "ways_by_group": roads["group"].value_counts().to_dict(),
        "width_sources": roads["width_source"].value_counts().to_dict(),
        "municipality_km2": round(municipality.area / 1e6, 3),
        "nodes": len(scene.geometry),
        "area_m2_by_group": {g: round(a) for g, a in area_by_group.items()},
        "triangles": int(sum(len(g.faces) for g in scene.geometry.values())),
        "size_mb": round(args.output.stat().st_size / 2**20, 2),
        "qa_principal_length_share_6_10m": round(in_range, 3),
        "qa_principal_width_median_m": round(float(np.median(principal["width_m"])), 2),
        "width_median_by_class": roads.groupby("highway")["width_m"].median().round(2).to_dict(),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
