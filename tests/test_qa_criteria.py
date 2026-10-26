"""Criterios de QA del agente 04 que se pueden automatizar sin navegador, y sanidad de los datos intermedios.

El criterio 2 (≥60 FPS a 1080p) se mide en el visor con `?bench=20` (ver `.claude/MEMORY.md`).
"""
from __future__ import annotations

import json

import geopandas as gpd
import numpy as np

from conftest import PROCESSED, require

PRINCIPAL = {"secondary", "tertiary", "residential", "construction"}


def test_principal_street_widths():
    """Criterio 3: las calles principales miden aprox. 6–10 m (anchura medida de fachada a fachada)."""
    # coordenadas locales en metros; el driver GeoJSON les asigna CRS84 por defecto (ver MEMORY.md): se quita
    roads = gpd.read_file(require(PROCESSED / "osm_roads.geojson")).set_crs(None, allow_override=True)
    principal = roads[roads["highway"].isin(PRINCIPAL) & ~roads["is_area"]]
    median = float(np.median(principal["width_m"]))
    length = principal.length
    share = float(length[(principal["width_m"] >= 6) & (principal["width_m"] <= 10)].sum() / length.sum())
    assert 6.0 <= median <= 10.0, f"mediana de calles principales {median:.2f} m fuera de 6–10 m"
    assert share >= 0.7, f"solo el {share:.0%} de la longitud principal está entre 6 y 10 m"


def test_building_heights_plausible():
    """Alturas finales: LiDAR o respaldo de Catastro, positivas y verosímiles para el término (≤ 25 m)."""
    parts = gpd.read_file(require(PROCESSED / "catastro_building_parts.geojson"))
    built = parts[parts["height_source"] != "catastro_zero_floors"]
    assert (built["height_m"] > 0).all()
    assert built["height_m"].max() <= 25.0
    if "lidar_status" in parts:
        share = built["height_source"].isin(["lidar", "lidar_building"]).mean()
        assert share >= 0.8, f"solo el {share:.0%} de las partes con plantas tiene altura LiDAR"


def test_dem_metadata():
    info = json.loads(require(PROCESSED / "dem_local.json").read_text(encoding="utf-8"))
    assert info["crs_grid"] == "EPSG:25829" and info["res_m"] == 5.0
    lo, hi = info["rel_range_m"]
    assert -60 < lo < 0 < hi < 80, f"relieve relativo inverosímil: {lo} … {hi} m"
    assert info["smoothing_diff_m"]["p99_abs"] < 1.5, "el suavizado deforma el MDT más de la cuantización"


def test_tree_counts_and_types(trees):
    types = trees["types"]
    counts = np.bincount([t[2] for t in trees["trees"]], minlength=len(types))
    assert len(trees["trees"]) > 10_000, "demasiados pocos árboles: ¿falló la detección LiDAR?"
    assert counts[types.index("olive")] > counts.sum() * 0.3, "el olivar debería dominar en el término"
