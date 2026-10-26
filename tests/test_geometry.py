"""Validación de geometría de los GLB (criterio QA 1 del agente 04) y convenciones de nombres."""
from __future__ import annotations

import re

import numpy as np

NODE_PATTERNS = {
    "almensilla_buildings.glb": [r"COL_\w+", r"PARAPET_-?\d+_-?\d+"],
    "almensilla_roads.glb": [r"ROAD_(carriageway|track|pedestrian|sidewalk)_-?\d+_-?\d+"],
    "almensilla_terrain.glb": [r"TERRAIN_-?\d+_-?\d+", r"POOL_(water|coping)_-?\d+_-?\d+"],
}


def test_no_nan_or_inf(scenes):
    for name, scene in scenes.items():
        for node, mesh in scene.geometry.items():
            assert np.isfinite(mesh.vertices).all(), f"{name}/{node}: vértices NaN o infinitos"


def test_node_names(scenes):
    for name, patterns in NODE_PATTERNS.items():
        nodes = list(scenes[name].geometry)
        assert nodes, f"{name} sin nodos"
        bad = [n for n in nodes if not any(re.fullmatch(p, n) for p in patterns)]
        assert not bad, f"{name}: nodos con nombre inesperado {bad[:5]}"
        assert len(set(nodes)) == len(nodes), f"{name}: nombres de nodo repetidos"


def test_buildings_closed_and_outward(scenes):
    """Las mallas de colisión COL_ son sólidos cerrados con las normales hacia fuera (volumen positivo)."""
    bad = []
    for node, mesh in scenes["almensilla_buildings.glb"].geometry.items():
        if node.startswith("COL_") and not (mesh.is_watertight and mesh.is_winding_consistent and mesh.volume > 0):
            bad.append(node)
    assert not bad, f"{len(bad)} edificios abiertos o invertidos, p. ej. {bad[:5]}"


def test_buildings_have_floors(scenes):
    """Atributo `_floors` (plantas de Catastro por vértice) que usa el shader de fachadas."""
    for node, mesh in scenes["almensilla_buildings.glb"].geometry.items():
        if not node.startswith("COL_"):
            continue
        floors = mesh.vertex_attributes.get("_floors", mesh.vertex_attributes.get("floors"))
        assert floors is not None, f"{node}: sin atributo _floors"
        assert len(floors) == len(mesh.vertices)
        assert floors.min() >= 1 and floors.max() <= 10, f"{node}: plantas fuera de rango"


def test_walkable_surfaces_face_up(scenes):
    """Terreno, viales planos y lámina de las piscinas miran hacia arriba (ninguna cara invertida).
    Se toleran astillas casi verticales del borde del término (normal Y positiva pero pequeña)."""
    groups = {
        "almensilla_terrain.glb": ("TERRAIN_", "POOL_water"),
        "almensilla_roads.glb": ("ROAD_carriageway", "ROAD_track", "ROAD_pedestrian"),
    }
    for name, prefixes in groups.items():
        for node, mesh in scenes[name].geometry.items():
            if node.startswith(prefixes):
                down = (mesh.face_normals[:, 1] < 0).sum()
                assert down == 0, f"{name}/{node}: {down} caras invertidas"


def test_sidewalks_have_no_downward_faces(scenes):
    for node, mesh in scenes["almensilla_roads.glb"].geometry.items():
        if node.startswith("ROAD_sidewalk"):
            assert (mesh.face_normals[:, 1] < -0.5).sum() == 0, f"{node}: caras mirando hacia abajo"


def test_shared_axes_and_extent(scenes):
    """Los tres GLB comparten sistema (X=E, Y=arriba, Z=−N) y caben en el término (~6.2 × 4.2 km)."""
    for name, scene in scenes.items():
        lo, hi = scene.bounds
        assert lo[0] > -3300 and hi[0] < 3300, f"{name}: X fuera del término"
        assert lo[2] > -2300 and hi[2] < 2300, f"{name}: Z fuera del término"
        assert -60 < lo[1] and hi[1] < 120, f"{name}: cotas Y inverosímiles {lo[1]:.1f} … {hi[1]:.1f}"
