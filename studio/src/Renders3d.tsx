import { useEffect, useMemo, useState } from 'react'
import { m3dApi, type Model3dVersion, type Render3d } from './api.ts'

// Model z dílů (3D infografika tvora, fáze 3, náčrt schválený 5. 11.): rendery, textura z lokálního FLUXu s výběrem
// varianty podle shody obrysu a stránka do Infografik. Vše 0 USD; FLUX i Blender jdou frontou Engine.

const SEEDS = [61, 62, 63]
const FORMATY = [{ id: 'oba', label: '16:9 i 9:16', formaty: ['16:9', '9:16'] }, { id: '169', label: 'jen 16:9', formaty: ['16:9'] }, { id: '916', label: 'jen 9:16', formaty: ['9:16'] }]
const iouText = (x: number) => x.toLocaleString('cs-CZ', { maximumFractionDigits: 3 })

export default function Renders3d({ model, onError, onDoc }: {
  model: Model3dVersion
  onError: (msg: string) => void
  onDoc: (id: string) => void
}) {
  const renders = model.renders ?? []
  // render v hlíně: má to v požadavku, nebo (starší render bez uloženého požadavku) už posloužil jako předloha textury
  const usedAsClay = new Set((model.textury ?? []).map((t) => t.predloha))
  const isClay = (r: Render3d) => !!r.pozadavek?.hlina || usedAsClay.has(r.id)
  const colour = renders.filter((r) => !isClay(r) && Object.keys(r.vrstvy ?? {}).length > 0)
  const [sel, setSel] = useState<string | null>(null)
  const render: Render3d | undefined = colour.find((r) => r.id === sel) ?? colour[colour.length - 1]
  const clay = renders.filter((r) => isClay(r) && render && r.res.join() === render.res.join())
  const textury = (model.textury ?? []).filter((t) => t.render === render?.id)
  const textura = textury[textury.length - 1]
  const layers = Object.keys(render?.vrstvy ?? {})
  const [zoom, setZoom] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  // textura: které vrstvy, prompt a složení; výchozí z poslední textury tohoto renderu
  const [form, setForm] = useState<Record<string, { on: boolean; prompt: string; slozeni: 'okno' | 'pod' }>>({})
  const [pick, setPick] = useState<Record<string, number>>({})
  const [titulek, setTitulek] = useState('')
  const [format, setFormat] = useState('oba')
  const [popisky, setPopisky] = useState<Record<string, string>>({})
  const [points, setPoints] = useState<string[]>([])
  const [docs, setDocs] = useState<{ id: string; size: string }[]>([])
  const [notes, setNotes] = useState<string[]>([])
  const [hotovo, setHotovo] = useState<string | null>(null)
  const [qid, setQid] = useState('')
  const [nazev, setNazev] = useState('')
  const [tema, setTema] = useState<string | null>(null)

  useEffect(() => {
    if (!render) return
    setForm(Object.fromEntries(layers.map((n) => {
      const last = textura?.vrstvy[n]
      return [n, { on: !!last || layers.length === 1, prompt: last?.prompt ?? '', slozeni: last?.slozeni ?? 'pod' }]
    })))
    fetch(m3dApi.file(model.id, model.version, render.body)).then((r) => r.json())
      .then((b: { points: Record<string, unknown> }) => setPoints(Object.keys(b.points))).catch(() => setPoints([]))
  }, [render?.id, textura?.id]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    setPick(textura ? Object.fromEntries(Object.entries(textura.vrstvy).map(([n, v]) => [n, v.doporuceny])) : {})
    setDocs([])
    setHotovo(null)
    setTema(null)
  }, [textura?.id])
  useEffect(() => { if (!titulek) setTitulek(model.title) }, [model.title]) // eslint-disable-line react-hooks/exhaustive-deps

  const run = async (what: string, fn: () => Promise<unknown>) => {
    setBusy(what)
    try {
      await fn()
    } catch (e) {
      onError(String((e as Error).message))
    } finally {
      setBusy(null)
    }
  }
  const file = (name: string, w?: number) => m3dApi.file(model.id, model.version, name, w)
  const clayRender = () => run('hlina', () => m3dApi.render(model.id, model.version,
    { ...(render?.pozadavek ?? {}), hlina: true, samples: 32, pruhledne: undefined, caller: 'studio-textura' }))
  const chosen = useMemo(() => Object.entries(form).filter(([, v]) => v.on), [form])
  const texture = () => {
    if (!render || !clay.length) return
    if (!chosen.length || chosen.some(([, v]) => !v.prompt.trim())) { onError('Vyber vrstvu a napiš k ní popis povrchu (anglicky).'); return }
    run('textura', () => m3dApi.textura(model.id, model.version, {
      render: render.id, predloha: clay[clay.length - 1].id, seeds: SEEDS,
      vrstvy: Object.fromEntries(chosen.map(([n, v]) => [n, { prompt: v.prompt.trim(), slozeni: v.slozeni }])),
    }))
  }
  const makePage = () => {
    if (!textura) return
    const formaty = FORMATY.find((f) => f.id === format)!.formaty
    if (!Object.values(popisky).some((t) => t.trim())) { onError('Napiš aspoň jeden popisek k bodu modelu.'); return }
    run('stranka', async () => {
      const picked = await m3dApi.texturaVyber(model.id, model.version, textura.id, { seedy: pick, na_vysku: formaty.includes('9:16') })
      const done = picked.dir.split('/').pop()!
      const out = await m3dApi.stranka(model.id, model.version, textura.id, { hotovo: done, titulek, popisky, nazvy_vrstev: {}, formaty })
      setHotovo(formaty.includes('9:16') ? done : null)     // řetězec skládá i stránku na výšku
      setDocs(out.dokumenty)
      setNotes(out.hlaseni ?? [])
    })
  }
  // do řetězce: názvy částí jsou první řádky popisků, texty k nim napíše řetězec z faktů dossieru
  const names = Object.fromEntries(Object.entries(popisky).map(([p, t]) => [p, t.split('\n')[0].trim()]).filter(([, t]) => t))
  const toTopic = () => {
    if (!textura) return
    if (!/^Q\d+$/.test(qid.trim())) { onError('Napiš položku Wikidaty tématu, např. Q81214 pro vorvaně.'); return }
    if (!nazev.trim() || !Object.keys(names).length) { onError('Napiš, co obraz ukazuje, a aspoň jeden popisek k bodu modelu.'); return }
    run('tema', async () => {
      const done = hotovo ?? (await m3dApi.texturaVyber(model.id, model.version, textura.id, { seedy: pick, na_vysku: true })).dir.split('/').pop()!
      setHotovo(done)
      setTema((await m3dApi.tema(model.id, model.version, textura.id, { qid: qid.trim(), hotovo: done, nazev: nazev.trim(), popisky: names })).id)
    })
  }

  if (!colour.length) {
    return <div className="r3d"><h3>Rendery a textura</h3><p className="hint">Model zatím nemá barevný render s vrstvami (render s „vrstvy“ a „samostatne“ přes API).</p></div>
  }
  return (
    <div className="r3d">
      <h3>1 · Rendery</h3>
      <div className="r3d-grid">
        {colour.map((r) => (
          <figure key={r.id} className={r.id === render?.id ? 'on' : ''} onClick={() => setSel(r.id)} title="Vybrat render pro texturu">
            <img src={file(r.file, 384)} alt={r.id} />
            <figcaption>{r.id} · barevný · {Object.keys(r.vrstvy).length} vrstvy</figcaption>
            <button className="zoom-btn" onClick={(e) => { e.stopPropagation(); setZoom(file(r.file)) }} title="Zvětšit">⤢</button>
          </figure>
        ))}
        {clay.map((r) => (
          <figure key={r.id}>
            <img src={file(r.file, 384)} alt={r.id} />
            <figcaption>{r.id} · v hlíně (předloha tvaru)</figcaption>
            <button className="zoom-btn" onClick={() => setZoom(file(r.file))} title="Zvětšit">⤢</button>
          </figure>
        ))}
        <div className="r3d-add">
          <button className="btn" disabled={busy === 'hlina' || !render?.pozadavek} onClick={clayRender}>{busy === 'hlina' ? 'Zadávám…' : 'Render v hlíně · 0 USD'}</button>
          <span className="hint">{render?.pozadavek ? `stejná kamera jako ${render.id}, asi 40 s` : `${render?.id} je starší render bez uložené kamery, hlínu k němu udělej přes API`}</span>
        </div>
      </div>

      <h3>2 · Textura FLUXem</h3>
      <div className="r3d-form">
        {layers.map((n) => (
          <div key={n} className="r3d-layer">
            <label><input type="checkbox" checked={form[n]?.on ?? false}
              onChange={(e) => setForm({ ...form, [n]: { ...form[n], on: e.target.checked } })} /> {n}</label>
            <select value={form[n]?.slozeni ?? 'pod'} disabled={!form[n]?.on}
              onChange={(e) => setForm({ ...form, [n]: { ...form[n], slozeni: e.target.value as 'okno' | 'pod' } })}>
              <option value="okno">okno (kůže s průhledem)</option>
              <option value="pod">pod (vnitřek nad dutinou)</option>
            </select>
            <textarea rows={2} disabled={!form[n]?.on} placeholder="Popis povrchu anglicky, tvar dodá render" value={form[n]?.prompt ?? ''}
              onChange={(e) => setForm({ ...form, [n]: { ...form[n], prompt: e.target.value } })} />
          </div>
        ))}
        <div className="row">
          <button className="btn" disabled={!clay.length || busy === 'textura'} onClick={texture}
            title={clay.length ? '' : 'Nejdřív render v hlíně'}>{busy === 'textura' ? 'Zadávám…' : `${textura ? 'Spustit znovu' : 'Spustit'} · 0 USD`}</button>
          <span className="hint">{chosen.length * SEEDS.length} obrazů lokálním FLUXem, kolem 80 s na obraz{clay.length ? '' : '; nejdřív render v hlíně'}</span>
        </div>
      </div>
      {textura && Object.entries(textura.vrstvy).map(([n, v]) => (
        <div key={n}>
          <p className="hint">{n} ({v.slozeni}) · klikni na variantu</p>
          <div className="r3d-grid">
            {Object.entries(v.seedy).map(([seed, s]) => {
              const bad = s.iou < 0.9
              return (
                <figure key={seed} className={`${pick[n] === Number(seed) ? 'on' : ''} ${bad ? 'bad' : ''}`} onClick={() => setPick({ ...pick, [n]: Number(seed) })}>
                  <img src={file(`${textura.dir}/${s.soubor}`, 384)} alt={`seed ${seed}`} />
                  <figcaption>seed {seed} · IoU {iouText(s.iou)}{Number(seed) === v.doporuceny ? ' · doporučeno' : ''}{bad ? ' · tvar nesedí' : ''}</figcaption>
                  <button className="zoom-btn" onClick={(e) => { e.stopPropagation(); setZoom(file(`${textura.dir}/${s.soubor}`)) }} title="Zvětšit">⤢</button>
                </figure>
              )
            })}
          </div>
        </div>
      ))}

      {textura && (
        <>
          <h3>3 · Stránka do Infografik</h3>
          <div className="row">
            <input className="grow" value={titulek} onChange={(e) => setTitulek(e.target.value)} placeholder="Titulek stránky" />
            <select value={format} onChange={(e) => setFormat(e.target.value)}>
              {FORMATY.map((f) => <option key={f.id} value={f.id}>{f.label}</option>)}
            </select>
          </div>
          <p className="hint">Popisky k bodům modelu, prázdný se nevypíše; druhý řádek za Enter.</p>
          <div className="r3d-labels">
            {points.map((p) => (
              <label key={p}><span>{p}</span>
                <textarea rows={1} value={popisky[p] ?? ''} onChange={(e) => setPopisky({ ...popisky, [p]: e.target.value })} />
              </label>
            ))}
          </div>
          <div className="row">
            <button className="btn primary" disabled={busy === 'stranka'} onClick={makePage}>{busy === 'stranka' ? 'Skládám…' : 'Složit a vytvořit stránku · 0 USD'}</button>
            {docs.map((d) => <button key={d.id} className="btn" onClick={() => onDoc(d.id)}>Otevřít {d.size}</button>)}
          </div>
          {docs.length > 0 && <p className="hint">Hotovo: stránky jsou v záložce Infografiky, ruční úprava přes „Otevřít ve VectorCraftu“ u dokumentu.</p>}
          {docs.length > 0 && notes.map((n) => <p key={n} className="warn">! {n}</p>)}

          <h3>4 · Do řetězce infografiky</h3>
          <p className="hint">Tvor se stane vlastním obrazem tématu. Průvodce → infografika k tomu tématu ho dá do návrhů jako hlavní obraz a stránku složí z těchto vrstev, popisky napíše z faktů k bodům, které tu mají název (první řádek popisku).</p>
          <div className="row">
            <input value={qid} onChange={(e) => setQid(e.target.value)} placeholder="Wikidata, např. Q81214" style={{ width: '13em' }} />
            <input className="grow" value={nazev} onChange={(e) => setNazev(e.target.value)} placeholder="Co obraz ukazuje, např. Vorvaň s průhledem do trávicí trubice, potápěč v měřítku" />
            <button className="btn" disabled={busy === 'tema'} onClick={toTopic}>{busy === 'tema' ? 'Ukládám…' : 'Dát do řetězce · 0 USD'}</button>
          </div>
          <p className="hint">Body s názvem: {Object.values(names).join(', ') || 'zatím žádný'}</p>
          {tema && <p className="hint">Uloženo jako vlastní obraz „{tema}“ tématu {qid.trim()}.</p>}
        </>
      )}

      {zoom && (
        <div className="lightbox" onClick={() => setZoom(null)}>
          <img src={zoom} alt="" style={{ maxWidth: '94vw', maxHeight: '88vh' }} />
        </div>
      )}
    </div>
  )
}
