#!/usr/bin/env python3
"""Alturas reales de los edificios a partir del MDS normalizado de edificación del IGN (LiDAR PNOA).

Entrada:
  * `data/processed/catastro_building_parts.geojson` (extract_catastro_buildings.py; coordenadas locales).
  * `data/raw/ign/mdsn_e025_3042.tif` (download_ign.py): altura sobre el suelo de la clase edificación, 2.5 m,
    EPSG:3042, int16 en metros enteros. Inspección y validación previas en `.claude/MEMORY.md` (Fase 2).

Para cada BuildingPart se rasteriza su huella erosionada 0.75 m sobre la malla del MDSn (centro de píxel dentro)
y se toma la mediana de los píxeles con altura ≥ 1.5 m. La altura LiDAR se acepta si:
  * hay al menos MIN_PIXELS píxeles en la huella y al menos la mitad son de edificación (si no, el edificio
    probablemente no existía en el vuelo o lo tapa vegetación), y
  * es plausible frente a las plantas de Catastro: entre 0.6·(plantas·3) − 1 m y 2·(plantas·3) + 3 m.
Una parte sin muestra válida propia (pequeña o tapada) toma la mediana LiDAR de las partes del mismo edificio con
el mismo número de plantas que sí la tienen (`lidar_building`). Si no hay ninguna, se mantiene la altura de Catastro
(plantas × 3 m), que es el respaldo pedido por el usuario.

El fichero se actualiza en su sitio (idempotente: la altura de Catastro se guarda en `height_catastro_m`):
  height_m, height_source ∈ {lidar, catastro_floors, catastro_zero_floors, ...}, lidar_height_m, lidar_pixels,
  lidar_building_share, lidar_status.

Uso:
    python -P tools/gis/apply_lidar_heights.py
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from collections import Counter
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
import shapely
from pyproj import Transformer
from rasterio.features import rasterize

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PARTS = ROOT / "data/processed/catastro_building_parts.geojson"
DEFAULT_META = ROOT / "data/processed/catastro_buildings.meta.json"
DEFAULT_MDSN = ROOT / "data/raw/ign/mdsn_e025_3042.tif"

EROSION_M = 0.5  # evita píxeles de borde que mezclan suelo y tejado
BUILDING_MIN_M = 1.5  # píxel de edificación
MIN_PIXELS = 1  # con 0.75 m y 2 píxeles quedaban sin muestra el 52 % de las partes (Catastro las parte mucho)
MIN_BUILDING_SHARE = 0.5
FLOOR_H = 3.0


def plausible(h: float, floors: int) -> bool:
    nominal = floors * FLOOR_H
    return 0.6 * nominal - 1.0 <= h <= 2.0 * nominal + 3.0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--parts", type=Path, default=DEFAULT_PARTS)
    ap.add_argument("--meta", type=Path, default=DEFAULT_META)
    ap.add_argument("--mdsn", type=Path, default=DEFAULT_MDSN)
    args = ap.parse_args(argv)
    for p in (args.parts, args.meta, args.mdsn):
        if not p.exists():
            sys.exit(f"[ERROR] {p} no existe (ver la secuencia del pipeline en .claude/MEMORY.md)")

    origin = json.loads(args.meta.read_text(encoding="utf-8"))["origin_epsg25829"]
    parts = gpd.read_file(args.parts)
    if "height_catastro_m" not in parts:
        parts["height_catastro_m"] = parts["height_m"]
        parts["height_source_catastro"] = parts["height_source"]

    with rasterio.open(args.mdsn) as src:
        mdsn = src.read(1).astype(np.float32)
        transform, shape, crs = src.transform, src.shape, src.crs
    if crs.to_epsg() != 3042:
        sys.exit(f"[ERROR] {args.mdsn}: CRS {crs}, se esperaba EPSG:3042")

    # local -> EPSG:25829 -> EPSG:25830 (EPSG:3042 son las mismas coordenadas con ejes N,E; rasterio trabaja en x,y)
    to30 = Transformer.from_crs(25829, 25830, always_xy=True)
    shifted = shapely.transform(parts.geometry.values, lambda c: c + np.asarray(origin))
    geoms30 = shapely.transform(shifted, lambda c: np.column_stack(to30.transform(c[:, 0], c[:, 1])))
    eroded = shapely.buffer(geoms30, -EROSION_M, join_style="mitre")

    ids = np.arange(1, len(parts) + 1, dtype=np.int32)
    shapes = [(g, int(i)) for g, i in zip(eroded, ids) if not g.is_empty]
    labels = rasterize(shapes, out_shape=shape, transform=transform, fill=0, dtype="int32", all_touched=False)

    flat_l, flat_v = labels.ravel(), mdsn.ravel()
    sel = flat_l > 0
    lab, val = flat_l[sel], flat_v[sel]
    order = np.argsort(lab, kind="stable")
    lab, val = lab[order], val[order]
    starts = np.searchsorted(lab, ids, side="left")
    ends = np.searchsorted(lab, ids, side="right")

    lidar_h, pixels, share, status = [], [], [], []
    final_h, final_src = list(parts["height_catastro_m"]), list(parts["height_source_catastro"])
    for k, (a, b) in enumerate(zip(starts, ends)):
        v = val[a:b]
        n = len(v)
        bld = v[v >= BUILDING_MIN_M]
        s = len(bld) / n if n else 0.0
        h = float(np.median(bld)) if len(bld) else float("nan")
        lidar_h.append(round(h, 2) if len(bld) else None)
        pixels.append(int(n))
        share.append(round(s, 3))
        floors = parts["numberOfFloorsAboveGround"].iloc[k]
        floors = int(floors) if floors == floors and floors is not None else 0
        if floors <= 0:
            st = "zero_floors"  # sin volumen sobre rasante en Catastro: se respeta
        elif n < MIN_PIXELS:
            st = "too_small"
        elif s < MIN_BUILDING_SHARE:
            st = "no_building_in_lidar"
        elif not plausible(h, floors):
            st = "implausible"
        else:
            st = "ok"
            final_h[k] = h
            final_src[k] = "lidar"
        status.append(st)

    # Partes sin muestra propia: toman la altura LiDAR de otra parte del mismo edificio con las mismas plantas
    measured = {}
    for k, st in enumerate(status):
        if st == "ok":
            key = (parts["buildingId"].iloc[k], int(parts["numberOfFloorsAboveGround"].iloc[k]))
            measured.setdefault(key, []).append(final_h[k])
    for k, st in enumerate(status):
        if st in ("too_small", "no_building_in_lidar"):
            floors = parts["numberOfFloorsAboveGround"].iloc[k]
            key = (parts["buildingId"].iloc[k], int(floors) if floors == floors else 0)
            if key in measured:
                final_h[k] = float(np.median(measured[key]))
                final_src[k] = "lidar_building"
                status[k] = f"{st}_from_building"

    parts["lidar_height_m"] = lidar_h
    parts["lidar_pixels"] = pixels
    parts["lidar_building_share"] = share
    parts["lidar_status"] = status
    parts["height_m"] = final_h
    parts["height_source"] = final_src

    args.parts.unlink()
    with warnings.catch_warnings():
        # CRS local sin código EPSG (ver catastro_buildings.meta.json); ID_FIELD consume la columna: se usa una copia
        warnings.filterwarnings("ignore", message="'crs' was not provided")
        parts.set_crs(None, allow_override=True).assign(_id=parts["localId"]).to_file(
            args.parts, driver="GeoJSON", engine="pyogrio",
            layer_options={"ID_FIELD": "_id", "COORDINATE_PRECISION": 3, "RFC7946": "NO"})

    ok = parts[parts["lidar_status"] == "ok"]
    ratio = (ok["height_m"] / ok["height_catastro_m"]).median() if len(ok) else float("nan")
    print(json.dumps({
        "parts": len(parts),
        "lidar_status": dict(Counter(status)),
        "height_source": parts["height_source"].value_counts().to_dict(),
        "lidar_vs_catastro_median_ratio": round(float(ratio), 3),
        "lidar_height_median_by_floors": ok.groupby("numberOfFloorsAboveGround")["height_m"].median().to_dict(),
        "height_max_m": float(parts["height_m"].max()),
    }, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
