"""Map-pack para WorldOpen (agente 04): anonimización, integridad del grafo y de los edificios.

Requiere haber ejecutado tools/gis/build_logic.py y tools/gis/pack_map.py (pasos `logic` y `pack` del pipeline).
"""
from __future__ import annotations

import base64
import json
import re
from collections import defaultdict
from pathlib import Path

import numpy as np
import pytest

from conftest import EXPORT, require

import pack_map  # tools/gis está en sys.path (conftest)

PACK = EXPORT / "mappack" / "valdeolivo-1.0.0"


@pytest.fixture(scope="module")
def pack() -> Path:
    return require(PACK / "manifest.json").parent


@pytest.fixture(scope="module")
def logic(pack):
    b = json.loads((pack / "logic/buildings.json").read_text(encoding="utf-8"))
    s = json.loads((pack / "logic/streets.json").read_text(encoding="utf-8"))
    return b, s


def real_street_names() -> set[str]:
    streets = json.loads(require(EXPORT / "logic/streets.json").read_text(encoding="utf-8"))
    return {n for n in streets["wayNames"] if n}


def test_auditoria_limpia(pack):
    assert pack_map.audit(pack, real_street_names()) == {}


def test_la_auditoria_detecta_datos_reales():
    """La auditoría no es de adorno: encuentra lo que hay en las fuentes sin limpiar."""
    names = real_street_names()
    raw_roads = pack_map.glb_json(require(EXPORT / "almensilla_roads.glb"))
    raw_terrain = pack_map.glb_json(require(EXPORT / "almensilla_terrain.glb"))
    assert "almensilla" in pack_map.forbidden_in(raw_roads, names)
    assert "código INE" in pack_map.forbidden_in(raw_terrain, names)
    assert "referencia catastral" in pack_map.forbidden_in('{"id":"5932833QB5353S"}', names)
    real = sorted(n for n in names if len(n) >= 6)[0]
    assert real in pack_map.forbidden_in(f"vive en la {real.upper()}", names)
    assert pack_map.forbidden_in("Calle Lorvia", names) == []


def test_sin_origen_absoluto(pack):
    """El origen EPSG geolocaliza el municipio real: no se publica."""
    manifest = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))
    assert "origin" not in manifest["crs"]
    for f in pack.rglob("*.json"):
        text = f.read_text(encoding="utf-8")
        assert "755870" not in text and "4132708" not in text, f
        assert "epsg" not in text.lower(), f


def test_glb_sin_extras(pack):
    for name in ("terrain.glb", "roads.glb"):
        gltf = json.loads(pack_map.glb_json(pack / "render" / name))
        assert "extras" not in gltf
        for coll in ("scenes", "nodes", "meshes", "materials"):
            assert all("extras" not in item for item in gltf.get(coll, [])), (name, coll)


def test_edificios(logic):
    buildings, streets = logic
    ids = [b["id"] for b in buildings]
    assert len(set(ids)) == len(ids) == 2793
    assert all(re.fullmatch(r"r1-b\d{4}", i) for i in ids)
    uses = {"residential", "agriculture", "industrial", "office", "retail", "publicServices", "unknown"}
    n_nodes = len(streets["nodes"])
    for b in buildings:
        assert b["use"] in uses
        assert b["floorsAboveGround"] >= 1 and b["heightM"] > 0
        assert np.isfinite(b["baseY"])
        assert b["footprint"] and all(len(p) >= 6 and len(p) % 2 == 0 for p in b["footprint"])
        (e,) = b["entrances"]
        assert 0 <= e["streetNodeId"] < n_nodes
    homes = [b for b in buildings if b["use"] == "residential" and b["dwellings"] > 0]
    assert len(homes) > 2000


def test_portal_en_la_fachada(logic):
    """El portal está en el contorno de la huella (a menos de 1 m de algún vértice o lado)."""
    buildings, _ = logic
    from shapely.geometry import Point, Polygon

    far = 0
    for b in buildings:
        e = b["entrances"][0]
        polys = [Polygon(np.array(p).reshape(-1, 2)) for p in b["footprint"]]
        if min(poly.exterior.distance(Point(e["x"], e["z"])) for poly in polys) > 1.0:
            far += 1
    assert far / len(buildings) < 0.01


def test_grafo_conexo_y_coherente(logic):
    _, streets = logic
    nodes, edges = streets["nodes"], streets["edges"]
    assert [n["id"] for n in nodes] == list(range(len(nodes)))
    adj = defaultdict(list)
    for e in edges:
        assert 0 <= e["from"] < len(nodes) and 0 <= e["to"] < len(nodes) and e["from"] != e["to"]
        assert e["lengthM"] > 0
        adj[e["from"]].append(e["to"])
        adj[e["to"]].append(e["from"])
    seen, stack = {0}, [0]
    while stack:
        for m in adj[stack.pop()]:
            if m not in seen:
                seen.add(m)
                stack.append(m)
    assert len(seen) == len(nodes), "el grafo publicado debe ser una sola componente"


def test_nombres_de_calle_ficticios_y_estables(logic):
    _, streets = logic
    names = {e["name"] for e in streets["edges"] if e["name"]}
    assert names, "las calles con nombre real reciben uno inventado"
    assert all(re.fullmatch(r"(Calle|Avenida|Paseo|Callejón) [A-Z][a-zñ]+", n) for n in names)
    assert pack_map.fictional_street("X", "s") == pack_map.fictional_street("X", "s")
    assert pack_map.fictional_street("X", "s") != pack_map.fictional_street("Y", "s")


def test_rejilla_de_cotas(pack):
    h = json.loads((pack / "render/heights.json").read_text(encoding="utf-8"))
    raw = base64.b64decode(h["heights"])
    assert len(raw) == h["cols"] * h["rows"] * 4
    a = np.frombuffer(raw, dtype="<f4")
    assert np.isfinite(a).all() and -40 < a.min() and a.max() < 60
