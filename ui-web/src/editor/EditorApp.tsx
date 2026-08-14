import { useEffect, useMemo, useRef, useState } from 'react';
import Konva from 'konva';
import { Stage, Layer, Image as KonvaImage, Rect, Transformer } from 'react-konva';
import {
  listProjects,
  getProject,
  listLayers,
  layerPngUrl,
  saveTransform,
  toggleVisibility,
  listProviders,
  aiEditLayer,
  inpaintBehind,
  reorderLayer,
  segmentProject,
  createProject,
  decomposeFile,
  exportPng,
  deleteLayer,
  undoProject,
  redoProject,
  getHistory,
  saveLayerMotion,
  clearLayerMotion,
  compileMotion,
  submitVideoJob,
  listVideoJobs,
  refreshVideoJob,
  verifyClip,
  ApiError,
  type ProjectListItem,
  type ProjectResponse,
  type LayerResponse,
  type TransformRequestBody,
  type ProviderInfo,
  type LayerMotionDto,
  type CameraMove,
  type MotionSpecDto,
  type CompileMotionResponse,
  type ClipRecordDto,
} from './api';
import Toolbar from './Toolbar';
import InspectorPanel from './InspectorPanel';
import LayersPanel from './LayersPanel';
import MotionPanel from './MotionPanel';
import ClipsPanel from './ClipsPanel';
import TrajectoryOverlay from './TrajectoryOverlay';
import { useBrush } from './useBrush';
import type { Tool, BusyState, CanvasPoint } from './types';
import './EditorApp.css';

type EditorLayer = LayerResponse;

const CANVAS_PADDING = 32;

// Dev hook for editor-verify.mjs (Playwright): expose the Konva runtime on
// window so the verify script can inspect nodes directly.
window.Konva = Konva;

declare global {
  interface Window {
    Konva?: typeof Konva;
    __editorState?: {
      fitScale: number;
      offsetX: number;
      offsetY: number;
      canvasWidth: number;
      canvasHeight: number;
      selectedLayerId: string | null;
      projectId: string | null;
      busy: string | null;
      tool: Tool;
    };
    __brushCanvas?: HTMLCanvasElement | null;
  }
}

function sortByZAsc(items: EditorLayer[]): EditorLayer[] {
  return [...items].sort((a, b) => a.z_order - b.z_order);
}

function describeError(err: unknown): string {
  if (err instanceof ApiError) return `${err.message} (HTTP ${err.status || '?'})`;
  if (err instanceof Error) return err.message;
  return String(err);
}

const EMPTY_MOTION: LayerMotionDto = { trajectory: [], static: false, description: '' };

/** True once a LayerMotion has drifted back to its all-defaults shape — persistMotion below
 * deletes the record in that case instead of storing a no-op object. */
function isEmptyMotion(m: LayerMotionDto): boolean {
  return m.trajectory.length === 0 && !m.static && m.description.trim() === '';
}

