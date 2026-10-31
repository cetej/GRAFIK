import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  api, fileToB64, groupStyles, imageUrl, STYLE_CATEGORIES, stylesApi,
  type ImageRequest, type PaletteColor, type RefMeta, type StyleCard, type StyleFields, type StyleImages,
} from './api.ts'
import RefPicker from './RefPicker.tsx'

// G4 — záložka Styly podle náčrtu schváleného 2026-10-23 (docs/spikes/img/g4-nacrt-1.png, -2.png).

const TRY_PROMPT = 'A lighthouse on a rocky coast'
const FIELDS: { key: keyof StyleFields; label: string; area?: boolean; hint?: string }[] = [
  { key: 'medium', label: 'Médium a technika', area: true },
  { key: 'light', label: 'Světlo' },
  { key: 'line', label: 'Linka a povrch' },
  { key: 'composition', label: 'Kompozice' },
  { key: 'avoid', label: 'Vyhnout se' },
  { key: 'signature', label: 'Podpisové znaky (podle nich se hodnotí výsledek)', area: true, hint: 'do promptu nejdou' },
]
const ORIGIN: Record<string, { label: string; cls: string }> = {
  default: { label: 'výchozí', cls: 'ok' }, detected: { label: 'z obrázků · Claude', cls: 'paid' }, manual: { label: 'ruční', cls: '' },
}
const EMPTY: StyleFields = { label: '', kategorie: '', note: '', medium: '', light: '', line: '', composition: '', avoid: '', signature: '', palette: [] }

/** Pending image: uploaded file, reference library item or studio image. */
export interface PendingImage { b64?: string; ref_id?: string; job?: string; preview: string }

const toImages = (imgs: PendingImage[]): StyleImages => ({
  b64: imgs.filter((i) => i.b64).map((i) => i.b64!),
  ref_ids: imgs.filter((i) => i.ref_id).map((i) => i.ref_id!),
  jobs: imgs.filter((i) => i.job).map((i) => i.job!),
})

// Mirror of ngm_shared.knihovna.image_text() for the editor's fields (a card with no `look` or film part),
// for the preview of an unsaved card.
export function promptText(f: StyleFields): string {
  const parts = (['medium', 'light', 'line', 'composition'] as const).map((k) => f[k].trim().replace(/\.$/, '')).filter(Boolean)
  if (f.palette.length) parts.push('colour palette: ' + f.palette.map((c) => `${c.name ?? ''} ${c.hex}`.trim()).join(', '))
  if (f.avoid.trim()) parts.push('avoid ' + f.avoid.trim().replace(/\.$/, ''))
  return parts.map((p) => p[0].toUpperCase() + p.slice(1)).join('. ')
}

export function Swatches({ palette, small }: { palette: PaletteColor[]; small?: boolean }) {
  return (
    <span className={`swatches ${small ? 'small' : ''}`}>
      {palette.map((c) => <span key={c.hex} className="sw" style={{ background: c.hex }} title={`${c.name ?? ''} ${c.hex}`} />)}
    </span>
  )
}

