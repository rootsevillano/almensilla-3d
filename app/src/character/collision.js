import * as THREE from 'three';

/**
 * Colisión del personaje contra las mallas COL_ (contrato del agente 01).
 *
 * Los edificios son extrusiones verticales desde Y=0 y el personaje camina siempre por debajo de sus cubiertas,
 * así que la colisión se resuelve en planta: se extraen de cada malla COL_ las aristas inferiores de sus caras
 * verticales (= contorno exacto de la huella, patios incluidos) y se guardan en una rejilla espacial.
 * El personaje es un círculo de radio r en XZ que se empuja fuera de los segmentos cercanos.
 */
export class FootprintCollider {
  constructor(meshes, cellSize = 8) {
    this.cellSize = cellSize;
    this.grid = new Map();
    this.segments = []; // [ax, az, bx, bz]
    const a = new THREE.Vector3();
    const b = new THREE.Vector3();
    const c = new THREE.Vector3();
    for (const mesh of meshes) this.#addMesh(mesh, a, b, c);
  }

  #addMesh(mesh, a, b, c) {
    const pos = mesh.geometry.attributes.position;
    const index = mesh.geometry.index;
    const count = index ? index.count : pos.count;
    const at = (i) => (index ? index.getX(i) : i);
    const ab = new THREE.Vector3();
    const ac = new THREE.Vector3();
    for (let i = 0; i < count; i += 3) {
      a.fromBufferAttribute(pos, at(i)).applyMatrix4(mesh.matrixWorld);
      b.fromBufferAttribute(pos, at(i + 1)).applyMatrix4(mesh.matrixWorld);
      c.fromBufferAttribute(pos, at(i + 2)).applyMatrix4(mesh.matrixWorld);
      const n = ab.subVectors(b, a).cross(ac.subVectors(c, a));
      if (Math.abs(n.y) > 0.1 * n.length()) continue; // solo caras verticales (muros)
      const ground = [a, b, c].filter((v) => v.y < 0.05);
      if (ground.length === 2) this.#insert(ground[0].x, ground[0].z, ground[1].x, ground[1].z);
    }
  }

  #key(i, j) {
    return `${i},${j}`;
  }

  #insert(ax, az, bx, bz) {
    const seg = [ax, az, bx, bz];
    this.segments.push(seg);
    const s = this.cellSize;
    for (let i = Math.floor(Math.min(ax, bx) / s); i <= Math.floor(Math.max(ax, bx) / s); i++) {
      for (let j = Math.floor(Math.min(az, bz) / s); j <= Math.floor(Math.max(az, bz) / s); j++) {
        const k = this.#key(i, j);
        if (!this.grid.has(k)) this.grid.set(k, []);
        this.grid.get(k).push(seg);
      }
    }
  }

  #nearby(x, z, r) {
    const s = this.cellSize;
    const found = new Set();
    for (let i = Math.floor((x - r) / s); i <= Math.floor((x + r) / s); i++) {
      for (let j = Math.floor((z - r) / s); j <= Math.floor((z + r) / s); j++) {
        const cell = this.grid.get(this.#key(i, j));
        if (cell) for (const seg of cell) found.add(seg);
      }
    }
    return found;
  }

  /** Empuja `pos` (Vector3, usa x/z) fuera de los muros. Devuelve true si hubo contacto. */
  resolve(pos, radius, iterations = 3) {
    let hit = false;
    for (let it = 0; it < iterations; it++) {
      let moved = false;
      for (const [ax, az, bx, bz] of this.#nearby(pos.x, pos.z, radius)) {
        const dx = bx - ax;
        const dz = bz - az;
        const len2 = dx * dx + dz * dz || 1e-9;
        const t = THREE.MathUtils.clamp(((pos.x - ax) * dx + (pos.z - az) * dz) / len2, 0, 1);
        const px = pos.x - (ax + t * dx);
        const pz = pos.z - (az + t * dz);
        const d2 = px * px + pz * pz;
        if (d2 >= radius * radius) continue;
        const d = Math.sqrt(d2) || 1e-6;
        pos.x += (px / d) * (radius - d);
        pos.z += (pz / d) * (radius - d);
        moved = hit = true;
      }
      if (!moved) break;
    }
    return hit;
  }
}
