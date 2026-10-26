// Copia los GLB del agente 01 (data/export) a app/public/models, el único directorio que lee el visor.
// Cada modelo se valida antes con tests/contracts/validate_glb.py (regla 4 de CLAUDE.md); si uno falla, no se copia nada.
import { copyFileSync, existsSync, mkdirSync, statSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const SRC = join(ROOT, 'data/export');
const DST = join(ROOT, 'app/public/models');
const CONTRACT = join(ROOT, 'tests/contracts/validate_glb.py');
const MODELS = ['almensilla_terrain.glb', 'almensilla_roads.glb', 'almensilla_buildings.glb'];

const missing = MODELS.filter((m) => !existsSync(join(SRC, m)));
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

mkdirSync(DST, { recursive: true });
for (const model of MODELS) {
  copyFileSync(join(SRC, model), join(DST, model));
  console.log(`[sync-models] ${model} (${(statSync(join(DST, model)).size / 2 ** 20).toFixed(2)} MB) validado y copiado`);
}
