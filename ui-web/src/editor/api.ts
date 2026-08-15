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
  created_at: string;
  updated_at: string;
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
  motion: LayerMotionDto | null;
  /** M6-UX1: text-layer detection (SAM-based) — see detectText/rewriteText below. */
  is_text: boolean;
  text_score: number | null;
  text_original: string | null;
  text_current: string | null;
}

// --- M3: motion / video (per-layer trajectory, camera intent, async clip jobs) ---

export interface TrajectoryPointDto {
  x: number;
  y: number;
}

export interface LayerMotionDto {
  trajectory: TrajectoryPointDto[];
  static: boolean;
  description: string;
}

/**
 * Body for POST /api/projects/{id}/layers/{layerId}/motion. Fields are optional server-side, but
 * the frontend always sends the FULL current motion state (see persistMotion in EditorApp) to
 * sidestep any ambiguity about merge-vs-replace semantics on partial payloads.
 */
export interface LayerMotionRequestBody {
  trajectory?: TrajectoryPointDto[];
  static?: boolean;
  description?: string;
}

export type CameraMove =
  | 'none'
  | 'pan_left'
  | 'pan_right'
  | 'tilt_up'
  | 'tilt_down'
  | 'zoom_in'
  | 'zoom_out'
  | 'custom';

export interface CameraSpecDto {
  move: CameraMove;
  magnitude: number;
  prompt: string;
}

export interface MotionSpecDto {
  camera: CameraSpecDto;
  duration: string;
  layer_motions: Record<string, LayerMotionDto>;
}

export type MotionWanted = 'move' | 'still';
export type VerifyVerdict = 'yes' | 'weak' | 'no';

export interface ElementVerdictDto {
  layer_id: string;
  layer_name: string;
  wanted: MotionWanted;
  in_motion: number;
  out_motion: number;
  ratio: number;
  verdict: VerifyVerdict;
}

export interface ClipVerificationDto {
  verified_at: string;
  frame_size: number[];
  frames_sampled: number;
  global_motion: number;
  elements: ElementVerdictDto[];
  summary: string;
}

export type ClipStatus = 'pending' | 'running' | 'completed' | 'failed';

export interface ClipRecordDto {
  id: string;
  created_at: string;
  provider_id: string;
  endpoint: string;
  status: ClipStatus;
  request_id: string;
  path: string;
  prompt: string;
  motion: MotionSpecDto | null;
  cost_note: string;
  error: string;
  verification: ClipVerificationDto | null;
}

/** Body for POST /api/projects/{id}/video/compile — a cheap preview call (no fal.ai network I/O). */
export interface CompileMotionRequestBody {
  motion: MotionSpecDto;
  provider: string;
}

export interface CompileMotionResponse {
  prompt: string;
  provider: string;
  endpoint: string;
  duration: string;
  est_cost_usd: number | null;
  price_note: string;
  payload_preview: Record<string, unknown>;
}

/**
 * Body for POST /api/projects/{id}/video/jobs. `prompt_override`, when non-empty, is used verbatim
 * instead of the server-compiled prompt (still persisted onto the resulting ClipRecord.prompt).
 */
export interface SubmitVideoJobRequestBody {
  motion: MotionSpecDto;
  provider: string;
  prompt_override?: string;
}

/** Body for POST /api/projects/{id}/layers/{layerId}/transform. All fields optional — only sent fields are applied server-side. */
export interface TransformRequestBody {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  rotation?: number;
}

export type ProviderKind = 'image_edit' | 'video' | 'segment' | 'image_gen' | 'decompose';

export interface ProviderCapabilities {
  supports_mask: boolean;
  supports_dynamic_masks: boolean;
  supports_camera_params: boolean;
  supports_camera_preset: boolean;
  supports_camera_prompt: boolean;
  verified_at: string;
  notes: string;
}

