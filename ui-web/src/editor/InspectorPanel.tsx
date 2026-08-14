import type { LayerResponse, ProviderInfo } from './api';

interface InspectorPanelProps {
  selectedLayer: LayerResponse | null;
  busy: boolean;

  providers: ProviderInfo[];
  providersError: string | null;

  aiEditPrompt: string;
  onAiEditPromptChange: (value: string) => void;
  aiEditProviderId: string | null;
  onAiEditProviderChange: (id: string) => void;
  onRunAiEdit: () => void;
  brushStrokeCount: number;
  onClearBrush: () => void;

  inpaintPrompt: string;
  onInpaintPromptChange: (value: string) => void;
  onRunInpaintBehind: () => void;

  segmentText: string;
  onSegmentTextChange: (value: string) => void;
  onRunSegment: () => void;
  segmentStatus: string | null;
}

export default function InspectorPanel(props: InspectorPanelProps) {
  const {
    selectedLayer,
    busy,
    providers,
    providersError,
    aiEditPrompt,
    onAiEditPromptChange,
    aiEditProviderId,
    onAiEditProviderChange,
    onRunAiEdit,
    brushStrokeCount,
    onClearBrush,
    inpaintPrompt,
    onInpaintPromptChange,
    onRunInpaintBehind,
    segmentText,
    onSegmentTextChange,
    onRunSegment,
    segmentStatus,
  } = props;

  return (
    <aside className="editor-inspector">
      <h2>Inspector</h2>

      <div className="inspector-section">
        <h3>AI edit</h3>
        {!selectedLayer && <p className="editor-hint">Select a layer first.</p>}
        <textarea
          className="inspector-textarea"
          placeholder="Describe the edit..."
          value={aiEditPrompt}
          disabled={busy}
          onChange={(e) => onAiEditPromptChange(e.target.value)}
        />
        <select
          value={aiEditProviderId ?? ''}
          disabled={busy || providers.length === 0}
          onChange={(e) => onAiEditProviderChange(e.target.value)}
        >
          {providers.length === 0 && <option value="">(no providers)</option>}
          {providers.map((p) => (
            <option
              key={p.id}
              value={p.id}
              disabled={!p.has_impl || !p.capabilities.supports_mask}
              title={p.capabilities.notes}
            >
              {p.id}
              {!p.has_impl ? ' (no impl)' : !p.capabilities.supports_mask ? ' (no mask support)' : ''}
            </option>
          ))}
        </select>
        {providersError && <p className="editor-hint error">Providers: {providersError}</p>}
        <p className="editor-hint">
          {brushStrokeCount > 0 ? (
            <>
              Brush maska aktivní ({brushStrokeCount} tahů){' '}
              <button type="button" className="inline-btn" disabled={busy} onClick={onClearBrush} title="Clear brush mask">
                ×
              </button>
            </>
          ) : (
            'Bez masky se použije alfa vrstvy.'
          )}
        </p>
        <button
          type="button"
          disabled={busy || !selectedLayer || !aiEditPrompt.trim() || !aiEditProviderId}
          onClick={onRunAiEdit}
        >
          Run
        </button>
      </div>

      <div className="inspector-section">
        <h3>Inpaint behind</h3>
        <input
          type="text"
          placeholder="(optional prompt)"
          value={inpaintPrompt}
          disabled={busy}
          onChange={(e) => onInpaintPromptChange(e.target.value)}
        />
        <p className="editor-hint">Vyplní pozadí za vybraným prvkem.</p>
        <button type="button" disabled={busy || !selectedLayer} onClick={onRunInpaintBehind}>
          Run
        </button>
      </div>

      <div className="inspector-section">
        <h3>Segment (SAM)</h3>
        <input
          type="text"
          placeholder="pojmenuj prvek"
          value={segmentText}
          disabled={busy}
          onChange={(e) => onSegmentTextChange(e.target.value)}
        />
        <button type="button" disabled={busy || !segmentText.trim()} onClick={onRunSegment}>
          Segment
        </button>
        {segmentStatus && <p className="editor-hint">{segmentStatus}</p>}
      </div>
    </aside>
  );
}