export default function Styles({ onError, onOpen, onSubmit, selectedImage, openDetect, onDetectOpen, onDetectClosed, onUse }: {
  onError: (msg: string) => void
  onOpen: (src: string) => void
  onDetectOpen: () => void
  onSubmit: (req: ImageRequest) => Promise<string | null>
  selectedImage: string | null
  openDetect: boolean
  onDetectClosed: () => void
  onUse: (slug: string) => void
}) {
  const [cards, setCards] = useState<StyleCard[]>([])
  const [q, setQ] = useState('')
  const [cat, setCat] = useState<string | null>(null) // null = all categories, '' = without a category
  const [slug, setSlug] = useState<string | null>(null) // null = new card
  const [draft, setDraft] = useState<StyleFields>(EMPTY)
  const [pending, setPending] = useState<PendingImage[]>([]) // samples of a card not saved yet
  const [dirty, setDirty] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)
  const [tryJob, setTryJob] = useState<{ slug: string; job: string } | null>(null)

  /** Reload the library and open `select` (or the first card). */
  const load = useCallback(async (select: string) => {
    try {
      const list = await stylesApi.list()
      setCards(list)
      const pick = list.find((c) => c.slug === select) ?? list[0]
      setSlug(pick?.slug ?? null); setDraft(pick ?? EMPTY); setDirty(false); setPending([])
    } catch (e) { onError((e as Error).message) }
  }, [onError])
  useEffect(() => { load('') }, [load])

  const card = cards.find((c) => c.slug === slug) ?? null
  const shown = useMemo(() => cards.filter((c) => (c.label + ' ' + c.note).toLowerCase().includes(q.toLowerCase())), [cards, q])
  const groups = useMemo(() => groupStyles(shown), [shown])
  const set = (patch: Partial<StyleFields>) => { setDraft((d) => ({ ...d, ...patch })); setDirty(true) }

  const open = (c: StyleCard) => {
    if (dirty && !confirm('Karta má neuložené změny. Zahodit je?')) return
    setSlug(c.slug); setDraft(c); setDirty(false); setPending([])
  }
  const newCard = (fields: StyleFields = EMPTY, samples: PendingImage[] = []) => {
    if (dirty && !confirm('Karta má neuložené změny. Zahodit je?')) return
    setSlug(null); setDraft(fields); setPending(samples); setDirty(true)
  }

  const save = async () => {
    setBusy('save')
    try {
      let saved: StyleCard
      if (slug) saved = await stylesApi.save(slug, draft)
      else {
        saved = await stylesApi.create(draft)
        for (const p of pending) {
          const b64 = p.b64 ?? (p.ref_id ? await fileToB64(await (await fetch(p.preview)).blob()) : undefined)
          saved = await stylesApi.addSample(saved.slug, p.job ? { job: p.job } : { b64 })
        }
      }
      setDirty(false); setPending([])
      await load(saved.slug)
    } catch (e) { onError((e as Error).message) } finally { setBusy(null) }
  }

  const remove = async () => {
    if (!slug || !confirm(`Přesunout styl „${draft.label}“ do koše sdílené knihovny (KNIHOVNA/.trash)? Zmizí i z KLAPKY.`)) return
    try { await stylesApi.remove(slug); setSlug(null); setDraft(EMPTY); setDirty(false); await load('') } catch (e) { onError((e as Error).message) }
  }

  const addSampleFiles = async (files: FileList | null) => {
    for (const f of [...(files ?? [])].filter((x) => x.type.startsWith('image/'))) {
      const b64 = await fileToB64(f)
      if (slug) {
        try { const c = await stylesApi.addSample(slug, { b64 }); setCards((cs) => cs.map((x) => (x.slug === c.slug ? c : x))) } catch (e) { onError((e as Error).message) }
      } else setPending((p) => [...p, { b64, preview: URL.createObjectURL(f) }].slice(0, 5))
    }
  }
  const removeSample = async (name: string) => {
    if (!slug) return
    try { const c = await stylesApi.removeSample(slug, name); setCards((cs) => cs.map((x) => (x.slug === c.slug ? c : x))) } catch (e) { onError((e as Error).message) }
  }

  const sampleImages = async (): Promise<StyleImages> => {
    if (!card) return toImages(pending)
    const b64 = await Promise.all(card.sample_urls.map(async (u) => fileToB64(await (await fetch(u)).blob())))
    return { b64 }
  }
  const remeasure = async () => {
    setBusy('palette')
    try {
      const imgs = await sampleImages()
      if (!(imgs.b64?.length || imgs.ref_ids?.length || imgs.jobs?.length)) { onError('Karta nemá vzory, není z čeho měřit.'); return }
      set({ palette: (await stylesApi.palette(imgs)).palette.map(({ hex, name }) => ({ hex, name })) })
    } catch (e) { onError((e as Error).message) } finally { setBusy(null) }
  }

  // "Vyzkoušet": one local image with this style, saved as the card's sample when done.
  const tryStyle = async () => {
    if (!slug) return
    const job = await onSubmit({ prompt: TRY_PROMPT, style: slug, style_id: slug, size: '1024x1024', n: 1, caller: `styl:${slug}` })
    if (job) setTryJob({ slug, job })
  }
  useEffect(() => {
    if (!tryJob) return
    const t = setInterval(async () => {
      try {
        const j = await api.job(tryJob.job)
        if (j.status === 'done') {
          const c = await stylesApi.addSample(tryJob.slug, { job: `${tryJob.job}/0` })
          setCards((cs) => cs.map((x) => (x.slug === c.slug ? c : x)))
          setTryJob(null)
        } else if (j.status === 'failed' || j.status === 'cancelled') { onError(`Zkouška stylu selhala: ${j.error ?? j.status}`); setTryJob(null) }
      } catch (e) { onError((e as Error).message); setTryJob(null) }
    }, 2000)
    return () => clearInterval(t)
  }, [tryJob, onError])

  const samples = card ? card.sample_urls.map((u, i) => ({ url: u, name: card.samples[i] })) : pending.map((p) => ({ url: p.preview, name: '' }))
  // A film card from KLAPKA has its words in `look`, lens and grade, not in the fields of this editor.
  const preview = !dirty && card ? card.prompt : promptText(draft) || card?.prompt
  const empty = !['medium', 'light', 'line', 'composition'].some((k) => (draft[k as keyof StyleFields] as string).trim()) && !draft.palette.length && !card?.prompt

  return (
    <main className="styles">
      <section className="card">
        <div className="row between">
          <h3 className="inline">Knihovna stylů · {cards.length}</h3>
          <div className="row tight">
            <button className="btn go" onClick={onDetectOpen}>+ Styl z obrázků</button>
            <button className="btn" onClick={() => newCard({ ...EMPTY, kategorie: cat ?? '' })}>+ Ručně</button>
          </div>
        </div>
        <input className="search full" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Hledat styl…" aria-label="Hledat styl" />
        <div className="seg wrap style-cats" role="group" aria-label="Kategorie stylů">
          <button className={cat === null ? 'on' : ''} onClick={() => setCat(null)}>Vše · {shown.length}</button>
          {groups.map((g) => (
            <button key={g.key} className={cat === g.key ? 'on' : ''} onClick={() => setCat(g.key)}>{g.label} · {g.cards.length}</button>
          ))}
        </div>
        {groups.filter((g) => cat === null || g.key === cat).map((g) => (
          <div key={g.key}>
            <h4 className="style-group">{g.label}</h4>
            <div className="style-grid">
              {g.cards.map((c) => (
                <button key={c.slug} className={`style-item ${c.slug === slug ? 'sel' : ''}`} title={c.note} onClick={() => open(c)}>
                  {c.sample_urls[0] ? <img src={c.sample_urls[0]} alt="" loading="lazy" /> : <span className="ph" style={{ background: grad(c.palette) }}>bez ukázky</span>}
                  <b>{c.label}</b>
                  <Swatches palette={c.palette} small />
                  <span className={`tag ${ORIGIN[c.origin ?? 'manual'].cls}`}>{ORIGIN[c.origin ?? 'manual'].label}</span>
                </button>
              ))}
            </div>
          </div>
        ))}
        {!groups.some((g) => cat === null || g.key === cat) && <p className="hint">{cards.length ? 'Nic nenalezeno.' : 'Knihovna je prázdná. Založte styl z obrázků nebo ručně.'}</p>}
        <p className="hint">Knihovna je sdílená: ostatní projekty ji čtou přes <code>GET /api/v2/styles</code> a v zadání pošlou jen název stylu (<code>style: "{cards[0]?.slug ?? 'akvarel-prirodovedny'}"</code>).</p>
      </section>

      <section className="card style-editor">
        <div>
          <h3>Vzory (2–5)</h3>
          <div className="samples">
            {samples.map((s, i) => (
              <div key={s.url} className={`sample ${i === 0 ? 'big' : ''}`}>
                <button className="sample-open" title="Zvětšit" aria-label="Zvětšit vzor" onClick={() => onOpen(s.url)}><img src={s.url} alt="" /></button>
                {slug && <button className="x" title="Odebrat vzor" aria-label="Odebrat vzor" onClick={() => removeSample(s.name)}>×</button>}
              </div>
            ))}
            {samples.length < 5 && (
              <label className="btn small">+ vzor<input type="file" accept="image/*" multiple hidden onChange={(e) => { addSampleFiles(e.target.files); e.target.value = '' }} /></label>
            )}
          </div>
          <p className="hint">Vzory slouží jen k ukázce a k detekci. Do generátoru se styl posílá vždy slovy (FLUX přenos stylu obrázkem neumí).</p>

          <h3>Paleta · změřená z vzorů</h3>
          <div className="row">
            {draft.palette.map((c, i) => (
              <span key={i} className="swedit">
                <input type="color" value={c.hex} aria-label={`Barva ${c.name ?? c.hex}`} title="Klik = upravit barvu"
                  onChange={(e) => set({ palette: draft.palette.map((x, j) => (j === i ? { hex: e.target.value } : x)) })} />
                <button className="x" title="Odebrat barvu" aria-label="Odebrat barvu" onClick={() => set({ palette: draft.palette.filter((_, j) => j !== i) })}>×</button>
              </span>
            ))}
            <button className="btn small" disabled={busy === 'palette' || !samples.length} onClick={remeasure}
              title={samples.length ? '' : 'Nejdřív přidejte vzor'}>{busy === 'palette' ? 'Měřím…' : 'změřit znovu'}</button>
          </div>
          <p className="hint">{draft.palette.map((c) => c.hex).join(' ') || 'Bez palety.'} · klik na barvu = upravit</p>

          <h3>Ověření</h3>
          <button className="btn" disabled={!slug || dirty || !!tryJob} onClick={tryStyle}>
            {tryJob ? 'Generuji ukázku…' : 'Vyzkoušet na vzorovém zadání · zdarma'}
          </button>
          <p className="hint">{!slug || dirty ? 'Nejdřív kartu uložte. ' : ''}Vygeneruje lokálně jeden obrázek s tímto stylem („{TRY_PROMPT}“) a uloží ho jako ukázku karty.</p>
        </div>

        <div>
          <div className="row between">
            <h3 className="inline">Karta stylu{dirty ? ' · neuloženo' : ''}</h3>
            {slug && <span className="tag">KNIHOVNA/styles/{slug}.yaml · sdílí GRAFIK i KLAPKA</span>}
          </div>
          <label className="field">Název<input value={draft.label} onChange={(e) => set({ label: e.target.value })} disabled={!!slug} title={slug ? 'Název určuje složku stylu, mění se duplikováním' : ''} /></label>
          <label className="field">Kategorie
            <select value={draft.kategorie ?? ''} onChange={(e) => set({ kategorie: e.target.value })}>
              <option value="">bez kategorie</option>
              {STYLE_CATEGORIES.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
            </select>
          </label>
          <label className="field">Podstata (k čemu se hodí)<input value={draft.note} onChange={(e) => set({ note: e.target.value })} /></label>
          {FIELDS.map((f) => (
            <label key={f.key} className="field">{f.label}{f.hint && <span className="hint"> · {f.hint}</span>}
              {f.area
                ? <textarea value={draft[f.key] as string} onChange={(e) => set({ [f.key]: e.target.value })} />
                : <input value={draft[f.key] as string} onChange={(e) => set({ [f.key]: e.target.value })} />}
            </label>
          ))}
          <h3>Takhle půjde do promptu</h3>
          <pre className="prompt">Style: {preview || '…'}</pre>
          <p className="hint">Česky vyplněná pole přeloží Engine při použití (jako zadání, ~0,01 USD, podruhé zdarma).</p>
          <div className="row end">
            {slug && <button className="btn" onClick={() => onUse(slug)} disabled={dirty}>Použít ve studiu</button>}
            {slug && <button className="btn" onClick={() => newCard({ ...draft, label: `${draft.label} (kopie)`, origin: 'manual' })}>Duplikovat</button>}
            {slug && <button className="btn" onClick={remove}>Smazat</button>}
            <button className="btn go" disabled={!dirty || busy === 'save' || !draft.label.trim() || empty} onClick={save}
              title={empty ? 'Vyplňte aspoň médium a techniku nebo paletu' : ''}>{busy === 'save' ? 'Ukládám…' : 'Uložit kartu'}</button>
          </div>
        </div>
      </section>

      {openDetect && (
        <DetectDialog selectedImage={selectedImage} onError={onError} onClose={onDetectClosed}
          onDone={(fields, imgs) => { onDetectClosed(); newCard(fields, imgs) }} />
      )}
    </main>
  )

}

