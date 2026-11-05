import { useCallback, useEffect, useState } from 'react'
import {
  chainApi, infoApi, PaymentRequired, researchApi, variantsApi,
  type Chain, type Fact, type Infographic, type Proposal, type SeriesPage,
} from './api.ts'
import { fmtUsd } from './App.tsx'
import { FactRow, ResearchBody, ROLES, type ResearchProps, type RoleKey } from './Podklady.tsx'

// Řetězec infografika z tématu (engine/chain.py): podklady a návrhy běží samy, operátor vybírá. Cena se schválila jednou na začátku.
type View = 'podklady' | 'navrhy' | 'vyber' | 'stranky'
const RUNNING: Chain['stage'][] = ['zadani', 'podklady', 'web', 'navrhy', 'kontrola', 'stranky']
const PAGES_WORD = (n: number) => (n === 1 ? 'stránka' : n >= 2 && n <= 4 ? 'stránky' : 'stránek')
const SEVERITY_TAG: Record<string, string> = { vysoká: 'bad', střední: '', nízká: 'ok' }

const viewOf = (wf: Chain): View => {
  const stage = wf.stage === 'stop' ? wf.resume_stage : wf.stage
  if (stage === 'zadani' || stage === 'podklady' || stage === 'web') return 'podklady'
  if (stage === 'stranky' || wf.serie.length) return 'stranky'
  return stage === 'navrhy' || stage === 'vyber' ? 'navrhy' : 'vyber'
}

const sketchOf = (wf: Chain, proposal: Proposal, page: number) => `/api/v2/workflows/${wf.id}/navrhy/navrh-${proposal.id}${page > 1 ? `-${page}` : ''}.svg`

function ProposalCard({ wf, proposal, onOpen, onPick, onLook }: {
  wf: Chain; proposal: Proposal; onOpen: (src: string) => void; onPick: (pages: number[]) => void; onLook: () => void
}) {
  const pages = [proposal, ...(proposal.dalsi_stranky ?? [])]
  const [chosen, setChosen] = useState<number[]>(pages.map((_, i) => i + 1))
  const toggle = (n: number) => setChosen((now) => (now.includes(n) ? now.filter((x) => x !== n) : [...now, n].sort((a, b) => a - b)))
  return (
    <section className="card proposal">
      <div className={`page-thumbs ${pages.length > 1 ? 'many' : ''}`}>
        {pages.map((page, i) => (
          <div className="page-thumb" key={page.nazev}>
            <button className="zoomable" onClick={() => onOpen(sketchOf(wf, proposal, i + 1))} title={`Zvětšit náčrt: ${page.nazev}`}><img src={sketchOf(wf, proposal, i + 1)} alt={`Náčrt: ${page.nazev}`} /></button>
            {pages.length > 1 && (
              <label className="page-pick"><input type="checkbox" checked={chosen.includes(i + 1)} onChange={() => toggle(i + 1)} /> {i + 1}. {page.nazev}</label>
            )}
          </div>
        ))}
      </div>
      <h3>{proposal.nazev}</h3>
      <p>{proposal.veta}</p>
      <p className="hint">Formát {proposal.format} · {pages.length} {PAGES_WORD(pages.length)} · faktů ze zdrojů: {proposal.fakta}</p>
      <details>
        <summary>Panely podle důležitosti</summary>
        {pages.map((page, i) => (
          <div key={page.nazev}>
            {pages.length > 1 && <b>{i + 1}. {page.nazev}</b>}
            <ol className="citations">{page.panely.map((p) => (
              <li key={`${p.poradi}-${p.titulek}`}><b>{p.titulek}</b> {p.co}{p.predloha && <span className="hint"> Předloha: {ROLES[p.predloha as RoleKey] ?? p.predloha}</span>}</li>
            ))}</ol>
          </div>
        ))}
      </details>
      {proposal.rozpory.length > 0 && (
        <p className="warn">Používá fakta, ve kterých si zdroje odporují: {proposal.rozpory.join('; ')}.</p>
      )}
      {proposal.neznama_fakta > 0 && <p className="hint">Odkazy na fakta, která v dossieru nejsou, vypadly: {proposal.neznama_fakta}.</p>}
      {(proposal.neznama_predloha ?? 0) > 0 && <p className="hint">Předlohy, které dossier nemá, vypadly: {proposal.neznama_predloha}.</p>}
      {(proposal.opakovana_fakta ?? 0) > 0 && <p className="hint">Stejná fakta na víc stránkách vypadla: {proposal.opakovana_fakta}.</p>}
      {(proposal.bez_stranky?.length ?? 0) > 0 && <p className="hint">Vlastní obrazy bez stránky v téhle sérii: {proposal.bez_stranky?.join("; ")}.</p>}
      <div className="row tight">
        <button className="btn go" disabled={!chosen.length} onClick={() => onPick(chosen)}>Vybrat tento · {chosen.length} {PAGES_WORD(chosen.length)}</button>
        {!chosen.length && <span className="hint">Vyberte aspoň jednu stránku.</span>}
        {proposal.vzhled && <button className="btn" onClick={onLook} title={proposal.vzhled}>Ukázka vzhledu · 0 USD</button>}
      </div>
    </section>
  )
}

