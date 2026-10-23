// GRAFIK Engine /api/v2 client for the studio (contract: engine/app.py).

export type Role = 'subject' | 'geometry' | 'scene' | 'style'
export type EditAction = 'add' | 'remove' | 'move' | 'recolor'
export type Box = [number, number, number, number] // [top, left, bottom, right], 0–1000

export interface RefIn { b64?: string; ref_id?: string; role: Role; text?: string; source?: string }

export interface ImageRequest {
  prompt: string
  backend?: string
  size?: string
  n?: number
  seed?: number | null
  refs?: RefIn[]
  supersample?: number | null
  parent?: string | null
  edit?: { action: EditAction; bbox: Box; target_bbox?: Box | null; instruction: string } | null
  translate?: 'auto' | 'off'
  style?: string | null
  style_id?: string | null
  caller?: string
  confirm_cost?: boolean
}

export interface Job {
  job_id: string
  status: 'queued' | 'running' | 'done' | 'failed' | 'cancelled'
  caller: string
  backend: string
  position: number | null
  error: string | null
  images: string[]
  created: number
  started: number | null
  finished: number | null
  request: ImageRequest & { refs: { role: Role; source?: string; text?: string }[] }
  result: { files: string[]; cost_usd: number; prompt_sent: string; seeds: (number | null)[] } | null
}

export interface CostItem { what: string; usd: number; kind?: string }

export interface Estimate {
  total_usd: number
  items: CostItem[]
  eta_s: number | null
  size: string
  render_size: string
}

export interface Backend { id: string; paid: boolean; usd_1024: number; refs: boolean; supersample: boolean }

export interface Health { sd_server: 'stopped' | 'starting' | 'ready'; queue_len: number; running_job: string | null }

export interface LineageNode {
  ref: string
  parent: string | null
  status: Job['status']
  image: string | null
  created: number
  request: Job['request']
}

export interface Provenance {
  backend: string
  model: string
  seed: number | null
  params: Record<string, unknown> & { size?: string; render_size?: string }
  prompt_original: string
  prompt_sent: string
  refs: { role: Role; source: string | null; license: string | null; sent_as: string }[]
  parent: string | null
  edit: { action: EditAction; instruction: string } | null
  cost_usd: number
  timing_s: { queue: number; generate: number }
  translations?: { field: string; cs: string; en: string; paid: boolean }[]
  style_id?: string | null
  ai_generated: boolean
  reviewed_by: string | null
  reviewed_at?: string
}

export class PaymentRequired extends Error {
  constructor(public estimate: number, public items: CostItem[]) {
    super(`Placená operace ~${estimate} USD`)
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...init })
  const body = await r.json().catch(() => ({}))
  if (r.status === 402) throw new PaymentRequired(body.estimate_usd, body.items ?? [])
  if (!r.ok) {
    const d = body.detail
    throw new Error(typeof d === 'string' ? d : Array.isArray(d) ? d.map((x: { msg: string }) => x.msg).join('; ') : `HTTP ${r.status}`)
  }
  return body as T
}

const post = <T>(path: string, data: unknown) => call<T>(path, { method: 'POST', body: JSON.stringify(data) })

export const api = {
  health: () => call<Health>('/api/v2/health'),
  backends: () => call<Backend[]>('/api/v2/backends'),
  jobs: (limit = 60) => call<Job[]>(`/api/v2/jobs?limit=${limit}`),
  job: (id: string) => call<Job>(`/api/v2/jobs/${id}`),
  estimate: (req: ImageRequest) => post<Estimate>('/api/v2/estimate', req),
  submit: (req: ImageRequest) => post<{ job_id: string }>('/api/v2/images', req),
  repeat: (id: string, n: number, confirm = false) => post<{ job_id: string }>(`/api/v2/jobs/${id}/repeat`, { n, confirm_cost: confirm }),
  cancel: (id: string) => post<Job>(`/api/v2/jobs/${id}/cancel`, {}),
  lineage: (ref: string) => call<LineageNode[]>(`/api/v2/lineage/${ref}`),
  provenance: (ref: string) => call<Provenance>(`/api/v2/jobs/${ref.replace('/', '/images/')}/provenance`),
  review: (ref: string, who: string) => post<Provenance>(`/api/v2/jobs/${ref.replace('/', '/images/')}/review`, { reviewed_by: who }),
  expand: (text: string, confirm: boolean) => post<{ prompt: string; usd: number }>('/api/v2/prompt/expand', { text, confirm_cost: confirm }),
  costs: () => call<{ total_usd: number; entries: { ts: string; usd: number }[] }>('/api/v2/costs?limit=500'),
}

