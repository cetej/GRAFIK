import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  api, fileToB64, imageUrl, infoApi, isCzech, onlyTranslation, PaymentRequired, refsApi, stylesApi,
  type Backend, type Batch, type Estimate, type Health, type ImageRequest, type Job, type RefIn, type RefMeta, type Role, type StyleCard,
} from './api.ts'
import Stage from './Stage.tsx'
import { HistoryPanel, Lightbox } from './panels.tsx'
import RefPicker, { storeDrop, type PickerTab } from './RefPicker.tsx'
import Wizard from './Wizard.tsx'
import Settings from './Settings.tsx'
import Styles, { Swatches } from './Styles.tsx'
import Infographics from './Infographics.tsx'
import Models3d from './Models3d.tsx'
import Scenes3d from './Scenes3d.tsx'
import { BatchPanel, BatchRow } from './Batch.tsx'

// ~1 MP per format, all multiples of 16 (Engine requirement)
const FORMATS: Record<string, string> = {
  '1:1': '1024x1024', '16:9': '1344x768', '3:2': '1248x832', '4:3': '1152x864', '3:4': '864x1152',
}
export const ROLE_LABEL: Record<Role, string> = { subject: 'předmět', geometry: 'tvar', scene: 'scéna', style: 'styl' }
const SUPERSAMPLE = 1.875

export type FormRef = RefIn & { name: string; preview: string; meta?: string }

export const refFromMeta = (m: RefMeta, role: Role = 'geometry'): FormRef => ({
  ref_id: m.id, role, name: m.title, preview: `${m.image}?w=256`,
  meta: [m.origin === 'commons' ? 'Commons' : m.origin === 'pinterest' ? 'Pinterest' : m.origin === 'web' ? 'web' : 'soubor', m.license].filter(Boolean).join(' · '),
})

export interface Confirm { title: string; items: { what: string; usd: number }[]; total: number; onOk: () => Promise<void> }

export const fmtUsd = (usd: number) => (usd === 0 ? '0 USD' : `${usd.toLocaleString('cs-CZ', { maximumFractionDigits: 3 })} USD`)
// Translation-only costs are confirmed by the click: the button already shows the price (decision 2026-10-23).
export const priceLabel = (e: Estimate | null) =>
  !e ? '…' : `${fmtUsd(e.total_usd)}${e.items.some((i) => i.kind === 'translation') ? ' za překlad' : ''}`
export const fmtTime = (s: number) => (s < 90 ? `~${Math.max(5, Math.round(s / 5) * 5)} s` : `~${Math.round(s / 60)} min`)

