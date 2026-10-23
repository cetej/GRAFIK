# Rozhodnutí operátora — GRAFIK

Nejnovější nahoře. Každé rozhodnutí: datum, co, proč, odkud.

## 2026-10-23 — G3 předlohy a průvodce, karta Nastavení

- **Náčrty G3 schváleny:** okno „Přidat předlohu“ (Wikimedia Commons, Schránka předloh, soubor) a záložka „Průvodce“ historickým objektem (předlohy → bokorys → oprava v rámečku → natočený pohled 3/4 shora → popisky v G5).
- **Karta Nastavení** na přání operátora: ukazuje připojené služby a stav generátoru. Hesla ani klíče se v GRAFIK nezadávají ani nezobrazují; Pinterest nepotřebuje účet v GRAFIK, protože piny jdou přes operátorův přihlášený Chrome (přes Google) záložkou „→ GRAFIK“ nebo Claude in Chrome.
- Pinterest obrázky mají licenci „neznámá — jen předloha“: slouží jen jako předloha, nikdy jako součást výstupu.

## 2026-10-23 — G2 studio, čeština, cena v tlačítku

- **Náčrt studia schválen** (`docs/spikes/img/g2-nacrt.png`): vlevo zadání a předlohy, uprostřed náhled s porovnáním a úpravou v rámečku, dole fronta a galerie, vpravo historie verzí a údaje o obrázku.
- **Nové studio běží na :5174**, starý editor zůstává na :5173 do rozhodnutí operátora o archivaci.
- **Překladová vrstva:** FLUX česky rozumí jen zhruba (ověřeno: český pokyn úpravu neprovedl, z „majáku“ udělal dům). Engine proto překládá české zadání, pokyn i styl přes Claude do angličtiny laděné pro cílový generátor; opakovaný text z mezipaměti zdarma.
- **Cena překladu (~0,01 USD) se ukazuje v tlačítku a kliknutí je souhlas.** Dialog s cenou zůstává pro placené generátory. Operátor odsouhlasil živý test dvou překladů (~0,02 USD).
- Pokračovat podle plánu: supersample, fal jako volba s cenou předem, G2; napojení dalších projektů zatím ne (zpráva zakládající session, operátor „Tak pokračuj“).

## 2026-10-22 — GRAFIK v2: spec G0 schválen, odpovědi Q1–Q5

Operátor schválil spec `docs/plans/2026-10-22-grafik-v2-greenfield.md` a start G1 (Engine).


- **Q1 rozhraní:** nový React web (Vite, :5173), stejný stack jako dnešní `ui-web/`.
- **Q2 výstupy:** centrálně v GRAFIK `library/RRRR-MM/<job>/` s proveniencí; volající projekt dostane kopii a uloží si ji po svém.
- **Q3 karta stylu:** formát POHYB — `styles/<slug>/STYLE.md` + `style.json` + `samples/`; knihovna v GRAFIK, ostatní projekty čtou přes API.
- **Q5 port:** nový Engine převezme :8300 (projekty ho mají natvrdo); starý editor se přesune na :8301 a zůstane spustitelný do konce G2, pak operátor rozhodne o archivaci.
- **Q4 Pinterest:** všechny tři cesty — Claude in Chrome uloží pin (obrázek + URL) do `refs/inbox/`, přetažení souboru do UI, bookmarklet v Chrome posílající obrázek do Engine.

## 2026-10-22 — GRAFIK v2: lokální FLUX jako výchozí generátor

Zdroj: `ZZZ_TEST/plan-flux-vychozi-vsude.md`, rozhodnutí operátora 22. 10.

1. **FLUX 3 Klein lokálně je výchozí generátor obrázků** ve všech projektech (Q4 GGUF + encoder Qwen3-VL-4B Q4, stable-diffusion.cpp `master-987`, `C:/Users/stock/models/flux3-klein/`). Měřeno na RTX 4060 Laptop 8 GB: 1024² ~38 s, 1920×1088 ~95 s s `--vae-tiling`, edit s referencí ~70–90 s.
2. **Placené generátory (Nano Banana Pro, fal) jen na výslovné přání** a s cenou zobrazenou předem. Nikdy automatický fallback.
3. **Licence FLUX Kommunity v1.0 je splněná** (obrat skupiny < 5 M USD). Podmínka § 2e: před zveřejněním výstup zkontroluje člověk a nese označení „vytvořeno AI“, kde to vyžaduje zákon. Engine ukládá `ai_generated: true`, `reviewed_by: null`.
4. **GRAFIK se přestaví od nuly** jako obrazové studio operátora a jediná obrazová služba (GRAFIK Engine) pro NG-ROBOT, KLAPKA, KARTOGRAF, POHYB, HEGEMON a STOPA `/nano`. Důvod: jedna GPU s 8 GB neunese souběžné instance FLUX. Starý kód zůstává jako reference; mazat jen se souhlasem.
5. **Video osa se do nového GRAFIK nepřenáší.**

Ověřené poznatky z testů 22. 10., které spec přebírá:
- Přenos stylu obrazovou referencí ve FLUX nefunguje, styl je nutné popsat slovy.
- Reference předmětu a geometrie funguje velmi dobře.
- Drobné postavy se deformují: reference se správným měřítkem, generovat výš a zmenšit.
- Schválený postup pro historické objekty: předloha → čistý bokorys → oprava v rámečku → natočený pohled 3/4 shora → popisky jako vektorová vrstva.