export interface RefMeta {
  id: string
  origin: 'commons' | 'pinterest' | 'web' | 'upload'
  title: string
  source_url: string | null
  page_url: string | null
  author: string | null
  license: string | null
  width: number
  height: number
  added: string
  seen: boolean
  image: string
}

export interface CommonsItem {
  title: string
  file: string
  thumb: string
  page_url: string
  author: string | null
  license: string | null
  description: string
  width: number
  height: number
}

export interface Workflow {
  id: string
  object: string
  refs: { ref_id: string; role: Role }[]
  side_job: string | null
  side_pick: string | null
  fixed: string | null
  rotate_job: string | null
  pick: string | null
  view: string
  background: string
  updated: string
}

export const refsApi = {
  list: () => call<RefMeta[]>('/api/v2/refs'),
  addUrl: (url: string, page_url?: string, title?: string) => post<RefMeta>('/api/v2/refs', { url, page_url, title }),
  addB64: (b64: string, title: string) => post<RefMeta>('/api/v2/refs', { b64, title, origin: 'upload' }),
  seen: (id: string) => post<RefMeta>(`/api/v2/refs/${id}/seen`, {}),
  commons: (q: string) => call<CommonsItem[]>(`/api/v2/commons/search?q=${encodeURIComponent(q)}`),
  commonsImport: (file: string) => post<RefMeta>('/api/v2/commons/import', { file }),
}

