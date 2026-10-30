import { useCallback, useEffect, useState, type DragEvent } from 'react'
import { fileToB64, imageUrl, localizeApi, PaymentRequired, type LocalizeJob, type LocalizeTexts } from './api.ts'
import { fmtUsd, type Confirm } from './App.tsx'

// Krok 2 algoritmu operátora (STOPA plán 2026-10-29): počeštěná kopie cizojazyčné infografiky nebo mapy.
// Engine: engine/localize.py. Čtení textu je placené (dialog s cenou), oprava překladu a nová sazba zdarma.
type Source = { b64?: string; image?: string; preview: string; label: string }

const RECENT = 6
const running = (j: LocalizeJob | null) => j?.status === 'queued' || j?.status === 'running'

const fromLibrary = (ref: string): Source => ({ image: ref, preview: imageUrl(ref, 960), label: `verze ${ref}` })

export default function Localize({ selectedImage, pickRef, onOpen, setConfirm, onError }: {
  selectedImage: string | null
  pickRef: string | null     // obrázek poslaný tlačítkem „→ Počeštit“ ze Studia
  onOpen: (src: string) => void
  setConfirm: (c: Confirm) => void
  onError: (msg: string) => void
}) {
  const [source, setSource] = useState<Source | null>(pickRef ? fromLibrary(pickRef) : null)
  const [jobId, setJobId] = useState<string | null>(null)
  const [job, setJob] = useState<LocalizeJob | null>(null)
  const [texts, setTexts] = useState<LocalizeTexts | null>(null)
  const [dirty, setDirty] = useState(false)
  const [recent, setRecent] = useState<LocalizeJob[]>([])
  const [usd, setUsd] = useState<number | null>(null)

  const loadRecent = useCallback(() => {
    localizeApi.jobs(RECENT).then(setRecent).catch((e: Error) => onError(e.message))
  }, [onError])

  useEffect(() => {
    loadRecent()
    localizeApi.estimate().then((e) => setUsd(e.usd)).catch((e: Error) => onError(e.message))
  }, [loadRecent, onError])

  useEffect(() => {
    if (!jobId) return
    let alive = true
    let timer = 0
    const tick = async () => {
      try {
        const j = await localizeApi.job(jobId)
        if (!alive) return
        setJob(j)
        if (running(j)) { timer = window.setTimeout(tick, 1500); return }
        loadRecent()
        if (j.status === 'done') {
          const t = await localizeApi.texts(jobId)
          if (alive) { setTexts(t); setDirty(false) }
        }
      } catch (e) {
        if (alive) onError((e as Error).message)
      }
    }
    tick()
    return () => { alive = false; window.clearTimeout(timer) }
  }, [jobId, loadRecent, onError])

  const pick = (s: Source) => { setSource(s); setJobId(null); setJob(null); setTexts(null); setDirty(false) }

  const addFile = async (file?: File) => {
    if (!file) return
    if (!file.type.startsWith('image/')) { onError(`${file.name} není obrázek.`); return }
    try {
      pick({ b64: await fileToB64(file), preview: URL.createObjectURL(file), label: file.name })
    } catch (e) { onError((e as Error).message) }
  }

  const start = async (confirm = false): Promise<void> => {
    if (!source) return
    try {
      const body = source.image ? { image: source.image } : { b64: source.b64 }
      setJob(null); setTexts(null)
      setJobId((await localizeApi.start({ ...body, confirm_cost: confirm })).job_id)
    } catch (e) {
      if (e instanceof PaymentRequired) {
        setConfirm({ title: 'Počeštit obrázek', items: e.items, total: e.estimate, onOk: () => start(true) })
      } else onError((e as Error).message)
    }
  }

  const retypeset = async () => {
    if (!job || !texts) return
    try {
      setJobId((await localizeApi.start({ source_job: job.job_id, texts })).job_id)
    } catch (e) { onError((e as Error).message) }
  }

  const setCs = (id: number, cs: string) => {
    setTexts((t) => t && { ...t, elements: t.elements.map((el) => (el.id === id ? { ...el, cs } : el)) })
    setDirty(true)
  }

  const openJob = (j: LocalizeJob) => {
    setSource({ preview: localizeApi.file(j.job_id, 'original'), label: j.request.source ?? j.job_id })
    setJob(null); setTexts(null); setJobId(j.job_id)
  }

  const original = job ? localizeApi.file(job.job_id, 'original') : source?.preview
  const done = job?.status === 'done' ? job : null
  const onDrop = (e: DragEvent) => { e.preventDefault(); addFile(e.dataTransfer.files[0]) }

  return (
    <main className="loc">
      <section className="card loc-start" onDragOver={(e) => e.preventDefault()} onDrop={onDrop}>
        <h2>Počeštěná kopie infografiky nebo mapy</h2>
        <div className="loc-actions">
          <label className="btn">
            Nahrát obrázek
            <input type="file" accept="image/*" hidden onChange={(e) => { addFile(e.target.files?.[0]); e.target.value = '' }} />
          </label>
          {selectedImage && (
            <button className="btn" onClick={() => pick(fromLibrary(selectedImage))}>Vzít vybraný obrázek ze Studia</button>
          )}
          {source && !job && !jobId && (
            <button className="btn go" onClick={() => start()}>Počeštit{usd !== null ? ` · ~${fmtUsd(usd)}` : ''}</button>
          )}
          {source && <span className="loc-name">{source.label}</span>}
        </div>
        {!source && <p className="hint">Obrázek můžete také přetáhnout sem. Claude přečte texty a přeloží je, kód je vymaže a vysází česky. Obraz zůstane původní.</p>}
      </section>

      {running(job) && <p className="sc-hint">{job?.status === 'queued' ? 'Čeká ve frontě…' : 'Čtu texty a sázím češtinu, obvykle do minuty…'}</p>}
      {job?.status === 'failed' && <p className="banner">Počeštění selhalo: {job.error}</p>}

      {original && (
        <section className="loc-pair">
          <figure className="card">
            <figcaption>Originál</figcaption>
            <button className="loc-img" title="Zvětšit" onClick={() => onOpen(original)}><img src={original} alt="Originál" /></button>
          </figure>
          <figure className="card">
            <figcaption>Česká kopie</figcaption>
            {done
              ? <button className="loc-img" title="Zvětšit" onClick={() => onOpen(done.images[0])}><img src={done.images[0]} alt="Česká kopie" /></button>
              : <p className="empty">Zatím není.</p>}
          </figure>
        </section>
      )}

      {done && (
        <section className="card">
          {done.result?.warnings.map((w) => (
            <p className="sc-hint" key={w.what}><b>{w.what}</b> {w.fix}</p>
          ))}
          <div className="loc-actions">
            <a className="btn" href={done.images[0]} download={`${done.job_id}-cs.png`}>Stáhnout PNG</a>
            <a className="btn" href={localizeApi.file(done.job_id, 'image-0.svg')} download={`${done.job_id}-cs.svg`}>Stáhnout SVG</a>
            <span className="loc-name">Cena: {fmtUsd(done.result?.cost_usd ?? 0)}</span>
          </div>
          {texts && (
            <details className="loc-texts">
              <summary>Opravit překlady ({texts.elements.length})</summary>
              <div className="loc-grid">
                {texts.elements.map((el) => (
                  <label key={el.id}>
                    <span>{el.en}</span>
                    <textarea rows={Math.max(el.cs.split('\n').length, Math.ceil(el.cs.length / 32))} value={el.cs} onChange={(e) => setCs(el.id, e.target.value)} />
                  </label>
                ))}
              </div>
              {dirty
                ? <button className="btn go" onClick={retypeset}>Vysázet znovu · zdarma</button>
                : <span className="loc-name">Po změně překladu půjde vysázet znovu, zdarma.</span>}
            </details>
          )}
        </section>
      )}

      {recent.length > 0 && (
        <section className="card">
          <h3>Naposledy počeštěné</h3>
          <div className="loc-recent">
            {recent.filter((j) => j.status === 'done').map((j) => (
              <button key={j.job_id} className={j.job_id === jobId ? 'on' : ''} title={j.request.source ?? j.job_id} onClick={() => openJob(j)}>
                <img src={imageUrl(`${j.job_id}/0`, 256)} alt="" loading="lazy" />
              </button>
            ))}
          </div>
        </section>
      )}
    </main>
  )
}