const backendLabel = (b: Backend) => {
  if (b.id === 'flux-local') return 'Lokální FLUX — zdarma'
  if (b.id === 'nb-pro') return `Nano Banana Pro (Gemini) — ${fmtUsd(b.usd_1024)}/obr.`
  return `fal: ${b.id.replace('fal:fal-ai/', '')} — od ${fmtUsd(b.usd_1024)}/obr.`
}

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [engineDown, setEngineDown] = useState(false)
  const [backends, setBackends] = useState<Backend[]>([])
  const [jobs, setJobs] = useState<Job[]>([])
  const [spentToday, setSpentToday] = useState(0)
  const [tab, setTab] = useState<'studio' | 'guide' | 'library' | 'styles' | 'info' | '3d' | 'settings'>('studio')
  const [mode3d, setMode3d] = useState<'models' | 'scenes'>('models')
  const [picker, setPicker] = useState<PickerTab | null>(null)
  const [inboxNew, setInboxNew] = useState(0)
  const [selected, setSelected] = useState<string | null>(null)
  const [lightbox, setLightbox] = useState<string | null>(null)
  const [confirm, setConfirm] = useState<Confirm | null>(null)
  const [toast, setToast] = useState<string | null>(null)

  const [prompt, setPrompt] = useState('')
  const [refs, setRefs] = useState<FormRef[]>([])
  const [format, setFormat] = useState('16:9')
  const [n, setN] = useState(1)
  const [detail, setDetail] = useState(false)
  const [translate, setTranslate] = useState(true)
  const [backend, setBackend] = useState('flux-local')
  const [estimate, setEstimate] = useState<Estimate | null>(null)
  const [expanding, setExpanding] = useState(false)
  const [styleCards, setStyleCards] = useState<StyleCard[]>([])
  const [styleSel, setStyleSel] = useState('') // '' = bez stylu, '__custom' = vlastní text, jinak slug karty
  const [styleText, setStyleText] = useState('')
  const [detectOpen, setDetectOpen] = useState(false)
  const [infoId, setInfoId] = useState<string | null>(null)
  const [batches, setBatches] = useState<Batch[]>(() => {
    try { return JSON.parse(localStorage.getItem('grafik.batches') ?? '[]') } catch { return [] }
  })
  useEffect(() => {
    try { localStorage.setItem('grafik.batches', JSON.stringify(batches)) } catch { /* private window */ }
  }, [batches])
  const pendingSelect = useRef<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const [h, js] = await Promise.all([api.health(), api.jobs()])
      setHealth(h)
      setJobs(js)
      setEngineDown(false)
      const want = pendingSelect.current
      const done = want && js.find((j) => j.job_id === want && j.status === 'done')
      if (done) {
        setSelected(`${done.job_id}/0`)
        pendingSelect.current = null
      }
    } catch {
      setEngineDown(true)
    }
  }, [])

  useEffect(() => {
    refresh()
    api.backends().then(setBackends).catch(() => setEngineDown(true))
    const t = setInterval(refresh, 2000)
    return () => clearInterval(t)
  }, [refresh])

  const doneImages = useMemo(
    () => jobs.filter((j) => j.status === 'done').flatMap((j) => j.images.map((_, i) => ({ ref: `${j.job_id}/${i}`, job: j }))),
    [jobs],
  )
  useEffect(() => {
    if (!selected && doneImages.length) setSelected(doneImages[0].ref)
  }, [doneImages, selected])

  useEffect(() => {
    const today = new Date().toISOString().slice(0, 10)
    api.costs().then((c) => setSpentToday(c.entries.filter((e) => e.ts.startsWith(today)).reduce((a, e) => a + e.usd, 0))).catch(() => {})
  }, [jobs.length])

  const usesRefs = backends.find((b) => b.id === backend)?.refs ?? true
  const canSupersample = backend === 'flux-local'
  const formRequest = useCallback(
    (): ImageRequest => ({
      prompt: prompt.trim() || '-',
      backend,
      size: FORMATS[format],
      n,
      refs: refs.map(({ b64, ref_id, role, text, source }) => ({ b64, ref_id, role, text, source })),
      supersample: canSupersample && detail ? SUPERSAMPLE : null,
      translate: translate ? 'auto' : 'off',
      style: styleSel === '__custom' ? styleText.trim() || null : styleSel || null,
      style_id: styleSel && styleSel !== '__custom' ? styleSel : null,
      caller: 'studio',
    }),
    [prompt, backend, format, n, refs, detail, canSupersample, translate, styleSel, styleText],
  )

  useEffect(() => {
    const t = setTimeout(() => {
      api.estimate(formRequest()).then(setEstimate).catch(() => setEstimate(null))
    }, 350)
    return () => clearTimeout(t)
  }, [formRequest])

  const submit = useCallback(async (req: ImageRequest, what: string) => {
    try {
      const r = await api.submit(req)
      pendingSelect.current = r.job_id
      refresh()
    } catch (e) {
      if (e instanceof PaymentRequired && onlyTranslation(e.items) && req.translate !== 'off') {
        try {
          pendingSelect.current = (await api.submit({ ...req, confirm_cost: true })).job_id
          refresh()
        } catch (e2) {
          setToast(String((e2 as Error).message))
        }
      } else if (e instanceof PaymentRequired) {
        setConfirm({
          title: what, items: e.items, total: e.estimate,
          onOk: async () => {
            const r = await api.submit({ ...req, confirm_cost: true })
            pendingSelect.current = r.job_id
            refresh()
          },
        })
      } else setToast(String((e as Error).message))
    }
  }, [refresh])

  useEffect(() => {
    if (tab === 'studio') stylesApi.list().then(setStyleCards).catch(() => {})
  }, [tab])
  const styleCard = styleCards.find((c) => c.slug === styleSel) ?? null

  // Style tab: submit and return the job id (translation-only costs confirmed by the click, like the studio button).
  const submitForStyle = useCallback(async (req: ImageRequest): Promise<string | null> => {
    try {
      return (await api.submit(req)).job_id
    } catch (e) {
      if (e instanceof PaymentRequired && onlyTranslation(e.items)) {
        try { return (await api.submit({ ...req, confirm_cost: true })).job_id } catch (e2) { setToast((e2 as Error).message) }
      } else setToast((e as Error).message)
      return null
    } finally { refresh() }
  }, [refresh])

  const openInfographic = useCallback(async (ref: string, title: string) => {
    try {
      setInfoId((await infoApi.create(ref, title)).id)
      setTab('info')
    } catch (e) { setToast((e as Error).message) }
  }, [])

  const variant = useCallback(async (ref: string) => {
    const [id, k] = ref.split('/')
    try {
      pendingSelect.current = (await api.repeat(id, Number(k))).job_id
      refresh()
    } catch (e) {
      if (e instanceof PaymentRequired && onlyTranslation(e.items)) {
        pendingSelect.current = (await api.repeat(id, Number(k), true)).job_id
        refresh()
      } else if (e instanceof PaymentRequired) {
        setConfirm({
          title: 'Další varianta', items: e.items, total: e.estimate,
          onOk: async () => { pendingSelect.current = (await api.repeat(id, Number(k), true)).job_id; refresh() },
        })
      } else setToast(String((e as Error).message))
    }
  }, [refresh])

  const expand = async () => {
    if (!prompt.trim()) return
    const run = async () => {
      setExpanding(true)
      try {
        setPrompt((await api.expand(prompt, true)).prompt)
      } catch (e) {
        setToast(String((e as Error).message))
      } finally {
        setExpanding(false)
      }
    }
    setConfirm({ title: 'Rozepsat zadání (Claude)', items: [{ what: 'rozepsání zadání do anglického promptu', usd: 0.01 }], total: 0.01, onOk: run })
  }

  const pickRef = useCallback((m: RefMeta) => setRefs((r) => (r.some((x) => x.ref_id === m.id) ? r : [...r, refFromMeta(m)].slice(0, 10))), [])
  const countInbox = useCallback(() => {
    refsApi.list().then((l) => setInboxNew(l.filter((m) => !m.seen && m.origin !== 'upload').length)).catch(() => {})
  }, [])
  useEffect(countInbox, [countInbox])

  // Bookmarklet "→ GRAFIK" opens the studio as /#addref=<image>&page=<page>&title=<title>
  useEffect(() => {
    const h = new URLSearchParams(location.hash.slice(1))
    const url = h.get('addref')
    if (!url) return
    history.replaceState(null, '', location.pathname)
    refsApi.addUrl(url, h.get('page') ?? undefined, h.get('title') ?? undefined)
      .then(() => { setToast('Předloha je ve schránce.'); countInbox(); setPicker('inbox') })
      .catch((e) => setToast(`Předlohu se nepodařilo uložit: ${e.message}`))
  }, [countInbox])

  const dropRefs = async (dt: DataTransfer) => {
    try {
      const metas = await storeDrop(dt)
      if (!metas.length) setToast('V přetaženém není obrázek ani jeho adresa.')
      metas.forEach(pickRef)
    } catch (e) {
      setToast(String((e as Error).message))
    }
  }

  const useAsRef = async (ref: string) => {
    const blob = await (await fetch(imageUrl(ref))).blob()
    setRefs((r) => [...r, { b64: '', role: 'scene' as Role, name: ref, preview: imageUrl(ref, 256), source: `verze ${ref}` }].slice(0, 10))
    const b64 = await fileToB64(blob)
    setRefs((r) => r.map((x) => (x.name === ref && !x.b64 ? { ...x, b64 } : x)))
  }

  const active = jobs.filter((j) => j.status === 'queued' || j.status === 'running').reverse()
  const recentFailed = jobs.filter((j) => j.status === 'failed' && j.finished && Date.now() / 1000 - j.finished < 600).slice(0, 2)
  const selJob = selected ? jobs.find((j) => j.job_id === selected.split('/')[0]) ?? null : null
  const fluxState = engineDown ? 'Engine neběží' : health?.sd_server === 'ready' ? 'Lokální FLUX připraven'
    : health?.sd_server === 'starting' ? 'Lokální FLUX startuje' : 'Lokální FLUX spí (probudí se sám)'

  const genLabel = `Vygenerovat${n > 1 ? ` ${n} varianty` : ''} · ${priceLabel(estimate)}${estimate?.eta_s ? ` · ${fmtTime(estimate.eta_s)}` : ''}`

  return (
    <>
      <header>
        <b>GRAFIK Studio</b>
        <nav>
          <button className={tab === 'studio' ? 'on' : ''} onClick={() => setTab('studio')}>Studio</button>
          <button className={tab === 'guide' ? 'on' : ''} onClick={() => setTab('guide')}>Průvodce</button>
          <button className={tab === 'library' ? 'on' : ''} onClick={() => setTab('library')}>Knihovna</button>
          <button className={tab === 'styles' ? 'on' : ''} onClick={() => setTab('styles')}>Styly</button>
          <button className={tab === 'info' ? 'on' : ''} onClick={() => setTab('info')}>Infografiky</button>
          <button className={tab === '3d' ? 'on' : ''} onClick={() => setTab('3d')}>3D</button>
          <button className={tab === 'settings' ? 'on' : ''} onClick={() => setTab('settings')}>Nastavení</button>
        </nav>
        <div className="status">
          <span className={`chip ${engineDown ? 'bad' : ''}`}><span className={`dot ${health?.sd_server ?? 'off'}`} />{fluxState}</span>
          <span className="chip">Fronta: {active.filter((j) => j.status === 'running').length} běží, {active.filter((j) => j.status === 'queued').length} čeká</span>
          <span className="chip">Útrata dnes: {fmtUsd(Math.round(spentToday * 1000) / 1000)}</span>
        </div>
      </header>

      {engineDown && <div className="banner">GRAFIK Engine na :8300 neodpovídá. Spusťte <code>start-grafik.bat</code>.</div>}

      {tab === 'settings' ? (
        <Settings onError={setToast} />
      ) : tab === '3d' ? (
        mode3d === 'scenes' ? (
          <Scenes3d onError={setToast} onModels={() => setMode3d('models')}
            onToStudio={(ref, hint) => {
              setRefs((r) => [...r, ref].slice(0, 10))
              // the size sentence in the prompt's language (LEARNINGS 2026-10-23: the generator enlarges people)
              setPrompt((p) => { const h = !p.trim() || isCzech(p) ? hint.cs : hint.en; return h && !p.includes(h) ? (p.trim() ? `${p.trim().replace(/[.;,]$/, '')}. ${h}` : h) : p })
              setTab('studio')
              setToast(`Snímek scény ${ref.name} je v předlohách jako „tvar“, věta o rozměrech v zadání.`)
            }} />
        ) : (
          <Models3d onError={setToast} onScenes={() => setMode3d('scenes')}
            onToStudio={(ref) => { setRefs((r) => [...r, ref].slice(0, 10)); setTab('studio'); setToast(`Pohled ${ref.name} je v předlohách jako „tvar“.`) }} />
        )
      ) : tab === 'info' ? (
        <Infographics openId={infoId} setOpenId={setInfoId} selectedImage={selected}
          recentImages={doneImages.map((d) => d.ref)} onError={setToast} />
      ) : tab === 'styles' ? (
        <Styles onError={setToast} onSubmit={submitForStyle} selectedImage={selected}
          openDetect={detectOpen} onDetectOpen={() => setDetectOpen(true)} onDetectClosed={() => setDetectOpen(false)}
          onUse={(slug) => { setStyleSel(slug); setTab('studio') }} />
      ) : tab === 'guide' ? (
        <Wizard jobs={jobs} onOpen={setLightbox} onSubmit={submit} setConfirm={setConfirm} onError={setToast}
          onOpenInStudio={(ref) => { setSelected(ref); setTab('studio') }} onInfographic={openInfographic} />
      ) : tab === 'library' ? (
        <main className="library">
          {doneImages.length === 0 && <p className="empty">Knihovna je prázdná.</p>}
          {doneImages.map(({ ref, job }) => (
            <figure key={ref} onClick={() => { setSelected(ref); setTab('studio') }} title="Otevřít ve studiu">
              <img src={imageUrl(ref, 384)} loading="lazy" alt="" />
              <figcaption>{(job.request.edit?.instruction ?? job.request.prompt).slice(0, 90)}</figcaption>
            </figure>
          ))}
        </main>
      ) : (
        <main className="studio">
          <section className="card left">
            <h3>Zadání</h3>
            <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="Co má být na obrázku. Česky nebo anglicky." />
            {isCzech(prompt) && (
              <label className="row check">
                <input type="checkbox" checked={translate} onChange={(e) => setTranslate(e.target.checked)} />
                Přeložit do angličtiny pro zvolený generátor <span className="hint">Claude, ~0,01 USD; stejný text podruhé zdarma</span>
              </label>
            )}
            {isCzech(prompt) && !translate && <p className="warn">Česky rozumí FLUX jen zhruba (ověřeno: z „majáku“ udělal dům).</p>}
            <div className="row">
              <button className="btn small" onClick={expand} disabled={expanding || !prompt.trim()}>{expanding ? 'Rozepisuji…' : 'Rozepsat zadání (Claude)'}</button>
              <span className="hint">~0,01 USD, potvrdíte předem</span>
            </div>

            <h3>Předlohy</h3>
            <div className="refs">
              {refs.map((r, i) => (
                <div className="ref" key={i} title={r.name}>
                  <img src={r.preview} alt="" />
                  {r.meta && <div className="refmeta">{r.meta}</div>}
                  <button className="x" title="Odebrat" onClick={() => setRefs(refs.filter((_, j) => j !== i))}>×</button>
                  <select value={r.role} onChange={(e) => setRefs(refs.map((x, j) => (j === i ? { ...x, role: e.target.value as Role } : x)))}>
                    {(Object.keys(ROLE_LABEL) as Role[]).map((k) => <option key={k} value={k}>{ROLE_LABEL[k]}</option>)}
                  </select>
                  {r.role === 'style' && (
                    <input className="styletext" placeholder="styl slovy (jinak Claude, placené)" value={r.text ?? ''}
                      onChange={(e) => setRefs(refs.map((x, j) => (j === i ? { ...x, text: e.target.value } : x)))} />
                  )}
                </div>
              ))}
              {refs.length < 10 && (
                <label className="drop" onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); dropRefs(e.dataTransfer) }}>
                  + Přetáhněte obrázek nebo klikněte
                  <input type="file" accept="image/*" multiple hidden onChange={(e) => {
                    const dt = new DataTransfer()
                    ;[...(e.target.files ?? [])].forEach((f) => dt.items.add(f))
                    dropRefs(dt)
                    e.target.value = ''
                  }} />
                </label>
              )}
            </div>
            <div className="sources">
              <button className="btn small" onClick={() => setPicker('commons')}>Hledat ve Wikimedia Commons</button>
              <button className="btn small" onClick={() => setPicker('inbox')}>Schránka předloh{inboxNew ? <span className="tag new">{inboxNew} nové</span> : null}</button>
            </div>
            <p className="hint">Předmět, tvar a scéna jdou do generátoru jako obraz. Styl jen slovy: přenos stylu obrazem FLUX neumí.</p>
            {!usesRefs && refs.length > 0 && <p className="warn">Zvolený generátor předlohy neumí.</p>}

            <h3>Styl</h3>
            {styleCard ? (
              <div className="style-pick">
                {styleCard.sample_urls[0] ? <img src={styleCard.sample_urls[0]} alt="" /> : <span className="ph" />}
                <div className="grow"><b>{styleCard.label}</b><Swatches palette={styleCard.palette} small /></div>
              </div>
            ) : styleSel === '__custom' ? (
              <input className="search full" value={styleText} onChange={(e) => setStyleText(e.target.value)}
                placeholder="styl slovy, např. tužková kresba" aria-label="Vlastní styl slovy" />
            ) : null}
            <select className="full" value={styleSel} onChange={(e) => setStyleSel(e.target.value)} aria-label="Styl">
              <option value="">bez stylu</option>
              {styleCards.map((c) => <option key={c.slug} value={c.slug}>{c.label}</option>)}
              <option value="__custom">vlastní text…</option>
            </select>
            <div className="row">
              <button className="btn small" onClick={() => { setDetectOpen(true); setTab('styles') }}>+ styl z obrázku</button>
              <button className="btn small" onClick={() => setTab('styles')}>Knihovna stylů</button>
            </div>
            <p className="hint">Styl se k zadání připojí slovy. Obrázek stylu se generátoru nikdy neposílá.</p>

            <h3>Formát</h3>
            <div className="seg">
              {Object.keys(FORMATS).map((f) => <button key={f} className={format === f ? 'on' : ''} onClick={() => setFormat(f)}>{f}</button>)}
            </div>
            <div className="row">
              <span>Varianty</span>
              <div className="seg">{[1, 2, 3, 4].map((k) => <button key={k} className={n === k ? 'on' : ''} onClick={() => setN(k)}>{k}</button>)}</div>
            </div>
            <label className={`row check ${canSupersample ? '' : 'disabled'}`}>
              <input type="checkbox" checked={detail && canSupersample} disabled={!canSupersample} onChange={(e) => setDetail(e.target.checked)} />
              Drobné detaily (vykreslit větší a zmenšit) <span className="hint">~3× déle</span>
            </label>

            <h3>Generátor</h3>
            <select className="full" value={backend} onChange={(e) => setBackend(e.target.value)}>
              {backends.map((b) => <option key={b.id} value={b.id}>{backendLabel(b)}</option>)}
            </select>
            <button className="btn primary" disabled={engineDown || !prompt.trim()} onClick={() => submit(formRequest(), 'Vygenerovat')}>{genLabel}</button>
            <p className="hint">Placený generátor se před spuštěním zeptá na cenu.</p>
            <BatchPanel request={formRequest} styleCards={styleCards} styleSel={styleSel} styleText={styleText}
              disabled={engineDown || !prompt.trim() || backend !== 'flux-local'}
              onCreated={(b) => { setBatches((bs) => [b, ...bs].slice(0, 3)); refresh() }}
              onConfirm={setConfirm} onError={setToast} />
          </section>

          <Stage
            selected={selected}
            job={selJob}
            onOpen={setLightbox}
            onUseAsRef={useAsRef}
            onSubmit={submit}
            onVariant={variant}
            onInfographic={(ref) => openInfographic(ref, (selJob?.request.edit ? '' : selJob?.request.prompt ?? '').slice(0, 60))}
            onReuse={(j) => {
              setPrompt(j.request.prompt)
              const sid = (j.request as ImageRequest).style_id
              if (sid) setStyleSel(sid)
              const f = Object.entries(FORMATS).find(([, s]) => s === j.request.size)
              if (f) setFormat(f[0])
            }}
            footer={
              <div className="queue">
                {batches.map((b) => <BatchRow key={b.id} batch={b} jobs={jobs} />)}
                {active.map((j) => <QueueRow key={j.job_id} job={j} onCancel={() => api.cancel(j.job_id).then(refresh)} />)}
                {recentFailed.map((j) => (
                  <div className="job failed" key={j.job_id}><b>Selhalo</b><span>{j.error}</span></div>
                ))}
                {active.length === 0 && recentFailed.length === 0 && <div className="job idle">Fronta je prázdná.</div>}
                <div className="gallery">
                  {doneImages.slice(0, 14).map(({ ref }) => (
                    <button key={ref} className={`thumb ${ref === selected ? 'sel' : ''}`} onClick={() => setSelected(ref)} title="Vybrat">
                      <img src={imageUrl(ref, 256)} alt="" loading="lazy" />
                    </button>
                  ))}
                </div>
              </div>
            }
          />

          <HistoryPanel selected={selected} jobs={jobs} onSelect={setSelected} />
        </main>
      )}

      {lightbox && <Lightbox src={lightbox} onClose={() => setLightbox(null)} />}
      {picker && <RefPicker initialTab={picker} onPick={pickRef} onError={setToast} onClose={() => { setPicker(null); countInbox() }} />}
      {confirm && <ConfirmDialog c={confirm} onClose={() => setConfirm(null)} />}
      {toast && <div className="toast" onClick={() => setToast(null)}>{toast} <b>×</b></div>}
    </>
  )
}

