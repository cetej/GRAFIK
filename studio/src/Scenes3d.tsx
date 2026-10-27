import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  api, fileToB64, m3dApi, scenesApi,
  type Model3dVersion, type RefIn, type Scene3d, type SceneFigure, type SceneHint, type SceneObj,
} from './api.ts'
import SceneViewer3d, { type SceneItem, type SceneViewerHandle } from './SceneViewer3d.tsx'
import type { Cam3d } from './Viewer3d.tsx'

// 3D scény (zadání B) podle náčrtu schváleného 2026-10-27 (docs/spikes/img/2026-10-27-3d-sceny-nacrt.png):
// modely z knihovny, kvádr/válec a kontrolní postava 1,72 m rozmístěné v metrech, bílý snímek z kamery prohlížeče,
// předloha „tvar“ jen se zkontrolovanými modely a s větou o skutečných rozměrech.

const ASPECTS = ['16:10', '16:9', '3:2', '4:3', '1:1']
const NAMED = [
  { label: 'Zepředu', az: 270, el: 8 }, { label: 'Z boku', az: 0, el: 8 },
  { label: 'Šikmo', az: 305, el: 22 }, { label: 'Shora (půdorys)', az: 270, el: 89 },
]
const LENSES = [35, 50, 85]
const num = (x: number, d = 1) => x.toLocaleString('cs-CZ', { maximumFractionDigits: d })
const parse = (s: string) => +s.replace(',', '.').replace('−', '-')
const ratio = (a: string) => { const [w, h] = a.split(':').map(Number); return w / h }
const thumbOf = (m: Model3dVersion) => {
  const v = m.views['20']
  if (v) return m3dApi.file(m.id, m.version, `${v.dir}/az045.png`, 128)
  return m.legacy ? m3dApi.file(m.id, m.version, 'legacy-thumb.png', 128) : null
}
const sizeOf = (m: Model3dVersion): [number | null, string] => {
  const dims = m.stretch?.dims
  if (dims) return [Math.max(...dims), `natažení: ${m.stretch?.source || 'rozměry ze zdroje'}`]
  if (m.rozmer_m) return [m.rozmer_m, m.rozmer_zdroj || 'zadáno ručně']
  return [null, '']
}
const FIGURE_KEY = 'postava'
type Draft = { title: string; objects: SceneObj[]; postava: SceneFigure; aspect: string }
const EMPTY: Draft = { title: '', objects: [], postava: { misto: [0, 0], otoceni: 0, na: null }, aspect: '16:10' }