function Picked({ wf, proposal, onOpen, onError, onPages }: { wf: Chain; proposal: Proposal; onOpen: (src: string) => void; onError: (msg: string) => void; onPages: () => void }) {
  const [facts, setFacts] = useState<Fact[]>([])
  useEffect(() => {
    if (wf.research_id) researchApi.get(wf.research_id).then((r) => setFacts(r.dossier?.facts ?? [])).catch((e) => onError(e.message))
  }, [wf.research_id, onError])
  const src = sketchOf(wf, proposal, wf.stranky[0] ?? 1)
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
        <p className="hint">Kontrola nic neblokuje.</p>
        {wf.stage === 'hotovo' && !wf.serie.length && <ComposeButton wf={wf} onPages={onPages} />}
        <h4>Fakta podle panelů</h4>
        {[proposal, ...(proposal.dalsi_stranky ?? [])].filter((_, i) => wf.stranky.includes(i + 1)).flatMap((page) => page.panely).map((p) => (
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

function ComposeButton({ wf, onPages }: { wf: Chain; onPages: () => void }) {
  return (
    <div className="row tight">
      <button className="btn go" onClick={onPages}>Složit stránky · {fmtUsd(wf.stranky_usd)}</button>
      <span className="hint">{wf.stranky.length} {PAGES_WORD(wf.stranky.length)}, cena je v rámci schválené ceny řetězce.</span>
    </div>
  )
}

/** Stránka tak, jak ji uvidí čtenář na telefonu: široká 360 px, vedle ní nálezy kontroly a hlášení skladby. */
function SeriesPageCard({ page, onError, onInfographicDoc }: { page: SeriesPage; onError: (msg: string) => void; onInfographicDoc: (id: string) => void }) {
  const [svg, setSvg] = useState('')
  const [doc, setDoc] = useState<Infographic | null>(null)
  const [checks, setChecks] = useState<{ ok: boolean; text: string }[]>([])
  const [busy, setBusy] = useState(false)
  const [png, setPng] = useState<string | null>(null)
  useEffect(() => {
    if (!page.doc) return
    fetch(`/api/v2/infographics/${page.doc}/svg`).then((r) => r.text()).then(setSvg).catch((e) => onError(e.message))
    infoApi.get(page.doc).then(setDoc).catch((e) => onError(e.message))
    infoApi.checks(page.doc).then(setChecks).catch((e) => onError(e.message))
  }, [page.doc, onError])
  if (!page.doc) {
    return (
      <section className="card">
        <h3>{page.stranka}. {page.nazev}</h3>
        <p className="warn">Stránka nevznikla.</p>
        {page.hlaseni.map((note) => <p className="hint" key={note}>{note}</p>)}
      </section>
    )
  }
  const docId = page.doc
  const exportPng = async () => {
    setBusy(true)
    try { setPng((await infoApi.export(docId, '', 'png')).url) } catch (e) { onError((e as Error).message) } finally { setBusy(false) }
  }
  const findings = checks.filter((c) => !c.ok)
  return (
    <section className="card series-page">
      <div className="series-phone" dangerouslySetInnerHTML={{ __html: svg }} />
      <div className="series-side">
        <h3>{page.stranka}. {page.nazev}</h3>
        <p className="hint">{doc?.size.replace('x', '×')} · náhled široký 360 px jako telefon</p>
        {page.hlaseni.length > 0 && (
          <>
            <h4>Hlášení skladby</h4>
            <ul className="panel-checks">{page.hlaseni.map((note) => <li key={note} className="warn">! {note}</li>)}</ul>
          </>
        )}
        <h4>Kontrola</h4>
        <ul className="panel-checks">
          {findings.map((c) => <li key={c.text} className="warn">! {c.text}</li>)}
          {checks.length > 0 && !findings.length && <li className="ok">✓ bez nálezu</li>}
        </ul>
        <details>
          <summary>Všechny kontroly</summary>
          <ul className="panel-checks">{checks.filter((c) => c.ok).map((c) => <li key={c.text} className="ok">✓ {c.text}</li>)}</ul>
        </details>
        <div className="row tight">
          <button className="btn" onClick={() => onInfographicDoc(docId)}>Otevřít ve velkém</button>
          <button className="btn" disabled={busy} onClick={exportPng}>{busy ? 'Exportuji…' : 'Export PNG'}</button>
          {png && <a href={png} target="_blank" rel="noreferrer">Otevřít PNG</a>}
        </div>
        {doc && (
          <details>
            <summary>Zdroje pod článek</summary>
            <p>{doc.sources}</p>
            <p className="hint">{doc.ai_note}</p>
          </details>
        )}
      </div>
    </section>
  )
}

export default function ChainView({ id, onBack, ...props }: ResearchProps & { id: string; onBack: () => void }) {
  const { onOpen, setConfirm, onError, onInfographicDoc } = props
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

  const pick = async (n: number, pages: number[]) => {
    try { setWf(await chainApi.pick(id, n, pages)) } catch (e) { onError((e as Error).message) }
  }
  const compose = async () => {
    try { setWf(await chainApi.pages(id)) } catch (e) { onError((e as Error).message) }
  }
  const resume = async (confirm = false, bezWebu = false) => {
    try {
      setWf(await chainApi.resume(id, confirm, bezWebu))
    } catch (e) {
      if (e instanceof PaymentRequired) setConfirm({ title: `Pokračovat: ${wf?.object}`, items: e.items, total: e.estimate, onOk: () => resume(true, bezWebu) })
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
  const reached: Record<View, boolean> = { podklady: !!wf.research_id, navrhy: wf.navrhy.length > 0 || current === 'navrhy', vyber: wf.vyber !== null, stranky: wf.stage === 'stranky' || wf.stage === 'hotovo' || wf.serie.length > 0 }
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
        {step('vyber', 4, 'Výběr', wf.stage === 'hotovo' || wf.stage === 'stranky')}
        {step('stranky', 5, 'Stránky', wf.serie.length > 0)}
      </div>
      <p className="hint">Řetězec: schváleno {fmtUsd(wf.budget_usd)}, utraceno {fmtUsd(wf.spent_usd)}{running ? ' · běží, není potřeba klikat' : ''}</p>

      {wf.stage === 'stop' && (
        <section className="card conflicts">
          <h3>Řetězec stojí</h3>
          <p>{wf.stop_reason}</p>
          {wf.resume_stage === 'web' ? (
            <div className="row">
              <button className="btn pay" onClick={() => resume(false)}>Hledat na webu · {fmtUsd(wf.resume_usd)}</button>
              <button className="btn" onClick={() => resume(false, true)}>Pokračovat jen s Wikipedií</button>
            </div>
          ) : <button className={`btn ${wf.resume_usd ? 'pay' : 'go'}`} onClick={() => resume(false)}>Pokračovat · {fmtUsd(wf.resume_usd)}</button>}
        </section>
      )}

      {wf.zadani && current === 'podklady' && (
        <section className="card">
          <h3>Zadání</h3>
          <p>Hledám heslo <b>{wf.zadani.predmet}</b>{wf.zadani.predmet !== wf.object ? <> · otázka stránky: {wf.object}</> : null}</p>
          {wf.zadani.otazky.length > 0 && <><b>Co musí podklady zodpovědět</b><ul className="citations">{wf.zadani.otazky.map((q) => <li key={q}>{q}</li>)}</ul></>}
          {wf.zadani.vzor && (
            <>
              <p><b>Vzor:</b> {wf.zadani.vzor.o_cem} {wf.zadani.vzor.skladba}</p>
              {wf.zadani.vzor.tvrzeni.length > 0 && <><b>Tvrzení vzoru k ověření</b><ul className="citations">{wf.zadani.vzor.tvrzeni.map((t) => <li key={t}>{t}</li>)}</ul></>}
            </>
          )}
        </section>
      )}

      {current === 'podklady' && (wf.research_id
        ? <ResearchBody id={wf.research_id} {...props} />
        : <section className="card"><p><b>{wf.stage === 'zadani' ? 'Čtu zadání a vzor…' : 'Dohledávám podklady…'}</b></p></section>)}

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
            {wf.navrhy.map((p) => <ProposalCard key={p.id} wf={wf} proposal={p} onOpen={onOpen} onPick={(pages) => pick(p.id, pages)} onLook={() => look(p)} />)}
          </div>
        </>
      )}

      {current === 'vyber' && proposal && <Picked wf={wf} proposal={proposal} onOpen={onOpen} onError={onError} onPages={compose} />}

      {current === 'stranky' && (
        <>
          {wf.stage === 'stranky' && (
            <section className="card">
              <p><b>Píšu texty a skládám stránky…</b></p>
              <p className="hint">{wf.model} přepíše fakta do krátkých popisků, rozvržení počítá kód. Obvykle do minuty.</p>
            </section>
          )}
          {wf.stage === 'hotovo' && !wf.serie.length && <section className="card"><ComposeButton wf={wf} onPages={compose} /></section>}
          {wf.serie.map((page) => <SeriesPageCard key={page.stranka} page={page} onError={onError} onInfographicDoc={onInfographicDoc} />)}
        </>
      )}
    </main>
  )
}
