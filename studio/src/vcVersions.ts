import { useEffect, useRef, useState } from 'react'
import { api } from './api.ts'

const EVERY_MS = 4000

/** Watches a picture's copies in VectorCraft: every edit saved there (Ctrl+S) becomes a new version in the
 *  Knihovna tab, the picture itself stays (operator 4 Nov). Engine: POST …/vectorcraft/verze. */
export function useVcVersions(ref: string | null, enabled: boolean, onError: (msg: string) => void) {
  const [busy, setBusy] = useState(false)
  const [created, setCreated] = useState<string | null>(null)
  const failed = useRef(new Set<string>())   // an edit that cannot be taken over is reported once, not every few seconds
  const report = useRef(onError)
  report.current = onError

  useEffect(() => {
    setCreated(null)
    setBusy(false)
    if (!ref || !enabled) return
    let alive = true
    let timer = 0
    const tick = async () => {
      try {
        const state = await api.vectorcraftState(ref)
        const waiting = state.edits.filter((e) => !e.version && !failed.current.has(`${ref}:${e.file}:${e.modified}`)).reverse()
        for (const e of waiting) {
          if (!alive) return
          setBusy(true)
          try {
            const v = await api.vectorcraftVersion(ref, e.file)
            if (alive) setCreated(v.ref)
          } catch (err) {
            failed.current.add(`${ref}:${e.file}:${e.modified}`)
            report.current(`Ruční úpravu ${e.file} se nepodařilo převzít jako novou verzi: ${(err as Error).message}`)
          }
        }
      } catch { /* Engine restarting: the next tick tries again */ }
      if (!alive) return
      setBusy(false)
      timer = window.setTimeout(tick, EVERY_MS)
    }
    tick()
    return () => { alive = false; window.clearTimeout(timer) }
  }, [ref, enabled])

  return { busy, created }
}
