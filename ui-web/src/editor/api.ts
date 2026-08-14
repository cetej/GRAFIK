/**
 * Typed fetch client for the GRAFIK FastAPI backend (grafik/api/app.py).
 *
 * Route shapes were read directly from grafik/api/app.py + grafik/api/models.py
 * (read-only) rather than assumed. Two surprises worth flagging:
 *
 * 1. GET /api/projects/{id} returns ProjectResponse, which does NOT include a
 *    `layers` array (only `layer_count`). Actual layer data comes from the
 *    separate GET /api/projects/{id}/layers route (`listLayers` below) — the
 *    two are combined by the caller.
 */

const API_BASE: string = import.meta.env.VITE_API_URL ?? 'http://localhost:8300';

export type BlendMode = 'normal' | 'multiply' | 'screen' | 'overlay' | 'soft_light';

export interface ProjectListItem {
  id: string;
  name: string;
  path: string;
  layer_count: number;
}

export interface ProjectResponse {
  id: string;
  name: string;
  canvas_width: number;
  canvas_height: number;
  layer_count: number;
  created_at: string;
  updated_at: string;
}

export interface LayerResponse {
  id: string;
  name: string;
  z_order: number;
  visible: boolean;
  opacity: number;
  blend_mode: BlendMode;
  x: number;
  y: number;
  width: number | null;
  height: number | null;
  rotation: number;
  source: string;
  tags: string[];
}

/** Body for POST /api/projects/{id}/layers/{layerId}/transform. All fields optional — only sent fields are applied server-side. */
export interface TransformRequestBody {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  rotation?: number;
}

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, init);
  } catch (err) {
    throw new ApiError(`Network error calling ${path}: ${err instanceof Error ? err.message : String(err)}`, 0);
  }
  if (!res.ok) {
    let detail = '';
    try {
      const body: unknown = await res.json();
      const maybeDetail = (body as { detail?: unknown } | null)?.detail;
      detail = typeof maybeDetail === 'string' ? maybeDetail : JSON.stringify(body);
    } catch {
      // Response body wasn't JSON — fall back to the status text below.
    }
    throw new ApiError(detail || `${res.status} ${res.statusText} (${path})`, res.status);
  }
  return (await res.json()) as T;
}

export function listProjects(): Promise<ProjectListItem[]> {
  return request<ProjectListItem[]>('/api/projects');
}

export function getProject(id: string): Promise<ProjectResponse> {
  return request<ProjectResponse>(`/api/projects/${id}`);
}

export function listLayers(projectId: string): Promise<LayerResponse[]> {
  return request<LayerResponse[]>(`/api/projects/${projectId}/layers`);
}

/** Direct <img>-able URL for a layer's RGBA PNG. `checker` overlays a checkerboard so transparency is visible. */
export function layerPngUrl(projectId: string, layerId: string, checker = false): string {
  const query = checker ? '?checker=true' : '';
  return `${API_BASE}/api/projects/${projectId}/layers/${layerId}/png${query}`;
}

export function saveTransform(
  projectId: string,
  layerId: string,
  body: TransformRequestBody,
): Promise<LayerResponse> {
  return request<LayerResponse>(`/api/projects/${projectId}/layers/${layerId}/transform`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

/** POST toggle route — flips the server's current value, so there is no request body. */
export function toggleVisibility(projectId: string, layerId: string): Promise<LayerResponse> {
  return request<LayerResponse>(`/api/projects/${projectId}/layers/${layerId}/visibility`, {
    method: 'POST',
  });
}
