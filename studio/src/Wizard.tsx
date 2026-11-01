import { useCallback, useEffect, useState } from 'react'
import {
  api, imageUrl, onlyTranslation, PaymentRequired, refsApi, wfApi,
  type Estimate, type ImageRequest, type Job, type LineageNode, type RefMeta, type Role, type Workflow,
} from './api.ts'
import Podklady, { TopicStart } from './Podklady.tsx'
import { fmtTime, priceLabel, refFromMeta, ROLE_LABEL, type Confirm, type FormRef } from './App.tsx'
import RefPicker, { type PickerTab } from './RefPicker.tsx'
import { BoxEditor } from './Stage.tsx'

// Guided workflow "historický objekt" (approved 2026-10-22): engine/workflows.py builds the prompts.
const STEPS = ['Předlohy', 'Čistý bokorys', 'Oprava v rámečku', 'Natočený pohled', 'Popisky'] as const
const VIEWS: Record<string, string> = { '34_left': '3/4 shora zleva', '34_right': '3/4 shora zprava', front: 'čelně shora' }
const BACKGROUNDS: Record<string, string> = { studio: 'tmavé studio', sea: 'moře' }

interface Props {
  jobs: Job[]
  onOpen: (src: string) => void
  onSubmit: (req: ImageRequest, what: string) => Promise<void>
  setConfirm: (c: Confirm) => void
  onError: (msg: string) => void
  onOpenInStudio: (ref: string) => void
  onInfographic: (ref: string, title: string) => void
  onInfographicDoc: (id: string) => void
  onUseRef: (m: RefMeta) => void
}

