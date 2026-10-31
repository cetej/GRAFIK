// "Dávka na výběr": N variants over chosen styles and one page to pick from (engine/variants.py).
// Local FLUX only (operator decision 2026-10-26); a cost (Czech translation) goes through the confirm dialog.
import { Fragment, useState } from 'react'
import { groupStyles, PaymentRequired, variantsApi, type Batch, type ImageRequest, type Job, type StyleCard } from './api.ts'
import type { Confirm } from './App.tsx'

const COUNTS = [6, 8, 12, 16]

export function BatchPanel({ request, styleCards, styleSel, styleText, disabled, onCreated, onConfirm, onError }: {
  request: () => ImageRequest
  styleCards: StyleCard[]
  styleSel: string
  styleText: string
  disabled: boolean
  onCreated: (b: Batch) => void
  onConfirm: (c: Confirm) => void
  onError: (msg: string) => void
}) {
  const [count, setCount] = useState(8)
  const [picked, setPicked] = useState<string[] | null>(null) // null = the style chosen above
  const chosen = picked ?? [styleSel]
  const toggle = (key: string) =>
    setPicked(chosen.includes(key) ? chosen.filter((k) => k !== key) : [...chosen, key])
  const option = (key: string, label: string) => (
    <label className="row check" key={key || 'none'}>
      <input type="checkbox" checked={chosen.includes(key)} onChange={() => toggle(key)} /> {label}
    </label>
  )

  const start = async (confirm = false) => {
    const styles = (chosen.length ? chosen : ['']).map((k) => (k === '__custom' ? styleText.trim() : k || null))
    const body = { request: { ...request(), n: 1, style: null, style_id: null, confirm_cost: confirm }, count, styles }
    try {
      onCreated(await variantsApi.create(body))
    } catch (e) {
      if (e instanceof PaymentRequired) {
        onConfirm({ title: `Dávka ${count} variant`, items: e.items, total: e.estimate, onOk: () => start(true) })
      } else onError((e as Error).message)
    }
  }

  return (
    <div className="batch">
      <b>Dávka na výběr</b>
      <p className="hint">Víc obrázků najednou a stránka, kde vyberete oblíbené.</p>
      <div className="row">
        <span>Počet</span>
        <div className="seg">{COUNTS.map((k) => <button key={k} className={count === k ? 'on' : ''} onClick={() => setCount(k)}>{k}</button>)}</div>
      </div>
      <span className="hint">Styly (varianty se rozdělí mezi ně)</span>
      <div className="batch-styles">
        {option('', 'bez stylu')}
        {groupStyles(styleCards).map((g) => (
          <Fragment key={g.key}>
            <b>{g.label}</b>
            {g.cards.map((c) => option(c.slug, c.label))}
          </Fragment>
        ))}
        {styleSel === '__custom' && styleText.trim() && option('__custom', `vlastní: ${styleText.trim()}`)}
      </div>
      <button className="btn" disabled={disabled} onClick={() => start()}>Vygenerovat {count} variant (0 USD)</button>
      <p className="hint">Jen lokální FLUX. Placený generátor dávku nedělá.</p>
    </div>
  )
}

export function BatchRow({ batch, jobs }: { batch: Batch; jobs: Job[] }) {
  const mine = batch.job_ids.map((id) => jobs.find((j) => j.job_id === id))
  const finished = mine.filter((j) => j && ['done', 'failed', 'cancelled'].includes(j.status))
  const images = mine.reduce((a, j) => a + (j?.status === 'done' ? j.images.length : 0), 0)
  const known = mine.every(Boolean) // older jobs drop out of the polled list; the page still works
  return (
    <div className="job batch-row">
      <b>Dávka {batch.count} variant</b>
      <span className="what">{!known ? 'hotovo dříve' : finished.length === mine.length ? `hotovo, ${images} obrázků` : `${images} z ${batch.count} hotovo`}</span>
      <a className="btn small" href={batch.page} target="_blank" rel="noreferrer">Otevřít stránku výběru</a>
    </div>
  )
}
