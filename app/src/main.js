import * as THREE from 'three';
import { createViewer } from './scene.js';
import { loadModels, mergeBuildings, urbanCenter } from './models.js';
import { Benchmark, FpsMeter, GpuTimer } from './stats.js';
import { SunShadows, enableShadows } from './shadows.js';
import { applyFacades } from './facades.js';
import { applyGroundMaterials } from './ground.js';
import { loadTrees } from './trees.js';
import { LodManager } from './lod.js';
import { Monigote } from './character/Monigote.js';
import { FootprintCollider } from './character/collision.js';
import { CharacterController } from './character/controller.js';

// Parámetros de URL: ?merge=0 desactiva la fusión de edificios; ?shadows=0 desactiva las sombras;
// ?lod=0 desactiva el nivel de detalle; ?bench=20 órbita automática de 20 s y resultado.
const params = new URLSearchParams(window.location.search);
const MERGE = params.get('merge') !== '0';
const SHADOWS = params.get('shadows') !== '0';
const LOD = params.get('lod') !== '0';
const BENCH_S = Number(params.get('bench')) || 0;
const BENCH_RADIUS_M = 900;
const BENCH_HEIGHT_M = 420;

const statusEl = document.getElementById('status');
const statsEl = document.getElementById('stats');
const { renderer, scene, camera, controls, sun } = createViewer(document.getElementById('viewport'));

const t0 = performance.now();
const models = await loadModels((n, total, key) => {
  statusEl.textContent = `Cargando modelos… ${n}/${total} (${key})`;
});
const loadMs = performance.now() - t0;

scene.add(models.terrain, models.roads);
let collisionMeshes;
let buildingsRoot;
let parapets;
if (MERGE) {
  ({ merged: buildingsRoot, collisionMeshes, parapets } = mergeBuildings(models.buildings));
} else {
  collisionMeshes = [];
  parapets = [];
  models.buildings.traverse((o) => o.isMesh && o.name.startsWith('COL_') && collisionMeshes.push(o));
  models.buildings.traverse((o) => o.isMesh && o.name.startsWith('PARAPET_') && parapets.push(o));
  buildingsRoot = models.buildings;
}
scene.add(buildingsRoot);
applyFacades(buildingsRoot);
applyGroundMaterials(models.terrain, models.roads);

const trees = await loadTrees('models/almensilla_trees.json', { castShadow: SHADOWS });
scene.add(trees.root);

const shadows = SHADOWS ? new SunShadows(renderer, sun, scene) : null;
if (shadows) enableShadows({ casters: [buildingsRoot], receivers: [models.terrain, models.roads, buildingsRoot] });
// Después de enableShadows: el LOD quita la sombra a los pretiles y la limita a los árboles cercanos
const lod = LOD ? new LodManager({ parapets, trees: trees.root.children, treeShadows: SHADOWS }) : null;

const center = urbanCenter(collisionMeshes);
controls.target.copy(center);
camera.position.copy(center).add(new THREE.Vector3(-600, 520, 900));
controls.update();

// Personaje (agente 03). En modo benchmark no se crea: la medida es de la escena con cámara orbital.
const helpEl = document.getElementById('help');
const HELP = {
  character: 'WASD/flechas: andar · Mayús: correr · Espacio: saltar · Arrastrar: cámara · Rueda: zoom · C: vista aérea',
  orbit: 'Arrastrar: orbitar · Rueda: zoom · Botón derecho: desplazar' + (BENCH_S ? '' : ' · C: personaje'),
};
let character = null;
let player = null;
let mode = 'orbit';
if (!BENCH_S) {
  const ground = [];
  for (const root of [models.terrain, models.roads]) root.traverse((o) => o.isMesh && ground.push(o));
  const t1 = performance.now();
  const collider = new FootprintCollider(collisionMeshes);
  console.log(`[character] ${collider.segments.length} muros indexados en ${(performance.now() - t1).toFixed(0)} ms`);
  character = new Monigote();
  if (shadows) {
    enableShadows({ casters: [character.body] });
    character.getObjectByName('CHARACTER_shadow').visible = false; // la sombra real sustituye a la difusa
  }
  scene.add(character);
  player = new CharacterController({
    character, camera, dom: renderer.domElement, ground, collider, walls: collisionMeshes,
  });
  player.spawnNear(center);
  setMode('character');
  window.addEventListener('keydown', (e) => e.code === 'KeyC' && setMode(mode === 'character' ? 'orbit' : 'character'));
}

