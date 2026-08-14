import { useState } from 'react';
import { clipVideoUrl, type ClipRecordDto, type ClipStatus, type MotionWanted, type VerifyVerdict } from './api';

interface ClipsPanelProps {
  projectId: string;
  clips: ClipRecordDto[];
  /** Cache-buster per clip id, bumped once when a clip transitions to completed (see EditorApp). */
  videoVersions: Record<string, number>;
  busy: boolean;
  onRetry: (clip: ClipRecordDto) => void;
}

const STATUS_LABEL: Record<ClipStatus, string> = {
  pending: 'čeká',
  running: 'běží',
  completed: 'hotovo',
  failed: 'selhalo',
};

// verdict "yes" means "did what was wanted" — for a static element that is
// "stayed still", so the label set depends on `wanted`, not just the verdict.
const VERDICT_LABEL: Record<MotionWanted, Record<VerifyVerdict, string>> = {
  move: { yes: 'hýbalo se ✓', weak: 'hýbalo se slabě', no: 'hýbalo se ✗' },
  still: { yes: 'v klidu ✓', weak: 'mírný pohyb', no: 'hýbalo se (nemělo) ✗' },
};

function formatTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

export default function ClipsPanel(props: ClipsPanelProps) {
  const { projectId, clips, videoVersions, busy, onRetry } = props;
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  return (
    <div className="editor-section editor-section-clips">
      <h2>Klipy</h2>
      {clips.length === 0 && <p className="editor-hint">Zatím žádné klipy.</p>}
      {clips.map((clip) => (
        <div key={clip.id} className="clip-card">
          <div className="clip-card-head">
            <span className={`status-chip status-${clip.status}`}>
              {(clip.status === 'running' || clip.status === 'pending') && (
                <span className="spinner" aria-hidden="true" />
              )}
              {STATUS_LABEL[clip.status]}
            </span>
            <span className="clip-provider">{clip.provider_id}</span>
            <span className="clip-time">{formatTime(clip.created_at)}</span>
          </div>
          {clip.cost_note && <p className="editor-hint">{clip.cost_note}</p>}
          {clip.prompt && (
            <p
              className={`clip-prompt${expanded[clip.id] ? ' expanded' : ''}`}
              title={clip.prompt}
              onClick={() => setExpanded((prev) => ({ ...prev, [clip.id]: !prev[clip.id] }))}
            >
              {clip.prompt}
            </p>
          )}
          {clip.status === 'failed' && clip.error && <p className="clip-error">{clip.error}</p>}
          {clip.verification && (
            <div className="clip-verification">
              {clip.verification.elements.map((el) => (
                <span
                  key={el.layer_id}
                  className={`verdict-chip verdict-${el.verdict}`}
                  title={`in=${el.in_motion.toFixed(2)} out=${el.out_motion.toFixed(2)} ratio=${el.ratio.toFixed(2)}`}
                >
                  {el.layer_name}: {VERDICT_LABEL[el.wanted][el.verdict]}
                </span>
              ))}
              <p className="editor-hint">
                Globální pohyb: {clip.verification.global_motion.toFixed(2)} — {clip.verification.summary}
              </p>
            </div>
          )}
          {clip.status === 'completed' && clip.path && (
            <video controls width="100%" src={clipVideoUrl(projectId, clip.id, videoVersions[clip.id])} />
          )}
          <button type="button" className="clip-retry-btn" disabled={busy} onClick={() => onRetry(clip)}>
            Retry / Upravit
          </button>
        </div>
      ))}
    </div>
  );
}
