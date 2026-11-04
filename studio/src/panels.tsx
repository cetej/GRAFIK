import { Component, useEffect, useState, type ReactNode } from 'react'
import { api, imageUrl, type Job, type LineageNode, type Provenance } from './api.ts'
import { fmtUsd } from './App.tsx'

const ACTION_LABEL = { add: 'přidat', remove: 'odstranit', move: 'přesunout', recolor: 'změnit' } as const
const BACKEND_LABEL = (b?: string) => (!b ? '—' : b === 'flux-local' ? 'Lokální FLUX 3 Klein' : b === 'nb-pro' ? 'Nano Banana Pro (Gemini)' : b)

// One broken panel must not blank the whole Studio (LEARNINGS 2026-11-01): the other tabs keep running.
export class PanelBoundary extends Component<
  { what: string; resetKey?: unknown; note?: string; panel?: boolean; children: ReactNode },
  { error: Error | null }
> {
  state = { error: null as Error | null }
  static getDerivedStateFromError(error: Error) { return { error } }
  componentDidUpdate(prev: { resetKey?: unknown }) {
    if (this.state.error && prev.resetKey !== this.props.resetKey) this.setState({ error: null })
  }
  render() {
    const { error } = this.state
    if (!error) return this.props.children
    const body = (
      <section className={`card ${this.props.panel ? 'right' : ''}`} role="alert">
        <h3>{this.props.what}: chyba při zobrazení</h3>
        <p>{this.props.note ?? 'Ostatní záložky běží dál, data zůstala beze změny.'}</p>
        <p className="warn">{error.message}</p>
        <button className="btn" onClick={() => this.setState({ error: null })}>Zkusit znovu</button>
      </section>
    )
    return this.props.panel ? body : <main className="guide-start">{body}</main>
  }
}

function nodeLabel(n: LineageNode, i: number) {
  if (n.request.edit) return `${ACTION_LABEL[n.request.edit.action]}: ${n.request.edit.instruction}`
  if (n.parent) return n.request.supersample ? 'varianta · drobné detaily' : 'varianta'
  return i === 0 ? 'zadání' : n.request.prompt ?? ''
}

export function HistoryPanel({ selected, jobs, onSelect }: {
  selected: string | null; jobs: Job[]; onSelect: (ref: string) => void
}) {
  const [tree, setTree] = useState<LineageNode[]>([])
  const [prov, setProv] = useState<Provenance | null>(null)
  const [showPrompt, setShowPrompt] = useState(false)
  // refetch when the selection changes or a job of this tree finishes
  const doneCount = jobs.filter((j) => j.status === 'done').length

  useEffect(() => {
    if (!selected) return
    api.lineage(selected).then(setTree).catch(() => setTree([]))
    api.provenance(selected).then(setProv).catch(() => setProv(null))
  }, [selected, doneCount])

  if (!selected) return <section className="card right"><p className="hint">Zatím žádný obrázek.</p></section>

  const depth = (n: LineageNode): number => {
    let d = 0
    let p = n.parent
    while (p && d < 20) { d++; p = tree.find((x) => x.ref === p)?.parent ?? null }
    return d
  }

  return (
    <section className="card right">
      <h3>Historie verzí</h3>
      <div className="tree">
        {tree.map((node, i) => (
          <button key={node.ref} className={`node ${node.ref === selected ? 'cur' : ''}`} style={{ marginLeft: Math.min(depth(node), 5) * 16 }}
            disabled={!node.image} onClick={() => node.image && onSelect(node.ref)} title={node.image ? 'Zobrazit tuto verzi' : 'Ještě se generuje'}>
            {node.image ? <img src={imageUrl(node.ref, 128)} alt="" /> : <span className="ph">…</span>}
            <span>v{i + 1} · {nodeLabel(node, i).slice(0, 48)}{node.status !== 'done' ? <i className="hint"> ({node.status === 'failed' ? 'selhalo' : 'běží'})</i> : null}</span>
          </button>
        ))}
      </div>

      <h3>O obrázku</h3>
      {prov ? (
        <>
          <dl>
            <dt>Generátor</dt><dd>{BACKEND_LABEL(prov.backend)}</dd>
            <dt>Cena</dt><dd>{prov.cost_usd == null ? '—' : <span className={`tag ${prov.cost_usd ? 'paid' : 'free'}`}>{fmtUsd(prov.cost_usd)}</span>}</dd>
            <dt>Rozměr</dt><dd>{prov.params?.size ?? '—'}{prov.params?.render_size && prov.params.render_size !== prov.params.size ? ` (vykresleno ${prov.params.render_size})` : ''}</dd>
            <dt>Seed</dt><dd>{prov.seed ?? '—'}</dd>
            {prov.style_id && <><dt>Styl</dt><dd>{prov.style_id}</dd></>}
            <dt>Předlohy</dt>
            <dd>{prov.refs?.length ? prov.refs.map((r, i) => <div key={i}>{r.source ?? 'obrázek'} ({r.role}{r.license ? `, ${r.license}` : ''})</div>) : '—'}</dd>
            {prov.timing_s?.generate != null && <><dt>Čas</dt><dd>{Math.round(prov.timing_s.generate)} s{prov.timing_s.queue > 2 ? ` + ${Math.round(prov.timing_s.queue)} s ve frontě` : ''}</dd></>}
            <dt>Stav</dt>
            <dd>{prov.reviewed_by
              ? <span className="tag ok">zkontroloval {prov.reviewed_by}</span>
              : <span className="tag ai">{prov.ai_generated ? 'AI · čeká na kontrolu člověkem' : 'čeká na kontrolu člověkem'}</span>}</dd>
          </dl>
          <div className="row">
            {!prov.reviewed_by && <button className="btn small" onClick={() => api.review(selected, 'operátor').then(setProv)}>✓ Zkontrolováno</button>}
            <button className="btn small" onClick={() => setShowPrompt(!showPrompt)}>{showPrompt ? 'Skrýt zadání' : 'Zobrazit zadání'}</button>
          </div>
          {showPrompt && (
            <>
              {prov.translations?.length ? <p className="hint">Původně: {prov.prompt_original}</p> : null}
              <pre className="prompt">{prov.prompt_sent ?? '—'}</pre>
            </>
          )}
        </>
      ) : <p className="hint">Načítám…</p>}
    </section>
  )
}

