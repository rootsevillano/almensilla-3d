"""Costuras con el relieve: lo que va encima del terreno queda encima y los edificios no flotan.

Se mide contra la malla del terreno del GLB (`TerrainSurface`), no contra la función de muestreo del pipeline, para
que la prueba detecte también un desajuste entre la malla dibujada y lo drapeado encima.
"""
from __future__ import annotations

import numpy as np
import pytest

FLOAT32_TOL = 1e-3  # los GLB guardan float32 (~0.2 mm a 3 km del origen)


def _sample(points, n, rng):
    return points if len(points) <= n else points[rng.choice(len(points), n, replace=False)]


def _margins(points, surface):
    out = []
    for x, y, z in points:
        h = surface.height(x, z)
        if h is not None:
            out.append(y - h)
    return np.asarray(out)


@pytest.mark.parametrize("group", ["carriageway", "track", "pedestrian"])
def test_roads_above_terrain(scenes, terrain_surface, rng, group):
    meshes = [m for n, m in scenes["almensilla_roads.glb"].geometry.items() if n.startswith(f"ROAD_{group}")]
    if not meshes:
        pytest.skip(f"sin viales {group}")
    verts = _sample(np.concatenate([m.vertices for m in meshes]), 1500, rng)
    centers = _sample(np.concatenate([m.triangles_center for m in meshes]), 1500, rng)  # entre vértices
    for label, pts in (("vértices", verts), ("centroides", centers)):
        m = _margins(pts, terrain_surface)
        assert len(m) > 0.9 * len(pts), f"{group}: muchos puntos fuera del terreno"
        assert m.min() > -FLOAT32_TOL, f"{group} ({label}): {int((m < -FLOAT32_TOL).sum())} bajo el terreno, mín {m.min():.3f} m"


def test_sidewalk_tops_above_terrain(scenes, terrain_surface, rng):
    meshes = [m for n, m in scenes["almensilla_roads.glb"].geometry.items() if n.startswith("ROAD_sidewalk")]
    tops = []
    for m in meshes:
        up = m.face_normals[:, 1] > 0.5
        tops.append(m.triangles_center[up])
    m = _margins(_sample(np.concatenate(tops), 1500, rng), terrain_surface)
    assert m.min() > 0.1, f"tapa de acera a {m.min():.3f} m del terreno (se esperan ~0.21 m)"


def test_pool_water_above_terrain(scenes, terrain_surface, rng):
    meshes = [m for n, m in scenes["almensilla_terrain.glb"].geometry.items() if n.startswith("POOL_water")]
    m = _margins(_sample(np.concatenate([x.vertices for x in meshes]), 1500, rng), terrain_surface)
    assert m.min() > -FLOAT32_TOL, f"agua de piscina bajo el terreno: mín {m.min():.3f} m"


def test_buildings_start_below_terrain(scenes, terrain_surface):
    """Cada edificio arranca bajo la malla del terreno en todos sus vértices inferiores: nada flota en ladera."""
    floating = []
    for node, mesh in scenes["almensilla_buildings.glb"].geometry.items():
        if not node.startswith("COL_"):
            continue
        v = mesh.vertices
        base = v[:, 1].min()
        for x, _, z in v[v[:, 1] < base + 0.01][::4]:
            h = terrain_surface.height(x, z)
            if h is not None and h < base - FLOAT32_TOL:
                floating.append(node)
                break
    assert not floating, f"{len(floating)} edificios con base sobre el terreno, p. ej. {floating[:5]}"


def test_trees_on_terrain(trees, terrain_surface, rng):
    fields = trees["fields"]
    if "y" not in fields:
        pytest.skip("árboles sin cota (formato antiguo)")
    ix, iz, iy = fields.index("x"), fields.index("z"), fields.index("y")
    rows = np.asarray(trees["trees"])
    sample = _sample(rows, 2000, rng)
    diffs = [t[iy] - terrain_surface.height(t[ix], t[iz]) for t in sample if terrain_surface.height(t[ix], t[iz]) is not None]
    diffs = np.asarray(diffs)
    assert np.abs(diffs).max() < 0.05, f"árboles separados del terreno hasta {np.abs(diffs).max():.3f} m"
