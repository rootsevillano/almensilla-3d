#!/usr/bin/env python3
"""Modelo del terreno local (MDT05 del IGN) para asentar todo el pipeline sobre el relieve real.

Entrada: `data/raw/ign/mdt05_25830.tif` (download_ign.py): EPSG:25830, 5 m, int16 en **metros enteros**.
Proceso:
  1. Reproyección bilineal a una malla local de 5 m en EPSG:25829, alineada con el origen local del proyecto
     (`catastro_buildings.meta.json`) y con 80 m de margen alrededor del término.
  2. Suavizado gaussiano (sigma = 3 celdas = 15 m) para quitar los escalones de 1 m de la cuantización entera; el
     relieve del Aljarafe es suave y a esa escala no se pierde forma.
  3. Cota cero: la del terreno en el origen local (redondeada al metro), para que las coordenadas sigan siendo
     relativas al origen (0, 0, 0) del contrato del agente 01.
Salida: `data/processed/dem_local.tif` (float32, metros relativos a la cota cero) y `dem_local.json`.

En los demás scripts: `from dem import LocalDEM; dem = LocalDEM.load(); z = dem.sample(x, y)` (coordenadas locales,
x = Este, y = Norte; devuelve la altura relativa con interpolación bilineal).

Uso:
    python -P tools/gis/dem.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SRC = ROOT / "data/raw/ign/mdt05_25830.tif"
DEFAULT_META = ROOT / "data/processed/catastro_buildings.meta.json"
DEFAULT_TIF = ROOT / "data/processed/dem_local.tif"
DEFAULT_JSON = ROOT / "data/processed/dem_local.json"
RES_M = 5.0
PAD_M = 80.0  # el MDT se descargó con 100 m de margen (download_ign.PAD_M); el giro 25830→25829 se come algo
SIGMA_CELLS = 3.0
# Lado de celda de la malla del terreno (build_terrain_glb.py) y de la partición de lo que se drapea encima
# (build_roads_glb.py). Única fuente: si no coinciden, los viales dejan de seguir el plano exacto del terreno.
# 20 m: con el MDT suavizado a 15 m no se pierde forma (con 10 m había 4 veces más triángulos).
MESH_CELL_M = 20.0
# extensión del término en coordenadas locales (CadastralZoning), ver MEMORY.md; se amplía con PAD_M
MUNICIPALITY_BOUNDS = (-3108.03, -2113.87, 3108.11, 2114.70)


def gaussian_smooth(a: np.ndarray, sigma: float) -> np.ndarray:
    """Gaussiana separable con borde replicado (sin scipy)."""
    radius = int(np.ceil(3 * sigma))
    k = np.exp(-0.5 * (np.arange(-radius, radius + 1) / sigma) ** 2)
    k /= k.sum()
    out = np.pad(a, radius, mode="edge")
    out = np.apply_along_axis(lambda r: np.convolve(r, k, mode="valid"), 1, out)
    out = np.apply_along_axis(lambda c: np.convolve(c, k, mode="valid"), 0, out)
    return out


class LocalDEM:
    """Altura relativa del terreno en coordenadas locales, con interpolación bilineal."""

    def __init__(self, heights: np.ndarray, x0: float, y1: float, res: float, z0: float):
        self.h, self.x0, self.y1, self.res, self.z0 = heights, x0, y1, res, z0

    @classmethod
    def load(cls, tif: Path = DEFAULT_TIF, meta: Path = DEFAULT_JSON) -> "LocalDEM":
        if not tif.exists():
            sys.exit(f"[ERROR] {tif} no existe: ejecuta antes tools/gis/dem.py")
        info = json.loads(meta.read_text(encoding="utf-8"))
        with rasterio.open(tif) as r:
            h = r.read(1).astype(np.float64)
        return cls(h, info["x0_local"], info["y1_local"], info["res_m"], info["z0_m"])

    def sample(self, x, y) -> np.ndarray:
        x = np.asarray(x, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64)
        # centros de celda en (x0 + (c+0.5)·res, y1 − (r+0.5)·res)
        c = (x - self.x0) / self.res - 0.5
        r = (self.y1 - y) / self.res - 0.5
        rows, cols = self.h.shape
        c = np.clip(c, 0, cols - 1.000001)
        r = np.clip(r, 0, rows - 1.000001)
        c0, r0 = np.floor(c).astype(int), np.floor(r).astype(int)
        fc, fr = c - c0, r - r0
        h = self.h
        top = h[r0, c0] * (1 - fc) + h[r0, c0 + 1] * fc
        bottom = h[r0 + 1, c0] * (1 - fc) + h[r0 + 1, c0 + 1] * fc
        return top * (1 - fr) + bottom * fr

    def sample_mesh(self, x, y, cell: float = MESH_CELL_M) -> np.ndarray:
        """Altura de la **malla del terreno** de build_terrain_glb.py (cuadrícula global de `cell` m, lineal por
        triángulos (a,b,c) y (a,c,d)), no del MDT bilineal: lo que se drapea encima (viales, piscinas, árboles)
        debe seguir la superficie que se dibuja. Con el MDT bilineal, en los terraplenes de la autovía la calzada
        quedaba hasta 22 cm bajo el terreno dibujado."""
        x = np.asarray(x, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64)
        c0, r0 = np.floor(x / cell), np.floor(y / cell)
        fx, fy = x / cell - c0, y / cell - r0
        x0, y0 = c0 * cell, r0 * cell
        z00, z10 = self.sample(x0, y0), self.sample(x0 + cell, y0)
        z11, z01 = self.sample(x0 + cell, y0 + cell), self.sample(x0, y0 + cell)
        return np.where(fx >= fy, z00 + fx * (z10 - z00) + fy * (z11 - z10),
                        z00 + fy * (z01 - z00) + fx * (z11 - z01))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--meta", type=Path, default=DEFAULT_META)
    ap.add_argument("--sigma", type=float, default=SIGMA_CELLS, help="Suavizado en celdas de 5 m")
    args = ap.parse_args(argv)
    if not args.src.exists():
        sys.exit(f"[ERROR] {args.src} no existe: ejecuta antes download_ign.py --only dem")

    e0, n0 = json.loads(args.meta.read_text(encoding="utf-8"))["origin_epsg25829"]
    minx, miny, maxx, maxy = MUNICIPALITY_BOUNDS
    x0 = np.floor((minx - PAD_M) / RES_M) * RES_M
    y1 = np.ceil((maxy + PAD_M) / RES_M) * RES_M
    cols = int(np.ceil((maxx + PAD_M - x0) / RES_M))
    rows = int(np.ceil((y1 - (miny - PAD_M)) / RES_M))
    dst_transform = from_origin(e0 + x0, n0 + y1, RES_M, RES_M)
    raw = np.full((rows, cols), np.nan, dtype=np.float32)
    with rasterio.open(args.src) as src:
        reproject(rasterio.band(src, 1), raw, src_transform=src.transform, src_crs=src.crs,
                  dst_transform=dst_transform, dst_crs="EPSG:25829", resampling=Resampling.bilinear,
                  dst_nodata=np.nan)
    if np.isnan(raw).any():
        sys.exit(f"[ERROR] {int(np.isnan(raw).sum())} celdas sin dato: el MDT descargado no cubre la malla local")

    smooth = gaussian_smooth(raw.astype(np.float64), args.sigma)
    dem = LocalDEM(smooth, x0, y1, RES_M, 0.0)
    z0 = float(np.round(dem.sample(0.0, 0.0)))
    rel = (smooth - z0).astype(np.float32)

    with rasterio.open(DEFAULT_TIF, "w", driver="GTiff", width=cols, height=rows, count=1, dtype="float32",
                       crs="EPSG:25829", transform=dst_transform, compress="deflate") as dst:
        dst.write(rel, 1)
        dst.update_tags(note=f"altura relativa: z_abs = z + {z0} m (EPSG:5782)")
    diff = smooth - raw
    info = {
        "source": args.src.name, "crs_grid": "EPSG:25829", "res_m": RES_M, "x0_local": x0, "y1_local": y1,
        "cols": cols, "rows": rows, "z0_m": z0, "sigma_cells": args.sigma,
        "abs_range_m": [round(float(raw.min()), 1), round(float(raw.max()), 1)],
        "rel_range_m": [round(float(rel.min()), 2), round(float(rel.max()), 2)],
        "smoothing_diff_m": {"p50_abs": round(float(np.median(np.abs(diff))), 3),
                             "p99_abs": round(float(np.percentile(np.abs(diff), 99)), 3),
                             "max_abs": round(float(np.abs(diff).max()), 3)},
    }
    DEFAULT_JSON.write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(info, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
