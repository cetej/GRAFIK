import { useEffect, useRef, useState } from 'react';

/** Live FPS sampled from requestAnimationFrame ticks, refreshed about twice a second. */
export function useFpsCounter(active: boolean): number {
  const [fps, setFps] = useState(0);
  const frameCountRef = useRef(0);
  const windowStartRef = useRef(0);

  useEffect(() => {
    if (!active) return;

    let rafId = 0;
    let cancelled = false;
    frameCountRef.current = 0;
    windowStartRef.current = performance.now();

    function tick(now: number) {
      if (cancelled) return;
      frameCountRef.current += 1;
      const elapsed = now - windowStartRef.current;
      if (elapsed >= 500) {
        setFps(Math.round((frameCountRef.current * 1000) / elapsed));
        frameCountRef.current = 0;
        windowStartRef.current = now;
      }
      rafId = requestAnimationFrame(tick);
    }
    rafId = requestAnimationFrame(tick);

    return () => {
      cancelled = true;
      cancelAnimationFrame(rafId);
    };
  }, [active]);

  return fps;
}
