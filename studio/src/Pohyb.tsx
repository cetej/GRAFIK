import { useEffect, useState } from 'react'
import { pohybApi, pohybKey, type PohybItem, type PohybPages, type PohybPreview, type PohybSent } from './api.ts'

const FORMATS = ['9:16', '16:9', '4:5', '1:1']

/** Hotová grafika i s podklady do POHYBu jako zadání animace (operátor 3. 11., náčrt schválený týž den). Kopie, nic se neplatí ani nepřepisuje. */
export default function PohybDialog({ start, onClose, onError }: { start: PohybItem; onClose: () => void; onError: (msg: string) => void }) {
  const [pages, setPages] = useState<PohybPages | null>(null)
  const [chosen, setChosen] = useState<PohybItem[]>([])
  const [preview, setPreview] = useState<PohybPreview | null>(null)
  const [sdeleni, setSdeleni] = useState('')
  const [format, setFormat] = useState('')
  const [busy, setBusy] = useState(false)
  const [sent, setSent] = useState<PohybSent | null>(null)

  const startKey = pohybKey(start)
  useEffect(() => {
    pohybApi.pages(start).then((p) => { setPages(p); setChosen(p.vybrane) }).catch((e) => { onError(e.message); onClose() })
  }, [startKey]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [onClose])
  useEffect(() => {
    if (!chosen.length) { setPreview(null); return }
    let stale = false
    const wait = setTimeout(() => pohybApi.preview(chosen).then((p) => { if (!stale) setPreview(p) }).catch((e) => !stale && onError(e.message)), 200)
    return () => { stale = true; clearTimeout(wait) }
  }, [chosen]) // eslint-disable-line react-hooks/exhaustive-deps

  const toggle = (it: PohybItem) => setChosen((c) => (c.some((x) => pohybKey(x) === pohybKey(it)) ? c.filter((x) => pohybKey(x) !== pohybKey(it)) : [...c, it]))
  const send = async () => {
    setBusy(true)
    try { setSent(await pohybApi.send(chosen, sdeleni, format || preview?.format || '')) } catch (e) { onError((e as Error).message) } finally { setBusy(false) }
  }
  const why = !pages ? '' : !pages.pohyb_bezi ? `POHYB neběží (${pages.pohyb_url}). Spusťte start-pohyb.bat a otevřete dialog znovu.` : !chosen.length ? 'Vyberte aspoň jednu stránku.' : ''
  const total = preview?.stranky.reduce((a, s) => ({ objekty: a.objekty + s.objekty, popisky: a.popisky + s.popisky, panely: a.panely + s.panely }), { objekty: 0, popisky: 0, panely: 0 })

  return (
    <div className="modal" onClick={onClose}>
      <div className="dialog pohyb" onClick={(e) => e.stopPropagation()}>
        <div className="row between">
          <h2>Poslat do POHYBu jako zadání animace</h2>
          <button className="btn small" onClick={onClose} aria-label="Zavřít">×</button>
        </div>
        {!pages ? <p className="hint">Načítám…</p> : sent ? (
          <>
            <p>Zadání <b>{sent.pohyb.id}</b> je v POHYBu: {sent.stranky} {sent.stranky === 1 ? 'stránka' : sent.stranky < 5 ? 'stránky' : 'stránek'} i s podklady.</p>
            <div className="row">
              <a className="btn go" href={sent.pohyb.url} target="_blank" rel="noreferrer">Otevřít v POHYBu</a>
              <button className="btn" onClick={onClose}>Zavřít</button>
            </div>
            {sent.upozorneni.map((u, i) => <p key={i} className="hint">! {u}</p>)}
            <p className="hint">Kopie balíku zůstala v GRAFIKu: {sent.slozka}</p>
          </>
        ) : (
          <>
            <div className="hint">Stránky v pořadí, v jakém se mají v animaci objevit. Kliknutím přidáte nebo uberete.</div>
            <div className="pohyb-pages">
              {pages.nabidka.map((o) => {
                const n = chosen.findIndex((x) => pohybKey(x) === pohybKey(o.polozka))
                return (
                  <button key={pohybKey(o.polozka)} className={`pohyb-page${n >= 0 ? ' on' : ''}`} onClick={() => toggle(o.polozka)}
                    aria-pressed={n >= 0} title={o.nazev}>
                    {o.nahled ? <img src={o.nahled} alt="" /> : <span className="ph" />}
                    {n >= 0 && <span className="n">{n + 1}</span>}
                    <span className="nm">{o.nazev}</span>
                  </button>
                )
              })}
            </div>
            <label className="hint" htmlFor="pohyb-sdeleni">Co má animace sdělit (nepovinné, jde do zadání POHYBu)</label>
            <textarea id="pohyb-sdeleni" className="full" rows={2} value={sdeleni} onChange={(e) => setSdeleni(e.target.value)}
              placeholder="Jednou dvěma větami: co má divák z animace pochopit." />
            <div className="hint">Formát videa</div>
            <div className="seg">
              {FORMATS.map((f) => <button key={f} className={(format || preview?.format) === f ? 'on' : ''} onClick={() => setFormat(f)}>{f}</button>)}
            </div>
            <div className="hint">Co pojede s ním</div>
            {preview && total ? (
              <ul className="pohyb-what">
                <li>{preview.stranky.length} {preview.stranky.length === 1 ? 'stránka' : preview.stranky.length < 5 ? 'stránky' : 'stránek'}: hotový obraz{preview.stranky.some((s) => s.vrstvy) ? ', vrstvy, obraz bez textu' : ''}{total.objekty ? `, ${total.objekty} objektů zvlášť` : ''}</li>
                {total.popisky > 0 && <li>{total.popisky} popisků s místem a kotvou</li>}
                {total.panely > 0 && <li>{total.panely} panelů s body.json</li>}
                {preview.predlohy > 0 && <li>{preview.predlohy} předloh s autorem a licencí</li>}
                {preview.reserse.length > 0 && <li>rešerše {preview.reserse.join(', ')}, {preview.fakta} faktů se zdroji</li>}
                <li>zdroje a výhrady (AI, model, licence)</li>
                {preview.upozorneni.map((u, i) => <li key={i} className="warn">! {u}</li>)}
              </ul>
            ) : <p className="hint">{chosen.length ? 'Počítám…' : '—'}</p>}
            <div className="row between">
              <span className="hint">Kopie, nic se nepřepisuje. Nic se neplatí.</span>
              <button className="btn go" disabled={busy || !!why} title={why} onClick={send}>{busy ? 'Skládám balík…' : 'Poslat do POHYBu · 0 USD'}</button>
            </div>
            {why && <p className="warn">{why}</p>}
          </>
        )}
      </div>
    </div>
  )
}
