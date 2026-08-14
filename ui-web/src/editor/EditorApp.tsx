import { useEffect, useMemo, useRef, useState } from 'react';
import type Konva from 'konva';
import { Stage, Layer, Image as KonvaImage, Rect, Transformer } from 'react-konva';
import {
  listProjects,
  getProject,
  listLayers,
  layerPngUrl,
  saveTransform,
  toggleVisibility,
  ApiError,
  type ProjectListItem,
  type ProjectResponse,
  type LayerResponse,
  type TransformRequestBody,
} from './api';
import './EditorApp.css';

/**
 * LayerResponse has no `rotation` field (see api.ts doc comment) even though
 * the backend persists one. We track it client-side only: it starts at 0 for
 * every freshly-loaded layer and is updated locally after a successful
 * transform. A page reload cannot recover a previously-saved rotation from
 * the API — this is a backend DTO gap, not something fixable from ui-web/.
 */
interface EditorLayer extends LayerResponse {
  rotation: number;
}

const CANVAS_PADDING = 32;

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

  const containerRef = useRef<HTMLDivElement | null>(null);
  const stageRef = useRef<Konva.Stage | null>(null);
  const layerRef = useRef<Konva.Layer | null>(null);
  const transformerRef = useRef<Konva.Transformer | null>(null);
  const imageNodeRefs = useRef<Record<string, Konva.Image | null>>({});
  const cachedIdsRef = useRef<Set<string>>(new Set());

  // Stable key that only changes when the *set* of layer ids changes, not on
  // every transform/visibility update (which replace `layers` with a new
  // array of the same ids). Used to avoid re-fetching PNGs on every save.
  const layerIdsKey = useMemo(() => layers.map((l) => l.id).join(','), [layers]);

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

  // Load a PNG per layer whenever the loaded project's layer *set* changes.
  useEffect(() => {
    imageNodeRefs.current = {};
    cachedIdsRef.current = new Set();
    setImages({});
    if (!selectedProjectId || layers.length === 0) return;

    let cancelled = false;
    const idsAndNames = layers.map((l) => ({ id: l.id, name: l.name }));
    for (const { id, name } of idsAndNames) {
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
      img.src = layerPngUrl(selectedProjectId, id);
    }
    return () => {
      cancelled = true;
    };
    // layerIdsKey (not `layers`) is the intended dependency — see its comment above.
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

  // Keep the Transformer attached to whichever layer is currently selected.
  useEffect(() => {
    const tr = transformerRef.current;
    if (!tr) return;
    const node = selectedLayerId ? imageNodeRefs.current[selectedLayerId] : null;
    tr.nodes(node ? [node] : []);
    tr.getLayer()?.batchDraw();
  }, [selectedLayerId, images]);

  const canvasWidth = project?.canvas_width ?? 0;
  const canvasHeight = project?.canvas_height ?? 0;

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

  async function handleSelectProject(id: string) {
    if (id === selectedProjectId) return;
    setSelectedProjectId(id);
    setSelectedLayerId(null);
    setProject(null);
    setLayers([]);
    setSaveStatus(null);
    setProjectLoading(true);
    try {
      const [proj, layerList] = await Promise.all([getProject(id), listLayers(id)]);
      setProject(proj);
      setLayers(sortByZAsc(layerList.map((l) => ({ ...l, rotation: 0 }))));
    } catch (err) {
      setBanner(`Failed to load project: ${describeError(err)}`);
    } finally {
      setProjectLoading(false);
    }
  }

  async function reloadLayers(projectId: string) {
    try {
      const layerList = await listLayers(projectId);
      setLayers(sortByZAsc(layerList.map((l) => ({ ...l, rotation: 0 }))));
    } catch (err) {
      setBanner(`Failed to reload layers: ${describeError(err)}`);
    }
  }

  function commitTransform(layer: EditorLayer, patch: TransformRequestBody, label: string) {
    const projectId = selectedProjectId;
    if (!projectId) return;
    setLayers((prev) => prev.map((l) => (l.id === layer.id ? { ...l, ...patch } : l)));
    setSaveStatus(`Saving ${label} of layer "${layer.name}"...`);
    saveTransform(projectId, layer.id, patch)
      .then(() => {
        setSaveStatus(`Saved ${label} of layer "${layer.name}".`);
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
    toggleVisibility(projectId, layer.id).catch((err: unknown) => {
      setBanner(`Failed to toggle visibility: ${describeError(err)}`);
      setLayers((prev) => prev.map((l) => (l.id === layer.id ? { ...l, visible: prevVisible } : l)));
    });
  }

  function handleStageMouseDown(e: Konva.KonvaEventObject<MouseEvent | TouchEvent>) {
    if (e.target === stageRef.current) {
      setSelectedLayerId(null);
    }
  }

  const sortedForList = useMemo(() => [...layers].sort((a, b) => b.z_order - a.z_order), [layers]);
  const selectedLayer = layers.find((l) => l.id === selectedLayerId) ?? null;

  return (
    <div className="editor-root">
      {banner && (
        <div className="editor-banner">
          <span>{banner}</span>
          <button onClick={() => setBanner(null)}>Close</button>
        </div>
      )}
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
            <div className="editor-section editor-section-layers">
              <h2>Layers{projectLoading ? ' (loading...)' : ''}</h2>
              {sortedForList.map((layer) => (
                <div
                  key={layer.id}
                  className={`layer-item${layer.id === selectedLayerId ? ' selected' : ''}`}
                  onClick={() => setSelectedLayerId(layer.id)}
                >
                  <button
                    className={`eye${layer.visible ? '' : ' hidden'}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      handleToggleVisibility(layer);
                    }}
                    title={layer.visible ? 'Hide layer' : 'Show layer'}
                  >
                    👁
                  </button>
                  <span className="name">{layer.name || layer.id}</span>
                </div>
              ))}
            </div>
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
            >
              <Layer ref={layerRef} x={offsetX} y={offsetY} scaleX={fitScale} scaleY={fitScale}>
                {canvasWidth > 0 && canvasHeight > 0 && (
                  <Rect
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
                      listening={layer.visible}
                      draggable={layer.visible}
                      onClick={() => setSelectedLayerId(layer.id)}
                      onTap={() => setSelectedLayerId(layer.id)}
                      onDragEnd={() => handleDragEnd(layer)}
                      onTransformEnd={() => handleTransformEnd(layer)}
                    />
                  );
                })}
                <Transformer ref={transformerRef} resizeEnabled rotateEnabled />
              </Layer>
            </Stage>
          )}
        </div>
      </div>

      <div className="status-strip">
        <span>
          <span className={`dot ${apiOnline === null ? 'checking' : apiOnline ? 'online' : 'offline'}`} />
          API {apiOnline === null ? 'checking...' : apiOnline ? 'online' : 'offline'}
        </span>
        <span>Project: {project ? project.name : '—'}</span>
        <span>Layer: {selectedLayer ? selectedLayer.name : '—'}</span>
        <span className="spacer" />
        <span>{saveStatus ?? 'Ready'}</span>
      </div>
    </div>
  );
}
