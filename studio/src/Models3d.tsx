import { useCallback, useEffect, useRef, useState } from 'react'
import {
  fileToB64, m3dApi, PaymentRequired,
  type Estimate3d, type Job3d, type Model3dVersion, type RefIn, type RefMeta, type View3d,
} from './api.ts'
import RefPicker from './RefPicker.tsx'
import { fmtTime, fmtUsd } from './App.tsx'

// 3D krok v1 podle náčrtu schváleného 2026-10-27 (docs/spikes/img/2026-10-27-3d-nacrt.png).

const SLOTS: { view: View3d; label: string }[] = [
  { view: 'front', label: 'zepředu' }, { view: 'right', label: 'zprava' }, { view: 'back', label: 'zezadu' }, { view: 'left', label: 'zleva' },
]
const ELEVATIONS: { el: number; label: string }[] = [{ el: 5, label: 'Kamera nízko' }, { el: 20, label: '20° nad' }, { el: 60, label: 'Shora' }]
const AZ = [0, 45, 90, 135, 180, 225, 270, 315]
const METHOD_LABEL: Record<string, string> = {
  'fal-trellis2': 'TRELLIS 2', 'fal-hunyuan3d': 'Hunyuan3D v3', upload: 'nahraný GLB', 'blender-script': 'Blender ze skriptu', stretch: 'natažený na rozměry',
}
const STATUS: Record<Model3dVersion['status'], { label: string; cls: string }> = {
  queued: { label: 've frontě', cls: '' }, generating: { label: 'model se tvoří', cls: 'ai' }, model: { label: 'bez bílých pohledů', cls: 'ai' },
  rendering: { label: 'kreslí se pohledy', cls: 'ai' }, stretching: { label: 'natahuje se', cls: 'ai' }, ready: { label: 'čeká na kontrolu', cls: 'ai' },
  failed: { label: 'chyba', cls: 'paid' },
}

interface Slot { view: View3d; original: string; cutout: string | null; source?: string | null; license?: string | null; busy?: boolean }

const KIND_LABEL: Record<string, string> = { model3d: 'model', views3d: 'bílé pohledy', stretch3d: 'natažení' }
const dataUrl = (b64: string) => `data:image/png;base64,${b64}`
const thumbOf = (m: Model3dVersion) => {
  const v = m.views['20']
  if (v) return m3dApi.file(m.id, m.version, `${v.dir}/az045.png`, 128)
  return m.legacy ? m3dApi.file(m.id, m.version, 'legacy-thumb.png', 128) : null
}
const ratio = (b: number[]) => {
  // Blender: x, y on the ground, z up -> length (longer ground side) : width : height, longest = 1
  const [len, wid] = b[0] >= b[1] ? [b[0], b[1]] : [b[1], b[0]]
  const top = Math.max(len, wid, b[2])
  return [len, wid, b[2]].map((x) => (x / top).toLocaleString('cs-CZ', { maximumFractionDigits: 2 })).join(' : ')
}

