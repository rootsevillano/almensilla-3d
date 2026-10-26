import * as THREE from 'three';

// Fachadas de pueblo andaluz dibujadas en el shader (sin texturas ni geometría extra):
// encalado, zócalo, una ventana con reja por hueco de ~3.2 m en cada planta de 3 m y cornisa.
// Para cada cara vertical se calcula al cargar su coordenada a lo largo del muro (u), la longitud del muro
// y la altura de coronación (atributo `facade`); las cubiertas y los pretiles se distinguen por su orientación
// y por su cota de arranque.
const FLOOR_H = 3.0; // contrato del agente 01: plantas × 3 m
const BAY_M = 3.2;

const KIND = { wall: 0, roof: 1, parapet: 2 };

// Variantes por material de uso (nombres de los GLB del agente 01)
const VARIANTS = {
  MAT_1_residential: 'house',
  MAT_4_3_publicServices: 'house',
  MAT_4_1_office: 'house',
  MAT_unknown: 'house',
  MAT_4_2_retail: 'shop',
  MAT_3_industrial: 'shed',
  MAT_2_agriculture: 'shed',
};

/** Añade el atributo `facade` (u, longitud de muro, tipo, coronación) a una geometría no indexada. */
function addFacadeAttribute(geometry) {
  const pos = geometry.attributes.position;
  const out = new Float32Array(pos.count * 4);
  const a = new THREE.Vector3();
  const b = new THREE.Vector3();
  const c = new THREE.Vector3();
  const n = new THREE.Vector3();
  const e1 = new THREE.Vector3();
  const e2 = new THREE.Vector3();
  for (let i = 0; i < pos.count; i += 3) {
    a.fromBufferAttribute(pos, i);
    b.fromBufferAttribute(pos, i + 1);
    c.fromBufferAttribute(pos, i + 2);
    n.crossVectors(e1.subVectors(b, a), e2.subVectors(c, a));
    const len = n.length() || 1;
    let kind;
    let u = [0, 0, 0];
    let wallLen = 0;
    const minY = Math.min(a.y, b.y, c.y);
    const maxY = Math.max(a.y, b.y, c.y);
    if (Math.abs(n.y) > 0.9 * len) {
      kind = KIND.roof;
    } else {
      // tangente horizontal del muro = up × normal
      const tx = n.z / len;
      const tz = -n.x / len;
      u = [a, b, c].map((v) => v.x * tx + v.z * tz);
      const uMin = Math.min(...u);
      wallLen = Math.max(...u) - uMin;
      u = u.map((x) => x - uMin);
      kind = minY > 0.3 ? KIND.parapet : KIND.wall; // los muros de cada parte arrancan en Y=0
    }
    for (let k = 0; k < 3; k++) out.set([u[k], wallLen, kind, maxY], (i + k) * 4);
  }
  geometry.setAttribute('facade', new THREE.BufferAttribute(out, 4));
}

const VERTEX_HEAD = /* glsl */ `
attribute vec4 facade;
varying vec4 vFacade;
varying float vWorldY;
`;

const FRAGMENT_HEAD = /* glsl */ `
varying vec4 vFacade;
varying float vWorldY;
uniform vec3 uWall;
uniform vec3 uSocle;
uniform vec3 uRoof;
uniform vec3 uGlass;
uniform vec3 uFrame;
`;

