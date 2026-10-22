# Rozhodnutí operátora — GRAFIK

Nejnovější nahoře. Každé rozhodnutí: datum, co, proč, odkud.

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
