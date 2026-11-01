import { useCallback, useEffect, useState } from 'react'
import {
  chainApi, PaymentRequired, researchApi, variantsApi,
  type Chain, type Fact, type Proposal,
} from './api.ts'
import { fmtUsd } from './App.tsx'
import { FactRow, ResearchBody, type ResearchProps } from './Podklady.tsx'

// Řetězec infografika z tématu (engine/chain.py): podklady a návrhy běží samy, operátor vybírá. Cena se schválila jednou na začátku.
type View = 'podklady' | 'navrhy' | 'vyber'
const RUNNING: Chain['stage'][] = ['podklady', 'navrhy', 'kontrola']
const SEVERITY_TAG: Record<string, string> = { vysoká: 'bad', střední: '', nízká: 'ok' }

const viewOf = (wf: Chain): View => {
  const stage = wf.stage === 'stop' ? wf.resume_stage : wf.stage
  if (stage === 'podklady') return 'podklady'
  return stage === 'navrhy' || stage === 'vyber' ? 'navrhy' : 'vyber'
}

function ProposalCard({ wf, proposal, onOpen, onPick, onLook }: {
  wf: Chain; proposal: Proposal; onOpen: (src: string) => void; onPick: () => void; onLook: () => void
}) {
  const src = `/api/v2/workflows/${wf.id}/navrhy/navrh-${proposal.id}.svg`
  return (
    <section className="card proposal">
      <button className="zoomable" onClick={() => onOpen(src)} title={`Zvětšit náčrt: ${proposal.nazev}`}><img src={src} alt={`Náčrt: ${proposal.nazev}`} /></button>
      <h3>{proposal.nazev}</h3>
      <p>{proposal.veta}</p>
      <p className="hint">Formát {proposal.format} · panelů: {proposal.panely.length} · faktů ze zdrojů: {proposal.fakta}</p>
      <details>
        <summary>Panely podle důležitosti</summary>
        <ol className="citations">{proposal.panely.map((p) => <li key={`${p.poradi}-${p.titulek}`}><b>{p.titulek}</b> {p.co}</li>)}</ol>
      </details>
      {proposal.rozpory.length > 0 && (
        <p className="warn">Používá fakta, ve kterých si zdroje odporují: {proposal.rozpory.join('; ')}.</p>
      )}
      {proposal.neznama_fakta > 0 && <p className="hint">Odkazy na fakta, která v dossieru nejsou, vypadly: {proposal.neznama_fakta}.</p>}
      <div className="row tight">
        <button className="btn go" onClick={onPick}>Vybrat tento</button>
        {proposal.vzhled && <button className="btn" onClick={onLook} title={proposal.vzhled}>Ukázka vzhledu · 0 USD</button>}
      </div>
    </section>
  )
}

function Picked({ wf, proposal, onOpen, onError }: { wf: Chain; proposal: Proposal; onOpen: (src: string) => void; onError: (msg: string) => void }) {
  const [facts, setFacts] = useState<Fact[]>([])
  useEffect(() => {
    if (wf.research_id) researchApi.get(wf.research_id).then((r) => setFacts(r.dossier?.facts ?? [])).catch((e) => onError(e.message))
  }, [wf.research_id, onError])
  const src = `/api/v2/workflows/${wf.id}/navrhy/navrh-${proposal.id}.svg`
  const check = wf.kontrola
  return (
    <section className="card picked">
      <button className="zoomable" onClick={() => onOpen(src)} title="Zvětšit náčrt"><img src={src} alt={`Náčrt: ${proposal.nazev}`} /></button>
      <div>
        <h3 className="dossier-title">Vybráno: {proposal.nazev}</h3>
        <p>{proposal.veta}</p>
        <h4>Poradní kontrola logiky</h4>
        {wf.stage === 'kontrola' && <p className="hint">Kontroluji návrh…</p>}
        {check?.chyba && <p className="hint">Kontrola se nepovedla, řetězec to nezastavuje: {check.chyba}</p>}
        {check?.summary && <p>{check.summary}</p>}
        {check?.warnings?.map((w) => (
          <div className="fact" key={w.what}>
            <span className={`tag ${SEVERITY_TAG[w.severity] ?? ''}`}>{w.severity}</span>
            <span className="grow">{w.what}{w.fix && <span className="hint"> Oprava: {w.fix}</span>}</span>
          </div>
        ))}
        {check && !check.chyba && !check.warnings?.length && <p className="hint">Bez upozornění.</p>}
        <p className="hint">Kontrola nic neblokuje. Další kroky (model, render, stránka) se teprve staví, tady řetězec zatím končí.</p>
        <h4>Fakta podle panelů</h4>
        {proposal.panely.map((p) => (
          <div key={`${p.poradi}-${p.titulek}`} className="panel-facts">
            <b>{p.poradi}. {p.titulek}</b>
            {p.fakta.length === 0 && <span className="hint"> bez faktu ze zdroje</span>}
            {facts.filter((f) => p.fakta.includes(f.id)).map((f) => <FactRow key={f.id} fact={f} />)}
          </div>
        ))}
      </div>
    </section>
  )
}