export default function Wizard(props: Props) {
  const [list, setList] = useState<Workflow[]>([])
  const [wf, setWf] = useState<Workflow | null>(null)
  const [research, setResearch] = useState<string | null>(null)
  useEffect(() => { wfApi.list().then(setList).catch((e) => props.onError(e.message)) }, [wf?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  if (research) {
    return <Podklady id={research} onBack={() => setResearch(null)} onOpenVersion={setResearch} onOpen={props.onOpen} setConfirm={props.setConfirm}
      onError={props.onError} onUseRef={props.onUseRef} onInfographicDoc={props.onInfographicDoc} />
  }
  if (!wf) {
    return (
      <main className="guide-start">
        <TopicStart onOpen={setResearch} onError={props.onError} />
        <section className="card">
          <h2>Průvodce historickým objektem</h2>
          <p>Postup ověřený 22. 10.: předloha → čistý bokorys → oprava v rámečku → natočený pohled 3/4 shora → popisky.
            Každý krok vytvoří normální verze, takže se k nim dá vrátit i ve studiu.</p>
          <button className="btn go" onClick={() => wfApi.create('', []).then(setWf).catch((e) => props.onError(e.message))}>+ Nový objekt</button>
          {list.length > 0 && <h3>Rozpracované</h3>}
          <div className="wf-list">
            {list.map((w) => (
              <button key={w.id} className="wf-item" onClick={() => setWf(w)}>
                {w.pick || w.fixed || w.side_pick ? <img src={imageUrl((w.pick || w.fixed || w.side_pick)!, 256)} alt="" /> : <span className="ph">bez obrázku</span>}
                <span>{w.object || 'bez popisu'}<small>{w.updated.replace('T', ' ')}</small></span>
              </button>
            ))}
          </div>
        </section>
      </main>
    )
  }
  return <WizardRun {...props} wf={wf} setWf={setWf} onBack={() => setWf(null)} />
}

function WizardRun({ wf, setWf, onBack, jobs, onOpen, onSubmit, setConfirm, onError, onOpenInStudio, onInfographic }: Props & {
  wf: Workflow; setWf: (w: Workflow) => void; onBack: () => void
}) {
  const [object, setObject] = useState(wf.object)
  const [refs, setRefs] = useState<FormRef[]>([])
  const [picker, setPicker] = useState<PickerTab | null>(null)
  const [step, setStep] = useState(wf.pick ? 3 : wf.side_pick ? 2 : wf.side_job ? 1 : 0)
  const [nSide, setNSide] = useState(3)
  const [view, setView] = useState(wf.view)
  const [background, setBackground] = useState(wf.background)
  const [nRot, setNRot] = useState(2)
  const [est, setEst] = useState<Estimate | null>(null)
  const [fixes, setFixes] = useState<LineageNode[]>([])

  // library metadata for the workflow's refs (titles, licences)
  useEffect(() => {
    refsApi.list().then((all) => setRefs(wf.refs.map((r) => {
      const m = all.find((x) => x.id === r.ref_id)
      return m ? refFromMeta(m, r.role) : { ref_id: r.ref_id, role: r.role, name: r.ref_id, preview: `/api/v2/refs/${r.ref_id}/image?w=256` }
    }))).catch(() => {})
  }, [wf.id]) // eslint-disable-line react-hooks/exhaustive-deps

  const save = useCallback(async (body: Parameters<typeof wfApi.patch>[1]) => {
    try { setWf(await wfApi.patch(wf.id, body)) } catch (e) { onError((e as Error).message) }
  }, [wf.id, setWf, onError])

  const saveSetup = () => save({ object, refs: refs.map((r) => ({ ref_id: r.ref_id!, role: r.role })) })
  const job = (id: string | null) => (id ? jobs.find((j) => j.job_id === id) ?? null : null)
  const sideJob = job(wf.side_job)
  const rotJob = job(wf.rotate_job)
  const base = wf.fixed || wf.side_pick

  // estimate for the step's main button
  useEffect(() => {
    setEst(null)
    const run = step === 1 ? () => wfApi.side(wf.id, nSide, { estimate_only: true })
      : step === 3 && base ? () => wfApi.rotate(wf.id, { view, background, n: nRot }, { estimate_only: true }) : null
    if (!run || !wf.object || !wf.refs.length) return
    run().then(setEst).catch(() => setEst(null))
  }, [step, nSide, nRot, view, background, wf.id, wf.object, wf.refs.length, base])

  // fixes = box edits made from the chosen elevation (chain)
  useEffect(() => {
    if (step !== 2 || !wf.side_pick) return
    api.lineage(wf.side_pick).then((t) => setFixes(t.filter((n) => n.request.edit))).catch(() => setFixes([]))
  }, [step, wf.side_pick, jobs.filter((j) => j.status === 'done').length]) // eslint-disable-line react-hooks/exhaustive-deps

  const runStep = async (kind: 'side' | 'rotate', confirm = false) => {
    const call = (c: boolean) => (kind === 'side' ? wfApi.side(wf.id, nSide, { confirm_cost: c })
      : wfApi.rotate(wf.id, { view, background, n: nRot }, { confirm_cost: c }))
    try {
      await call(confirm)
      setWf(await wfApi.get(wf.id))
    } catch (e) {
      if (e instanceof PaymentRequired && onlyTranslation(e.items)) return runStep(kind, true)
      if (e instanceof PaymentRequired) {
        return setConfirm({ title: kind === 'side' ? 'Čistý bokorys' : 'Natočený pohled', items: e.items, total: e.estimate,
          onOk: async () => { await call(true); setWf(await wfApi.get(wf.id)) } })
      }
      onError((e as Error).message)
    }
  }

  const canStep = [true, !!wf.object && wf.refs.length > 0, !!wf.side_pick, !!wf.side_pick, !!wf.pick]
  const done = [canStep[1], !!wf.side_pick, !!wf.side_pick && step > 2, !!wf.pick, false]

  return (
    <main className="guide">
      <section className="guide-main">
        <div className="row">
          <button className="btn small" onClick={onBack}>← Rozpracované</button>
          <b className="guide-title">Historický objekt{wf.object ? `: ${wf.object.slice(0, 60)}` : ''}</b>
        </div>
        <div className="steps">
          {STEPS.map((label, i) => (
            <button key={label} className={`step ${i === step ? 'cur' : ''} ${done[i] && i !== step ? 'done' : ''}`}
              disabled={!canStep[i]} onClick={() => setStep(i)}>
              <span className="n">{done[i] && i !== step ? '✓' : i + 1}</span>{label}
            </button>
          ))}
        </div>

        {step === 0 && (
          <div className="card">
            <h3>Objekt</h3>
            <textarea value={object} onChange={(e) => setObject(e.target.value)}
              placeholder="Co to je a z jaké doby, se znaky, které musí sedět. Např. římská kvinquerema z 1. punské války: pět řad veslařů, dřevěná věž, corvus na přídi, bronzové beranidlo se třemi žebry." />
            <h3>Předlohy objektu</h3>
            <div className="refs wide">
              {refs.map((r, i) => (
                <div className="ref" key={r.ref_id} title={r.name}>
                  <img src={r.preview} alt="" />
                  <button className="x" title="Odebrat" onClick={() => setRefs(refs.filter((_, j) => j !== i))}>×</button>
                  {r.meta && <div className="refmeta">{r.meta}</div>}
                  <select value={r.role} onChange={(e) => setRefs(refs.map((x, j) => (j === i ? { ...x, role: e.target.value as Role } : x)))}>
                    {(['geometry', 'subject', 'scene'] as Role[]).map((k) => <option key={k} value={k}>{ROLE_LABEL[k]}</option>)}
                  </select>
                </div>
              ))}
            </div>
            <div className="sources">
              <button className="btn small" onClick={() => setPicker('commons')}>Hledat ve Wikimedia Commons</button>
              <button className="btn small" onClick={() => setPicker('inbox')}>Schránka předloh</button>
              <button className="btn small" onClick={() => setPicker('file')}>Soubor</button>
            </div>
            <p className="hint">První předloha by měla ukazovat objekt z boku: podle ní se kreslí bokorys. Další slouží jen pro detaily.</p>
            <div className="row end">
              <button className="btn go" disabled={!object.trim() || !refs.length}
                onClick={async () => { await saveSetup(); setStep(1) }}>Uložit a pokračovat →</button>
            </div>
          </div>
        )}

        {step === 1 && (
          <div className="card">
            <p>FLUX z předlohy nakreslí čistý bokorys: přesný profil bez perspektivy, muzejní model, tmavé pozadí, bez textu.</p>
            <div className="row">
              <span>Variant</span>
              <div className="seg">{[1, 2, 3, 4].map((k) => <button key={k} className={nSide === k ? 'on' : ''} onClick={() => setNSide(k)}>{k}</button>)}</div>
              <button className="btn go" onClick={() => runStep('side')} disabled={isActive(sideJob)}>
                Vygenerovat bokorys · {priceLabel(est)}{est?.eta_s ? ` · ${fmtTime(est.eta_s)}` : ''}
              </button>
            </div>
            <Candidates job={sideJob} pick={wf.side_pick} onOpen={onOpen}
              onPick={(ref) => save({ side_pick: ref }).then(() => setStep(2))} pickLabel="Vybrat a opravit →" />
          </div>
        )}

        {step === 2 && base && (
          <div className="card">
            <p>Opravte, co nesedí: tažením nakreslete rámeček, zvolte akci a napište, co změnit. Mimo rámeček zůstane obraz beze změny.
              Když je bokorys v pořádku, pokračujte rovnou.</p>
            <div className="fixbox">
              <BoxEditor src={imageUrl(base)} selected={base} onSubmit={onSubmit} onDone={() => {}} />
            </div>
            {fixes.length > 0 && <h3>Opravy</h3>}
            <div className="cands small">
              {fixes.map((f) => (
                <div key={f.ref} className={`cand ${f.ref === wf.fixed ? 'sel' : ''}`}>
                  {f.image ? <img src={imageUrl(f.ref, 512)} alt="" onClick={() => onOpen(imageUrl(f.ref))} /> : <div className="ph">generuje se…</div>}
                  <div className="act">
                    <span className="hint">{f.request.edit?.instruction.slice(0, 40)}</span>
                    <button className="btn small" disabled={!f.image || f.ref === wf.fixed} onClick={() => save({ fixed: f.ref })}>
                      {f.ref === wf.fixed ? '✓ Použito' : 'Použít'}
                    </button>
                  </div>
                </div>
              ))}
            </div>
            <div className="row end">
              {wf.fixed && <button className="btn" onClick={() => save({ fixed: null })}>Zpět na neopravený</button>}
              <button className="btn go" onClick={() => setStep(3)}>{wf.fixed ? 'Pokračovat s opravou →' : 'Bez opravy dál →'}</button>
            </div>
          </div>
        )}

        {step === 3 && base && (
          <div className="card">
            <div className="src">
              <img src={imageUrl(base, 512)} alt="" onClick={() => onOpen(imageUrl(base))} />
              <div>
                <b>Z bokorysu se natočí pohled</b>
                <p className="hint">Tvar, proporce a barvy se drží bokorysu; vykreslí se větší a zmenší, aby drobné postavy nebyly zdeformované.</p>
                <div className="row">
                  <span>Pohled</span>
                  <div className="seg">{Object.entries(VIEWS).map(([k, v]) => <button key={k} className={view === k ? 'on' : ''} onClick={() => setView(k)}>{v}</button>)}</div>
                </div>
                <div className="row">
                  <span>Pozadí</span>
                  <div className="seg">{Object.entries(BACKGROUNDS).map(([k, v]) => <button key={k} className={background === k ? 'on' : ''} onClick={() => setBackground(k)}>{v}</button>)}</div>
                  <span>Variant</span>
                  <div className="seg">{[1, 2, 3].map((k) => <button key={k} className={nRot === k ? 'on' : ''} onClick={() => setNRot(k)}>{k}</button>)}</div>
                </div>
                <button className="btn go" onClick={() => runStep('rotate')} disabled={isActive(rotJob)}>
                  Vygenerovat natočený pohled · {priceLabel(est)}{est?.eta_s ? ` · ${fmtTime(est.eta_s)}` : ''}
                </button>
              </div>
            </div>
            <Candidates job={rotJob} pick={wf.pick} onOpen={onOpen}
              onPick={(ref) => save({ pick: ref }).then(() => setStep(4))} pickLabel="Vybrat →" />
          </div>
        )}

        {step === 4 && wf.pick && (
          <div className="card">
            <img className="final" src={imageUrl(wf.pick)} alt="" onClick={() => onOpen(imageUrl(wf.pick!))} />
            <p>Obrázek je v knihovně i ve stromu verzí (bokorys → opravy → natočený pohled). Popisky, fakta a schéma doplníte v editoru infografiky; text v obrázku nikdy nekreslí model.</p>
            <div className="row">
              <button className="btn go" onClick={() => onInfographic(wf.pick!, wf.object.split(/[:—–]/)[0].trim())}>Otevřít v editoru infografiky</button>
              <button className="btn" onClick={() => onOpenInStudio(wf.pick!)}>Otevřít ve studiu</button>
              <a className="btn" href={imageUrl(wf.pick)} download={`grafik-${wf.pick.replace('/', '-')}.png`}>Stáhnout PNG</a>
            </div>
          </div>
        )}
      </section>

      <aside className="card guide-side">
        <h3>Objekt</h3>
        <p>{wf.object || <span className="hint">zatím bez popisu</span>}</p>
        <h3>Předlohy</h3>
        {refs.map((r) => <div key={r.ref_id} className="side-ref"><img src={r.preview} alt="" /><span>{r.name.slice(0, 40)}<small>{ROLE_LABEL[r.role]}{r.meta ? ` · ${r.meta}` : ''}</small></span></div>)}
        {wf.side_pick && <><h3>Bokorys</h3><img className="side-img" src={imageUrl(base!, 512)} alt="" onClick={() => onOpen(imageUrl(base!))} /></>}
        {wf.pick && <><h3>Natočený pohled</h3><img className="side-img" src={imageUrl(wf.pick, 512)} alt="" onClick={() => onOpen(imageUrl(wf.pick!))} /></>}
        <p className="hint">Každý krok je verze ve stromu historie; stejný průvodce mohou volat i jiné projekty přes Engine.</p>
      </aside>
      {picker && <RefPicker initialTab={picker} onError={onError} onClose={() => setPicker(null)}
        onPick={(m: RefMeta) => setRefs((r) => (r.some((x) => x.ref_id === m.id) ? r : [...r, refFromMeta(m, r.length ? 'subject' : 'geometry')]))} />}
    </main>
  )
}

const isActive = (j: Job | null) => !!j && (j.status === 'queued' || j.status === 'running')

function Candidates({ job, pick, onPick, onOpen, pickLabel }: {
  job: Job | null; pick: string | null; onPick: (ref: string) => void; onOpen: (src: string) => void; pickLabel: string
}) {
  const [now, setNow] = useState(Date.now() / 1000)
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now() / 1000), 1000)
    return () => clearInterval(t)
  }, [])
  if (!job) return null
  if (job.status === 'failed') return <p className="warn">Selhalo: {job.error}</p>
  if (isActive(job)) {
    return <p className="hint">{job.status === 'running' ? `Generuje se… ${Math.round(now - (job.started ?? now))} s` : 'Čeká ve frontě…'} ({job.request.n} variant)</p>
  }
  return (
    <div className="cands">
      {job.images.map((_, i) => {
        const ref = `${job.job_id}/${i}`
        return (
          <div key={ref} className={`cand ${ref === pick ? 'sel' : ''}`}>
            <img src={imageUrl(ref, 768)} alt="" onClick={() => onOpen(imageUrl(ref))} title="Zvětšit" />
            <div className="act">
              <button className={`btn small ${ref === pick ? 'go' : ''}`} onClick={() => onPick(ref)}>{ref === pick ? '✓ Vybráno' : pickLabel}</button>
              <button className="btn small" onClick={() => onOpen(imageUrl(ref))}>⤢</button>
            </div>
          </div>
        )
      })}
    </div>
  )
}