export default function EditorApp() {
  const [apiOnline, setApiOnline] = useState<boolean | null>(null);
  const [projects, setProjects] = useState<ProjectListItem[]>([]);
  const [projectsError, setProjectsError] = useState<string | null>(null);

  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [project, setProject] = useState<ProjectResponse | null>(null);
  const [projectLoading, setProjectLoading] = useState(false);
  const [layers, setLayers] = useState<EditorLayer[]>([]);
  const [selectedLayerId, setSelectedLayerId] = useState<string | null>(null);

  const [banner, setBanner] = useState<string | null>(null);
  const [saveStatus, setSaveStatus] = useState<string | null>(null);

  const [images, setImages] = useState<Record<string, HTMLImageElement>>({});
  const [containerSize, setContainerSize] = useState({ width: 1, height: 1 });

  // --- M2 additions: tool mode, busy/sequential-ops gate, pixel cache-busting ---
  const [tool, setTool] = useState<Tool>('select');
  const [busy, setBusy] = useState<BusyState | null>(null);
  const [pngVersions, setPngVersions] = useState<Record<string, number>>({});
  const [history, setHistory] = useState<{ undo_count: number; redo_count: number } | null>(null);

  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [providersError, setProvidersError] = useState<string | null>(null);
  const [aiEditPrompt, setAiEditPrompt] = useState('');
  const [aiEditProviderId, setAiEditProviderId] = useState<string | null>(null);
  const [inpaintPrompt, setInpaintPrompt] = useState('');
  const [segmentText, setSegmentText] = useState('');
  const [segmentStatus, setSegmentStatus] = useState<string | null>(null);

  // --- M3 additions: motion/camera UI state, compile preview, video jobs ---
  const [videoProviders, setVideoProviders] = useState<ProviderInfo[]>([]);
  const [videoProvidersError, setVideoProvidersError] = useState<string | null>(null);
  const [videoProviderId, setVideoProviderId] = useState<string | null>(null);
  const [clipDuration, setClipDuration] = useState('5');
  const [cameraMove, setCameraMove] = useState<CameraMove>('none');
  const [cameraMagnitude, setCameraMagnitude] = useState(0.5);
  const [cameraPrompt, setCameraPrompt] = useState('');
  const [compiling, setCompiling] = useState(false);
  const [compileResult, setCompileResult] = useState<CompileMotionResponse | null>(null);
  const [compilePromptDraft, setCompilePromptDraft] = useState('');
  const [clips, setClips] = useState<ClipRecordDto[]>([]);
  const [clipVideoVersions, setClipVideoVersions] = useState<Record<string, number>>({});
  const clipsRef = useRef<ClipRecordDto[]>([]);
  const busyRef = useRef<BusyState | null>(null);

  const containerRef = useRef<HTMLDivElement | null>(null);
  const stageRef = useRef<Konva.Stage | null>(null);
  const layerRef = useRef<Konva.Layer | null>(null);
  const transformerRef = useRef<Konva.Transformer | null>(null);
  const imageNodeRefs = useRef<Record<string, Konva.Image | null>>({});
  const cachedIdsRef = useRef<Set<string>>(new Set());

  const canvasWidth = project?.canvas_width ?? 0;
  const canvasHeight = project?.canvas_height ?? 0;

  const brush = useBrush(canvasWidth, canvasHeight, selectedProjectId, () => layerRef.current?.batchDraw());

  // Stable key that only changes when the *set* of layer ids or their pixel
  // versions change, not on every transform/visibility update (which replace
  // `layers` with a new array of the same ids/versions). Used to avoid
  // re-fetching PNGs on every save, while still refetching after a mutation
  // that actually changed pixels (ai-edit, inpaint-behind, undo/redo).
  const layerIdsKey = useMemo(
    () => layers.map((l) => `${l.id}:${pngVersions[l.id] ?? 0}`).join(','),
    [layers, pngVersions],
  );

  // Ping the API + load the project list on mount.
  useEffect(() => {
    let cancelled = false;
    listProjects()
      .then((list) => {
        if (cancelled) return;
        setProjects(list);
        setApiOnline(true);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setApiOnline(false);
        setProjectsError(describeError(err));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Load the image-edit provider list once on mount (independent of project selection).
  useEffect(() => {
    let cancelled = false;
    listProviders('image_edit')
      .then((list) => {
        if (cancelled) return;
        setProviders(list);
        setProvidersError(null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setProvidersError(describeError(err));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Default the AI-edit provider select to the first usable (implemented + mask-capable)
  // entry once providers load, without clobbering a choice the user already made.
  useEffect(() => {
    if (providers.length === 0) return;
    setAiEditProviderId((prev) => {
      if (prev && providers.some((p) => p.id === prev)) return prev;
      const usable = providers.find((p) => p.has_impl && p.capabilities.supports_mask);
      return (usable ?? providers[0]).id;
    });
  }, [providers]);

  // Load the video-job provider list once on mount (separate kind from the AI-edit list above).
  useEffect(() => {
    let cancelled = false;
    listProviders('video')
      .then((list) => {
        if (cancelled) return;
        setVideoProviders(list);
        setVideoProvidersError(null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setVideoProvidersError(describeError(err));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Default the video provider select to wan-26 (best price/quality per the M3 contract) once
  // providers load, without clobbering a choice the user already made.
  useEffect(() => {
    if (videoProviders.length === 0) return;
    setVideoProviderId((prev) => {
      if (prev && videoProviders.some((p) => p.id === prev)) return prev;
      const preferred = videoProviders.find((p) => p.id === 'wan-26');
      return (preferred ?? videoProviders[0]).id;
    });
  }, [videoProviders]);

  // Keep the selected duration valid for whichever provider is currently chosen.
  useEffect(() => {
    const provider = videoProviders.find((p) => p.id === videoProviderId);
    if (!provider) return;
    setClipDuration((prev) => (provider.duration_choices.includes(prev) ? prev : (provider.duration_choices[0] ?? '5')));
  }, [videoProviderId, videoProviders]);

  useEffect(() => {
    clipsRef.current = clips;
  }, [clips]);

  useEffect(() => {
    busyRef.current = busy;
  }, [busy]);

  // Poll running clips every 15s (only while a project is loaded and nothing else is busy), and
  // auto-verify any clip that just finished. Reads clipsRef/busyRef instead of closing over
  // `clips`/`busy` directly so a single long-lived interval (recreated only on project switch)
  // never acts on stale data.
  useEffect(() => {
    const projectId = selectedProjectId;
    if (!projectId) return;
    const interval = setInterval(() => {
      if (busyRef.current) return;
      const running = clipsRef.current.filter((c) => c.status === 'running' || c.status === 'pending');
      for (const clip of running) {
        refreshVideoJob(projectId, clip.id)
          .then((updated) => {
            setClips((prev) => prev.map((c) => (c.id === updated.id ? updated : c)));
            if (updated.status === 'completed') {
              bumpClipVideoVersion(updated.id);
              if (!updated.verification) {
                setSaveStatus(`Verifikuji klip ${updated.id}…`);
                verifyClip(projectId, updated.id)
                  .then((verified) => {
                    setClips((prev) => prev.map((c) => (c.id === verified.id ? verified : c)));
                    setSaveStatus(`Klip ${verified.id} zverifikován.`);
                  })
                  .catch((err: unknown) => {
                    setSaveStatus(`Verifikace klipu ${updated.id} selhala: ${describeError(err)}`);
                  });
              }
            } else if (updated.status === 'failed') {
              setSaveStatus(`Klip ${updated.id} selhal: ${updated.error || 'neznámá chyba'}`);
            }
          })
          .catch((err: unknown) => {
            setSaveStatus(`Poll klipu ${clip.id} selhal: ${describeError(err)}`);
          });
      }
    }, 15000);
    return () => clearInterval(interval);
  }, [selectedProjectId]);

  // Fit the canvas area (viewport minus sidebar/status strip) with a resize observer.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      const { width, height } = entry.contentRect;
      setContainerSize({ width: Math.max(1, Math.floor(width)), height: Math.max(1, Math.floor(height)) });
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // Load a PNG per layer whenever the loaded project's layer *set* or any layer's
  // pixel version changes.
  useEffect(() => {
    imageNodeRefs.current = {};
    cachedIdsRef.current = new Set();
    setImages({});
    if (!selectedProjectId || layers.length === 0) return;

    let cancelled = false;
    const idsAndNames = layers.map((l) => ({ id: l.id, name: l.name, v: pngVersions[l.id] ?? 0 }));
    for (const { id, name, v } of idsAndNames) {
      const img = new Image();
      img.crossOrigin = 'anonymous';
      img.onload = () => {
        if (cancelled) return;
        setImages((prev) => ({ ...prev, [id]: img }));
      };
      img.onerror = () => {
        if (cancelled) return;
        setBanner(`Failed to load PNG for layer "${name}".`);
      };
      img.src = layerPngUrl(selectedProjectId, id, false, v);
    }
    return () => {
      cancelled = true;
    };
    // layerIdsKey (not `layers`/`pngVersions`) is the intended dependency — see its comment above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedProjectId, layerIdsKey]);

  // Cache each newly-loaded image node exactly once, same as the spike, so
  // clicks alpha-hit-test through transparent pixels instead of hitting the
  // node's bounding box.
  useEffect(() => {
    let changed = false;
    for (const id of Object.keys(images)) {
      const node = imageNodeRefs.current[id];
      if (node && !cachedIdsRef.current.has(id)) {
        node.cache({ pixelRatio: 1 });
        node.drawHitFromCache(0);
        cachedIdsRef.current.add(id);
        changed = true;
      }
    }
    if (changed) layerRef.current?.batchDraw();
  }, [images]);

  // Keep the Transformer attached to whichever layer is currently selected —
  // only in the select tool (brush/segment disconnect it, see handleTransformEnd et al)
  // and only while idle: the Transformer's resize/rotate handles are separate
  // Konva shapes with their own listeners, so `interactive` below (which only
  // gates the image node's own listening/draggable) wouldn't stop a resize
  // drag started mid-operation without this.
  useEffect(() => {
    const tr = transformerRef.current;
    if (!tr) return;
    const node = tool === 'select' && !busy && selectedLayerId ? imageNodeRefs.current[selectedLayerId] : null;
    tr.nodes(node ? [node] : []);
    tr.getLayer()?.batchDraw();
  }, [selectedLayerId, images, tool, busy]);

  const { fitScale, offsetX, offsetY } = useMemo(() => {
    if (!canvasWidth || !canvasHeight) {
      return { fitScale: 1, offsetX: 0, offsetY: 0 };
    }
    const availW = Math.max(1, containerSize.width - CANVAS_PADDING * 2);
    const availH = Math.max(1, containerSize.height - CANVAS_PADDING * 2);
    const s = Math.min(availW / canvasWidth, availH / canvasHeight);
    const scale = Number.isFinite(s) && s > 0 ? s : 1;
    return {
      fitScale: scale,
      offsetX: (containerSize.width - canvasWidth * scale) / 2,
      offsetY: (containerSize.height - canvasHeight * scale) / 2,
    };
  }, [containerSize, canvasWidth, canvasHeight]);

  // Dev hooks for editor-verify.mjs.
  useEffect(() => {
    window.__editorState = {
      fitScale,
      offsetX,
      offsetY,
      canvasWidth,
      canvasHeight,
      selectedLayerId,
      projectId: selectedProjectId,
      busy: busy?.op ?? null,
      tool,
    };
  }, [fitScale, offsetX, offsetY, canvasWidth, canvasHeight, selectedLayerId, selectedProjectId, busy, tool]);

  useEffect(() => {
    window.__brushCanvas = brush.canvas;
  }, [brush.canvas]);

  async function refreshHistory(projectId: string) {
    try {
      const h = await getHistory(projectId);
      setHistory(h);
    } catch {
      // Non-critical — keep whatever counts we last had.
    }
  }

  async function handleSelectProject(id: string) {
    if (id === selectedProjectId) return;
    setSelectedProjectId(id);
    setSelectedLayerId(null);
    setProject(null);
    setLayers([]);
    setSaveStatus(null);
    setSegmentStatus(null);
    setPngVersions({});
    setHistory(null);
    setTool('select');
    setClips([]);
    setClipVideoVersions({});
    setCompileResult(null);
    setCompilePromptDraft('');
    setProjectLoading(true);
    try {
      const [proj, layerList, hist, clipList] = await Promise.all([
        getProject(id),
        listLayers(id),
        getHistory(id),
        listVideoJobs(id),
      ]);
      setProject(proj);
      setLayers(sortByZAsc(layerList.map((l) => ({ ...l }))));
      setHistory(hist);
      setClips(clipList);
    } catch (err) {
      setBanner(`Failed to load project: ${describeError(err)}`);
    } finally {
      setProjectLoading(false);
    }
  }

  async function reloadLayers(projectId: string): Promise<EditorLayer[] | null> {
    try {
      const layerList = await listLayers(projectId);
      const sorted = sortByZAsc(layerList.map((l) => ({ ...l })));
      setLayers(sorted);
      return sorted;
    } catch (err) {
      setBanner(`Failed to reload layers: ${describeError(err)}`);
      return null;
    }
  }

  function bumpPngVersion(layerId: string) {
    setPngVersions((prev) => ({ ...prev, [layerId]: (prev[layerId] ?? 0) + 1 }));
  }

  function bumpAllPngVersions(list: EditorLayer[]) {
    setPngVersions((prev) => {
      const next = { ...prev };
      for (const l of list) next[l.id] = (next[l.id] ?? 0) + 1;
      return next;
    });
  }

  function bumpClipVideoVersion(clipId: string) {
    setClipVideoVersions((prev) => ({ ...prev, [clipId]: (prev[clipId] ?? 0) + 1 }));
  }

  /** Shared by ai-edit and inpaint-behind: both return one updated LayerResponse. */
  function applyLayerUpdate(updated: LayerResponse) {
    setLayers((prev) => prev.map((l) => (l.id === updated.id ? updated : l)));
    bumpPngVersion(updated.id);
  }

  function commitTransform(layer: EditorLayer, patch: TransformRequestBody, label: string) {
    const projectId = selectedProjectId;
    if (!projectId) return;
    setLayers((prev) => prev.map((l) => (l.id === layer.id ? { ...l, ...patch } : l)));
    setSaveStatus(`Saving ${label} of layer "${layer.name}"...`);
    saveTransform(projectId, layer.id, patch)
      .then(() => {
        setSaveStatus(`Saved ${label} of layer "${layer.name}".`);
        void refreshHistory(projectId);
      })
      .catch((err: unknown) => {
        setBanner(`Failed to save transform: ${describeError(err)}`);
        setSaveStatus(`Save failed: ${label} of layer "${layer.name}".`);
        void reloadLayers(projectId);
      });
  }

  /**
   * Persists a layer's full motion state — same optimistic-update-then-persist shape as
   * commitTransform. Always sends the FULL LayerMotion (trajectory + static + description), not a
   * partial patch, since the /motion route rebuilds the record from what it's sent. When the
   * result would be all-defaults, deletes the record instead of storing a no-op LayerMotion.
   */
  function persistMotion(layer: EditorLayer, nextMotion: LayerMotionDto, label: string) {
    const projectId = selectedProjectId;
    if (!projectId) return;
    const empty = isEmptyMotion(nextMotion);
    setLayers((prev) => prev.map((l) => (l.id === layer.id ? { ...l, motion: empty ? null : nextMotion } : l)));
    setSaveStatus(`Saving ${label}...`);
    const call = empty ? clearLayerMotion(projectId, layer.id) : saveLayerMotion(projectId, layer.id, nextMotion);
    call
      .then((updated) => {
        setLayers((prev) => prev.map((l) => (l.id === layer.id ? updated : l)));
        setSaveStatus(`Saved ${label}.`);
        void refreshHistory(projectId);
      })
      .catch((err: unknown) => {
        setBanner(`Failed to save motion: ${describeError(err)}`);
        setSaveStatus(`Save failed: ${label}.`);
        void reloadLayers(projectId);
      });
  }

  function handleSetMotionStatic(layer: EditorLayer, value: boolean) {
    const current = layer.motion ?? EMPTY_MOTION;
    persistMotion(layer, { ...current, static: value }, 'motion (static)');
  }

  function handleCommitMotionDescription(layer: EditorLayer, description: string) {
    const current = layer.motion ?? EMPTY_MOTION;
    if (current.description === description) return;
    persistMotion(layer, { ...current, description }, 'motion (description)');
  }

  function handleClearTrajectory(layer: EditorLayer) {
    const current = layer.motion ?? EMPTY_MOTION;
    if (current.trajectory.length === 0) return;
    persistMotion(layer, { ...current, trajectory: [] }, 'trajektorie');
  }

  function handleAddTrajectoryPoint(layer: EditorLayer, pt: CanvasPoint) {
    const current = layer.motion ?? EMPTY_MOTION;
    const x = Math.max(0, Math.min(canvasWidth, Math.round(pt.x)));
    const y = Math.max(0, Math.min(canvasHeight, Math.round(pt.y)));
    persistMotion(layer, { ...current, trajectory: [...current.trajectory, { x, y }] }, 'trajektorie');
  }

  /** dragmove: local-only state update (no persist) — see TrajectoryOverlay. */
  function handleTrajectoryPointDragMove(layer: EditorLayer, index: number, pt: CanvasPoint) {
    setLayers((prev) =>
      prev.map((l) => {
        if (l.id !== layer.id || !l.motion) return l;
        const trajectory = l.motion.trajectory.map((p, i) => (i === index ? pt : p));
        return { ...l, motion: { ...l.motion, trajectory } };
      }),
    );
  }

  /** dragend: persist whatever handleTrajectoryPointDragMove landed on. Re-reads `layers` (not the
   * `layer` param) since several dragmove updates may have landed on layers/setState since the
   * overlay's closure was created. */
  function handleTrajectoryPointDragEnd(layer: EditorLayer) {
    const current = layers.find((l) => l.id === layer.id);
    if (!current?.motion) return;
    persistMotion(current, current.motion, 'trajektorie');
  }

  function handleDragEnd(layer: EditorLayer) {
    const node = imageNodeRefs.current[layer.id];
    if (!node) return;
    commitTransform(layer, { x: Math.round(node.x()), y: Math.round(node.y()) }, 'position');
  }

  function handleTransformEnd(layer: EditorLayer) {
    const node = imageNodeRefs.current[layer.id];
    if (!node) return;
    // Transformer resizes via scaleX/scaleY, not width/height — convert then
    // reset scale to 1 before persisting (Layer model has int width/height).
    const newWidth = Math.max(1, Math.round(node.width() * node.scaleX()));
    const newHeight = Math.max(1, Math.round(node.height() * node.scaleY()));
    node.scaleX(1);
    node.scaleY(1);
    node.width(newWidth);
    node.height(newHeight);
    // Changing width/height invalidates Konva's cached hit bitmap — rebuild it
    // so alpha hit-testing keeps working at the new size.
    node.cache({ pixelRatio: 1 });
    node.drawHitFromCache(0);
    layerRef.current?.batchDraw();
    commitTransform(
      layer,
      {
        x: Math.round(node.x()),
        y: Math.round(node.y()),
        width: newWidth,
        height: newHeight,
        rotation: node.rotation(),
      },
      'transform',
    );
  }

  function handleToggleVisibility(layer: EditorLayer) {
    const projectId = selectedProjectId;
    if (!projectId) return;
    const prevVisible = layer.visible;
    setLayers((prev) => prev.map((l) => (l.id === layer.id ? { ...l, visible: !prevVisible } : l)));
    toggleVisibility(projectId, layer.id)
      .then(() => {
        void refreshHistory(projectId);
      })
      .catch((err: unknown) => {
        setBanner(`Failed to toggle visibility: ${describeError(err)}`);
        setLayers((prev) => prev.map((l) => (l.id === layer.id ? { ...l, visible: prevVisible } : l)));
      });
  }

  async function handleReorder(layer: EditorLayer, direction: 1 | -1) {
    const projectId = selectedProjectId;
    if (!projectId) return;
    setBusy({ op: `Přeřazuji vrstvu "${layer.name}"...` });
    try {
      const newList = await reorderLayer(projectId, layer.id, layer.z_order + direction);
      setLayers(sortByZAsc(newList.map((l) => ({ ...l }))));
      await refreshHistory(projectId);
    } catch (err) {
      setBanner(`Failed to reorder layer: ${describeError(err)}`);
    } finally {
      setBusy(null);
    }
  }

  async function handleDeleteLayer(layer: EditorLayer) {
    const projectId = selectedProjectId;
    if (!projectId) return;
    if (!window.confirm(`Delete layer "${layer.name || layer.id}"?`)) return;
    setBusy({ op: `Mažu vrstvu "${layer.name}"...` });
    try {
      await deleteLayer(projectId, layer.id);
      if (selectedLayerId === layer.id) setSelectedLayerId(null);
      await reloadLayers(projectId);
      await refreshHistory(projectId);
      setSaveStatus(`Deleted layer "${layer.name}".`);
    } catch (err) {
      setBanner(`Failed to delete layer: ${describeError(err)}`);
    } finally {
      setBusy(null);
    }
  }

  async function handleUndo() {
    const projectId = selectedProjectId;
    if (!projectId) return;
    setBusy({ op: 'Undo...' });
    try {
      await undoProject(projectId);
      const newLayers = await reloadLayers(projectId);
      if (newLayers) bumpAllPngVersions(newLayers);
      await refreshHistory(projectId);
      setSaveStatus('Undo done.');
    } catch (err) {
      setBanner(`Undo failed: ${describeError(err)}`);
    } finally {
      setBusy(null);
    }
  }

  async function handleRedo() {
    const projectId = selectedProjectId;
    if (!projectId) return;
    setBusy({ op: 'Redo...' });
    try {
      await redoProject(projectId);
      const newLayers = await reloadLayers(projectId);
      if (newLayers) bumpAllPngVersions(newLayers);
      await refreshHistory(projectId);
      setSaveStatus('Redo done.');
    } catch (err) {
      setBanner(`Redo failed: ${describeError(err)}`);
    } finally {
      setBusy(null);
    }
  }

  async function handleRunAiEdit() {
    const projectId = selectedProjectId;
    const layer = selectedLayer;
    const prompt = aiEditPrompt.trim();
    if (!projectId || !layer || !aiEditProviderId || !prompt) return;
    setBusy({ op: 'AI edit běží… může trvat desítky sekund' });
    try {
      const maskB64 = brush.isEmpty ? null : brush.exportMaskB64();
      const resp = await aiEditLayer(projectId, layer.id, {
        prompt,
        provider: aiEditProviderId,
        ...(maskB64 ? { mask_b64: maskB64 } : {}),
      });
      applyLayerUpdate(resp.layer);
      setSaveStatus(`AI edit hotov (${resp.provider}, ${resp.elapsed_s.toFixed(1)}s).`);
      await refreshHistory(projectId);
    } catch (err) {
      setBanner(`AI edit failed: ${describeError(err)}`);
    } finally {
      setBusy(null);
    }
  }

  async function handleRunInpaintBehind() {
    const projectId = selectedProjectId;
    const layer = selectedLayer;
    if (!projectId || !layer) return;
    setBusy({ op: 'Inpaint pozadí běží… může trvat desítky sekund' });
    try {
      const prompt = inpaintPrompt.trim();
      const resp = await inpaintBehind(projectId, layer.id, prompt ? { prompt } : {});
      applyLayerUpdate(resp.layer);
      setSaveStatus(`Inpaint behind hotov (${resp.provider}, ${resp.elapsed_s.toFixed(1)}s).`);
      await refreshHistory(projectId);
    } catch (err) {
      setBanner(`Inpaint behind failed: ${describeError(err)}`);
    } finally {
      setBusy(null);
    }
  }

  async function handleRunSegment() {
    const projectId = selectedProjectId;
    const text = segmentText.trim();
    if (!projectId || !text) return;
    setBusy({ op: 'Segmentace běží…' });
    try {
      const resp = await segmentProject(projectId, text);
      await reloadLayers(projectId);
      const msg = `SAM našel ${resp.mask_count} masek, vytvořeno ${resp.layers.length} vrstev.`;
      setSegmentStatus(msg);
      setSaveStatus(msg);
      await refreshHistory(projectId);
    } catch (err) {
      setBanner(`Segment failed: ${describeError(err)}`);
    } finally {
      setBusy(null);
    }
  }

  async function handleExportPng() {
    const projectId = selectedProjectId;
    if (!projectId || !project) return;
    setBusy({ op: 'Export běží…' });
    try {
      const blob = await exportPng(projectId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${project.name}_composite.png`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      setSaveStatus('Export uložen.');
    } catch (err) {
      setBanner(`Export failed: ${describeError(err)}`);
    } finally {
      setBusy(null);
    }
  }

  async function handleCreateFromImage(file: File, numLayers: number) {
    setBusy({ op: 'Dekompozice běží…' });
    try {
      const name = file.name.replace(/\.[^./]+$/, '') || 'untitled';
      const proj = await createProject(name);
      await decomposeFile(proj.id, file, numLayers);
      const list = await listProjects();
      setProjects(list);
      await handleSelectProject(proj.id);
    } catch (err) {
      setBanner(`New from image failed: ${describeError(err)}`);
    } finally {
      setBusy(null);
    }
  }

  /** layer_motions = every layer that currently has a non-null motion; camera+duration from UI state. */
  function buildMotionSpec(): MotionSpecDto {
    const layerMotions: Record<string, LayerMotionDto> = {};
    for (const l of layers) {
      if (l.motion) layerMotions[l.id] = l.motion;
    }
    return {
      camera: { move: cameraMove, magnitude: cameraMagnitude, prompt: cameraPrompt },
      duration: clipDuration,
      layer_motions: layerMotions,
    };
  }

  /** Cheap preview call (server just builds a prompt string + cost math, no fal.ai I/O) — not
   * behind the busy gate, which is reserved for paid/long operations per the M3 contract. */
  async function handleCompileMotion() {
    const projectId = selectedProjectId;
    if (!projectId || !videoProviderId) return;
    setCompiling(true);
    try {
      const spec = buildMotionSpec();
      const result = await compileMotion(projectId, { motion: spec, provider: videoProviderId });
      setCompileResult(result);
      setCompilePromptDraft(result.prompt);
      setSaveStatus('Náhled promptu připraven.');
    } catch (err) {
      setBanner(`Compile failed: ${describeError(err)}`);
    } finally {
      setCompiling(false);
    }
  }

  async function handleSubmitVideoJob() {
    const projectId = selectedProjectId;
    if (!projectId || !videoProviderId || !compilePromptDraft.trim()) return;
    setBusy({ op: 'Generuji klip… bude pokračovat na pozadí' });
    try {
      const spec = buildMotionSpec();
      // Send the draft as an explicit override unless it's still exactly what the last compile
      // produced — in that case leave it out so the server derives the prompt fresh from `spec`
      // (matters if camera/trajectory changed since the last "Náhled promptu" click).
      const unedited = compileResult != null && compilePromptDraft.trim() === compileResult.prompt.trim();
      const override = unedited ? '' : compilePromptDraft.trim();
      const clip = await submitVideoJob(projectId, { motion: spec, provider: videoProviderId, prompt_override: override });
      setClips((prev) => [clip, ...prev]);
      setCompileResult(null);
      setCompilePromptDraft('');
      setSaveStatus(`Klip odeslán ke generování (${clip.provider_id}).`);
    } catch (err) {
      setBanner(`Video job submit failed: ${describeError(err)}`);
    } finally {
      setBusy(null);
    }
  }

  /** Restores camera/duration/provider + a prefilled prompt draft from an old clip so the user can
   * tweak and resubmit. Does not touch per-layer motions (those stay whatever they currently are)
   * and does not submit anything itself. */
  function handleRetryClip(clip: ClipRecordDto) {
    if (clip.motion) {
      setCameraMove(clip.motion.camera.move);
      setCameraMagnitude(clip.motion.camera.magnitude);
      setCameraPrompt(clip.motion.camera.prompt);
      setClipDuration(clip.motion.duration);
    }
    setVideoProviderId(clip.provider_id);
    setCompileResult(null);
    setCompilePromptDraft(clip.prompt);
    setTool('motion');
  }

  function getCanvasPoint(): CanvasPoint | null {
    const stage = stageRef.current;
    if (!stage) return null;
    const pos = stage.getPointerPosition();
    if (!pos) return null;
    return { x: (pos.x - offsetX) / fitScale, y: (pos.y - offsetY) / fitScale };
  }

  function handleStageMouseDown(e: Konva.KonvaEventObject<MouseEvent | TouchEvent>) {
    if (busy) return;
    if (tool === 'brush') {
      const pt = getCanvasPoint();
      if (pt) brush.beginStroke(pt);
      return;
    }
    if (tool === 'motion') {
      // Layers listen (and can be clicked to select) in motion mode too — only a click that
      // reaches the empty Stage background, with a layer already selected, adds a point.
      if (e.target === stageRef.current && selectedLayer) {
        const pt = getCanvasPoint();
        if (pt) handleAddTrajectoryPoint(selectedLayer, pt);
      }
      return;
    }
    // Layers don't listen outside the select tool, so every segment-tool click
    // hits the Stage background — only treat that as "deselect" in select mode,
    // so a selection made before switching to Segment survives the round trip.
    if (tool === 'select' && e.target === stageRef.current) {
      setSelectedLayerId(null);
    }
  }

  function handleStageMouseMove() {
    if (busy || tool !== 'brush') return;
    const pt = getCanvasPoint();
    if (pt) brush.continueStroke(pt);
  }

  function handleStageMouseUp() {
    if (tool === 'brush') brush.endStroke();
  }

  const sortedForList = useMemo(() => [...layers].sort((a, b) => b.z_order - a.z_order), [layers]);
  const selectedLayer = layers.find((l) => l.id === selectedLayerId) ?? null;
  // draggable/Transformer stay select-only (unchanged); listening also opens up in motion mode so
  // a layer can still be clicked to select it there (see handleStageMouseDown).
  const interactive = tool === 'select' && !busy;
  const layersListenable = (tool === 'select' || tool === 'motion') && !busy;
  const runningClipsCount = clips.filter((c) => c.status === 'running' || c.status === 'pending').length;

  return (
    <div className="editor-root">
      {banner && (
        <div className="editor-banner">
          <span>{banner}</span>
          <button onClick={() => setBanner(null)}>Close</button>
        </div>
      )}

      <Toolbar
        tool={tool}
        onToolChange={setTool}
        busy={!!busy}
        canUndo={(history?.undo_count ?? 0) > 0}
        canRedo={(history?.redo_count ?? 0) > 0}
        onUndo={() => void handleUndo()}
        onRedo={() => void handleRedo()}
        canInpaintBehind={!!selectedLayer}
        onInpaintBehind={() => void handleRunInpaintBehind()}
        canExport={!!project}
        onExportPng={() => void handleExportPng()}
        onNewFromImage={(file, n) => void handleCreateFromImage(file, n)}
        brushSize={brush.brushSize}
        onBrushSizeChange={brush.setBrushSize}
        brushStrokeCount={brush.strokeCount}
        onBrushClear={brush.clear}
      />

      <div className="editor-body">
        <aside className="editor-sidebar">
          <h1>GRAFIK Editor</h1>
          <div className="editor-section">
            <h2>Projects</h2>
            {projectsError && <p className="editor-hint">Error: {projectsError}</p>}
            {projects.length === 0 && !projectsError && <p className="editor-hint">No projects.</p>}
            {projects.map((p) => (
              <div
                key={p.id}
                className={`project-item${p.id === selectedProjectId ? ' selected' : ''}`}
                onClick={() => void handleSelectProject(p.id)}
              >
                <span className="name">{p.name}</span>
                <span className="meta">
                  {p.layer_count} layers
                </span>
              </div>
            ))}
          </div>
          {selectedProjectId && (
            <LayersPanel
              layers={sortedForList}
              selectedLayerId={selectedLayerId}
              busy={!!busy}
              loading={projectLoading}
              onSelect={setSelectedLayerId}
              onToggleVisibility={handleToggleVisibility}
              onReorder={(layer, dir) => void handleReorder(layer, dir)}
              onDelete={(layer) => void handleDeleteLayer(layer)}
            />
          )}
          {selectedProjectId && (
            <ClipsPanel
              projectId={selectedProjectId}
              clips={clips}
              videoVersions={clipVideoVersions}
              busy={!!busy}
              onRetry={handleRetryClip}
            />
          )}
        </aside>

        <div className="editor-canvas-area" ref={containerRef}>
          {!selectedProjectId && <div className="editor-empty">Select a project on the left.</div>}
          {selectedProjectId && (
            <Stage
              ref={stageRef}
              width={containerSize.width}
              height={containerSize.height}
              onMouseDown={handleStageMouseDown}
              onTouchStart={handleStageMouseDown}
              onMouseMove={handleStageMouseMove}
              onTouchMove={handleStageMouseMove}
              onMouseUp={handleStageMouseUp}
              onTouchEnd={handleStageMouseUp}
            >
              <Layer ref={layerRef} x={offsetX} y={offsetY} scaleX={fitScale} scaleY={fitScale}>
                {canvasWidth > 0 && canvasHeight > 0 && (
                  <Rect
                    name="canvas-border"
                    x={0}
                    y={0}
                    width={canvasWidth}
                    height={canvasHeight}
                    stroke="#4a7dff"
                    strokeWidth={1 / fitScale}
                    listening={false}
                  />
                )}
                {layers.map((layer) => {
                  const img = images[layer.id];
                  if (!img) return null;
                  const width = layer.width ?? img.naturalWidth;
                  const height = layer.height ?? img.naturalHeight;
                  if (!width || !height) return null;
                  return (
                    <KonvaImage
                      key={layer.id}
                      ref={(node) => {
                        imageNodeRefs.current[layer.id] = node;
                      }}
                      image={img}
                      x={layer.x}
                      y={layer.y}
                      width={width}
                      height={height}
                      rotation={layer.rotation}
                      opacity={layer.opacity}
                      visible={layer.visible}
                      listening={layer.visible && layersListenable}
                      draggable={layer.visible && interactive}
                      onClick={() => setSelectedLayerId(layer.id)}
                      onTap={() => setSelectedLayerId(layer.id)}
                      onDragEnd={() => handleDragEnd(layer)}
                      onTransformEnd={() => handleTransformEnd(layer)}
                    />
                  );
                })}
                {brush.canvas && !brush.isEmpty && canvasWidth > 0 && canvasHeight > 0 && (
                  <KonvaImage
                    image={brush.canvas}
                    x={0}
                    y={0}
                    width={canvasWidth}
                    height={canvasHeight}
                    opacity={0.4}
                    listening={false}
                  />
                )}
                {tool === 'motion' && canvasWidth > 0 && canvasHeight > 0 && (
                  <TrajectoryOverlay
                    layers={layers}
                    selectedLayerId={selectedLayerId}
                    fitScale={fitScale}
                    canvasWidth={canvasWidth}
                    canvasHeight={canvasHeight}
                    busy={!!busy}
                    onPointDragMove={handleTrajectoryPointDragMove}
                    onPointDragEnd={handleTrajectoryPointDragEnd}
                  />
                )}
                <Transformer ref={transformerRef} resizeEnabled rotateEnabled />
              </Layer>
            </Stage>
          )}
        </div>

        {selectedProjectId && (
          <div className="editor-right-column">
            <MotionPanel
              selectedLayer={selectedLayer}
              busy={!!busy}
              onSetStatic={handleSetMotionStatic}
              onCommitDescription={handleCommitMotionDescription}
              onClearTrajectory={handleClearTrajectory}
              cameraMove={cameraMove}
              onCameraMoveChange={setCameraMove}
              cameraMagnitude={cameraMagnitude}
              onCameraMagnitudeChange={setCameraMagnitude}
              cameraPrompt={cameraPrompt}
              onCameraPromptChange={setCameraPrompt}
              videoProviders={videoProviders}
              videoProvidersError={videoProvidersError}
              videoProviderId={videoProviderId}
              onVideoProviderChange={setVideoProviderId}
              clipDuration={clipDuration}
              onClipDurationChange={setClipDuration}
              compiling={compiling}
              compileResult={compileResult}
              onCompile={() => void handleCompileMotion()}
              compilePromptDraft={compilePromptDraft}
              onCompilePromptDraftChange={setCompilePromptDraft}
              onSubmit={() => void handleSubmitVideoJob()}
            />
            <InspectorPanel
              selectedLayer={selectedLayer}
              busy={!!busy}
              providers={providers}
              providersError={providersError}
              aiEditPrompt={aiEditPrompt}
              onAiEditPromptChange={setAiEditPrompt}
              aiEditProviderId={aiEditProviderId}
              onAiEditProviderChange={setAiEditProviderId}
              onRunAiEdit={() => void handleRunAiEdit()}
              brushStrokeCount={brush.strokeCount}
              onClearBrush={brush.clear}
              inpaintPrompt={inpaintPrompt}
              onInpaintPromptChange={setInpaintPrompt}
              onRunInpaintBehind={() => void handleRunInpaintBehind()}
              segmentText={segmentText}
              onSegmentTextChange={setSegmentText}
              onRunSegment={() => void handleRunSegment()}
              segmentStatus={segmentStatus}
            />
          </div>
        )}
      </div>

      <div className="status-strip">
        <span>
          <span className={`dot ${apiOnline === null ? 'checking' : apiOnline ? 'online' : 'offline'}`} />
          API {apiOnline === null ? 'checking...' : apiOnline ? 'online' : 'offline'}
        </span>
        <span>Project: {project ? project.name : '—'}</span>
        <span>Layer: {selectedLayer ? selectedLayer.name : '—'}</span>
        {runningClipsCount > 0 && <span>Klipy: {runningClipsCount} běží</span>}
        <span className="spacer" />
        <span className="status-op">
          {busy ? (
            <>
              <span className="spinner" aria-hidden="true" />
              {busy.op}
            </>
          ) : (
            (saveStatus ?? 'Ready')
          )}
        </span>
      </div>
    </div>
  );
}
