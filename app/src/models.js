import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';

// Contrato con el agente 01: solo se lee app/public/models/; los nodos COL_* son colisión estática.
const MODELS = {
  terrain: 'models/almensilla_terrain.glb',
  roads: 'models/almensilla_roads.glb',
  buildings: 'models/almensilla_buildings.glb',
};
export const COLLISION_PREFIX = 'COL_';
export const PARAPET_PREFIX = 'PARAPET_';

export async function loadModels(onProgress) {
  const loader = new GLTFLoader();
  const entries = Object.entries(MODELS);
  let done = 0;
  const results = await Promise.all(
    entries.map(async ([key, url]) => {
      const gltf = await loader.loadAsync(url);
      onProgress?.(++done, entries.length, key);
      return [key, gltf.scene];
    }),
  );
  return Object.fromEntries(results);
}

// Mismas teselas que terreno y viales: el frustum culling (incluida la pasada de sombras) descarta lo lejano
const TILE_M = 500;

/**
 * Fusiona las ~2800 mallas COL_ de edificios en una malla por material y tesela de 500 m (regla 2 del agente 02:
 * pocas draw calls, pero sin perder el culling: con una sola malla por material, la pasada de sombras dibujaba
 * el pueblo entero aunque el mapa de sombras cubriera 64 m).
 * Las mallas originales se devuelven aparte, fuera de la escena, para el sistema de colisiones (agente 03).
 */
export function mergeBuildings(root) {
  root.updateMatrixWorld(true);
  const collisionMeshes = [];
  const groups = new Map();
  const box = new THREE.Box3();
  const c = new THREE.Vector3();
  root.traverse((obj) => {
    if (!obj.isMesh || !obj.name.startsWith(COLLISION_PREFIX)) return;
    collisionMeshes.push(obj);
    box.setFromObject(obj).getCenter(c);
    const tile = `${Math.floor(c.x / TILE_M)}_${Math.floor(-c.z / TILE_M)}`; // glTF Z = -Norte
    const key = `${obj.material.name}|${tile}`;
    if (!groups.has(key)) groups.set(key, { material: obj.material, tile, geometries: [] });
    groups.get(key).geometries.push(obj.geometry.clone().applyMatrix4(obj.matrixWorld));
  });

  const merged = new THREE.Group();
  merged.name = 'BUILDINGS_MERGED';
  for (const { material, tile, geometries } of groups.values()) {
    const mesh = new THREE.Mesh(mergeGeometries(geometries, false), material);
    mesh.name = `BUILDINGS_${material.name}_${tile}`;
    merged.add(mesh);
    geometries.forEach((g) => g.dispose());
  }
  for (const mesh of collisionMeshes) mesh.removeFromParent();

  // Pretiles (PARAPET_<i>_<j>): decoración ya agrupada por tesela en el GLB; no colisionan
  const parapets = [];
  root.traverse((obj) => obj.isMesh && obj.name.startsWith(PARAPET_PREFIX) && parapets.push(obj));
  for (const mesh of parapets) merged.add(mesh); // add() lo saca de su padre anterior
  return { merged, collisionMeshes, parapets };
}

/** Centro del casco: mediana de los centros de los edificios (robusta frente a cortijos dispersos). */
export function urbanCenter(collisionMeshes) {
  const box = new THREE.Box3();
  const xs = [];
  const zs = [];
  for (const mesh of collisionMeshes) {
    box.setFromObject(mesh);
    xs.push((box.min.x + box.max.x) / 2);
    zs.push((box.min.z + box.max.z) / 2);
  }
  const median = (a) => a.sort((p, q) => p - q)[Math.floor(a.length / 2)];
  return new THREE.Vector3(median(xs), 0, median(zs));
}
