// GRAFIK Engine /api/v2 client for the studio (contract: engine/app.py).

export type Role = 'subject' | 'geometry' | 'scene' | 'style'
export type EditAction = 'add' | 'remove' | 'move' | 'recolor'
export type Box = [number, number, number, number] // [top, left, bottom, right], 0–1000

export interface RefIn { b64?: string; ref_id?: string; knihovna?: string; role: Role; text?: string; source?: string; license?: string | null }

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

// Records of kinds other than a generated image (localize, upload) can be short: what is missing stays unknown, not zero.
export interface Provenance {
  backend?: string
  model?: string
  seed?: number | null
  params?: Record<string, unknown> & { size?: string; render_size?: string }
  prompt_original?: string
  prompt_sent?: string
  refs?: { role: Role; source: string | null; license: string | null; sent_as: string }[]
  parent?: string | null
  edit?: { action: EditAction; instruction: string } | null
  cost_usd?: number | null
  timing_s?: { queue: number; generate: number | null }
  translations?: { field: string; cs: string; en: string; paid: boolean }[]
  style_id?: string | null
  ai_generated: boolean
  reviewed_by: string | null
  reviewed_at?: string
  vectorcraft_svg?: string
}

export class PaymentRequired extends Error {
  constructor(public estimate: number, public items: CostItem[]) {
    super(`Placená operace ~${estimate} USD`)
  }
}

/** A manual edit in VectorCraft exists: the operator chooses, Engine overwrites nothing. */
export class ManualEdit extends Error {}

export interface ManualEditFile { file: string; modified: string; can_export: boolean; exported: string | null }

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...init })
  const body = await r.json().catch(() => ({}))
  if (r.status === 402) throw new PaymentRequired(body.estimate_usd, body.items ?? [])
  if (r.status === 409 && body.edited) throw new ManualEdit(body.detail)
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
  openVectorcraft: (ref: string, mode?: 'edited' | 'new') =>
    post<{ opened: string; path: string; created: boolean }>(`/api/v2/jobs/${ref.replace('/', '/images/')}/vectorcraft`, { mode }),
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

// Characters, places and props of the shared library KNIHOVNA (Engine GET /api/v2/knihovna)
export type KnihovnaKind = 'character' | 'environment' | 'prop'
export interface KnihovnaImage { file: string; label: string; primary: boolean; role: Role; knihovna: string; url: string }
export interface KnihovnaItem { kind: KnihovnaKind; slug: string; name: string; about: string; updated: string; images: KnihovnaImage[] }

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
  kind: 'historical' | 'infografika'
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

