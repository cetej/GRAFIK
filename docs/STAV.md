# Stav GRAFIK

Aktualizováno 2026-10-23.

## Teď

**GRAFIK v2: G0 spec, G1 Engine, supersample, fal backend a G2 studio jsou hotové a ověřené na RTX 4060.**
Spec: [`plans/2026-10-22-grafik-v2-greenfield.md`](plans/2026-10-22-grafik-v2-greenfield.md) · rozhodnutí: [`DECISIONS.md`](DECISIONS.md) · důkazy: [`spikes/2026-10-22-g1-engine.md`](spikes/2026-10-22-g1-engine.md), [`spikes/2026-10-23-supersample.md`](spikes/2026-10-23-supersample.md), [`spikes/2026-10-23-g2-studio.md`](spikes/2026-10-23-g2-studio.md).

- **Engine** `engine/` na :8300 (`/api/v2`): fronta SQLite + jeden worker, sd-server jen podle vlastního PID, zámek GPU, provenience a náklady; výchozí lokální FLUX zdarma; placené `nb-pro` a `fal:<endpoint>` jen s `confirm_cost`; supersample; úprava v rámečku s paste-back; strom verzí; **překlad českých zadání přes Claude** (cena v odhadu, mezipaměť).
- **Studio** `studio/` na :5174: zadání, předlohy s rolí, formát, varianty, drobné detaily, výběr generátoru s cenou; náhled se zvětšením, porovnání před/po, úprava v rámečku, další varianta, použít jako předlohu; fronta a galerie; historie verzí, údaje o obrázku, kontrola člověkem; knihovna.
- **Klient** `clients/grafik_client.py` pro ostatní projekty (jen stdlib).
- `start-grafik.bat`: Engine :8300, studio :5174 (otevře se), starý editor API :8301 + UI :5173.
- Testy: `tests/test_engine_v2.py` (offline, falešný sd-server), celá sada 255.

## Další krok

- **G3 předlohy:** hledání ve Wikimedia Commons, Pinterest (Claude in Chrome do `refs/inbox/`, přetažení, bookmarklet), průvodce „historický objekt“ (bokorys → oprava → natočený pohled).
- **G4 styly:** karty stylu ve formátu POHYB, detekce z obrázku, knihovna přes API.
- **G5 infografiky:** vrstva českých popisků HTML/SVG, export PNG/SVG/PDF.
- Napojení projektů (KLAPKA, NG-ROBOT…) až na pokyn operátora.
- Drobnosti: „Rozepsat zadání“ naostro neklikáno (ověřeno offline); čas v provenienci u více variant je za celou úlohu.

## Starý GRAFIK (v1)

Unified Editor M2–M6-UX1 (`grafik/`, `ui-web/`) — funkční, API :8301, UI :5173. Jen reference; o archivaci rozhodne operátor.