/** One picture in the enlarged view; the arrows walk the list the opener passed. */
export interface LbItem {
  src: string
  title?: string
  download?: string                       // file name for ⤓ Stáhnout
  onDelete?: () => Promise<void>          // no delete button without it
  deleteLabel?: string
  open?: { label: string; run: () => void }
}
export type OpenImage = (src: string, items?: LbItem[]) => void

export function Lightbox({ items: initial, start, onClose }: { items: LbItem[]; start: number; onClose: () => void }) {
  const [items, setItems] = useState(initial)
  const [i, setI] = useState(start)
  const [fit, setFit] = useState(true)
  const [asking, setAsking] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const n = items.length
  const go = (d: number) => {
    const k = i + d
    if (k < 0 || k >= n) return
    setI(k); setAsking(false); setError(null)
  }
  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
      if (e.key === 'Escape') { if (asking) setAsking(false); else onClose() }
      else if (e.key === 'ArrowLeft') go(-1)
      else if (e.key === 'ArrowRight') go(1)
    }
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  })
  const item = items[i]
  const remove = async () => {
    setBusy(true)
    try {
      await item.onDelete!()
      const left = items.filter((_, k) => k !== i)
      if (!left.length) { onClose(); return }
      setItems(left); setI(Math.min(i, left.length - 1)); setAsking(false)
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  return (
    <div className="lightbox" onClick={onClose}>
      <div className="lb-top" onClick={(e) => e.stopPropagation()}>
        <span className="lb-info">{n > 1 && <b>{i + 1} / {n}</b>}{item.title && <span title={item.title}>{item.title}</span>}</span>
        <div className="lb-bar">
          {item.open && <button className="btn small" onClick={() => { item.open!.run(); onClose() }}>{item.open.label}</button>}
          <a className="btn small" href={item.src} download={item.download ?? ''} title="Stáhnout obrázek v plné velikosti">⤓ Stáhnout</a>
          {item.onDelete && (asking ? (
            <>
              <span className="lb-ask">{item.deleteLabel ?? 'Smazat'}?</span>
              <button className="btn small del" disabled={busy} onClick={remove}>Ano, smazat</button>
              <button className="btn small" disabled={busy} onClick={() => setAsking(false)}>Ne</button>
            </>
          ) : <button className="btn small" onClick={() => setAsking(true)} title={item.deleteLabel ?? 'Smazat'}>🗑 Smazat…</button>)}
          <button className="btn small" onClick={() => setFit(!fit)}>{fit ? '1:1 (skutečná velikost)' : 'Přizpůsobit oknu'}</button>
          <button className="btn small" onClick={onClose}>Zavřít (Esc)</button>
        </div>
      </div>
      {error && <p className="lb-error" onClick={(e) => e.stopPropagation()}>{error}</p>}
      <div className={`lb-img ${fit ? 'fit' : 'full'}`} onClick={(e) => e.stopPropagation()}>
        <img key={item.src} src={item.src} alt={item.title ?? ''} onClick={() => setFit(!fit)} />
      </div>
      {n > 1 && <>
        <button className="lb-arrow prev" disabled={i === 0} onClick={(e) => { e.stopPropagation(); go(-1) }} title="Předchozí (←)" aria-label="Předchozí obrázek">‹</button>
        <button className="lb-arrow next" disabled={i === n - 1} onClick={(e) => { e.stopPropagation(); go(1) }} title="Další (→)" aria-label="Další obrázek">›</button>
      </>}
    </div>
  )
}
