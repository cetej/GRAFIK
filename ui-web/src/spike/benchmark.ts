/**
 * Automated performance benchmark for the Konva spike: idle redraw cost,
 * animated drag, animated transform, alpha hit-test cost, and memory.
 *
 * Framework-agnostic on purpose — SpikeStage.tsx supplies live Konva node
 * references and renders the returned results; this module only touches
 * Konva's imperative API plus a couple of reporting side effects
 * (console.log + window.__benchResults) that the task explicitly requires.
 */
import type Konva from 'konva';

export interface PhaseResult {
  name: string;
  durationMs: number;
  frameCount: number;
  avgFps: number;
  minFps: number;
}

export interface HitTestResult {
  calls: number;
  totalMs: number;
  avgMsPerCall: number;
}

export interface MemorySample {
  usedJSHeapSizeMB: number | null;
  totalJSHeapSizeMB: number | null;
  jsHeapSizeLimitMB: number | null;
}

export interface TheoreticalBitmapMemory {
  sourceCanvasesMB: number;
  cacheSceneCanvasesMB: number;
  cacheHitCanvasesMB: number;
  totalMB: number;
}

export interface MemoryResult {
  supported: boolean;
  before: MemorySample;
  after: MemorySample;
  deltaUsedMB: number | null;
  theoreticalBitmap: TheoreticalBitmapMemory;
}

export interface BenchResults {
  startedAt: string;
  userAgent: string;
  devicePixelRatio: number;
  stageSize: { width: number; height: number };
  layerSize: { width: number; height: number };
  layerCount: number;
  phases: {
    idle: PhaseResult;
    drag: PhaseResult;
    transform: PhaseResult;
  };
  hitTest: HitTestResult;
  memory: MemoryResult;
  notes: string[];
  totalElapsedMs: number;
}

export interface BenchContext {
  stage: Konva.Stage;
  layer: Konva.Layer;
  /** The topmost (last z-order) image node — animated by the drag/transform phases. */
  topNode: Konva.Image;
  layerWidth: number;
  layerHeight: number;
  layerCount: number;
}

declare global {
  interface Window {
    __benchResults?: BenchResults;
  }
}

interface PerformanceMemoryInfo {
  usedJSHeapSize: number;
  totalJSHeapSize: number;
  jsHeapSizeLimit: number;
}

interface PerformanceWithMemory extends Performance {
  memory?: PerformanceMemoryInfo;
}

const BYTES_PER_MB = 1024 * 1024;

function readMemory(): MemorySample {
  const memory = (performance as PerformanceWithMemory).memory;
  if (!memory) {
    return { usedJSHeapSizeMB: null, totalJSHeapSizeMB: null, jsHeapSizeLimitMB: null };
  }
  return {
    usedJSHeapSizeMB: memory.usedJSHeapSize / BYTES_PER_MB,
    totalJSHeapSizeMB: memory.totalJSHeapSize / BYTES_PER_MB,
    jsHeapSizeLimitMB: memory.jsHeapSizeLimit / BYTES_PER_MB,
  };
}

/**
 * Runs `onFrame` on every requestAnimationFrame tick for `durationMs` and
 * reports average / minimum instantaneous FPS (1000 / frame-delta) across the run.
 */
function runFramePhase(
  name: string,
  durationMs: number,
  onFrame: (elapsedMs: number) => void
): Promise<PhaseResult> {
  return new Promise((resolve) => {
    let frameCount = 0;
    let minFps = Infinity;
    let fpsSum = 0;
    let fpsSamples = 0;
    let lastTs: number | null = null;
    const start = performance.now();

    function tick(ts: number) {
      const elapsed = ts - start;
      const dt = lastTs === null ? 0 : ts - lastTs;
      lastTs = ts;
      onFrame(elapsed);
      frameCount += 1;
      if (dt > 0) {
        const fps = 1000 / dt;
        fpsSum += fps;
        fpsSamples += 1;
        if (fps < minFps) minFps = fps;
      }
      if (elapsed < durationMs) {
        requestAnimationFrame(tick);
      } else {
        resolve({
          name,
          durationMs: elapsed,
          frameCount,
          avgFps: fpsSamples > 0 ? fpsSum / fpsSamples : 0,
          minFps: Number.isFinite(minFps) ? minFps : 0,
        });
      }
    }
    requestAnimationFrame(tick);
  });
}

function runHitTestPhase(stage: Konva.Stage, calls: number): HitTestResult {
  const width = stage.width();
  const height = stage.height();
  const start = performance.now();
  for (let i = 0; i < calls; i++) {
    stage.getIntersection({ x: Math.random() * width, y: Math.random() * height });
  }
  const totalMs = performance.now() - start;
  return { calls, totalMs, avgMsPerCall: totalMs / calls };
}