export default function Models3d({ onError, onToStudio }: {
  onError: (msg: string) => void
  onToStudio: (ref: RefIn & { name: string; preview: string; meta?: string }) => void
}) {
  const [models, setModels] = useState<Model3dVersion[]>([])
  const [openId, setOpenId] = useState<string | null>(null)
  const [versions, setVersions] = useState<Model3dVersion[]>([])
  const [ver, setVer] = useState<string | null>(null)
  const [el, setEl] = useState(20)
  const [az, setAz] = useState(45)
  const [zoom, setZoom] = useState<number | null>(null)
  const [jobs, setJobs] = useState<Job3d[]>([])
  // new model form
  const [slots, setSlots] = useState<Slot[]>([])
  const [title, setTitle] = useState('')
  const [target, setTarget] = useState<string | null>(null) // model id when the form makes a new version
  const [method, setMethod] = useState<string | null>(null) // null = recommended
  const [glb, setGlb] = useState<{ name: string; b64: string } | null>(null)
  const [est, setEst] = useState<Estimate3d | null>(null)
  const [sending, setSending] = useState(false)
  const [editing, setEditing] = useState<View3d | null>(null)
  const [picker, setPicker] = useState<View3d | null>(null)
  const [stretchOpen, setStretchOpen] = useState(false)
  const glbInput = useRef<HTMLInputElement>(null)

  const load = useCallback(async () => {
    try {
      const [list, js] = await Promise.all([m3dApi.list(), m3dApi.jobs()])
      setModels(list)
      setJobs(js)
      if (openId) setVersions((await m3dApi.get(openId)).versions)
    } catch (e) {
      onError(String((e as Error).message))
    }
  }, [openId, onError])
  useEffect(() => {
    load()
    const t = setInterval(load, 2500)
    return () => clearInterval(t)
  }, [load])
  useEffect(() => {
    if (!openId && models.length) setOpenId(models[0].id)
  }, [models, openId])

  const cur = versions.find((v) => v.version === ver) ?? versions[versions.length - 1] ?? null
  useEffect(() => {
    setVer(null)
    setVersions([])
    if (openId) m3dApi.get(openId).then((m) => setVersions(m.versions)).catch((e) => onError(String(e.message)))
  }, [openId, onError])

  const isUpload = method === 'upload'
  const filled = slots.filter((s) => s.cutout)
  useEffect(() => {
    if (isUpload) { setEst({ method: 'upload', recommended: 'upload', items: [], total_usd: 0, eta_s: 40, label: 'Nahrát GLB' }); return }
    if (!filled.length) { setEst(null); return }
    m3dApi.estimate({ method, refs: filled.map((s) => ({ view: s.view })) }).then(setEst).catch((e) => { setEst(null); onError(String(e.message)) })
  }, [method, isUpload, filled.map((s) => s.view).join(','), onError]) // eslint-disable-line react-hooks/exhaustive-deps

  // -- refs and their cutouts (Q2: shown before anything is sent, eraser to fix) ----------------
  const setSlot = (view: View3d, patch: Partial<Slot> | null) =>
    setSlots((ss) => (patch === null ? ss.filter((s) => s.view !== view)
      : ss.some((s) => s.view === view) ? ss.map((s) => (s.view === view ? { ...s, ...patch } : s)) : [...ss, { view, original: '', cutout: null, ...patch }]))

  const addImage = async (view: View3d, b64: string, source?: string | null, license?: string | null) => {
    setSlot(view, { original: b64, cutout: null, busy: true, source, license })
    try {
      const r = await m3dApi.cutout(b64)
      setSlot(view, { cutout: r.b64, busy: false })
    } catch (e) {
      setSlot(view, null)
      onError(`Výřez se nepovedl: ${(e as Error).message}`)
    }
  }
  const pickFile = (view: View3d) => {
    const inp = document.createElement('input')
    inp.type = 'file'
    inp.accept = 'image/*'
    inp.onchange = async () => {
      const f = inp.files?.[0]
      if (f) addImage(view, await fileToB64(f), `soubor ${f.name}`, null)
    }
    inp.click()
  }
  const fromLibrary = async (view: View3d, m: RefMeta) => {
    setPicker(null)
    const b64 = await fileToB64(await (await fetch(m.image)).blob())
    addImage(view, b64, m.page_url ?? m.source_url ?? m.title, m.license)
  }

  const newModel = () => {
    setTarget(null); setTitle(''); setSlots([]); setGlb(null); setMethod(null)
  }
  const newVersionOf = async (m: Model3dVersion) => {
    setTarget(m.id); setTitle(m.title); setGlb(null); setMethod(m.method === 'fal-trellis2' || m.method === 'fal-hunyuan3d' ? m.method : null)
    const loaded: Slot[] = []
    for (const r of m.refs) {
      const b64 = await fileToB64(await (await fetch(m3dApi.file(m.id, m.version, r.file))).blob())
      loaded.push({ view: r.view, original: b64, cutout: b64, source: r.source, license: r.license })
    }
    setSlots(loaded)
  }

  const create = async () => {
    setSending(true)
    try {
      const r = isUpload
        ? await m3dApi.create({ title: title || glb!.name.replace(/\.glb$/i, ''), model_id: target, glb_b64: glb!.b64, origin: glb!.name })
        : await m3dApi.create({
          title: title || 'model', model_id: target, method: est?.method, confirm_cost: true, // the price is in the button: the click is the consent
          refs: filled.map((s) => ({ view: s.view, b64: s.cutout!, source: s.source, license: s.license })),
        })
      setOpenId(r.model_id); setVer(r.version); newModel()
      load()
    } catch (e) {
      onError(e instanceof PaymentRequired ? `Placená operace ${fmtUsd(e.estimate)} nebyla potvrzena.` : String((e as Error).message))
    } finally {
      setSending(false)
    }
  }

  // -- the open model ---------------------------------------------------------------------------
  const viewSet = cur?.views[String(el)]
  const renderEl = async (e: number) => {
    setEl(e)
    if (cur && !cur.views[String(e)] && cur.status !== 'rendering') {
      try { await m3dApi.views(cur.id, cur.version, e); load() } catch (err) { onError(String((err as Error).message)) }
    }
  }
  const toggleReview = async (on: boolean) => {
    if (!cur) return
    try { await m3dApi.review(cur.id, cur.version, on); load() } catch (e) { onError(String((e as Error).message)) }
  }
  const toStudio = async () => {
    if (!cur) return
    try {
      const ref = await m3dApi.asRef(cur.id, cur.version, az, el)
      const url = m3dApi.file(cur.id, cur.version, `${viewSet!.dir}/az${String(az).padStart(3, '0')}.png`)
      const b64 = await fileToB64(await (await fetch(url)).blob())
      onToStudio({ b64, role: 'geometry', source: ref.source, license: ref.license, name: `${cur.title} ${az}°`, preview: `${url}?w=256`, meta: `3D ${cur.version} · ${az}°` })
    } catch (e) {
      onError(String((e as Error).message))
    }
  }
  const curJobs = jobs.filter((j) => j.request.model_id === cur?.id && j.request.version === cur?.version)
  const pending = curJobs.find((j) => j.status === 'queued' || j.status === 'running')
  const lastFail = curJobs.find((j) => j.status === 'failed')

  const running = jobs.find((j) => j.status === 'running')
  const waiting = jobs.filter((j) => j.status === 'queued')
  const jobLabel = (j: Job3d) => `${KIND_LABEL[j.kind] ?? j.kind} ${models.find((m) => m.id === j.request.model_id)?.title ?? j.request.model_id} ${j.request.version}`

  const btnLabel = isUpload
    ? (glb ? 'Nahrát GLB · 0 USD' : 'Nahrát GLB (nejdřív vyberte soubor)')
    : est ? `Vytvořit 3D model · ${fmtUsd(est.total_usd)} · ${fmtTime(est.eta_s)}` : 'Vytvořit 3D model (nejdřív předloha)'
  const canCreate = !sending && (isUpload ? !!glb : !!est && filled.length > 0 && !slots.some((s) => s.busy))
  const zoomSrc = zoom !== null && cur && viewSet ? m3dApi.file(cur.id, cur.version, `${viewSet.dir}/az${String(zoom).padStart(3, '0')}.png`) : null

  return (
    <main className="m3d">
      <aside className="card">
        <h3>3D modely</h3>
        <div className="m3d-list">
          {models.map((m) => (
            <button key={m.id} className={`node ${m.id === openId ? 'cur' : ''}`} onClick={() => setOpenId(m.id)}>
              {thumbOf(m) ? <img src={thumbOf(m)!} alt="" /> : <span className="ph">—</span>}
              <span>
                {m.title} · {m.version}
                <small>{METHOD_LABEL[m.method] ?? m.method}{m.refs.length ? ` · ${m.refs.length} ${m.refs.length === 1 ? 'předloha' : 'předlohy'}` : ''} · {fmtUsd(m.cost_usd)}</small>
              </span>
            </button>
          ))}
          {!models.length && <p className="hint">Zatím žádný model.</p>}
        </div>
        <button className="btn small" onClick={newModel}>+ Nový model</button>

        <h3>{target ? `Nová verze: ${title}` : 'Nový model: předlohy'}</h3>
        {!isUpload && (
          <>
            <div className="slots">
              {SLOTS.map(({ view, label }) => {
                const s = slots.find((x) => x.view === view)
                return s ? (
                  <div key={view} className="slot filled">
                    {s.cutout ? <img src={dataUrl(s.cutout)} alt="" onClick={() => setEditing(view)} title="Zvětšit a umazat gumou" />
                      : <span className="ph">vyřezávám…</span>}
                    <span className="slot-lbl">{label}</span>
                    <button className="x" onClick={() => setSlot(view, null)} title="Odebrat">×</button>
                  </div>
                ) : (
                  <div key={view} className="slot empty">
                    <span>+ {label}{view !== 'front' ? ' (nepovinné)' : ''}</span>
                    <span className="slot-act">
                      <button className="btn small" onClick={() => pickFile(view)}>Soubor</button>
                      <button className="btn small" onClick={() => setPicker(view)}>Knihovna</button>
                    </span>
                  </div>
                )
              })}
            </div>
            <p className="hint">Pozadí se vyřízne samo. Klik na předlohu = zvětšit a umazat gumou, co k objektu nepatří.</p>
            <p className="hint">⚠ Zezadu: chobot ani ocas nesmí být vidět mezi nohama, jinak vznikne končetina navíc.</p>
          </>
        )}
        {isUpload && (
          <div className="row">
            <input ref={glbInput} type="file" accept=".glb" hidden onChange={async (e) => {
              const f = e.target.files?.[0]
              if (f) setGlb({ name: f.name, b64: await fileToB64(f) })
            }} />
            <button className="btn small" onClick={() => glbInput.current?.click()}>Vybrat soubor .glb</button>
            <span className="hint">{glb ? glb.name : 'z Blenderu, skriptu nebo dřívějšího běhu'}</span>
          </div>
        )}
        <input className="title-in" placeholder="Název modelu (např. Tatra 87)" value={title} onChange={(e) => setTitle(e.target.value)} />
        <div className="seg method">
          {[
            { id: 'fal-hunyuan3d', label: `Hunyuan3D${filled.length > 1 ? ` · ${filled.length} předlohy` : ''}` },
            { id: 'fal-trellis2', label: 'TRELLIS 2' },
            { id: 'upload', label: 'Nahrát GLB' },
          ].map((o) => {
            const on = (method ?? est?.recommended ?? (filled.length > 1 ? 'fal-hunyuan3d' : 'fal-trellis2')) === o.id
            return <button key={o.id} className={on ? 'on' : ''} onClick={() => setMethod(o.id)}>{o.label}</button>
          })}
        </div>
        {!isUpload && est && (
          <p className="hint">{method === null || method === est.recommended
            ? `Doporučeno: ${filled.length > 1 ? 'máte víc než jednu předlohu.' : 'jedna předloha.'}`
            : `Doporučeno by bylo ${METHOD_LABEL[est.recommended]}.`}</p>
        )}
        <button className="btn primary" disabled={!canCreate} onClick={create}>{sending ? 'Odesílám…' : btnLabel}</button>
        <p className="hint">Kliknutí je souhlas s cenou. Nahraný GLB je zdarma.</p>
      </aside>

      <section className="card m3d-views">
        {!cur ? <p className="empty">Vyberte model vlevo, nebo založte nový.</p> : (
          <>
            <h3>{cur.title} · {cur.version} · bílé pohledy (jen tvar, barvy dodá generátor)</h3>
            <div className="seg full">
              {ELEVATIONS.map((e) => (
                <button key={e.el} className={el === e.el ? 'on' : ''} onClick={() => renderEl(e.el)}
                  title={cur.views[String(e.el)] ? '' : 'Ještě nevykresleno: kliknutí zadá render (0 USD)'}>
                  {e.label}{cur.views[String(e.el)] ? '' : ' ·'}
                </button>
              ))}
            </div>
            {cur.status === 'failed' && (
              <div className="banner-in bad">
                {cur.error}
                {cur.request_id && !cur.views['20'] && (
                  <button className="btn small" onClick={async () => { try { await m3dApi.recover(cur.id, cur.version); load() } catch (e) { onError(String((e as Error).message)) } }}>
                    Vyzvednout zaplacený výsledek (bez platby)
                  </button>
                )}
              </div>
            )}
            {viewSet ? (
              <div className="views8">
                {AZ.map((a) => (
                  <figure key={a} className={a === az ? 'sel' : ''} onClick={() => setAz(a)}>
                    <img src={m3dApi.file(cur.id, cur.version, `${viewSet.dir}/az${String(a).padStart(3, '0')}.png`, 512)} alt={`${a}°`} />
                    <span className="lbl">{a}°{a === az ? ' · vybráno' : ''}</span>
                    <button className="zoom-btn" onClick={(e) => { e.stopPropagation(); setZoom(a) }} title="Zvětšit">⤢</button>
                  </figure>
                ))}
              </div>
            ) : (
              <div className="views-empty">
                {pending ? `${pending.status === 'running' ? 'Běží' : 'Čeká ve frontě'}: ${KIND_LABEL[pending.kind]} (${pending.status === 'running' ? 'chvilku' : `před ní ${pending.position ?? 0}`})`
                  : cur.status === 'model' ? (
                    <button className="btn" onClick={() => renderEl(el)}>Vykreslit bílé pohledy · 0 USD</button>
                  ) : lastFail?.error ?? STATUS[cur.status].label}
              </div>
            )}
            {viewSet && (
              <div className="checkbar">
                <label className="row check">
                  <input type="checkbox" checked={!!cur.review} onChange={(e) => toggleReview(e.target.checked)} />
                  <span><b>Model zkontrolován</b>: počet nohou a kol, úlomky, části navíc (⤢ u pohledu = zvětšit)</span>
                </label>
                <span className="grow" />
                <button className="btn small" onClick={() => setStretchOpen(true)}>Natáhnout na rozměry…</button>
                <button className="btn small" onClick={() => newVersionOf(cur)}>Nová verze</button>
              </div>
            )}
          </>
        )}
      </section>

      <aside className="card">
        <h3>O modelu</h3>
        {cur && (
          <>
            <dl>
              <dt>Metoda</dt><dd>{METHOD_LABEL[cur.method] ?? cur.method}{cur.method === 'fal-hunyuan3d' ? ' (tvar bez textury)' : ''}{cur.parent ? ` z ${cur.parent}` : ''}</dd>
              <dt>Předlohy</dt><dd>{cur.refs.length ? cur.refs.map((r) => <div key={r.view}>{SLOTS.find((s) => s.view === r.view)?.label}: {r.source ?? '?'}{r.license ? `, ${r.license}` : ''}</div>) : (cur.origin ?? '—')}</dd>
              <dt>Cena</dt><dd>{fmtUsd(cur.cost_usd)}</dd>
              {cur.stats?.bbox && <><dt>Rozměry</dt><dd>poměr d:š:v {ratio(cur.stats.bbox)}
                {cur.stretch && <div className="hint">zadáno {cur.stretch.dims.join(' × ')} m{cur.stretch.source ? ` (${cur.stretch.source})` : ''}</div>}</dd></>}
              {cur.stats && <><dt>Síť</dt><dd>{cur.stats.verts.toLocaleString('cs-CZ')} vrcholů</dd></>}
              <dt>Verze</dt>
              <dd>
                <select value={cur.version} onChange={(e) => setVer(e.target.value)}>
                  {versions.map((v) => <option key={v.version} value={v.version}>{v.version} ({METHOD_LABEL[v.method] ?? v.method}, {v.created.slice(0, 10)})</option>)}
                </select>
              </dd>
              <dt>Stav</dt><dd><span className={`tag ${cur.review ? 'ok' : STATUS[cur.status].cls}`}>{cur.review ? 'zkontrolováno' : STATUS[cur.status].label}</span></dd>
            </dl>
            <button className="btn primary" disabled={!cur.review || !viewSet} onClick={toStudio}>→ Studio jako tvarová předloha</button>
            <p className="hint">Aktivní po zaškrtnutí „Model zkontrolován“. Vybraný pohled ({az}°) jde do zadání jako předloha „tvar“.</p>
            <a className="btn small" href={m3dApi.glb(cur.id, cur.version)} download>Stáhnout GLB</a>
          </>
        )}
      </aside>

      <div className="queue m3d-queue">
        <b>Běží</b> {running ? jobLabel(running) : 'nic'} · <b>Čeká</b> {waiting.length ? waiting.map(jobLabel).join(', ') : 'nic'}
        <span className="hint"> (Blender a FLUX se střídají v jedné frontě; render jede na procesoru, FLUX zůstane načtený)</span>
      </div>

      {editing && slots.find((s) => s.view === editing)?.cutout && (
        <Eraser slot={slots.find((s) => s.view === editing)!} onClose={() => setEditing(null)}
          onSave={(b64) => { setSlot(editing, { cutout: b64 }); setEditing(null) }} />
      )}
      {picker && <RefPicker initialTab="commons" onPick={(m) => fromLibrary(picker, m)} onError={onError} onClose={() => setPicker(null)} />}
      {zoomSrc && (
        <div className="lightbox" onClick={() => setZoom(null)}>
          <div className="lb-bar" onClick={(e) => e.stopPropagation()}>
            <button className="btn small" onClick={() => setZoom(AZ[(AZ.indexOf(zoom!) + 7) % 8])}>← {AZ[(AZ.indexOf(zoom!) + 7) % 8]}°</button>
            <button className="btn small" onClick={() => setZoom(AZ[(AZ.indexOf(zoom!) + 1) % 8])}>{AZ[(AZ.indexOf(zoom!) + 1) % 8]}° →</button>
            <button className="btn small" onClick={() => setZoom(null)}>Zavřít (Esc)</button>
          </div>
          <div className="lb-img fit m3d-zoom" onClick={(e) => e.stopPropagation()}><img src={zoomSrc} alt="" /></div>
        </div>
      )}
      {stretchOpen && cur && (
        <Stretch m={cur} onClose={() => setStretchOpen(false)} onError={onError}
          onDone={(v) => { setStretchOpen(false); setVer(v); load() }} />
      )}
    </main>
  )
}

