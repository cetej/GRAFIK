import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent as RPointerEvent, type RefObject } from 'react'
import { imageUrl, infoApi, PaymentRequired, termsApi, type Infographic, type InfoLabel, type TermResult } from './api.ts'

// G5 — editor infografiky podle náčrtu schváleného 2026-10-23 (docs/spikes/img/g5-nacrt-*.png) a vzoru
// models/flux3-klein/overlay_quinq3.html: ~5 popisků s tenkou čarou mimo objekt, 3 fakta, vektorové schéma,
// jedno tmavé pozadí, patička se zdroji a označením AI. Text v obrázku nikdy z modelu.
// Jeden renderer: náhled je přesně to, co jde do exportu (Engine z něj dělá PNG a PDF).
// Zásady vzhledu: docs/infografiky-zasady.md (jedna písmová rodina ve dvou řezech, popisky u věci s krátkými
// lomenými vodítky, rozvržení „pruh“: obraz přes celé plátno, nadpis a fakta v liště přes jeho spodek).

const SIZES: Record<Infographic['size'], [number, number]> = { '1280x990': [1280, 990], '1920x1080': [1920, 1080], '1080x1350': [1080, 1350] }
const SIZE_LABEL: Record<Infographic['size'], string> = { '1280x990': '1280×990', '1920x1080': '16:9', '1080x1350': '4:5' }
const THEMES = {
  dark: { bg: '#1d2532', ink: '#f1ede4', muted: '#a7b1bf', rule: 'rgba(255,255,255,.14)', foot: '#7b8594', shadow: '#000', lead: 'rgba(255,255,255,.75)', dot: '#fff' },
  light: { bg: '#f2f3f5', ink: '#1d1f23', muted: '#5d636b', rule: 'rgba(0,0,0,.14)', foot: '#6b7079', shadow: '#fff', lead: 'rgba(0,0,0,.6)', dot: '#1d1f23' },
}
// one family, two weights: bold accent for names and keys, regular light for explanations (Windows font,
// so the studio preview and the Playwright export render the same glyphs)
const FONT = 'Bahnschrift, "Roboto Condensed", "Arial Narrow", sans-serif'
const MAX_LABELS = 10
const MAX_LABEL_CHARS = 40
const LEADER_MEDIAN_MAX = 0.06   // of the canvas width (reference infographic 0.035)
const LEADER_MAX = 0.12
type Suggestion = { text: string; small: string; anchor: [number, number] }

const clamp = (v: number, lo = 0, hi = 1000) => Math.max(lo, Math.min(hi, v))

function wrap(text: string, maxChars: number): string[] {
  const out: string[] = []
  let line = ''
  for (const w of text.split(/\s+/).filter(Boolean)) {
    if (line && (line + ' ' + w).length > maxChars) { out.push(line); line = w } else line = line ? `${line} ${w}` : w
  }
  if (line) out.push(line)
  return out
}

/** Geometry shared by the renderer and the editor. "klasika": image on top, facts and schema below it;
 *  "pruh": image over the whole canvas, title and facts in a bar across its bottom, schema inset top right. */
export function layout(doc: Infographic, iw: number, ih: number) {
  const [W, H] = SIZES[doc.size]
  const k = W / 1280
  const pad = 40 * k
  const pruh = doc.layout === 'pruh'
  const bottomH = doc.facts.length || doc.schema ? 265 * k : 60 * k
  const imgH = pruh ? H : Math.min((W * ih) / iw, H - bottomH)
  const s = Math.max(W / iw, imgH / ih)
  const ox = (W - iw * s) / 2
  const oy = (imgH - ih * s) / 2
  return {
    W, H, k, pad, imgH, pruh,
    toCanvas: (a: [number, number]): [number, number] => [ox + (a[0] / 1000) * iw * s, oy + (a[1] / 1000) * ih * s],
    toImage: (x: number, y: number): [number, number] => [Math.round(clamp(((x - ox) / (iw * s)) * 1000)), Math.round(clamp(((y - oy) / (ih * s)) * 1000))],
    pos: (p: [number, number]): [number, number] => [(p[0] / 1000) * W, (p[1] / 1000) * H],
    toPos: (x: number, y: number): [number, number] => [Math.round(clamp((x / W) * 1000)), Math.round(clamp((y / H) * 1000))],
  }
}

/** New label placed outside the object: text up and away from the image centre. */
function placeLabel(L: ReturnType<typeof layout>, anchor: [number, number], text = '', small = ''): InfoLabel {
  const [x, y] = L.toCanvas(anchor)
  const left = x < L.W / 2
  const px = clamp(x + (left ? -90 : 70) * L.k, L.pad, L.W - L.pad)
  const py = clamp(y - 60 * L.k, 110 * L.k, L.imgH - 30 * L.k)
  return { text, small, anchor, pos: L.toPos(px, py), align: left ? 'right' : 'left' }
}

function labelBox(l: InfoLabel, L: ReturnType<typeof layout>) {
  const [x, y] = L.pos(l.pos)
  const w = Math.max(l.text.length * 8.4, l.small.length * 6.9, 30) * L.k
  const h = (l.small ? 38 : 21) * L.k
  return { x: l.align === 'right' ? x - w : x, y, w, h }
}

