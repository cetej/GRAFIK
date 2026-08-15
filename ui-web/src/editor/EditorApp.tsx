import { useEffect, useMemo, useRef, useState, type DragEvent } from 'react';
import Konva from 'konva';
import { Stage, Layer, Image as KonvaImage, Rect, Circle, Transformer } from 'react-konva';
import {
  listProjects,
  getProject,
  listLayers,
  layerPngUrl,
  compositeUrl,
  saveTransform,
  toggleVisibility,
  listProviders,
  aiEditLayer,
  inpaintBehind,
  reorderLayer,
  segmentProject,
  segmentProjectPoint,
  segmentProjectPoints,
  segmentProjectBox,
  createProject,
  decomposeFile,
  exportPng,
  deleteLayer,
  renameLayer,
  renameProject,
  duplicateProject,
  deleteProject,
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
  listTrash,
  restoreTrashEntry,
  emptyTrash,
  purgeTrashEntry,
  getProjectCosts,
  getSessionCosts,
  attachProjectCost,
  generateImage,
  decomposeLayer,
  detectText,
  rewriteText,
  projectThumbnailUrl,
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
  type TrashItem,
  type CostsSummary,
  type GenerateImageResponse,
  type SegmentBoxDto,
} from './api';
import Toolbar, { vrstvyWord } from './Toolbar';
import InspectorPanel from './InspectorPanel';
import LayersPanel from './LayersPanel';
import MotionPanel from './MotionPanel';
import ClipsPanel from './ClipsPanel';
import Section from './Section';
import TrajectoryOverlay, { TRAJECTORY_ANCHOR_NAME } from './TrajectoryOverlay';
import { useBrush } from './useBrush';
import type { Tool, BusyState, CanvasPoint } from './types';
import './EditorApp.css';

type EditorLayer = LayerResponse;

const CANVAS_PADDING = 32;

/** Alpha hit-test threshold for drawHitFromCache (M6-UX1) — empirically tuned so nearly-transparent
 * edge pixels (feathered/antialiased borders) don't register a click; only pixels above this alpha
 * count as part of a layer's clickable hit region. */
const ALPHA_HIT_THRESHOLD = 40;

/** Generate-modal reference images (M5): hard cap + downscale target for NB Pro reference_b64. */
const MAX_GEN_REFS = 3;
const MAX_REF_EDGE_PX = 1024;

/** localStorage key for the one-time first-run gesture hint (M2.5). */
const FIRST_RUN_HINT_KEY = 'grafik.firstRunHint.v1';

/** "15. 8. 14:03" (current year) or "22. 3. 2025 14:03" from an ISO timestamp; empty when missing/invalid. */
function formatDateShort(iso: string): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const withYear = d.getFullYear() !== new Date().getFullYear();
  return d.toLocaleString('cs-CZ', {
    day: 'numeric',
    month: 'numeric',
    ...(withYear ? { year: 'numeric' } : {}),
    hour: '2-digit',
    minute: '2-digit',
  });
}

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
      segPointsCount: number;
      segBoxActive: boolean;
      hoveredPanelLayerId: string | null;
      hoverTarget: string | null;
    };
    __brushCanvas?: HTMLCanvasElement | null;
  }
}

function sortByZAsc(items: EditorLayer[]): EditorLayer[] {
  return [...items].sort((a, b) => a.z_order - b.z_order);
}

/** True when both id lists have the same members in the same order (used to decide whether a
 * click landed on the same overlapping-layer stack as the previous one — see handleLayerClick). */