export const wfApi = {
  list: () => call<Workflow[]>('/api/v2/workflows'),
  create: (object: string, refs: Workflow['refs']) => post<Workflow>('/api/v2/workflows/historical', { object, refs }),
  get: (id: string) => call<Workflow>(`/api/v2/workflows/${id}`),
  patch: (id: string, body: Partial<Pick<Workflow, 'object' | 'refs' | 'side_pick' | 'fixed' | 'pick'>>) =>
    call<Workflow>(`/api/v2/workflows/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  side: (id: string, n: number, opts: { estimate_only?: boolean; confirm_cost?: boolean } = {}) =>
    post<Estimate & { job_id?: string }>(`/api/v2/workflows/${id}/side`, { n, ...opts }),
  rotate: (id: string, body: { view: string; background: string; n: number }, opts: { estimate_only?: boolean; confirm_cost?: boolean } = {}) =>
    post<Estimate & { job_id?: string }>(`/api/v2/workflows/${id}/rotate`, { ...body, ...opts }),
}

export const imageUrl = (ref: string, w?: number) =>
  `/api/v2/jobs/${ref.replace('/', '/images/')}${w ? `?w=${w}` : ''}`

export async function fileToB64(file: Blob): Promise<string> {
  const buf = await file.arrayBuffer()
  let bin = ''
  const bytes = new Uint8Array(buf)
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000))
  return btoa(bin)
}

// Czech diacritics -> the Engine will translate (engine/translate.py uses the same test)
export const isCzech = (t: string) => /[ěščřžýáíéůúťďňóĚŠČŘŽÝÁÍÉŮÚŤĎŇÓ]/.test(t)
export const onlyTranslation = (items: CostItem[]) => items.length > 0 && items.every((i) => i.kind === 'translation')

// -- G4 style library --------------------------------------------------------
export interface PaletteColor { hex: string; name?: string; share?: number }

export interface StyleFields {
  label: string
  note: string
  medium: string
  light: string
  line: string
  composition: string
  avoid: string
  signature: string
  palette: PaletteColor[]
  origin?: 'default' | 'detected' | 'manual'
  puvod?: string
}

export interface StyleCard extends StyleFields {
  slug: string
  samples: string[]
  sample_urls: string[]
  prompt: string
  updated: string
}

export interface StyleImages { b64?: string[]; jobs?: string[]; ref_ids?: string[] }

const send = <T>(method: string, path: string, data?: unknown) =>
  call<T>(path, { method, body: data === undefined ? undefined : JSON.stringify(data) })

export const stylesApi = {
  list: () => call<StyleCard[]>('/api/v2/styles'),
  create: (f: StyleFields) => post<StyleCard>('/api/v2/styles', f),
  save: (slug: string, f: StyleFields) => send<StyleCard>('PUT', `/api/v2/styles/${slug}`, f),
  remove: (slug: string) => send<{ moved_to: string }>('DELETE', `/api/v2/styles/${slug}`),
  addSample: (slug: string, body: { b64?: string; job?: string }) => post<StyleCard>(`/api/v2/styles/${slug}/samples`, body),
  removeSample: (slug: string, name: string) => send<StyleCard>('DELETE', `/api/v2/styles/${slug}/samples/${name}`),
  palette: (img: StyleImages) => post<{ palette: PaletteColor[] }>('/api/v2/styles/palette', img),
  describe: (img: StyleImages, confirm: boolean) =>
    post<Omit<StyleFields, 'palette'> & { palette: PaletteColor[] }>('/api/v2/styles/describe', { ...img, confirm_cost: confirm }),
}

// -- G5 infographics -----------------------------------------------------------
export interface InfoLabel { text: string; small: string; anchor: [number, number]; pos: [number, number]; align?: 'left' | 'right' }
export interface InfoFact { value: string; text: string }
export interface InfoSchema { title: string; svg: string }

export interface Infographic {
  id: string
  base: string
  title: string
  subtitle: string
  template: 'dark' | 'light'
  size: '1280x990' | '1920x1080' | '1080x1350'
  accent: string
  labels: InfoLabel[]
  facts: InfoFact[]
  schema: InfoSchema | null
  sources: string
  ai_note: string
  reviewed_by: string | null
  reviewed_at: string | null
  updated: string
  exports: string[]
}

export const infoApi = {
  list: () => call<Infographic[]>('/api/v2/infographics'),
  create: (base: string, title: string) => post<Infographic>('/api/v2/infographics', { base, title }),
  get: (id: string) => call<Infographic>(`/api/v2/infographics/${id}`),
  save: (doc: Infographic) => send<Infographic>('PUT', `/api/v2/infographics/${doc.id}`, doc),
  remove: (id: string) => send<{ moved_to: string }>('DELETE', `/api/v2/infographics/${id}`),
  export: (id: string, svg: string, format: 'png' | 'svg' | 'pdf') =>
    post<{ file: string; url: string; bytes: number }>(`/api/v2/infographics/${id}/export`, { svg, format }),
  suggest: (id: string, confirm: boolean) =>
    post<{ labels: { text: string; small: string; anchor: [number, number] }[] }>(`/api/v2/infographics/${id}/suggest-labels`, { confirm_cost: confirm }),
  schemas: () => call<{ slug: string; title: string; svg: string }[]>('/api/v2/schemas'),
  saveSchema: (title: string, svg: string) => post<{ slug: string }>('/api/v2/schemas', { title, svg }),
}

// -- termdb (editorial term database, read-only, free) --------------------------
export interface TermResult { text: string; ok: string[]; ambiguous: { phrase: string; senses: string[] }[]; missing: string[]; hints: string[] }
export const termsApi = {
  check: (texts: string[]) => post<{ available: boolean; results: TermResult[] }>('/api/v2/terms/check', { texts }),
}
