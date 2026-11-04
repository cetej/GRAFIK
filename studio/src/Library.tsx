import { useEffect, useState } from 'react'
import { api, imageUrl, jobRefs, type Job } from './api.ts'
import type { LbItem, OpenImage } from './panels.tsx'

const PAGE = 48

const caption = (job: Job) => job.request.edit?.instruction ?? job.request.prompt
const fileName = (ref: string) => `grafik-${ref.replace('/', '-')}.png`

/** A finished picture in the enlarged view: download, delete to library/.trash, open in Studio. */
export function libraryItem(ref: string, job: Job, onDeleted: (ref: string) => void, open: LbItem['open']): LbItem {
  return {
    src: imageUrl(ref), title: caption(job), download: fileName(ref), open, deleteLabel: 'Přesunout do koše',
    onDelete: async () => { await api.deleteImage(ref); onDeleted(ref) },
  }
}

// The Knihovna tab: every finished picture page by page (Engine /api/v2/library), deleting moves to library/.trash.
export default function Library({ reloadKey, onOpen, onZoom, onDeleted, onError }: {
  reloadKey: string   // the newest finished pictures changed: reload the page
  onOpen: (ref: string) => void
  onZoom: OpenImage
  onDeleted: (ref: string) => void
  onError: (msg: string) => void
}) {
  const [page, setPage] = useState(0)
  const [data, setData] = useState<{ total: number; offset: number; items: Job[] } | null>(null)
  const [asking, setAsking] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [tick, setTick] = useState(0)

  useEffect(() => {
    let live = true   // a late answer for another page must not replace this one
    api.library(page * PAGE, PAGE).then((d) => { if (live) setData(d) }).catch((e: Error) => onError(e.message))
    return () => { live = false }
  }, [page, reloadKey, tick, onError])
  const stale = data !== null && data.offset !== page * PAGE
  const go = (p: number) => { setPage(p); window.scrollTo({ top: 0 }) }

  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE)) : 1
  useEffect(() => { if (page >= pages) setPage(pages - 1) }, [page, pages])

  const remove = async (ref: string) => {
    setBusy(true)
    try {
      await api.deleteImage(ref)
      onDeleted(ref)
      setTick((t) => t + 1)
    } catch (e) { onError((e as Error).message) } finally { setBusy(false); setAsking(null) }
  }

  const pager = data && data.total > PAGE && (
    <nav className="pager">
      <button className="btn small" disabled={page === 0} onClick={() => go(0)}>« První</button>
      <button className="btn small" disabled={page === 0} onClick={() => go(page - 1)}>‹ Novější</button>
      <span>Strana {page + 1} z {pages}{stale ? ' · načítám…' : ''}</span>
      <button className="btn small" disabled={page >= pages - 1} onClick={() => go(page + 1)}>Starší ›</button>
      <button className="btn small" disabled={page >= pages - 1} onClick={() => go(pages - 1)}>Poslední »</button>
    </nav>
  )

  const deleted = (ref: string) => { onDeleted(ref); setTick((t) => t + 1) }
  const items = data ? data.items.flatMap((job) => jobRefs(job).map((ref) => libraryItem(ref, job, deleted, { label: 'Otevřít ve Studiu', run: () => onOpen(ref) }))) : []

  if (!data) return <main className="library-page"><p className="empty">Načítám knihovnu…</p></main>
  return (
    <main className="library-page">
      <p className="library-count">{data.total === 0 ? 'Knihovna je prázdná.' : `Prací v knihovně: ${data.total}`}</p>
      {pager}
      <div className={`library${stale ? ' stale' : ''}`}>
        {data.items.flatMap((job) => jobRefs(job).map((ref) => (
          <figure key={ref}>
            <button className="library-open" onClick={() => onZoom(imageUrl(ref), items)} title="Zvětšit, šipkami na další">
              <img src={imageUrl(ref, 384)} loading="lazy" alt="" />
            </button>
            <figcaption>
              <span>{caption(job).slice(0, 90)}</span>
              <small>{new Date(job.created * 1000).toLocaleString('cs-CZ', { dateStyle: 'short', timeStyle: 'short' })}</small>
            </figcaption>
            <div className="library-act">
              {asking === ref ? (
                <>
                  <span>Přesunout do koše?</span>
                  <button className="btn small del" disabled={busy} onClick={() => remove(ref)}>Smazat</button>
                  <button className="btn small" disabled={busy} onClick={() => setAsking(null)}>Ne</button>
                </>
              ) : (
                <>
                  <button className="btn small" onClick={() => onOpen(ref)}>Otevřít ve Studiu</button>
                  <a className="btn small" href={imageUrl(ref)} download={fileName(ref)} title="Stáhnout PNG">⤓</a>
                  <button className="btn small" onClick={() => setAsking(ref)} title="Přesunout do koše">🗑</button>
                </>
              )}
            </div>
          </figure>
        )))}
      </div>
      {pager}
    </main>
  )
}