const grad = (p: PaletteColor[]) => (p.length > 1 ? `linear-gradient(135deg, ${p[0].hex}, ${p[p.length - 1].hex})` : p[0]?.hex ?? '#e9e7e1')

function DetectDialog({ selectedImage, onError, onClose, onDone }: {
  selectedImage: string | null
  onError: (msg: string) => void
  onClose: () => void
  onDone: (fields: StyleFields, imgs: PendingImage[]) => void
}) {
  const [imgs, setImgs] = useState<PendingImage[]>([])
  const [pal, setPal] = useState<PaletteColor[]>([])
  const [desc, setDesc] = useState<Omit<StyleFields, 'palette'> | null>(null)
  const [label, setLabel] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [picker, setPicker] = useState(false)

  useEffect(() => {
    if (!imgs.length) { setPal([]); return }
    setBusy('palette')
    stylesApi.palette(toImages(imgs)).then((r) => setPal(r.palette)).catch((e) => onError(e.message)).finally(() => setBusy(null))
  }, [imgs, onError])
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === 'Escape' && !picker && onClose()
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [onClose, picker])

  const add = (i: PendingImage) => setImgs((xs) => [...xs, i].slice(0, 5))
  const addFiles = async (files: FileList | File[]) => {
    for (const f of [...files].filter((x) => x.type.startsWith('image/'))) add({ b64: await fileToB64(f), preview: URL.createObjectURL(f) })
  }
  const describe = async () => {
    setBusy('describe')
    try {
      const r = await stylesApi.describe(toImages(imgs), true)
      setDesc(r)
      if (!label.trim()) setLabel(r.label)
    } catch (e) { onError((e as Error).message) } finally { setBusy(null) }
  }
  const finish = () => onDone({
    ...(desc ?? EMPTY), label: label.trim(), palette: pal.map(({ hex, name }) => ({ hex, name })),
    origin: desc ? 'detected' : 'manual', puvod: desc ? 'popis Claude Haiku ze vzorů, paleta k-means z pixelů' : 'paleta k-means z pixelů',
  }, imgs)

  return (
    <div className="modal" onClick={onClose}>
      <div className="dialog detect" onClick={(e) => e.stopPropagation()}>
        <div className="row between"><h2>Nový styl z obrázků</h2><button className="btn small" onClick={onClose}>Zavřít (Esc)</button></div>
        <div className="detect-cols">
          <div>
            <h3>1. Vzory stylu (2–5 obrázků)</h3>
            <div className="samples">
              {imgs.map((i, k) => (
                <div key={k} className="sample"><img src={i.preview} alt="" />
                  <button className="x" title="Odebrat" aria-label="Odebrat obrázek" onClick={() => setImgs(imgs.filter((_, j) => j !== k))}>×</button></div>
              ))}
            </div>
            {imgs.length < 5 && (
              <label className="drop" onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); addFiles(e.dataTransfer.files) }}>
                Přetáhněte obrázky sem nebo klikněte a vyberte soubor
                <input type="file" accept="image/*" multiple hidden onChange={(e) => { addFiles(e.target.files ?? []); e.target.value = '' }} />
              </label>
            )}
            <div className="row">
              <button className="btn small" disabled={imgs.length >= 5} onClick={() => setPicker(true)}>Z knihovny předloh nebo Commons</button>
              <button className="btn small" disabled={!selectedImage || imgs.length >= 5} title={selectedImage ? '' : 'Ve studiu není vybraný obrázek'}
                onClick={() => selectedImage && add({ job: selectedImage, preview: imageUrl(selectedImage, 384) })}>Vybraný obrázek ze studia</button>
            </div>
            <h3>2. Paleta · změřeno hned, zdarma</h3>
            {busy === 'palette' ? <p className="hint">Měřím…</p> : pal.length ? <Swatches palette={pal} /> : <p className="hint">Přidejte obrázky.</p>}
          </div>
          <div>
            <h3>3. Popis slovy · Claude se podívá na vzory</h3>
            <p className="hint">Popíše jen styl (médium, techniku, světlo, linku, kompozici), ne obsah obrázků. Výsledek se otevře v kartě stylu k úpravě, nic se neuloží samo.</p>
            <button className="btn pay" disabled={!imgs.length || busy === 'describe'} onClick={describe}
              title={imgs.length ? '' : 'Nejdřív přidejte obrázky'}>{busy === 'describe' ? 'Claude popisuje…' : desc ? 'Popsat znovu · 0,01 USD' : 'Popsat styl · 0,01 USD'}</button>
            <p className="hint">Kliknutí je souhlas s cenou (jako u překladu). Bez Claude lze kartu vyplnit ručně.</p>
            {desc && <pre className="prompt">{promptText({ ...desc, palette: pal })}</pre>}
            <h3>4. Název</h3>
            <input className="search full" value={label} onChange={(e) => setLabel(e.target.value)} placeholder="např. Muzejní rekonstrukce" aria-label="Název stylu" />
            <div className="row end">
              <button className="btn" onClick={onClose}>Zrušit</button>
              <button className="btn go" disabled={!label.trim() || !imgs.length} onClick={finish}
                title={!imgs.length ? 'Přidejte obrázky' : !label.trim() ? 'Zadejte název' : ''}>Otevřít v kartě stylu</button>
            </div>
          </div>
        </div>
      </div>
      {picker && (
        <div onClick={(e) => e.stopPropagation()}>
          <RefPicker initialTab="inbox" onError={onError} onClose={() => setPicker(false)}
            onPick={(m: RefMeta) => add({ ref_id: m.id, preview: `${m.image}?w=384` })} />
        </div>
      )}
    </div>
  )
}
