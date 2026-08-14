import { Arrow, Circle } from 'react-konva';
import type { LayerResponse } from './api';
import type { CanvasPoint } from './types';

const SELECTED_COLOR = '#4a7dff';
const OTHER_COLOR = '#888';

interface TrajectoryOverlayProps {
  /** All layers of the current project (only those with motion.trajectory get an Arrow drawn). */
  layers: LayerResponse[];
  selectedLayerId: string | null;
  fitScale: number;
  canvasWidth: number;
  canvasHeight: number;
  busy: boolean;
  /** Fired continuously while dragging an anchor — caller should update local state only (no persist). */
  onPointDragMove: (layer: LayerResponse, index: number, point: CanvasPoint) => void;
  /** Fired once the drag ends — caller should persist the layer's motion here. */
  onPointDragEnd: (layer: LayerResponse) => void;
}

function clamp(value: number, max: number): number {
  return Math.max(0, Math.min(max, value));
}

/**
 * Renders one motion-direction Arrow per layer that has trajectory points (dimmed for
 * non-selected layers), plus draggable anchor Circles for the currently selected layer only.
 * Only mounted by EditorApp while tool === 'motion'.
 */
export default function TrajectoryOverlay(props: TrajectoryOverlayProps) {
  const { layers, selectedLayerId, fitScale, canvasWidth, canvasHeight, busy, onPointDragMove, onPointDragEnd } =
    props;
  // Visual sizes are divided by fitScale so they stay a constant screen size regardless of zoom
  // (same trick the canvas-border Rect and Transformer use elsewhere in EditorApp).
  const scale = fitScale > 0 ? fitScale : 1;
  const selectedLayer = layers.find((l) => l.id === selectedLayerId) ?? null;
  const selectedTrajectory = selectedLayer?.motion?.trajectory ?? [];

  return (
    <>
      {layers.map((layer) => {
        const trajectory = layer.motion?.trajectory ?? [];
        if (trajectory.length < 2) return null;
        const selected = layer.id === selectedLayerId;
        const color = selected ? SELECTED_COLOR : OTHER_COLOR;
        return (
          <Arrow
            key={`traj-${layer.id}`}
            points={trajectory.flatMap((p) => [p.x, p.y])}
            tension={0.5}
            stroke={color}
            fill={color}
            strokeWidth={2 / scale}
            pointerLength={12 / scale}
            pointerWidth={12 / scale}
            listening={false}
          />
        );
      })}
      {selectedLayer &&
        selectedTrajectory.map((pt, index) => (
          <Circle
            key={`anchor-${selectedLayer.id}-${index}`}
            x={pt.x}
            y={pt.y}
            radius={6 / scale}
            fill="#ffffff"
            stroke={SELECTED_COLOR}
            strokeWidth={2 / scale}
            draggable={!busy}
            onDragMove={(e) => {
              const node = e.target;
              const x = clamp(Math.round(node.x()), canvasWidth);
              const y = clamp(Math.round(node.y()), canvasHeight);
              node.position({ x, y });
              onPointDragMove(selectedLayer, index, { x, y });
            }}
            onDragEnd={() => onPointDragEnd(selectedLayer)}
          />
        ))}
    </>
  );
}
