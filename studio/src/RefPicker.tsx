import { useEffect, useRef, useState } from 'react'
import { fileToB64, knihovnaApi, refsApi, type CommonsItem, type KnihovnaImage, type KnihovnaItem, type KnihovnaKind, type RefMeta } from './api.ts'
import { ROLE_LABEL } from './App.tsx'

export type PickerTab = 'commons' | 'inbox' | 'knihovna' | 'file'

const ORIGIN_LABEL: Record<RefMeta['origin'], string> = { commons: 'Commons', pinterest: 'Pinterest', web: 'web', upload: 'soubor' }

// Bookmarklet: opens the studio with the page's main image; the studio stores it (no CORS, no localhost fetch from the site).
export const BOOKMARKLET = `javascript:(()=>{const m=document.querySelector('meta[property="og:image"]');const i=m?m.content:[...document.images].sort((a,b)=>b.naturalWidth*b.naturalHeight-a.naturalWidth*a.naturalHeight)[0]?.src;if(!i){alert('Na stránce není obrázek');return}window.open('${location.origin}/#addref='+encodeURIComponent(i)+'&page='+encodeURIComponent(location.href)+'&title='+encodeURIComponent(document.title),'grafik')})()`

/** Store dropped files or a dragged web image in the library. */
export async function storeDrop(dt: DataTransfer): Promise<RefMeta[]> {
  const files = [...dt.files].filter((f) => f.type.startsWith('image/'))
  if (files.length) return Promise.all(files.map(async (f) => refsApi.addB64(await fileToB64(f), f.name)))
  const url = dt.getData('text/uri-list').split('\n').find((l) => l && !l.startsWith('#')) || dt.getData('text/plain')
  return url && /^https?:/.test(url) ? [await refsApi.addUrl(url.trim())] : []
}

