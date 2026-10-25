#!/usr/bin/env python3
"""Extracción de edificios del Catastro INSPIRE (A.ES.SDGC.BU.<INE>.zip) a GeoJSON local.

Basado exclusivamente en el esquema inspeccionado en los ficheros reales
(ver `.claude/MEMORY.md`, sección "Catastro"):

  * building.gml          -> Building          (huella + uso; numberOfFloorsAboveGround = nil)
  * buildingpart.gml      -> BuildingPart      (huella por volumen + numberOfFloorsAboveGround)
  * otherconstruction.gml -> OtherConstruction (constructionNature=openAirPool)

Lectura con GDAL (driver GML vía geopandas/pyogrio) directamente desde el ZIP (`/vsizip/`).
GDAL aplana el esquema INSPIRE a columnas por nombre local; `SCHEMA` fija las columnas
verificadas y el script aborta si alguna falta.

CRS de entrada: EPSG:25829 (ETRS89 / UTM 29N).
Salida: coordenadas métricas locales  x = E - E0,  y = N - N0  (origen relativo (0,0,0)),
anillos orientados según RFC 7946 (exterior CCW, interiores CW).

Uso:
    python tools/gis/extract_catastro_buildings.py
    python tools/gis/extract_catastro_buildings.py --zip data/raw/catastro/A.ES.SDGC.BU.41010.zip \
        --out data/processed --origin 755870 4132708
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from pyproj import CRS, Transformer

SOURCE_CRS = CRS.from_epsg(25829)

# --- Contrato de salida (agente 01_gis_pipeline) ---
FLOOR_HEIGHT_M = 3.0
FALLBACK_HOUSING_M = 3.5
FALLBACK_SHED_M = 6.0
# Valores de currentUse observados que se tratan como "nave"
SHED_USES = {"3_industrial", "2_agriculture"}

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ZIP = ROOT / "data/raw/catastro/A.ES.SDGC.BU.41010.zip"
DEFAULT_OUT = ROOT / "data/processed"
# Centro del extent de CadastralParcel del municipio 41010, redondeado a metros
DEFAULT_ORIGIN = (755870.0, 4132708.0)

# Columnas GDAL verificadas -> nombre de salida (orden = orden de salida)
SCHEMA = {
    ".building.gml": {
        "localId": "localId",
        "currentUse": "currentUse",  # 17 Building sin valor
        "conditionOfConstruction": "conditionOfConstruction",
        "numberOfBuildingUnits": "numberOfBuildingUnits",
        "numberOfDwellings": "numberOfDwellings",
        # Observado: siempre nil en building.gml; se conserva por si cambia en otra descarga
        "numberOfFloorsAboveGround": "numberOfFloorsAboveGround",
        "value": "grossFloorArea_m2",  # officialArea/OfficialArea/value (grossFloorArea)
        "end": "dateOfConstruction",  # dateOfConstruction/DateOfEvent/end
    },
    ".buildingpart.gml": {
        "localId": "localId",
        "numberOfFloorsAboveGround": "numberOfFloorsAboveGround",
        "numberOfFloorsBelowGround": "numberOfFloorsBelowGround",
        "heightBelowGround": "heightBelowGround_m",
    },
    ".otherconstruction.gml": {
        "localId": "localId",
        "constructionNature": "constructionNature",
    },
}
INT_COLUMNS = {"numberOfBuildingUnits", "numberOfDwellings", "numberOfFloorsAboveGround",
               "numberOfFloorsBelowGround"}


def find_member(zip_path: Path, suffix: str) -> str:
    with zipfile.ZipFile(zip_path) as zf:
        matches = [n for n in zf.namelist() if n.lower().endswith(suffix)]
    if len(matches) != 1:
        sys.exit(f"[ERROR] se esperaba un único '*{suffix}' en el ZIP, encontrados: {matches}")
    return matches[0]


def read_layer(zip_path: Path, suffix: str, origin: tuple[float, float]) -> tuple[str, gpd.GeoDataFrame]:
    """Lee un GML del ZIP, valida esquema y CRS, y devuelve el GeoDataFrame en coordenadas locales."""
    member = find_member(zip_path, suffix)
    gdf = gpd.read_file(f"/vsizip/{zip_path.as_posix()}/{member}")
    if gdf.crs is None or not SOURCE_CRS.equals(gdf.crs):
        sys.exit(f"[ERROR] {member}: CRS inesperado {gdf.crs} (se esperaba EPSG:25829)")
    columns = SCHEMA[suffix]
    missing = sorted(set(columns) - set(gdf.columns))
    if missing:
        sys.exit(f"[ERROR] {member}: faltan columnas del esquema verificado: {missing}")
    if gdf.geometry.isna().any():
        sys.exit(f"[ERROR] {member}: {int(gdf.geometry.isna().sum())} geometrías nulas")

    out = gdf[list(columns)].rename(columns=columns)
    for col in INT_COLUMNS & set(out.columns):
        out[col] = pd.to_numeric(out[col], errors="coerce").astype("Int64")
    for col in {"grossFloorArea_m2", "heightBelowGround_m"} & set(out.columns):
        out[col] = pd.to_numeric(out[col], errors="coerce").astype(float)

    geoms = shapely.orient_polygons(gdf.geometry.values, exterior_cw=False)
    geoms = shapely.transform(geoms, lambda c: c - np.asarray(origin))
    return member, gpd.GeoDataFrame(out, geometry=geoms, crs=None)


def part_heights(floors: pd.Series, parent_use: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    f = floors.to_numpy(dtype=float, na_value=np.nan)
    known = ~np.isnan(f)
    shed = parent_use.isin(SHED_USES).to_numpy()
    conditions = [known & (f > 0), known & (f == 0), ~known & shed, ~known]
    # Volumen sin plantas sobre rasante (sótano, patio cubierto...): altura 0 sobre rasante.
    heights = np.select(conditions, [f * FLOOR_HEIGHT_M, 0.0, FALLBACK_SHED_M, FALLBACK_HOUSING_M])
    sources = np.select(conditions, ["catastro_floors", "catastro_zero_floors",
                                     "fallback_shed", "fallback_housing"], default="")
    return heights, sources


def write_geojson(gdf: gpd.GeoDataFrame, path: Path) -> None:
    path.unlink(missing_ok=True)
    # ID_FIELD consume la columna: se usa una copia para conservar localId en las propiedades
    with warnings.catch_warnings():
        # El CRS local (origen desplazado) no tiene código EPSG; se documenta en *.meta.json
        warnings.filterwarnings("ignore", message="'crs' was not provided")
        gdf.assign(_id=gdf["localId"]).to_file(
            path, driver="GeoJSON", engine="pyogrio",
            layer_options={"ID_FIELD": "_id", "COORDINATE_PRECISION": 3, "RFC7946": "NO"})


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--zip", type=Path, default=DEFAULT_ZIP, help="ZIP A.ES.SDGC.BU.<INE>.zip")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Directorio de salida")
    ap.add_argument("--origin", type=float, nargs=2, default=DEFAULT_ORIGIN, metavar=("E0", "N0"),
                    help="Origen local en EPSG:25829 (por defecto centro del municipio)")
    args = ap.parse_args(argv)
    origin = tuple(args.origin)
    args.out.mkdir(parents=True, exist_ok=True)

    b_src, buildings = read_layer(args.zip, ".building.gml", origin)
    p_src, parts = read_layer(args.zip, ".buildingpart.gml", origin)
    o_src, others = read_layer(args.zip, ".otherconstruction.gml", origin)

    # localId observado: '<refcat14>_part<N>' -> enlace con Building.localId
    parts.insert(1, "buildingId", parts["localId"].str.split("_part").str[0])
    parent_use = parts["buildingId"].map(buildings.set_index("localId")["currentUse"])
    parts.insert(2, "currentUse", parent_use)
    parts["height_m"], parts["height_source"] = part_heights(parts["numberOfFloorsAboveGround"], parent_use)
    orphans = int((~parts["buildingId"].isin(buildings["localId"])).sum())

    write_geojson(buildings, args.out / "catastro_buildings.geojson")
    write_geojson(parts, args.out / "catastro_building_parts.geojson")
    write_geojson(others, args.out / "catastro_other_constructions.geojson")

    to_wgs84 = Transformer.from_crs(SOURCE_CRS, "EPSG:4326", always_xy=True)
    bb = np.array(gpd.GeoSeries(pd.concat([buildings.geometry, parts.geometry, others.geometry])).total_bounds)
    sw_lon, sw_lat = to_wgs84.transform(bb[0] + origin[0], bb[1] + origin[1])
    ne_lon, ne_lat = to_wgs84.transform(bb[2] + origin[0], bb[3] + origin[1])
    o_lon, o_lat = to_wgs84.transform(*origin)
    meta = {
        "source_zip": args.zip.name,
        "source_members": [b_src, p_src, o_src],
        "source_crs": "EPSG:25829",
        "local_crs": f"x=E-{origin[0]}, y=N-{origin[1]} (EPSG:25829), z=0 a rasante",
        "origin_epsg25829": list(origin),
        "origin_wgs84_latlon": [o_lat, o_lon],
        "bbox_local": [round(float(v), 3) for v in bb],
        "bbox_wgs84": {"minlat": sw_lat, "minlon": sw_lon, "maxlat": ne_lat, "maxlon": ne_lon},
        "counts": {"buildings": len(buildings), "building_parts": len(parts),
                   "other_constructions": len(others), "orphan_parts": orphans},
        "height_sources": parts["height_source"].value_counts().to_dict(),
        "height_rule": {"floor_m": FLOOR_HEIGHT_M, "fallback_housing_m": FALLBACK_HOUSING_M,
                        "fallback_shed_m": FALLBACK_SHED_M, "shed_uses": sorted(SHED_USES)},
    }
    (args.out / "catastro_buildings.meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(meta, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
