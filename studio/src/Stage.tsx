import { useEffect, useRef, useState, type ReactNode } from 'react'
import { api, imageUrl, isCzech, ManualEdit, type Box, type EditAction, type Estimate, type ImageRequest, type Job } from './api.ts'
import { fmtTime, priceLabel } from './App.tsx'

const ACTIONS: { id: EditAction; label: string; hint: string }[] = [
  { id: 'add', label: 'Přidat', hint: 'co má v rámečku přibýt' },
  { id: 'remove', label: 'Odstranit', hint: 'co z rámečku zmizí' },
  { id: 'move', label: 'Přesunout', hint: 'co se přesune (cíl nakreslíte potom)' },
  { id: 'recolor', label: 'Přebarvit / změnit', hint: 'co a jak změnit' },
]

interface Props {
  selected: string | null
  job: Job | null
  onOpen: (src: string) => void
  onUseAsRef: (ref: string) => void
  onSubmit: (req: ImageRequest, what: string) => Promise<void>
  onReuse: (job: Job) => void
  onVariant: (ref: string) => void
  onInfographic: (ref: string) => void
  onLocalize: (ref: string) => void
  onError: (msg: string) => void
  footer: ReactNode
}

type Mode = 'view' | 'compare' | 'box'

export default function Stage({ selected, job, onOpen, onUseAsRef, onSubmit, onReuse, onVariant, onInfographic, onLocalize, onError, footer }: Props) {
  const [mode, setMode] = useState<Mode>('view')
  // a finished picture with its own layers opens whole in VectorCraft, without a 16:9 document around it
  const [layered, setLayered] = useState(false)
  const [vcAsk, setVcAsk] = useState<string | null>(null)
  const [vcOpened, setVcOpened] = useState<string | null>(null)
  useEffect(() => {
    setLayered(false)
    setVcAsk(null)
    setVcOpened(null)
    if (selected) api.provenance(selected).then((p) => setLayered(!!p.vectorcraft_svg)).catch(() => setLayered(false))
  }, [selected])
  const parent = job?.request.parent ?? null
  // "before" = the parent version, else the first image reference (image-to-image)
  const firstImageRef = job?.request.refs.findIndex((r) => r.role !== 'style') ?? -1
  const before = parent ? imageUrl(parent) : job && firstImageRef >= 0 ? `/api/v2/jobs/${job.job_id}/refs/${firstImageRef}` : null
  useEffect(() => setMode('view'), [selected])

  if (!selected) {
    return (
      <section className="stage">
        <div className="canvas empty-stage">
          <div>
            <h2>Začněte zadáním vlevo</h2>
            <p>Napište, co má být na obrázku, případně přidejte předlohu, a klikněte na Vygenerovat.</p>
          </div>
        </div>
        {footer}
      </section>
    )
  }

  const src = imageUrl(selected)
  const openVectorcraft = async (how?: 'edited' | 'new') => {
    setVcAsk(null)
    try {
      setVcOpened((await api.openVectorcraft(selected, how)).opened)
    } catch (e) {
      if (e instanceof ManualEdit) setVcAsk(e.message)
      else onError((e as Error).message)
    }
  }
  return (
    <section className="stage">
      <div className="toolbar">
        <button className={`btn ${mode === 'box' ? 'active' : ''}`} onClick={() => setMode(mode === 'box' ? 'view' : 'box')}>▭ Upravit v rámečku</button>
        <button className={`btn ${mode === 'compare' ? 'active' : ''}`} disabled={!before}
          title={before ? 'Posuvníkem porovnáte s předchozí verzí nebo předlohou' : 'Tenhle obrázek nemá předchozí verzi ani předlohu'}
          onClick={() => setMode(mode === 'compare' ? 'view' : 'compare')}>⇔ Porovnat před/po</button>
        <button className="btn" onClick={() => onVariant(selected)} title="Stejné zadání i předlohy, nový seed">↻ Další varianta</button>
        <button className="btn" onClick={() => onUseAsRef(selected)}>→ Použít jako předlohu</button>
        {job && !job.request.edit && <button className="btn" onClick={() => onReuse(job)}>✎ Upravit zadání</button>}
        <a className="btn" href={src} download={`grafik-${selected.replace('/', '-')}.png`}>⤓ Stáhnout PNG</a>
        {layered && <button className="btn go" onClick={() => openVectorcraft()} title="Celý obrázek, každý popisek a objekt zvlášť ve vrstvách">Otevřít ve VectorCraftu</button>}
        <button className={`btn ${layered ? '' : 'go'}`} onClick={() => onInfographic(selected)}>→ Infografika</button>
        <button className="btn" onClick={() => onLocalize(selected)}>→ Počeštit</button>
      </div>
      {vcAsk && (
        <div className="row">
          <span className="hint">{vcAsk}</span>
          <button className="btn small" onClick={() => openVectorcraft('edited')}>Otevřít ruční úpravu</button>
          <button className="btn small" onClick={() => openVectorcraft('new')}>Otevřít novou kopii</button>
        </div>
      )}
      {vcOpened && <p className="hint">Otevřeno ve VectorCraftu: {vcOpened}</p>}
      <div className="canvas">
        {mode === 'compare' && before ? (
          <Compare before={before} after={src} />
        ) : mode === 'box' ? (
          <BoxEditor src={src} selected={selected} onSubmit={onSubmit} onDone={() => setMode('view')} />
        ) : (
          <img className="main" src={src} alt="" onClick={() => onOpen(src)} title="Kliknutím zvětšíte" />
        )}
        {mode === 'view' && <button className="btn small zoom" onClick={() => onOpen(src)}>⤢ Zvětšit</button>}
      </div>
      {footer}
    </section>
  )
}

