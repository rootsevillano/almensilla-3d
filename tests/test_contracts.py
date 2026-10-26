"""Contratos de las salidas del agente 01 y de lo que lee el visor (agente 02)."""
from __future__ import annotations

import hashlib
import importlib.util
import json

import pytest
from PIL import Image

from conftest import APP_MODELS, EXPORT, GLBS, ROOT, require


def _validate_glb():
    spec = importlib.util.spec_from_file_location("validate_glb", ROOT / "tests/contracts/validate_glb.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.validate_glb


@pytest.mark.parametrize("name", GLBS)
def test_glb_contract(name):
    """Contrato de tests/contracts/validate_glb.py (existencia y presupuesto)."""
    path = require(EXPORT / name)
    assert _validate_glb()(str(path))
    assert path.stat().st_size < 50 * 2**20, "supera el presupuesto de 50 MB del contrato"


def test_glb_binary_header():
    for name in GLBS:
        raw = require(EXPORT / name).read_bytes()
        assert raw[:4] == b"glTF", f"{name}: no es un GLB"
        assert int.from_bytes(raw[4:8], "little") == 2, f"{name}: no es glTF 2.0"
        assert int.from_bytes(raw[8:12], "little") == len(raw), f"{name}: longitud de cabecera incoherente"


def test_trees_json_structure(trees):
    assert trees["axes"] == "X=East, Y=Up, Z=-North"
    assert trees["types"] and trees["trees"]
    n = len(trees["fields"])
    assert trees["fields"][:4] == ["x", "z", "type", "scale"]
    for t in trees["trees"]:
        assert len(t) == n
        assert all(isinstance(v, (int, float)) for v in t)
        assert 0 <= t[2] < len(trees["types"])
        assert t[3] > 0


def test_ortho_index_and_textures():
    index_path = require(EXPORT / "ortho/index.json")
    idx = json.loads(index_path.read_text(encoding="utf-8"))
    assert idx["tiles"], "índice de ortofoto vacío"
    assert "CC BY 4.0" in idx["attribution"], "falta la atribución obligatoria del IGN"
    for i, j in idx["tiles"]:
        for kind, px in (("hi", idx["hi_px"]), ("lo", idx["lo_px"])):
            path = EXPORT / "ortho" / kind / f"pnoa_{i}_{j}.jpg"
            assert path.exists(), f"falta {path.relative_to(ROOT)}"
            with Image.open(path) as im:
                assert im.size == (px, px), f"{path.name} ({kind}): {im.size}"


def test_ortho_covers_every_terrain_tile(scenes):
    idx = json.loads(require(EXPORT / "ortho/index.json").read_text(encoding="utf-8"))
    tiles = {f"{i}_{j}" for i, j in idx["tiles"]}
    terrain = {n[len("TERRAIN_"):] for n in scenes["almensilla_terrain.glb"].geometry if n.startswith("TERRAIN_")}
    assert terrain <= tiles, f"teselas de terreno sin ortofoto: {sorted(terrain - tiles)[:5]}"


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("name", GLBS + ["almensilla_trees.json", "ortho/index.json"])
def test_app_models_in_sync(name):
    """El visor solo lee app/public/models: debe coincidir con data/export (npm run sync-models)."""
    src, dst = require(EXPORT / name), APP_MODELS / name
    assert dst.exists(), f"{name} no está en app/public/models: ejecuta npm --prefix app run sync-models"
    assert _sha(src) == _sha(dst), f"{name} desactualizado en el visor: ejecuta npm --prefix app run sync-models"
