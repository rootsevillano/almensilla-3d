#!/usr/bin/env python3
"""Ortofoto PNOA -> texturas del terreno para el visor, en dos resoluciones por tesela.

Entrada: `data/raw/ign/pnoa/pnoa_<i>_<j>.jpg` (1000×1000 px, 0.5 m/px, tesela local i,j de 500 m; ver
`download_ign.py`). Las teselas y sus índices coinciden con los nodos `TERRAIN_<i>_<j>` del GLB de terreno.

Salida: `data/export/ortho/`
  * `hi/pnoa_<i>_<j>.jpg`  1024×1024 (~0.49 m/px): solo se carga en el visor para las teselas cercanas.
  * `lo/pnoa_<i>_<j>.jpg`  256×256 (~1.95 m/px): se carga para todas al arrancar.
  * `index.json`           teselas, tamaño de tesela, resoluciones y atribución (CC BY 4.0 scne.es).
Orientación: fila 0 de la imagen = norte (borde j+1), columna 0 = oeste (borde i).

Uso:
    python -P tools/gis/build_ortho_textures.py
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "data/raw/ign/pnoa"
DEFAULT_OUTPUT = ROOT / "data/export/ortho"
TILE_M = 500.0
HI_PX, LO_PX = 1024, 256
HI_QUALITY, LO_QUALITY = 85, 82
ATTRIBUTION = "Ortofoto PNOA máxima actualidad © Instituto Geográfico Nacional (CC BY 4.0 scne.es)"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = ap.parse_args(argv)

    files = sorted(args.input.glob("pnoa_*.jpg"))
    if not files:
        sys.exit(f"[ERROR] no hay teselas en {args.input}: ejecuta antes download_ign.py --only ortho")
    tiles, sizes = [], {"hi": 0, "lo": 0}
    for f in files:
        m = re.fullmatch(r"pnoa_(-?\d+)_(-?\d+)\.jpg", f.name)
        if not m:
            continue
        with Image.open(f) as im:
            if im.size != (1000, 1000):
                sys.exit(f"[ERROR] {f.name}: tamaño {im.size}, se esperaba 1000×1000")
            rgb = im.convert("RGB")
            for kind, px, q in (("hi", HI_PX, HI_QUALITY), ("lo", LO_PX, LO_QUALITY)):
                out = args.output / kind / f.name
                out.parent.mkdir(parents=True, exist_ok=True)
                rgb.resize((px, px), Image.LANCZOS).save(out, "JPEG", quality=q, optimize=True, progressive=False)
                sizes[kind] += out.stat().st_size
        tiles.append([int(m.group(1)), int(m.group(2))])

    index = {
        "tile_m": TILE_M, "hi_px": HI_PX, "lo_px": LO_PX, "tiles": tiles,
        "naming": "{hi|lo}/pnoa_<i>_<j>.jpg; tesela local x∈[i·500,(i+1)·500], y(norte)∈[j·500,(j+1)·500]",
        "orientation": "fila 0 = norte, columna 0 = oeste",
        "attribution": ATTRIBUTION,
    }
    (args.output / "index.json").write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"tiles": len(tiles), "hi_mb": round(sizes["hi"] / 2**20, 1),
                      "lo_mb": round(sizes["lo"] / 2**20, 2), "output": str(args.output.relative_to(ROOT))},
                     indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