export default function RefPicker({ initialTab, onPick, onPickKnihovna, onClose, onError }: {
  initialTab: PickerTab
  onPick: (meta: RefMeta) => void
  onPickKnihovna?: (item: KnihovnaItem, img: KnihovnaImage) => void   // the tab shows only where this is given
  onClose: () => void
  onError: (msg: string) => void
}) {
  const [tab, setTab] = useState<PickerTab>(initialTab)
  const [q, setQ] = useState('')
  const [results, setResults] = useState<CommonsItem[] | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [added, setAdded] = useState<Record<string, boolean>>({})
  const [inbox, setInbox] = useState<RefMeta[]>([])
  const bm = useRef<HTMLAnchorElement>(null)

  const loadInbox = () => refsApi.list().then(setInbox).catch((e) => onError(e.message))
  useEffect(() => { loadInbox() }, []) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { bm.current?.setAttribute('href', BOOKMARKLET) }, [tab])
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [onClose])

  const search = async () => {
    if (!q.trim()) return
    setBusy('search')
    try { setResults(await refsApi.commons(q.trim())) } catch (e) { onError((e as Error).message) } finally { setBusy(null) }
  }
  const importCommons = async (it: CommonsItem) => {
    setBusy(it.file)
    try {
      const meta = await refsApi.commonsImport(it.file)
      refsApi.seen(meta.id).catch(() => {}) // picked right away, so not "new" in the inbox
      onPick(meta)
      setAdded((a) => ({ ...a, [it.file]: true }))
    } catch (e) { onError((e as Error).message) } finally { setBusy(null) }
  }
  const use = async (m: RefMeta) => {
    if (!m.seen) refsApi.seen(m.id).catch(() => {})
    onPick(m)
    setAdded((a) => ({ ...a, [m.id]: true }))
  }
  const drop = async (dt: DataTransfer) => {
    setBusy('drop')
    try {
      const metas = await storeDrop(dt)
      if (!metas.length) onError('V přetaženém není obrázek ani jeho adresa.')
      metas.forEach(use)
      loadInbox()
    } catch (e) { onError((e as Error).message) } finally { setBusy(null) }
  }
  const unseen = inbox.filter((m) => !m.seen && m.origin !== 'upload').length

  return (
    <div className="modal" onClick={onClose}>
      <div className="dialog picker" onClick={(e) => e.stopPropagation()}>
        <div className="row"><h2>Přidat předlohu</h2><button className="btn small" style={{ marginLeft: 'auto' }} onClick={onClose}>Hotovo (Esc)</button></div>
        <div className="tabs">
          <button className={tab === 'commons' ? 'on' : ''} onClick={() => setTab('commons')}>Wikimedia Commons</button>
          <button className={tab === 'inbox' ? 'on' : ''} onClick={() => setTab('inbox')}>Schránka{unseen ? ` (${unseen} nové)` : ''}</button>
          {onPickKnihovna && <button className={tab === 'knihovna' ? 'on' : ''} onClick={() => setTab('knihovna')}>Postavy a místa</button>}
          <button className={tab === 'file' ? 'on' : ''} onClick={() => setTab('file')}>Soubor</button>
        </div>

        {tab === 'commons' && (
          <>
            <form className="row" onSubmit={(e) => { e.preventDefault(); search() }}>
              <input className="search" autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="např. roman warship model" />
              <button className="btn go" disabled={busy === 'search'}>{busy === 'search' ? 'Hledám…' : 'Hledat'}</button>
              <span className="hint">Commons hledá nejlépe anglicky; jen obrázky</span>
            </form>
            <div className="results">
              {results?.length === 0 && <p className="hint">Nic nenalezeno. Zkuste jiné nebo anglické slovo.</p>}
              {results?.map((it) => (
                <div key={it.file} className={`res ${added[it.file] ? 'sel' : ''}`}>
                  <a href={it.page_url} target="_blank" rel="noreferrer" title="Otevřít stránku souboru na Commons"><img src={it.thumb} alt="" loading="lazy" /></a>
                  <div className="info">
                    <b title={it.title}>{it.title}</b>
                    <span>{it.author ?? 'autor neuveden'}</span> · <span className="tag ok">{it.license ?? 'licence?'}</span>
                    <span className="hint"> {it.width}×{it.height}</span>
                  </div>
                  <div className="act">
                    <button className="btn small" disabled={!!added[it.file] || busy === it.file} onClick={() => importCommons(it)}>
                      {added[it.file] ? '✓ Přidáno' : busy === it.file ? 'Stahuji…' : '+ Přidat'}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </>
        )}

        {tab === 'inbox' && (
          <>
            <div className="inbox-help">
              Sem chodí předlohy z Pinterestu a webu. Cesty: řekněte Claude v Chrome „ulož tenhle pin do GRAFIK“,
              přetáhněte obrázek z jiné záložky sem, nebo přetáhněte tuhle záložku do lišty Chrome:{' '}
              <a ref={bm} className="bookmarklet" onClick={(e) => e.preventDefault()} title="Přetáhněte do lišty záložek">→ GRAFIK</a>
            </div>
            <DropZone busy={busy === 'drop'} onDrop={drop} label="Přetáhněte obrázek z webu nebo soubor" />
            <div className="results">
              {inbox.length === 0 && <p className="hint">Schránka je prázdná.</p>}
              {inbox.map((m) => (
                <div key={m.id} className={`res ${added[m.id] ? 'sel' : ''}`}>
                  <img src={`${m.image}?w=320`} alt="" loading="lazy" />
                  <div className="info">
                    <b title={m.title}>{m.title}</b>
                    <span>{ORIGIN_LABEL[m.origin]}{m.author ? ` · ${m.author}` : ''}</span> · <span className={`tag ${m.origin === 'pinterest' ? 'ai' : 'ok'}`}>{m.license ?? 'licence?'}</span>
                    {!m.seen && m.origin !== 'upload' && <span className="tag new">nové</span>}
                  </div>
                  <div className="act">
                    <button className="btn small" disabled={!!added[m.id]} onClick={() => use(m)}>{added[m.id] ? '✓ Přidáno' : '+ Použít'}</button>
                    {m.page_url && <a className="btn small" href={m.page_url} target="_blank" rel="noreferrer">Zdroj</a>}
                  </div>
                </div>
              ))}
            </div>
          </>
        )}

        {tab === 'knihovna' && onPickKnihovna && <KnihovnaTab onPick={onPickKnihovna} onError={onError} />}

        {tab === 'file' && <DropZone busy={busy === 'drop'} onDrop={drop} label="Přetáhněte soubor nebo klikněte a vyberte" big />}
      </div>
    </div>
  )
}

function DropZone({ busy, onDrop, label, big }: { busy: boolean; onDrop: (dt: DataTransfer) => void; label: string; big?: boolean }) {
  const [over, setOver] = useState(false)
  return (
    <label className={`drop ${over ? 'over' : ''} ${big ? 'big' : ''}`}
      onDragOver={(e) => { e.preventDefault(); setOver(true) }} onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); onDrop(e.dataTransfer) }}>
      {busy ? 'Ukládám…' : label}
      <input type="file" accept="image/*" multiple hidden onChange={(e) => {
        const dt = new DataTransfer()
        ;[...(e.target.files ?? [])].forEach((f) => dt.items.add(f))
        onDrop(dt)
        e.target.value = ''
      }} />
    </label>
  )
}