/** Enlarged cutout over a checkerboard; dragging erases (alpha 0). */
function Eraser({ slot, onSave, onClose }: { slot: Slot; onSave: (b64: string) => void; onClose: () => void }) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const [size, setSize] = useState(30)
  const drawing = useRef(false)
  const load = useCallback((b64: string) => {
    const img = new Image()
    img.onload = () => {
      const c = canvas.current!
      c.width = img.width; c.height = img.height
      const ctx = c.getContext('2d')!
      ctx.clearRect(0, 0, c.width, c.height)
      ctx.drawImage(img, 0, 0)
    }
    img.src = dataUrl(b64)
  }, [])
  useEffect(() => { load(slot.cutout!) }, [load, slot.cutout])
  const erase = (e: React.PointerEvent) => {
    if (!drawing.current) return
    const c = canvas.current!
    const r = c.getBoundingClientRect()
    const k = c.width / r.width
    const ctx = c.getContext('2d')!
    ctx.globalCompositeOperation = 'destination-out'
    ctx.beginPath()
    ctx.arc((e.clientX - r.left) * k, (e.clientY - r.top) * k, size * k / 2, 0, Math.PI * 2)
    ctx.fill()
    ctx.globalCompositeOperation = 'source-over'
  }
  return (
    <div className="modal" onClick={onClose}>
      <div className="dialog eraser" onClick={(e) => e.stopPropagation()}>
        <h2>Výřez předlohy: umažte gumou, co k objektu nepatří</h2>
        <p className="hint">Cedulky, pozadí mezi nohama, lidé okolo: z nich generátor udělá plovoucí úlomky nebo části navíc.</p>
        <div className="checker">
          <canvas ref={canvas} onPointerDown={(e) => { drawing.current = true; e.currentTarget.setPointerCapture(e.pointerId); erase(e) }}
            onPointerMove={erase} onPointerUp={() => { drawing.current = false }} style={{ cursor: 'crosshair' }} />
        </div>
        <div className="row">
          <span>Guma</span>
          <input type="range" min={6} max={120} value={size} onChange={(e) => setSize(+e.target.value)} />
          <span className="hint">{size} px</span>
          <span className="grow" />
          <button className="btn small" onClick={() => load(slot.cutout!)}>Vrátit změny</button>
          <button className="btn small" onClick={onClose}>Zrušit</button>
          <button className="btn go" onClick={() => onSave(canvas.current!.toDataURL('image/png').split(',')[1])}>Hotovo</button>
        </div>
      </div>
    </div>
  )
}

