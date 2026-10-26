// Medidor de FPS para el HUD y benchmark reproducible (?bench=<segundos>).
// requestAnimationFrame está limitado por la frecuencia de refresco del monitor: 60 FPS en una pantalla
// de 60 Hz es el techo, no el rendimiento máximo de la GPU.

export class FpsMeter {
  constructor(windowMs = 500) {
    this.windowMs = windowMs;
    this.frames = 0;
    this.elapsed = 0;
    this.fps = 0;
    this.ms = 0;
  }

  tick(dtMs) {
    this.frames += 1;
    this.elapsed += dtMs;
    if (this.elapsed < this.windowMs) return false;
    this.fps = (this.frames * 1000) / this.elapsed;
    this.ms = this.elapsed / this.frames;
    this.frames = 0;
    this.elapsed = 0;
    return true;
  }
}

/**
 * Tiempo de GPU por fotograma con EXT_disjoint_timer_query_webgl2 (independiente del tope de refresco).
 * Los resultados llegan con unos fotogramas de retraso; si la extensión no existe, `available` es false.
 */
export class GpuTimer {
  constructor(gl) {
    this.gl = gl;
    this.ext = gl.getExtension('EXT_disjoint_timer_query_webgl2');
    this.pending = [];
    this.samples = [];
    this.active = null;
  }

  get available() {
    return Boolean(this.ext);
  }

  begin() {
    if (!this.ext || this.active) return;
    this.active = this.gl.createQuery();
    this.gl.beginQuery(this.ext.TIME_ELAPSED_EXT, this.active);
  }

  end() {
    if (!this.active) return;
    this.gl.endQuery(this.ext.TIME_ELAPSED_EXT);
    this.pending.push(this.active);
    this.active = null;
    this.#poll();
  }

  #poll() {
    const gl = this.gl;
    const disjoint = gl.getParameter(this.ext.GPU_DISJOINT_EXT);
    while (this.pending.length) {
      const q = this.pending[0];
      if (!gl.getQueryParameter(q, gl.QUERY_RESULT_AVAILABLE)) break;
      if (!disjoint) this.samples.push(gl.getQueryParameter(q, gl.QUERY_RESULT) / 1e6);
      gl.deleteQuery(q);
      this.pending.shift();
    }
  }

  summary() {
    if (!this.samples.length) return null;
    const ms = [...this.samples].sort((a, b) => a - b);
    const pct = (p) => +ms[Math.min(ms.length - 1, Math.floor((p / 100) * ms.length))].toFixed(3);
    return { gpu_samples: ms.length, gpu_ms_p50: pct(50), gpu_ms_p95: pct(95), gpu_ms_p99: pct(99) };
  }

  reset() {
    this.samples = [];
  }
}

export class Benchmark {
  constructor(durationS, warmupS = 2) {
    this.durationMs = durationS * 1000;
    this.warmupMs = warmupS * 1000;
    this.clock = 0;
    this.samples = [];
    this.result = null;
  }

  get running() {
    return this.result === null;
  }

  /** Progreso 0..1 del tramo medido (negativo durante el calentamiento). */
  get progress() {
    return (this.clock - this.warmupMs) / this.durationMs;
  }

  tick(dtMs) {
    if (!this.running) return;
    this.clock += dtMs;
    if (this.clock <= this.warmupMs) return;
    this.samples.push(dtMs);
    if (this.clock >= this.warmupMs + this.durationMs) this.result = this.#summarize();
  }

  #summarize() {
    const ms = [...this.samples].sort((a, b) => a - b);
    const pct = (p) => ms[Math.min(ms.length - 1, Math.floor((p / 100) * ms.length))];
    const total = ms.reduce((a, b) => a + b, 0);
    return {
      frames: ms.length,
      seconds: +(total / 1000).toFixed(2),
      fps_avg: +((ms.length * 1000) / total).toFixed(1),
      fps_1pct_low: +(1000 / pct(99)).toFixed(1),
      ms_p50: +pct(50).toFixed(2),
      ms_p95: +pct(95).toFixed(2),
      ms_p99: +pct(99).toFixed(2),
      ms_max: +ms[ms.length - 1].toFixed(2),
    };
  }
}
