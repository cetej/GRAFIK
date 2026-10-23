# Rozhodnutí operátora — GRAFIK

Nejnovější nahoře. Každé rozhodnutí: datum, co, proč, odkud.

## 2026-10-23 — GRAFIK v1 z repa pryč

Operátor: „Starého grafika nepotřebuji.“

- Kód v1 (`grafik/`, `ui/`, `ui-web/`, `.streamlit/`, testy a skripty v1) odebrán; historie pod tagem `v1-final`.
- `start-grafik.bat` spouští jen Engine :8300 a Studio :5174; `pyproject.toml` balí jen `engine` (bez streamlit, typer, opencv).
- Uživatelská data (`projects/`, `library/`, `styles/`, `run/`, `logs/`) zůstala beze změny.

## 2026-10-23 — Zásady infografik místo kopírování vzoru

Operátor: „nejde o to sekat infografiky stejné jedna jako druhá, jako Baťa cvičky … jde o to pochopit, okoukat čistý grafický styl, rovnováhu, informační hodnotu a čtenářský zážitek.“ Pak „Dobře dotáhni to“.

- Zásady a měřitelné prahy v `docs/infografiky-zasady.md`, pravidlo `.claude/rules/infografiky.md`; úsudek o celku zůstává na člověku, čísla jen upozorní.
- Nové infografiky: rozvržení „Lišta přes obraz“ 1920×1080; staré dokumenty beze změny („Klasické“).
- Co nemá doklad, do obrazu nepatří: věž na lodi z 1. punské války odstraněna; řez boku bez informační hodnoty vynechán; moře pryč, protože zhoršovalo čitelnost popisků.
- Postup obrázku pro infografiku: model v Blenderu z rozměrů → hliněný render → pokusy na lokálním FLUX zdarma → konečná kresba placeným modelem jen se souhlasem a cenou předem.

## 2026-10-23 — 3D cesta: TRELLIS 2 + Blender jako předloha pro generátor

Operátor: TRELLIS má z dobrých předloh postavit správné 3D, z něj dostane správné zadání náš generátor; hodí se i pro 3D scény ve spolupráci s Blenderem. Schválil instalaci Blenderu a nejvýš 2 běhy TRELLIS 2 po 0,30 USD.

- TRELLIS 2 běží na fal.ai (`fal-ai/trellis-2`, 0,25/0,30/0,35 USD za 512p/1024p/1536p), lokálně ne (≥16 GB VRAM, Linux). Placený jako ostatní: cena předem, souhlas.
- Blender 5.2.3 LTS portable v `C:/Users/stock/tools/`, ovládaný skriptem headless; render jde do lokálního FLUX jako `geometry` předloha (zdarma).
- Spike: `docs/spikes/2026-10-23-3d-trellis-blender.md` (0,30 USD, tvar lodi držel). Napojení do Engine/Studia zatím ne.

## 2026-10-23 — Termdb v překladu a v kontrole infografiky

Operátor: „Napoj termdb na překlad i na kontrolu infografiky: zdarma a lokálně, jednoznačné termíny předat překladu jako nápovědu, neznámé označit ‚není v termdb‘, bez placeného vyhledávání na webu.“

- Termdb = `BIOLIB/termdb.db` (sdílená s NG-ROBOT), GRAFIK ji jen čte (`GRAFIK_TERMDB`, prázdná hodnota vypne). Placené vyhledávání na webu z NG-ROBOT se nepoužívá.
- **Nápověda do překladu jen pro jednoznačné odborné termíny** (biologie, zeměpis…): všechny odborné významy se shodují a slovníkový výklad nemluví o něčem jiném. Proto „liška obecná“ (v biologii houba, ve slovníku liška) ani „Most“ (město × most) nápovědu nedostanou. Nápověda je součástí klíče mezipaměti překladu a je v provenienci.
- **Kontrola infografiky:** „není v termdb“ se hlásí jen u nadpisu a hlavních textů popisků (1. pád); podtitulek, drobné texty, schéma a fakta jsou skloňovaná věta, tam jen nejednoznačné termíny.

## 2026-10-23 — G5 infografiky