const FRAGMENT_BODY = /* glsl */ `
{
  float kind = vFacade.z;
  vec3 col = uWall;
  if (kind > 0.5 && kind < 1.5) {
    col = uRoof;
  } else if (kind < 0.5) {
    float u = vFacade.x;
    float wallLen = vFacade.y;
    float top = vFacade.w;
    float y = vWorldY;
    if (y < SOCLE_H) col = uSocle;
    if (top > 2.0 && top - y < 0.22) col = uWall * 0.9;   // cornisa
#ifdef WINDOWS
    float level = floor(y / ${FLOOR_H.toFixed(1)});
    float fy = y - level * ${FLOOR_H.toFixed(1)};
    float bays = floor(wallLen / ${BAY_M.toFixed(1)});
    if (bays >= 1.0 && level * ${FLOOR_H.toFixed(1)} + 2.4 <= top + 0.01) {
      float slot = wallLen / bays;
      float su = mod(u, slot) - 0.5 * slot;
  #ifdef SHOP
      float hw = level < 0.5 ? min(1.4, 0.4 * slot) : 0.55;
      float y0 = level < 0.5 ? 0.35 : 0.95;
      float y1 = level < 0.5 ? 2.6 : 2.25;
  #else
      float hw = 0.55;
      float y0 = 0.95;
      float y1 = 2.25;
  #endif
      if (abs(su) < hw && fy > y0 && fy < y1) {
        float edge = min(hw - abs(su), min(fy - y0, y1 - fy));
        vec3 w = edge < 0.07 ? uFrame : uGlass;
        if (edge >= 0.07 && mod(su + hw, 0.14) < 0.025) w = uFrame * 0.35;   // reja
        // a distancia el patrón se funde con el color medio (evita muaré)
        float far = smoothstep(0.08, 0.35, fwidth(u));
        col = mix(w, mix(col, uGlass, 0.35), far);
      }
    }
#endif
  }
  diffuseColor.rgb = col;
}
`;

function facadeMaterial(base, variant) {
  const mat = base.clone();
  mat.name = `${base.name}_facade`;
  mat.flatShading = true;
  const shed = variant === 'shed';
  const uniforms = {
    uWall: { value: new THREE.Color(shed ? 0xc9c8c2 : 0xf4f2ea) },
    uSocle: { value: new THREE.Color(shed ? 0x9a9a94 : 0xe0c27f) }, // zócalo albero
    uRoof: { value: new THREE.Color(shed ? 0x9ea3a6 : 0xd8cfbf) },
    uGlass: { value: new THREE.Color(0x2f3a44) },
    uFrame: { value: new THREE.Color(0xe9e6dc) },
  };
  mat.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, uniforms);
    shader.defines = { ...shader.defines, SOCLE_H: shed ? '0.4' : '0.65' };
    if (!shed) shader.defines.WINDOWS = '';
    if (variant === 'shop') shader.defines.SHOP = '';
    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', `#include <common>\n${VERTEX_HEAD}`)
      .replace('#include <begin_vertex>', '#include <begin_vertex>\nvFacade = facade;\nvWorldY = position.y;');
    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', `#include <common>\n${FRAGMENT_HEAD}`)
      .replace('#include <color_fragment>', `#include <color_fragment>\n${FRAGMENT_BODY}`);
  };
  mat.customProgramCacheKey = () => `facade-${variant}`;
  return mat;
}

/** Prepara las mallas de edificios (no indexadas, normales planas, atributo facade) y les asigna el shader. */
export function applyFacades(root) {
  const cache = new Map();
  const parapet = new THREE.MeshStandardMaterial({ name: 'MAT_parapet', color: 0xf4f2ea, roughness: 0.9, flatShading: true });
  root.traverse((mesh) => {
    if (!mesh.isMesh) return;
    if (mesh.material.name === 'MAT_parapet') {
      mesh.material = parapet; // pretil: cal lisa, sin ventanas
      return;
    }
    if (mesh.geometry.index) mesh.geometry = mesh.geometry.toNonIndexed();
    if (!mesh.geometry.attributes.normal) mesh.geometry.computeVertexNormals();
    addFacadeAttribute(mesh.geometry);
    const variant = VARIANTS[mesh.material.name] ?? 'house';
    const key = `${mesh.material.name}|${variant}`;
    if (!cache.has(key)) cache.set(key, facadeMaterial(mesh.material, variant));
    mesh.material = cache.get(key);
  });
}
