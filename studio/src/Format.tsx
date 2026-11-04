import { useEffect, useState } from 'react'
import { api, type FormatPreview } from './api.ts'

// GRAFIK#150: hotová ilustrace na jiný poměr stran. Ořez podle objektu 0 USD, rozšíření obrazu placené (cena v tlačítku = souhlas).
const SIZES = ['16:9', '3:2', '4:5', '1:1', '2:3', '9:16']

const pct = (box: number[]) => ({ top: `${box[0] / 10}%`, left: `${box[1] / 10}%`, height: `${(box[2] - box[0]) / 10}%`, width: `${(box[3] - box[1]) / 10}%` })

export default function FormatDialog({ selected, src, onCreated, onClose, onError }:
  { selected: string; src: string; onCreated: (ref: string) => void; onClose: () => void; onError: (msg: string) => void }) {
  const [size, setSize] = useState('16:9')
  const [objekt, setObjekt] = useState<number[] | null>(null)
  const [preview, setPreview] = useState<FormatPreview | null>(null)
  const [busy, setBusy] = useState<'orez' | 'rozsirit' | null>(null)
  useEffect(() => { setObjekt(null) }, [selected])
  useEffect(() => {
    let stale = false
    api.formatPreview(selected, { size, objekt }).then((p) => { if (!stale) setPreview(p) }).catch((e) => onError(e.message))
    return () => { stale = true }
  }, [selected, size, objekt, onError])
  const pick = (e: React.MouseEvent<HTMLDivElement>) => {
    const r = e.currentTarget.getBoundingClientRect()
    const y = Math.round((e.clientY - r.top) / r.height * 1000), x = Math.round((e.clientX - r.left) / r.width * 1000)
    setObjekt([Math.max(0, y - 20), Math.max(0, x - 20), Math.min(1000, y + 20), Math.min(1000, x + 20)])
  }
  const make = async (zpusob: 'orez' | 'rozsirit') => {
    setBusy(zpusob)
    try {
      onCreated((await api.formatMake(selected, { size, objekt, zpusob, confirm_cost: zpusob === 'rozsirit' })).ref)
    } catch (e) { onError((e as Error).message) } finally { setBusy(null) }
  }
  const status = !preview ? '' : preview.subject_from === 'operator' ? 'Hlavní objekt: určený vámi.'
    : preview.subject_from === 'saliency' ? 'Hlavní objekt našel stroj (červený rámeček). Když nesedí, klepněte na objekt v náhledu.'
    : 'Hlavní objekt stroj jistě nenašel, výřez je uprostřed. Klepněte na hlavní objekt v náhledu.'
  return (
    <div className="panel-choose format-choose">
      <div className="panel-format">
        <div className="hint">Nový formát</div>
        <div className="seg wrap">
          {SIZES.map((f) => <button key={f} className={size === f ? 'on' : ''} onClick={() => setSize(f)}>{f}</button>)}
        </div>
        <p className="hint">{status}</p>
        {preview?.cuts_subject && <p className="panel-warning">Výřez hlavní objekt ořízne. Klepněte na to, co musí zůstat, nebo obraz rozšiřte.</p>}
        <p className="hint">Vznikne nový obrázek v Knihovně, tenhle zůstane beze změny.</p>
        <div className="row">
          <button className="btn go" disabled={!!busy || !preview} onClick={() => make('orez')}>{busy === 'orez' ? 'Ořezávám…' : 'Oříznout · 0 USD'}</button>
          {preview?.expand && <button className="btn" disabled={!!busy} onClick={() => make('rozsirit')}
            title="Celý obraz zůstane, okraje dogeneruje fal (Bria Expand)">{busy === 'rozsirit' ? 'Rozšiřuji…' : `Rozšířit obraz · ${preview.expand_usd.toFixed(2).replace('.', ',')} USD`}</button>}
          <button className="btn" onClick={onClose}>Zavřít</button>
        </div>
      </div>
      <div className="panel-choose-preview">
        <div className="hint">Zelená = co po ořezu zůstane</div>
        <div className="format-preview" onClick={pick} title="Klepnutím určíte hlavní objekt">
          <img src={src} alt="" />
          {preview?.subject && <div className="format-subject" style={pct(preview.subject)} />}
          {preview && <div className="format-crop" style={pct(preview.crop)} />}
        </div>
      </div>
    </div>
  )
}
