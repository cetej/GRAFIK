import { useCallback, useEffect, useState } from 'react'
import {
  chainApi, fileToB64, infoApi, PaymentRequired, refsApi, researchApi,
  type Chain, type Dossier, type DossierImage, type Fact, type FactSource, type Pin, type RefMeta, type ResearchRow, type ResearchState, type Workflow,
} from './api.ts'
import { fmtUsd, type Confirm } from './App.tsx'

// Infografika z tématu, krok Podklady (engine/research.py). Rozpory nahoře, nic se nerozhoduje potichu; placené hledání je jen tlačítko s cenou.
const THEMES = { rozmery: 'Rozměry', vznik: 'Vznik', stavba: 'Stavba a materiál', rekord: 'Rekordy', ostatni: 'Ostatní' } as const
const ROLES = { rekonstrukce: 'Rekonstrukce a modely', pudorys: 'Půdorys', rez: 'Řez', pruceli: 'Průčelí', interier: 'Interiér', detail: 'Detail', material: 'Materiál', nezarazeno: 'Nezařazeno' } as const
const STATE_LABEL = { shoda: 'shoda', rozpor: 'rozpor', jediny_zdroj: 'jeden zdroj' } as const

const num = (v: number) => v.toLocaleString('cs-CZ', { maximumFractionDigits: 2 })
const fmtValue = (v: FactSource['hodnota'], unit: string | null) => {
  if (v === undefined || v === null) return ''
  return `${Array.isArray(v) ? `${num(v[0])}–${num(v[1])}` : num(v)}${unit ? ` ${unit}` : ''}`
}

const STAGE_LABEL: Record<Chain['stage'], string> = { podklady: 'dohledává podklady', navrhy: 'skládá návrhy', vyber: 'čeká na výběr návrhu', kontrola: 'kontroluje návrh', hotovo: 'návrh vybrán', stop: 'stojí, čeká na vás' }

export function TopicStart({ chains, onOpen, onChain, setConfirm, onError }: {
  chains: (Workflow | Chain)[]; onOpen: (id: string) => void; onChain: (id: string) => void; setConfirm: (c: Confirm) => void; onError: (msg: string) => void
}) {
  const [topic, setTopic] = useState('')
  const [busy, setBusy] = useState(false)
  const [list, setList] = useState<ResearchRow[]>([])
  const [price, setPrice] = useState<number | null>(null)
  const [vzor, setVzor] = useState<RefMeta | null>(null)
  useEffect(() => { researchApi.list().then(setList).catch((e) => onError(e.message)) }, [onError])
  useEffect(() => { chainApi.estimate().then((e) => setPrice(e.total_usd)).catch(() => setPrice(null)) }, [])
  const running = chains.filter((w): w is Chain => w.kind === 'infografika')
  const startChain = async (confirm = false) => {
    try {
      onChain((await chainApi.start({ topic: topic.trim(), vzor: vzor?.id ?? null, confirm_cost: confirm })).id)
    } catch (e) {
      if (e instanceof PaymentRequired) setConfirm({ title: `Podklady a návrhy: ${topic.trim()}`, items: e.items, total: e.estimate, onOk: () => startChain(true) })
      else onError((e as Error).message)
    }
  }
  const addVzor = async (file: File) => {
    try { setVzor(await refsApi.addB64(await fileToB64(file), file.name)) } catch (e) { onError((e as Error).message) }
  }
  const start = async () => {
    setBusy(true)
    try { onOpen((await researchApi.start(topic.trim())).id) } catch (e) { onError((e as Error).message) } finally { setBusy(false) }
  }
  return (
    <section className="card">
      <h2>Infografika z tématu</h2>
      <p>GRAFIK sám dohledá fakta se zdroji a obrazové podklady z Wikidaty, Wikipedie a Wikimedia Commons. Zdroje, které si odporují, ukáže nahoře.</p>
      <div className="row">
        <input className="search" value={topic} onChange={(e) => setTopic(e.target.value)} aria-label="Téma"
          placeholder="Např. Pantheon, Řím" onKeyDown={(e) => { if (e.key === 'Enter' && topic.trim()) start() }} />
        <button className="btn pay" disabled={!topic.trim() || price === null} onClick={() => startChain(false)} title="Podklady, tři návrhy skladby a kontrola vybraného návrhu. Cena se schvaluje jednou, zastaví se až u výběru.">
          Podklady a návrhy{price !== null ? ` · ${fmtUsd(price)}` : ''}
        </button>
        <button className="btn" disabled={!topic.trim() || busy} onClick={start}>{busy ? 'Spouštím…' : 'Jen podklady · 0 USD'}</button>
      </div>
      <div className="row">
        {vzor ? (
          <>
            <img className="vzor-thumb" src={`/api/v2/refs/${vzor.id}/image?w=128`} alt={vzor.title} />
            <span className="hint">Vzor: {vzor.title}. GRAFIK drží jeho žánr a bohatost, skladbu navrhne vlastní.</span>
            <button className="btn small" onClick={() => setVzor(null)}>Odebrat vzor</button>
          </>
        ) : (
          <>
            <label className="btn small">Vložit vzor…<input type="file" accept="image/*" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) addVzor(f); e.target.value = '' }} /></label>
            <span className="hint">Nepovinné, téma napište i ke vzoru. Vzor jde jen do návrhů, do podkladů ne.</span>
          </>
        )}
      </div>
      {running.length > 0 && <h3>Řetězce</h3>}
      <div className="wf-list">
        {running.map((w) => (
          <button key={w.id} className="wf-item" onClick={() => onChain(w.id)}>
            <span><b>{w.object}</b> · {STAGE_LABEL[w.stage]}<small>utraceno {fmtUsd(w.spent_usd)} z {fmtUsd(w.budget_usd)} · {w.updated.replace('T', ' ')}</small></span>
          </button>
        ))}
      </div>
      {list.length > 0 && <h3>Hotové podklady</h3>}
      <div className="wf-list">
        {list.map((r) => (
          <button key={r.id} className="wf-item" onClick={() => onOpen(r.id)}>
            <span><b>{r.entita ?? r.tema}</b> · verze {r.verze}
              <small>{r.status === 'done' ? `${r.facts} faktů · ${r.rozpory} rozporů · ${r.images} obrázků${r.cost_usd ? ` · ${fmtUsd(r.cost_usd)}` : ''}` : r.status === 'failed' ? 'selhalo' : 'běží'}</small></span>
          </button>
        ))}
      </div>
    </section>
  )
}

