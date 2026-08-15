import { useState } from 'react';
import type { LayerResponse } from './api';

interface LayersPanelProps {
  /** Pre-sorted, topmost (highest z_order) first — see sortedForList in EditorApp. */
  layers: LayerResponse[];
  selectedLayerId: string | null;
  busy: boolean;
  onSelect: (id: string) => void;
  onToggleVisibility: (layer: LayerResponse) => void;
  onReorder: (layer: LayerResponse, direction: 1 | -1) => void;
  onDelete: (layer: LayerResponse) => void;
  onRename: (layer: LayerResponse, name: string) => void;
  /** M6-UX1: canvas hover-highlight — item reports itself on enter, null on leave. */
  onHoverLayer: (id: string | null) => void;
  /** M6-UX1: thumbnail <img> src — same URL Konva uses (layerPngUrl), so the browser cache serves
   * it with no extra network round-trip. */
  getThumbUrl: (layer: LayerResponse) => string;
}

interface LayerRowProps {
  layer: LayerResponse;
  selected: boolean;
  busy: boolean;
  /** Whole-project min/max z_order — up/down disable state must key off z_order, not list
   * position, because the list can render as two groups (text/other) instead of one flat run. */
  minZ: number;
  maxZ: number;
  editing: boolean;
  onStartEdit: () => void;
  onCommitEdit: (value: string) => void;
  onCancelEdit: () => void;
  onSelect: (id: string) => void;
  onToggleVisibility: (layer: LayerResponse) => void;
  onReorder: (layer: LayerResponse, direction: 1 | -1) => void;
  onDelete: (layer: LayerResponse) => void;
  onHoverLayer: (id: string | null) => void;
  getThumbUrl: (layer: LayerResponse) => string;
}

function LayerRow(props: LayerRowProps) {
  const {
    layer,
    selected,
    busy,
    minZ,
    maxZ,
    editing,
    onStartEdit,
    onCommitEdit,
    onCancelEdit,
    onSelect,
    onToggleVisibility,
    onReorder,
    onDelete,
    onHoverLayer,
    getThumbUrl,
  } = props;

  const textBadgeTitle = layer.text_current
    ? `Text: "${layer.text_current}"`
    : `Textová vrstva (score ${layer.text_score != null ? layer.text_score.toFixed(2) : '?'})`;

  return (
    <div
      className={`layer-item${selected ? ' selected' : ''}`}
      onClick={() => onSelect(layer.id)}
      onMouseEnter={() => onHoverLayer(layer.id)}
      onMouseLeave={() => onHoverLayer(null)}
    >
      <div className="layer-thumb" aria-hidden="true">
        <img src={getThumbUrl(layer)} alt="" loading="lazy" />
      </div>
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
      {editing ? (
        <input
          className="rename-input"
          autoFocus
          defaultValue={layer.name}
          onClick={(e) => e.stopPropagation()}
          onKeyDown={(e) => {
            if (e.key === 'Enter') onCommitEdit((e.target as HTMLInputElement).value);
            if (e.key === 'Escape') onCancelEdit();
          }}
          onBlur={(e) => onCommitEdit(e.target.value)}
        />
      ) : (
        <span
          className="name"
          title="Dvojklikem přejmenujete vrstvu"
          onDoubleClick={(e) => {
            e.stopPropagation();
            if (!busy) onStartEdit();
          }}
        >
          {layer.name || layer.id}
        </span>
      )}
      {layer.is_text && (
        <span className="badge badge-text" title={textBadgeTitle}>
          TEXT
        </span>
      )}
      {layer.tags.includes('sam') && <span className="badge">SAM</span>}
      <span className="zorder-controls">
        <button
          type="button"
          disabled={busy || layer.z_order === maxZ}
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
          disabled={busy || layer.z_order === minZ}
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
  );
}

export default function LayersPanel(props: LayersPanelProps) {
  const {
    layers,
    selectedLayerId,
    busy,
    onSelect,
    onToggleVisibility,
    onReorder,
    onDelete,
    onRename,
    onHoverLayer,
    getThumbUrl,
  } = props;
  const [editingId, setEditingId] = useState<string | null>(null);

  function commitRename(layer: LayerResponse, value: string) {
    setEditingId(null);
    onRename(layer, value);
  }

  if (layers.length === 0) {
    return <p className="editor-hint">Zatím žádné vrstvy.</p>;
  }

  const zOrders = layers.map((l) => l.z_order);
  const minZ = Math.min(...zOrders);
  const maxZ = Math.max(...zOrders);
  const textLayers = layers.filter((l) => l.is_text);
  const otherLayers = layers.filter((l) => !l.is_text);
  const grouped = textLayers.length > 0;

  function renderRow(layer: LayerResponse) {
    return (
      <LayerRow
        key={layer.id}
        layer={layer}
        selected={layer.id === selectedLayerId}
        busy={busy}
        minZ={minZ}
        maxZ={maxZ}
        editing={editingId === layer.id}
        onStartEdit={() => setEditingId(layer.id)}
        onCommitEdit={(value) => commitRename(layer, value)}
        onCancelEdit={() => setEditingId(null)}
        onSelect={onSelect}
        onToggleVisibility={onToggleVisibility}
        onReorder={onReorder}
        onDelete={onDelete}
        onHoverLayer={onHoverLayer}
        getThumbUrl={getThumbUrl}
      />
    );
  }

  if (!grouped) {
    return <>{layers.map(renderRow)}</>;
  }

  return (
    <>
      <p className="layer-group-heading">Textové vrstvy</p>
      {textLayers.map(renderRow)}
      <p className="layer-group-heading">Ostatní vrstvy</p>
      {otherLayers.length === 0 ? (
        <p className="editor-hint">Žádné další vrstvy.</p>
      ) : (
        otherLayers.map(renderRow)
      )}
    </>
  );
}
