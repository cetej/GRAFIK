import type { LayerResponse } from './api';

interface LayersPanelProps {
  /** Pre-sorted, topmost (highest z_order) first — see sortedForList in EditorApp. */
  layers: LayerResponse[];
  selectedLayerId: string | null;
  busy: boolean;
  loading: boolean;
  onSelect: (id: string) => void;
  onToggleVisibility: (layer: LayerResponse) => void;
  onReorder: (layer: LayerResponse, direction: 1 | -1) => void;
  onDelete: (layer: LayerResponse) => void;
}

export default function LayersPanel(props: LayersPanelProps) {
  const { layers, selectedLayerId, busy, loading, onSelect, onToggleVisibility, onReorder, onDelete } = props;

  return (
    <div className="editor-section editor-section-layers">
      <h2>Layers{loading ? ' (loading...)' : ''}</h2>
      {layers.map((layer, index) => (
        <div
          key={layer.id}
          className={`layer-item${layer.id === selectedLayerId ? ' selected' : ''}`}
          onClick={() => onSelect(layer.id)}
        >
          <button
            type="button"
            className={`eye${layer.visible ? '' : ' hidden'}`}
            disabled={busy}
            onClick={(e) => {
              e.stopPropagation();
              onToggleVisibility(layer);
            }}
            title={layer.visible ? 'Hide layer' : 'Show layer'}
          >
            👁
          </button>
          <span className="name">{layer.name || layer.id}</span>
          {layer.tags.includes('sam') && <span className="badge">SAM</span>}
          <span className="zorder-controls">
            <button
              type="button"
              disabled={busy || index === 0}
              onClick={(e) => {
                e.stopPropagation();
                onReorder(layer, 1);
              }}
              title="Move up"
            >
              ▲
            </button>
            <button
              type="button"
              disabled={busy || index === layers.length - 1}
              onClick={(e) => {
                e.stopPropagation();
                onReorder(layer, -1);
              }}
              title="Move down"
            >
              ▼
            </button>
          </span>
          <button
            type="button"
            className="delete-btn"
            disabled={busy}
            onClick={(e) => {
              e.stopPropagation();
              onDelete(layer);
            }}
            title="Delete layer"
          >
            🗑
          </button>
        </div>
      ))}
    </div>
  );
}