export async function runBenchmark(ctx: BenchContext): Promise<BenchResults> {
  const startedAt = new Date().toISOString();
  const t0 = performance.now();
  const memoryBefore = readMemory();

  // Phase a: idle — nothing moves, but we force a redraw every frame to measure
  // raw draw-call throughput of the static 5-layer scene.
  const idle = await runFramePhase('idle', 3000, () => {
    ctx.layer.batchDraw();
  });

  // Phase b: drag — animate the top node's absolute position in a Lissajous-ish
  // path (independent x/y frequencies), simulating a user dragging it around.
  const dragStart = ctx.topNode.position();
  const drag = await runFramePhase('drag', 5000, (elapsed) => {
    const t = elapsed / 1000;
    ctx.topNode.position({
      x: dragStart.x + Math.sin(t * ((2 * Math.PI) / 1.6)) * 300,
      y: dragStart.y + Math.cos(t * ((2 * Math.PI) / 2.3)) * 300,
    });
    ctx.layer.batchDraw();
  });
  ctx.topNode.position(dragStart);
  ctx.layer.batchDraw();

  // Phase c: transform — animate scale 1 -> 1.3 -> 1 and rotation 0 -> 15deg -> 0.
  // The node's cache (built once in SpikeStage right after generation) is static:
  // scaling/rotating a cached node just re-transforms the existing cached bitmap,
  // so we deliberately do NOT call node.cache() again inside this loop.
  const baseScaleX = ctx.topNode.scaleX();
  const baseScaleY = ctx.topNode.scaleY();
  const baseRotation = ctx.topNode.rotation();
  const transform = await runFramePhase('transform', 5000, (elapsed) => {
    const phase = Math.sin((elapsed / 5000) * Math.PI); // 0 -> 1 -> 0 across the phase
    ctx.topNode.scaleX(baseScaleX * (1 + phase * 0.3));
    ctx.topNode.scaleY(baseScaleY * (1 + phase * 0.3));
    ctx.topNode.rotation(baseRotation + phase * 15);
    ctx.layer.batchDraw();
  });
  ctx.topNode.scaleX(baseScaleX);
  ctx.topNode.scaleY(baseScaleY);
  ctx.topNode.rotation(baseRotation);
  ctx.layer.batchDraw();

  // Phase d: hit-test — 300 random stage.getIntersection() lookups against the
  // shared hit canvas (the same structure alpha-aware click selection relies on).
  const hitTest = runHitTestPhase(ctx.stage, 300);

  // Phase e: memory.
  const memoryAfter = readMemory();
  const bytesPerCanvas = ctx.layerWidth * ctx.layerHeight * 4; // RGBA8
  const perCategoryMB = (ctx.layerCount * bytesPerCanvas) / BYTES_PER_MB;
  const theoreticalBitmap: TheoreticalBitmapMemory = {
    sourceCanvasesMB: perCategoryMB,
    cacheSceneCanvasesMB: perCategoryMB,
    cacheHitCanvasesMB: perCategoryMB,
    totalMB: perCategoryMB * 3,
  };

  const totalElapsedMs = performance.now() - t0;

  const results: BenchResults = {
    startedAt,
    userAgent: navigator.userAgent,
    devicePixelRatio: window.devicePixelRatio,
    stageSize: { width: ctx.stage.width(), height: ctx.stage.height() },
    layerSize: { width: ctx.layerWidth, height: ctx.layerHeight },
    layerCount: ctx.layerCount,
    phases: { idle, drag, transform },
    hitTest,
    memory: {
      supported: memoryBefore.usedJSHeapSizeMB !== null,
      before: memoryBefore,
      after: memoryAfter,
      deltaUsedMB:
        memoryBefore.usedJSHeapSizeMB !== null && memoryAfter.usedJSHeapSizeMB !== null
          ? memoryAfter.usedJSHeapSizeMB - memoryBefore.usedJSHeapSizeMB
          : null,
      theoreticalBitmap,
    },
    notes: [
      'Nodes are cached once (node.cache({pixelRatio:1}) + node.drawHitFromCache(0)) right after generation, before the benchmark starts; the transform phase never re-caches, it only re-transforms the existing cached bitmap.',
      'cache({pixelRatio:1}) is forced explicitly (Konva otherwise defaults the scene cache canvas to devicePixelRatio) so theoreticalBitmap stays comparable across displays.',
      'Memory before/after are snapshots at the very start and very end of the whole benchmark run, not per-phase.',
      'All *MB figures are MiB (bytes / 1024^2).',
      'performance.memory is a non-standard Chromium-only API; memory fields are null when it is unavailable.',
    ],
    totalElapsedMs,
  };

  window.__benchResults = results;
  console.log('BENCH_RESULTS ' + JSON.stringify(results));

  return results;
}
