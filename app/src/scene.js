import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

// Luz de mediodía andaluz: cielo claro, sol alto desde el sur-suroeste.
const SKY_COLOR = 0xbcd6ec;
const FOG_NEAR_M = 700;
const FOG_FAR_M = 3600; // el término mide ~6.2 x 4.2 km: la niebla oculta el borde sin suelo exterior

export function createViewer(canvas) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(window.innerWidth, window.innerHeight, false);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.12; // la cal debe leerse blanca también en las fachadas a la sombra

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(SKY_COLOR);
  scene.fog = new THREE.Fog(SKY_COLOR, FOG_NEAR_M, FOG_FAR_M);

  // near=1 m: mejor precisión de profundidad a varios km (los viales están solo 2 cm sobre el terreno)
  const camera = new THREE.PerspectiveCamera(55, window.innerWidth / window.innerHeight, 1, 8000);
  camera.position.set(-600, 520, 900);

  const hemi = new THREE.HemisphereLight(0xdcecff, 0xb8a888, 1.7);
  scene.add(hemi);
  const sun = new THREE.DirectionalLight(0xfff1dc, 2.4);
  sun.position.set(-0.35, 1.0, 0.55).multiplyScalar(1000); // glTF: X=Este, Y=arriba, Z=-Norte -> sol al sur-oeste
  scene.add(sun);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.maxPolarAngle = Math.PI * 0.49; // no pasar bajo el terreno
  controls.minDistance = 20;
  controls.maxDistance = 5000;

  window.addEventListener('resize', () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(window.innerWidth, window.innerHeight, false);
  });

  return { renderer, scene, camera, controls, sun };
}
