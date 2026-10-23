import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  api, fileToB64, imageUrl, isCzech, onlyTranslation, PaymentRequired,
  type Backend, type Estimate, type Health, type ImageRequest, type Job, type RefIn, type Role,
} from './api.ts'
import Stage from './Stage.tsx'
import { HistoryPanel, Lightbox } from './panels.tsx'

// ~1 MP per format, all multiples of 16 (Engine requirement)
const FORMATS: Record<string, string> = {
  '1:1': '1024x1024', '16:9': '1344x768', '3:2': '1248x832', '4:3': '1152x864', '3:4': '864x1152',
}
const ROLE_LABEL: Record<Role, string> = { subject: 'předmět', geometry: 'tvar', scene: 'scéna', style: 'styl' }
const SUPERSAMPLE = 1.875

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
  const [tab, setTab] = useState<'studio' | 'library'>('studio')
  const [selected, setSelected] = useState<string | null>(null)
  const [lightbox, setLightbox] = useState<string | null>(null)
  const [confirm, setConfirm] = useState<Confirm | null>(null)
  const [toast, setToast] = useState<string | null>(null)

  const [prompt, setPrompt] = useState('')
  const [refs, setRefs] = useState<(RefIn & { name: string; preview: string })[]>([])
  const [format, setFormat] = useState('16:9')
  const [n, setN] = useState(1)
  const [detail, setDetail] = useState(false)
  const [translate, setTranslate] = useState(true)
  const [backend, setBackend] = useState('flux-local')
  const [estimate, setEstimate] = useState<Estimate | null>(null)
  const [expanding, setExpanding] = useState(false)
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
      refs: refs.map(({ b64, role, text, source }) => ({ b64, role, text, source })),
      supersample: canSupersample && detail ? SUPERSAMPLE : null,
      translate: translate ? 'auto' : 'off',
      caller: 'studio',
    }),
    [prompt, backend, format, n, refs, detail, canSupersample, translate],
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

  const addFiles = async (files: FileList | File[]) => {
    const added = await Promise.all(
      [...files].filter((f) => f.type.startsWith('image/')).map(async (f) => ({
        b64: await fileToB64(f), role: 'subject' as Role, name: f.name, preview: URL.createObjectURL(f), source: f.name,
      })),
    )
    setRefs((r) => [...r, ...added].slice(0, 10))
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
          <button className={tab === 'library' ? 'on' : ''} onClick={() => setTab('library')}>Knihovna</button>
          <span className="off" title="Fáze G4">Styly</span>
          <span className="off" title="Fáze G5">Infografiky</span>
        </nav>
        <div className="status">
          <span className={`chip ${engineDown ? 'bad' : ''}`}><span className={`dot ${health?.sd_server ?? 'off'}`} />{fluxState}</span>
          <span className="chip">Fronta: {active.filter((j) => j.status === 'running').length} běží, {active.filter((j) => j.status === 'queued').length} čeká</span>
          <span className="chip">Útrata dnes: {fmtUsd(Math.round(spentToday * 1000) / 1000)}</span>
        </div>
      </header>

      {engineDown && <div className="banner">GRAFIK Engine na :8300 neodpovídá. Spusťte <code>start-grafik.bat</code>.</div>}

      {tab === 'library' ? (
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
                <div className="ref" key={i}>
                  <img src={r.preview} alt="" />
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
                <label className="drop" onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); addFiles(e.dataTransfer.files) }}>
                  + Přetáhněte obrázek nebo klikněte
                  <input type="file" accept="image/*" multiple hidden onChange={(e) => e.target.files && addFiles(e.target.files)} />
                </label>
              )}
            </div>
            <p className="hint">Předmět, tvar a scéna jdou do generátoru jako obraz. Styl jen slovy: přenos stylu obrazem FLUX neumí.</p>
            {!usesRefs && refs.length > 0 && <p className="warn">Zvolený generátor předlohy neumí.</p>}

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
          </section>

          <Stage
            selected={selected}
            job={selJob}
            onOpen={setLightbox}
            onUseAsRef={useAsRef}
            onSubmit={submit}
            onVariant={variant}
            onReuse={(j) => {
              setPrompt(j.request.prompt)
              const f = Object.entries(FORMATS).find(([, s]) => s === j.request.size)
              if (f) setFormat(f[0])
            }}
            footer={
              <div className="queue">
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
