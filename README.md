# Almensilla 3D

Visor WebGL (Vite + Three.js) del término municipal de Almensilla (Sevilla), navegable a pie con un personaje en
tercera persona. Los modelos se generan con un pipeline GIS en Python a partir de datos abiertos: Catastro, OpenStreetMap
e Instituto Geográfico Nacional (ortofoto PNOA, MDT05 y LiDAR).

## Requisitos

- Python 3.10+ con las dependencias de `tools/gis/requirements.txt`.
- Node.js 20.19+ (o 22.12+) para el visor.

```bash
python -m pip install -r tools/gis/requirements.txt
```

```bash
npm --prefix app ci
```

## Ejecutar el visor

```bash
npm --prefix app run dev
```

Abre http://localhost:5173. Controles: WASD o flechas para andar, Mayús para correr, Espacio para saltar, arrastrar
para girar la cámara, rueda para el zoom y C para alternar con la vista aérea.

Parámetros de URL: `?bench=20` (benchmark de 20 s), `?shadows=0`, `?lod=0`, `?ortho=0`, `?merge=0`.

## Regenerar los datos

Un único script ejecuta todo el pipeline en orden (Catastro → alturas LiDAR → relieve → edificios → viales → terreno →
árboles → ortofoto):

```bash
python -P tools/gis/run_pipeline.py --sync --test
```

- `--download` incluye la descarga de datos del IGN (`tools/gis/download_ign.py`, idempotente).
- `--from <paso>` empieza en un paso; `--only <pasos…>` ejecuta solo esos.
- `--sync` valida los contratos y copia los modelos al visor (`npm run sync-models`).
- `--test` ejecuta las pruebas al final.

El pipeline es reproducible: dos ejecuciones con los mismos datos de entrada producen ficheros idénticos.

## Pruebas

```bash
python -P -m pytest tests
```

Comprueban los contratos de los GLB, la geometría (sin NaN, edificios cerrados, normales, nombres de nodo), las
costuras con el relieve (viales, piscinas y árboles sobre el terreno; edificios sin flotar), los criterios de QA
automatizables (anchura de calles) y que el visor tenga los modelos actualizados. El rendimiento (≥60 FPS a 1080p) se
mide en el visor con `?bench=20`.

## Atribución

- Ortofoto PNOA, MDT05 y MDS LiDAR © Instituto Geográfico Nacional ([CC BY 4.0](https://creativecommons.org/licenses/by/4.0/deed.es) scne.es).
- Edificios y parcelas © Dirección General del Catastro.
- Viales y vegetación © colaboradores de OpenStreetMap ([ODbL](https://www.openstreetmap.org/copyright)).
