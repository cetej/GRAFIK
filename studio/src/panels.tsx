import { useEffect, useState } from 'react'
import { api, imageUrl, type Job, type LineageNode, type Provenance } from './api.ts'
import { fmtUsd } from './App.tsx'

const ACTION_LABEL = { add: 'přidat', remove: 'odstranit', move: 'přesunout', recolor: 'změnit' } as const
const BACKEND_LABEL = (b: string) => (b === 'flux-local' ? 'Lokální FLUX 3 Klein' : b === 'nb-pro' ? 'Nano Banana Pro (Gemini)' : b)

function nodeLabel(n: LineageNode, i: number) {
  if (n.request.edit) return `${ACTION_LABEL[n.request.edit.action]}: ${n.request.edit.instruction}`
  if (n.parent) return n.request.supersample ? 'varianta · drobné detaily' : 'varianta'
  return i === 0 ? 'zadání' : n.request.prompt
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
            <dt>Cena</dt><dd><span className={`tag ${prov.cost_usd ? 'paid' : 'free'}`}>{fmtUsd(prov.cost_usd)}</span></dd>
            <dt>Rozměr</dt><dd>{prov.params.size}{prov.params.render_size && prov.params.render_size !== prov.params.size ? ` (vykresleno ${prov.params.render_size})` : ''}</dd>
            <dt>Seed</dt><dd>{prov.seed ?? '—'}</dd>
            {prov.style_id && <><dt>Styl</dt><dd>{prov.style_id}</dd></>}
            <dt>Předlohy</dt>
            <dd>{prov.refs.length ? prov.refs.map((r, i) => <div key={i}>{r.source ?? 'obrázek'} ({r.role}{r.license ? `, ${r.license}` : ''})</div>) : '—'}</dd>
            <dt>Čas</dt><dd>{Math.round(prov.timing_s.generate)} s{prov.timing_s.queue > 2 ? ` + ${Math.round(prov.timing_s.queue)} s ve frontě` : ''}</dd>
            <dt>Stav</dt>
            <dd>{prov.reviewed_by
              ? <span className="tag ok">zkontroloval {prov.reviewed_by}</span>
              : <span className="tag ai">AI · čeká na kontrolu člověkem</span>}</dd>
          </dl>
          <div className="row">
            {!prov.reviewed_by && <button className="btn small" onClick={() => api.review(selected, 'operátor').then(setProv)}>✓ Zkontrolováno</button>}
            <button className="btn small" onClick={() => setShowPrompt(!showPrompt)}>{showPrompt ? 'Skrýt zadání' : 'Zobrazit zadání'}</button>
          </div>
          {showPrompt && (
            <>
              {prov.translations?.length ? <p className="hint">Původně: {prov.prompt_original}</p> : null}
              <pre className="prompt">{prov.prompt_sent}</pre>
            </>
          )}
        </>
      ) : <p className="hint">Načítám…</p>}
    </section>
  )
}

export function Lightbox({ src, onClose }: { src: string; onClose: () => void }) {
  const [fit, setFit] = useState(true)
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [onClose])
  return (
    <div className="lightbox" onClick={onClose}>
      <div className="lb-bar" onClick={(e) => e.stopPropagation()}>
        <button className="btn small" onClick={() => setFit(!fit)}>{fit ? '1:1 (skutečná velikost)' : 'Přizpůsobit oknu'}</button>
        <button className="btn small" onClick={onClose}>Zavřít (Esc)</button>
      </div>
      <div className={`lb-img ${fit ? 'fit' : 'full'}`} onClick={(e) => e.stopPropagation()}>
        <img src={src} alt="" onClick={() => setFit(!fit)} />
      </div>
    </div>
  )
}
