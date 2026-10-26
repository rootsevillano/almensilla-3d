import * as THREE from 'three';

// Sombra del sol con un único mapa ajustado alrededor del foco (personaje o objetivo de la vista aérea).
// El radio cubierto crece con la distancia de la cámara al foco: a pie, texels de ~4 cm; en vista aérea,
// más superficie con menos detalle (la niebla disimula el resto). El centro se ajusta a la rejilla de texels
// en el espacio de la luz para que las sombras no "tiemblen" al desplazarse.
const MAP_SIZE = 2048;
const MIN_RADIUS_M = 32; // potencias de 2: el radio va por escalones (texel 3 cm … 50 cm)
const MAX_RADIUS_M = 512;
const RADIUS_PER_CAMERA_M = 1.1; // radio ≈ 1.1 × distancia cámara-foco
const LIGHT_DISTANCE_M = 300; // de sobra para edificios de ≤15 m

export class SunShadows {
  constructor(renderer, sun, scene) {
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFShadowMap;
    this.sun = sun;
    this.direction = sun.position.clone().normalize(); // hacia el sol
    sun.castShadow = true;
    sun.shadow.mapSize.set(MAP_SIZE, MAP_SIZE);
    sun.shadow.bias = -0.0004;
    sun.shadow.normalBias = 0.03;
    const cam = sun.shadow.camera;
    cam.near = 1;
    cam.far = LIGHT_DISTANCE_M * 2;
    scene.add(sun.target);

    // Base ortonormal del espacio de la luz, para el ajuste a la rejilla de texels
    this.right = new THREE.Vector3().crossVectors(new THREE.Vector3(0, 1, 0), this.direction).normalize();
    this.up = new THREE.Vector3().crossVectors(this.direction, this.right).normalize();
    this.radius = 0;
  }

  /** Recoloca el mapa de sombras alrededor de `focus`; `cameraDistance` fija el radio cubierto. */
  update(focus, cameraDistance) {
    const radius = THREE.MathUtils.clamp(cameraDistance * RADIUS_PER_CAMERA_M, MIN_RADIUS_M, MAX_RADIUS_M);
    // Radio por escalones para no recalcular la proyección (ni hacer temblar los texels) en cada fotograma
    const stepped = Math.pow(2, Math.ceil(Math.log2(radius)));
    const cam = this.sun.shadow.camera;
    if (stepped !== this.radius) {
      this.radius = stepped;
      cam.left = cam.bottom = -stepped;
      cam.right = cam.top = stepped;
      cam.updateProjectionMatrix();
    }
    const texel = (2 * this.radius) / MAP_SIZE;
    const u = Math.round(focus.dot(this.right) / texel) * texel;
    const v = Math.round(focus.dot(this.up) / texel) * texel;
    const w = focus.dot(this.direction);
    const center = new THREE.Vector3()
      .addScaledVector(this.right, u)
      .addScaledVector(this.up, v)
      .addScaledVector(this.direction, w);
    this.sun.target.position.copy(center);
    this.sun.position.copy(center).addScaledVector(this.direction, LIGHT_DISTANCE_M);
    this.sun.target.updateMatrixWorld();
  }

  get texelSizeM() {
    return (2 * this.radius) / MAP_SIZE;
  }
}

/** Activa proyección y recepción de sombras; añade normales donde faltan (los GLB solo traen POSITION). */
export function enableShadows({ casters = [], receivers = [] }) {
  const prepare = (mesh) => {
    if (!mesh.geometry.attributes.normal) {
      // Normales planas: geometría no indexada para que cada cara tenga la suya (normalBias las necesita)
      if (mesh.geometry.index) mesh.geometry = mesh.geometry.toNonIndexed();
      mesh.geometry.computeVertexNormals();
    }
  };
  for (const root of casters) root.traverse((o) => o.isMesh && (prepare(o), (o.castShadow = true)));
  for (const root of receivers) root.traverse((o) => o.isMesh && (prepare(o), (o.receiveShadow = true)));
}