export const knihovnaApi = {
  list: () => call<{ items: KnihovnaItem[]; problems: string[] }>('/api/v2/knihovna'),
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

// -- řetězec infografika z tématu (engine/chain.py) --------------------------------------------------------
export interface ProposalPanel { titulek: string; co: string; druh: string; x: number; y: number; w: number; h: number; poradi: number; fakta: string[]; predloha: string | null }
export interface Proposal { id: number; nazev: string; veta: string; format: string; panely: ProposalPanel[]; vzhled: string; fakta: number; neznama_fakta: number; rozpory: string[] }
export interface ChainWarning { severity: string; what: string; why: string; fix: string }
export interface Chain {
  id: string
  kind: 'infografika'
  object: string
  vzor: string | null
  model: string
  stage: 'podklady' | 'navrhy' | 'vyber' | 'kontrola' | 'hotovo' | 'stop'
  research_id: string | null
  budget_usd: number
  spent_usd: number
  navrhy: Proposal[]
  rozbor: { drzet?: string[]; zmenit?: string[] } | null
  vyber: number | null
  kontrola: { summary?: string; purpose?: string; warnings?: ChainWarning[]; chyba?: string } | null
  stop_reason: string | null
  resume_stage: string | null
  resume_usd: number
  updated: string
}
export const chainApi = {
  estimate: (research?: string) => call<{ total_usd: number; items: CostItem[] }>(`/api/v2/workflows/infografika/estimate${research ? `?research=${encodeURIComponent(research)}` : ''}`),
  start: (body: { topic?: string; research?: string; vzor?: string | null; confirm_cost: boolean }) => post<Chain>('/api/v2/workflows/infografika', body),
  get: (id: string) => call<Chain>(`/api/v2/workflows/${id}`),
  pick: (id: string, navrh: number) => post<Chain>(`/api/v2/workflows/${id}/pick`, { navrh }),
  resume: (id: string, confirm: boolean) => post<Chain>(`/api/v2/workflows/${id}/continue`, { confirm_cost: confirm }),
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
// -- batch of variants to pick from (engine/variants.py) -----------------------
export interface Batch { id: string; title: string; prompt: string; job_ids: string[]; count: number; page: string }

export const variantsApi = {
  create: (body: { request: ImageRequest; count: number; styles: (string | null)[]; title?: string }) =>
    post<Batch>('/api/v2/variants', body),
}

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
  kategorie?: string
  origin?: 'default' | 'detected' | 'manual'
  puvod?: string
}

export interface StyleCard extends StyleFields {
  slug: string
  poradi?: number | null
  samples: string[]
  sample_urls: string[]
  prompt: string
  updated: string
}

// Mirror of ngm_shared.knihovna.STYLE_CATEGORIES, in the order the Engine sorts the library.
export const STYLE_CATEGORIES: [string, string][] = [
  ['fotografie', 'Fotografie'], ['historicke', 'Historické'], ['ilustrace', 'Ilustrace'],
  ['3d', '3D'], ['komiks', 'Komiks'], ['film', 'Film'],
]

/** Cards by category, empty categories left out; `key` '' = cards without a category. */
export function groupStyles(cards: StyleCard[]): { key: string; label: string; cards: StyleCard[] }[] {
  const known = STYLE_CATEGORIES.map(([key]) => key)
  return [...STYLE_CATEGORIES, ['', 'Bez kategorie'] as [string, string]]
    .map(([key, label]) => ({ key, label, cards: cards.filter((c) => (key ? c.kategorie === key : !known.includes(c.kategorie ?? ''))) }))
    .filter((g) => g.cards.length)
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
  layout?: 'klasika' | 'pruh'
  size: string   // "WxH": a preset or the picture's own format
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
  in_library?: Record<string, string>   // PNG export -> its picture in the Knihovna tab
}

// -- rešerše k tématu (engine/research.py) ----------------------------------------------------------------
export interface FactSource { url: string; nazev: string; citace: string; datum: string; jazyk: string; hodnota?: number | number[] }
export interface Fact {
  id: string
  tvrzeni: string
  predmet: string | null
  velicina: string | null
  hodnota: number | number[] | null
  jednotka: string | null
  zdroje: FactSource[]
  stav: 'shoda' | 'rozpor' | 'jediny_zdroj'
  tema: 'rozmery' | 'vznik' | 'stavba' | 'rekord' | 'ostatni'
}
export interface DossierImage {
  file: string
  nazev: string
  url: string
  stranka: string | null
  autor: string | null
  licence: string | null
  popis: string
  sirka: number | null
  vyska: number | null
  role: 'pudorys' | 'rez' | 'pruceli' | 'interier' | 'detail' | 'material' | 'nezarazeno'
  ref_id?: string
  chyba?: string
}
export interface Dossier {
  id: string
  tema: string
  verze: number
  entita: { qid: string; label: string; popis: string; url: string }
  facts: Fact[]
  images: DossierImage[]
  otazky_bez_odpovedi: string[]
  cost_usd: number
}
export interface ResearchState {
  id: string
  tema: string
  verze: number
  status: Job['status']
  error: string | null
  dossier: Dossier | null
  page: string | null
}
export interface ResearchRow extends Omit<ResearchState, 'dossier'> { entita: string | null; facts: number; rozpory: number; images: number; cost_usd: number | null }
export const researchApi = {
  list: () => call<ResearchRow[]>('/api/v2/research'),
  get: (id: string) => call<ResearchState>(`/api/v2/research/${id}`),
  estimate: (paid: boolean) => call<{ total_usd: number; items: CostItem[] }>(`/api/v2/research/estimate?paid=${paid}`),
  start: (topic: string, qid?: string) => post<{ id: string; job_id: string }>('/api/v2/research', { topic, qid }),
  extend: (id: string, confirm: boolean) => post<{ id: string; job_id: string }>('/api/v2/research', { extends: id, confirm_cost: confirm }),
}

// -- počeštění cizí infografiky nebo mapy (engine/localize.py) ---------------------------------------------
export interface LocalizeWarning { severity: string; what: string; fix: string }
export interface LocalizeTexts { kind: string; elements: ({ id: number; en: string; cs: string } & Record<string, unknown>)[] }
export interface LocalizeJob {
  job_id: string
  status: Job['status']
  error: string | null
  images: string[]
  created: number
  request: { source?: string | null }
  result: { cost_usd: number; image_kind: string; warnings: LocalizeWarning[] } | null
}
export const localizeApi = {
  estimate: () => call<{ usd: number }>('/api/v2/localize/estimate'),
  jobs: (limit: number) => call<LocalizeJob[]>(`/api/v2/localize/jobs?limit=${limit}`),
  job: (id: string) => call<LocalizeJob>(`/api/v2/jobs/${id}`),
  texts: (id: string) => call<LocalizeTexts>(`/api/v2/localize/${id}/image-0.texty.json`),
  file: (id: string, name: string) => `/api/v2/localize/${id}/${name}`,
  start: (body: { image?: string; b64?: string; source_job?: string; texts?: LocalizeTexts; confirm_cost?: boolean }) =>
    post<{ job_id: string; estimate_usd: number }>('/api/v2/localize', body),
}

export const infoApi = {
  list: () => call<Infographic[]>('/api/v2/infographics'),
  create: (base: string, title: string) => post<Infographic>('/api/v2/infographics', { base, title }),
  upload: (b64: string, name: string, blenderRender = false) => post<Infographic>('/api/v2/infographics/upload', { b64, name, blender_render: blenderRender }),
  fromRef: (refId: string, title: string) => post<Infographic>('/api/v2/infographics/from-ref', { ref_id: refId, title }),
  toLibrary: (id: string, name: string) => post<{ ref: string; created: boolean }>(`/api/v2/infographics/${id}/exports/${name}/library`, {}),
  get: (id: string) => call<Infographic>(`/api/v2/infographics/${id}`),
  save: (doc: Infographic) => send<Infographic>('PUT', `/api/v2/infographics/${doc.id}`, doc),
  remove: (id: string) => send<{ moved_to: string }>('DELETE', `/api/v2/infographics/${id}`),
  export: (id: string, svg: string, format: 'png' | 'svg' | 'pdf') =>
    post<{ file: string; url: string; bytes: number }>(`/api/v2/infographics/${id}/export`, { svg, format }),
  vectorcraft: (id: string) => call<{ available: boolean; edits: ManualEditFile[] }>(`/api/v2/infographics/${id}/vectorcraft`),
  openVectorcraft: (id: string, svg: string, mode?: 'edited' | 'new') =>
    post<{ opened: string; path: string; created: boolean }>(`/api/v2/infographics/${id}/vectorcraft`, { svg, mode }),
  exportManual: (id: string, file: string) =>
    post<{ source: string; files: { file: string; format: 'png' | 'svg' | 'pdf'; url: string; bytes: number }[]; warnings: string[] }>(`/api/v2/infographics/${id}/vectorcraft/export`, { file }),
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

// -- 3D step (engine/api3d.py, docs/plans/2026-10-27-3d-v1.md; v2 viewer + camera render) ---------------
export type View3d = 'front' | 'back' | 'left' | 'right'
export interface Ref3d { view: View3d; b64?: string; source?: string | null; license?: string | null; author?: string | null }
export interface Model3dVersion {
  schema_version: number
  id: string
  version: string
  title: string
  created: string
  status: 'queued' | 'generating' | 'model' | 'viewer' | 'rendering' | 'stretching' | 'ready' | 'failed'
  method: 'fal-trellis2' | 'fal-hunyuan3d' | 'fal-hunyuan31pro' | 'upload' | 'blender-script' | 'stretch'
  backend: string | null
  refs: { view: View3d; file: string; source: string | null; license: string | null }[]
  cost_usd: number
  request_id?: string | null
  views: Record<string, { dir: string; files: string[]; rendered: string; seconds: number; engine: string }>
  review: { by: string; at: string } | null
  viewer?: {
    file: string; bytes: number; triangles: number | null; job_id: string; seconds: number
    // viewer.opt.glb from glTF Transform; `error` = the viewer loads viewer.glb
    optimized?: { file?: string; bytes?: number; bytes_before?: number; seconds?: number; tool?: string; error?: string; at: string }
  }
  jobs: { job_id: string; kind: string }[]
  error: string | null
  stats?: { verts: number; faces: number; bbox: [number, number, number] }
  blender?: string
  parent?: string
  origin?: string | null
  stretch?: { dims: [number, number, number]; part: string; source: string; bbox?: number[] }
  rozmer_m?: number        // the longest side in metres typed in a 3D scene (DECISIONS 2026-10-27, Q2)
  rozmer_zdroj?: string
  legacy?: { dir: string }
  versions?: number
}
export interface Estimate3d { method: string; recommended: string; items: CostItem[]; total_usd: number; eta_s: number; label: string }
export interface Job3d extends Omit<Job, 'request'> { kind: string; request: { model_id: string; version: string; elevation?: number; recover?: boolean } }

const m3 = '/api/v2/models3d'
export const m3dApi = {
  list: () => call<Model3dVersion[]>(m3),
  get: (id: string) => call<{ id: string; title: string; versions: Model3dVersion[] }>(`${m3}/${id}`),
  jobs: () => call<Job3d[]>(`${m3}/jobs?limit=20`),
  estimate: (body: { method?: string | null; refs: Ref3d[] }) => post<Estimate3d>(`${m3}/estimate`, body),
  cutout: (b64: string) => post<{ b64: string }>(`${m3}/cutout`, { b64 }),
  create: (body: { title: string; model_id?: string | null; method?: string | null; refs?: Ref3d[]; glb_b64?: string; origin?: string; confirm_cost?: boolean }) =>
    post<{ model_id: string; version: string; job_id: string; estimate_usd: number }>(m3, body),
  views: (id: string, v: string, elevation: number) => post<{ job_id: string }>(`${m3}/${id}/${v}/views`, { elevation }),
  review: (id: string, v: string, reviewed: boolean) => post<Model3dVersion>(`${m3}/${id}/${v}/review`, { reviewed, by: 'operátor' }),
  stretch: (id: string, v: string, dims: number[], part: string, source: string) =>
    post<{ version: string; job_id: string }>(`${m3}/${id}/${v}/stretch`, { dims, part, source }),
  recover: (id: string, v: string) => post<{ job_id: string }>(`${m3}/${id}/${v}/recover`, {}),
  viewer: (id: string, v: string, optimizeOnly = false) =>
    post<{ job_id: string }>(`${m3}/${id}/${v}/viewer${optimizeOnly ? '?optimize_only=true' : ''}`, {}),
  // the job id (and the optimizer's time) change with every new copy, so the browser never shows a stale one;
  // `url` is the optimized copy when there is one, `fallback` always viewer.glb
  viewerGlb: (id: string, v: string, viewer: NonNullable<Model3dVersion['viewer']>) => {
    const fallback = `${m3}/${id}/${v}/viewer.glb?j=${viewer.job_id}`
    const opt = viewer.optimized
    return { url: opt?.file ? `${m3}/${id}/${v}/viewer.opt.glb?j=${viewer.job_id}&o=${encodeURIComponent(opt.at)}` : fallback, fallback }
  },
  camera: (id: string, v: string, cam: { target: number[]; azimuth: number; elevation: number; distance: number; lens: number }) =>
    post<{ key: string; job_id: string | null; file: string }>(`${m3}/${id}/${v}/camera`, cam),
  asRefCam: (id: string, v: string, key: string) =>
    call<{ path: string; file: string; role: Role; source: string; license: string | null }>(`${m3}/${id}/${v}/as-ref?cam=${key}`),
  asRef: (id: string, v: string, azimuth: number, elevation: number) =>
    call<{ path: string; role: Role; source: string; license: string | null }>(`${m3}/${id}/${v}/as-ref?azimuth=${azimuth}&elevation=${elevation}`),
  file: (id: string, v: string, name: string, w?: number) => `${m3}/${id}/${v}/files/${name}${w ? `?w=${w}` : ''}`,
  glb: (id: string, v: string) => `${m3}/${id}/${v}/model.glb`,
}

// -- 3D scenes (engine/api_scenes3d.py, docs/plans/2026-10-27-3d-sceny.md) ---------------------------------
export interface SceneObj {
  id: string
  model?: string | null
  model_version?: string | null
  tvar?: 'kvadr' | 'valec' | null
  rozmery: number[]
  nazev: string
  misto: [number, number]
  otoceni: number
  rozmer: number | null
  rozmer_zdroj: string
  na: string | null
}
export interface SceneFigure { misto: [number, number]; otoceni: number; na: string | null }
export interface Cam3dIn { target: number[]; azimuth: number; elevation: number; distance: number; lens: number }
export interface SceneSnap { key: string; file: string; rendered: string; seconds: number; aspect: string; postava: boolean }
export interface Scene3d {
  id: string
  version: string
  title: string
  created: string
  objects: SceneObj[]
  postava: SceneFigure
  aspect: string
  camera: Cam3dIn | null
  snaps: SceneSnap[]
  problems?: string[]
  unchecked?: string[]
  hint?: { cs: string; en: string }
  versions?: number
}
export interface SceneHint { cs: string; en: string }

const sc3 = '/api/v2/scenes3d'
export const scenesApi = {
  list: () => call<Scene3d[]>(sc3),
  get: (id: string) => call<{ id: string; title: string; versions: Scene3d[] }>(`${sc3}/${id}`),
  version: (id: string, v: string) => call<Scene3d>(`${sc3}/${id}/${v}`),
  save: (body: { scene_id?: string | null; title: string; objects: Partial<SceneObj>[]; postava: SceneFigure; aspect: string; camera?: Cam3dIn | null }) =>
    post<Scene3d>(sc3, body),
  camera: (id: string, v: string, camera: Cam3dIn) => post<Scene3d>(`${sc3}/${id}/${v}/camera`, { camera }),
  render: (id: string, v: string, camera: Cam3dIn, aspect: string, postava: boolean) =>
    post<{ key: string; job_id: string | null; file: string }>(`${sc3}/${id}/${v}/render`, { camera, aspect, postava }),
  asRef: (id: string, v: string, snap: string) =>
    call<{ path: string; file: string; role: Role; source: string; license: string | null; hint: SceneHint }>(`${sc3}/${id}/${v}/as-ref?snap=${snap}`),
  file: (id: string, v: string, name: string) => `${sc3}/${id}/${v}/files/${name}`,
  figureGlb: `${sc3}/figure.glb`,
}
