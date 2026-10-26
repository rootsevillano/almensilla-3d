#!/usr/bin/env python3
"""Descarga de datos abiertos del IGN para el término de Almensilla (fase 2).

Servicios y coberturas verificados en sus GetCapabilities/DescribeCoverage (ver `.claude/MEMORY.md`, Fase 2).
Licencia de todos: CC BY 4.0 scne.es (atribución: © Instituto Geográfico Nacional).

  * Ortofoto PNOA máxima actualidad (WMS 1.3.0, capa OI.OrthoimageCoverage, EPSG:25829): una imagen JPEG de
    1000×1000 px (0.5 m/px) por cada tesela de 500 m que toca el término -> `pnoa/pnoa_<i>_<j>.jpg`
    (mismas teselas e índices que el terreno y los viales, en coordenadas locales).
  * MDT05 (WCS 2.0.1, `Elevacion25830_5`, EPSG:25830, ejes x y) -> `mdt05_25830.tif`
  * MDS normalizado de edificación y de vegetación (WCS 2.0.1, `mdsn_e025` / `mdsn_v025`, EPSG:3042 con ejes
    **y x**, 2.5 m) -> `mdsn_e025_3042.tif`, `mdsn_v025_3042.tif`

Los ficheros ya descargados no se vuelven a pedir. Cada respuesta se comprueba (imagen/TIFF, no un
ExceptionReport XML) y se registra en `manifest.json`.

Uso:
    python -P tools/gis/download_ign.py              # todo
    python -P tools/gis/download_ign.py --only dem   # solo MDT y MDSn
    python -P tools/gis/download_ign.py --only ortho
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from pyproj import Transformer
from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_roads_glb as roads_glb  # noqa: E402

ROOT = roads_glb.ROOT
DEFAULT_OUT = ROOT / "data/raw/ign"
LICENSE = "CC BY 4.0 scne.es (© Instituto Geográfico Nacional)"
USER_AGENT = "almensilla-3d/0.1 (visor 3D; descarga de datos abiertos IGN)"

WMS_PNOA = "https://www.ign.es/wms-inspire/pnoa-ma"
WCS_MDT = "https://servicios.idee.es/wcs-inspire/mdt"
WCS_MDS = "https://wcs-mds.idee.es/mds"

TILE_M = roads_glb.TILE_M
ORTHO_PX = 1000  # 0.5 m/px en teselas de 500 m
PAD_M = 100.0  # margen alrededor del término para los modelos de elevación
PAUSE_S = 0.25  # cortesía con el servidor entre peticiones


def fetch(url: str | list[str], dest: Path, expect: tuple[str, ...], manifest: dict, retries: int = 3) -> None:
    """`url` puede ser una lista de URLs equivalentes: cada reintento usa la siguiente (ver `wms_url`)."""
    if dest.exists() and dest.stat().st_size > 0:
        return
    urls = url if isinstance(url, list) else [url]
    last = None
    for attempt in range(1, retries + 1):
        url = urls[(attempt - 1) % len(urls)]
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=180) as resp:
                ctype = resp.headers.get("Content-Type", "")
                body = resp.read()
            if not any(ctype.startswith(e) for e in expect) or body[:5] in (b"<?xml", b"<Serv", b"<ows:"):
                raise RuntimeError(f"respuesta inesperada ({ctype}): {body[:300]!r}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(body)
            manifest[str(dest.relative_to(manifest["_root"]))] = {
                "url": url, "content_type": ctype, "bytes": len(body),
                "downloaded_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            time.sleep(PAUSE_S)
            return
        except Exception as exc:  # noqa: BLE001 — se reintenta y se informa al final
            last = exc
            time.sleep(2 * attempt)
    raise RuntimeError(f"{dest.name}: {last}")


def wms_url(bbox: tuple[float, float, float, float], decimals: int = 2) -> str:
    params = {
        "SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap", "LAYERS": "OI.OrthoimageCoverage",
        "STYLES": "", "CRS": "EPSG:25829",  # EPSG:25829 en WMS 1.3.0: orden E,N
        "BBOX": ",".join(f"{v:.{decimals}f}" for v in bbox),
        "WIDTH": ORTHO_PX, "HEIGHT": ORTHO_PX, "FORMAT": "image/jpeg",
    }
    return f"{WMS_PNOA}?{urllib.parse.urlencode(params)}"


def wms_urls(bbox) -> list[str]:
    """La misma petición escrita de tres formas: un proxy de caché del IGN guarda los 502 por URL exacta y los
    sigue sirviendo; cambiar la precisión del BBOX (misma zona) evita esa entrada de caché."""
    return [wms_url(bbox, d) for d in (2, 1, 0)]


def wcs_url(base: str, coverage: str, subsets: list[tuple[str, float, float]]) -> str:
    query = [("SERVICE", "WCS"), ("VERSION", "2.0.1"), ("REQUEST", "GetCoverage"),
             ("COVERAGEID", coverage), ("FORMAT", "image/tiff")]
    query += [("SUBSET", f"{axis}({lo:.1f},{hi:.1f})") for axis, lo, hi in subsets]
    return f"{base}?{urllib.parse.urlencode(query)}"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--only", choices=["dem", "ortho"], help="Descargar solo elevaciones o solo ortofoto")
    args = ap.parse_args(argv)

    origin = roads_glb.load_origin(roads_glb.DEFAULT_META)
    municipality, _, _ = roads_glb.load_cadastre(roads_glb.DEFAULT_CP_ZIP, origin)
    manifest_path = args.out / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    manifest["_root"] = str(args.out)
    manifest["_license"] = LICENSE
    errors = []

    if args.only in (None, "dem"):
        minx, miny, maxx, maxy = municipality.bounds
        e0, n0 = origin
        to30 = Transformer.from_crs(25829, 25830, always_xy=True)
        xs, ys = to30.transform([minx - PAD_M + e0, maxx + PAD_M + e0] * 2,
                                [miny - PAD_M + n0] * 2 + [maxy + PAD_M + n0] * 2)
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        manifest["_dem_bbox_25830"] = [round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)]
        jobs = [
            (wcs_url(WCS_MDT, "Elevacion25830_5", [("x", x0, x1), ("y", y0, y1)]), "mdt05_25830.tif"),
            # EPSG:3042 = UTM 30 con orden de ejes N,E: mismos números que 25830, ejes y x
            (wcs_url(WCS_MDS, "mdsn_e025", [("y", y0, y1), ("x", x0, x1)]), "mdsn_e025_3042.tif"),
            (wcs_url(WCS_MDS, "mdsn_v025", [("y", y0, y1), ("x", x0, x1)]), "mdsn_v025_3042.tif"),
        ]
        for url, name in jobs:
            try:
                fetch(url, args.out / name, ("image/tiff", "image/geotiff", "application/octet-stream"), manifest)
                print(f"[ok] {name}")
            except RuntimeError as exc:
                errors.append(str(exc))
                print(f"[error] {exc}", file=sys.stderr)

    if args.only in (None, "ortho"):
        e0, n0 = origin
        minx, miny, maxx, maxy = municipality.bounds
        tiles = [(i, j)
                 for i in range(int(np.floor(minx / TILE_M)), int(np.floor(maxx / TILE_M)) + 1)
                 for j in range(int(np.floor(miny / TILE_M)), int(np.floor(maxy / TILE_M)) + 1)
                 if box(i * TILE_M, j * TILE_M, (i + 1) * TILE_M, (j + 1) * TILE_M).intersects(municipality)]
        for k, (i, j) in enumerate(tiles, 1):
            bbox = (i * TILE_M + e0, j * TILE_M + n0, (i + 1) * TILE_M + e0, (j + 1) * TILE_M + n0)
            try:
                fetch(wms_urls(bbox), args.out / "pnoa" / f"pnoa_{i}_{j}.jpg", ("image/jpeg",), manifest)
            except RuntimeError as exc:
                errors.append(str(exc))
                print(f"[error] {exc}", file=sys.stderr)
            if k % 10 == 0 or k == len(tiles):
                print(f"[ortho] {k}/{len(tiles)}")
        manifest["_ortho"] = {"tiles": len(tiles), "tile_m": TILE_M, "px": ORTHO_PX, "crs": "EPSG:25829",
                              "origin_epsg25829": list(origin), "naming": "pnoa_<i>_<j>.jpg, tesela local i,j"}

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    if errors:
        sys.exit(f"[ERROR] {len(errors)} descargas fallidas (ver arriba); se pueden reintentar sin repetir las demás")


if __name__ == "__main__":
    main()
