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
  ApiError,
  type ProjectListItem,
  type ProjectResponse,
  type LayerResponse,
  type TransformRequestBody,
  type ProviderInfo,
} from './api';
import Toolbar from './Toolbar';
import InspectorPanel from './InspectorPanel';
import LayersPanel from './LayersPanel';
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
    };
  }, [fitScale, offsetX, offsetY, canvasWidth, canvasHeight, selectedLayerId, selectedProjectId, busy]);

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
    setProjectLoading(true);
    try {
      const [proj, layerList, hist] = await Promise.all([getProject(id), listLayers(id), getHistory(id)]);
      setProject(proj);
      setLayers(sortByZAsc(layerList.map((l) => ({ ...l }))));
      setHistory(hist);
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
  const interactive = tool === 'select' && !busy;

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
                      listening={layer.visible && interactive}
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
                <Transformer ref={transformerRef} resizeEnabled rotateEnabled />
              </Layer>
            </Stage>
          )}
        </div>

        {selectedProjectId && (
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
        )}
      </div>

      <div className="status-strip">
        <span>
          <span className={`dot ${apiOnline === null ? 'checking' : apiOnline ? 'online' : 'offline'}`} />
          API {apiOnline === null ? 'checking...' : apiOnline ? 'online' : 'offline'}
        </span>
        <span>Project: {project ? project.name : '—'}</span>
        <span>Layer: {selectedLayer ? selectedLayer.name : '—'}</span>
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
