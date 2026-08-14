import { useRef, useState } from 'react';
import type { Tool } from './types';

interface ToolbarProps {
  tool: Tool;
  onToolChange: (tool: Tool) => void;
  busy: boolean;

  canUndo: boolean;
  canRedo: boolean;
  onUndo: () => void;
  onRedo: () => void;

  canInpaintBehind: boolean;
  onInpaintBehind: () => void;

  canExport: boolean;
  onExportPng: () => void;

  onNewFromImage: (file: File, numLayers: number) => void;

  brushSize: number;
  onBrushSizeChange: (size: number) => void;
  brushStrokeCount: number;
  onBrushClear: () => void;
}

const TOOLS: { id: Tool; label: string; title: string }[] = [
  { id: 'select', label: 'Select', title: 'Select / move / transform layers' },
  { id: 'brush', label: 'Brush', title: 'Paint a mask for AI edit' },
  { id: 'segment', label: 'Segment', title: 'Segment mode — canvas dragging disabled' },
];

const NUM_LAYER_OPTIONS = [2, 3, 4, 5, 6, 7, 8];

export default function Toolbar(props: ToolbarProps) {
  const {
    tool,
    onToolChange,
    busy,
    canUndo,
    canRedo,
    onUndo,
    onRedo,
    canInpaintBehind,
    onInpaintBehind,
    canExport,
    onExportPng,
    onNewFromImage,
    brushSize,
    onBrushSizeChange,
    brushStrokeCount,
    onBrushClear,
  } = props;

  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [numLayers, setNumLayers] = useState(4);

  return (
    <div className="editor-toolbar">
      <div className="toolbar-group" role="group" aria-label="Tools">
        {TOOLS.map((t) => (
          <button
            key={t.id}
            type="button"
            className={`tool-btn${tool === t.id ? ' active' : ''}`}
            disabled={busy}
            title={t.title}
            onClick={() => onToolChange(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tool === 'brush' && (
        <div className="toolbar-group brush-controls">
          <label className="brush-size-label">
            Size
            <input
              type="range"
              min={4}
              max={200}
              value={brushSize}
              disabled={busy}
              onChange={(e) => onBrushSizeChange(Number(e.target.value))}
            />
            <span>{brushSize}px</span>
          </label>
          <button type="button" disabled={busy || brushStrokeCount === 0} onClick={onBrushClear}>
            Clear ({brushStrokeCount})
          </button>
        </div>
      )}

      <div className="toolbar-spacer" />

      <div className="toolbar-group">
        <button type="button" disabled={busy || !canUndo} onClick={onUndo} title="Undo">
          Undo
        </button>
        <button type="button" disabled={busy || !canRedo} onClick={onRedo} title="Redo">
          Redo
        </button>
        <button
          type="button"
          disabled={busy || !canInpaintBehind}
          onClick={onInpaintBehind}
          title="Inpaint the background behind the selected layer"
        >
          Inpaint behind
        </button>
        <button type="button" disabled={busy || !canExport} onClick={onExportPng} title="Export composite as PNG">
          Export PNG
        </button>
      </div>

      <div className="toolbar-group">
        <select
          value={numLayers}
          disabled={busy}
          onChange={(e) => setNumLayers(Number(e.target.value))}
          title="Number of layers to decompose into"
        >
          {NUM_LAYER_OPTIONS.map((n) => (
            <option key={n} value={n}>
              {n} layers
            </option>
          ))}
        </select>
        <button type="button" disabled={busy} onClick={() => fileInputRef.current?.click()}>
          New from image
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          className="hidden-file-input"
          onChange={(e) => {
            const file = e.target.files?.[0] ?? null;
            e.target.value = '';
            if (file) onNewFromImage(file, numLayers);
          }}
        />
      </div>
    </div>
  );
}