- **Náčrt G5 schválen** („Schvaluji náčrt G5, stavěj.“): záložka Infografiky (obsah vlevo, živý náhled uprostřed, vzhled, kontrola a export vpravo), vstupy z kroku 5 Průvodce a tlačítkem „→ Infografika“, návrh popisků od Claude jen na kliknutí s cenou. Vzor: kvinquerema `overlay_quinq3.html` (do ~5 popisků, čáry mimo objekt, 3 fakta, vektorové schéma, tmavé pozadí, patička se zdroji a AI).
- **Text v infografice nikdy z modelu**: popisky, fakta i schéma píše redakce v editoru; Claude navrhuje jen názvy částí a místa, ne fakta.
- **Označení AI v patičce se doplní z provenience a nejde smazat**; export bez něj Engine odmítne. Kontrola člověkem (jméno) se zapíše do provenience exportu.
- **Jeden renderer:** studio kreslí SVG, Engine ho jen vyčistí (bez skriptů a odkazů ven) a převede na PNG/PDF stejným Chromiem. Exporty v `library/infographics/<id>/exports/`.
- Operátor 23. 10.: „Kloun? To je snad zobec“ a napojit ověření překladu na termdb (`BIOLIB/termdb.db`). Rozsah se domlouvá, viz STAV.

## 2026-10-23 — G4 styly

- **Náčrt G4 schválen** (`docs/spikes/img/g4-nacrt-1.png`, `-2.png`): záložka „Styly“ (knihovna vlevo, karta stylu vpravo), dialog „Nový styl z obrázků“ a výběr stylu v zadání ve studiu. Zadání předala zakládající session („pokračuj G4 … nejdřív mi ukaž náčrt UI“), schválení operátor dal přímo: „Schvaluji náčrt G4, stavěj.“
- **Styl jde do generátoru jen slovy**, ukázky slouží k náhledu a detekci. Paleta se měří z pixelů zdarma; popis slovy od Claude je placený (0,01 USD) a spustí ho jen tlačítko s cenou, kliknutí je souhlas jako u překladu.
- **`style.json` je zdroj pravdy**, `STYLE.md` se z něj přepisuje při každém uložení (upravovat ve studiu nebo ve `style.json`). Smazaný styl jde do `styles/.trash/`, ne pryč.
- Projekty posílají `style: "<slug>"`; volný text ve `style` zůstává volným textem.

## 2026-10-23 — Poznatky z PromptEnhancer (cetej/GRAFIK#9)

Zadání operátora přes session „PromptEnhancer analýza“ (ta byla mezitím archivovaná): co je nové oproti GRAFIK, připravit k testování a implementovat v projektu. Z Tencent PromptEnhancer přebíráme jen principy, vlastními slovy; kód ani text jejich promptů ne (licence v EU neplatí). Dataset T2I-Keypoints-Eval je apache-2.0.

- **C, překlad bez tichého pádu do češtiny:** prázdný překlad nebo překlad, ve kterém zůstala čeština, se neuloží do mezipaměti a úloha skončí čitelnou chybou. Za češtinu se počítá víc než pětina slov s diakritikou mimo uvozovky, takže místní jména („Kutná Hora“) a citované nápisy projdou.
- **Text v uvozovkách se nepřekládá** (#9 bod 1): nápis, který má být v obrázku, zůstává v původním jazyce a pravopisu v dvojitých uvozovkách. Platí pro překlad i „Rozepsat zadání“.
- **D, „Rozepsat zadání“ má pevnou stavbu:** celek → části v daném prostorovém pořadí s výslovnými slovy (vzadu, vlevo, před) → zase celek; poslední věta jmenuje styl a typ obrázku. K tomu pravidla z #9 bodu 2: fyzikální soudržnost, jen viditelné (žádné „krásný“), přesné počty, vágní přání → konkrétní změna.
- **B, překlad pokynu k úpravě vidí výřez rámečku** (≤ 512 px): objekt se pojmenuje podle toho, co v rámečku opravdu je, ne jen podle slova operátora. Klíč mezipaměti zahrnuje otisk výřezu. Výřez je v odhadu jako položka 0,002 USD (Haiku 5.5 za ~350 tokenů reálně ~0,0001 USD, odhad je s rezervou).
- **A, měření klíčových bodů** je skript `scripts/eval_keypoints.py`, ne funkce studia: vzorek anglických promptů, lokální FLUX zdarma, soudce Claude po bodech (verdikt = poslední accept/reject). Placený, bez `--confirm-cost` jen vypíše odhad. Při 20–30 promptech nečíst rozdíly pod ~10 p. b.

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