function Compare({ before, after }: { before: string; after: string }) {
  const [pos, setPos] = useState(50)
  const ref = useRef<HTMLDivElement>(null)
  const drag = (e: React.PointerEvent) => {
    if (e.buttons !== 1 && e.type !== 'pointerdown') return
    const r = ref.current!.getBoundingClientRect()
    setPos(Math.max(0, Math.min(100, ((e.clientX - r.left) / r.width) * 100)))
  }
  return (
    <div className="compare" ref={ref} onPointerDown={drag} onPointerMove={drag}>
      <img src={before} alt="před" draggable={false} />
      <img src={after} alt="po" className="after" style={{ clipPath: `inset(0 0 0 ${pos}%)` }} draggable={false} />
      <div className="knob" style={{ left: `${pos}%` }} />
      <span className="lbl" style={{ left: 10 }}>Před</span>
      <span className="lbl" style={{ right: 10 }}>Po</span>
    </div>
  )
}

function boxStyle(b: Box) {
  const [t, l, bo, r] = b
  return { top: `${t / 10}%`, left: `${l / 10}%`, height: `${(bo - t) / 10}%`, width: `${(r - l) / 10}%` }
}

export function BoxEditor({ src, selected, onSubmit, onDone }: {
  src: string; selected: string; onSubmit: Props['onSubmit']; onDone: () => void
}) {
  const wrap = useRef<HTMLDivElement>(null)
  const [box, setBox] = useState<Box | null>(null)
  const [target, setTarget] = useState<Box | null>(null)
  const [drawing, setDrawing] = useState<'box' | 'target'>('box')
  const [start, setStart] = useState<[number, number] | null>(null)
  const [live, setLive] = useState<Box | null>(null)
  const [action, setAction] = useState<EditAction>('remove')
  const [instruction, setInstruction] = useState('')
  const [est, setEst] = useState<Estimate | null>(null)
  const [error, setError] = useState<string | null>(null)

  const pt = (e: React.PointerEvent): [number, number] => {
    const r = wrap.current!.getBoundingClientRect()
    const clamp = (v: number) => Math.round(Math.max(0, Math.min(1000, v)))
    return [clamp(((e.clientY - r.top) / r.height) * 1000), clamp(((e.clientX - r.left) / r.width) * 1000)]
  }
  const toBox = (a: [number, number], b: [number, number]): Box =>
    [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[0], b[0]), Math.max(a[1], b[1])]

  const request = (): ImageRequest | null =>
    box && instruction.trim() && (action !== 'move' || target)
      ? { prompt: '-', parent: selected, caller: 'studio',
          edit: { action, bbox: box, target_bbox: action === 'move' ? target : null, instruction: instruction.trim() } }
      : null

  useEffect(() => {
    const req = request()
    if (!req) return setEst(null)
    const t = setTimeout(() => api.estimate(req).then((x) => { setEst(x); setError(null) }).catch((e) => setError(e.message)), 300)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [box, target, action, instruction])

  return (
    <div className="boxwrap">
      <div className="boxarea" ref={wrap}
        onPointerDown={(e) => {
          try { (e.target as HTMLElement).setPointerCapture(e.pointerId) } catch { /* pen/synthetic pointers */ }
          setStart(pt(e))
          setLive(null)
        }}
        onPointerMove={(e) => start && setLive(toBox(start, pt(e)))}
        onPointerUp={(e) => {
          if (!start) return
          const b = toBox(start, pt(e))
          setStart(null)
          setLive(null)
          if (b[2] - b[0] < 15 || b[3] - b[1] < 15) return
          if (drawing === 'target') { setTarget(b); setDrawing('box') } else { setBox(b); setTarget(null) }
        }}>
        <img src={src} alt="" draggable={false} />
        {box && <div className="bbox" style={boxStyle(box)} />}
        {target && <div className="bbox target" style={boxStyle(target)} />}
        {live && <div className={`bbox ${drawing === 'target' ? 'target' : ''}`} style={boxStyle(live)} />}
      </div>
      <div className="pop">
        <b>Úprava v rámečku</b>
        {!box ? (
          <p className="hint">Tažením myší nakreslete rámeček kolem místa, které chcete změnit.</p>
        ) : (
          <>
            <div className="seg wrap">
              {ACTIONS.map((a) => <button key={a.id} className={action === a.id ? 'on' : ''} onClick={() => setAction(a.id)}>{a.label}</button>)}
            </div>
            <input autoFocus value={instruction} onChange={(e) => setInstruction(e.target.value)}
              placeholder={ACTIONS.find((a) => a.id === action)!.hint} />
            {action === 'move' && (
              <button className={`btn small ${drawing === 'target' ? 'active' : ''}`} onClick={() => setDrawing('target')}>
                {target ? 'Nakreslit cíl znovu' : 'Nakreslit cíl (kam to přesunout)'}
              </button>
            )}
            <div className="row">
              <button className="btn small go" disabled={!request()}
                onClick={async () => { await onSubmit(request()!, 'Úprava v rámečku'); onDone() }}>
                Provést{est ? ` · ${priceLabel(est)}${est.eta_s ? ` · ${fmtTime(est.eta_s)}` : ''}` : ''}
              </button>
              <button className="btn small" onClick={onDone}>Zrušit</button>
            </div>
            {isCzech(instruction) && <p className="hint">Pokyn přeloží Claude do angličtiny (cena je v tlačítku).</p>}
            <p className="hint">Mimo rámeček zůstane obraz beze změny.</p>
          </>
        )}
        {error && <p className="warn">{error}</p>}
      </div>
    </div>
  )
}
