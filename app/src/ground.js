import * as THREE from 'three';

// Detalle de suelo en el shader, en coordenadas de mundo (sin texturas):
// baldosa de 40 cm en las aceras y lámina de agua para las piscinas.
const SIDEWALK_TILE_M = 0.4;

function sidewalkMaterial(base) {
  const mat = base.clone();
  mat.name = `${base.name}_tiles`;
  mat.onBeforeCompile = (shader) => {
    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', '#include <common>\nvarying vec3 vWorldPos;')
      .replace('#include <begin_vertex>', '#include <begin_vertex>\nvWorldPos = (modelMatrix * vec4(position, 1.0)).xyz;');
    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', '#include <common>\nvarying vec3 vWorldPos;')
      .replace('#include <color_fragment>', /* glsl */ `#include <color_fragment>
      {
        vec2 g = abs(fract(vWorldPos.xz / ${SIDEWALK_TILE_M.toFixed(2)}) - 0.5);
        float joint = step(0.46, max(g.x, g.y));
        float far = smoothstep(0.05, 0.25, fwidth(vWorldPos.x));   // sin muaré a distancia
        diffuseColor.rgb *= mix(1.0 - 0.18 * joint, 0.97, far);
      }`);
  };
  mat.customProgramCacheKey = () => 'sidewalk-tiles';
  return mat;
}

function waterMaterial(base) {
  return new THREE.MeshStandardMaterial({
    name: `${base.name}_water`,
    color: 0x2f9fd0,
    emissive: 0x0b3a52,
    roughness: 0.08,
    metalness: 0.0,
  });
}

/**
 * Sustituye los materiales de aceras y piscinas por sus variantes con detalle. Viales y piscinas van encima del
 * terreno continuo (unos cm, triangulados de otra forma): se les acerca en profundidad para que nunca parpadeen.
 */
export function applyGroundMaterials(...roots) {
  const cache = new Map();
  const variant = (mat) => {
    if (cache.has(mat)) return cache.get(mat);
    let out = mat;
    if (mat.name === 'MAT_road_sidewalk') out = sidewalkMaterial(mat);
    else if (mat.name === 'MAT_pool_water') out = waterMaterial(mat);
    if (mat.name.startsWith('MAT_road_') || mat.name.startsWith('MAT_pool_')) {
      out.polygonOffset = true;
      out.polygonOffsetFactor = -2;
      out.polygonOffsetUnits = -4;
    }
    if (mat.name === 'MAT_road_marking') { // pasos de cebra: 1 cm sobre la calzada, más cerca aún en profundidad
      out.polygonOffsetFactor = -4;
      out.polygonOffsetUnits = -8;
    }
    cache.set(mat, out);
    return out;
  };
  for (const root of roots) root.traverse((o) => o.isMesh && (o.material = variant(o.material)));
}
