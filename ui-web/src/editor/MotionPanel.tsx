import { useEffect, useState } from 'react';
import type { CameraMove, CompileMotionResponse, LayerResponse, ProviderInfo } from './api';

interface MotionPanelProps {
  selectedLayer: LayerResponse | null;
  busy: boolean;

  onSetStatic: (layer: LayerResponse, value: boolean) => void;
  onCommitDescription: (layer: LayerResponse, description: string) => void;
  onClearTrajectory: (layer: LayerResponse) => void;

  cameraMove: CameraMove;
  onCameraMoveChange: (move: CameraMove) => void;
  cameraMagnitude: number;
  onCameraMagnitudeChange: (value: number) => void;
  cameraPrompt: string;
  onCameraPromptChange: (value: string) => void;

  videoProviders: ProviderInfo[];
  videoProvidersError: string | null;
  videoProviderId: string | null;
  onVideoProviderChange: (id: string) => void;

  clipDuration: string;
  onClipDurationChange: (value: string) => void;

  compiling: boolean;
  compileResult: CompileMotionResponse | null;
  onCompile: () => void;

  compilePromptDraft: string;
  onCompilePromptDraftChange: (value: string) => void;

  onSubmit: () => void;
}

const CAMERA_MOVE_OPTIONS: { value: CameraMove; label: string }[] = [
  { value: 'none', label: 'Žádná' },
  { value: 'pan_left', label: 'Pan vlevo' },
  { value: 'pan_right', label: 'Pan vpravo' },
  { value: 'tilt_up', label: 'Tilt nahoru' },
  { value: 'tilt_down', label: 'Tilt dolů' },
  { value: 'zoom_in', label: 'Zoom in' },
  { value: 'zoom_out', label: 'Zoom out' },
  { value: 'custom', label: 'Vlastní' },
];

const DEFAULT_DURATION_CHOICES = ['5', '10'];