export interface ProviderInfo {
  id: string;
  endpoint: string;
  kind: ProviderKind;
  capabilities: ProviderCapabilities;
  price_note: string;
  has_impl: boolean;
  /** Name of the fal.ai payload field the composite image URL is sent under (drifts per endpoint — e.g. "image_url" vs "start_image_url"). */
  image_field: string;
  /** Endpoint-specific fal.ai payload fields merged into every video job build (e.g. forcing generate_audio: false). */
  payload_defaults: Record<string, unknown>;
  /** Valid values for the video job's `duration` field on this provider. */
  duration_choices: string[];
  /** Secondary-sourced, unverified $/s rate. Null when no price could be found. */
  est_cost_usd_per_second: number | null;
}

/** Body for POST /api/projects/{id}/layers/{layerId}/ai-edit. mask_b64 is a base64 PNG (no data: prefix), canvas-sized, white = editable area. */
export interface AiEditRequestBody {
  prompt: string;
  provider: string;
  dilate_px?: number;
  feather_px?: number;
  mask_b64?: string;
  /** M5: crop around a small mask and edit at full resolution instead of the whole (possibly
   * downscaled) composite. Server defaults to true when omitted. */
  crop_inpaint?: boolean;
}

export interface AiEditResponse {
  layer: LayerResponse;
  provider: string;
  elapsed_s: number;
}

/** Body for POST /api/projects/{id}/layers/{layerId}/inpaint-behind. */
export interface InpaintBehindRequestBody {
  prompt?: string;
  provider?: string;
  /** M5: same crop_inpaint plumbing as AiEditRequestBody — see there. */
  crop_inpaint?: boolean;
}

export interface InpaintBehindResponse {
  /** The CHANGED background layer, not the target layer named in the URL. */
  layer: LayerResponse;
  provider: string;
  elapsed_s: number;
}

export interface SegmentResponse {
  layers: LayerResponse[];
  mask_count: number;
}

export interface HistoryResponse {
  undo_count: number;
  redo_count: number;
}

export interface UndoRedoResponse {
  undone?: boolean;
  redone?: boolean;
}

export interface DeleteLayerResponse {
  deleted: string;
}

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

/** Extracts a `{detail}` message from a non-ok JSON error response, falling back to the status line, then throws. */
async function throwForError(res: Response, path: string): Promise<never> {
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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, init);
  } catch (err) {
    throw new ApiError(`Network error calling ${path}: ${err instanceof Error ? err.message : String(err)}`, 0);
  }
  if (!res.ok) await throwForError(res, path);
  return (await res.json()) as T;
}

const JSON_HEADERS = { 'Content-Type': 'application/json' };

export function listProjects(): Promise<ProjectListItem[]> {
  return request<ProjectListItem[]>('/api/projects');
}

export function getProject(id: string): Promise<ProjectResponse> {
  return request<ProjectResponse>(`/api/projects/${id}`);
}

export function listLayers(projectId: string): Promise<LayerResponse[]> {
  return request<LayerResponse[]>(`/api/projects/${projectId}/layers`);
}

/**
 * Direct <img>-able URL for a layer's RGBA PNG. `checker` overlays a checkerboard so
 * transparency is visible. `version` is a client-side cache-buster (see pngVersions in
 * EditorApp) — bump it after a mutation so the <img> actually re-fetches instead of
 * reusing a cached response for the same URL.
 */
export function layerPngUrl(projectId: string, layerId: string, checker = false, version?: number): string {
  const params = new URLSearchParams();
  if (checker) params.set('checker', 'true');
  if (version !== undefined) params.set('v', String(version));
  const query = params.toString();
  return `${API_BASE}/api/projects/${projectId}/layers/${layerId}/png${query ? `?${query}` : ''}`;
}

/** Direct <img>-able / fetch-able URL for a project's full RGBA composite PNG (M5: used to seed
 * NB Pro reference images from the current canvas). */