export const KIND_LABEL: Record<KnihovnaKind, string> = { character: 'postava', environment: 'místo', prop: 'rekvizita' }
const KIND_FILTER: { key: KnihovnaKind | ''; label: string }[] = [
  { key: '', label: 'Vše' }, { key: 'character', label: 'Postavy' }, { key: 'environment', label: 'Místa' }, { key: 'prop', label: 'Rekvizity' },
]
const fold = (s: string) => s.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase()

/** Characters, places and props of the shared library: one tile each (the main image), the other images on demand. */
function KnihovnaTab({ onPick, onError }: { onPick: (item: KnihovnaItem, img: KnihovnaImage) => void; onError: (msg: string) => void }) {
  const [items, setItems] = useState<KnihovnaItem[] | null>(null)
  const [q, setQ] = useState('')
  const [kind, setKind] = useState<KnihovnaKind | ''>('')
  const [open, setOpen] = useState<string | null>(null)
  const [added, setAdded] = useState<Record<string, boolean>>({})

  useEffect(() => {
    knihovnaApi.list().then((r) => {
      setItems(r.items)
      if (r.problems.length) onError(`Knihovna: ${r.problems.join('; ')}`)
    }).catch((e) => onError((e as Error).message))
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const words = fold(q).split(/\s+/).filter(Boolean)
  const shown = (items ?? [])
    .filter((it) => (!kind || it.kind === kind) && words.every((w) => fold(`${it.name} ${it.slug} ${it.about}`).includes(w)))
    .sort((a, b) => Number(!a.images.length) - Number(!b.images.length) || b.updated.localeCompare(a.updated))
  const count = (k: KnihovnaKind | '') => (items ?? []).filter((it) => !k || it.kind === k).length
  const use = (it: KnihovnaItem, img: KnihovnaImage) => {
    onPick(it, img)
    setAdded((a) => ({ ...a, [img.knihovna]: true }))
  }

  return (
    <>
      <div className="row">
        <input className="search" autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="hledat: jméno nebo popis (caesar, toga, amfora…)" />
        <div className="seg wrap">
          {KIND_FILTER.map((f) => <button key={f.key} className={kind === f.key ? 'on' : ''} onClick={() => setKind(f.key)}>{f.label} {count(f.key)}</button>)}
        </div>
      </div>
      <p className="hint">Sdílená knihovna KNIHOVNA, stejné karty jako v KLAPCE. Naposledy změněné nahoře, bez obrázku na konci.</p>
      <div className="results kn">
        {items === null && <p className="hint">Načítám…</p>}
        {items?.length === 0 && <p className="hint">Knihovna je prázdná. Postavy, místa a rekvizity se zakládají v KLAPCE.</p>}
        {!!items?.length && !shown.length && <p className="hint">Nic nenalezeno.</p>}
        {shown.map((it) => {
          const key = `${it.kind}/${it.slug}`
          const main = it.images[0]
          const more = it.images.length > 1
          return [
            <div key={key} className={`res ${open === key ? 'sel' : ''}`}>
              {main ? <img src={`${main.url}?w=256`} alt="" loading="lazy" /> : <div className="noimg">bez obrázku</div>}
              <div className="info">
                <b title={it.name}>{it.name}</b>
                <span title={it.about}>{KIND_LABEL[it.kind]}{more ? ` · ${it.images.length} obr.` : ''}</span>
              </div>
              <div className="act">
                <button className="btn small" disabled={!main || !!added[main.knihovna]} onClick={() => main && use(it, main)}
                  title={main ? `hlavní předloha, jde jako ${ROLE_LABEL[main.role]}` : 'karta nemá obrázek (doplní se v KLAPCE)'}>
                  {main && added[main.knihovna] ? '✓ Přidáno' : '+ Použít'}
                </button>
                {more && (
                  <button className="btn small" aria-expanded={open === key} title="další obrázky položky" onClick={() => setOpen(open === key ? null : key)}>
                    {open === key ? '▴' : '▾'} {it.images.length}
                  </button>
                )}
              </div>
            </div>,
            open === key && (
              <div key={`${key}-more`} className="kn-more">
                <div className="hint"><b>{it.name}</b> · klik přidá ten obrázek</div>
                <div className="kn-strip">
                  {it.images.map((img) => (
                    <button key={img.file} className={`kn-img ${added[img.knihovna] ? 'sel' : ''}`} disabled={!!added[img.knihovna]}
                      onClick={() => use(it, img)} title={`${img.label}, jde jako ${ROLE_LABEL[img.role]}`}>
                      <img src={`${img.url}?w=160`} alt="" loading="lazy" />
                      <span>{added[img.knihovna] ? '✓ ' : img.primary ? 'hlavní · ' : '+ '}{img.label}</span>
                    </button>
                  ))}
                </div>
              </div>
            ),
          ]
        })}
      </div>
    </>
  )
}
