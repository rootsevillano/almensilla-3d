import * as THREE from 'three';

// Nivel de detalle por tesela según la distancia de la cámara al borde de la tesela (bounding sphere).
// Distancias elegidas por tamaño en pantalla a 1080p (FOV 55°: ~0.04° por píxel):
//  - pretil de 0.9 m: ~2 px a 700 m -> se oculta más lejos; nunca proyecta sombra.
//  - árboles: sombra solo cerca (la del olivo ya no se distingue a más de ~200 m), copa simple a partir de 350 m
//    y ocultos a partir de 2200 m (la niebla, 700–3600 m, ya los ha fundido con el suelo).
const PARAPET_HIDE_M = 700;
const TREE_SHADOW_M = 220;
const TREE_LOW_M = 350;
const TREE_HIDE_M = 2200;

const sphere = new THREE.Sphere();

function distanceTo(mesh, camera) {
  if (!mesh.geometry.boundingSphere) mesh.geometry.computeBoundingSphere();
  sphere.copy(mesh.boundingSphere ?? mesh.geometry.boundingSphere).applyMatrix4(mesh.matrixWorld);
  return Math.max(0, camera.position.distanceTo(sphere.center) - sphere.radius);
}

export class LodManager {
  constructor({ parapets = [], trees = [], treeShadows = true }) {
    this.parapets = parapets;
    this.trees = trees;
    this.treeShadows = treeShadows;
    this.distanceScale = 1; // niveles de calidad: <1 acorta todas las distancias de LOD (quality.js)
    for (const m of parapets) {
      m.castShadow = false;
      m.receiveShadow = true;
    }
    this.stats = { parapetsVisible: 0, treeTilesHigh: 0, treeTilesLow: 0, treeTilesShadow: 0 };
  }

  update(camera) {
    const s = { parapetsVisible: 0, treeTilesHigh: 0, treeTilesLow: 0, treeTilesShadow: 0 };
    const k = this.distanceScale;
    for (const m of this.parapets) {
      m.visible = distanceTo(m, camera) < PARAPET_HIDE_M * k;
      s.parapetsVisible += m.visible;
    }
    for (const m of this.trees) {
      const d = distanceTo(m, camera);
      m.visible = d < TREE_HIDE_M * k;
      if (!m.visible) continue;
      const high = d < TREE_LOW_M * k;
      m.geometry = high ? m.userData.lod.high : m.userData.lod.low;
      m.castShadow = this.treeShadows && d < TREE_SHADOW_M * k;
      s.treeTilesHigh += high;
      s.treeTilesLow += !high;
      s.treeTilesShadow += m.castShadow;
    }
    this.stats = s;
  }
}