export function compositeUrl(projectId: string): string {
  return `${API_BASE}/api/projects/${projectId}/composite`;
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

export function listProviders(kind?: ProviderKind): Promise<ProviderInfo[]> {
  const query = kind ? `?kind=${encodeURIComponent(kind)}` : '';
  return request<ProviderInfo[]>(`/api/providers${query}`);
}

export function aiEditLayer(projectId: string, layerId: string, body: AiEditRequestBody): Promise<AiEditResponse> {
  return request<AiEditResponse>(`/api/projects/${projectId}/layers/${layerId}/ai-edit`, {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  });
}

export function inpaintBehind(
  projectId: string,
  layerId: string,
  body: InpaintBehindRequestBody,
): Promise<InpaintBehindResponse> {
  return request<InpaintBehindResponse>(`/api/projects/${projectId}/layers/${layerId}/inpaint-behind`, {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  });
}

/** Whole updated layer list (server re-sorts by z_order internally; caller should not assume order). */
export function reorderLayer(projectId: string, layerId: string, zOrder: number): Promise<LayerResponse[]> {
  return request<LayerResponse[]>(`/api/projects/${projectId}/layers/${layerId}/reorder`, {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ z_order: zOrder }),
  });
}

export function segmentProject(projectId: string, text: string): Promise<SegmentResponse> {
  return request<SegmentResponse>(`/api/projects/${projectId}/segment`, {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ text }),
  });
}

export function renameProject(id: string, name: string): Promise<ProjectResponse> {
  return request<ProjectResponse>(`/api/projects/${id}`, {
    method: 'PATCH',
    headers: JSON_HEADERS,
    body: JSON.stringify({ name }),
  });
}

export function duplicateProject(id: string): Promise<ProjectResponse> {
  return request<ProjectResponse>(`/api/projects/${id}/duplicate`, { method: 'POST' });
}

/** M4 soft-delete: the project moves into projects/.trash (see listTrash/restoreTrashEntry). */
export function deleteProject(id: string): Promise<{ deleted: string; trash_entry: string }> {
  return request<{ deleted: string; trash_entry: string }>(`/api/projects/${id}`, { method: 'DELETE' });
}

export function renameLayer(projectId: string, layerId: string, name: string): Promise<LayerResponse> {
  return request<LayerResponse>(`/api/projects/${projectId}/layers/${layerId}/rename`, {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ name }),
  });
}

/** Point-prompted SAM segmentation: one canvas click = one foreground point (canvas px == composite px). */
export function segmentProjectPoint(projectId: string, x: number, y: number): Promise<SegmentResponse> {
  return request<SegmentResponse>(`/api/projects/${projectId}/segment`, {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ points: [{ x, y, label: 1 }] }),
  });
}

/** One foreground/background point in a multi-point SAM prompt (M5). `object_id` groups points
 * that describe the same object server-side — this UI always builds a single group (0). */
export interface SegmentPointDto {
  x: number;
  y: number;
  label: number;
  object_id: number;
}

/** Multi-point SAM segmentation (M5: Shift+klik accumulates points, Enter confirms) — whole-object
 * granularity, unlike the single-point click above which is part-level. */
export function segmentProjectPoints(projectId: string, points: SegmentPointDto[]): Promise<SegmentResponse> {
  return request<SegmentResponse>(`/api/projects/${projectId}/segment`, {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ points }),
  });
}

/** Axis-aligned box in canvas px (M5: drag-to-select on the segment tool) — whole-object SAM prompt. */
export interface SegmentBoxDto {
  x_min: number;
  y_min: number;
  x_max: number;
  y_max: number;
}

export function segmentProjectBox(projectId: string, box: SegmentBoxDto): Promise<SegmentResponse> {
  return request<SegmentResponse>(`/api/projects/${projectId}/segment`, {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ boxes: [box] }),
  });
}

export function createProject(name: string): Promise<ProjectResponse> {
  return request<ProjectResponse>('/api/projects', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ name, canvas_width: 0, canvas_height: 0 }),
  });
}

/** Multipart upload; num_layers is a QUERY param (not form/body) per the API contract. */
export function decomposeFile(projectId: string, file: File, numLayers: number): Promise<LayerResponse[]> {
  const form = new FormData();
  form.append('file', file);
  return request<LayerResponse[]>(
    `/api/projects/${projectId}/decompose/file?num_layers=${encodeURIComponent(String(numLayers))}`,
    { method: 'POST', body: form },
  );
}

