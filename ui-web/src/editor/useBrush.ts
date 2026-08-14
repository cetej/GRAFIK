import { useCallback, useEffect, useRef, useState } from 'react';
import type { CanvasPoint } from './types';

const DEFAULT_BRUSH_SIZE = 24;
const MIN_BRUSH_SIZE = 4;
const MAX_BRUSH_SIZE = 200;
const BRUSH_COLOR = '#ff0000';

export interface UseBrushResult {
  /** Full-resolution offscreen canvas (project canvas size), or null until that size is known. */
  canvas: HTMLCanvasElement | null;
  strokeCount: number;
  isEmpty: boolean;
  brushSize: number;
  setBrushSize: (size: number) => void;
  clear: () => void;
  beginStroke: (pt: CanvasPoint) => void;
  continueStroke: (pt: CanvasPoint) => void;
  endStroke: () => void;
  /** Black background, white where the brush painted (alpha > 0). Base64 PNG, no data-url prefix. Null if there's no canvas. */
  exportMaskB64: () => string | null;
}

/**
 * Full-resolution offscreen mask-brush canvas, in project-canvas coordinates
 * (not screen pixels) — callers convert pointer positions via
 * `(screenX - offsetX) / fitScale` before calling begin/continueStroke.
 *
 * `onDraw` fires after every pixel change so the caller can batchDraw() the
 * Konva layer hosting the overlay <Image>: mutating the canvas in place
 * doesn't itself trigger a Konva repaint.
 *
 * `resetKey` (typically the selected project id) forces the canvas to be
 * recreated even if width/height happen to match the previous project —
 * otherwise a same-size project swap would leave the old project's mask
 * visible on the new one.
 */
export function useBrush(
  canvasWidth: number,
  canvasHeight: number,
  resetKey: string | null,
  onDraw: () => void,
): UseBrushResult {
  const [canvas, setCanvas] = useState<HTMLCanvasElement | null>(null);
  const [strokeCount, setStrokeCount] = useState(0);
  const [brushSize, setBrushSizeState] = useState(DEFAULT_BRUSH_SIZE);
  const drawingRef = useRef(false);
  const lastPtRef = useRef<CanvasPoint | null>(null);

  useEffect(() => {
    drawingRef.current = false;
    lastPtRef.current = null;
    if (!canvasWidth || !canvasHeight) {
      setCanvas(null);
      setStrokeCount(0);
      return;
    }
    const el = document.createElement('canvas');
    el.width = canvasWidth;
    el.height = canvasHeight;
    setCanvas(el);
    setStrokeCount(0);
  }, [canvasWidth, canvasHeight, resetKey]);

  const setBrushSize = useCallback((size: number) => {
    setBrushSizeState(Math.min(MAX_BRUSH_SIZE, Math.max(MIN_BRUSH_SIZE, Math.round(size))));
  }, []);

  const clear = useCallback(() => {
    if (!canvas) return;
    canvas.getContext('2d')?.clearRect(0, 0, canvas.width, canvas.height);
    drawingRef.current = false;
    lastPtRef.current = null;
    setStrokeCount(0);
    onDraw();
  }, [canvas, onDraw]);

  const beginStroke = useCallback(
    (pt: CanvasPoint) => {
      const ctx = canvas?.getContext('2d');
      if (!ctx) return;
      drawingRef.current = true;
      lastPtRef.current = pt;
      // Paint a dot immediately so a plain click (no drag) still marks a spot.
      ctx.fillStyle = BRUSH_COLOR;
      ctx.beginPath();
      ctx.arc(pt.x, pt.y, brushSize / 2, 0, Math.PI * 2);
      ctx.fill();
      setStrokeCount((n) => n + 1);
      onDraw();
    },
    [canvas, brushSize, onDraw],
  );

  const continueStroke = useCallback(
    (pt: CanvasPoint) => {
      const ctx = canvas?.getContext('2d');
      if (!ctx || !drawingRef.current || !lastPtRef.current) return;
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      ctx.strokeStyle = BRUSH_COLOR;
      ctx.lineWidth = brushSize;
      ctx.beginPath();
      ctx.moveTo(lastPtRef.current.x, lastPtRef.current.y);
      ctx.lineTo(pt.x, pt.y);
      ctx.stroke();
      lastPtRef.current = pt;
      onDraw();
    },
    [canvas, brushSize, onDraw],
  );

  const endStroke = useCallback(() => {
    drawingRef.current = false;
    lastPtRef.current = null;
  }, []);

  const exportMaskB64 = useCallback((): string | null => {
    if (!canvas) return null;
    const srcCtx = canvas.getContext('2d');
    if (!srcCtx) return null;
    const { width, height } = canvas;
    const src = srcCtx.getImageData(0, 0, width, height);

    const maskCanvas = document.createElement('canvas');
    maskCanvas.width = width;
    maskCanvas.height = height;
    const maskCtx = maskCanvas.getContext('2d');
    if (!maskCtx) return null;
    maskCtx.fillStyle = '#000000';
    maskCtx.fillRect(0, 0, width, height);
    const dst = maskCtx.getImageData(0, 0, width, height);
    for (let i = 0; i < src.data.length; i += 4) {
      if (src.data[i + 3] > 0) {
        dst.data[i] = 255;
        dst.data[i + 1] = 255;
        dst.data[i + 2] = 255;
        dst.data[i + 3] = 255;
      }
    }
    maskCtx.putImageData(dst, 0, 0);
    const dataUrl = maskCanvas.toDataURL('image/png');
    const comma = dataUrl.indexOf(',');
    return comma >= 0 ? dataUrl.slice(comma + 1) : null;
  }, [canvas]);

  return {
    canvas,
    strokeCount,
    isEmpty: strokeCount === 0,
    brushSize,
    setBrushSize,
    clear,
    beginStroke,
    continueStroke,
    endStroke,
    exportMaskB64,
  };
}