function Citations({ fact }: { fact: Fact }) {
  return (
    <ul className="citations">
      {fact.zdroje.map((z, i) => (
        <li key={`${z.url}-${i}`}>
          <a href={z.url} target="_blank" rel="noreferrer">{z.nazev}</a>{z.hodnota !== undefined && <> · {fmtValue(z.hodnota, fact.jednotka)}</>} <span className="hint">{z.datum}</span>
          {z.jazyk !== 'wikidata' && <q>{z.citace}</q>}
        </li>
      ))}
    </ul>
  )
}

function SourceLinks({ fact }: { fact: Fact }) {
  // one link per source; a number shows its own value, so a conflict can be read straight away
  return (
    <span className="src-links">
      {fact.zdroje.map((z, i) => (
        <a key={`${z.url}-${i}`} href={z.url} target="_blank" rel="noreferrer" title={z.citace}>
          {z.jazyk}{z.hodnota !== undefined ? ` ${fmtValue(z.hodnota, fact.jednotka)}` : ''}
        </a>
      ))}
    </span>
  )
}

export function FactRow({ fact }: { fact: Fact }) {
  const hasCitation = fact.hodnota !== null
  return (
    <div className="fact">
      <span className="grow">{fact.tvrzeni}</span>
      <span className={`tag ${fact.stav === 'shoda' ? 'ok' : ''}`}>{STATE_LABEL[fact.stav]}</span>
      <SourceLinks fact={fact} />
      {hasCitation && <details><summary>citace</summary><Citations fact={fact} /></details>}
    </div>
  )
}

