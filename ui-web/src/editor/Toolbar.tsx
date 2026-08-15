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

  /** Decompose target layer count lives in EditorApp (shared with canvas drag&drop). */
  numLayers: number;
  onNumLayersChange: (n: number) => void;
  /** Opens the shared hidden file input owned by EditorApp. */
  onNewFromImageClick: () => void;

  brushSize: number;
  onBrushSizeChange: (size: number) => void;
  brushStrokeCount: number;
  onBrushClear: () => void;
}

const TOOLS: { id: Tool; label: string; title: string }[] = [
  { id: 'select', label: 'Výběr', title: 'Výběr, posun a transformace vrstev' },
  { id: 'brush', label: 'Štětec', title: 'Malování masky pro AI úpravu' },
  { id: 'segment', label: 'Segmentace', title: 'Kliknutím na prvek v obraze vznikne nová vrstva (SAM)' },
  { id: 'motion', label: 'Pohyb', title: 'Trajektorie pohybu prvků + kamera' },
];

const NUM_LAYER_OPTIONS = [2, 3, 4, 5, 6, 7, 8];

/** Czech plural for "vrstva" after a numeral: 2-4 vrstvy, 5+ vrstev. */
export function vrstvyWord(n: number): string {
  return n >= 2 && n <= 4 ? 'vrstvy' : 'vrstev';
}

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
    numLayers,
    onNumLayersChange,
    onNewFromImageClick,
    brushSize,
    onBrushSizeChange,
    brushStrokeCount,
    onBrushClear,
  } = props;

  return (
    <div className="editor-toolbar">
      <div className="toolbar-group" role="group" aria-label="Nástroje">
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
            Velikost
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
          <button
            type="button"
            disabled={busy || brushStrokeCount === 0}
            onClick={onBrushClear}
            title="Smaže nakreslenou masku"
          >
            Smazat ({brushStrokeCount})
          </button>
        </div>
      )}

      <div className="toolbar-spacer" />

      <div className="toolbar-group">
        <button type="button" disabled={busy || !canUndo} onClick={onUndo} title="Vrátí poslední akci zpět">
          Zpět
        </button>
        <button type="button" disabled={busy || !canRedo} onClick={onRedo} title="Provede vrácenou akci znovu">
          Znovu
        </button>
        <button
          type="button"
          disabled={busy || !canInpaintBehind}
          onClick={onInpaintBehind}
          title="Vyplní pozadí za vybranou vrstvou (AI inpaint)"
        >
          Vyplnit pozadí
        </button>
        <button
          type="button"
          disabled={busy || !canExport}
          onClick={onExportPng}
          title="Uloží kompozit jako PNG"
        >
          Export PNG
        </button>
      </div>

      <div className="toolbar-group">
        <label className="toolbar-label" title="Na kolik vrstev se nahraný obrázek rozloží">
          Rozložit na
          <select
            value={numLayers}
            disabled={busy}
            onChange={(e) => onNumLayersChange(Number(e.target.value))}
          >
            {NUM_LAYER_OPTIONS.map((n) => (
              <option key={n} value={n}>
                {n} {vrstvyWord(n)}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="primary-btn"
          disabled={busy}
          onClick={onNewFromImageClick}
          title="Nahraje obrázek a rozloží ho na vrstvy (nový projekt)"
        >
          Nový z obrázku
        </button>
      </div>
    </div>
  );
}