export default function MotionPanel(props: MotionPanelProps) {
  const {
    selectedLayer,
    busy,
    onSetStatic,
    onCommitDescription,
    onClearTrajectory,
    cameraMove,
    onCameraMoveChange,
    cameraMagnitude,
    onCameraMagnitudeChange,
    cameraPrompt,
    onCameraPromptChange,
    videoProviders,
    videoProvidersError,
    videoProviderId,
    onVideoProviderChange,
    clipDuration,
    onClipDurationChange,
    compiling,
    compileResult,
    onCompile,
    compilePromptDraft,
    onCompilePromptDraftChange,
    onSubmit,
  } = props;

  // Local edit buffer for the description field so typing doesn't persist on every keystroke —
  // committed onBlur (see commitDescriptionIfChanged), mirroring commitTransform's
  // "mutate then persist at the end of the interaction" pattern used for drag/resize in EditorApp.
  const [descriptionDraft, setDescriptionDraft] = useState(selectedLayer?.motion?.description ?? '');
  useEffect(() => {
    setDescriptionDraft(selectedLayer?.motion?.description ?? '');
  }, [selectedLayer?.id, selectedLayer?.motion?.description]);

  const trajectoryCount = selectedLayer?.motion?.trajectory.length ?? 0;
  const isStatic = selectedLayer?.motion?.static ?? false;
  const showMagnitude = cameraMove !== 'none' && cameraMove !== 'custom';
  const showCameraPrompt = cameraMove === 'custom';

  const selectedProvider = videoProviders.find((p) => p.id === videoProviderId) ?? null;
  const durationChoices = selectedProvider?.duration_choices ?? DEFAULT_DURATION_CHOICES;

  function commitDescriptionIfChanged() {
    if (!selectedLayer) return;
    const current = selectedLayer.motion?.description ?? '';
    if (descriptionDraft !== current) onCommitDescription(selectedLayer, descriptionDraft);
  }

  return (
    <div className="editor-motion-panel">
      <h2>Motion</h2>

      <div className="inspector-section">
        <h3>Pohyb prvku</h3>
        {!selectedLayer && <p className="editor-hint">Select a layer first.</p>}
        {selectedLayer && (
          <>
            <label className="motion-checkbox-label">
              <input
                type="checkbox"
                checked={isStatic}
                disabled={busy}
                onChange={(e) => onSetStatic(selectedLayer, e.target.checked)}
              />
              Statický (nehýbe se)
            </label>
            <input
              type="text"
              placeholder="Popis pohybu (volitelný, anglicky)"
              value={descriptionDraft}
              disabled={busy}
              onChange={(e) => setDescriptionDraft(e.target.value)}
              onBlur={commitDescriptionIfChanged}
            />
            <p className="editor-hint">
              {trajectoryCount} bodů trajektorie{' '}
              <button
                type="button"
                className="inline-btn"
                disabled={busy || trajectoryCount === 0}
                onClick={() => onClearTrajectory(selectedLayer)}
              >
                Smazat trajektorii
              </button>
            </p>
            <p className="editor-hint">Klikni na plátno pro přidání bodu.</p>
          </>
        )}
      </div>

      <div className="inspector-section">
        <h3>Kamera</h3>
        <select value={cameraMove} disabled={busy} onChange={(e) => onCameraMoveChange(e.target.value as CameraMove)}>
          {CAMERA_MOVE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        {showMagnitude && (
          <label className="motion-slider-label">
            Velikost
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={cameraMagnitude}
              disabled={busy}
              onChange={(e) => onCameraMagnitudeChange(Number(e.target.value))}
            />
            <span>{cameraMagnitude.toFixed(2)}</span>
          </label>
        )}
        {showCameraPrompt && (
          <textarea
            className="inspector-textarea"
            placeholder="Vlastní popis pohybu kamery (anglicky)"
            value={cameraPrompt}
            disabled={busy}
            onChange={(e) => onCameraPromptChange(e.target.value)}
          />
        )}
      </div>

      <div className="inspector-section">
        <h3>Generace klipu</h3>
        <select
          value={videoProviderId ?? ''}
          disabled={busy || videoProviders.length === 0}
          onChange={(e) => onVideoProviderChange(e.target.value)}
        >
          {videoProviders.length === 0 && <option value="">(no providers)</option>}
          {videoProviders.map((p) => (
            <option key={p.id} value={p.id} title={p.capabilities.notes}>
              {p.id}
              {p.est_cost_usd_per_second != null ? ` (~$${p.est_cost_usd_per_second.toFixed(2)}/s)` : ''}
              {p.id === 'kling-15-pro' ? ' (legacy)' : ''}
            </option>
          ))}
        </select>
        {videoProvidersError && <p className="editor-hint error">Providers: {videoProvidersError}</p>}
        <select value={clipDuration} disabled={busy} onChange={(e) => onClipDurationChange(e.target.value)}>
          {durationChoices.map((d) => (
            <option key={d} value={d}>
              {d}s
            </option>
          ))}
        </select>
        <button type="button" disabled={busy || compiling || !videoProviderId} onClick={onCompile}>
          {compiling ? 'Kompiluji…' : 'Náhled promptu'}
        </button>
        {compilePromptDraft && (
          <>
            <textarea
              className="inspector-textarea"
              value={compilePromptDraft}
              disabled={busy}
              onChange={(e) => onCompilePromptDraftChange(e.target.value)}
            />
            {compileResult && (
              <p className="editor-hint">
                Odhad: {compileResult.est_cost_usd != null ? `~$${compileResult.est_cost_usd.toFixed(2)}` : 'neznámý'}{' '}
                ({compileResult.price_note || 'orientační, sekundární zdroj'}) · {compileResult.endpoint}
              </p>
            )}
          </>
        )}
        <button type="button" disabled={busy || !compilePromptDraft.trim()} onClick={onSubmit}>
          Generovat klip
        </button>
      </div>
    </div>
  );
}
