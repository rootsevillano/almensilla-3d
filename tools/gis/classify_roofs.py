#!/usr/bin/env python3
"""Tipo de cubierta de cada parte de edificio (teja / azotea) a partir del color de la ortofoto PNOA.

Inspección (ver `.claude/MEMORY.md`, Fase 3): con la ortofoto se ve que Almensilla tiene muchos chalés con tejado de
teja a cuatro aguas (urbanizaciones) junto a azoteas planas. Se mide la "rojez" media de la cubierta,
(R − B) / (R + G + B), en la huella erosionada 1 m (para no mezclar con el suelo de alrededor), sobre la ortofoto de
0.5 m. Mosaicos de validación: ≥ 0.065 es casi siempre teja; por debajo dominan azoteas, cubiertas claras o grises y
placas solares.

Actualiza `data/processed/catastro_building_parts.geojson` en su sitio (idempotente):
  roof_redness (o vacío si no hay muestra), roof_type ∈ {tile, flat}. Las partes sin muestra (pequeñas) toman el tipo
  mayoritario de las partes medidas de su edificio; si no hay ninguna, azotea.

Uso:
    python -P tools/gis/classify_roofs.py
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
import shapely
from PIL import Image
from rasterio.features import rasterize
from rasterio.transform import from_origin

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PARTS = ROOT / "data/processed/catastro_building_parts.geojson"
DEFAULT_PNOA = ROOT / "data/raw/ign/pnoa"
TILE_M = 500.0
PX_M = 0.5  # ortofoto de 1000 px por tesela de 500 m (download_ign.py)
EROSION_M = 1.0
MIN_PIXELS = 8  # 2 m² de cubierta
TILE_REDNESS = 0.065


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--parts", type=Path, default=DEFAULT_PARTS)
    ap.add_argument("--pnoa", type=Path, default=DEFAULT_PNOA)
    args = ap.parse_args(argv)
    if not args.parts.exists():
        sys.exit(f"[ERROR] {args.parts} no existe: ejecuta antes extract_catastro_buildings.py")

    parts = gpd.read_file(args.parts)
    redness = np.full(len(parts), np.nan)
    centroids = parts.geometry.centroid
    tiles = list(zip((centroids.x // TILE_M).astype(int), (centroids.y // TILE_M).astype(int)))
    by_tile: dict[tuple[int, int], list[int]] = {}
    for k, t in enumerate(tiles):
        by_tile.setdefault(t, []).append(k)
    missing_tiles = 0
    for (i, j), ks in by_tile.items():
        path = args.pnoa / f"pnoa_{i}_{j}.jpg"
        if not path.exists():
            missing_tiles += 1
            continue
        img = np.asarray(Image.open(path).convert("RGB"), dtype=np.float32)
        eroded = shapely.buffer(parts.geometry.values[ks], -EROSION_M)
        shapes = [(g, n + 1) for n, g in enumerate(eroded) if not g.is_empty]
        if not shapes:
            continue
        labels = rasterize(shapes, out_shape=img.shape[:2], transform=from_origin(i * TILE_M, (j + 1) * TILE_M, PX_M, PX_M),
                           fill=0, dtype="int32")
        flat_l = labels.ravel()
        sel = flat_l > 0
        lab = flat_l[sel] - 1
        rgb = img.reshape(-1, 3)[sel]
        counts = np.bincount(lab, minlength=len(ks))
        sums = np.stack([np.bincount(lab, weights=rgb[:, c], minlength=len(ks)) for c in range(3)], axis=1)
        for n, k in enumerate(ks):
            if counts[n] >= MIN_PIXELS:
                r, g, b = sums[n] / counts[n]
                redness[k] = (r - b) / (r + g + b)

    roof = np.where(np.isnan(redness), "", np.where(redness >= TILE_REDNESS, "tile", "flat")).astype(object)
    # partes sin muestra: tipo mayoritario de las partes medidas del mismo edificio
    majority = {}
    for bid, grp in parts.assign(roof=roof).groupby("buildingId"):
        measured = [r for r in grp["roof"] if r]
        if measured:
            majority[bid] = Counter(measured).most_common(1)[0][0]
    inherited = 0
    for k in np.where(roof == "")[0]:
        roof[k] = majority.get(parts["buildingId"].iloc[k], "flat")
        inherited += 1

    parts["roof_redness"] = [None if np.isnan(v) else round(float(v), 4) for v in redness]
    parts["roof_type"] = roof
    args.parts.unlink()
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="'crs' was not provided")
        parts.set_crs(None, allow_override=True).assign(_id=parts["localId"]).to_file(
            args.parts, driver="GeoJSON", engine="pyogrio",
            layer_options={"ID_FIELD": "_id", "COORDINATE_PRECISION": 3, "RFC7946": "NO"})
    print(json.dumps({
        "parts": len(parts), "measured": int((~np.isnan(redness)).sum()), "inherited_or_default": inherited,
        "roof_type": dict(Counter(roof)), "threshold": TILE_REDNESS, "missing_ortho_tiles": missing_tiles,
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