/** Binary PNG — caller turns the blob into an <a download> click (see handleExportPng in EditorApp). */
export async function exportPng(projectId: string): Promise<Blob> {
  const path = `/api/projects/${projectId}/export/png`;
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { method: 'POST' });
  } catch (err) {
    throw new ApiError(`Network error calling ${path}: ${err instanceof Error ? err.message : String(err)}`, 0);
  }
  if (!res.ok) await throwForError(res, path);
  return res.blob();
}

export function deleteLayer(projectId: string, layerId: string): Promise<DeleteLayerResponse> {
  return request<DeleteLayerResponse>(`/api/projects/${projectId}/layers/${layerId}`, { method: 'DELETE' });
}

export function undoProject(projectId: string): Promise<UndoRedoResponse> {
  return request<UndoRedoResponse>(`/api/projects/${projectId}/undo`, { method: 'POST' });
}

export function redoProject(projectId: string): Promise<UndoRedoResponse> {
  return request<UndoRedoResponse>(`/api/projects/${projectId}/redo`, { method: 'POST' });
}

export function getHistory(projectId: string): Promise<HistoryResponse> {
  return request<HistoryResponse>(`/api/projects/${projectId}/history`);
}

// --- M3: motion / video ---

export function saveLayerMotion(
  projectId: string,
  layerId: string,
  body: LayerMotionRequestBody,
): Promise<LayerResponse> {
  return request<LayerResponse>(`/api/projects/${projectId}/layers/${layerId}/motion`, {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  });
}

export function clearLayerMotion(projectId: string, layerId: string): Promise<LayerResponse> {
  return request<LayerResponse>(`/api/projects/${projectId}/layers/${layerId}/motion`, {
    method: 'DELETE',
  });
}

export function compileMotion(projectId: string, body: CompileMotionRequestBody): Promise<CompileMotionResponse> {
  return request<CompileMotionResponse>(`/api/projects/${projectId}/video/compile`, {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  });
}

export function submitVideoJob(projectId: string, body: SubmitVideoJobRequestBody): Promise<ClipRecordDto> {
  return request<ClipRecordDto>(`/api/projects/${projectId}/video/jobs`, {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  });
}

export function listVideoJobs(projectId: string): Promise<ClipRecordDto[]> {
  return request<ClipRecordDto[]>(`/api/projects/${projectId}/video/jobs`);
}

/** GET, not POST — the server polls fal.ai for the job's current status as a side effect of this read. */
export function refreshVideoJob(projectId: string, clipId: string): Promise<ClipRecordDto> {
  return request<ClipRecordDto>(`/api/projects/${projectId}/video/jobs/${clipId}`);
}

export function verifyClip(projectId: string, clipId: string): Promise<ClipRecordDto> {
  return request<ClipRecordDto>(`/api/projects/${projectId}/clips/${clipId}/verify`, {
    method: 'POST',
  });
}

/** Direct <video>-able URL for a completed clip's mp4. `version` is a client-side cache-buster, same role as layerPngUrl's. */
export function clipVideoUrl(projectId: string, clipId: string, version?: number): string {
  const params = new URLSearchParams();
  if (version !== undefined) params.set('v', String(version));
  const query = params.toString();
  return `${API_BASE}/api/projects/${projectId}/clips/${clipId}/video${query ? `?${query}` : ''}`;
}

// --- M4: trash (soft-delete), cost ledger, image generation, layer decompose ---

export interface TrashItem {
  entry: string;
  id: string;
  name: string;
  layer_count: number;
  deleted_at: string;
}

/** One paid call as recorded in the project's costs.jsonl (est_usd is an estimate; null = unknown rate). */
export interface CostEntry {
  ts: string;
  endpoint: string;
  kind: string;
  mp: number | null;
  seconds: number | null;
  calls: number;
  est_usd: number | null;
  note: string;
}

