import { useState } from 'react';
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
  onRename: (layer: LayerResponse, name: string) => void;
}

export default function LayersPanel(props: LayersPanelProps) {
  const { layers, selectedLayerId, busy, loading, onSelect, onToggleVisibility, onReorder, onDelete, onRename } =
    props;
  const [editingId, setEditingId] = useState<string | null>(null);

  function commitRename(layer: LayerResponse, value: string) {
    setEditingId(null);
    onRename(layer, value);
  }

  return (
    <div className="editor-section editor-section-layers">
      <h2>Vrstvy{loading ? ' (načítám…)' : ''}</h2>
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
            title={layer.visible ? 'Skrýt vrstvu' : 'Zobrazit vrstvu'}
          >
            👁
          </button>
          {editingId === layer.id ? (
            <input
              className="rename-input"
              autoFocus
              defaultValue={layer.name}
              onClick={(e) => e.stopPropagation()}
              onKeyDown={(e) => {
                if (e.key === 'Enter') commitRename(layer, (e.target as HTMLInputElement).value);
                if (e.key === 'Escape') setEditingId(null);
              }}
              onBlur={(e) => commitRename(layer, e.target.value)}
            />
          ) : (
            <span
              className="name"
              title="Dvojklikem přejmenujete vrstvu"
              onDoubleClick={(e) => {
                e.stopPropagation();
                if (!busy) setEditingId(layer.id);
              }}
            >
              {layer.name || layer.id}
            </span>
          )}
          {layer.tags.includes('sam') && <span className="badge">SAM</span>}
          <span className="zorder-controls">
            <button
              type="button"
              disabled={busy || index === 0}
              onClick={(e) => {
                e.stopPropagation();
                onReorder(layer, 1);
              }}
              title="Posunout výš"
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
              title="Posunout níž"
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
            title="Smazat vrstvu"
          >
            🗑
          </button>
        </div>
      ))}
    </div>
  );
}
