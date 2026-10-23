import { useEffect, useRef, useState } from 'react'
import { BOOKMARKLET } from './RefPicker.tsx'
import { fmtUsd } from './App.tsx'

interface Status {
  flux_local: { model: string; dir: string; exe_found: boolean; model_found: boolean; sd_server: string; gpu_free_mib: number | null; min_free_vram_mib: number; idle_timeout_s: number }
  services: { id: string; label: string; connected: boolean; note?: string }[]
  keys_from: string
  library: { refs: number }
  costs: { today_usd: number; total_usd: number }
}

const CLAUDE_CMD = 'python C:/Users/stock/Documents/000_NGM/GRAFIK/clients/grafik_client.py ref-add "<adresa obrázku nebo pinu>" --page "<adresa pinu>"'

// Settings card (operator request 2026-10-23): connected services at a glance. No passwords or keys are
// entered or shown here — keys live in .env files, Pinterest works through the operator's own Chrome.
export default function Settings({ onError }: { onError: (m: string) => void }) {
  const [st, setSt] = useState<Status | null>(null)
  const bm = useRef<HTMLAnchorElement>(null)
  useEffect(() => {
    fetch('/api/v2/settings').then((r) => r.json()).then(setSt).catch((e) => onError(String(e)))
  }, [onError])
  useEffect(() => { bm.current?.setAttribute('href', BOOKMARKLET) }, [st])
  if (!st) return <main className="settings"><p className="hint">Načítám…</p></main>
  const f = st.flux_local
  return (
    <main className="settings">
      <section className="card">
        <h3>Lokální generátor</h3>
        <dl>
          <dt>Model</dt><dd>FLUX 3 Klein ({f.model}) {f.model_found && f.exe_found ? <span className="tag ok">nalezen</span> : <span className="tag ai">chybí v {f.dir}</span>}</dd>
          <dt>Stav</dt><dd>{f.sd_server === 'ready' ? 'běží' : f.sd_server === 'starting' ? 'startuje' : 'spí, probudí se při generování'} · vypne se po {Math.round(f.idle_timeout_s / 60)} min nečinnosti</dd>
          <dt>Grafika</dt><dd>{f.gpu_free_mib ?? '?'} MiB volných (potřeba aspoň {f.min_free_vram_mib}). Programy jako Illustrator si berou část paměti.</dd>
          <dt>Cena</dt><dd><span className="tag free">0 USD</span></dd>
        </dl>
      </section>

      <section className="card">
        <h3>Připojené služby</h3>
        <table className="services">
          <tbody>
            {st.services.map((s) => (
              <tr key={s.id}>
                <td>{s.label}</td>
                <td>{s.note ? <span className="tag free">bez účtu</span> : s.connected ? <span className="tag ok">připojeno</span> : <span className="tag ai">chybí klíč</span>}</td>
                <td className="hint">{s.note?.replace(/^bez účtu(: | v GRAFIK: )?/, '') ?? ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="hint">Klíče se berou z {st.keys_from}. Placené služby se vždy zeptají na cenu, než cokoli spustí.</p>
      </section>

      <section className="card">
        <h3>Pinterest</h3>
        <p>GRAFIK žádné přihlášení k Pinterestu nepotřebuje. Piny se berou ve vašem Chrome, kde jste přihlášený (přes Google):</p>
        <ol>
          <li>Přetáhněte tuhle záložku do lišty záložek Chrome: <a ref={bm} className="bookmarklet" onClick={(e) => e.preventDefault()}>→ GRAFIK</a>.
            Na stránce pinu na ni klikněte a obrázek se uloží do Schránky předloh.</li>
          <li>Nebo řekněte Claude v Chrome „ulož tenhle pin do GRAFIK“. Claude použije příkaz:
            <pre className="prompt">{CLAUDE_CMD}</pre></li>
          <li>Nebo obrázek přetáhněte z jiné záložky do okna Předlohy.</li>
        </ol>
      </section>

      <section className="card">
        <h3>Knihovna a útrata</h3>
        <dl>
          <dt>Předlohy</dt><dd>{st.library.refs} ve schránce</dd>
          <dt>Útrata dnes</dt><dd>{fmtUsd(st.costs.today_usd)}</dd>
          <dt>Útrata celkem</dt><dd>{fmtUsd(st.costs.total_usd)}</dd>
        </dl>
      </section>
    </main>
  )
}
