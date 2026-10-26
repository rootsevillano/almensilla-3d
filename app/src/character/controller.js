import * as THREE from 'three';
import { GroundIndex } from './groundIndex.js';

const WALK_SPEED = 3.0; // m/s (algo más rápido que la marcha real: el término mide ~6 km)
const RUN_SPEED = 8.0;
const ACCEL = 14.0; // m/s²
const DECEL = 18.0;
const TURN_RATE = 12.0; // suavizado del giro hacia la dirección de marcha
const GRAVITY = 18.0; // más fuerte que 9.81 para un salto con buena respuesta
const JUMP_SPEED = 5.5;
const RADIUS = 0.32; // radio del personaje en planta
const EYE_HEIGHT = 1.55; // punto de mira de la cámara

const CAM_DISTANCE = 5.5;
const CAM_MIN = 1.2;
const CAM_MAX = 14;
const CAM_PITCH = 0.32;
const CAM_LERP = 10.0;
const CAM_WALL_GAP = 0.3;

const KEYS = {
  forward: ['KeyW', 'ArrowUp'],
  back: ['KeyS', 'ArrowDown'],
  left: ['KeyA', 'ArrowLeft'],
  right: ['KeyD', 'ArrowRight'],
  run: ['ShiftLeft', 'ShiftRight'],
  jump: ['Space'],
};

export class CharacterController {
  /**
   * @param character  Monigote (origen en los pies)
   * @param camera     PerspectiveCamera
   * @param dom        elemento que recibe el arrastre del ratón
   * @param ground     mallas caminables (TERRAIN_*, ROAD_*)
   * @param collider   FootprintCollider (muros de las mallas COL_)
   * @param walls      mallas COL_ para la colisión de la cámara
   */
  constructor({ character, camera, dom, ground, collider, walls }) {
    Object.assign(this, { character, camera, dom, ground, collider, walls });
    this.groundIndex = new GroundIndex(ground);
    this.enabled = true;
    this.velocity = new THREE.Vector3();
    this.verticalSpeed = 0;
    this.onGround = true;
    this.pressed = new Set();
    this.yaw = Math.PI; // cámara: rotación alrededor del personaje
    this.pitch = CAM_PITCH;
    this.distance = CAM_DISTANCE;
    this.currentDistance = CAM_DISTANCE;
    this.raycaster = new THREE.Raycaster();
    this.#bindInput();
  }

  #bindInput() {
    const all = new Set(Object.values(KEYS).flat());
    window.addEventListener('keydown', (e) => {
      if (!this.enabled || !all.has(e.code)) return;
      this.pressed.add(e.code);
      e.preventDefault();
    });
    window.addEventListener('keyup', (e) => this.pressed.delete(e.code));
    window.addEventListener('blur', () => this.pressed.clear());

