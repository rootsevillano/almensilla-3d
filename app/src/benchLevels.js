// Benchmark de niveles de calidad (agente 04): `?benchlevels` mide el tiempo de GPU de cada nivel (alta, media,
// baja) en órbita y a pie, renderizando fotogramas a un lienzo fijo de 1920×1080 con DPR 1 (pantalla 1080p típica),
// independiente del tamaño de la ventana y del tope de refresco. Resultado en `window.__benchLevels` y en consola.
const PIXEL_RATIO = { high: 1.0, medium: 1.0, low: 0.75 };
const FRAMES = 360;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const pct = (arr, p) => +[...arr].sort((a, b) => a - b)[Math.min(arr.length - 1, Math.floor(p * arr.length))].toFixed(2);

async function measure(A, step) {
  const { renderer: R, camera: cam, gpu, scene } = A;
  gpu.reset();
  const cpu = [];
  for (let i = 0; i < FRAMES; i++) {
    step(i);
    A.lod?.update(cam);
    A.ortho?.update(cam);
    const t = performance.now();
    gpu.begin();
    R.render(scene, cam);
    gpu.end();
    cpu.push(performance.now() - t);
    if (i % 15 === 0) await sleep(0);
  }
  for (let k = 0; k < 40 && gpu.samples.length < FRAMES * 0.85; k++) { // resultados de GPU con retraso
    await sleep(25);
    gpu.begin();
    R.render(scene, cam);
    gpu.end();
  }
  const g = gpu.samples;
  return {
    gpu_ms_p50: g.length ? pct(g, 0.5) : null, gpu_ms_p95: g.length ? pct(g, 0.95) : null,
    cpu_submit_ms_p50: pct(cpu, 0.5), calls: R.info.render.calls, triangles: R.info.render.triangles,
    canvas: `${R.domElement.width}x${R.domElement.height}`,
  };
}

export async function runLevelBenchmark(A) {
  const { renderer: R, camera: cam, quality: Q, player: P, character: C, center: c0 } = A;
  const setSize = R.setSize.bind(R);
  const setPixelRatio = R.setPixelRatio.bind(R);
  R.setSize = () => {}; // que ningún redimensionado de la ventana cambie el lienzo durante la medida
  R.setPixelRatio = () => {};
  A.pauseLoop?.(); // sin el bucle del visor: solo cuentan los fotogramas del benchmark
  const gl = R.getContext();
  const info = gl.getExtension('WEBGL_debug_renderer_info');
  const result = {
    gpu: info ? gl.getParameter(info.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER),
    gpu_timer: A.gpu.available, levels: {},
  };
  try {
    for (const level of ['high', 'medium', 'low']) {
      Q.auto = false;
      Q.apply(level, 'benchlevels');
      setPixelRatio(PIXEL_RATIO[level]);
      setSize(1920, 1080, false);
      cam.aspect = 1920 / 1080;
      cam.near = 1;
      cam.updateProjectionMatrix();
      const orbit = await measure(A, (i) => {
        const a = (i / FRAMES) * Math.PI * 2;
        cam.position.set(c0.x + Math.cos(a) * 900, 420, c0.z + Math.sin(a) * 900);
        cam.lookAt(c0);
        A.shadows?.update(c0, 1000);
      });
      let walk = null;
      if (P) {
        cam.near = 0.2;
        cam.updateProjectionMatrix();
        P.spawnNear(c0);
        P.velocity.set(0, 0, 0);
        P.enabled = true;
        P.pressed.add('KeyW');
        for (let i = 0; i < 120; i++) { P.update(1 / 60); A.ortho?.update(cam); }
        await sleep(2000); // texturas de ortofoto en alta
        walk = await measure(A, () => {
          P.yaw += 0.01;
          P.update(1 / 60);
          A.shadows?.update(C.position, cam.position.distanceTo(C.position));
        });
        P.pressed.clear();
      }
      result.levels[level] = { orbit, walk };
    }
  } finally {
    R.setSize = setSize;
    R.setPixelRatio = setPixelRatio;
    Q.auto = true;
    Q.apply('high', 'fin de benchlevels');
    cam.aspect = window.innerWidth / window.innerHeight;
    cam.updateProjectionMatrix();
    A.resumeLoop?.();
  }
  window.__benchLevels = result;
  console.log('[benchlevels]', JSON.stringify(result));
  return result;
}