function etaFor(req: ImageRequest): number | null {
  if ((req.backend ?? 'flux-local') !== 'flux-local') return null
  const [w, h] = (req.size ?? '1024x1024').split('x').map(Number)
  let mp = (w * h) / 1e6
  if (req.supersample) mp = Math.min(mp * req.supersample ** 2, 1920 * 1088 / 1e6)
  return (5 + 38 * mp) * (req.n ?? 1)
}

function QueueRow({ job, onCancel }: { job: Job; onCancel: () => void }) {
  const [now, setNow] = useState(Date.now() / 1000)
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now() / 1000), 1000)
    return () => clearInterval(t)
  }, [])
  const eta = etaFor(job.request)
  const elapsed = job.started ? now - job.started : 0
  const pct = eta && job.status === 'running' ? Math.min(95, (elapsed / eta) * 100) : 0
  const what = job.request.edit ? `úprava: ${job.request.edit.instruction}` : job.request.prompt
  return (
    <div className="job">
      <b>{job.status === 'running' ? 'Běží' : 'Čeká'}</b>
      <span className="what">{what.slice(0, 70)}</span>
      {job.caller !== 'studio' && <span className="hint">{job.caller}</span>}
      {job.status === 'running' ? (
        <>
          <div className="bar"><i style={{ width: `${pct}%` }} /></div>
          <span className="hint">{Math.round(elapsed)} s{eta ? ` z ${fmtTime(eta)}` : ''}</span>
        </>
      ) : (
        <>
          <span className="hint grow">{job.position ? `${job.position}. ve frontě` : 'na řadě'}</span>
          <button className="btn small" onClick={onCancel}>Zrušit</button>
        </>
      )}
    </div>
  )
}

function ConfirmDialog({ c, onClose }: { c: Confirm; onClose: () => void }) {
  const [busy, setBusy] = useState(false)
  return (
    <div className="modal" onClick={onClose}>
      <div className="dialog" onClick={(e) => e.stopPropagation()}>
        <h2>Placená operace</h2>
        <p>{c.title}</p>
        <table>
          <tbody>
            {c.items.map((i) => <tr key={i.what}><td>{i.what}</td><td className="num">{fmtUsd(i.usd)}</td></tr>)}
            <tr className="total"><td>Celkem (odhad)</td><td className="num">{fmtUsd(c.total)}</td></tr>
          </tbody>
        </table>
        <div className="row end">
          <button className="btn" onClick={onClose}>Zrušit</button>
          <button className="btn pay" disabled={busy} onClick={async () => { setBusy(true); try { await c.onOk() } finally { onClose() } }}>
            Zaplatit a spustit · {fmtUsd(c.total)}
          </button>
        </div>
      </div>
    </div>
  )
}
