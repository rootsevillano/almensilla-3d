#!/usr/bin/env python3
"""Regenera todo el pipeline GIS de Almensilla en el orden correcto (agente 01).

Pasos (cada uno es un script de tools/gis/, ejecutado con `python -P`; ver `.claude/MEMORY.md`):
  download     download_ign.py            datos IGN (ortofoto, MDT05, MDSn): solo con --download; es idempotente
  extract      extract_catastro_buildings  Catastro BU -> data/processed (huellas, partes, piscinas)
  lidar        apply_lidar_heights        alturas de las partes con el MDSn de edificación
  dem          dem.py                     MDT05 -> malla local suavizada (cota cero en el origen)
  buildings    build_buildings_glb        data/export/almensilla_buildings.glb
  roads        build_roads_glb            data/export/almensilla_roads.glb + data/processed/osm_roads.geojson
  terrain      build_terrain_glb          data/export/almensilla_terrain.glb (necesita osm_roads)
  trees        build_trees                data/export/almensilla_trees.json (necesita osm_roads)
  ortho        build_ortho_textures       data/export/ortho/
Después, opcionalmente: `--sync` (npm run sync-models: contratos + copia a app/public/models) y `--test` (pytest).

Uso:
    python -P tools/gis/run_pipeline.py                    # todo salvo descargas
    python -P tools/gis/run_pipeline.py --download --sync --test
    python -P tools/gis/run_pipeline.py --from roads       # desde un paso hasta el final
    python -P tools/gis/run_pipeline.py --only trees ortho
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GIS = ROOT / "tools/gis"
STEPS = [
    ("download", "download_ign.py"),
    ("extract", "extract_catastro_buildings.py"),
    ("lidar", "apply_lidar_heights.py"),
    ("dem", "dem.py"),
    ("buildings", "build_buildings_glb.py"),
    ("roads", "build_roads_glb.py"),
    ("terrain", "build_terrain_glb.py"),
    ("trees", "build_trees.py"),
    ("ortho", "build_ortho_textures.py"),
]
NAMES = [name for name, _ in STEPS]


def run(cmd: list[str], label: str) -> float:
    print(f"\n=== {label}: {' '.join(cmd)}", flush=True)
    t0 = time.perf_counter()
    result = subprocess.run(cmd, cwd=ROOT)
    elapsed = time.perf_counter() - t0
    if result.returncode != 0:
        sys.exit(f"[ERROR] '{label}' terminó con código {result.returncode} tras {elapsed:.1f} s: pipeline detenido")
    print(f"=== {label}: OK en {elapsed:.1f} s", flush=True)
    return elapsed


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--download", action="store_true", help="Incluir la descarga de datos del IGN")
    ap.add_argument("--from", dest="start", choices=NAMES, help="Empezar en este paso")
    ap.add_argument("--only", nargs="+", choices=NAMES, help="Ejecutar solo estos pasos (en el orden del pipeline)")
    ap.add_argument("--sync", action="store_true", help="Validar contratos y copiar al visor (npm run sync-models)")
    ap.add_argument("--test", action="store_true", help="Ejecutar las pruebas (pytest tests/) al final")
    args = ap.parse_args(argv)

    if args.only:
        selected = [n for n in NAMES if n in args.only]
    else:
        selected = NAMES[NAMES.index(args.start):] if args.start else NAMES
        if not args.download:
            selected = [n for n in selected if n != "download"]

    timings = {}
    for name, script in STEPS:
        if name in selected:
            timings[name] = run([sys.executable, "-P", str(GIS / script)], name)
    if args.sync:
        npm = shutil.which("npm") or sys.exit("[ERROR] npm no está en el PATH (necesario para --sync)")
        timings["sync"] = run([npm, "--prefix", "app", "run", "sync-models"], "sync")
    if args.test:
        timings["test"] = run([sys.executable, "-P", "-m", "pytest", "-q", "tests"], "test")

    print("\nResumen: " + ", ".join(f"{k} {v:.1f} s" for k, v in timings.items())
          + f" · total {sum(timings.values()):.1f} s")


if __name__ == "__main__":
    main()
