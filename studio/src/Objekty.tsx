import { useCallback, useEffect, useRef, useState } from 'react'
import { api, isCzech, type Objekt, type ObjektyDoc } from './api.ts'

// Vrstvy objektů v generované ilustraci (náčrt schválený 2026-11-04): najít objekty, pod nimi se dokreslí podklad,
// objekt jde smazat, posunout tažením a změnit pokynem. Uložení = nový obrázek v Knihovně s vrstvami pro VectorCraft.
const usd = (v: number) => `${v.toFixed(3).replace(/0$/, '').replace('.', ',')} USD`
const SAM_USD = 0.005
const TRANSLATE_USD = 0.01

type Box = [number, number, number, number]

export default function ObjektyPanel({ selected, src, onCreated, onError }:
  { selected: string; src: string; onCreated: (ref: string) => void; onError: (msg: string) => void }) {
  const [doc, setDoc] = useState<ObjektyDoc | null>(null)
  const [sel, setSel] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [pokyn, setPokyn] = useState('')
  const [adding, setAdding] = useState(false)
  const [newBox, setNewBox] = useState<Box | null>(null)
  const [newName, setNewName] = useState('')
  const [drag, setDrag] = useState<{ oid: string; x: number; y: number; dx: number; dy: number } | null>(null)
  const area = useRef<HTMLDivElement>(null)

  const load = useCallback(() => api.objekty(selected).then(setDoc).catch((e) => onError(e.message)), [selected, onError])
  useEffect(() => { setDoc(null); setSel(null); load() }, [load])
  const pending = doc?.ulohy.some((u) => u.status === 'queued' || u.status === 'running') ?? false
  useEffect(() => {
    if (!pending) return
    const t = setTimeout(load, 2000)
    return () => clearTimeout(t)
  }, [pending, doc, load])

  const run = async (what: string, fn: () => Promise<unknown>) => {
    setBusy(what)
    try { await fn() } catch (e) { onError((e as Error).message) } finally { setBusy(null) }
  }
  const size = doc?.size ?? [1000, 1000]
  const plate = doc?.podklad && !doc.podklad.zastaraly
  const failed = doc?.ulohy.filter((u) => u.status === 'failed').slice(-1)[0]
  const current = doc?.objects.find((o) => o.id === sel) ?? null

  const point = (e: React.PointerEvent) => {
    const r = area.current!.getBoundingClientRect()
    return { x: (e.clientX - r.left) / r.width * 1000, y: (e.clientY - r.top) / r.height * 1000, w: r.width, h: r.height }
  }
  // posun je v px obrázku, rámeček objektu v 0–1000
  const shift = (o: Objekt) => [o.posun[0] / size[0] * 1000, o.posun[1] / size[1] * 1000]
  const hit = (x: number, y: number) => [...(doc?.objects ?? [])].reverse().find((o) => {
    if (!o.viditelny) return false
    const [sx, sy] = shift(o)
    return y >= o.box[0] + sy && y <= o.box[2] + sy && x >= o.box[1] + sx && x <= o.box[3] + sx
  })
  const down = (e: React.PointerEvent) => {
    const p = point(e)
    if (adding) { setNewBox([p.y, p.x, p.y, p.x]); e.currentTarget.setPointerCapture(e.pointerId); return }
    const o = hit(p.x, p.y)
    setSel(o?.id ?? null)
    if (o && plate) { setDrag({ oid: o.id, x: e.clientX, y: e.clientY, dx: 0, dy: 0 }); e.currentTarget.setPointerCapture(e.pointerId) }
  }
  const move = (e: React.PointerEvent) => {
    if (adding && newBox && e.buttons === 1) {
      const p = point(e)
      setNewBox([newBox[0], newBox[1], p.y, p.x])
    } else if (drag) {
      const r = area.current!.getBoundingClientRect()
      setDrag({ ...drag, dx: (e.clientX - drag.x) / r.width * size[0], dy: (e.clientY - drag.y) / r.height * size[1] })
    }
  }
  const up = () => {
    if (drag && (Math.abs(drag.dx) > 2 || Math.abs(drag.dy) > 2)) {
      const o = doc!.objects.find((x) => x.id === drag.oid)!
      const posun = [Math.round(o.posun[0] + drag.dx), Math.round(o.posun[1] + drag.dy)]
      run('posun', async () => setDoc(await api.objektyEdit(selected, o.id, { posun })))
    }
    setDrag(null)
  }
  const normBox = (b: Box): number[] => [Math.min(b[0], b[2]), Math.min(b[1], b[3]), Math.max(b[0], b[2]), Math.max(b[1], b[3])].map((v) => Math.round(Math.max(0, Math.min(1000, v))))
  const boxOk = newBox && Math.abs(newBox[2] - newBox[0]) > 15 && Math.abs(newBox[3] - newBox[1]) > 15

  const layerStyle = (o: Objekt): React.CSSProperties => {
    const dx = o.posun[0] + (drag?.oid === o.id ? drag.dx : 0), dy = o.posun[1] + (drag?.oid === o.id ? drag.dy : 0)
    return { transform: `translate(${dx / size[0] * 100}%, ${dy / size[1] * 100}%)` }
  }
  const changeUsd = SAM_USD + (isCzech(pokyn) ? TRANSLATE_USD : 0)

  return (
    <div className="objekty">
      <div className="objekty-canvas" ref={area} onPointerDown={down} onPointerMove={move} onPointerUp={up}
        style={{ cursor: adding ? 'crosshair' : plate ? 'grab' : 'default' }}>
        <img src={plate ? doc!.podklad!.url : src} alt="" draggable={false} />
        {plate && doc!.objects.filter((o) => o.viditelny).map((o) => (
          <img key={o.id + o.verze.length} src={o.vrstva_url} alt={o.nazev} draggable={false}
            className={`objekty-layer ${o.id === sel ? 'sel' : ''}`} style={layerStyle(o)} />
        ))}
        {!plate && current && <div className="objekty-box" style={{ top: `${current.box[0] / 10}%`, left: `${current.box[1] / 10}%`,
          height: `${(current.box[2] - current.box[0]) / 10}%`, width: `${(current.box[3] - current.box[1]) / 10}%` }} />}
        {newBox && <div className="objekty-box new" style={(([t, l, b, r]) => ({ top: `${t / 10}%`, left: `${l / 10}%`,
          height: `${(b - t) / 10}%`, width: `${(r - l) / 10}%` }))(normBox(newBox))} />}
      </div>

      <div className="objekty-side">
        <b>Vrstvy</b>
        {!doc ? <p className="hint">Načítám…</p> : doc.objects.length === 0 ? (
          <>
            <p className="hint">Obrázek zatím nemá vrstvy. Claude pojmenuje objekty, SAM-3 je přesně obtáhne a lokální FLUX pod nimi dokreslí podklad.</p>
            <button className="btn go" disabled={!!busy} onClick={() => run('find', async () => setDoc(await api.objektyFind(selected)))}>
              {busy === 'find' ? 'Hledám objekty…' : `Najít objekty · do ${usd(doc.find_usd)}`}</button>
          </>
        ) : (
          <>
            <ul className="objekty-list">
              {doc.objects.map((o) => (
                <li key={o.id} className={o.id === sel ? 'sel' : ''} onClick={() => setSel(o.id)}>
                  <input type="checkbox" checked={o.viditelny} disabled={!plate || !!busy} title="Zaškrtnuto = objekt je v obrázku"
                    onClick={(e) => e.stopPropagation()}
                    onChange={(e) => run('vid', async () => setDoc(await api.objektyEdit(selected, o.id, { viditelny: e.target.checked })))} />
                  <span>{o.nazev}</span>
                  {o.verze.length > 1 && <span className="hint">v{o.verze.length}</span>}
                </li>
              ))}
              <li className="podklad"><span>Podklad</span>
                <span className="hint">{plate ? 'dokreslený' : doc.podklad?.zastaraly ? 'zastaralý' : pending ? 'dokresluje se…' : 'chybí'}</span></li>
            </ul>
            {pending && <p className="hint">Lokální FLUX pracuje, stav se obnoví sám.</p>}
            {failed && <p className="panel-warning">Úloha selhala: {failed.error}</p>}
            {(!doc.podklad || doc.podklad.zastaraly) && !pending && (
              <button className="btn" disabled={!!busy} onClick={() => run('plate', async () => { await api.objektyPlate(selected); await load() })}>
                Dokreslit podklad · 0 USD</button>)}

            {current && (
              <div className="objekty-actions">
                <div className="hint">Vybráno: <b>{current.nazev}</b>{plate ? ' · posunete tažením v obrázku' : ''}</div>
                <div className="row">
                  <button className="btn small" disabled={!plate || !!busy}
                    onClick={() => run('vid', async () => setDoc(await api.objektyEdit(selected, current.id, { viditelny: !current.viditelny })))}>
                    {current.viditelny ? 'Smazat' : 'Vrátit'}</button>
                  <button className="btn small" disabled={!plate || !!busy || !(current.posun[0] || current.posun[1])}
                    onClick={() => run('posun', async () => setDoc(await api.objektyEdit(selected, current.id, { posun: [0, 0] })))}>
                    Na původní místo</button>
                </div>
                <input className="objekty-input" placeholder="Změnit: třeba „plachetnice s bílou plachtou“" value={pokyn}
                  onChange={(e) => setPokyn(e.target.value)} />
                <button className="btn small" disabled={!pokyn.trim() || !!busy || pending}
                  title="Lokální FLUX překreslí objekt, SAM-3 ho znovu obtáhne"
                  onClick={() => run('change', async () => { await api.objektyChange(selected, current.id, pokyn.trim()); setPokyn(''); await load() })}>
                  {`Změnit · ${usd(changeUsd)}`}</button>
              </div>
            )}

            <div className="objekty-actions">
              {!adding ? (
                <button className="btn small" onClick={() => { setAdding(true); setNewBox(null) }}>+ Objekt, který chybí</button>
              ) : (
                <>
                  <div className="hint">Obtáhněte objekt rámečkem v obrázku a pojmenujte ho.</div>
                  <input className="objekty-input" placeholder="Název, třeba racek" value={newName} onChange={(e) => setNewName(e.target.value)} />
                  <div className="row">
                    <button className="btn small" disabled={!boxOk || !newName.trim() || !!busy}
                      onClick={() => run('add', async () => {
                        setDoc(await api.objektyAdd(selected, normBox(newBox!), newName.trim()))
                        setAdding(false); setNewBox(null); setNewName('')
                      })}>{busy === 'add' ? 'Obtahuji…' : `Přidat · ${usd(doc.add_usd ?? SAM_USD)}`}</button>
                    <button className="btn small" onClick={() => { setAdding(false); setNewBox(null) }}>Zrušit</button>
                  </div>
                </>
              )}
            </div>

            <div className="row">
              <button className="btn go" disabled={!plate || !!busy || pending}
                title="Nový obrázek v Knihovně, každý objekt ve vlastní vrstvě; tenhle zůstane beze změny"
                onClick={() => run('done', async () => onCreated((await api.objektyDone(selected)).ref))}>Uložit jako nový obrázek</button>
              <button className="btn" disabled={!plate || !!busy || pending}
                onClick={() => run('vc', async () => { const { ref } = await api.objektyDone(selected); await api.openVectorcraft(ref); onCreated(ref) })}>
                Otevřít ve VectorCraftu</button>
            </div>
            <p className="hint">Smazat a posunout jsou zdarma. Tenhle obrázek zůstane beze změny.</p>
          </>
        )}
      </div>
    </div>
  )
}