/** Leader from the anchor to the label: straight when nearly vertical or horizontal, else one elbow
 *  (vertical from the object, then horizontal into the label). */
export function leader(l: InfoLabel, L: ReturnType<typeof layout>): [number, number][] {
  const [ax, ay] = L.toCanvas(l.anchor)
  const [px, py] = L.pos(l.pos)
  const ex = px + (l.align === 'right' ? 6 : -6) * L.k
  const ey = py + 11 * L.k
  if (Math.abs(ax - ex) < 8 * L.k || Math.abs(ay - ey) < 8 * L.k) return [[ax, ay], [ex, ey]]
  return [[ax, ay], [ax, ey], [ex, ey]]
}

const polyLen = (p: [number, number][]) => p.slice(1).reduce((s, q, i) => s + Math.hypot(q[0] - p[i][0], q[1] - p[i][1]), 0)

function segCross(a: [number, number], b: [number, number], c: [number, number], d: [number, number]) {
  const o = (p: [number, number], q: [number, number], r: [number, number]) => (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
  return o(a, b, c) * o(a, b, d) < 0 && o(c, d, a) * o(c, d, b) < 0
}

/** Layout checks from docs/infografiky-zasady.md: leader length and crossings. */
export function leaderChecks(doc: Infographic, L: ReturnType<typeof layout>): { ok: boolean; text: string }[] {
  if (!doc.labels.length) return []
  const polys = doc.labels.map((l) => leader(l, L))
  const lens = polys.map(polyLen).map((x) => x / L.W)
  const median = [...lens].sort((a, b) => a - b)[Math.floor(lens.length / 2)]
  const out = [{ ok: median <= LEADER_MEDIAN_MAX, text: `vodítka: medián ${Math.round(median * 1000) / 10} % šířky${median > LEADER_MEDIAN_MAX ? ' – dej popisky blíž k věci' : ''}` }]
  lens.forEach((x, i) => { if (x > LEADER_MAX) out.push({ ok: false, text: `vodítko „${doc.labels[i].text}“ je dlouhé (${Math.round(x * 100)} % šířky)` }) })
  let crossings = 0
  for (let i = 0; i < polys.length; i++) for (let j = i + 1; j < polys.length; j++) {
    const si = polys[i].slice(1).map((q, n) => [polys[i][n], q] as const)
    const sj = polys[j].slice(1).map((q, n) => [polys[j][n], q] as const)
    if (si.some(([a, b]) => sj.some(([c, d]) => segCross(a, b, c, d)))) crossings++
  }
  out.push({ ok: crossings === 0, text: crossings ? `${crossings}× se vodítka kříží` : 'vodítka se nekříží' })
  return out
}

function schemaParts(svg: string): { viewBox: string; inner: string } | null {
  const doc = new DOMParser().parseFromString(svg, 'image/svg+xml')
  const root = doc.documentElement
  if (root.nodeName !== 'svg') return null
  const vb = root.getAttribute('viewBox') || `0 0 ${parseFloat(root.getAttribute('width') || '500')} ${parseFloat(root.getAttribute('height') || '200')}`
  root.querySelectorAll('title').forEach((t) => t.remove())
  return { viewBox: vb, inner: root.innerHTML }
}

interface EditorHooks {
  selected: number | null
  suggestions: Suggestion[]
  onDown: (i: number, what: 'anchor' | 'label', e: RPointerEvent) => void
  onImageClick: (x: number, y: number) => void
}

/** Facts flowed into lines across the bar ("value text | value text"), then the bar's top edge. */
function factBar(doc: Infographic, W: number, H: number, k: number, pad: number) {
  const items = doc.facts.filter((f) => f.value || f.text)
  // readable measure (~100 characters) that also leaves the bar's right end to the picture
  const maxW = Math.min(W - 2 * pad, 0.66 * W)
  const width = (f: { value: string; text: string }) => (f.value.length * 9.2 + (f.text ? f.text.length * 8.2 + 5 : 0)) * k
  const lines: { value: string; text: string }[][] = []
  let cur: { value: string; text: string }[] = []
  let w = 0
  for (const f of items) {
    const fw = width(f) + (cur.length ? 30 * k : 0)
    if (cur.length && w + fw > maxW) { lines.push(cur); cur = []; w = 0 }
    cur.push(f)
    w += width(f) + (cur.length > 1 ? 30 * k : 0)
  }
  if (cur.length) lines.push(cur)
  const footerH = 30 * k
  const top = H - (58 * k + lines.length * 25 * k + footerH)
  return { top, lines }
}

export function InfoSvg({ doc, href, iw, ih, svgRef, ed }: {
  doc: Infographic; href: string; iw: number; ih: number; svgRef?: RefObject<SVGSVGElement | null>; ed?: EditorHooks
}) {
  const L = layout(doc, iw, ih)
  const { W, H, k, pad, imgH, pruh } = L
  const t = THEMES[doc.template]
  const schema = doc.schema ? schemaParts(doc.schema.svg) : null
  const bar = pruh ? factBar(doc, W, H, k, pad) : null
  const bottomTop = imgH + 10 * k
  const schemaW = 500 * k
  const factsW = (schema ? W - 2 * pad - schemaW - 40 * k : W - 2 * pad) - 134 * k
  let fy = bottomTop + 22 * k
  const facts = doc.facts.filter((f) => f.value || f.text).map((f) => {
    const lines = wrap(f.text, Math.max(20, Math.floor(factsW / (7 * k))))
    const y = fy
    fy += Math.max(30 * k, lines.length * 19 * k) + 16 * k
    return { ...f, lines, y }
  })
  const footer = wrap(`${doc.sources ? `Zdroj: ${doc.sources} ` : ''}${doc.ai_note}`, Math.floor((W - 2 * pad) / (5.4 * k)))
  const svgPoint = (e: { clientX: number; clientY: number }) => {
    const svg = svgRef?.current
    if (!svg) return [0, 0]
    const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(svg.getScreenCTM()!.inverse())
    return [p.x, p.y]
  }

  return (
    <svg ref={svgRef} xmlns="http://www.w3.org/2000/svg" width={W} height={H} viewBox={`0 0 ${W} ${H}`} className="info-svg">
      <defs>
        <linearGradient id="fade" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#fff" /><stop offset=".9" stopColor="#fff" /><stop offset="1" stopColor="#000" /></linearGradient>
        <mask id="fade-mask"><rect width={W} height={imgH} fill="url(#fade)" /></mask>
        {/* behind the title: keeps it readable over a light sky or sea */}
        <linearGradient id="scrim" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={t.bg} stopOpacity=".85" /><stop offset="1" stopColor={t.bg} stopOpacity="0" /></linearGradient>
        <filter id="halo"><feDropShadow dx="0" dy={1 * k} stdDeviation={2 * k} floodColor={t.shadow} floodOpacity=".95" /></filter>
      </defs>
      <rect width={W} height={H} fill={t.bg} />
      <image href={href} x="0" y="0" width={W} height={imgH} preserveAspectRatio="xMidYMid slice" mask={pruh ? undefined : 'url(#fade-mask)'}
        onClick={ed ? (e) => { const [x, y] = svgPoint(e); ed.onImageClick(x, y) } : undefined} style={ed ? { cursor: 'crosshair' } : undefined} />
      {!pruh && <>
        <rect x="0" y="0" width={W} height={Math.min(170 * k, imgH)} fill="url(#scrim)" pointerEvents="none" />
        <text x={pad} y={pad + 30 * k} fill={doc.accent} fontFamily={FONT} fontStretch="semi-condensed" fontWeight="700" fontSize={34 * k} letterSpacing={0.6 * k}>{doc.title.toUpperCase()}</text>
        {doc.subtitle && <text x={pad} y={pad + 56 * k} fill={t.muted} fontFamily={FONT} fontStretch="semi-condensed" fontSize={17 * k}>{doc.subtitle}</text>}
      </>}

      {bar && (
        <g fontFamily={FONT} fontStretch="semi-condensed">
          <defs><linearGradient id="bar" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={t.bg} stopOpacity="0" /><stop offset=".35" stopColor={t.bg} stopOpacity=".86" /><stop offset="1" stopColor={t.bg} stopOpacity=".94" /></linearGradient>
            {/* the bar backs only the text: past its measure the picture shows through (bow, ram) */}
            <linearGradient id="bar-h"><stop offset=".68" stopColor="#fff" /><stop offset=".86" stopColor="#fff" stopOpacity="0" /></linearGradient>
            <mask id="bar-mask"><rect x="0" y="0" width={W} height={H} fill="url(#bar-h)" /></mask></defs>
          <rect x="0" y={bar.top - 70 * k} width={W} height={H - bar.top + 70 * k} fill="url(#bar)" mask="url(#bar-mask)" />
          <line x1={pad} y1={bar.top} x2={0.7 * W} y2={bar.top} stroke={t.rule} strokeWidth="1" />
          <text x={pad} y={bar.top + 36 * k}>
            <tspan fill={doc.accent} fontWeight="700" fontSize={30 * k} letterSpacing={0.5 * k}>{doc.title.toUpperCase()}</tspan>
            {doc.subtitle && <tspan fill={t.ink} fontSize={22 * k}>{'  —  '}{doc.subtitle}</tspan>}
          </text>
          {bar.lines.map((line, j) => (
            <text key={j} x={pad} y={bar.top + 70 * k + j * 25 * k} fontSize={17 * k}>
              {line.map((f, n) => (
                <tspan key={n}>
                  {n > 0 && <tspan fill={t.rule}>{'   |   '}</tspan>}
                  <tspan fill={doc.accent} fontWeight="700">{f.value}</tspan>
                  {f.text && <tspan fill={t.ink}>{' '}{f.text}</tspan>}
                </tspan>
              ))}
            </text>
          ))}
        </g>
      )}

      {doc.labels.map((l, i) => {
        const pts = leader(l, L)
        const [ax, ay] = pts[0]
        const [px, py] = L.pos(l.pos)
        const anchorEnd = l.align === 'right' ? 'end' : 'start'
        return (
          <g key={i} fontFamily={FONT} fontStretch="semi-condensed">
            <polyline points={pts.map((q) => q.join(',')).join(' ')} stroke={t.lead} strokeWidth={1.1 * k} fill="none" />
            <circle cx={ax} cy={ay} r={2.8 * k} fill={t.dot} />
            <g filter="url(#halo)" stroke={t.shadow} strokeWidth={3 * k} strokeLinejoin="round" paintOrder="stroke">
              <text x={px} y={py + 16 * k} textAnchor={anchorEnd} fill={doc.accent} fontSize={16 * k} fontWeight="700">{l.text}</text>
              {l.small && <text x={px} y={py + 33 * k} textAnchor={anchorEnd} fill={t.ink} fontSize={14 * k}>{l.small}</text>}
            </g>
          </g>
        )
      })}


      {!pruh && (facts.length > 0 || schema) && <line x1={pad} y1={bottomTop} x2={W - pad} y2={bottomTop} stroke={t.rule} strokeWidth="1" />}
      {!pruh && facts.map((f, i) => (
        <g key={i} fontFamily="Segoe UI, sans-serif">
          <text x={pad} y={f.y + 20 * k} fill={doc.accent} fontSize={22 * k} fontWeight="700">{f.value}</text>
          {f.lines.map((line, j) => <text key={j} x={pad + 134 * k} y={f.y + 15 * k + j * 19 * k} fill={t.muted} fontSize={13.5 * k}>{line}</text>)}
        </g>
      ))}
      {schema && doc.schema && pruh && (() => {
        const [, , vw, vh] = schema.viewBox.split(/[\s,]+/).map(Number)
        const iw2 = 0.3 * W
        const ih2 = (iw2 * vh) / vw
        const x = W - pad - iw2
        const y = pad
        return (
          <g fontFamily={FONT} fontStretch="semi-condensed">
            <rect x={x - 12 * k} y={y - 10 * k} width={iw2 + 24 * k} height={ih2 + 48 * k} rx={4 * k} fill={t.bg} fillOpacity=".82" stroke={t.rule} />
            <text x={x} y={y + 14 * k} fill={doc.accent} fontSize={15 * k} fontWeight="700" letterSpacing={0.6 * k}>{doc.schema!.title.toUpperCase()}</text>
            <svg x={x} y={y + 26 * k} width={iw2} height={ih2} viewBox={schema.viewBox} dangerouslySetInnerHTML={{ __html: schema.inner }} />
          </g>
        )
      })()}
      {schema && doc.schema && !pruh && (
        <g>
          <text x={W - pad - schemaW} y={bottomTop + 35 * k} fill={doc.accent} fontFamily="Segoe UI, sans-serif" fontSize={13 * k} fontWeight="700" letterSpacing={1 * k}>{doc.schema.title.toUpperCase()}</text>
          <svg x={W - pad - schemaW} y={bottomTop + 47 * k} width={schemaW} height={Math.min(200 * k, H - bottomTop - 47 * k - 30 * k)}
            viewBox={schema.viewBox} dangerouslySetInnerHTML={{ __html: schema.inner }} />
        </g>
      )}
      {footer.map((line, i) => <text key={i} x={pad} y={H - 8 * k - (footer.length - 1 - i) * 13 * k} fill={t.foot} fontFamily={FONT} fontStretch="semi-condensed" fontSize={11 * k}>{line}</text>)}

      {ed && (
        <g className="ed">
          {doc.labels.map((l, i) => {
            const [ax, ay] = L.toCanvas(l.anchor)
            const b = labelBox(l, L)
            return (
              <g key={i}>
                <rect x={b.x - 3 * k} y={b.y - 2 * k} width={b.w + 6 * k} height={b.h + 4 * k} rx={3} fill={ed.selected === i ? 'rgba(74,157,255,.14)' : 'transparent'}
                  stroke={ed.selected === i ? '#4a9dff' : '#ffcc00'} strokeWidth={ed.selected === i ? 2 : 1.5} strokeDasharray={ed.selected === i ? '' : '5 3'}
                  style={{ cursor: 'move' }} onPointerDown={(e) => ed.onDown(i, 'label', e)} />
                <circle cx={ax} cy={ay} r={8 * k} fill="rgba(255,204,0,.25)" stroke="#ffcc00" strokeWidth={2} style={{ cursor: 'move' }}
                  onPointerDown={(e) => ed.onDown(i, 'anchor', e)} />
              </g>
            )
          })}
          {ed.suggestions.map((s, i) => {
            const [x, y] = L.toCanvas(s.anchor)
            return (
              <g key={`s${i}`} pointerEvents="none">
                <circle cx={x} cy={y} r={6 * k} fill="#c77dff" stroke="#fff" strokeWidth={2} />
                <text x={x + 10 * k} y={y - 8 * k} fill="#fff" fontFamily="Segoe UI, sans-serif" fontSize={13 * k} fontWeight="600" filter="url(#halo)">{s.text}</text>
              </g>
            )
          })}
        </g>
      )}
    </svg>
  )
}

/** Same SVG without the editor layer, image embedded: what the Engine stores and rasterises. */
async function exportSvg(svg: SVGSVGElement, base: string): Promise<string> {
  const clone = svg.cloneNode(true) as SVGSVGElement
  clone.querySelectorAll('.ed').forEach((n) => n.remove())
  clone.removeAttribute('class')
  const blob = await (await fetch(imageUrl(base))).blob()
  const dataUrl = await new Promise<string>((ok) => { const r = new FileReader(); r.onload = () => ok(String(r.result)); r.readAsDataURL(blob) })
  clone.querySelector('image')?.setAttribute('href', dataUrl)
  return new XMLSerializer().serializeToString(clone)
}

export default function Infographics({ openId, setOpenId, selectedImage, recentImages, onError }: {
  openId: string | null
  setOpenId: (id: string | null) => void
  selectedImage: string | null
  recentImages: string[]
  onError: (msg: string) => void
}) {
  const [list, setList] = useState<Infographic[]>([])
  useEffect(() => { if (!openId) infoApi.list().then(setList).catch((e) => onError(e.message)) }, [openId, onError])

  if (openId) return <Editor key={openId} id={openId} onClose={() => setOpenId(null)} recentImages={recentImages} onError={onError} />

  const create = async () => {
    if (!selectedImage) return
    try { setOpenId((await infoApi.create(selectedImage, '')).id) } catch (e) { onError((e as Error).message) }
  }
  return (
    <main className="guide-start">
      <div className="row between">
        <h2>Infografiky</h2>
        <button className="btn go" disabled={!selectedImage} onClick={create} title={selectedImage ? '' : 'Ve studiu není vybraný obrázek'}>+ Nová z vybraného obrázku</button>
      </div>
      <p className="hint">Popisky, fakta a schéma píšete česky v editoru; generátor text nikdy nekreslí. Infografiku založíte i z kroku 5 Průvodce nebo tlačítkem „→ Infografika“ u obrázku ve studiu.</p>
      <div className="wf-list">
        {list.map((d) => (
          <button key={d.id} className="wf-item" onClick={() => setOpenId(d.id)}>
            <img src={imageUrl(d.base, 256)} alt="" />
            <span><b>{d.title || 'bez nadpisu'}</b><small>{d.labels.length} popisků · {d.exports.length} exportů · {d.updated.slice(0, 16).replace('T', ' ')}</small></span>
          </button>
        ))}
        {!list.length && <p className="hint">Zatím žádná infografika.</p>}
      </div>
    </main>
  )
}

function Editor({ id, onClose, recentImages, onError }: { id: string; onClose: () => void; recentImages: string[]; onError: (msg: string) => void }) {
  const [doc, setDoc] = useState<Infographic | null>(null)
  const [dims, setDims] = useState<[number, number] | null>(null)
  const [selected, setSelected] = useState<number | null>(null)
  const [suggestions, setSuggestions] = useState<Suggestion[]>([])
  const [schemas, setSchemas] = useState<{ slug: string; title: string; svg: string }[]>([])
  const [busy, setBusy] = useState<string | null>(null)
  const [saved, setSaved] = useState(true)
  const [reviewer, setReviewer] = useState('')
  const [lastExport, setLastExport] = useState<string | null>(null)
  const [terms, setTerms] = useState<{ available: boolean; names: TermResult[]; facts: TermResult[] } | null>(null)
  const svgRef = useRef<SVGSVGElement>(null)
  const drag = useRef<{ i: number; what: 'anchor' | 'label' } | null>(null)
  const loaded = useRef(false)

  useEffect(() => {
    infoApi.get(id).then((d) => { setDoc(d); setReviewer(d.reviewed_by ?? '') }).catch((e) => onError(e.message))
    infoApi.schemas().then(setSchemas).catch(() => {})
  }, [id, onError])
  useEffect(() => {
    if (!doc) return
    const img = new Image()
    img.onload = () => setDims([img.naturalWidth, img.naturalHeight])
    img.src = imageUrl(doc.base)
  }, [doc?.base]) // eslint-disable-line react-hooks/exhaustive-deps

  // autosave, debounced
  useEffect(() => {
    if (!doc) return
    if (!loaded.current) { loaded.current = true; return }
    setSaved(false)
    const t = setTimeout(() => infoApi.save(doc).then(() => setSaved(true)).catch((e) => onError(e.message)), 600)
    return () => clearTimeout(t)
  }, [doc, onError])

  // termdb check (free, local): names = title and label texts (nominative, "není v termdb" makes sense);
  // the rest (subtitle, small texts, schema title, facts) is inflected prose, checked only for ambiguous terms
  const termTexts = doc ? JSON.stringify([[doc.title, ...doc.labels.map((l) => l.text)],
    [doc.subtitle, ...doc.labels.map((l) => l.small), doc.schema?.title ?? '', ...doc.facts.map((f) => f.text)]]) : ''
  useEffect(() => {
    if (!termTexts) return
    const [names, facts] = JSON.parse(termTexts) as [string[], string[]]
    const t = setTimeout(() => {
      termsApi.check([...names, ...facts]).then((r) => {
        const byText = new Map(r.results.map((x) => [x.text, x]))
        const pick = (xs: string[]) => xs.filter((x) => x.trim()).map((x) => byText.get(x)).filter(Boolean) as TermResult[]
        setTerms({ available: r.available, names: pick(names), facts: pick(facts) })
      }).catch(() => setTerms(null))
    }, 500)
    return () => clearTimeout(t)
  }, [termTexts])

  const set = useCallback((patch: Partial<Infographic>) => setDoc((d) => (d ? { ...d, ...patch } : d)), [])
  const setLabel = (i: number, patch: Partial<InfoLabel>) => setDoc((d) => (d ? { ...d, labels: d.labels.map((l, j) => (j === i ? { ...l, ...patch } : l)) } : d))
  const L = useMemo(() => (doc && dims ? layout(doc, dims[0], dims[1]) : null), [doc, dims])

  const toSvg = (e: { clientX: number; clientY: number }) => {
    const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(svgRef.current!.getScreenCTM()!.inverse())
    return [p.x, p.y]
  }
  const onMove = (e: RPointerEvent) => {
    if (!drag.current || !L) return
    const [x, y] = toSvg(e)
    const { i, what } = drag.current
    if (what === 'anchor') setLabel(i, { anchor: L.toImage(x, Math.min(y, L.imgH)) })
    else setLabel(i, { pos: L.toPos(x, y) })
  }

  if (!doc || !dims || !L) return <main className="guide-start"><p className="hint">Načítám…</p></main>

  const hooks: EditorHooks = {
    selected, suggestions,
    onDown: (i, what, e) => {
      e.preventDefault()
      drag.current = { i, what }
      setSelected(i)
      try { (e.target as Element).setPointerCapture(e.pointerId) } catch { /* the wrapper's pointermove still drives the drag */ }
    },
    onImageClick: (x, y) => {
      if (y > L.imgH) return
      setDoc({ ...doc, labels: [...doc.labels, placeLabel(L, L.toImage(x, y), 'Nový popisek')] })
      setSelected(doc.labels.length)
    },
  }

  const suggest = async () => {
    setBusy('suggest')
    try { setSuggestions((await infoApi.suggest(doc.id, true)).labels) } catch (e) {
      onError(e instanceof PaymentRequired ? 'Návrh popisků se nespustil.' : (e as Error).message)
    } finally { setBusy(null) }
  }
  const accept = (s: Suggestion[]) => {
    setDoc({ ...doc, labels: [...doc.labels, ...s.map((x) => placeLabel(L, x.anchor, x.text, x.small))] })
    setSuggestions((cur) => cur.filter((x) => !s.includes(x)))
  }
  const loadSchemaFile = async (f: File | undefined) => {
    if (!f) return
    const svg = await f.text()
    if (!svg.includes('<svg')) { onError('Soubor není SVG.'); return }
    set({ schema: { title: doc.schema?.title || f.name.replace(/\.svg$/i, ''), svg } })
  }
  const doExport = async (fmt: 'png' | 'svg' | 'pdf') => {
    setBusy(fmt)
    try {
      await infoApi.save(doc)
      const r = await infoApi.export(doc.id, await exportSvg(svgRef.current!, doc.base), fmt)
      setLastExport(r.url)
      setDoc((d) => (d ? { ...d, exports: [r.file, ...d.exports] } : d))
    } catch (e) { onError((e as Error).message) } finally { setBusy(null) }
  }

  const longLabels = doc.labels.map((l, i) => ({ i, n: (l.text + l.small).length })).filter((x) => x.n > MAX_LABEL_CHARS)
  const checks: { ok: boolean; text: string; title?: string }[] = [
    { ok: doc.labels.length <= MAX_LABELS, text: `${doc.labels.length} popisků${doc.labels.length > MAX_LABELS ? `, doporučeno do ${MAX_LABELS}` : ''}` },
    ...(longLabels.length ? longLabels.map((x) => ({ ok: false, text: `popisek ${x.i + 1} je delší než ${MAX_LABEL_CHARS} znaků` })) : [{ ok: true, text: 'popisky krátké' }]),
    ...leaderChecks(doc, L),
    { ok: true, text: 'text jen z editoru, ne z modelu' },
    { ok: !!doc.sources.trim(), text: doc.sources.trim() ? 'zdroj vyplněn' : 'chybí zdroj' },
    { ok: true, text: 'označení AI v patičce' },
    { ok: !!doc.reviewed_by, text: doc.reviewed_by ? `zkontroloval(a) ${doc.reviewed_by}` : 'před zveřejněním zkontroluje člověk' },
  ]
  const termChecks: { ok: boolean; text: string; title?: string }[] = []
  if (terms && !terms.available) termChecks.push({ ok: false, text: 'termdb nedostupná (Nastavení)' })
  if (terms?.available) {
    const okCount = new Set(terms.names.flatMap((r) => r.ok)).size
    const missing = [...new Set(terms.names.flatMap((r) => r.missing))]
    const ambiguous = [...terms.names, ...terms.facts].flatMap((r) => r.ambiguous)
    termChecks.push({ ok: true, text: `termdb: ${okCount} ${okCount === 1 ? 'termín' : okCount < 5 && okCount ? 'termíny' : 'termínů'} nalezeno` })
    for (const h of [...new Set([...terms.names, ...terms.facts].flatMap((r) => r.hints))]) termChecks.push({ ok: true, text: `termdb: ${h}` })
    for (const a of ambiguous) termChecks.push({ ok: false, text: `nejednoznačné v termdb: ${a.phrase}`, title: a.senses.join('\n') })
    if (missing.length) termChecks.push({ ok: false, text: `není v termdb: ${missing.join(', ')}` })
  }
  const sel = selected !== null ? doc.labels[selected] : null
  const selBox = sel ? labelBox(sel, L) : null

  return (
    <main className="info-editor">
      <section className="card info-left">
        <div className="row between"><button className="btn small" onClick={onClose}>← Všechny infografiky</button><span className="hint">{saved ? 'uloženo' : 'ukládám…'}</span></div>
        <h3>Nadpis</h3>
        <input className="search full" value={doc.title} onChange={(e) => set({ title: e.target.value })} placeholder="Nadpis" aria-label="Nadpis" />
        <input className="search full" value={doc.subtitle} onChange={(e) => set({ subtitle: e.target.value })} placeholder="Podtitulek" aria-label="Podtitulek" />

        <h3>Popisky · {doc.labels.length} <span className={`tag ${doc.labels.length > MAX_LABELS ? 'ai' : 'ok'}`}>doporučeno do {MAX_LABELS}</span></h3>
        {doc.labels.map((l, i) => (
          <div key={i} className={`lrow ${selected === i ? 'sel' : ''}`} onFocus={() => setSelected(i)}>
            <span className="n">{i + 1}</span>
            <input value={l.text} onChange={(e) => setLabel(i, { text: e.target.value })} aria-label={`Popisek ${i + 1}`} />
            <input value={l.small} onChange={(e) => setLabel(i, { small: e.target.value })} placeholder="drobný text" aria-label={`Drobný text ${i + 1}`} />
            <button className="x" title="Smazat popisek" aria-label="Smazat popisek" onClick={() => { set({ labels: doc.labels.filter((_, j) => j !== i) }); setSelected(null) }}>×</button>
          </div>
        ))}
        <p className="hint">Nový popisek: klikněte na místo v obrázku (bod), pak táhněte text mimo objekt.</p>
        <button className="btn pay" disabled={busy === 'suggest'} onClick={suggest}>{busy === 'suggest' ? 'Claude navrhuje…' : 'Navrhnout popisky (Claude) · 0,01 USD'}</button>
        <p className="hint">Kliknutí je souhlas s cenou. Claude navrhne jen názvy částí a místa, ne fakta.</p>

        <h3>Fakta · {doc.facts.length}</h3>
        {doc.facts.map((f, i) => (
          <div key={i} className="frow">
            <input value={f.value} onChange={(e) => set({ facts: doc.facts.map((x, j) => (j === i ? { ...x, value: e.target.value } : x)) })} placeholder="číslo / datum" aria-label={`Fakt ${i + 1} číslo`} />
            <input value={f.text} onChange={(e) => set({ facts: doc.facts.map((x, j) => (j === i ? { ...x, text: e.target.value } : x)) })} placeholder="co to znamená" aria-label={`Fakt ${i + 1} text`} />
            <button className="x" title="Smazat fakt" aria-label="Smazat fakt" onClick={() => set({ facts: doc.facts.filter((_, j) => j !== i) })}>×</button>
          </div>
        ))}
        {doc.facts.length < 4 && <button className="btn small" onClick={() => set({ facts: [...doc.facts, { value: '', text: '' }] })}>+ fakt</button>}

        <h3>Schéma (vektor)</h3>
        {doc.schema && <input className="search full" value={doc.schema.title} onChange={(e) => set({ schema: { ...doc.schema!, title: e.target.value } })} aria-label="Nadpis schématu" />}
        <div className="row">
          <label className="btn small">Vložit SVG<input type="file" accept=".svg,image/svg+xml" hidden onChange={(e) => { loadSchemaFile(e.target.files?.[0]); e.target.value = '' }} /></label>
          <select className="btn small" value="" onChange={(e) => { const s = schemas.find((x) => x.slug === e.target.value); if (s) set({ schema: { title: s.title, svg: s.svg } }) }} aria-label="Ze šablony schémat">
            <option value="">Ze šablony schémat…</option>
            {schemas.map((s) => <option key={s.slug} value={s.slug}>{s.title}</option>)}
          </select>
          {doc.schema && <button className="btn small" onClick={() => set({ schema: null })}>Bez schématu</button>}
          {doc.schema && <button className="btn small" onClick={() => infoApi.saveSchema(doc.schema!.title, doc.schema!.svg).then(() => infoApi.schemas().then(setSchemas)).catch((e) => onError(e.message))}>Uložit jako šablonu</button>}
        </div>

        <h3>Zdroje a označení</h3>
        <textarea className="info-src" value={doc.sources} onChange={(e) => set({ sources: e.target.value })} placeholder="Odkud jsou fakta (kniha, článek, muzeum)" aria-label="Zdroje" />
        <div className="lock">🔒 {doc.ai_note} <span className="hint">· z provenience obrázku, nelze smazat</span></div>
      </section>

      <section className="card info-stage">
        {suggestions.length > 0 && (
          <div className="sug-bar">
            <b>Claude navrhl {suggestions.length} popisků</b>
            {suggestions.map((s, i) => (
              <span key={i} className="sug-chip">{s.text}
                <button className="x ok" title="Převzít" aria-label={`Převzít ${s.text}`} onClick={() => accept([s])}>✓</button>
                <button className="x" title="Zahodit" aria-label={`Zahodit ${s.text}`} onClick={() => setSuggestions(suggestions.filter((x) => x !== s))}>✕</button>
              </span>
            ))}
            <button className="btn go small" onClick={() => accept(suggestions)}>Převzít vše</button>
            <button className="btn small" onClick={() => setSuggestions([])}>Zahodit</button>
          </div>
        )}
        <div className="info-wrap" onPointerMove={onMove} onPointerUp={() => { drag.current = null }} onPointerLeave={() => { drag.current = null }}>
          <InfoSvg doc={doc} href={imageUrl(doc.base)} iw={dims[0]} ih={dims[1]} svgRef={svgRef} ed={hooks} />
          {sel && selBox && selected !== null && (
            <div className="info-pop" style={{ left: `${((selBox.x + selBox.w + 14 * L.k) / L.W) * 100}%`, top: `${(selBox.y / L.H) * 100}%` }}>
              <b>Popisek {selected + 1}</b>
              <input value={sel.text} onChange={(e) => setLabel(selected, { text: e.target.value })} aria-label="Text popisku" />
              <input value={sel.small} onChange={(e) => setLabel(selected, { small: e.target.value })} placeholder="drobný text" aria-label="Drobný text popisku" />
              <div className="row">
                <button className="btn small" onClick={() => setLabel(selected, { align: sel.align === 'right' ? 'left' : 'right' })}>Zarovnat čáru</button>
                <button className="btn small" onClick={() => { set({ labels: doc.labels.filter((_, j) => j !== selected) }); setSelected(null) }}>Smazat</button>
                <button className="btn small" onClick={() => setSelected(null)}>Hotovo</button>
              </div>
            </div>
          )}
        </div>
      </section>

      <section className="card info-right">
        <h3>Podklad</h3>
        <img className="info-base" src={imageUrl(doc.base, 256)} alt="" />
        <p className="hint">verze {doc.base} · {dims[0]}×{dims[1]}</p>
        <select className="full" value="" onChange={(e) => e.target.value && set({ base: e.target.value })} aria-label="Změnit obrázek">
          <option value="">Změnit obrázek…</option>
          {recentImages.filter((r) => r !== doc.base).slice(0, 30).map((r) => <option key={r} value={r}>{r}</option>)}
        </select>

        <h3>Vzhled</h3>
        <div className="hint">Rozvržení</div>
        <div className="seg">{(['pruh', 'klasika'] as const).map((v) => <button key={v} className={(doc.layout ?? 'klasika') === v ? 'on' : ''} onClick={() => set({ layout: v })} title={v === 'pruh' ? 'obraz přes celé plátno, nadpis a fakta v liště přes jeho spodek, schéma v rohu' : 'obraz nahoře, fakta a schéma pod ním'}>{v === 'pruh' ? 'Lišta přes obraz' : 'Klasické'}</button>)}</div>
        <div className="hint">Šablona</div>
        <div className="seg">{(['dark', 'light'] as const).map((t) => <button key={t} className={doc.template === t ? 'on' : ''} onClick={() => set({ template: t })}>{t === 'dark' ? 'Tmavá muzejní' : 'Světlá'}</button>)}</div>
        <div className="hint" style={{ marginTop: 8 }}>Formát</div>
        <div className="seg">{(Object.keys(SIZES) as Infographic['size'][]).map((s) => <button key={s} className={doc.size === s ? 'on' : ''} onClick={() => set({ size: s })}>{SIZE_LABEL[s]}</button>)}</div>
        <div className="hint" style={{ marginTop: 8 }}>Akcent</div>
        <div className="row"><input type="color" className="accent" value={doc.accent} onChange={(e) => set({ accent: e.target.value })} aria-label="Barva akcentu" /><span className="hint">{doc.accent}</span></div>

        <h3>Kontrola</h3>
        <ul className="check">{[...checks, ...termChecks].map((c, i) => <li key={i} title={c.title}><b className={c.ok ? 'ok' : 'w'}>{c.ok ? '✓' : '!'}</b>{c.text}</li>)}</ul>
        <p className="hint">Termíny ověřuje lokální termdb (sdílená s NG-ROBOT), zdarma. Nejednoznačné ukáže význam po najetí myší.</p>
        <div className="row">
          <input className="search" style={{ flex: 1 }} value={reviewer} onChange={(e) => setReviewer(e.target.value)} placeholder="jméno" aria-label="Kdo zkontroloval" />
          <button className="btn small" disabled={!reviewer.trim()} onClick={() => set({ reviewed_by: reviewer.trim(), reviewed_at: new Date().toISOString().slice(0, 19) })}>Zkontrolováno</button>
        </div>

        <h3>Export</h3>
        <div className="row">
          {(['png', 'svg', 'pdf'] as const).map((f) => (
            <button key={f} className={`btn ${f === 'png' ? 'go' : ''}`} disabled={!!busy} onClick={() => doExport(f)}>{busy === f ? 'Ukládám…' : f.toUpperCase()}</button>
          ))}
        </div>
        {lastExport && <p className="hint">Hotovo: <a href={lastExport} target="_blank" rel="noreferrer">{lastExport.split('/').pop()}</a></p>}
        <p className="hint">Uloží se do knihovny (library/infographics) i s proveniencí: zdroje, označení AI, kdo kontroloval. Popisky zůstanou upravitelné.</p>
        {doc.exports.length > 0 && (
          <ul className="exports">{doc.exports.slice(0, 6).map((n) => <li key={n}><a href={`/api/v2/infographics/${doc.id}/exports/${n}`} target="_blank" rel="noreferrer">{n}</a></li>)}</ul>
        )}
      </section>
    </main>
  )
}