    let dragging = false;
    this.dom.addEventListener('pointerdown', (e) => {
      if (!this.enabled) return;
      dragging = true;
      this.dom.setPointerCapture(e.pointerId);
    });
    this.dom.addEventListener('pointerup', () => (dragging = false));
    this.dom.addEventListener('pointermove', (e) => {
      if (!dragging || !this.enabled) return;
      this.yaw -= e.movementX * 0.005;
      this.pitch = THREE.MathUtils.clamp(this.pitch + e.movementY * 0.004, -0.15, 1.25);
    });
    this.dom.addEventListener('wheel', (e) => {
      if (!this.enabled) return;
      this.distance = THREE.MathUtils.clamp(this.distance * (1 + Math.sign(e.deltaY) * 0.12), CAM_MIN, CAM_MAX);
    }, { passive: true });
  }

  #down(action) {
    return KEYS[action].some((k) => this.pressed.has(k));
  }

  /** Altura del suelo bajo (x, z) por debajo de fromY, o null si no hay suelo (fuera del término municipal). */
  groundHeight(x, z, fromY = Infinity) {
    return this.groundIndex.heightAt(x, z, fromY);
  }

  /** Busca un punto de calle libre en espiral alrededor de `center` para colocar al personaje. */
  spawnNear(center) {
    const roads = this.ground.filter((m) => m.name.startsWith('ROAD_carriageway') || m.name.startsWith('ROAD_pedestrian'));
    const p = new THREE.Vector3();
    for (let r = 0; r < 400; r += 3) {
      for (let a = 0; a < Math.PI * 2; a += Math.max(0.2, 3 / Math.max(r, 1))) {
        p.set(center.x + Math.cos(a) * r, 300, center.z + Math.sin(a) * r); // relieve relativo: −29 … +36 m
        this.raycaster.set(p, new THREE.Vector3(0, -1, 0));
        this.raycaster.far = 600;
        const hit = this.raycaster.intersectObjects(roads, false)[0];
        if (!hit) continue;
        const probe = hit.point.clone();
        if (this.collider.resolve(probe.clone(), RADIUS * 3)) continue; // lejos de muros
        this.character.position.copy(hit.point);
        return hit.point;
      }
    }
    this.character.position.copy(center);
    return center;
  }

  update(dt) {
    dt = Math.min(dt, 0.05); // evita atravesar muros tras un parón
    const c = this.character;

    // Dirección deseada relativa a la cámara
    const input = new THREE.Vector2(
      (this.#down('right') ? 1 : 0) - (this.#down('left') ? 1 : 0),
      (this.#down('forward') ? 1 : 0) - (this.#down('back') ? 1 : 0),
    );
    const running = this.#down('run');
    const target = new THREE.Vector3();
    if (this.enabled && input.lengthSq() > 0) {
      input.normalize();
      const fwd = new THREE.Vector3(-Math.sin(this.yaw), 0, -Math.cos(this.yaw));
      const right = new THREE.Vector3(-fwd.z, 0, fwd.x);
      target.addScaledVector(fwd, input.y).addScaledVector(right, input.x).multiplyScalar(running ? RUN_SPEED : WALK_SPEED);
    }

    // Aceleración / deceleración hacia la velocidad deseada
    const diff = target.clone().sub(this.velocity);
    const rate = target.lengthSq() > 0 ? ACCEL : DECEL;
    const step = rate * dt;
    if (diff.length() <= step) this.velocity.copy(target);
    else this.velocity.addScaledVector(diff.normalize(), step);

    // Movimiento horizontal + colisión contra muros + límite del término (sin suelo no se avanza)
    const prev = c.position.clone();
    c.position.addScaledVector(this.velocity, dt);
    if (this.collider.resolve(c.position, RADIUS)) {
      // la velocidad conserva solo la componente que no empuja contra el muro
      const moved = c.position.clone().sub(prev).divideScalar(dt);
      if (moved.lengthSq() < this.velocity.lengthSq()) this.velocity.copy(moved.setY(0));
    }
    const floor = this.groundHeight(c.position.x, c.position.z, c.position.y + 2);
    if (floor === null) {
      c.position.x = prev.x;
      c.position.z = prev.z;
      this.velocity.set(0, 0, 0);
    }

    // Gravedad, salto y apoyo en el suelo
    if (this.enabled && this.onGround && this.#down('jump')) {
      this.verticalSpeed = JUMP_SPEED;
      this.onGround = false;
    }
    this.verticalSpeed -= GRAVITY * dt;
    c.position.y += this.verticalSpeed * dt;
    const groundY = floor ?? prev.y;
    if (c.position.y <= groundY) {
      c.position.y = groundY;
      this.verticalSpeed = 0;
      this.onGround = true;
    }

    // Giro suave hacia la dirección de marcha (el modelo mira a +Z)
    const speed = Math.hypot(this.velocity.x, this.velocity.z);
    if (speed > 0.2) {
      const desired = Math.atan2(this.velocity.x, this.velocity.z);
      let delta = desired - c.rotation.y;
      delta = Math.atan2(Math.sin(delta), Math.cos(delta));
      c.rotation.y += delta * (1 - Math.exp(-TURN_RATE * dt));
    }
    c.animate(dt, this.onGround ? speed : 0, THREE.MathUtils.clamp((speed - WALK_SPEED) / (RUN_SPEED - WALK_SPEED), 0, 1));

    if (this.enabled) this.#updateCamera(dt);
  }

  #updateCamera(dt) {
    const pivot = this.character.position.clone().add(new THREE.Vector3(0, EYE_HEIGHT, 0));
    const dir = new THREE.Vector3(
      Math.sin(this.yaw) * Math.cos(this.pitch),
      Math.sin(this.pitch),
      Math.cos(this.yaw) * Math.cos(this.pitch),
    );

    // La cámara no atraviesa muros: se acerca hasta el primer impacto entre el personaje y la posición deseada
    let allowed = this.distance;
    this.raycaster.set(pivot, dir);
    this.raycaster.far = this.distance + CAM_WALL_GAP;
    const hit = this.raycaster.intersectObjects(this.walls, false)[0];
    if (hit) allowed = Math.max(CAM_MIN * 0.5, hit.distance - CAM_WALL_GAP);
    // Acercarse al instante (evita ver a través del muro); alejarse con suavidad
    this.currentDistance = allowed < this.currentDistance
      ? allowed
      : THREE.MathUtils.lerp(this.currentDistance, allowed, 1 - Math.exp(-4 * dt));

    const desired = pivot.clone().addScaledVector(dir, this.currentDistance);
    const groundY = this.groundHeight(desired.x, desired.z, desired.y + 1);
    if (groundY !== null) desired.y = Math.max(desired.y, groundY + 0.3);
    this.camera.position.lerp(desired, hit ? 1 : 1 - Math.exp(-CAM_LERP * dt));
    this.camera.lookAt(pivot);
  }
}