export default function ChainView({ id, onBack, ...props }: ResearchProps & { id: string; onBack: () => void }) {
  const { onOpen, setConfirm, onError } = props
  const [wf, setWf] = useState<Chain | null>(null)
  const [view, setView] = useState<View | null>(null)
  const load = useCallback(() => chainApi.get(id).then(setWf).catch((e) => onError(e.message)), [id, onError])
  const running = !wf || RUNNING.includes(wf.stage)
  useEffect(() => { load() }, [load])
  useEffect(() => {
    if (!running) return
    const t = setInterval(load, 2000)
    return () => clearInterval(t)
  }, [running, load])
  useEffect(() => { setView(null) }, [wf?.stage])

  const pick = async (n: number) => {
    try { setWf(await chainApi.pick(id, n)) } catch (e) { onError((e as Error).message) }
  }
  const resume = async (confirm = false) => {
    try {
      setWf(await chainApi.resume(id, confirm))
    } catch (e) {
      if (e instanceof PaymentRequired) setConfirm({ title: `Pokračovat: ${wf?.object}`, items: e.items, total: e.estimate, onOk: () => resume(true) })
      else onError((e as Error).message)
    }
  }
  const look = async (proposal: Proposal) => {
    try {
      const batch = await variantsApi.create({ request: { prompt: proposal.vzhled, backend: 'flux-local', n: 1, caller: 'studio:infografika' }, count: 4, styles: [null], title: `Vzhled: ${proposal.nazev}` })
      window.open(batch.page, '_blank', 'noreferrer')
    } catch (e) { onError((e as Error).message) }
  }

  const header = (
    <div className="row">
      <button className="btn small" onClick={onBack}>← Průvodce</button>
      <b className="guide-title">Infografika z tématu{wf ? `: ${wf.object}` : ''}</b>
    </div>
  )
  if (!wf) return <main className="guide-start podklady">{header}</main>

  const current = view ?? viewOf(wf)
  const reached: Record<View, boolean> = { podklady: !!wf.research_id, navrhy: wf.navrhy.length > 0 || current === 'navrhy', vyber: wf.vyber !== null }
  const proposal = wf.navrhy.find((p) => p.id === wf.vyber)
  const step = (key: View, n: number, label: string, done: boolean) => (
    <button className={`step ${key === current ? 'cur' : done ? 'done' : ''}`} disabled={!reached[key]} onClick={() => setView(key)}>
      <span className="n">{done && key !== current ? '✓' : n}</span>{label}
    </button>
  )
  return (
    <main className="guide-start podklady">
      {header}
      <div className="steps">
        <button className="step done" onClick={onBack}><span className="n">✓</span>Zadání</button>
        {step('podklady', 2, 'Podklady', wf.navrhy.length > 0 || wf.stage === 'navrhy')}
        {step('navrhy', 3, 'Návrhy skladby', wf.vyber !== null)}
        {step('vyber', 4, 'Výběr', wf.stage === 'hotovo')}
      </div>
      <p className="hint">Řetězec: schváleno {fmtUsd(wf.budget_usd)}, utraceno {fmtUsd(wf.spent_usd)}{running ? ' · běží, není potřeba klikat' : ''}</p>

      {wf.stage === 'stop' && (
        <section className="card conflicts">
          <h3>Řetězec stojí</h3>
          <p>{wf.stop_reason}</p>
          <button className={`btn ${wf.resume_usd ? 'pay' : 'go'}`} onClick={() => resume(false)}>Pokračovat · {fmtUsd(wf.resume_usd)}</button>
        </section>
      )}

      {current === 'podklady' && (wf.research_id
        ? <ResearchBody id={wf.research_id} {...props} />
        : <section className="card"><p><b>Dohledávám podklady…</b></p></section>)}

      {current === 'navrhy' && (
        <>
          {wf.stage === 'navrhy' && (
            <section className="card">
              <p><b>Skládám návrhy…</b></p>
              <p className="hint">{wf.model} čte dossier a navrhuje tři skladby. Obvykle do minuty. Náčrty kreslí kód za 0 USD.</p>
            </section>
          )}
          {wf.rozbor && (
            <section className="card">
              <h3>Rozbor vzoru</h3>
              <div className="rozbor">
                <div><b>Držet</b><ul className="citations">{wf.rozbor.drzet?.map((t) => <li key={t}>{t}</li>)}</ul></div>
                <div><b>Změnit</b><ul className="citations">{wf.rozbor.zmenit?.map((t) => <li key={t}>{t}</li>)}</ul></div>
              </div>
            </section>
          )}
          <div className="proposals">
            {wf.navrhy.map((p) => <ProposalCard key={p.id} wf={wf} proposal={p} onOpen={onOpen} onPick={() => pick(p.id)} onLook={() => look(p)} />)}
          </div>
        </>
      )}

      {current === 'vyber' && proposal && <Picked wf={wf} proposal={proposal} onOpen={onOpen} onError={onError} />}
    </main>
  )
}
