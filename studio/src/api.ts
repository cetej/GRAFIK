// GRAFIK Engine /api/v2 client for the studio (contract: engine/app.py).

export type Role = 'subject' | 'geometry' | 'scene' | 'style'
export type EditAction = 'add' | 'remove' | 'move' | 'recolor'
export type Box = [number, number, number, number] // [top, left, bottom, right], 0–1000

export interface RefIn { b64: string; role: Role; text?: string; source?: string }

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
