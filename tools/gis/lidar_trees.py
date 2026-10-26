"""Detección de árboles individuales en el MDS normalizado de vegetación del IGN (LiDAR PNOA).

Entrada: `data/raw/ign/mdsn_v025_3042.tif` (download_ign.py): altura sobre el suelo de la clase vegetación, 2.5 m,
EPSG:3042 (ejes N,E), int16 en metros enteros. Inspección en `.claude/MEMORY.md` (Fase 2).

Método (detección por máximos locales, habitual en LiDAR forestal):
  1. Reproyección (vecino más próximo, para no rebajar las cimas) a una malla local de 2.5 m en EPSG:25829.
  2. Los valores enteros forman mesetas con empates: se ordena por `altura + 0.01·suavizada` (gaussiana, sigma
     0.7 px), así el suavizado solo desempata y nunca rebaja una cima. (Umbralizar la suavizada borraba los olivos:
     un píxel aislado de 3 m rodeado de ceros quedaba en ~1 m.)
  3. Cima = píxel con altura ≥ MIN_TREE_H que es el máximo de su ventana: 3×3 (7.5 m) o 5×5 (12.5 m) si supera
     TALL_H, porque una copa grande ocupa varios píxeles y con 3×3 se partiría en varios árboles.
Devuelve posición (centro del píxel, coordenadas locales), altura de la cima (de la malla original, en metros) y un
radio de copa estimado por alometría simple a partir de la altura.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject

from dem import gaussian_smooth

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MDSN_V = ROOT / "data/raw/ign/mdsn_v025_3042.tif"
RES_M = 2.5
MIN_TREE_H = 2.0  # olivos: 2–3 m en el dato entero; por debajo, cultivos y matorral bajo
TALL_H = 7.0
SMOOTH_SIGMA_PX = 0.7


def window_max(a: np.ndarray, radius: int) -> np.ndarray:
    pad = np.pad(a, radius, mode="constant", constant_values=-np.inf)
    win = np.lib.stride_tricks.sliding_window_view(pad, (2 * radius + 1, 2 * radius + 1))
    return win.max(axis=(-1, -2))


def crown_radius(h: np.ndarray) -> np.ndarray:
    """Radio de copa (m) por alometría simple: ~0.35·h + 0.5, entre 1.2 y 6 m."""
    return np.clip(0.35 * h + 0.5, 1.2, 6.0)


def detect_trees(origin, bounds, mdsn_path: Path = DEFAULT_MDSN_V):
    """Árboles en el rectángulo local `bounds` (minx, miny, maxx, maxy). Devuelve x, y, altura, radio (arrays)."""
    e0, n0 = origin
    minx, miny, maxx, maxy = bounds
    x0 = np.floor(minx / RES_M) * RES_M
    y1 = np.ceil(maxy / RES_M) * RES_M
    cols = int(np.ceil((maxx - x0) / RES_M))
    rows = int(np.ceil((y1 - miny) / RES_M))
    grid = np.zeros((rows, cols), dtype=np.float32)
    with rasterio.open(mdsn_path) as src:
        reproject(rasterio.band(src, 1), grid, src_transform=src.transform, src_crs=src.crs,
                  dst_transform=from_origin(e0 + x0, n0 + y1, RES_M, RES_M), dst_crs="EPSG:25829",
                  resampling=Resampling.nearest, dst_nodata=0)
    score = grid + 0.01 * gaussian_smooth(grid.astype(np.float64), SMOOTH_SIGMA_PX)
    peak = grid >= MIN_TREE_H
    small = score >= window_max(score, 1)
    large = score >= window_max(score, 2)
    peak &= np.where(grid > TALL_H, large, small)
    r, c = np.nonzero(peak)
    h = grid[r, c].astype(np.float64)
    x = x0 + (c + 0.5) * RES_M
    y = y1 - (r + 0.5) * RES_M
    stats = {"grid": [rows, cols], "veg_px_ge_min": int((grid >= MIN_TREE_H).sum()), "peaks": int(len(h))}
    return x, y, h, crown_radius(h), stats


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    meta = json.loads((ROOT / "data/processed/catastro_buildings.meta.json").read_text(encoding="utf-8"))
    x, y, h, rad, st = detect_trees(meta["origin_epsg25829"], (-3108.03, -2113.87, 3108.11, 2114.70))
    print(json.dumps({**st, "h_p50": float(np.median(h)), "h_p95": float(np.percentile(h, 95)),
                      "h_max": float(h.max())}, indent=2))
