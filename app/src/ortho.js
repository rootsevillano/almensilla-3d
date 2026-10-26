import * as THREE from 'three';

// Ortofoto PNOA como textura del terreno (datos: models/ortho/ del agente 01, CC BY 4.0 scne.es).
// Cada nodo TERRAIN_<i>_<j> corresponde a la imagen pnoa_<i>_<j> (misma rejilla local de 500 m).
// Todas las teselas arrancan con su versión de 256 px; la de 1024 px solo se carga en las teselas cercanas
// y se libera al alejarse (con margen para no cargar/descargar sin parar en el límite).
const NEAR_LOAD_M = 300;
const FAR_UNLOAD_M = 550;
const MAX_CONCURRENT = 3;

function addTileUVs(geometry, i, j, tile) {
  const pos = geometry.attributes.position;
  const uv = new Float32Array(pos.count * 2);
  for (let k = 0; k < pos.count; k++) {
    uv[2 * k] = (pos.getX(k) - i * tile) / tile;
    uv[2 * k + 1] = (-pos.getZ(k) - j * tile) / tile; // glTF Z = -Norte; v=1 en el borde norte (fila 0 de la imagen)
  }
  geometry.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
}

// La ortofoto (0.5 m/px) se ve borrosa a pie: se añade un grano procedural en coordenadas de mundo
// (dos octavas de ruido, ~0.4 m y ~1.6 m) que se desvanece con la distancia (fwidth) y no gasta memoria.
const DETAIL_VERTEX = /* glsl */ `
varying vec3 vOrthoWorld;
`;
const DETAIL_FRAGMENT = /* glsl */ `
varying vec3 vOrthoWorld;
float orthoHash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float orthoNoise(vec2 p) {
  vec2 i = floor(p), f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(mix(orthoHash(i), orthoHash(i + vec2(1.0, 0.0)), u.x),
             mix(orthoHash(i + vec2(0.0, 1.0)), orthoHash(i + vec2(1.0, 1.0)), u.x), u.y);
}
`;
const DETAIL_APPLY = /* glsl */ `
{
  vec2 wp = vOrthoWorld.xz;
  float n = 0.6 * orthoNoise(wp * 2.5) + 0.4 * orthoNoise(wp * 0.6);
  float near = 1.0 - smoothstep(0.02, 0.12, fwidth(wp.x));
  diffuseColor.rgb *= mix(1.0, 0.86 + 0.28 * n, near);
}
`;

function detailMaterial(map, name) {
  const mat = new THREE.MeshStandardMaterial({ name, map, roughness: 1.0, metalness: 0.0 });
  mat.onBeforeCompile = (shader) => {
    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', `#include <common>\n${DETAIL_VERTEX}`)
      .replace('#include <begin_vertex>', '#include <begin_vertex>\nvOrthoWorld = (modelMatrix * vec4(position, 1.0)).xyz;');
    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', `#include <common>\n${DETAIL_FRAGMENT}`)
      .replace('#include <map_fragment>', `#include <map_fragment>\n${DETAIL_APPLY}`);
  };
  mat.customProgramCacheKey = () => 'ortho-detail'; // un único programa para las 85 teselas
  return mat;
}

export class OrthoGround {
  constructor(renderer, baseUrl = 'models/ortho') {
    this.baseUrl = baseUrl;
    this.loader = new THREE.TextureLoader();
    this.anisotropy = renderer.capabilities.getMaxAnisotropy();
    this.tiles = [];
    this.loading = 0;
    this.stats = { tiles: 0, hiLoaded: 0, hiLoading: 0 };
  }

  #configure(texture) {
    texture.colorSpace = THREE.SRGBColorSpace;
    texture.anisotropy = this.anisotropy;
    texture.wrapS = texture.wrapT = THREE.ClampToEdgeWrapping;
    return texture;
  }

  /** Prepara las mallas TERRAIN_* (UV y material propio con la textura de baja resolución). */
  async init(terrainRoot) {
    const index = await (await fetch(`${this.baseUrl}/index.json`)).json();
    this.attribution = index.attribution;
    const T = index.tile_m;
    const available = new Set(index.tiles.map(([i, j]) => `${i}_${j}`));
    const meshes = [];
    terrainRoot.traverse((o) => o.isMesh && o.name.startsWith('TERRAIN_') && meshes.push(o));
    await Promise.all(meshes.map(async (mesh) => {
      const [i, j] = mesh.name.slice('TERRAIN_'.length).split('_').map(Number);
      if (!available.has(`${i}_${j}`)) return;
      addTileUVs(mesh.geometry, i, j, T);
      const low = this.#configure(await this.loader.loadAsync(`${this.baseUrl}/lo/pnoa_${i}_${j}.jpg`));
      mesh.material = detailMaterial(low, `MAT_terrain_ortho_${i}_${j}`);
      this.tiles.push({
        mesh, i, j, low, hi: null, pending: false,
        box: new THREE.Box3().setFromObject(mesh), // con relieve: la caja incluye las cotas reales de la tesela
      });
    }));
    this.stats.tiles = this.tiles.length;
  }

  update(camera) {
    const p = camera.position;
    const wanted = [];
    for (const t of this.tiles) {
      const d = t.box.distanceToPoint(p);
      if (t.hi && d > FAR_UNLOAD_M) {
        t.mesh.material.map = t.low;
        t.hi.dispose();
        t.hi = null;
      } else if (!t.hi && !t.pending && d < NEAR_LOAD_M) {
        wanted.push([d, t]);
      }
    }
    wanted.sort((a, b) => a[0] - b[0]);
    for (const [, t] of wanted) {
      if (this.loading >= MAX_CONCURRENT) break;
      this.#loadHi(t);
    }
    this.stats.hiLoaded = this.tiles.filter((t) => t.hi).length;
    this.stats.hiLoading = this.loading;
  }

  #loadHi(t) {
    t.pending = true;
    this.loading++;
    this.loader.loadAsync(`${this.baseUrl}/hi/pnoa_${t.i}_${t.j}.jpg`).then((tex) => {
      t.hi = this.#configure(tex);
      t.mesh.material.map = t.hi;
    }).catch((err) => console.warn(`[ortho] ${t.i}_${t.j}:`, err))
      .finally(() => {
        t.pending = false;
        this.loading--;
      });
  }
}