function sameIdOrder(a: string[], b: string[]): boolean {
  return a.length === b.length && a.every((v, i) => v === b[i]);
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

  // --- M6-UX1 additions: canvas hover-highlight (from LayersPanel) + hit-test hover status ---
  const [hoveredPanelLayerId, setHoveredPanelLayerId] = useState<string | null>(null);
  const [hoverTarget, setHoverTarget] = useState<{ name: string; count: number } | null>(null);
  const lastClickRef = useRef<{ x: number; y: number; ids: string[] } | null>(null);
  const hoverRafRef = useRef(false);

  // --- M2.5 additions: onboarding (drag&drop + shared file input), project
  // management (inline rename), first-run hint ---
  const [numLayers, setNumLayers] = useState(4);
  const [dragActive, setDragActive] = useState(false);
  const [editingProjectId, setEditingProjectId] = useState<string | null>(null);
  const [hintDismissed, setHintDismissed] = useState(
    () => localStorage.getItem(FIRST_RUN_HINT_KEY) === '1',
  );
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [pngVersions, setPngVersions] = useState<Record<string, number>>({});
  const [history, setHistory] = useState<{ undo_count: number; redo_count: number } | null>(null);

  // --- M4 additions: trash (soft-delete), cost summaries, NB Pro generation,
  // recursive layer decomposition ---
  const [trashItems, setTrashItems] = useState<TrashItem[]>([]);
  const [trashError, setTrashError] = useState<string | null>(null);
  const [projectCosts, setProjectCosts] = useState<CostsSummary | null>(null);
  const [sessionCosts, setSessionCosts] = useState<CostsSummary | null>(null);
  const [genOpen, setGenOpen] = useState(false);
  const [genPrompt, setGenPrompt] = useState('');
  const [genAspect, setGenAspect] = useState('1:1');
  const [genSize, setGenSize] = useState('2K');
  const [genBusy, setGenBusy] = useState(false);
  const [genResult, setGenResult] = useState<GenerateImageResponse | null>(null);
  const [genRefs, setGenRefs] = useState<{ b64: string; label: string }[]>([]);
  const [subLayers, setSubLayers] = useState(3);

  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [providersError, setProvidersError] = useState<string | null>(null);
  const [aiEditPrompt, setAiEditPrompt] = useState('');
  const [aiEditProviderId, setAiEditProviderId] = useState<string | null>(null);
  const [cropInpaint, setCropInpaint] = useState(true);
  const [inpaintPrompt, setInpaintPrompt] = useState('');
  const [segmentText, setSegmentText] = useState('');
  const [segmentStatus, setSegmentStatus] = useState<string | null>(null);
  // --- M5 additions: segment box-drag + multi-point (whole-object segmentation) ---
  const [segPoints, setSegPoints] = useState<CanvasPoint[]>([]);
  const [segBoxDraft, setSegBoxDraft] = useState<{ x1: number; y1: number; x2: number; y2: number } | null>(null);
  const segDragStartRef = useRef<CanvasPoint | null>(null);

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
    let timer: number | undefined;
    const attempt = () => {
      listProjects()
        .then((list) => {
          if (cancelled) return;
          setProjects(list);
          setApiOnline(true);
          setProjectsError(null);
        })
        .catch((err: unknown) => {
          if (cancelled) return;
          setApiOnline(false);
          setProjectsError(describeError(err));
          // API down (typicky server po restartu stroje neběží) — zkoušej dál,
          // ať se UI samo zotaví, jakmile backend naběhne.
          timer = window.setTimeout(attempt, 5000);
        });
    };
    attempt();
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, []);

  // Load the trash + session-cost summary whenever the API comes (back) online —
  // mount-only fetches stay permanently broken after a cold start without backend.
  useEffect(() => {
    if (apiOnline !== true) return;
    listTrash()
      .then(setTrashItems)
      .catch(() => {});
    getSessionCosts()
      .then(setSessionCosts)
      .catch(() => {});
  }, [apiOnline]);

  // Load the image-edit provider list whenever the API comes (back) online
  // (independent of project selection).
  useEffect(() => {
    if (apiOnline !== true) return;
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
  }, [apiOnline]);

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

  // Load the video-job provider list whenever the API comes (back) online
  // (separate kind from the AI-edit list above).
  useEffect(() => {
    if (apiOnline !== true) return;
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
  }, [apiOnline]);

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
        setBanner(`Nepodařilo se načíst PNG vrstvy „${name}".`);
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
        node.drawHitFromCache(ALPHA_HIT_THRESHOLD);
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

  // M6-UX1: hover state is purely a transient pointer hint — drop it whenever a blocking
  // operation starts, so a stale highlight/status line doesn't survive the context switch.
  useEffect(() => {
    if (busy) {
      setHoveredPanelLayerId(null);
      setHoverTarget(null);
    }
  }, [busy]);

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

  // M5: leaving the segment tool clears any in-progress box drag / accumulated multi-point set —
  // switching tools (or projects, which resets tool to 'select') must not leave stale draft state.
  useEffect(() => {
    if (tool !== 'segment') {
      setSegPoints([]);
      setSegBoxDraft(null);
      segDragStartRef.current = null;
    }
  }, [tool]);

  // M5: Enter confirms the accumulated segment multi-point set (Shift+klik), Escape cancels the
  // current draft (points and/or an in-progress box) — only wired while the segment tool is active.
  useEffect(() => {
    if (tool !== 'segment') return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Enter') {
        if (segPoints.length > 0 && !busy) {
          e.preventDefault();
          void handleSegmentMultiPoint();
        }
      } else if (e.key === 'Escape') {
        setSegPoints([]);
        setSegBoxDraft(null);
      }
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
    // handleSegmentMultiPoint is a plain function recreated every render; omitting it is safe
    // because its only external closure values are `segPoints` (already a dep) and
    // `selectedProjectId`, and every path that changes selectedProjectId (handleSelectProject)
    // also flips `tool` away from 'segment' first — which already tears this listener down.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tool, segPoints, busy]);

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
      segPointsCount: segPoints.length,
      segBoxActive: segBoxDraft !== null,
      hoveredPanelLayerId,
      hoverTarget: hoverTarget?.name ?? null,
    };
  }, [
    fitScale,
    offsetX,
    offsetY,
    canvasWidth,
    canvasHeight,
    selectedLayerId,
    selectedProjectId,
    busy,
    tool,
    segPoints,
    segBoxDraft,
    hoveredPanelLayerId,
    hoverTarget,
  ]);

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

  async function refreshTrash() {
    try {
      setTrashItems(await listTrash());
      setTrashError(null);
    } catch (err) {
      setTrashError(describeError(err));
    }
  }

  /** Refresh the cost summaries (project + API session). Called after every paid operation. */
  async function refreshCosts(projectId: string | null = selectedProjectId) {
    try {
      setSessionCosts(await getSessionCosts());
      if (projectId) setProjectCosts(await getProjectCosts(projectId));
    } catch {
      // Non-critical — keep the last known summary.
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
    setSegPoints([]);
    setSegBoxDraft(null);
    setHoveredPanelLayerId(null);
    setHoverTarget(null);
    setPngVersions({});
    setHistory(null);
    setTool('select');
    setClips([]);
    setClipVideoVersions({});
    setCompileResult(null);
    setCompilePromptDraft('');
    setProjectCosts(null);
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
      void refreshCosts(id);
    } catch (err) {
      setBanner(`Načtení projektu selhalo: ${describeError(err)}`);
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
      setBanner(`Nepodařilo se znovu načíst vrstvy: ${describeError(err)}`);
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
    setSaveStatus(`Ukládám: ${label} vrstvy „${layer.name}"…`);
    saveTransform(projectId, layer.id, patch)
      .then(() => {
        setSaveStatus(`Uloženo: ${label} vrstvy „${layer.name}".`);
        void refreshHistory(projectId);
      })
      .catch((err: unknown) => {
        setBanner(`Uložení transformace selhalo: ${describeError(err)}`);
        setSaveStatus(`Uložení selhalo: ${label} vrstvy „${layer.name}".`);
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
    setSaveStatus(`Ukládám: ${label}…`);
    const call = empty ? clearLayerMotion(projectId, layer.id) : saveLayerMotion(projectId, layer.id, nextMotion);
    call
      .then((updated) => {
        setLayers((prev) => prev.map((l) => (l.id === layer.id ? updated : l)));
        setSaveStatus(`Uloženo: ${label}.`);
        void refreshHistory(projectId);
      })
      .catch((err: unknown) => {
        setBanner(`Uložení pohybu selhalo: ${describeError(err)}`);
        setSaveStatus(`Uložení selhalo: ${label}.`);
        void reloadLayers(projectId);
      });
  }

  function handleSetMotionStatic(layer: EditorLayer, value: boolean) {
    const current = layer.motion ?? EMPTY_MOTION;
    persistMotion(layer, { ...current, static: value }, 'pohyb (statický)');
  }

  function handleCommitMotionDescription(layer: EditorLayer, description: string) {
    const current = layer.motion ?? EMPTY_MOTION;
    if (current.description === description) return;
    persistMotion(layer, { ...current, description }, 'pohyb (popis)');
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
    commitTransform(layer, { x: Math.round(node.x()), y: Math.round(node.y()) }, 'pozice');
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
    node.drawHitFromCache(ALPHA_HIT_THRESHOLD);
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
      'transformace',
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
        setBanner(`Přepnutí viditelnosti selhalo: ${describeError(err)}`);
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
      setBanner(`Přeřazení vrstvy selhalo: ${describeError(err)}`);
    } finally {
      setBusy(null);
    }
  }

  async function handleDeleteLayer(layer: EditorLayer) {
    const projectId = selectedProjectId;
    if (!projectId) return;
    if (!window.confirm(`Smazat vrstvu „${layer.name || layer.id}"?`)) return;
    setBusy({ op: `Mažu vrstvu „${layer.name}"…` });
    try {
      await deleteLayer(projectId, layer.id);
      if (selectedLayerId === layer.id) setSelectedLayerId(null);
      await reloadLayers(projectId);
      await refreshHistory(projectId);
      setSaveStatus(`Vrstva „${layer.name}" smazána.`);
    } catch (err) {
      setBanner(`Smazání vrstvy selhalo: ${describeError(err)}`);
    } finally {
      setBusy(null);
    }
  }

  async function handleUndo() {
    const projectId = selectedProjectId;
    if (!projectId) return;
    setBusy({ op: 'Beru zpět…' });
    try {
      await undoProject(projectId);
      const newLayers = await reloadLayers(projectId);
      if (newLayers) bumpAllPngVersions(newLayers);
      await refreshHistory(projectId);
      setSaveStatus('Vráceno zpět.');
    } catch (err) {
      setBanner(`Zpět selhalo: ${describeError(err)}`);
    } finally {
      setBusy(null);
    }
  }

  async function handleRedo() {
    const projectId = selectedProjectId;
    if (!projectId) return;
    setBusy({ op: 'Provádím znovu…' });
    try {
      await redoProject(projectId);
      const newLayers = await reloadLayers(projectId);
      if (newLayers) bumpAllPngVersions(newLayers);
      await refreshHistory(projectId);
      setSaveStatus('Provedeno znovu.');
    } catch (err) {
      setBanner(`Znovu selhalo: ${describeError(err)}`);
    } finally {
      setBusy(null);
    }
  }

  async function handleRunAiEdit() {
    const projectId = selectedProjectId;
    const layer = selectedLayer;
    const prompt = aiEditPrompt.trim();
    if (!projectId || !layer || !aiEditProviderId || !prompt) return;
    setBusy({ op: 'AI úprava běží… může trvat desítky sekund' });
    try {
      const maskB64 = brush.isEmpty ? null : brush.exportMaskB64();
      const resp = await aiEditLayer(projectId, layer.id, {
        prompt,
        provider: aiEditProviderId,
        crop_inpaint: cropInpaint,
        ...(maskB64 ? { mask_b64: maskB64 } : {}),
      });
      applyLayerUpdate(resp.layer);
      setSaveStatus(`AI úprava hotova (${resp.provider}, ${resp.elapsed_s.toFixed(1)}s).`);
      await refreshHistory(projectId);
      void refreshCosts();
    } catch (err) {
      setBanner(`AI úprava selhala: ${describeError(err)}`);
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
      const resp = await inpaintBehind(projectId, layer.id, {
        ...(prompt ? { prompt } : {}),
        crop_inpaint: cropInpaint,
      });
      applyLayerUpdate(resp.layer);
      setSaveStatus(`Pozadí vyplněno (${resp.provider}, ${resp.elapsed_s.toFixed(1)}s).`);
      await refreshHistory(projectId);
      void refreshCosts();
    } catch (err) {
      setBanner(`Vyplnění pozadí selhalo: ${describeError(err)}`);
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
      void refreshCosts();
    } catch (err) {
      setBanner(`Segmentace selhala: ${describeError(err)}`);
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
      setBanner(`Export selhal: ${describeError(err)}`);
    } finally {
      setBusy(null);
    }
  }

  async function handleCreateFromImage(file: File, layerCount: number) {
    setBusy({ op: `Dekompozice na ${layerCount} ${vrstvyWord(layerCount)} běží…` });
    try {
      const name = file.name.replace(/\.[^./]+$/, '') || 'untitled';
      const proj = await createProject(name);
      await decomposeFile(proj.id, file, layerCount);
      const list = await listProjects();
      setProjects(list);
      await handleSelectProject(proj.id);
      // M6-UX1 auto-detect: a failure here must not fail the whole import — the project is
      // already usable at this point, so only the status line reports it.
      setBusy({ op: 'Detekuji textové vrstvy…' });
      try {
        setSaveStatus(await runDetectText(proj.id));
        await refreshHistory(proj.id);
        void refreshCosts(proj.id);
      } catch (err) {
        setSaveStatus(`Detekce textu selhala: ${describeError(err)}`);
      }
    } catch (err) {
      setBanner(`Nový projekt z obrázku selhal: ${describeError(err)}`);
    } finally {
      setBusy(null);
    }
  }

  async function refreshProjects() {
    try {
      setProjects(await listProjects());
      setProjectsError(null);
    } catch (err) {
      setProjectsError(describeError(err));
    }
  }

  async function handleDeleteProject(p: ProjectListItem) {
    if (busy) return;
    if (!window.confirm(`Přesunout projekt „${p.name}" do koše? Obnovit ho pak lze v sekci Koš.`)) return;
    setBusy({ op: `Přesouvám projekt „${p.name}" do koše…` });
    try {
      await deleteProject(p.id);
      if (selectedProjectId === p.id) {
        setSelectedProjectId(null);
        setProject(null);
        setLayers([]);
        setSelectedLayerId(null);
        setClips([]);
        setHistory(null);
        setProjectCosts(null);
      }
      await refreshProjects();
      await refreshTrash();
      setSaveStatus(`Projekt „${p.name}" přesunut do koše.`);
    } catch (err) {
      setBanner(`Smazání projektu selhalo: ${describeError(err)}`);
    } finally {
      setBusy(null);
    }
  }

  async function handleRestoreTrash(item: TrashItem) {
    if (busy) return;
    setBusy({ op: `Obnovuji projekt „${item.name}" z koše…` });
    try {
      const restored = await restoreTrashEntry(item.entry);
      await refreshProjects();
      await refreshTrash();
      setSaveStatus(`Projekt „${restored.name}" obnoven z koše.`);
    } catch (err) {
      setBanner(`Obnovení z koše selhalo: ${describeError(err)}`);
    } finally {
      setBusy(null);
    }
  }

  async function handleEmptyTrash() {
    if (busy || trashItems.length === 0) return;
    if (
      !window.confirm(
        `Trvale smazat všechny projekty v koši (${trashItems.length})? Tuto akci nelze vrátit.`,
      )
    )
      return;
    setBusy({ op: 'Vysypávám koš…' });
    try {
      const resp = await emptyTrash();
      await refreshTrash();
      setSaveStatus(`Koš vysypán (${resp.purged} položek).`);
    } catch (err) {
      setBanner(`Vysypání koše selhalo: ${describeError(err)}`);
    } finally {
      setBusy(null);
    }
  }

  /** M5: per-entry permanent delete (Koš keeps ↩ restore; this is the irreversible companion). */
  async function handlePurgeTrashEntry(item: TrashItem) {
    if (busy) return;
    if (!window.confirm(`Trvale smazat „${item.name}" z koše? Tuto akci nelze vrátit.`)) return;
    setBusy({ op: `Trvale mažu „${item.name}" z koše…` });
    try {
      await purgeTrashEntry(item.entry);
      await refreshTrash();
      setSaveStatus(`Projekt „${item.name}" trvale smazán z koše.`);
    } catch (err) {
      setBanner(`Trvalé smazání z koše selhalo: ${describeError(err)}`);
    } finally {
      setBusy(null);
    }
  }

  /** One paid NB Pro call (~$0.13) → preview in the dialog. Modal-local busy,
   * not the global gate — canvas operations are untouched while generating. */
  async function handleGenerateImage() {
    const prompt = genPrompt.trim();
    if (!prompt || genBusy) return;
    setGenBusy(true);
    try {
      setGenResult(
        await generateImage({
          prompt,
          aspect_ratio: genAspect,
          image_size: genSize,
          ...(genRefs.length > 0 ? { reference_b64: genRefs.map((r) => r.b64) } : {}),
        }),
      );
      void refreshCosts();
    } catch (err) {
      setBanner(`Generování obrázku selhalo: ${describeError(err)}`);
    } finally {
      setGenBusy(false);
    }
  }

  function b64ToFile(b64: string, filename: string): File {
    const bytes = atob(b64);
    const arr = new Uint8Array(bytes.length);
    for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i);
    return new File([arr], filename, { type: 'image/png' });
  }

  /** Downscales a source image to at most MAX_REF_EDGE_PX on its longer edge and returns it as a
   * base64 PNG (no data: prefix) — the shape NB Pro's reference_b64 expects. */
  async function blobToRefB64(blob: Blob): Promise<string> {
    const bitmap = await createImageBitmap(blob);
    try {
      const scale = Math.min(1, MAX_REF_EDGE_PX / Math.max(bitmap.width, bitmap.height));
      const w = Math.max(1, Math.round(bitmap.width * scale));
      const h = Math.max(1, Math.round(bitmap.height * scale));
      const canvas = document.createElement('canvas');
      canvas.width = w;
      canvas.height = h;
      const ctx = canvas.getContext('2d');
      if (!ctx) throw new Error('2D canvas kontext nedostupný');
      ctx.drawImage(bitmap, 0, 0, w, h);
      const dataUrl = canvas.toDataURL('image/png');
      const comma = dataUrl.indexOf(',');
      return comma >= 0 ? dataUrl.slice(comma + 1) : dataUrl;
    } finally {
      bitmap.close();
    }
  }

  /** Adds one reference image (from an uploaded File or a fetched Blob) to genRefs, silently capped
   * at MAX_GEN_REFS — used by all three reference sources (file picker, composite, selected layer). */
  async function addGenRef(blob: Blob, label: string) {
    if (genRefs.length >= MAX_GEN_REFS) return;
    try {
      const b64 = await blobToRefB64(blob);
      setGenRefs((prev) => (prev.length >= MAX_GEN_REFS ? prev : [...prev, { b64, label }]));
    } catch (err) {
      setBanner(`Načtení referenčního obrázku selhalo: ${describeError(err)}`);
    }
  }

  /** Reference sources (b)/(c): fetch a same-origin API image (project composite / layer PNG) and
   * feed it through the same downscale-and-add path as an uploaded file. */
  async function addGenRefFromUrl(url: string, label: string) {
    if (genRefs.length >= MAX_GEN_REFS) return;
    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      await addGenRef(await res.blob(), label);
    } catch (err) {
      setBanner(`Načtení referenčního obrázku selhalo: ${describeError(err)}`);
    }
  }

  function handleAddCompositeRef() {
    if (!selectedProjectId) return;
    void addGenRefFromUrl(compositeUrl(selectedProjectId), 'kompozit projektu');
  }

  function handleAddSelectedLayerRef() {
    if (!selectedProjectId || !selectedLayer) return;
    void addGenRefFromUrl(layerPngUrl(selectedProjectId, selectedLayer.id), `vrstva „${selectedLayer.name}"`);
  }

  /** Adopt the generated preview: new project + attach the generation cost to
   * its ledger + the standard decompose flow (same path as an uploaded file). */
  async function handleAdoptGenerated() {
    const result = genResult;
    if (!result || busy) return;
    const name = genPrompt.trim().slice(0, 40) || 'generováno';
    setGenOpen(false);
    setBusy({ op: `Dekompozice na ${numLayers} ${vrstvyWord(numLayers)} běží…` });
    try {
      const proj = await createProject(name);
      await attachProjectCost(proj.id, result.cost);
      await decomposeFile(proj.id, b64ToFile(result.image_b64, `${name}.png`), numLayers);
      setProjects(await listProjects());
      await handleSelectProject(proj.id);
      setGenResult(null);
      setGenPrompt('');
      setGenRefs([]);
      // M6-UX1 auto-detect (see handleCreateFromImage) — its status message is the final one shown.
      setBusy({ op: 'Detekuji textové vrstvy…' });
      try {
        setSaveStatus(await runDetectText(proj.id));
        await refreshHistory(proj.id);
        void refreshCosts(proj.id);
      } catch (err) {
        setSaveStatus(`Detekce textu selhala: ${describeError(err)}`);
      }
    } catch (err) {
      setBanner(`Převzetí vygenerovaného obrázku selhalo: ${describeError(err)}`);
    } finally {
      setBusy(null);
    }
  }

  /** Recursive decomposition: replaces the selected layer with sub-layers (undo restores it). */
  async function handleRunLayerDecompose() {
    const projectId = selectedProjectId;
    const layer = selectedLayer;
    if (!projectId || !layer) return;
    setBusy({ op: `Rozkládám vrstvu „${layer.name}" na ${subLayers} pod${vrstvyWord(subLayers)}…` });
    try {
      const subs = await decomposeLayer(projectId, layer.id, subLayers);
      await reloadLayers(projectId);
      setSelectedLayerId(subs[0]?.id ?? null);
      await refreshHistory(projectId);
      void refreshCosts();
      setSaveStatus(`Vrstva „${layer.name}" rozložena na ${subs.length} pod${vrstvyWord(subs.length)}.`);
    } catch (err) {
      setBanner(`Rozložení vrstvy selhalo: ${describeError(err)}`);
    } finally {
      setBusy(null);
    }
  }

  /**
   * Runs SAM text detection over the whole project and applies the refreshed layer list
   * (is_text/text_score/text_original/text_current). Shared core for both the manual "Detekovat
   * text" button (handleDetectText below) and the auto-detect step after a fresh decomposition
   * (handleCreateFromImage/handleAdoptGenerated) — those two call sites differ in how loudly they
   * surface a failure, so error handling stays with the caller.
   */
  async function runDetectText(projectId: string): Promise<string> {
    const resp = await detectText(projectId);
    setLayers(sortByZAsc(resp.layers));
    const count = resp.layers.filter((l) => l.is_text).length;
    return count > 0 ? `Nalezeno ${count} textových vrstev.` : 'Žádné textové vrstvy nenalezeny.';
  }

  /** Manual trigger (Vrstvy section header button, M6-UX1) — own busy gate + refreshCosts, failure
   * surfaced as a banner like the other segment/ai-edit handlers. */
  async function handleDetectText() {
    const projectId = selectedProjectId;
    if (!projectId) return;
    setBusy({ op: 'Detekuji textové vrstvy…' });
    try {
      setSaveStatus(await runDetectText(projectId));
      await refreshHistory(projectId);
      void refreshCosts();
    } catch (err) {
      setBanner(`Detekce textu selhala: ${describeError(err)}`);
    } finally {
      setBusy(null);
    }
  }

  /** Text-layer rewrite (M6-UX1) — pixel mutation, same optimistic-update shape as handleRunAiEdit. */
  async function handleRewriteText(layer: EditorLayer, newText: string, originalText: string) {
    const projectId = selectedProjectId;
    const trimmedNew = newText.trim();
    if (!projectId || !trimmedNew) return;
    setBusy({ op: 'Přepisuji text vrstvy…' });
    try {
      const resp = await rewriteText(projectId, layer.id, {
        new_text: trimmedNew,
        ...(originalText.trim() ? { original_text: originalText.trim() } : {}),
        crop_inpaint: cropInpaint,
      });
      applyLayerUpdate(resp.layer);
      setSaveStatus(`Text přepsán (${resp.provider}, ${resp.elapsed_s.toFixed(1)}s).`);
      await refreshHistory(projectId);
      void refreshCosts();
    } catch (err) {
      setBanner(`Přepis textu selhal: ${describeError(err)}`);
    } finally {
      setBusy(null);
    }
  }

  async function handleDuplicateProject(p: ProjectListItem) {
    if (busy) return;
    setBusy({ op: `Duplikuji projekt „${p.name}"…` });
    try {
      const copy = await duplicateProject(p.id);
      await refreshProjects();
      setSaveStatus(`Projekt zduplikován jako „${copy.name}".`);
    } catch (err) {
      setBanner(`Duplikace projektu selhala: ${describeError(err)}`);
    } finally {
      setBusy(null);
    }
  }

  function handleCommitProjectRename(p: ProjectListItem, name: string) {
    setEditingProjectId(null);
    const trimmed = name.trim();
    if (!trimmed || trimmed === p.name) return;
    setProjects((prev) => prev.map((x) => (x.id === p.id ? { ...x, name: trimmed } : x)));
    setSaveStatus(`Přejmenovávám projekt na „${trimmed}"…`);
    renameProject(p.id, trimmed)
      .then((updated) => {
        setProject((prev) => (prev && prev.id === p.id ? { ...prev, name: updated.name } : prev));
        setSaveStatus(`Projekt přejmenován na „${updated.name}".`);
        void refreshProjects();
      })
      .catch((err: unknown) => {
        setBanner(`Přejmenování projektu selhalo: ${describeError(err)}`);
        void refreshProjects();
      });
  }

  function handleRenameLayer(layer: EditorLayer, name: string) {
    const projectId = selectedProjectId;
    if (!projectId) return;
    const trimmed = name.trim();
    if (!trimmed || trimmed === layer.name) return;
    setLayers((prev) => prev.map((l) => (l.id === layer.id ? { ...l, name: trimmed } : l)));
    setSaveStatus(`Přejmenovávám vrstvu na „${trimmed}"…`);
    renameLayer(projectId, layer.id, trimmed)
      .then((updated) => {
        setLayers((prev) => prev.map((l) => (l.id === updated.id ? updated : l)));
        setSaveStatus(`Vrstva přejmenována na „${updated.name}".`);
        void refreshHistory(projectId);
      })
      .catch((err: unknown) => {
        setBanner(`Přejmenování vrstvy selhalo: ${describeError(err)}`);
        void reloadLayers(projectId);
      });
  }

  /** Segment-tool canvas click → one paid SAM point call (~$0.005) → new layer, selected. */
  async function handleSegmentPointClick(pt: CanvasPoint) {
    const projectId = selectedProjectId;
    if (!projectId) return;
    const x = Math.round(pt.x);
    const y = Math.round(pt.y);
    setBusy({ op: `Segmentuji prvek na (${x}, ${y})…` });
    try {
      const resp = await segmentProjectPoint(projectId, x, y);
      await reloadLayers(projectId);
      const created = resp.layers[0];
      if (created) setSelectedLayerId(created.id);
      const msg = created
        ? `Vytvořena vrstva „${created.name}" z kliknutí.`
        : 'SAM v místě kliknutí nic nenašel.';
      setSegmentStatus(msg);
      setSaveStatus(msg);
      void refreshCosts();
    } catch (err) {
      setBanner(`Segmentace kliknutím selhala: ${describeError(err)}`);
    } finally {
      setBusy(null);
    }
  }

  /** Segment-tool box drag → one paid SAM box call (whole object) → new layer, selected. */
  async function handleSegmentBoxDrag(box: SegmentBoxDto) {
    const projectId = selectedProjectId;
    if (!projectId) return;
    setBusy({ op: `Segmentuji rámeček (${box.x_min}, ${box.y_min})–(${box.x_max}, ${box.y_max})…` });
    try {
      const resp = await segmentProjectBox(projectId, box);
      await reloadLayers(projectId);
      const created = resp.layers[0];
      if (created) setSelectedLayerId(created.id);
      const msg = created ? `Vytvořena vrstva „${created.name}" z rámečku.` : 'SAM v rámečku nic nenašel.';
      setSegmentStatus(msg);
      setSaveStatus(msg);
      void refreshCosts();
    } catch (err) {
      setBanner(`Segmentace rámečkem selhala: ${describeError(err)}`);
    } finally {
      setBusy(null);
    }
  }

  /** Segment-tool Shift+klik multi-point set, confirmed with Enter → one paid SAM call spanning all
   * accumulated points (same object_id) → new layer, selected. */
  async function handleSegmentMultiPoint() {
    const projectId = selectedProjectId;
    if (!projectId || segPoints.length === 0) return;
    const count = segPoints.length;
    setBusy({ op: `Segmentuji ${count} bodů…` });
    try {
      const resp = await segmentProjectPoints(
        projectId,
        segPoints.map((p) => ({ x: Math.round(p.x), y: Math.round(p.y), label: 1, object_id: 0 })),
      );
      await reloadLayers(projectId);
      const created = resp.layers[0];
      if (created) setSelectedLayerId(created.id);
      const msg = created
        ? `Vytvořena vrstva „${created.name}" z ${count} bodů.`
        : 'SAM v zadaných bodech nic nenašel.';
      setSegmentStatus(msg);
      setSaveStatus(msg);
      setSegPoints([]);
      void refreshCosts();
    } catch (err) {
      setBanner(`Segmentace body selhala: ${describeError(err)}`);
    } finally {
      setBusy(null);
    }
  }

  // --- M2.5 drag&drop: an image dropped anywhere on the canvas area starts a
  // brand-new project + decomposition (same path as the file picker). ---

  function handleCanvasDragOver(e: DragEvent<HTMLDivElement>) {
    if (busy) return;
    if (Array.from(e.dataTransfer.types).includes('Files')) {
      e.preventDefault();
      setDragActive(true);
    }
  }

  function handleCanvasDragLeave(e: DragEvent<HTMLDivElement>) {
    // dragleave also fires when entering a child — only clear when actually
    // leaving the container.
    if (!e.currentTarget.contains(e.relatedTarget as Node | null)) {
      setDragActive(false);
    }
  }

  function handleCanvasDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragActive(false);
    if (busy) return;
    const file = e.dataTransfer.files?.[0];
    if (!file) return;
    if (!file.type.startsWith('image/')) {
      setBanner('Přetažený soubor není obrázek.');
      return;
    }
    void handleCreateFromImage(file, numLayers);
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
      setBanner(`Kompilace promptu selhala: ${describeError(err)}`);
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
      void refreshCosts();
    } catch (err) {
      setBanner(`Odeslání video úlohy selhalo: ${describeError(err)}`);
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
      // A full-bleed background layer means canvas clicks practically never reach the empty
      // Stage itself (M3 E2E finding), so "click on empty background" can't be the add-point
      // gesture. Instead: with a layer selected, ANY click inside the canvas rect adds a point
      // — except on a trajectory anchor, whose drag must not spawn extra points. Selection
      // switches via LayersPanel (or by canvas click while nothing is selected yet).
      if (e.target.name?.() === TRAJECTORY_ANCHOR_NAME) return;
      if (selectedLayer) {
        const pt = getCanvasPoint();
        if (pt && pt.x >= 0 && pt.x <= canvasWidth && pt.y >= 0 && pt.y <= canvasHeight) {
          handleAddTrajectoryPoint(selectedLayer, pt);
        }
      }
      return;
    }
    if (tool === 'segment') {
      // Layers don't listen in segment mode, so every canvas gesture lands on the Stage (same
      // "every click is the tool's action" pattern as motion, see the M3 full-bleed-background
      // finding). Mousedown only stakes out the drag start — mouseup below measures the total
      // distance moved to decide klik (point) vs. tažení (box).
      const pt = getCanvasPoint();
      if (pt && pt.x >= 0 && pt.x <= canvasWidth && pt.y >= 0 && pt.y <= canvasHeight) {
        segDragStartRef.current = pt;
        setSegBoxDraft({ x1: pt.x, y1: pt.y, x2: pt.x, y2: pt.y });
      }
      return;
    }
    // Every other Stage-background click: only treat as "deselect" in select
    // mode, so a selection made before switching tools survives the round trip.
    if (tool === 'select' && e.target === stageRef.current) {
      setSelectedLayerId(null);
    }
  }

  function handleStageMouseMove(e: Konva.KonvaEventObject<MouseEvent | TouchEvent>) {
    if (busy) return;
    if (tool === 'brush') {
      const pt = getCanvasPoint();
      if (pt) brush.continueStroke(pt);
      return;
    }
    if (tool === 'segment' && segDragStartRef.current) {
      const pt = getCanvasPoint();
      if (pt) {
        const x2 = Math.max(0, Math.min(canvasWidth, pt.x));
        const y2 = Math.max(0, Math.min(canvasHeight, pt.y));
        setSegBoxDraft((prev) => (prev ? { ...prev, x2, y2 } : prev));
      }
    }
    // M6-UX1: hover status for the status strip ("Klik vybere: …") — select tool, idle (no mouse
    // button held, i.e. not mid-drag/resize). TouchEvent has no .buttons, so the `in` check makes
    // touch-move simply fall through to clearing the hint instead of computing it.
    if (tool === 'select' && 'buttons' in e.evt && e.evt.buttons === 0) {
      updateHoverTarget();
    } else if (hoverTarget) {
      setHoverTarget(null);
    }
  }

  function handleStageMouseUp(e: Konva.KonvaEventObject<MouseEvent | TouchEvent>) {
    if (tool === 'brush') brush.endStroke();
    if (tool === 'segment') {
      const start = segDragStartRef.current;
      const draft = segBoxDraft;
      segDragStartRef.current = null;
      setSegBoxDraft(null);
      if (!start || !draft || busy) return;
      const dist = Math.hypot(draft.x2 - draft.x1, draft.y2 - draft.y1);
      if (dist < 5 / fitScale) {
        // KLIK: no shift + no accumulated points yet → immediate single-point call (unchanged
        // pre-M5 behavior). Otherwise (shift held, or already building a multi-point set) just
        // accumulate — Enter confirms the whole set via handleSegmentMultiPoint.
        const pt = {
          x: Math.max(0, Math.min(canvasWidth, Math.round(start.x))),
          y: Math.max(0, Math.min(canvasHeight, Math.round(start.y))),
        };
        if (!e.evt.shiftKey && segPoints.length === 0) {
          void handleSegmentPointClick(pt);
        } else {
          setSegPoints((prev) => [...prev, pt]);
        }
        return;
      }
      // TAŽENÍ: a real drag → whole-object box segmentation.
      const box: SegmentBoxDto = {
        x_min: Math.max(0, Math.min(canvasWidth, Math.round(Math.min(draft.x1, draft.x2)))),
        y_min: Math.max(0, Math.min(canvasHeight, Math.round(Math.min(draft.y1, draft.y2)))),
        x_max: Math.max(0, Math.min(canvasWidth, Math.round(Math.max(draft.x1, draft.x2)))),
        y_max: Math.max(0, Math.min(canvasHeight, Math.round(Math.max(draft.y1, draft.y2)))),
      };
      void handleSegmentBoxDrag(box);
    }
  }

  /** Every overlapping "layer-image" node under the pointer, topmost (highest z_order) first. */
  function intersectingLayerIds(pos: { x: number; y: number }): string[] {
    const stage = stageRef.current;
    if (!stage) return [];
    const zOrderById = new Map(layers.map((l) => [l.id, l.z_order]));
    const raw = stage
      .getAllIntersections(pos)
      .filter((n) => n.name() === 'layer-image')
      .map((n) => n.id());
    return [...new Set(raw)].sort((a, b) => (zOrderById.get(b) ?? 0) - (zOrderById.get(a) ?? 0));
  }

  /**
   * Shared onClick/onTap for every layer image (M6-UX1). Repeated clicks at the same spot (<= 4px,
   * same overlapping stack) cycle top-down through overlapping layers instead of always reselecting
   * the topmost one; a click anywhere else (or a different stack) just selects the topmost hit.
   */
  function handleLayerClick() {
    // In motion mode with a selection, canvas clicks add trajectory points (Stage mousedown) —
    // don't let them also switch layers. Same guard the old per-node handler carried.
    if (tool === 'motion' && selectedLayerId) return;
    const stage = stageRef.current;
    const pos = stage?.getPointerPosition();
    if (!pos) return;
    const ids = intersectingLayerIds(pos);
    if (ids.length === 0) return;
    const last = lastClickRef.current;
    const samePlace = !!last && Math.hypot(pos.x - last.x, pos.y - last.y) <= 4 && sameIdOrder(last.ids, ids);
    const nextId =
      samePlace && selectedLayerId && ids.includes(selectedLayerId)
        ? ids[(ids.indexOf(selectedLayerId) + 1) % ids.length]
        : ids[0];
    lastClickRef.current = { x: pos.x, y: pos.y, ids };
    setSelectedLayerId(nextId);
  }

  /** rAF-throttled hover-stack lookup for the status strip's "Klik vybere: …" hint (M6-UX1). */
  function updateHoverTarget() {
    if (hoverRafRef.current) return;
    hoverRafRef.current = true;
    requestAnimationFrame(() => {
      hoverRafRef.current = false;
      const stage = stageRef.current;
      const pos = stage?.getPointerPosition();
      if (!pos) {
        setHoverTarget(null);
        return;
      }
      const ids = intersectingLayerIds(pos);
      if (ids.length === 0) {
        setHoverTarget(null);
        return;
      }
      const top = layers.find((l) => l.id === ids[0]);
      setHoverTarget({ name: top?.name || ids[0], count: ids.length });
    });
  }

  /** Thumbnail <img> src for LayersPanel — same URL Konva's own loader uses, so the browser's HTTP
   * cache serves it with no extra request (M6-UX1). Only ever rendered while a project is selected. */
  function getLayerThumbUrl(layer: EditorLayer): string {
    return layerPngUrl(selectedProjectId ?? '', layer.id, false, pngVersions[layer.id] ?? 0);
  }

  const sortedForList = useMemo(() => [...layers].sort((a, b) => b.z_order - a.z_order), [layers]);
  const selectedLayer = layers.find((l) => l.id === selectedLayerId) ?? null;
  // draggable/Transformer stay select-only (unchanged); listening also opens up in motion mode so
  // a layer can still be clicked to select it there (see handleStageMouseDown).
  const interactive = tool === 'select' && !busy;
  const layersListenable = (tool === 'select' || tool === 'motion') && !busy;
  const runningClipsCount = clips.filter((c) => c.status === 'running' || c.status === 'pending').length;

  // M6-UX1: canvas hover-highlight (from LayersPanel) — only "active" once the hovered layer is
  // both visible and its image has actually loaded, same guard the Transformer-attach effect uses.
  const hoveredLayer = hoveredPanelLayerId ? (layers.find((l) => l.id === hoveredPanelLayerId) ?? null) : null;
  const hoveredImg = hoveredLayer ? images[hoveredLayer.id] : undefined;
  const hoverActive = !!hoveredLayer && hoveredLayer.visible && !!hoveredImg;
  const hoverRectW = hoveredLayer && hoveredImg ? (hoveredLayer.width ?? hoveredImg.naturalWidth) : 0;
  const hoverRectH = hoveredLayer && hoveredImg ? (hoveredLayer.height ?? hoveredImg.naturalHeight) : 0;

  // M6-UX1: permanent selection outline for modes where the Transformer isn't attached (see the
  // Transformer-attach effect above — it only connects during idle 'select').
  const selectedImg = selectedLayer ? images[selectedLayer.id] : undefined;
  const showSelectedOutline = (tool !== 'select' || !!busy) && !!selectedLayer && !!selectedImg;
  const selectedRectW = selectedLayer && selectedImg ? (selectedLayer.width ?? selectedImg.naturalWidth) : 0;
  const selectedRectH = selectedLayer && selectedImg ? (selectedLayer.height ?? selectedImg.naturalHeight) : 0;

  return (
    <div className="editor-root">
      {banner && (
        <div className="editor-banner">
          <span>{banner}</span>
          <button onClick={() => setBanner(null)}>Zavřít</button>
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
        numLayers={numLayers}
        onNumLayersChange={setNumLayers}
        onNewFromImageClick={() => fileInputRef.current?.click()}
        onGenerateClick={() => setGenOpen(true)}
        brushSize={brush.brushSize}
        onBrushSizeChange={brush.setBrushSize}
        brushStrokeCount={brush.strokeCount}
        onBrushClear={brush.clear}
      />

      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        className="hidden-file-input"
        onChange={(e) => {
          const file = e.target.files?.[0] ?? null;
          e.target.value = '';
          if (file) void handleCreateFromImage(file, numLayers);
        }}
      />

      {tool === 'segment' && (
        <div className="segment-hint">
          Klik = část · tažení = rámeček (celý objekt) · Shift+klik = víc bodů, Enter potvrdí
        </div>
      )}

      <div className="editor-body">
        <aside className="editor-sidebar">
          <h1>GRAFIK Editor</h1>
          <Section title="Projekty">
            {projectsError && <p className="editor-hint error">Chyba: {projectsError}</p>}
            {projects.length === 0 && !projectsError && (
              <p className="editor-hint">Zatím žádné projekty — nahrajte obrázek.</p>
            )}
            {projects.map((p) => (
              <div
                key={p.id}
                className={`project-item${p.id === selectedProjectId ? ' selected' : ''}`}
                onClick={() => void handleSelectProject(p.id)}
              >
                <img
                  className="project-thumb"
                  src={projectThumbnailUrl(p.id, p.updated_at)}
                  alt=""
                  loading="lazy"
                  onError={(e) => {
                    e.currentTarget.style.display = 'none';
                  }}
                />
                {editingProjectId === p.id ? (
                  <input
                    className="rename-input"
                    autoFocus
                    defaultValue={p.name}
                    onClick={(e) => e.stopPropagation()}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') handleCommitProjectRename(p, (e.target as HTMLInputElement).value);
                      if (e.key === 'Escape') setEditingProjectId(null);
                    }}
                    onBlur={(e) => handleCommitProjectRename(p, e.target.value)}
                  />
                ) : (
                  <span className="name" title={`${p.name} — ${p.layer_count} ${vrstvyWord(p.layer_count)}`}>
                    {p.name}
                  </span>
                )}
                <span className="meta">{formatDateShort(p.updated_at)}</span>
                <span className="project-actions">
                  <button
                    type="button"
                    className="icon-btn"
                    disabled={!!busy}
                    title="Přejmenovat projekt"
                    onClick={(e) => {
                      e.stopPropagation();
                      setEditingProjectId(p.id);
                    }}
                  >
                    ✎
                  </button>
                  <button
                    type="button"
                    className="icon-btn"
                    disabled={!!busy}
                    title="Duplikovat projekt"
                    onClick={(e) => {
                      e.stopPropagation();
                      void handleDuplicateProject(p);
                    }}
                  >
                    ⧉
                  </button>
                  <button
                    type="button"
                    className="icon-btn"
                    disabled={!!busy}
                    title="Smazat projekt"
                    onClick={(e) => {
                      e.stopPropagation();
                      void handleDeleteProject(p);
                    }}
                  >
                    🗑
                  </button>
                </span>
              </div>
            ))}
          </Section>
          <Section
            title="Koš"
            defaultOpen={false}
            badge={trashItems.length > 0 ? trashItems.length : undefined}
            onOpen={() => void refreshTrash()}
          >
            {trashError && <p className="editor-hint error">Chyba: {trashError}</p>}
            {trashItems.length === 0 && !trashError && <p className="editor-hint">Koš je prázdný.</p>}
            {trashItems.map((t) => (
              <div key={t.entry} className="trash-item">
                <span className="name" title={`${t.name} — ${t.layer_count} ${vrstvyWord(t.layer_count)}`}>
                  {t.name}
                </span>
                <span className="meta">{formatDateShort(t.deleted_at)}</span>
                <button
                  type="button"
                  className="icon-btn"
                  disabled={!!busy}
                  title="Obnovit projekt z koše"
                  onClick={() => void handleRestoreTrash(t)}
                >
                  ↩
                </button>
                <button
                  type="button"
                  className="icon-btn"
                  disabled={!!busy}
                  title="Trvale smazat z koše"
                  onClick={() => void handlePurgeTrashEntry(t)}
                >
                  🗑
                </button>
              </div>
            ))}
            {trashItems.length > 0 && (
              <div className="trash-actions-row">
                <button
                  type="button"
                  className="secondary-btn"
                  disabled={!!busy}
                  onClick={() => void handleEmptyTrash()}
                >
                  Vysypat koš
                </button>
              </div>
            )}
            <p className="editor-hint">Položky starší 30 dní se mažou automaticky.</p>
          </Section>
          {selectedProjectId && (
            <div className="section-flex-grow">
              <Section
                title={`Vrstvy${projectLoading ? ' (načítám…)' : ''}`}
                badge={layers.length}
                headerExtra={
                  <button
                    type="button"
                    className="section-header-btn"
                    disabled={!!busy}
                    title="Označí vrstvy s textem (SAM, ~$0.005)"
                    onClick={() => void handleDetectText()}
                  >
                    🔤 Detekovat text
                  </button>
                }
              >
                <LayersPanel
                  layers={sortedForList}
                  selectedLayerId={selectedLayerId}
                  busy={!!busy}
                  onSelect={setSelectedLayerId}
                  onToggleVisibility={handleToggleVisibility}
                  onReorder={(layer, dir) => void handleReorder(layer, dir)}
                  onDelete={(layer) => void handleDeleteLayer(layer)}
                  onRename={handleRenameLayer}
                  onHoverLayer={setHoveredPanelLayerId}
                  getThumbUrl={getLayerThumbUrl}
                />
              </Section>
            </div>
          )}
          {selectedProjectId && (
            <div className="section-flex-grow">
              <Section title="Klipy">
                <ClipsPanel
                  projectId={selectedProjectId}
                  clips={clips}
                  videoVersions={clipVideoVersions}
                  busy={!!busy}
                  onRetry={handleRetryClip}
                />
              </Section>
            </div>
          )}
          {selectedProjectId && projectCosts && (
            <Section title="Útrata">
              <p className="cost-line">
                Projekt: <strong>${projectCosts.total_usd.toFixed(2)}</strong> · {projectCosts.count}{' '}
                volání
              </p>
              {sessionCosts && (
                <p className="cost-line">
                  Session celkem: ${sessionCosts.total_usd.toFixed(2)} · {sessionCosts.count} volání
                </p>
              )}
              {projectCosts.entries
                .slice(-3)
                .reverse()
                .map((e, i) => (
                  <p key={`${e.ts}-${i}`} className="editor-hint">
                    {e.kind} · {e.endpoint.split('/').pop()} ·{' '}
                    {e.est_usd != null ? `$${e.est_usd.toFixed(3)}` : 'cena neznámá'}
                  </p>
                ))}
            </Section>
          )}
        </aside>

        <div
          className="editor-canvas-area"
          ref={containerRef}
          onDragOver={handleCanvasDragOver}
          onDragLeave={handleCanvasDragLeave}
          onDrop={handleCanvasDrop}
        >
          {apiOnline === false && (
            <div className="editor-empty-state">
              <div className="empty-icon" aria-hidden="true">
                🔌
              </div>
              <h3>API server neběží</h3>
              <p>
                Frontend běží, ale backend na portu 8300 neodpovídá — projekty proto nejsou vidět
                (na disku zůstávají netknuté). Spusťte <code>start-grafik.bat</code> ve složce
                GRAFIK; jakmile server naběhne, tato stránka se obnoví sama.
              </p>
            </div>
          )}
          {apiOnline !== false && !selectedProjectId && (
            <div className="editor-empty-state">
              <div className="empty-icon" aria-hidden="true">
                🖼️
              </div>
              <h3>Začněte obrázkem</h3>
              <p>
                Přetáhněte obrázek sem — rozloží se na {numLayers} {vrstvyWord(numLayers)}, které pak
                upravujete jednotlivě.
              </p>
              <button
                type="button"
                className="primary-btn"
                disabled={!!busy}
                onClick={() => fileInputRef.current?.click()}
              >
                Nahrát nový obrázek
              </button>
              <button
                type="button"
                className="secondary-btn"
                disabled={!!busy}
                title="Vygeneruje vstupní obrázek textem (Nano Banana Pro, ~$0.13)"
                onClick={() => setGenOpen(true)}
              >
                Vygenerovat obrázek
              </button>
              <p className="editor-hint">…nebo vyberte existující projekt vlevo.</p>
            </div>
          )}
          {selectedProjectId && !hintDismissed && !projectLoading && (
            <div className="first-run-hint">
              <span>
                Kliknutím na prvek v obraze se vybere vrstva · tažením ji posunete · rohy mění velikost a
                rotaci
              </span>
              <button
                type="button"
                title="Zavřít nápovědu"
                onClick={() => {
                  localStorage.setItem(FIRST_RUN_HINT_KEY, '1');
                  setHintDismissed(true);
                }}
              >
                ×
              </button>
            </div>
          )}
          {dragActive && (
            <div className="drop-overlay">
              <span>
                Pusťte obrázek — rozloží se na {numLayers} {vrstvyWord(numLayers)} (nový projekt)
              </span>
            </div>
          )}
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
              onMouseLeave={() => setHoverTarget(null)}
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
                  // M6-UX1: dim every other visible layer while one is hovered from LayersPanel.
                  const dimmed = hoverActive && layer.id !== hoveredPanelLayerId;
                  return (
                    <KonvaImage
                      key={layer.id}
                      id={layer.id}
                      name="layer-image"
                      ref={(node) => {
                        imageNodeRefs.current[layer.id] = node;
                      }}
                      image={img}
                      x={layer.x}
                      y={layer.y}
                      width={width}
                      height={height}
                      rotation={layer.rotation}
                      opacity={dimmed ? layer.opacity * 0.25 : layer.opacity}
                      visible={layer.visible}
                      listening={layer.visible && layersListenable}
                      draggable={layer.visible && interactive}
                      onClick={handleLayerClick}
                      onTap={handleLayerClick}
                      onDragEnd={() => handleDragEnd(layer)}
                      onTransformEnd={() => handleTransformEnd(layer)}
                    />
                  );
                })}
                {showSelectedOutline && selectedLayer && (
                  <Rect
                    name="selected-outline"
                    x={selectedLayer.x}
                    y={selectedLayer.y}
                    width={selectedRectW}
                    height={selectedRectH}
                    rotation={selectedLayer.rotation}
                    stroke="#4a9dff"
                    strokeWidth={1.5 / fitScale}
                    listening={false}
                  />
                )}
                {hoverActive && hoveredLayer && (
                  <Rect
                    name="hover-highlight"
                    x={hoveredLayer.x}
                    y={hoveredLayer.y}
                    width={hoverRectW}
                    height={hoverRectH}
                    rotation={hoveredLayer.rotation}
                    stroke="#7cc4ff"
                    dash={[8 / fitScale, 4 / fitScale]}
                    strokeWidth={2 / fitScale}
                    listening={false}
                  />
                )}
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
                {tool === 'segment' && segBoxDraft && (
                  <Rect
                    x={Math.min(segBoxDraft.x1, segBoxDraft.x2)}
                    y={Math.min(segBoxDraft.y1, segBoxDraft.y2)}
                    width={Math.abs(segBoxDraft.x2 - segBoxDraft.x1)}
                    height={Math.abs(segBoxDraft.y2 - segBoxDraft.y1)}
                    stroke="#4a7dff"
                    dash={[6 / fitScale, 4 / fitScale]}
                    strokeWidth={1.5 / fitScale}
                    listening={false}
                  />
                )}
                {tool === 'segment' &&
                  segPoints.map((pt, index) => (
                    <Circle
                      key={`seg-pt-${index}`}
                      x={pt.x}
                      y={pt.y}
                      radius={4 / fitScale}
                      fill="#4a7dff"
                      stroke="#ffffff"
                      strokeWidth={1 / fitScale}
                      listening={false}
                    />
                  ))}
                <Transformer
                  ref={transformerRef}
                  resizeEnabled
                  rotateEnabled
                  borderStroke="#4a9dff"
                  borderStrokeWidth={2}
                  anchorStroke="#4a9dff"
                  anchorSize={10}
                  anchorCornerRadius={2}
                />
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
              cropInpaint={cropInpaint}
              onCropInpaintChange={setCropInpaint}
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
              subLayers={subLayers}
              onSubLayersChange={setSubLayers}
              onRunLayerDecompose={() => void handleRunLayerDecompose()}
              onRewriteText={(layer, newText, originalText) => void handleRewriteText(layer, newText, originalText)}
            />
          </div>
        )}
      </div>

      {genOpen && (
        <div
          className="modal-overlay"
          onClick={() => {
            if (!genBusy) setGenOpen(false);
          }}
        >
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>Vygenerovat obrázek (Nano Banana Pro)</h3>
            <textarea
              placeholder="Popište obrázek, který chcete vygenerovat…"
              value={genPrompt}
              disabled={genBusy}
              onChange={(e) => setGenPrompt(e.target.value)}
            />
            <div className="modal-row">
              <label htmlFor="gen-aspect">Poměr stran</label>
              <select
                id="gen-aspect"
                value={genAspect}
                disabled={genBusy}
                onChange={(e) => setGenAspect(e.target.value)}
              >
                {['1:1', '3:4', '4:3', '16:9', '9:16'].map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
              <label htmlFor="gen-size">Rozlišení</label>
              <select
                id="gen-size"
                value={genSize}
                disabled={genBusy}
                onChange={(e) => setGenSize(e.target.value)}
              >
                {['1K', '2K'].map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
              <span className="editor-hint">~$0.13 / obrázek</span>
            </div>
            <div className="modal-row">
              <input
                type="file"
                accept="image/*"
                multiple
                disabled={genBusy || genRefs.length >= MAX_GEN_REFS}
                onChange={(e) => {
                  const files = Array.from(e.target.files ?? []);
                  e.target.value = '';
                  for (const f of files) void addGenRef(f, f.name);
                }}
              />
              {selectedProjectId && (
                <button
                  type="button"
                  className="secondary-btn"
                  disabled={genBusy || genRefs.length >= MAX_GEN_REFS}
                  onClick={handleAddCompositeRef}
                >
                  + kompozit projektu
                </button>
              )}
              {selectedLayer && (
                <button
                  type="button"
                  className="secondary-btn"
                  disabled={genBusy || genRefs.length >= MAX_GEN_REFS}
                  onClick={handleAddSelectedLayerRef}
                >
                  + vybraná vrstva
                </button>
              )}
            </div>
            {genRefs.length > 0 && (
              <div className="gen-refs-row">
                {genRefs.map((r, i) => (
                  <div key={i} className="gen-ref-thumb">
                    <img src={`data:image/png;base64,${r.b64}`} alt={r.label} title={r.label} />
                    <button
                      type="button"
                      className="gen-ref-remove"
                      disabled={genBusy}
                      title="Odebrat referenci"
                      onClick={() => setGenRefs((prev) => prev.filter((_, idx) => idx !== i))}
                    >
                      ×
                    </button>
                  </div>
                ))}
              </div>
            )}
            <p className="editor-hint">Reference udrží stejnou postavu/styl napříč obrázky (max 3).</p>
            {genResult && (
              <>
                <img
                  className="gen-preview"
                  src={`data:image/png;base64,${genResult.image_b64}`}
                  alt="Vygenerovaný náhled"
                />
                <p className="editor-hint">
                  {genResult.width}×{genResult.height}
                  {genResult.cost.est_usd != null ? ` · ~$${genResult.cost.est_usd.toFixed(2)}` : ''}
                </p>
              </>
            )}
            <div className="modal-actions">
              <button
                type="button"
                className="secondary-btn"
                disabled={genBusy || !genPrompt.trim()}
                onClick={() => void handleGenerateImage()}
              >
                {genBusy ? 'Generuji…' : genResult ? 'Vygenerovat znovu' : 'Vygenerovat'}
              </button>
              {genResult && (
                <button
                  type="button"
                  className="primary-btn"
                  disabled={genBusy || !!busy}
                  onClick={() => void handleAdoptGenerated()}
                >
                  Převzít → rozložit na {numLayers} {vrstvyWord(numLayers)}
                </button>
              )}
              <button
                type="button"
                className="secondary-btn"
                disabled={genBusy}
                onClick={() => setGenOpen(false)}
              >
                Zavřít
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="status-strip">
        <span>
          <span className={`dot ${apiOnline === null ? 'checking' : apiOnline ? 'online' : 'offline'}`} />
          API {apiOnline === null ? 'ověřuji…' : apiOnline ? 'online' : 'offline'}
        </span>
        <span>Projekt: {project ? project.name : '—'}</span>
        <span>Vrstva: {selectedLayer ? selectedLayer.name : '—'}</span>
        {hoverTarget && (
          <span>
            Klik vybere: {hoverTarget.name}
            {hoverTarget.count > 1
              ? ` · ${hoverTarget.count} vrstvy pod kurzorem — opakovaný klik je střídá`
              : ''}
          </span>
        )}
        {project && projectCosts && <span>Útrata: ${projectCosts.total_usd.toFixed(2)}</span>}
        {runningClipsCount > 0 && <span>Klipy: {runningClipsCount} běží</span>}
        <span className="spacer" />
        <span className="status-op">
          {busy ? (
            <>
              <span className="spinner" aria-hidden="true" />
              {busy.op}
            </>
          ) : (
            (saveStatus ?? 'Připraveno')
          )}
        </span>
      </div>
    </div>
  );
}
