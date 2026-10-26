"""Fixtures compartidas de las pruebas del pipeline (agente 04).

Las pruebas leen las salidas ya generadas (`data/export`, `data/processed`); si faltan, se saltan con un aviso para
regenerarlas con `python -P tools/gis/run_pipeline.py`. Ejecución: `python -P -m pytest tests`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
EXPORT = ROOT / "data/export"
PROCESSED = ROOT / "data/processed"
APP_MODELS = ROOT / "app/public/models"
GLBS = ["almensilla_buildings.glb", "almensilla_roads.glb", "almensilla_terrain.glb"]

sys.path.insert(0, str(ROOT / "tools/gis"))


def require(path: Path) -> Path:
    if not path.exists():
        pytest.skip(f"{path.relative_to(ROOT)} no existe: ejecuta python -P tools/gis/run_pipeline.py")
    return path


@pytest.fixture(scope="session")
def scenes():
    import trimesh
    return {name: trimesh.load(require(EXPORT / name), process=False) for name in GLBS}


@pytest.fixture(scope="session")
def trees():
    return json.loads(require(EXPORT / "almensilla_trees.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def dem():
    from dem import LocalDEM
    require(PROCESSED / "dem_local.tif")
    return LocalDEM.load()


class TerrainSurface:
    """Altura de la malla del terreno **tal como está en el GLB** (no la función de muestreo del pipeline):
    triángulos indexados en planta y altura por baricéntricas, la superficie más alta en (x, z)."""

    def __init__(self, meshes, cell: float = 10.0):
        tris = np.concatenate([m.vertices[m.faces] for m in meshes])  # (n, 3, 3) en glTF
        self.tris, self.cell, self.grid = tris, cell, {}
        lo = np.floor(tris[:, :, [0, 2]].min(axis=1) / cell).astype(int)
        hi = np.floor(tris[:, :, [0, 2]].max(axis=1) / cell).astype(int)
        for t, (i0, j0), (i1, j1) in zip(range(len(tris)), lo, hi):
            for i in range(i0, i1 + 1):
                for j in range(j0, j1 + 1):
                    self.grid.setdefault((i, j), []).append(t)

    def height(self, x: float, z: float):
        best = None
        for t in self.grid.get((int(np.floor(x / self.cell)), int(np.floor(z / self.cell))), ()):
            (ax, ay, az), (bx, by, bz), (cx, cy, cz) = self.tris[t]
            d = (bz - cz) * (ax - cx) + (cx - bx) * (az - cz)
            if abs(d) < 1e-12:
                continue
            l1 = ((bz - cz) * (x - cx) + (cx - bx) * (z - cz)) / d
            l2 = ((cz - az) * (x - cx) + (ax - cx) * (z - cz)) / d
            l3 = 1 - l1 - l2
            if min(l1, l2, l3) < -1e-6:
                continue
            y = l1 * ay + l2 * by + l3 * cy
            best = y if best is None else max(best, y)
        return best


@pytest.fixture(scope="session")
def terrain_surface(scenes):
    meshes = [m for n, m in scenes["almensilla_terrain.glb"].geometry.items() if n.startswith("TERRAIN_")]
    return TerrainSurface(meshes)


@pytest.fixture(scope="session")
def rng():
    return np.random.default_rng(41010)
