import * as THREE from 'three';

/**
 * Consulta rápida de la altura del suelo caminable (TERRAIN_*, ROAD_*, POOL_*).
 *
 * Con relieve, terreno y viales suman ~0.5–0.7 M triángulos y un Raycaster de Three.js prueba todos los de cada
 * tesela cuya esfera envolvente cruza el rayo (11 teselas en la vertical): 4.3 ms por consulta. Aquí los triángulos
 * se reparten al cargar en una rejilla en planta (XZ) y cada consulta solo prueba los de su celda.
 * Devuelve la superficie más alta por debajo de `fromY` (lo mismo que el primer impacto de un rayo hacia abajo).
 */
export class GroundIndex {
  constructor(meshes, cellSize = 5) {
    this.cell = cellSize;
    this.grid = new Map();
    let total = 0;
    for (const mesh of meshes) total += this.#addMesh(mesh);
    this.triangles = total;
  }

  #addMesh(mesh) {
    mesh.updateWorldMatrix(true, false);
    const pos = mesh.geometry.attributes.position;
    const index = mesh.geometry.index;
    const count = index ? index.count : pos.count;
    const v = new THREE.Vector3();
    const tri = new Float32Array(count * 3); // copia en mundo: [x, y, z] × 3 por triángulo
    for (let i = 0; i < count; i++) {
      v.fromBufferAttribute(pos, index ? index.getX(i) : i).applyMatrix4(mesh.matrixWorld);
      tri.set([v.x, v.y, v.z], i * 3);
    }
    const s = this.cell;
    for (let t = 0; t < count / 3; t++) {
      const o = t * 9;
      const minX = Math.min(tri[o], tri[o + 3], tri[o + 6]);
      const maxX = Math.max(tri[o], tri[o + 3], tri[o + 6]);
      const minZ = Math.min(tri[o + 2], tri[o + 5], tri[o + 8]);
      const maxZ = Math.max(tri[o + 2], tri[o + 5], tri[o + 8]);
      for (let i = Math.floor(minX / s); i <= Math.floor(maxX / s); i++) {
        for (let j = Math.floor(minZ / s); j <= Math.floor(maxZ / s); j++) {
          const key = i * 100003 + j; // clave numérica: más rápida que una cadena
          let cell = this.grid.get(key);
          if (!cell) this.grid.set(key, (cell = []));
          cell.push(tri, o);
        }
      }
    }
    return count / 3;
  }

  /** Altura del suelo en (x, z) por debajo de fromY, o null si no hay suelo (fuera del término). */
  heightAt(x, z, fromY = Infinity) {
    const cell = this.grid.get(Math.floor(x / this.cell) * 100003 + Math.floor(z / this.cell));
    if (!cell) return null;
    let best = null;
    for (let k = 0; k < cell.length; k += 2) {
      const t = cell[k];
      const o = cell[k + 1];
      const ax = t[o], ay = t[o + 1], az = t[o + 2];
      const bx = t[o + 3], by = t[o + 4], bz = t[o + 5];
      const cx = t[o + 6], cy = t[o + 7], cz = t[o + 8];
      // baricéntricas en planta
      const d = (bz - cz) * (ax - cx) + (cx - bx) * (az - cz);
      if (Math.abs(d) < 1e-12) continue; // triángulo vertical (bordillo): no es suelo
      const l1 = ((bz - cz) * (x - cx) + (cx - bx) * (z - cz)) / d;
      const l2 = ((cz - az) * (x - cx) + (ax - cx) * (z - cz)) / d;
      const l3 = 1 - l1 - l2;
      if (l1 < -1e-6 || l2 < -1e-6 || l3 < -1e-6) continue;
      const y = l1 * ay + l2 * by + l3 * cy;
      if (y <= fromY && (best === null || y > best)) best = y;
    }
    return best;
  }
}
