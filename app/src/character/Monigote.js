import * as THREE from 'three';

// Monigote 3D blanco (cabeza de huevo sin cara, cuerpo de cápsula, manos de manopla, pies redondeados),
// construido con primitivas. Altura ~1.8 m; mira hacia +Z local; el origen está en los pies.
// Algo de emisión para que siga leyéndose blanco a contraluz (la escena no tiene luz de relleno).
const WHITE = new THREE.MeshStandardMaterial({
  color: 0xf4f4f6, emissive: 0x4a4a50, roughness: 0.38, metalness: 0.0,
});

const HIP_Y = 0.74;
const SHOULDER_Y = 1.22;
const STRIDE_M = 1.35; // distancia recorrida por ciclo completo de paso

function part(geometry, { x = 0, y = 0, z = 0, sx = 1, sy = 1, sz = 1 } = {}) {
  const mesh = new THREE.Mesh(geometry, WHITE);
  mesh.position.set(x, y, z);
  mesh.scale.set(sx, sy, sz);
  return mesh;
}

function limb(pivotX, pivotY, { radius, length, endRadius, endOffset = {} }) {
  const pivot = new THREE.Group();
  pivot.position.set(pivotX, pivotY, 0);
  pivot.add(part(new THREE.CapsuleGeometry(radius, length, 6, 12), { y: -(length / 2 + radius * 0.6) }));
  pivot.add(part(new THREE.SphereGeometry(endRadius, 16, 12), { y: -(length + radius * 1.6), ...endOffset }));
  return pivot;
}

export class Monigote extends THREE.Group {
  constructor() {
    super();
    this.name = 'CHARACTER_monigote';

    this.body = new THREE.Group(); // todo lo que oscila con el paso
    this.add(this.body);

    this.torso = part(new THREE.CapsuleGeometry(0.2, 0.4, 8, 16), { y: 1.03, sz: 0.78 });
    this.head = part(new THREE.SphereGeometry(0.26, 24, 18), { y: 1.55, sy: 1.12 });
    this.body.add(this.torso, this.head);

    this.armL = limb(0.255, SHOULDER_Y, { radius: 0.072, length: 0.36, endRadius: 0.088 });
    this.armR = limb(-0.255, SHOULDER_Y, { radius: 0.072, length: 0.36, endRadius: 0.088 });
    this.armL.rotation.z = 0.12;
    this.armR.rotation.z = -0.12;
    const foot = { sy: 0.55, sz: 1.65, z: 0.07 };
    this.legL = limb(0.105, HIP_Y, { radius: 0.095, length: 0.4, endRadius: 0.105, endOffset: foot });
    this.legR = limb(-0.105, HIP_Y, { radius: 0.095, length: 0.4, endRadius: 0.105, endOffset: foot });
    this.body.add(this.armL, this.armR, this.legL, this.legR);

    this.add(createBlobShadow());
    this.phase = 0;
    this.opacity = 1;
    this.idleTime = 0;
  }

  /** Opacidad del cuerpo (1 = opaco). Solo se activa la transparencia cuando hace falta (cámara muy cerca). */
  setOpacity(a) {
    if (Math.abs(a - this.opacity) < 0.01) return;
    const wasTransparent = this.opacity < 1;
    this.opacity = a;
    WHITE.opacity = a;
    WHITE.transparent = a < 1;
    WHITE.depthWrite = a >= 1;
    if (wasTransparent !== WHITE.transparent) WHITE.needsUpdate = true;
  }

  /** speed en m/s; runFactor 0..1 (andar..correr) solo cambia la amplitud del gesto. */
  animate(dt, speed, runFactor = 0) {
    this.idleTime += dt;
    this.phase += (speed * dt) / STRIDE_M * Math.PI * 2;
    const moving = THREE.MathUtils.clamp(speed / 2.0, 0, 1);
    const swing = Math.sin(this.phase) * moving;
    const legAmp = 0.55 + 0.25 * runFactor;
    const armAmp = 0.45 + 0.45 * runFactor;

    this.legL.rotation.x = swing * legAmp;
    this.legR.rotation.x = -swing * legAmp;
    this.armL.rotation.x = -swing * armAmp;
    this.armR.rotation.x = swing * armAmp;

    const breathe = Math.sin(this.idleTime * 2.2) * 0.008 * (1 - moving);
    this.body.position.y = Math.abs(Math.cos(this.phase)) * 0.045 * moving + breathe;
    this.body.rotation.x = 0.06 * moving + 0.08 * runFactor; // inclinación hacia delante
    this.body.rotation.y = Math.sin(this.phase) * 0.06 * moving; // contoneo de hombros
    this.head.rotation.x = -this.body.rotation.x * 0.6; // la cabeza compensa y mira al frente
  }
}

/** Sombra difusa bajo los pies (la escena no usa mapas de sombra). */
function createBlobShadow() {
  const size = 64;
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext('2d');
  const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  g.addColorStop(0, 'rgba(0,0,0,0.45)');
  g.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, size, size);
  const mesh = new THREE.Mesh(
    new THREE.CircleGeometry(0.5, 24),
    new THREE.MeshBasicMaterial({ map: new THREE.CanvasTexture(canvas), transparent: true, depthWrite: false }),
  );
  mesh.rotation.x = -Math.PI / 2;
  mesh.position.y = 0.015; // 1.5 cm sobre el suelo que pisa el personaje
  mesh.renderOrder = 1;
  mesh.name = 'CHARACTER_shadow';
  return mesh;
}
