#!/usr/bin/env python3
"""Empaqueta un map-pack anonimizado para WorldOpen (agente 01; contrato en WorldOpen/.harness/CONTRACTS/map-pack.md).

Línea roja de WorldOpen (ADR-0007): nada real identificable. Este paso:
  * da ids opacos con prefijo de región a los edificios (la tabla refcat → id queda en data/processed, privada);
  * sustituye cada nombre de calle real por uno inventado (mismo nombre real → mismo nombre inventado);
  * no publica el origen absoluto (geolocaliza el municipio) ni metadatos de las fuentes con nombres o códigos;
  * limpia los metadatos (`extras`) de los GLB que se reutilizan;
  * FALLA si en cualquier fichero del paquete aparece un nombre real, una referencia catastral o el código INE.

Salida: data/export/mappack/<id>-<version>/ (manifest.json, logic/, render/).

Uso:  python -P tools/gis/pack_map.py [--id valdeolivo] [--version 1.0.0] [--name Valdeolivo] [--region r1]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import struct
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOGIC = ROOT / "data/export/logic"
EXPORT = ROOT / "data/export"
PROCESSED = ROOT / "data/processed"
SCHEMA_VERSION = 1

# Nombres reales que nunca pueden aparecer (municipio, vecinos, provincia, fuentes).
REAL_PLACES = [
    "almensilla", "mairena", "palomares", "coria", "puebla del rio", "sevilla", "bollullos", "aljarafe",
    "gelves", "santa iglesia", "vista del aljarafe", "la senora", "ugena",
]
REFCAT = re.compile(r"\d{7}[A-Z]{2}\d{4}[A-Z]|\d{5}[A-Z]\d{8}")
INE = re.compile(r"41010|41\.010")

ONSETS = ["l", "v", "m", "r", "t", "n", "s", "d", "b", "c", "f", "g", "br", "tr", "cl", "nd", "rv", "ls"]
VOWELS = ["a", "e", "i", "o", "u", "ia", "ea", "io"]
KINDS = ["Calle", "Calle", "Calle", "Avenida", "Paseo", "Callejón"]


def fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


def fictional_street(real: str, salt: str) -> str:
    """Nombre inventado y estable para un nombre real (sílabas sin significado; ver WorldOpen content/names.ts)."""
    h = hashlib.sha256((salt + "|" + real).encode()).digest()
    k = 0

    def pick(lst):
        nonlocal k
        v = lst[h[k % len(h)] % len(lst)]
        k += 1
        return v

    stem = "".join(pick(ONSETS) + pick(VOWELS) for _ in range(2 + h[31] % 2))
    return f"{pick(KINDS)} {stem.capitalize()}"


def sanitize_glb(src: Path, dst: Path) -> None:
    """Copia un GLB quitando `extras` de escena, nodos y mallas (metadatos de fuentes con nombres y códigos)."""
    data = src.read_bytes()
    magic, version, _ = struct.unpack("<4sII", data[:12])
    assert magic == b"glTF" and version == 2, f"{src} no es GLB 2.0"
    jlen, jtype = struct.unpack("<II", data[12:20])
    assert jtype == 0x4E4F534A
    gltf = json.loads(data[20:20 + jlen])
    rest = data[20 + jlen:]
    gltf.pop("extras", None)
    gltf.get("asset", {}).pop("extras", None)
    gltf.get("asset", {}).pop("copyright", None)
    for coll in ("scenes", "nodes", "meshes", "materials"):
        for item in gltf.get(coll, []):
            item.pop("extras", None)
    text = json.dumps(gltf, separators=(",", ":")).encode()
    text += b" " * (-len(text) % 4)
    body = struct.pack("<II", len(text), 0x4E4F534A) + text + rest
    dst.write_bytes(struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body)


def glb_json(path: Path) -> str:
    data = path.read_bytes()
    jlen = struct.unpack("<I", data[12:16])[0]
    return data[20:20 + jlen].decode("utf-8")


def forbidden_in(text: str, real_names: set[str]) -> list[str]:
    hits = []
    folded = fold(text)
    for place in REAL_PLACES:
        if place in folded:
            hits.append(place)
    for name in real_names:
        if len(name) >= 6 and fold(name) in folded:
            hits.append(name)
    if REFCAT.search(text):
        hits.append("referencia catastral")
    if INE.search(text):
        hits.append("código INE")
    return hits


def audit(pack: Path, real_names: set[str]) -> dict[str, list[str]]:
    """Revisa todos los ficheros de texto y el JSON de los GLB del paquete."""
    problems = {}
    for f in sorted(pack.rglob("*")):
        if f.is_dir():
            continue
        text = glb_json(f) if f.suffix == ".glb" else f.read_text(encoding="utf-8")
        hits = forbidden_in(text, real_names)
        if hits:
            problems[str(f.relative_to(pack))] = hits
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--id", default="valdeolivo")
    ap.add_argument("--version", default="1.0.0")
    ap.add_argument("--name", default="Valdeolivo")
    ap.add_argument("--region", default="r1")
    args = ap.parse_args(argv)

    if not (LOGIC / "buildings.json").exists():
        sys.exit("[ERROR] Falta data/export/logic: ejecuta antes tools/gis/build_logic.py")
    if any(p in fold(args.name) for p in REAL_PLACES):
        sys.exit("[ERROR] El nombre visible debe ser ficticio")

    buildings = json.loads((LOGIC / "buildings.json").read_text(encoding="utf-8"))
    streets = json.loads((LOGIC / "streets.json").read_text(encoding="utf-8"))
    bounds = json.loads((LOGIC / "bounds.json").read_text(encoding="utf-8"))
    real_names = {n for n in streets.pop("wayNames") if n}
    way_names = json.loads((LOGIC / "streets.json").read_text(encoding="utf-8"))["wayNames"]

    pack = EXPORT / "mappack" / f"{args.id}-{args.version}"
    if pack.exists():
        shutil.rmtree(pack)
    (pack / "logic").mkdir(parents=True)
    (pack / "render").mkdir()

    width = len(str(len(buildings)))
    for i, b in enumerate(buildings):
        b["id"] = f"{args.region}-b{str(i).zfill(max(4, width))}"
    salt = f"{args.id}-{args.region}"
    for e in streets["edges"]:
        real = way_names[e.pop("way")]
        e["name"] = fictional_street(real, salt) if real else None

    (pack / "logic" / "buildings.json").write_text(json.dumps(buildings, separators=(",", ":")), encoding="utf-8")
    (pack / "logic" / "streets.json").write_text(json.dumps(streets, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    shutil.copy(LOGIC / "heights.json", pack / "render" / "heights.json")
    sanitize_glb(EXPORT / "almensilla_terrain.glb", pack / "render" / "terrain.glb")
    sanitize_glb(EXPORT / "almensilla_roads.glb", pack / "render" / "roads.glb")
    trees = json.loads((EXPORT / "almensilla_trees.json").read_text(encoding="utf-8"))
    (pack / "render" / "trees.json").write_text(
        json.dumps({"axes": trees["axes"], "units": trees["units"], "types": trees["types"], "fields": trees["fields"], "trees": trees["trees"]},
                   separators=(",", ":")), encoding="utf-8")

    manifest = {
        "schemaVersion": SCHEMA_VERSION,
        "id": args.id,
        "version": args.version,
        "displayName": args.name,
        "crs": {"frame": "local", "axes": "X=East,Y=Up,Z=-North", "units": "m"},
        "bounds": bounds,
        "logic": {"buildings": "logic/buildings.json", "streets": "logic/streets.json"},
        "render": {"terrain": "render/terrain.glb", "roads": "render/roads.glb", "trees": "render/trees.json", "heights": "render/heights.json"},
        "attribution": [
            "Relieve: MDT05 © Instituto Geográfico Nacional (CC BY 4.0 scne.es)",
            "Edificios y parcelas: © Dirección General del Catastro",
            "Viales y vegetación: © colaboradores de OpenStreetMap (ODbL)",
        ],
    }
    (pack / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    problems = audit(pack, real_names)
    if problems:
        shutil.rmtree(pack)
        sys.exit(f"[ERROR] El map-pack contiene datos reales identificables y se ha borrado: {json.dumps(problems, ensure_ascii=False)}")
    size = sum(f.stat().st_size for f in pack.rglob("*") if f.is_file())
    print(f"Map-pack {pack.relative_to(ROOT)}: {len(buildings)} edificios, {len(streets['nodes'])} nodos, "
          f"{len(streets['edges'])} tramos, {size / 1e6:.1f} MB · auditoría de anonimización: OK "
          f"({len(real_names)} nombres reales de calle comprobados)")


if __name__ == "__main__":
    main()