export default function Scenes3d({ onError, onToStudio, onModels }: {
  onError: (msg: string) => void
  onToStudio: (ref: RefIn & { name: string; preview: string; meta?: string }, hint: SceneHint) => void
  onModels: () => void
}) {
  const [scenes, setScenes] = useState<Scene3d[]>([])
  const [models, setModels] = useState<Model3dVersion[]>([])
  const [versions, setVersions] = useState<Record<string, Model3dVersion>>({}) // "id/v" -> version of a scene object
  const [cur, setCur] = useState<Scene3d | null>(null)                         // the saved version open
  const [draft, setDraft] = useState<Draft>(EMPTY)
  const [sel, setSel] = useState<string | null>(null)
  const [lens, setLens] = useState(50)
  const [cam, setCam] = useState<Cam3d | null>(null)
  const [withFigure, setWithFigure] = useState(false)
  const [busy, setBusy] = useState<'' | 'save' | 'render' | 'ref'>('')
  const [snap, setSnap] = useState<string | null>(null)
  const [zoom, setZoom] = useState(false)
  const [picker, setPicker] = useState(false)
  const viewer = useRef<SceneViewerHandle>(null)

  const load = useCallback(async () => {
    try {
      const [list, ms] = await Promise.all([scenesApi.list(), m3dApi.list()])
      setScenes(list)
      setModels(ms)
    } catch (e) { onError(String((e as Error).message)) }
  }, [onError])
  useEffect(() => { load() }, [load])

  // the model versions the draft uses (viewer copy, check, size)
  useEffect(() => {
    const need = [...new Set(draft.objects.filter((o) => o.model).map((o) => o.model!))]
    for (const id of need) {
      if (Object.keys(versions).some((k) => k.startsWith(`${id}/`))) continue
      m3dApi.get(id).then((m) => setVersions((vs) => ({ ...vs, ...Object.fromEntries(m.versions.map((v) => [`${v.id}/${v.version}`, v])) })))
        .catch((e) => onError(String(e.message)))
    }
  }, [draft.objects, versions, onError])

  const open = async (id: string, v?: string) => {
    try {
      const s = v ? await scenesApi.version(id, v) : await scenesApi.version(id, (await scenesApi.get(id)).versions.slice(-1)[0].version)
      setCur(s)
      setDraft({ title: s.title, objects: s.objects, postava: s.postava, aspect: s.aspect })
      setSel(null)
      setSnap(s.snaps.length ? s.snaps[s.snaps.length - 1].key : null)
      if (s.camera) { setLens(s.camera.lens); setTimeout(() => viewer.current?.setCamera(s.camera as Cam3d), 0) }
    } catch (e) { onError(String((e as Error).message)) }
  }
  useEffect(() => { if (!cur && scenes.length) open(scenes[0].id) }, [scenes]) // eslint-disable-line react-hooks/exhaustive-deps
  const newScene = () => { setCur(null); setDraft({ ...EMPTY, title: 'Nová scéna' }); setSel(null); setSnap(null) }

  const dirty = !cur || JSON.stringify({ t: cur.title, o: cur.objects, p: cur.postava, a: cur.aspect })
    !== JSON.stringify({ t: draft.title, o: draft.objects, p: draft.postava, a: draft.aspect })
  const setObj = (id: string, patch: Partial<SceneObj>) => setDraft((d) => ({ ...d, objects: d.objects.map((o) => (o.id === id ? { ...o, ...patch } : o)) }))
  const nextId = (base: string) => {
    let id = base, i = 2
    while (draft.objects.some((o) => o.id === id) || id === FIGURE_KEY) id = `${base}-${i++}`
    return id
  }
  const freeSpot = (): [number, number] => {
    // to the right of what is there, so a new object does not land inside another one
    const xs = draft.objects.map((o) => o.misto[0] + (o.rozmer ?? Math.max(...(o.rozmery.length ? o.rozmery : [1]))) / 2)
    return [xs.length ? Math.round(Math.max(...xs) + 2) : 0, 0]
  }
  const addModel = (m: Model3dVersion) => {
    setPicker(false)
    const [rozmer, zdroj] = sizeOf(m)
    const id = nextId(m.id)
    setVersions((vs) => ({ ...vs, [`${m.id}/${m.version}`]: m }))
    setDraft((d) => ({ ...d, objects: [...d.objects, { id, model: m.id, model_version: m.version, tvar: null, rozmery: [], nazev: m.title.replace(/\s*\([^)]*\)\s*$/, ''),
      misto: freeSpot(), otoceni: 0, rozmer, rozmer_zdroj: zdroj, na: null }] }))
    setSel(id)
  }
  const addShape = (tvar: 'kvadr' | 'valec') => {
    const id = nextId(tvar === 'kvadr' ? 'kvadr' : 'valec')
    setDraft((d) => ({ ...d, objects: [...d.objects, { id, model: null, model_version: null, tvar, rozmery: tvar === 'kvadr' ? [10, 4, 1] : [2, 3],
      nazev: tvar === 'kvadr' ? 'Kvádr' : 'Válec', misto: freeSpot(), otoceni: 0, rozmer: null, rozmer_zdroj: '', na: null }] }))
    setSel(id)
  }
  const remove = (id: string) => {
    setDraft((d) => ({ ...d, objects: d.objects.filter((o) => o.id !== id).map((o) => (o.na === id ? { ...o, na: null } : o)),
      postava: d.postava.na === id ? { ...d.postava, na: null } : d.postava }))
    setSel(null)
  }

  const items: SceneItem[] = useMemo(() => {
    const out: SceneItem[] = draft.objects.map((o): SceneItem => {
      const v = o.model ? versions[`${o.model}/${o.model_version}`] : null
      return o.model
        ? { key: o.id, ...(v?.viewer ? m3dApi.viewerGlb(v.id, v.version, v.viewer) : {}), rozmer: o.rozmer ?? 1, misto: o.misto, otoceni: o.otoceni, na: o.na }
        : { key: o.id, shape: o.tvar!, box: o.rozmery, misto: o.misto, otoceni: o.otoceni, na: o.na }
    }).filter((it) => it.url || it.box)
    out.push({ key: FIGURE_KEY, url: scenesApi.figureGlb, rozmer: 1.72, misto: draft.postava.misto, otoceni: draft.postava.otoceni, na: draft.postava.na, figure: true })
    return out
  }, [draft, versions])

  // what stands on an object (`na`, also in a chain) moves and turns with it, as on KLAPKA's anchors
  const carry = (d: Draft, key: string, f: (m: [number, number]) => [number, number], turnBy = 0): Draft => {
    const riders = new Set<string>([key])
    let grew = true
    while (grew) {
      grew = false
      for (const o of d.objects) if (o.na && riders.has(o.na) && !riders.has(o.id)) { riders.add(o.id); grew = true }
    }
    riders.delete(key)
    const spin = (o: number) => (o + turnBy + 360) % 360
    return {
      ...d,
      objects: d.objects.map((o) => (riders.has(o.id) ? { ...o, misto: f(o.misto), otoceni: spin(o.otoceni) } : o)),
      postava: d.postava.na && (riders.has(d.postava.na) || d.postava.na === key)
        ? { ...d.postava, misto: f(d.postava.misto), otoceni: spin(d.postava.otoceni) } : d.postava,
    }
  }
  const move = (key: string, misto: [number, number]) => setDraft((d) => {
    if (key === FIGURE_KEY) return { ...d, postava: { ...d.postava, misto } }
    const o = d.objects.find((x) => x.id === key)!
    const dx = misto[0] - o.misto[0], dy = misto[1] - o.misto[1]
    const moved = carry(d, key, (m) => [+(m[0] + dx).toFixed(2), +(m[1] + dy).toFixed(2)])
    return { ...moved, objects: moved.objects.map((x) => (x.id === key ? { ...x, misto } : x)) }
  })
  const turn = (key: string, delta: number) => setDraft((d) => {
    if (key === FIGURE_KEY) return { ...d, postava: { ...d.postava, otoceni: (d.postava.otoceni + delta + 360) % 360 } }
    const o = d.objects.find((x) => x.id === key)!
    const [cx, cy] = o.misto, a = (delta * Math.PI) / 180
    const turned = carry(d, key, ([x, y]) => [+(cx + (x - cx) * Math.cos(a) - (y - cy) * Math.sin(a)).toFixed(2),
      +(cy + (x - cx) * Math.sin(a) + (y - cy) * Math.cos(a)).toFixed(2)], delta)
    return { ...turned, objects: turned.objects.map((x) => (x.id === key ? { ...x, otoceni: (x.otoceni + delta + 360) % 360 } : x)) }
  })

  const save = async (): Promise<Scene3d | null> => {
    setBusy('save')
    try {
      const c = viewer.current?.camera()
      const s = await scenesApi.save({ scene_id: cur?.id ?? null, title: draft.title || 'Scéna', objects: draft.objects, postava: draft.postava, aspect: draft.aspect, camera: c })
      setCur(s)
      setDraft({ title: s.title, objects: s.objects, postava: s.postava, aspect: s.aspect })
      load()
      return s
    } catch (e) { onError(String((e as Error).message)); return null } finally { setBusy('') }
  }
  const waitJob = async (id: string) => {
    for (;;) {
      const j = await api.job(id)
      if (j.status === 'failed' || j.status === 'cancelled') throw new Error(j.error ?? 'render scény selhal')
      if (j.status === 'done') return
      await new Promise((ok) => setTimeout(ok, 1000))
    }
  }
  const render = async () => {
    const s = dirty ? await save() : cur
    const c = viewer.current?.camera()
    if (!s || !c) return
    setBusy('render')
    try {
      scenesApi.camera(s.id, s.version, c).catch(() => {})   // reopen the scene where it was rendered from
      const r = await scenesApi.render(s.id, s.version, c, draft.aspect, withFigure)
      if (r.job_id) await waitJob(r.job_id)
      setCur(await scenesApi.version(s.id, s.version))
      setSnap(r.key)
      load()
    } catch (e) { onError(String((e as Error).message)) } finally { setBusy('') }
  }
  const toStudio = async () => {
    if (!cur || !snap) return
    setBusy('ref')
    try {
      const ref = await scenesApi.asRef(cur.id, cur.version, snap)
      const url = scenesApi.file(cur.id, cur.version, ref.file)
      const b64 = await fileToB64(await (await fetch(url)).blob())
      onToStudio({ b64, role: 'geometry', source: ref.source, license: ref.license, name: `${cur.title} ${cur.version}`, preview: url, meta: `3D scéna ${cur.version}` }, ref.hint)
    } catch (e) { onError(String((e as Error).message)) } finally { setBusy('') }
  }

  const selObj = draft.objects.find((o) => o.id === sel) ?? null
  const missing = draft.objects.filter((o) => o.model && !o.rozmer)
  const unchecked = draft.objects.filter((o) => o.model && !versions[`${o.model}/${o.model_version}`]?.review)
  const snapInfo = cur?.snaps.find((x) => x.key === snap)
  const snapUrl = cur && snapInfo ? scenesApi.file(cur.id, cur.version, snapInfo.file) : null
  const hint = cur?.hint && !dirty ? (snapInfo?.postava ? `malá stojící postava v předloze je člověk 1,72 m, nech ho přesně tam a tak velkého; ${cur.hint.cs}` : cur.hint.cs) : null
  const others = (id: string | null) => draft.objects.filter((o) => o.id !== id && draft.objects.indexOf(o) < (id ? draft.objects.findIndex((x) => x.id === id) : draft.objects.length))

  return (
    <main className="m3d">
      <aside className="card">
        <div className="seg full"><button onClick={onModels}>Modely</button><button className="on">Scény</button></div>
        <h3>3D scény</h3>
        <div className="m3d-list">
          {scenes.map((s) => (
            <button key={s.id} className={`node ${s.id === cur?.id ? 'cur' : ''}`} onClick={() => open(s.id)}>
              {s.snaps.length ? <img src={scenesApi.file(s.id, s.version, s.snaps[s.snaps.length - 1].file)} alt="" /> : <span className="ph">—</span>}
              <span>{s.title} · {s.version}<small>{s.objects.length} {s.objects.length === 1 ? 'objekt' : s.objects.length < 5 ? 'objekty' : 'objektů'} · {s.snaps.length ? 'bílý snímek hotový' : 'bez snímku'}</small></span>
            </button>
          ))}
          {!scenes.length && <p className="hint">Zatím žádná scéna.</p>}
        </div>
        <button className="btn small" onClick={newScene}>+ Nová scéna</button>

        <h3>Ve scéně</h3>
        <input className="title-in" value={draft.title} placeholder="Název scény (např. Loď u mola)" onChange={(e) => setDraft((d) => ({ ...d, title: e.target.value }))} />
        <div className="m3d-list sc-objs">
          {draft.objects.map((o) => {
            const v = o.model ? versions[`${o.model}/${o.model_version}`] : null
            return (
              <button key={o.id} className={`node ${o.id === sel ? 'cur' : ''}`} onClick={() => setSel(o.id)}>
                {v && thumbOf(v) ? <img src={thumbOf(v)!} alt="" /> : <span className="ph">{o.tvar === 'valec' ? '◯' : o.tvar ? '▭' : '—'}</span>}
                <span>
                  <b>{o.nazev}</b>{o.model_version ? ` · ${o.model_version}` : ''}
                  <small>
                    {o.model ? (o.rozmer ? `nejdelší strana ${num(o.rozmer, 2)} m` : 'chybí rozměr') : o.rozmery.map((x) => num(x, 2)).join(' × ') + ' m'}
                    {o.na ? ` · na ${draft.objects.find((x) => x.id === o.na)?.nazev ?? o.na}` : ''}
                  </small>
                  {o.model && <span className={`tag ${o.rozmer ? '' : 'paid'}`} title={o.rozmer_zdroj}>{!o.rozmer ? 'doplňte rozměr' : o.rozmer_zdroj && !o.rozmer_zdroj.startsWith('zadáno ručně') ? 'rozměr se zdrojem' : 'zadáno ručně'}</span>}
                  {o.model && <span className={`tag ${v?.review ? 'ok' : 'ai'}`}>{v?.review ? 'zkontrolováno' : 'čeká na kontrolu'}</span>}
                  {!o.model && <span className="tag">jednoduchý tvar</span>}
                </span>
              </button>
            )
          })}
          <button className={`node ${sel === FIGURE_KEY ? 'cur' : ''}`} onClick={() => setSel(FIGURE_KEY)}>
            <span className="ph fig">1,72</span>
            <span><b>Kontrolní postava</b><small>1,72 m · vždy ve scéně</small><span className="tag">měřítko</span></span>
          </button>
        </div>
        <div className="row">
          <button className="btn small" onClick={() => setPicker(true)}>+ Model z knihovny</button>
          <button className="btn small" onClick={() => addShape('kvadr')}>+ Kvádr</button>
          <button className="btn small" onClick={() => addShape('valec')}>+ Válec</button>
        </div>
        <p className="hint">Rozměr se předvyplní z natažení nebo z dřívější scény. Model bez rozměrů ze zdroje chce jedno číslo: nejdelší stranu v metrech. Tvar se nedeformuje.</p>
      </aside>

      <section className="card m3d-views">
        <h3>{draft.title || 'Nová scéna'}{cur ? ` · ${cur.version}` : ''} · rozmístění (jen tvar, barvy dodá generátor){dirty ? ' · neuloženo' : ''}</h3>
        <div className="row m3d-viewbar">
          <div className="seg">{NAMED.map((n) => <button key={n.label} onClick={() => viewer.current?.view(n.az, n.el)}>{n.label}</button>)}</div>
          <span className="grow" />
          <span className="hint">Ohnisko</span>
          <div className="seg">{LENSES.map((l) => <button key={l} className={lens === l ? 'on' : ''} onClick={() => setLens(l)}>{l} mm</button>)}</div>
        </div>
        <div className="viewer-wrap">
          <SceneViewer3d ref={viewer} items={items} selected={sel} aspect={ratio(draft.aspect)} lens={lens}
            onSelect={setSel} onMove={move} onTurn={turn} onCamera={setCam} onError={onError} />
          {cam && <span className="readout">azimut {num(cam.azimuth, 0)}° · výška {num(cam.elevation, 0)}° · vzdálenost {num(cam.distance, 0)} m · ohnisko {lens} mm · mřížka 1 m, silné čáry po 10 m</span>}
          <span className="vctl">
            <button className="btn small" onClick={() => viewer.current?.zoom(1.15)} title="Oddálit">−</button>
            <button className="btn small" onClick={() => viewer.current?.zoom(1 / 1.15)} title="Přiblížit">+</button>
            <button className="btn small" onClick={() => viewer.current?.fit()}>Celá scéna</button>
          </span>
        </div>
        {sel === FIGURE_KEY ? (
          <div className="sc-form">
            <b>Vybráno: kontrolní postava 1,72 m</b>
            <Num label="X (m)" value={draft.postava.misto[0]} onChange={(x) => move(FIGURE_KEY, [x, draft.postava.misto[1]])} />
            <Num label="Y (m)" value={draft.postava.misto[1]} onChange={(y) => move(FIGURE_KEY, [draft.postava.misto[0], y])} />
            <Num label="Otočení (°)" value={draft.postava.otoceni} onChange={(r) => setDraft((d) => ({ ...d, postava: { ...d.postava, otoceni: r } }))} />
            <label className="dim">stojí na<select value={draft.postava.na ?? ''} onChange={(e) => setDraft((d) => ({ ...d, postava: { ...d.postava, na: e.target.value || null } }))}>
              <option value="">na zemi</option>{draft.objects.map((o) => <option key={o.id} value={o.id}>{o.nazev}</option>)}</select></label>
          </div>
        ) : selObj ? (
          <div className="sc-form">
            <b>Vybráno: {selObj.nazev}</b>
            <Num label="X (m)" value={selObj.misto[0]} onChange={(x) => move(selObj.id, [x, selObj.misto[1]])} />
            <Num label="Y (m)" value={selObj.misto[1]} onChange={(y) => move(selObj.id, [selObj.misto[0], y])} />
            <Num label="Otočení (°)" value={selObj.otoceni} onChange={(r) => turn(selObj.id, r - selObj.otoceni)} />
            {selObj.model ? (
              <>
                <Num label="Nejdelší strana (m)" value={selObj.rozmer} positive onChange={(r) => setObj(selObj.id, { rozmer: r, rozmer_zdroj: selObj.rozmer_zdroj.startsWith('natažení') ? '' : selObj.rozmer_zdroj })} />
                <label className="dim wide">zdroj rozměru<input value={selObj.rozmer_zdroj} placeholder="např. Wikipedie: Quinquereme" onChange={(e) => setObj(selObj.id, { rozmer_zdroj: e.target.value })} /></label>
              </>
            ) : (
              <>
                <label className="dim">název<input value={selObj.nazev} onChange={(e) => setObj(selObj.id, { nazev: e.target.value })} /></label>
                {(selObj.tvar === 'kvadr' ? ['délka (m)', 'šířka (m)', 'výška (m)'] : ['průměr (m)', 'výška (m)']).map((l, i) => (
                  <Num key={l} label={l} value={selObj.rozmery[i]} positive onChange={(x) => setObj(selObj.id, { rozmery: selObj.rozmery.map((r, j) => (j === i ? x : r)) })} />
                ))}
              </>
            )}
            <label className="dim">stojí na<select value={selObj.na ?? ''} onChange={(e) => setObj(selObj.id, { na: e.target.value || null })}>
              <option value="">na zemi</option>{others(selObj.id).map((o) => <option key={o.id} value={o.id}>{o.nazev}</option>)}</select></label>
            <button className="btn small" onClick={() => remove(selObj.id)}>Odebrat ze scény</button>
          </div>
        ) : <p className="hint sc-form">Klepněte na objekt v pohledu nebo v seznamu: pak jde posunout tažením, otočit Q / E a upravit čísly.</p>}
      </section>

      <aside className="card">
        <h3>Bílý snímek scény</h3>
        <span className="hint">Formát snímku</span>
        <div className="seg full">{ASPECTS.map((a) => <button key={a} className={draft.aspect === a ? 'on' : ''} onClick={() => setDraft((d) => ({ ...d, aspect: a }))}>{a}</button>)}</div>
        <button className="btn primary" disabled={!!busy || !draft.objects.length || missing.length > 0} onClick={render}>
          {busy === 'render' ? 'Renderuji bílý snímek…' : busy === 'save' ? 'Ukládám scénu…' : 'Vyrenderovat bílý snímek · 0 USD · ~10–60 s'}
        </button>
        <p className="hint">{missing.length ? `Nejdřív doplňte rozměr: ${missing.map((o) => o.nazev).join(', ')}.`
          : !draft.objects.length ? 'Přidejte do scény aspoň jeden model.'
            : 'Blender na procesoru (FLUX zůstane načtený), kamera = pohled vlevo, rámeček = snímek, bez podlahy a stínů.'}</p>
        {dirty && draft.objects.length > 0 && <button className="btn small" disabled={!!busy} onClick={save}>Uložit scénu jako novou verzi</button>}
        {snapUrl && snapInfo && (
          <div className="lastref">
            <img src={snapUrl} alt="" onClick={() => setZoom(true)} title="Zvětšit" />
            <button className="zoom-btn" onClick={() => setZoom(true)} title="Zvětšit">⤢</button>
            <p className="hint">{cur!.version} · {snapInfo.rendered.slice(11, 16)} · {num(snapInfo.seconds, 0)} s · {snapInfo.aspect}{snapInfo.postava ? ' · s postavou' : ''}</p>
          </div>
        )}
        <label className="sc-check"><input type="checkbox" checked={withFigure} onChange={(e) => setWithFigure(e.target.checked)} /><span>Kontrolní postava i ve snímku pro FLUX</span></label>
        <p className="hint">Postava pomůže jen v bližším záběru, kde je ve snímku vidět (asi 40 px a víc); v širokém záběru z ní FLUX udělá sloupek. Věta v zadání ji pak výslovně jmenuje.</p>
        {hint && <div className="sc-hint"><b>Do zadání se doplní:</b> „{hint}“</div>}
        <button className="btn primary" disabled={!!busy || !snapUrl || dirty || unchecked.length > 0} onClick={toStudio}>
          {busy === 'ref' ? 'Posílám do Studia…' : 'Použít jako předlohu „tvar“ · 0 USD'}
        </button>
        <p className="hint">{unchecked.length ? <>Až budou všechny modely zkontrolované. Chybí: <b>{unchecked.map((o) => o.nazev).join(', ')}</b> (zkontrolujte v Modelech).</>
          : !snapUrl ? 'Nejdřív vyrenderujte bílý snímek.' : dirty ? 'Scéna se od snímku změnila: vyrenderujte ho znovu.'
            : 'Snímek půjde do Studia jako předloha „tvar“ a věta o rozměrech do zadání.'}</p>
        {snapUrl && <a className="btn small" href={snapUrl} download>Stáhnout PNG</a>}
      </aside>

      {picker && (
        <div className="modal" onClick={() => setPicker(false)}>
          <div className="dialog" onClick={(e) => e.stopPropagation()}>
            <h2>Model z knihovny 3D</h2>
            <p className="hint">Do scény jde model, který už má kopii pro prohlížeč. Předlohou pro FLUX bude až po kontrole.</p>
            <div className="m3d-list sc-picker">
              {models.map((m) => (
                <button key={m.id} className="node" disabled={!m.viewer} onClick={() => addModel(m)}>
                  {thumbOf(m) ? <img src={thumbOf(m)!} alt="" /> : <span className="ph">—</span>}
                  <span>{m.title} · {m.version}<small>{m.review ? 'zkontrolováno' : 'čeká na kontrolu'}{sizeOf(m)[0] ? ` · ${num(sizeOf(m)[0]!, 2)} m` : ' · bez rozměru'}{m.viewer ? '' : ' · nejdřív otevřete v Modelech (připraví se prohlížeč)'}</small></span>
                </button>
              ))}
            </div>
            <div className="row end"><button className="btn" onClick={() => setPicker(false)}>Zavřít</button></div>
          </div>
        </div>
      )}
      {zoom && snapUrl && (
        <div className="lightbox" onClick={() => setZoom(false)}>
          <div className="lb-bar" onClick={(e) => e.stopPropagation()}><button className="btn small" onClick={() => setZoom(false)}>Zavřít (Esc)</button></div>
          <div className="lb-img fit m3d-zoom" onClick={(e) => e.stopPropagation()}><img src={snapUrl} alt="" /></div>
        </div>
      )}
    </main>
  )
}

/** A number field that accepts a decimal comma and keeps what is typed until it parses. */
function Num({ label, value, onChange, positive }: { label: string; value: number | null; onChange: (v: number) => void; positive?: boolean }) {
  const [text, setText] = useState(value === null ? '' : num(value, 3))
  useEffect(() => { if (value === null ? text !== '' : parse(text) !== value) setText(value === null ? '' : num(value, 3)) }, [value]) // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <label className="dim">{label}
      <input value={text} inputMode="decimal" className={text && !Number.isFinite(parse(text)) ? 'bad' : ''} onChange={(e) => {
        setText(e.target.value)
        const v = parse(e.target.value)
        if (Number.isFinite(v) && e.target.value.trim() !== '' && (!positive || v > 0)) onChange(v)
      }} />
    </label>
  )
}
