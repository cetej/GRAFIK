import { useEffect, useMemo, useRef, useState } from 'react';
import type Konva from 'konva';
import { Stage, Layer, Image as KonvaImage, Transformer } from 'react-konva';
import { generateLayers, LAYER_WIDTH, LAYER_HEIGHT, type GeneratedLayer } from './layerGenerator';
import { runBenchmark, type BenchResults } from './benchmark';
import { useFpsCounter } from './useFpsCounter';

type BenchStatus = 'pending' | 'running' | 'done';

export default function SpikeStage() {
  const [layers, setLayers] = useState<GeneratedLayer[] | null>(null);
  const [progress, setProgress] = useState({ done: 0, total: 5 });
  const [ready, setReady] = useState(false);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [benchStatus, setBenchStatus] = useState<BenchStatus>('pending');
  const [benchResults, setBenchResults] = useState<BenchResults | null>(null);

  const stageRef = useRef<Konva.Stage | null>(null);
  const layerRef = useRef<Konva.Layer | null>(null);
  const transformerRef = useRef<Konva.Transformer | null>(null);
  const imageNodeRefs = useRef<Array<Konva.Image | null>>([]);
  const cachedOnceRef = useRef(false);

  // Captured once at load — this spike does not re-fit on window resize.
  const stageWidth = window.innerWidth;
  const stageHeight = window.innerHeight;

  const { scale, offsetX, offsetY } = useMemo(() => {
    const s = Math.min(stageWidth / LAYER_WIDTH, stageHeight / LAYER_HEIGHT) * 0.92;
    return {
      scale: s,
      offsetX: (stageWidth - LAYER_WIDTH * s) / 2,
      offsetY: (stageHeight - LAYER_HEIGHT * s) / 2,
    };
  }, [stageWidth, stageHeight]);

  const fps = useFpsCounter(ready);

  // Generate the 5 procedural layers once, on mount.
  useEffect(() => {
    generateLayers((done, total) => setProgress({ done, total })).then(setLayers);
  }, []);

  // Once every Image node has mounted, cache each one exactly once so clicks
  // hit-test against alpha (transparent pixels) instead of the bounding box.
  useEffect(() => {
    if (!layers || cachedOnceRef.current) return;
    cachedOnceRef.current = true;
    for (const node of imageNodeRefs.current) {
      if (!node) continue;
      node.cache({ pixelRatio: 1 });
      node.drawHitFromCache(0);
    }
    layerRef.current?.batchDraw();
    setReady(true);
  }, [layers]);

  // Auto-run the benchmark ~1s after the layers are ready and cached.
  useEffect(() => {
    if (!ready || !layers) return;
    const stage = stageRef.current;
    const layer = layerRef.current;
    const topNode = imageNodeRefs.current[layers.length - 1];
    if (!stage || !layer || !topNode) return;

    const timer = window.setTimeout(() => {
      setBenchStatus('running');
      runBenchmark({
        stage,
        layer,
        topNode,
        layerWidth: LAYER_WIDTH,
        layerHeight: LAYER_HEIGHT,
        layerCount: layers.length,
      }).then((results) => {
        setBenchResults(results);
        setBenchStatus('done');
      });
    }, 1000);

    return () => window.clearTimeout(timer);
  }, [ready, layers]);

  // Keep the Transformer attached to whichever node is currently selected.
  useEffect(() => {
    const tr = transformerRef.current;
    if (!tr) return;
    const node = selectedId !== null ? imageNodeRefs.current[selectedId] : null;
    tr.nodes(node ? [node] : []);
    tr.getLayer()?.batchDraw();
  }, [selectedId]);

  function handleStageDeselect(e: Konva.KonvaEventObject<MouseEvent | TouchEvent>) {
    if (e.target === stageRef.current) {
      setSelectedId(null);
    }
  }

  return (
    <div className="spike-root">
      <div className="panel panel-top-left">
        <h1>GRAFIK Konva Spike</h1>
        <p>
          5 layers, 4096x2304 RGBA each. Alpha hit-test via node.cache() +
          drawHitFromCache(0): clicks pass through transparent holes to the layer
          underneath. Drag to move, use the handles to resize/rotate, click empty
          space to deselect.
        </p>
        {!ready && (
          <p className="status">
            Generating layers... ({progress.done}/{progress.total})
          </p>
        )}
        {ready && benchStatus !== 'done' && (
          <p className="status">
            {benchStatus === 'pending' ? 'Benchmark starting shortly...' : 'Benchmark running...'}
          </p>
        )}
      </div>

      <div className="panel panel-top-right">
        <div className="fps">{ready ? `${fps} FPS` : '--'}</div>
      </div>

      {benchResults && (
        <div className="panel panel-results">
          <h2>Benchmark results</h2>
          <pre id="bench-results">{JSON.stringify(benchResults, null, 2)}</pre>
        </div>
      )}

      <Stage
        ref={stageRef}
        width={stageWidth}
        height={stageHeight}
        className="spike-stage"
        onMouseDown={handleStageDeselect}
        onTouchStart={handleStageDeselect}
      >
        <Layer ref={layerRef}>
          {layers?.map((genLayer, i) => (
            <KonvaImage
              key={genLayer.id}
              ref={(node) => {
                imageNodeRefs.current[i] = node;
              }}
              image={genLayer.canvas}
              x={offsetX}
              y={offsetY}
              width={LAYER_WIDTH}
              height={LAYER_HEIGHT}
              scaleX={scale}
              scaleY={scale}
              draggable
              onClick={() => setSelectedId(genLayer.id)}
              onTap={() => setSelectedId(genLayer.id)}
            />
          ))}
          <Transformer ref={transformerRef} resizeEnabled rotateEnabled />
        </Layer>
      </Stage>
    </div>
  );
}