function ImageCard({ img, title, onOpen, onUseRef, onInfographicDoc, onError }: {
  img: DossierImage; title: string; onOpen: (src: string) => void; onUseRef: (m: RefMeta) => void; onInfographicDoc: (id: string) => void; onError: (msg: string) => void
}) {
  const [busy, setBusy] = useState(false)
  if (!img.ref_id) return <figure className="doc-img"><div className="ph">Nestáhlo se</div><figcaption title={img.chyba}>{img.nazev}</figcaption></figure>
  const src = `/api/v2/refs/${img.ref_id}/image`
  const meta: RefMeta = {
    id: img.ref_id, origin: 'commons', title: img.nazev, source_url: img.url, page_url: img.stranka, author: img.autor, license: img.licence,
    width: img.sirka ?? 0, height: img.vyska ?? 0, added: '', seen: true, image: src,
  }
  return (
    <figure className="doc-img">
      <button className="zoomable" onClick={() => onOpen(src)} title={`Zvětšit: ${img.nazev}`}><img src={`${src}?w=384`} alt={img.nazev} loading="lazy" /></button>
      <figcaption>
        <a href={img.stranka ?? undefined} target="_blank" rel="noreferrer" title={img.nazev}>{img.autor || 'autor neuveden'}</a> · {img.licence || 'licence neuvedena'}
      </figcaption>
      <div className="row tight">
        <button className="btn small" onClick={() => onUseRef(meta)} title="Do předloh ve Studiu">→ Předloha</button>
        <button className="btn small" disabled={busy} title="Nová infografika s tímto obrázkem; autor a licence půjdou do patičky"
          onClick={async () => {
            setBusy(true)
            try { onInfographicDoc((await infoApi.fromRef(img.ref_id!, title)).id) } catch (e) { onError((e as Error).message) } finally { setBusy(false) }
          }}>→ Infografika</button>
      </div>
    </figure>
  )
}

function PinCard({ pin, onOpen, onUseRef }: { pin: Pin; onOpen: (src: string) => void; onUseRef: (m: RefMeta) => void }) {
  const src = `/api/v2/refs/${pin.ref_id}/image`
  const meta: RefMeta = {
    id: pin.ref_id, origin: 'pinterest', title: pin.nazev || pin.dotaz, source_url: null, page_url: pin.pin, author: null, license: pin.licence,
    width: pin.sirka, height: pin.vyska, added: '', seen: true, image: src,
  }
  return (
    <figure className="doc-img">
      <button className="zoomable" onClick={() => onOpen(src)} title={`Zvětšit: ${pin.nazev}`}><img src={`${src}?w=384`} alt={pin.nazev} loading="lazy" /></button>
      <figcaption><a href={pin.pin} target="_blank" rel="noreferrer" title={pin.nazev}>pin na Pinterestu</a> · jen předloha</figcaption>
      <div className="row tight"><button className="btn small" onClick={() => onUseRef(meta)} title="Do předloh ve Studiu">→ Předloha</button></div>
    </figure>
  )
}