/** Q4: dimensions from the source and which part to lengthen; the result is a new version. */
function Stretch({ m, onClose, onDone, onError }: { m: Model3dVersion; onClose: () => void; onDone: (v: string) => void; onError: (msg: string) => void }) {
  const [dims, setDims] = useState(['', '', ''])
  const [part, setPart] = useState('middle')
  const [source, setSource] = useState('')
  const alongX = !m.stats || m.stats.bbox[0] >= m.stats.bbox[1]
  const parts = [
    { id: 'middle', label: 'střed', hint: 'oba konce drží tvar (kola zůstanou kulatá)' },
    { id: 'end-min', label: `konec u pohledu ${alongX ? 180 : 270}°`, hint: 'jen tahle třetina se protáhne' },
    { id: 'end-max', label: `konec u pohledu ${alongX ? 0 : 90}°`, hint: 'jen tahle třetina se protáhne' },
    { id: 'all', label: 'celé', hint: 'každý rozměr zvlášť; tvar se může zdeformovat' },
  ]
  const ok = dims.every((d) => +d.replace(',', '.') > 0)
  return (
    <div className="modal" onClick={onClose}>
      <div className="dialog" onClick={(e) => e.stopPropagation()}>
        <h2>Natáhnout na rozměry</h2>
        <p className="hint">Rozměry ze zdroje v metrech. Vznikne nová verze, {m.version} zůstane.</p>
        <div className="row">
          {['délka', 'šířka', 'výška'].map((l, i) => (
            <label key={l} className="dim">{l}<input value={dims[i]} inputMode="decimal" onChange={(e) => setDims(dims.map((d, j) => (j === i ? e.target.value : d)))} /></label>
          ))}
        </div>
        <label className="dim wide">zdroj rozměrů<input value={source} placeholder="např. Wikipedia: Tatra 87" onChange={(e) => setSource(e.target.value)} /></label>
        <h3>Kterou část protáhnout</h3>
        <div className="seg wrap">
          {parts.map((p) => <button key={p.id} className={part === p.id ? 'on' : ''} onClick={() => setPart(p.id)} title={p.hint}>{p.label}</button>)}
        </div>
        <p className="hint">{parts.find((p) => p.id === part)?.hint}. Protažení středu udělalo z Tatry limuzínu (měření 27. 10.).</p>
        <div className="row end">
          <button className="btn" onClick={onClose}>Zrušit</button>
          <button className="btn go" disabled={!ok} onClick={async () => {
            try {
              const r = await m3dApi.stretch(m.id, m.version, dims.map((d) => +d.replace(',', '.')), part, source)
              onDone(r.version)
            } catch (e) { onError(String((e as Error).message)) }
          }}>Natáhnout · 0 USD</button>
        </div>
      </div>
    </div>
  )
}
