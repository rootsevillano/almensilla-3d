// Copia los GLB del agente 01 (data/export) a app/public/models, el único directorio que lee el visor.
// Cada modelo se valida antes con tests/contracts/validate_glb.py (regla 4 de CLAUDE.md); si uno falla, no se copia nada.
import { copyFileSync, existsSync, mkdirSync, readFileSync, statSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const SRC = join(ROOT, 'data/export');
const DST = join(ROOT, 'app/public/models');
const CONTRACT = join(ROOT, 'tests/contracts/validate_glb.py');
const MODELS = ['almensilla_terrain.glb', 'almensilla_roads.glb', 'almensilla_buildings.glb'];
// Instancias de árboles (tools/gis/build_trees.py): no es GLB, se comprueba su estructura aquí
const DATA = ['almensilla_trees.json'];

const missing = [...MODELS, ...DATA].filter((m) => !existsSync(join(SRC, m)));
if (missing.length) {
  console.error(`[sync-models] faltan en data/export: ${missing.join(', ')} (ejecuta los scripts de tools/gis)`);
  process.exit(1);
}

for (const model of MODELS) {
  // -P: el stack GIS está en el site-packages de usuario (ver .claude/MEMORY.md)
  const run = spawnSync('python', ['-P', CONTRACT, join(SRC, model)], { encoding: 'utf-8' });
  if (run.status !== 0) {
    console.error(`[sync-models] contrato FALLIDO para ${model}:\n${run.stdout}${run.stderr}`);
    process.exit(1);
  }
}

for (const file of DATA) {
  const data = JSON.parse(readFileSync(join(SRC, file), 'utf-8'));
  const ok = Array.isArray(data.types) && Array.isArray(data.trees)
    && data.trees.every((t) => t.length >= 4 && t.length <= 6 && t.every(Number.isFinite)
      && data.types[t[2]] !== undefined);
  if (!ok) {
    console.error(`[sync-models] ${file}: estructura inválida (se espera {types, trees: [[x, z, tipo, escala, y?, ancho?]]})`);
    process.exit(1);
  }
}

// Texturas de ortofoto (tools/gis/build_ortho_textures.py): índice + hi/lo por tesela
const ORTHO = 'ortho';
const orthoIndex = join(SRC, ORTHO, 'index.json');
let orthoFiles = [];
if (existsSync(orthoIndex)) {
  const idx = JSON.parse(readFileSync(orthoIndex, 'utf-8'));
  orthoFiles = idx.tiles.flatMap(([i, j]) => ['hi', 'lo'].map((k) => join(ORTHO, k, `pnoa_${i}_${j}.jpg`)));
  const absent = orthoFiles.filter((f) => !existsSync(join(SRC, f)));
  if (!Array.isArray(idx.tiles) || !idx.tiles.length || absent.length) {
    console.error(`[sync-models] ortho/index.json incoherente: faltan ${absent.length} texturas (p. ej. ${absent[0]})`);
    process.exit(1);
  }
  orthoFiles.push(join(ORTHO, 'index.json'));
} else {
  console.warn('[sync-models] sin ortofoto (data/export/ortho/index.json no existe): el terreno irá sin textura');
}

mkdirSync(DST, { recursive: true });
for (const model of [...MODELS, ...DATA]) {
  copyFileSync(join(SRC, model), join(DST, model));
  console.log(`[sync-models] ${model} (${(statSync(join(DST, model)).size / 2 ** 20).toFixed(2)} MB) validado y copiado`);
}
let orthoBytes = 0;
for (const f of orthoFiles) {
  mkdirSync(dirname(join(DST, f)), { recursive: true });
  copyFileSync(join(SRC, f), join(DST, f));
  orthoBytes += statSync(join(DST, f)).size;
}
if (orthoFiles.length) {
  console.log(`[sync-models] ortho: ${orthoFiles.length - 1} texturas (${(orthoBytes / 2 ** 20).toFixed(1)} MB) validadas y copiadas`);
}
