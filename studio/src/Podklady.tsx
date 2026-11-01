import { useCallback, useEffect, useState } from 'react'
import {
  infoApi, PaymentRequired, researchApi,
  type Dossier, type DossierImage, type Fact, type FactSource, type RefMeta, type ResearchRow, type ResearchState,
} from './api.ts'
import { fmtUsd, type Confirm } from './App.tsx'

// Infografika z tématu, krok Podklady (engine/research.py). Rozpory nahoře, nic se nerozhoduje potichu; placené hledání je jen tlačítko s cenou.
const THEMES = { rozmery: 'Rozměry', vznik: 'Vznik', stavba: 'Stavba a materiál', rekord: 'Rekordy', ostatni: 'Ostatní' } as const
const ROLES = { pudorys: 'Půdorys', rez: 'Řez', pruceli: 'Průčelí', interier: 'Interiér', detail: 'Detail', material: 'Materiál', nezarazeno: 'Nezařazeno' } as const
const STATE_LABEL = { shoda: 'shoda', rozpor: 'rozpor', jediny_zdroj: 'jeden zdroj' } as const

const num = (v: number) => v.toLocaleString('cs-CZ', { maximumFractionDigits: 2 })
const fmtValue = (v: FactSource['hodnota'], unit: string | null) => {
  if (v === undefined || v === null) return ''
  return `${Array.isArray(v) ? `${num(v[0])}–${num(v[1])}` : num(v)}${unit ? ` ${unit}` : ''}`
}

export function TopicStart({ onOpen, onError }: { onOpen: (id: string) => void; onError: (msg: string) => void }) {
  const [topic, setTopic] = useState('')
  const [busy, setBusy] = useState(false)
  const [list, setList] = useState<ResearchRow[]>([])
  useEffect(() => { researchApi.list().then(setList).catch((e) => onError(e.message)) }, [onError])
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
        <button className="btn go" disabled={!topic.trim() || busy} onClick={start}>{busy ? 'Spouštím…' : 'Dohledat podklady · 0 USD'}</button>
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

function FactRow({ fact }: { fact: Fact }) {
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

function DossierView({ state, dossier, onOpenVersion, onOpen, setConfirm, onError, onUseRef, onInfographicDoc }: Props & { state: ResearchState; dossier: Dossier }) {
  const facts = dossier.facts
  const conflicts = facts.filter((f) => f.stav === 'rozpor')
  const others = facts.filter((f) => f.stav !== 'rozpor')
  const themes = (Object.keys(THEMES) as (keyof typeof THEMES)[]).filter((t) => others.some((f) => f.tema === t))
  const [theme, setTheme] = useState<keyof typeof THEMES>(themes[0] ?? 'rozmery')
  const [askQid, setAskQid] = useState(false)
  const [qid, setQid] = useState(dossier.entita.qid)
  const [webUsd, setWebUsd] = useState<number | null>(null)
  useEffect(() => { researchApi.estimate(true).then((e) => setWebUsd(e.total_usd)).catch(() => setWebUsd(null)) }, [])

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

      {dossier.otazky_bez_odpovedi.length > 0 && (
        <section className="card">
          <h3>Bez odpovědi</h3>
          <ul className="citations">{dossier.otazky_bez_odpovedi.map((q) => <li key={q}>{q}</li>)}</ul>
        </section>
      )}
    </>
  )
}

interface Props {
  onOpenVersion: (id: string) => void
  onOpen: (src: string) => void
  setConfirm: (c: Confirm) => void
  onError: (msg: string) => void
  onUseRef: (m: RefMeta) => void
  onInfographicDoc: (id: string) => void
}

export default function Podklady({ id, onBack, ...props }: Props & { id: string; onBack: () => void }) {
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
    <main className="guide-start podklady">
      <div className="row">
        <button className="btn small" onClick={onBack}>← Průvodce</button>
        <b className="guide-title">Infografika z tématu{state ? `: ${state.tema}` : ''}</b>
      </div>
      <div className="steps">
        <button className="step done" onClick={onBack}><span className="n">✓</span>Zadání</button>
        <button className="step cur"><span className="n">2</span>Podklady</button>
      </div>
      {waiting && (
        <section className="card">
          <p><b>Dohledávám podklady…</b></p>
          <p className="hint">Wikidata, Wikipedia a Wikimedia Commons, 0 USD. Běžně kolem minuty a půl, obrázky se stahují po jednom.</p>
        </section>
      )}
      {state?.status === 'failed' && !state.dossier && (
        <section className="card">
          <p className="warn">Rešerše selhala: {state.error ?? 'důvod Engine neuvedl'}</p>
          <button className="btn" onClick={onBack}>Zpět na zadání</button>
        </section>
      )}
      {state?.dossier && <DossierView key={state.id} state={state} dossier={state.dossier} {...props} />}
    </main>
  )
}
