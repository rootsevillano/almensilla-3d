// Niveles de calidad (agente 02) y modo automático para equipos modestos (criterio QA 2 del agente 04: ≥60 FPS).
// Todo se ajusta en caliente: resolución de dibujo, sombra del sol, distancias de LOD, ortofoto en alta y alcance.
//
// `?quality=auto` (por defecto) empieza en alta y baja un nivel si durante EVAL_S segundos el 75 % de los fotogramas
// tarda más de SLOW_FRAME_MS o la GPU pasa de SLOW_GPU_MS; sube uno si lleva UPGRADE_AFTER_S con mucho margen.
// Los umbrales de bajada y subida están muy separados para que no oscile.
export const LEVELS = ['high', 'medium', 'low'];
const LABELS = { high: 'alta', medium: 'media', low: 'baja' };

const PRESETS = {
  high: { pixelRatio: null, shadows: true, shadowMap: 2048, lod: 1.0, treeShadows: true, orthoHi: true, fogFar: 3600, far: 8000 },
  // media: sin sombras pero a resolución completa (con sombras y mapa de 1024 apenas mejoraba a la alta con DPR 1)
  medium: { pixelRatio: 1.0, shadows: false, shadowMap: 1024, lod: 0.6, treeShadows: false, orthoHi: true, fogFar: 3000, far: 4000 },
  low: { pixelRatio: 0.75, shadows: false, shadowMap: 1024, lod: 0.45, treeShadows: false, orthoHi: false, fogFar: 2400, far: 2600 },
};

const WARMUP_S = 3;
const EVAL_S = 3;
const SLOW_FRAME_MS = 1000 / 50; // por debajo de 50 FPS sostenidos: bajar
const SLOW_GPU_MS = 15;
const FAST_GPU_MS = 5; // con mucho margen: se puede intentar subir
const FAST_FRAME_MS = 1000 / 70;
const UPGRADE_AFTER_S = 15;

const pct = (arr, p) => {
  const s = [...arr].sort((a, b) => a - b);
  return s[Math.min(s.length - 1, Math.floor(p * s.length))];
};

export class QualityManager {
  constructor({ renderer, scene, camera, shadows, lod, ortho, mode = 'auto' }) {
    Object.assign(this, { renderer, scene, camera, shadows, lod, ortho });
    this.auto = mode === 'auto';
    this.level = LEVELS.includes(mode) ? mode : 'high';
    this.frames = [];
    this.gpu = [];
    this.clock = -WARMUP_S;
    this.sinceChange = 0;
    this.history = [];
    window.addEventListener('resize', () => this.#applyPixelRatio());
    this.apply(this.level, 'inicio');
  }

  get label() {
    return `${LABELS[this.level]}${this.auto ? ' (auto)' : ''}`;
  }

  #applyPixelRatio() {
    const p = PRESETS[this.level];
    this.renderer.setPixelRatio(p.pixelRatio ?? Math.min(window.devicePixelRatio, 2));
    this.renderer.setSize(window.innerWidth, window.innerHeight, false);
  }

  apply(level, reason = 'manual') {
    const p = PRESETS[level];
    this.level = level;
    this.#applyPixelRatio();
    if (this.shadows) {
      this.shadows.setEnabled(p.shadows);
      this.shadows.setMapSize(p.shadowMap);
    }
    if (this.lod) {
      this.lod.distanceScale = p.lod;
      this.lod.treeShadows = p.treeShadows && p.shadows;
    }
    if (this.ortho) this.ortho.hiEnabled = p.orthoHi;
    if (this.scene.fog) this.scene.fog.far = p.fogFar;
    this.camera.far = p.far;
    this.camera.updateProjectionMatrix();
    this.history.push({ t: +performance.now().toFixed(0), level, reason });
    this.frames = [];
    this.gpu = [];
    this.sinceChange = 0;
  }

  /** Llamar una vez por fotograma con su duración (ms) y el último tiempo de GPU medido (ms, o null). */
  update(dtMs, gpuMs) {
    if (!this.auto || document.hidden || dtMs > 250) return; // página oculta o parón: no cuenta
    this.clock += dtMs / 1000;
    this.sinceChange += dtMs / 1000;
    if (this.clock < 0) return; // calentamiento: carga de texturas y compilación de shaders
    this.frames.push(dtMs);
    if (gpuMs != null) this.gpu.push(gpuMs);
    if (this.sinceChange < EVAL_S) return;

    const frame75 = pct(this.frames, 0.75);
    const gpu50 = this.gpu.length ? pct(this.gpu, 0.5) : null;
    const index = LEVELS.indexOf(this.level);
    if ((frame75 > SLOW_FRAME_MS || (gpu50 != null && gpu50 > SLOW_GPU_MS)) && index < LEVELS.length - 1) {
      this.apply(LEVELS[index + 1], `lento: 75 % de fotogramas ${frame75.toFixed(1)} ms, GPU ${gpu50?.toFixed(1) ?? 'n/d'} ms`);
    } else if (index > 0 && this.sinceChange > UPGRADE_AFTER_S && frame75 < FAST_FRAME_MS
               && gpu50 != null && gpu50 < FAST_GPU_MS) {
      this.apply(LEVELS[index - 1], `margen: GPU ${gpu50.toFixed(1)} ms`);
    } else if (this.frames.length > 600) {
      this.frames = this.frames.slice(-300); // ventana deslizante
      this.gpu = this.gpu.slice(-300);
    }
  }
}
