/**
 * Procedural generation of 5 large RGBA "decomposition" layers, entirely on
 * an OffscreenCanvas at runtime — no binary image assets are committed.
 *
 * Each layer is a handful of large soft-edged blobs (radial gradients) with
 * a few holes punched out (destination-out compositing) so the layers
 * visibly overlap *and* have transparent gaps that reveal whatever sits
 * underneath. That is the exact scenario the alpha hit-test in
 * SpikeStage.tsx needs in order to prove clicks pass through transparent
 * pixels to the layer beneath.
 */

export const LAYER_WIDTH = 4096;
export const LAYER_HEIGHT = 2304;

export interface GeneratedLayer {
  id: number;
  name: string;
  canvas: OffscreenCanvas;
}

interface ColorScheme {
  name: string;
  colors: Array<[number, number, number]>;
}

// Layer 0 is the near-opaque background; 1-4 stack on top, each with holes.
const COLOR_SCHEMES: ColorScheme[] = [
  {
    name: 'Ember (background)',
    colors: [
      [178, 58, 36],
      [214, 98, 44],
      [240, 146, 60],
      [120, 40, 30],
      [200, 80, 40],
    ],
  },
  {
    name: 'Glacier',
    colors: [
      [40, 110, 180],
      [60, 170, 210],
      [20, 70, 130],
      [100, 200, 220],
    ],
  },
  {
    name: 'Moss',
    colors: [
      [46, 120, 64],
      [92, 168, 74],
      [24, 84, 52],
      [150, 196, 90],
    ],
  },
  {
    name: 'Orchid',
    colors: [
      [142, 58, 160],
      [186, 90, 196],
      [100, 36, 120],
      [210, 140, 220],
    ],
  },
  {
    name: 'Solar (top)',
    colors: [
      [230, 178, 30],
      [250, 210, 80],
      [200, 130, 20],
      [255, 232, 140],
    ],
  },
];

/** Small deterministic PRNG so each layer's composition is stable across reloads. */
function mulberry32(seed: number): () => number {
  let a = seed;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function drawBlob(
  ctx: OffscreenCanvasRenderingContext2D,
  cx: number,
  cy: number,
  r: number,
  rgb: [number, number, number],
  coreAlpha: number,
  rx: number,
  ry: number
): void {
  ctx.save();
  ctx.translate(cx, cy);
  ctx.scale(rx, ry);
  const [red, green, blue] = rgb;
  const gradient = ctx.createRadialGradient(0, 0, 0, 0, 0, r);
  gradient.addColorStop(0, `rgba(${red},${green},${blue},${coreAlpha})`);
  gradient.addColorStop(0.65, `rgba(${red},${green},${blue},${coreAlpha * 0.55})`);
  gradient.addColorStop(1, `rgba(${red},${green},${blue},0)`);
  ctx.fillStyle = gradient;
  ctx.beginPath();
  ctx.arc(0, 0, r, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
}

function punchHole(ctx: OffscreenCanvasRenderingContext2D, cx: number, cy: number, r: number): void {
  ctx.save();
  ctx.globalCompositeOperation = 'destination-out';
  const gradient = ctx.createRadialGradient(cx, cy, 0, cx, cy, r);
  gradient.addColorStop(0, 'rgba(0,0,0,1)');
  gradient.addColorStop(0.7, 'rgba(0,0,0,0.85)');
  gradient.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = gradient;
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
}

/** Adds fine grain noise to RGB channels wherever alpha > 0; alpha itself is untouched. */
function addNoise(ctx: OffscreenCanvasRenderingContext2D, width: number, height: number, intensity: number): void {
  const imageData = ctx.getImageData(0, 0, width, height);
  const data = imageData.data;
  for (let i = 0; i < data.length; i += 4) {
    if (data[i + 3] === 0) continue;
    const n = (Math.random() - 0.5) * intensity;
    // Uint8ClampedArray clamps out-of-range values on assignment.
    data[i] += n;
    data[i + 1] += n;
    data[i + 2] += n;
  }
  ctx.putImageData(imageData, 0, 0);
}

function paintLayer(ctx: OffscreenCanvasRenderingContext2D, index: number, scheme: ColorScheme): void {
  const isBackground = index === 0;
  const rng = mulberry32(1000 + index * 977);
  const blobCount = isBackground ? 6 : 4;
  const marginX = LAYER_WIDTH * 0.08;
  const marginY = LAYER_HEIGHT * 0.08;
  const centers: Array<{ x: number; y: number; r: number }> = [];

  for (let b = 0; b < blobCount; b++) {
    const cx = marginX + rng() * (LAYER_WIDTH - marginX * 2);
    const cy = marginY + rng() * (LAYER_HEIGHT - marginY * 2);
    const r = isBackground
      ? LAYER_HEIGHT * (0.45 + rng() * 0.25)
      : LAYER_HEIGHT * (0.22 + rng() * 0.2);
    const color = scheme.colors[b % scheme.colors.length];
    const coreAlpha = isBackground ? 0.92 : 0.72 + rng() * 0.18;
    const rx = 0.8 + rng() * 0.4;
    const ry = 0.8 + rng() * 0.4;
    drawBlob(ctx, cx, cy, r, color, coreAlpha, rx, ry);
    centers.push({ x: cx, y: cy, r });
  }

  // Holes reveal whatever sits beneath — the scenario alpha hit-testing must handle.
  // The background layer stays solid so there is always something opaque at the bottom.
  if (!isBackground) {
    const holeCount = 2 + Math.floor(rng() * 2);
    for (let h = 0; h < holeCount; h++) {
      const base = centers[Math.floor(rng() * centers.length)];
      const hx = base.x + (rng() - 0.5) * base.r * 0.8;
      const hy = base.y + (rng() - 0.5) * base.r * 0.8;
      const hr = base.r * (0.25 + rng() * 0.25);
      punchHole(ctx, hx, hy, hr);
    }
  }

  addNoise(ctx, LAYER_WIDTH, LAYER_HEIGHT, isBackground ? 14 : 18);
}

function yieldToBrowser(): Promise<void> {
  return new Promise((resolve) => requestAnimationFrame(() => resolve()));
}

/**
 * Generates the 5 layers one at a time, yielding a frame between each so a
 * "generating..." progress UI can actually paint instead of the tab looking frozen.
 */
export async function generateLayers(
  onProgress?: (done: number, total: number) => void
): Promise<GeneratedLayer[]> {
  const layers: GeneratedLayer[] = [];
  for (let i = 0; i < COLOR_SCHEMES.length; i++) {
    const canvas = new OffscreenCanvas(LAYER_WIDTH, LAYER_HEIGHT);
    const ctx = canvas.getContext('2d');
    if (!ctx) {
      throw new Error('OffscreenCanvas 2D context is not available in this browser.');
    }
    paintLayer(ctx, i, COLOR_SCHEMES[i]);
    layers.push({ id: i, name: COLOR_SCHEMES[i].name, canvas });
    onProgress?.(i + 1, COLOR_SCHEMES.length);
    await yieldToBrowser();
  }
  return layers;
}
