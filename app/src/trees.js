import * as THREE from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';

// Árboles low-poly instanciados (datos: models/almensilla_trees.json del agente 01).
// Una InstancedMesh por tipo y tesela de 500 m, para que el frustum culling (también el de la pasada de
// sombras) descarte las teselas lejanas.
const TILE_M = 500;

function colored(geometry, hex) {
  const g = geometry.toNonIndexed();
  const c = new THREE.Color(hex);
  const colors = new Float32Array(g.attributes.position.count * 3);
  for (let i = 0; i < colors.length; i += 3) colors.set([c.r, c.g, c.b], i);
  g.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  g.deleteAttribute('uv');
  return g;
}

function trunk(rTop, rBottom, height, hex = 0x6b5038) {
  return colored(new THREE.CylinderGeometry(rTop, rBottom, height, 6, 1, true).translate(0, height / 2, 0), hex);
}

function crown(radius, y, scale, hex) {
  return colored(new THREE.IcosahedronGeometry(radius, 0).scale(...scale).translate(0, y, 0), hex);
}

function crownLow(radius, y, scale, hex) {
  return colored(new THREE.OctahedronGeometry(radius, 0).scale(...scale).translate(0, y, 0), hex);
}

// Radio de la base del tronco de cada modelo (SHAPES.high); los arbustos no tienen tronco: no bloquean el paso
const TRUNK_RADIUS = { broadleaf: 0.18, olive: 0.24, pine: 0.3 };

// Formas por tipo (alturas en metros, escala 1). `low`: LOD lejano de 8 triángulos (copa sin tronco).
const SHAPES = {
  broadleaf: {
    high: () => [trunk(0.12, 0.18, 2.4), crown(1.7, 3.6, [1, 0.9, 1], 0x4f7d34)],
    low: () => [crownLow(1.8, 3.4, [1, 0.95, 1], 0x4f7d34)],
  },
  olive: {
    high: () => [trunk(0.14, 0.24, 1.3, 0x5e5446), crown(1.6, 2.3, [1.25, 0.75, 1.25], 0x7f8f5c)],
    low: () => [crownLow(1.7, 2.1, [1.25, 0.8, 1.25], 0x7f8f5c)],
  },
  pine: {
    high: () => [trunk(0.18, 0.3, 5.2, 0x5a4330), crown(2.9, 6.0, [1, 0.42, 1], 0x3f6130)],
    low: () => [crownLow(3.0, 5.8, [1, 0.5, 1], 0x3f6130)],
  },
  shrub: {
    high: () => [crown(0.75, 0.55, [1.2, 0.8, 1.2], 0x6e7c46)],
    low: () => [crownLow(0.8, 0.5, [1.2, 0.8, 1.2], 0x6e7c46)],
  },
};

export async function loadTrees(url, { castShadow = false } = {}) {
  const data = await (await fetch(url)).json();
  const geometries = Object.fromEntries(
    data.types.map((t) => [t, mergeGeometries(SHAPES[t].high(), false)]),
  );
  const lowGeometries = Object.fromEntries(
    data.types.map((t) => [t, mergeGeometries(SHAPES[t].low(), false)]),
  );
  const material = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.95, flatShading: true });

  // Agrupar instancias por tipo y tesela
  const groups = new Map();
  // y: cota del terreno en el pie; scale: escala vertical (altura LiDAR / altura del modelo); width: escala
  // horizontal (radio de copa / radio del modelo). Con datos antiguos (4–5 campos) la escala es uniforme.
  for (const [x, z, type, scale, y = 0, width = scale] of data.trees) {
    const key = `${type}|${Math.floor(x / TILE_M)}_${Math.floor(z / TILE_M)}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push([x, z, scale, y, width]);
  }

  const root = new THREE.Group();
  root.name = 'TREES';
  const m = new THREE.Matrix4();
  const q = new THREE.Quaternion();
  const up = new THREE.Vector3(0, 1, 0);
  const s = new THREE.Vector3();
  const p = new THREE.Vector3();
  for (const [key, items] of groups) {
    const [typeIndex, tile] = key.split('|');
    const type = data.types[Number(typeIndex)];
    const mesh = new THREE.InstancedMesh(geometries[type], material, items.length);
    mesh.name = `TREES_${type}_${tile}`;
    items.forEach(([x, z, scale, y, width], i) => {
      q.setFromAxisAngle(up, ((x * 12.9898 + z * 78.233) % 6.283)); // giro pseudoaleatorio estable
      m.compose(p.set(x, y - 0.1, z), q, s.set(width, scale, width)); // 10 cm hundido: no flota en ladera
      mesh.setMatrixAt(i, m);
    });
    mesh.computeBoundingSphere(); // con la geometría completa: también vale (conservadora) para la de LOD
    mesh.castShadow = castShadow;
    mesh.userData.lod = { high: geometries[type], low: lowGeometries[type] };
    root.add(mesh);
  }
  // Troncos para la colisión del personaje: radio de la base del tronco del modelo × escala horizontal
  const trunks = [];
  for (const [x, z, type, scale, , width = scale] of data.trees) {
    const r = TRUNK_RADIUS[data.types[type]];
    if (r) trunks.push(x, z, r * width);
  }
  return { root, count: data.trees.length, meshes: root.children.length, trunks };
}
