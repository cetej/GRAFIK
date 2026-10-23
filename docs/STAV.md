# Stav GRAFIK

Aktualizováno 2026-10-23.

## Teď

**GRAFIK v2: G0–G3 hotové a ověřené na RTX 4060** (spec, Engine, supersample, fal, studio, překlad češtiny, předlohy a průvodce historickým objektem, karta Nastavení).
Spec: [`plans/2026-10-22-grafik-v2-greenfield.md`](plans/2026-10-22-grafik-v2-greenfield.md) · rozhodnutí: [`DECISIONS.md`](DECISIONS.md) · důkazy: [G1](spikes/2026-10-22-g1-engine.md), [supersample](spikes/2026-10-23-supersample.md), [G2](spikes/2026-10-23-g2-studio.md), [G3](spikes/2026-10-23-g3-predlohy.md).

- **Engine** `engine/` :8300 `/api/v2`: fronta + jeden worker, sd-server jen podle vlastního PID (při nedostatku VRAM restart a nový pokus), zámek GPU, provenience a náklady; lokální FLUX zdarma, placené `nb-pro` a `fal:` jen s `confirm_cost`; supersample; úprava v rámečku; strom verzí; překlad češtiny; **knihovna předloh** (`refs/library/`, `ref_id`), **Wikimedia Commons** (hledání, import s autorem a licencí), **příjem z Pinterestu** (URL obrázku i pinu), **průvodce historickým objektem** (`/api/v2/workflows`), `/api/v2/settings`.
- **Studio** `studio/` :5174: Studio, Průvodce, Knihovna, Nastavení; okno Přidat předlohu (Commons, Schránka, soubor), záložka „→ GRAFIK“ pro Chrome.
- **Klient** `clients/grafik_client.py`: `generate`, `add_ref`, CLI `ref-add` (pro Claude in Chrome).
- Pinterest: návod [`pinterest.md`](pinterest.md).
- Testy: celá sada 264.

## Další krok

- **G4 styly:** karty stylu ve formátu POHYB, detekce z obrázku, knihovna přes API.
- **G5 infografiky:** vrstva českých popisků HTML/SVG nad výsledkem průvodce, export PNG/SVG/PDF.
- Napojení projektů (KLAPKA, NG-ROBOT…) až na pokyn operátora.
- Drobnosti: „Rozepsat zadání“ naostro neklikáno; pin přes `og:image` ověřen jen offline (Pinterest robotům ukazuje přihlášení).

## Starý GRAFIK (v1)

Unified Editor M2–M6-UX1 (`grafik/`, `ui-web/`) — funkční, API :8301, UI :5173. Jen reference; o archivaci rozhodne operátor.