function DossierView({ state, dossier, onOpenVersion, onOpen, setConfirm, onError, onUseRef, onInfographicDoc, onChain }: ResearchProps & { state: ResearchState; dossier: Dossier; onChain?: (id: string) => void }) {
  const facts = dossier.facts
  const conflicts = facts.filter((f) => f.stav === 'rozpor')
  const others = facts.filter((f) => f.stav !== 'rozpor')
  const themes = (Object.keys(THEMES) as (keyof typeof THEMES)[]).filter((t) => others.some((f) => f.tema === t))
  const [theme, setTheme] = useState<keyof typeof THEMES>(themes[0] ?? 'rozmery')
  const [askQid, setAskQid] = useState(false)
  const [qid, setQid] = useState(dossier.entita.qid)
  const [webUsd, setWebUsd] = useState<number | null>(null)
  const [nextUsd, setNextUsd] = useState<number | null>(null)
  useEffect(() => { researchApi.estimate(true).then((e) => setWebUsd(e.total_usd)).catch(() => setWebUsd(null)) }, [])
  useEffect(() => { chainApi.estimate(state.id).then((e) => setNextUsd(e.total_usd)).catch(() => setNextUsd(null)) }, [state.id])
  const toProposals = async (confirm = false) => {
    if (!onChain) return
    try {
      onChain((await chainApi.start({ research: state.id, confirm_cost: confirm })).id)
    } catch (e) {
      if (e instanceof PaymentRequired) setConfirm({ title: `Návrhy skladby: ${dossier.entita.label}`, items: e.items, total: e.estimate, onOk: () => toProposals(true) })
      else onError((e as Error).message)
    }
  }

  const askWeb = async () => {
    try {
      onOpenVersion((await researchApi.extend(state.id, false)).id)
    } catch (e) {
      if (e instanceof PaymentRequired) {
        setConfirm({ title: `Dohledat na webu: ${dossier.entita.label}`, items: e.items, total: e.estimate,
          onOk: async () => { try { onOpenVersion((await researchApi.extend(state.id, true)).id) } catch (e2) { onError((e2 as Error).message) } } })
      } else onError((e as Error).message)
    }
  }
  const otherEntity = async () => {
    try { onOpenVersion((await researchApi.start(dossier.tema, qid.trim())).id) } catch (e) { onError((e as Error).message) }
  }

  return (
    <>
      <section className="card">
        <div className="row between">
          <div>
            <h2 className="dossier-title">{dossier.entita.label}</h2>
            <span className="hint">{dossier.entita.popis} · <a href={dossier.entita.url} target="_blank" rel="noreferrer">Wikidata {dossier.entita.qid}</a> · verze {dossier.verze}{dossier.cost_usd ? ` · ${fmtUsd(dossier.cost_usd)}` : ' · 0 USD'}</span>
          </div>
          <div className="row tight">
            <button className="btn" onClick={() => setAskQid(!askQid)}>Jiná položka</button>
            {state.page && <a className="btn" href={state.page} target="_blank" rel="noreferrer">Přehled obrázků</a>}
            <button className="btn pay" onClick={askWeb} title="Sonnet s hledáním na webu, nejvýš 8 hledání; zeptá se na cenu">Dohledat na webu{webUsd !== null ? ` · ${fmtUsd(webUsd)}` : ''}</button>
          </div>
        </div>
        {askQid && (
          <div className="row">
            <input className="search" value={qid} onChange={(e) => setQid(e.target.value)} aria-label="Položka Wikidaty" placeholder="Q99309" />
            <button className="btn" disabled={!/^Q\d+$/.test(qid.trim())} onClick={otherEntity}>Hledat znovu · 0 USD</button>
            <span className="hint">Našla se jiná věc, než jste chtěli? Vložte číslo položky z Wikidaty. Vznikne nová verze.</span>
          </div>
        )}
      </section>

      {conflicts.length > 0 && (
        <section className="card conflicts">
          <h3>Rozpory mezi zdroji ({conflicts.length})</h3>
          <p className="hint">GRAFIK nevybírá. Rozhodněte, co na stránce bude, nebo uveďte rozpětí.</p>
          {conflicts.map((f) => (
            <div className="fact" key={f.id}>
              <b className="grow">{f.tvrzeni}</b>
              <SourceLinks fact={f} />
              <details><summary>citace</summary><Citations fact={f} /></details>
            </div>
          ))}
        </section>
      )}

      <section className="card">
        <div className="row">
          <h3 className="inline">Fakta ({others.length})</h3>
          {themes.length > 0 && (
            <div className="seg wrap">
              {themes.map((t) => <button key={t} className={t === theme ? 'on' : ''} onClick={() => setTheme(t)}>{THEMES[t]} {others.filter((f) => f.tema === t).length}</button>)}
            </div>
          )}
        </div>
        {others.filter((f) => f.tema === theme).map((f) => <FactRow key={f.id} fact={f} />)}
        {others.length === 0 && <p className="hint">Žádná fakta se nenašla.</p>}
        <p className="hint">Věta bez čísla je citace ze zdroje v jeho jazyce. Před zveřejněním texty čte člověk.</p>
      </section>

      <section className="card">
        <h3>Obrázky po rolích ({dossier.images.length})</h3>
        {(Object.keys(ROLES) as (keyof typeof ROLES)[]).map((role) => {
          const imgs = dossier.images.filter((i) => i.role === role)
          return (
            <div className="role-row" key={role}>
              <b>{ROLES[role]}</b>
              {imgs.length ? (
                <div className="role-imgs">
                  {imgs.map((img) => <ImageCard key={img.file} img={img} title={dossier.entita.label} onOpen={onOpen} onUseRef={onUseRef} onInfographicDoc={onInfographicDoc} onError={onError} />)}
                </div>
              ) : <span className="hint">Nic se nenašlo.</span>}
            </div>
          )
        })}
        <p className="hint">Obrázky jsou ve Schránce předloh s autorem a licencí. Role určil kód podle názvu souboru a kategorie, je to jen třídění.</p>
      </section>

      {state.inspirace.length > 0 && (
        <section className="card">
          <h3>Inspirace z Pinterestu ({state.inspirace.length})</h3>
          <p className="hint">Licence neznámá: slouží jako předloha a inspirace pro skladbu, do hotového obrázku nesmí. Mnoho z nich je generovaných, fakta z nich neber.</p>
          {[...new Set(state.inspirace.map((p) => p.dotaz))].map((dotaz) => (
            <div className="role-row" key={dotaz}>
              <b>{dotaz || 'Bez dotazu'}</b>
              <div className="role-imgs">
                {state.inspirace.filter((p) => p.dotaz === dotaz).map((pin) => <PinCard key={pin.pin} pin={pin} onOpen={onOpen} onUseRef={onUseRef} />)}
              </div>
            </div>
          ))}
        </section>
      )}

      {dossier.otazky_bez_odpovedi.length > 0 && (
        <section className="card">
          <h3>Bez odpovědi</h3>
          <ul className="citations">{dossier.otazky_bez_odpovedi.map((q) => <li key={q}>{q}</li>)}</ul>
        </section>
      )}
      {onChain && (
        <div className="row end">
          <button className="btn pay" disabled={nextUsd === null} onClick={() => toProposals(false)}>Pokračovat k návrhům{nextUsd !== null ? ` · ${fmtUsd(nextUsd)}` : ''} →</button>
        </div>
      )}
    </>
  )
}