export interface CostsSummary {
  entries: CostEntry[];
  total_usd: number;
  count: number;
}

export interface GenerateImageResponse {
  image_b64: string;
  width: number;
  height: number;
  provider: string;
  /** Session-recorded paid call — pass it to attachProjectCost when adopting the image. */
  cost: CostEntry;
}

export function listTrash(): Promise<TrashItem[]> {
  return request<TrashItem[]>('/api/trash');
}

export function restoreTrashEntry(entry: string): Promise<ProjectResponse> {
  return request<ProjectResponse>(`/api/trash/${encodeURIComponent(entry)}/restore`, { method: 'POST' });
}

export function emptyTrash(): Promise<{ purged: number }> {
  return request<{ purged: number }>('/api/trash', { method: 'DELETE' });
}

/** M5: permanently deletes one trash entry (irreversible — unlike restoreTrashEntry). */
export function purgeTrashEntry(entry: string): Promise<{ purged: string }> {
  return request<{ purged: string }>(`/api/trash/${encodeURIComponent(entry)}`, { method: 'DELETE' });
}

export function getProjectCosts(projectId: string): Promise<CostsSummary> {
  return request<CostsSummary>(`/api/projects/${projectId}/costs`);
}

/** Paid calls recorded by the CURRENT API process (across all projects). */
export function getSessionCosts(): Promise<CostsSummary> {
  return request<CostsSummary>('/api/costs/session');
}

export function attachProjectCost(projectId: string, entry: CostEntry): Promise<CostsSummary> {
  return request<CostsSummary>(`/api/projects/${projectId}/costs`, {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify(entry),
  });
}

export function generateImage(body: {
  prompt: string;
  aspect_ratio: string;
  /** "1K" | "2K" — both $0.134; 4K is API-only (different price). */
  image_size?: string;
  provider?: string;
  /** Base64 PNGs (no data: prefix), max 3 — style/subject reference images (M5). */
  reference_b64?: string[];
}): Promise<GenerateImageResponse> {
  return request<GenerateImageResponse>('/api/generate-image', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  });
}

/** Recursive decomposition: replaces the layer with the returned sub-layers (undo restores it). */
export function decomposeLayer(
  projectId: string,
  layerId: string,
  numLayers: number,
): Promise<LayerResponse[]> {
  return request<LayerResponse[]>(`/api/projects/${projectId}/layers/${layerId}/decompose`, {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ num_layers: numLayers }),
  });
}

// --- M6-UX1: text layers (SAM-based detection + AI rewrite) ---

export interface DetectTextResponse {
  /** ALL layers of the project with their is_text/text_score fields refreshed (not just the ones found). */
  layers: LayerResponse[];
  mask_count: number;
}

/** Body for POST /api/projects/{id}/layers/{layerId}/rewrite-text. Mutates the layer's pixels. */
export interface RewriteTextRequestBody {
  new_text: string;
  original_text?: string;
  provider?: string;
  crop_inpaint?: boolean;
}

export interface RewriteTextResponse {
  layer: LayerResponse;
  provider: string;
  elapsed_s: number;
  prompt: string;
}

export function detectText(projectId: string, body?: { threshold?: number }): Promise<DetectTextResponse> {
  return request<DetectTextResponse>(`/api/projects/${projectId}/detect-text`, {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify(body ?? {}),
  });
}

export function rewriteText(
  projectId: string,
  layerId: string,
  body: RewriteTextRequestBody,
): Promise<RewriteTextResponse> {
  return request<RewriteTextResponse>(`/api/projects/${projectId}/layers/${layerId}/rewrite-text`, {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify(body),
  });
}

/** Direct <img>-able URL for a project's thumbnail PNG (404 for an empty project). `version` is a
 * client-side cache-buster, same role as layerPngUrl's (callers pass e.g. `updated_at`). */
export function projectThumbnailUrl(projectId: string, version?: string): string {
  return `${API_BASE}/api/projects/${projectId}/thumbnail${version ? `?v=${encodeURIComponent(version)}` : ''}`;
}
