import type { LayerResponse, ProviderInfo } from './api';

/** M5: one-line reminder of each provider's prompt semantics, shown under the AI-edit provider
 * select. Fill models (flux-fill) never see the masked content; edit models (qwen-inpaint) see the
 * whole image. Providers not listed here render no hint. */
const PROVIDER_HINTS: Record<string, string> = {
  'qwen-inpaint': 'qwen: popište ÚPRAVU stávajícího obsahu (model vidí celý obraz)',
  'flux-fill': 'flux-fill: popište, co má v oblasti VZNIKNOUT (model obsah masky nevidí)',
};

interface InspectorPanelProps {
  selectedLayer: LayerResponse | null;
  busy: boolean;

  providers: ProviderInfo[];
  providersError: string | null;

  aiEditPrompt: string;
  onAiEditPromptChange: (value: string) => void;
  aiEditProviderId: string | null;
  onAiEditProviderChange: (id: string) => void;
  /** M5: crop around a small mask and edit at full resolution (see the hint text next to it). */
  cropInpaint: boolean;
  onCropInpaintChange: (value: boolean) => void;
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

  subLayers: number;
  onSubLayersChange: (n: number) => void;
  onRunLayerDecompose: () => void;
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
    cropInpaint,
    onCropInpaintChange,
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
    subLayers,
    onSubLayersChange,
    onRunLayerDecompose,
  } = props;

  return (
    <aside className="editor-inspector">
      <h2>Inspektor</h2>

      <div className="inspector-section">
        <h3>AI úprava</h3>
        {!selectedLayer && <p className="editor-hint">Nejdřív vyberte vrstvu.</p>}
        <textarea
          className="inspector-textarea"
          placeholder="Popište úpravu…"
          value={aiEditPrompt}
          disabled={busy}
          onChange={(e) => onAiEditPromptChange(e.target.value)}
        />
        <select
          value={aiEditProviderId ?? ''}
          disabled={busy || providers.length === 0}
          onChange={(e) => onAiEditProviderChange(e.target.value)}
        >
          {providers.length === 0 && <option value="">(žádní provideři)</option>}
          {providers.map((p) => (
            <option
              key={p.id}
              value={p.id}
              disabled={!p.has_impl || !p.capabilities.supports_mask}
              title={p.capabilities.notes}
            >
              {p.id}
              {!p.has_impl ? ' (bez implementace)' : !p.capabilities.supports_mask ? ' (bez podpory masky)' : ''}
            </option>
          ))}
        </select>
        {providersError && <p className="editor-hint error">Provideři: {providersError}</p>}
        {aiEditProviderId && PROVIDER_HINTS[aiEditProviderId] && (
          <p className="editor-hint">{PROVIDER_HINTS[aiEditProviderId]}</p>
        )}
        <p className="editor-hint">
          {brushStrokeCount > 0 ? (
            <>
              Maska štětcem aktivní ({brushStrokeCount} tahů){' '}
              <button
                type="button"
                className="inline-btn"
                disabled={busy}
                onClick={onClearBrush}
                title="Smazat masku štětcem"
              >
                ×
              </button>
            </>
          ) : (
            'Bez masky se použije alfa vrstvy.'
          )}
        </p>
        <label className="motion-checkbox-label">
          <input
            type="checkbox"
            checked={cropInpaint}
            disabled={busy}
            onChange={(e) => onCropInpaintChange(e.target.checked)}
          />
          Crop kolem masky (ostřejší edit na velkém plátně)
        </label>
        <p className="editor-hint">Malou masku na plátně &gt;1536 px pošle modelu ve výřezu v plném rozlišení.</p>
        <button
          type="button"
          disabled={busy || !selectedLayer || !aiEditPrompt.trim() || !aiEditProviderId}
          onClick={onRunAiEdit}
        >
          Spustit
        </button>
      </div>

      <div className="inspector-section">
        <h3>Vyplnit pozadí</h3>
        <input
          type="text"
          placeholder="(volitelný prompt)"
          value={inpaintPrompt}
          disabled={busy}
          onChange={(e) => onInpaintPromptChange(e.target.value)}
        />
        <p className="editor-hint">Vyplní pozadí za vybraným prvkem.</p>
        <button type="button" disabled={busy || !selectedLayer} onClick={onRunInpaintBehind}>
          Spustit
        </button>
      </div>

      <div className="inspector-section">
        <h3>Segmentace textem</h3>
        <input
          type="text"
          placeholder="popište prvek (např. socha)"
          value={segmentText}
          disabled={busy}
          onChange={(e) => onSegmentTextChange(e.target.value)}
        />
        <button type="button" disabled={busy || !segmentText.trim()} onClick={onRunSegment}>
          Segmentovat
        </button>
        <p className="editor-hint">
          Tip: nástroj Segmentace v horní liště — kliknutím na prvek přímo v obraze.
        </p>
        {segmentStatus && <p className="editor-hint">{segmentStatus}</p>}
      </div>

      <div className="inspector-section">
        <h3>Rozložit vrstvu</h3>
        {!selectedLayer && <p className="editor-hint">Nejdřív vyberte vrstvu.</p>}
        <label className="toolbar-label">
          Podvrstvy
          <select
            value={subLayers}
            disabled={busy}
            onChange={(e) => onSubLayersChange(Number(e.target.value))}
          >
            {[2, 3, 4, 5, 6].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <p className="editor-hint">
          Rozloží vybranou vrstvu na podvrstvy (I2L, ~$0.05). Podvrstvy nahradí původní vrstvu;
          Zpět ji vrátí.
        </p>
        <button type="button" disabled={busy || !selectedLayer} onClick={onRunLayerDecompose}>
          Rozložit
        </button>
      </div>
    </aside>
  );
}