export interface ResearchProps {
  onOpenVersion: (id: string) => void
  onOpen: (src: string) => void
  setConfirm: (c: Confirm) => void
  onError: (msg: string) => void
  onUseRef: (m: RefMeta) => void
  onInfographicDoc: (id: string) => void
}

/** Průběh a výsledek jedné rešerše; krok Podklady samostatně i v řetězci. */
export function ResearchBody({ id, onBack, onChain, ...props }: ResearchProps & { id: string; onBack?: () => void; onChain?: (id: string) => void }) {
  const [state, setState] = useState<ResearchState | null>(null)
  const load = useCallback(() => researchApi.get(id).then(setState).catch((e) => props.onError(e.message)), [id]) // eslint-disable-line react-hooks/exhaustive-deps
  const waiting = !state || state.status === 'queued' || state.status === 'running'
  useEffect(() => {
    load()
  }, [load])
  useEffect(() => {
    if (!waiting) return
    const t = setInterval(load, 2000)
    return () => clearInterval(t)
  }, [waiting, load])

  return (
    <>
      {waiting && (
        <section className="card">
          <p><b>Dohledávám podklady…</b></p>
          <p className="hint">Wikidata, Wikipedia a Wikimedia Commons, 0 USD. Běžně kolem minuty a půl, obrázky se stahují po jednom.</p>
        </section>
      )}
      {state?.status === 'failed' && !state.dossier && (
        <section className="card">
          <p className="warn">Rešerše selhala: {state.error ?? 'důvod Engine neuvedl'}</p>
          {onBack && <button className="btn" onClick={onBack}>Zpět na zadání</button>}
        </section>
      )}
      {state?.dossier && <DossierView key={state.id} state={state} dossier={state.dossier} onChain={onChain} {...props} />}
    </>
  )
}

export default function Podklady({ id, onBack, onChain, ...props }: ResearchProps & { id: string; onBack: () => void; onChain: (id: string) => void }) {
  return (
    <main className="guide-start podklady">
      <div className="row">
        <button className="btn small" onClick={onBack}>← Průvodce</button>
        <b className="guide-title">Infografika z tématu</b>
      </div>
      <div className="steps">
        <button className="step done" onClick={onBack}><span className="n">✓</span>Zadání</button>
        <button className="step cur"><span className="n">2</span>Podklady</button>
        <button className="step" disabled><span className="n">3</span>Návrhy skladby</button>
        <button className="step" disabled><span className="n">4</span>Výběr</button>
      </div>
      <ResearchBody id={id} onBack={onBack} onChain={onChain} {...props} />
    </main>
  )
}