function setMode(next) {
  mode = next;
  const walking = mode === 'character';
  player.enabled = walking;
  controls.enabled = !walking;
  camera.near = walking ? 0.2 : 1; // de cerca hace falta un plano cercano corto; en aéreo, más precisión de profundidad
  camera.updateProjectionMatrix();
  if (!walking) {
    controls.target.copy(character.position);
    camera.position.copy(character.position).add(new THREE.Vector3(-150, 140, 220));
    controls.update();
  }
  helpEl.textContent = HELP[mode];
}

// Acceso para depuración y pruebas
const gpu = new GpuTimer(renderer.getContext());
window.__almensilla = { scene, camera, renderer, collisionMeshes, center, character, player, shadows, gpu, lod };

const sceneInfo = () => {
  const { calls, triangles } = renderer.info.render;
  return { calls, triangles, geometries: renderer.info.memory.geometries };
};
statusEl.textContent = `Modelos cargados en ${(loadMs / 1000).toFixed(1)} s · ${collisionMeshes.length} edificios COL_ · ${trees.count.toLocaleString('es-ES')} árboles · fusión ${MERGE ? 'sí' : 'no'} · sombras ${SHADOWS ? 'sí' : 'no'} · LOD ${LOD ? 'sí' : 'no'}`;

const meter = new FpsMeter();
const bench = BENCH_S > 0 ? new Benchmark(BENCH_S) : null;
if (bench) controls.enabled = false;
let last = performance.now();
let benchMeasuring = false;

renderer.setAnimationLoop((now) => {
  const dt = now - last;
  last = now;

  if (bench?.running) {
    bench.tick(dt);
    if (!benchMeasuring && bench.progress >= 0) {
      benchMeasuring = true;
      gpu.reset(); // solo cuenta el tramo medido, no el calentamiento
    }
    const a = Math.max(0, bench.progress) * Math.PI * 2;
    camera.position.set(center.x + Math.cos(a) * BENCH_RADIUS_M, BENCH_HEIGHT_M, center.z + Math.sin(a) * BENCH_RADIUS_M);
    camera.lookAt(center);
    if (!bench.running) {
      const result = {
        ...bench.result, ...gpu.summary(), merge: MERGE, shadows: SHADOWS, lod: LOD, ...sceneInfo(),
        viewport: `${renderer.domElement.width}x${renderer.domElement.height}`,
        pixelRatio: renderer.getPixelRatio(), load_s: +(loadMs / 1000).toFixed(2),
      };
      window.__bench = result;
      console.log('[bench]', JSON.stringify(result));
      controls.enabled = true;
    }
  } else if (mode === 'character') {
    player.update(dt / 1000);
  } else {
    player?.update(dt / 1000); // el personaje sigue animándose (y cayendo) aunque la cámara sea aérea
    controls.update();
  }

  if (shadows) {
    const focus = mode === 'character' ? character.position : bench ? center : controls.target;
    shadows.update(focus, camera.position.distanceTo(focus));
  }

  lod?.update(camera);
  gpu.begin();
  renderer.render(scene, camera);
  gpu.end();

  if (meter.tick(dt)) {
    const info = sceneInfo();
    const gpuMs = gpu.samples.length ? gpu.samples[gpu.samples.length - 1].toFixed(2) : '—';
    if (!bench && gpu.samples.length > 600) gpu.reset();
    const benchLine = bench
      ? bench.running
        ? `bench   ${bench.progress < 0 ? 'calentando…' : `${Math.round(bench.progress * 100)} %`}\n`
        : `bench   ${bench.result.fps_avg} FPS media · ${bench.result.fps_1pct_low} 1% low\n`
      : '';
    statsEl.textContent =
      `FPS     ${meter.fps.toFixed(0)}  (${meter.ms.toFixed(1)} ms)\n` +
      `GPU     ${gpu.available ? `${gpuMs} ms` : 'n/d'}\n` +
      `draws   ${info.calls}\n` +
      `tris    ${info.triangles.toLocaleString('es-ES')}\n` +
      benchLine;
  }
});
