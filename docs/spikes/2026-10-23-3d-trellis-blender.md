# Spike 2026-10-23: 3D model z předlohy (TRELLIS 2) → Blender → lokální FLUX

Operátor: „zda TRELLIS, když vygeneruje z podkladových obrázků 3D správně, tak pak může dostat správně zadání i náš generátor … navíc se nám to hodí kdekoli, kde budeme vytvářet 3D scénu, ve spolupráci s Blenderem.“ Schválil Blender a nejvýš 2 běhy TRELLIS 2 po 0,30 USD.

Proč: lokální FLUX 3 Klein kreslil kvinqueremu deformovaně (dva stěžně, vesla různé délky, směru i rozestupu). Lepší prompt ani termdb tvar nespraví.

## Postup a výsledek

| Krok | Nástroj | Cena | Čas |
|---|---|---|---|
| 1. Výřez předlohy (světlé šedé pozadí → alfa, flood fill od okrajů) | `scripts/3d/cutout.py` | 0 | <1 s |
| 2. Obrázek → 3D (GLB, 21,6 MB, 1024p, seed 7) | fal `fal-ai/trellis-2`, `scripts/3d/trellis_run.py` | 0,30 USD | 88 s |
| 3. Import GLB, kamera, světlo, render 1280×720 | Blender 5.2.3 LTS headless, `scripts/3d/render_glb.py` | 0 | ~40 s / 8 pohledů |
| 4. Render jako `role: geometry` předloha, anglický prompt, `translate: off` | Engine, lokální FLUX 3 Klein (job `20261023-115724-5a9c21`) | 0 | ~2 min / 2 obrázky |

Celkem 0,30 USD (zapsáno v `library/costs.jsonl`, caller `spike-3d`). Druhý běh TRELLIS nebyl potřeba.

![předloha](img/2026-10-23-3d/1-predloha.jpg)
![TRELLIS, 8 pohledů z Blenderu](img/2026-10-23-3d/2-trellis-8-pohledu.jpg)
![render pro FLUX](img/2026-10-23-3d/3-blender-render.jpg)
![FLUX podle renderu](img/2026-10-23-3d/4-flux-podle-renderu.jpg)

## Zjištění

- **TRELLIS 2 udržel tvar ze všech stran:** jeden stěžeň s ráhnem, pravidelná vesla na obou bocích (stejná délka, úhel i rozestup), kloun, zakřivená záď, žádné slité tvary. Tenká vesla nezmizela, přestože jsme se toho báli.
- **FLUX podle renderu (geometry ref) tvar převzal:** jeden stěžeň a pravidelná vesla, loď na moři, materiály dřevo a bronz. Oproti dřívější generaci bez předlohy je to zásadní posun.
- **Model kopíruje předlohu, ne historii.** Předloha je zjednodušená stavebnicová loď s jednou řadou vesel na bok. Rekonstrukce kvinqueremy (Morrison) má tři řady vesel. Na historickou správnost je potřeba předloha s více řadami vesel, nebo doplnit řady vesel v Blenderu skriptem.
- Materiál z TRELLIS je lesklý tmavý plast; v Blenderu je potřeba světlejší svět (`Background` 2.0), slunce 5 a `view_transform = Standard`, jinak je render skoro černý.
- TRELLIS 2 bere jen jeden obrázek (`image_url`); `fal-ai/trellis/multi` (více pohledů) má nejasnou cenu „0,02 USD za jednotku“, nezkoušeno.
- Lokálně TRELLIS nepojede: Linux, ≥16 GB VRAM; notebook má RTX 4060 8 GB.

## Instalace

Blender 5.2.3 LTS portable: `C:/Users/stock/tools/blender-5.2.3-windows-x64/blender.exe` (zip z download.blender.org, SHA256 ověřený proti `blender-5.2.3.sha256`).

## Data

Model a předloha: `library/3d/kvinquerema-trellis2/` (`model.glb`, `model.json` s proveniencí, `predloha.png`, `render-az225.png`).

## Iterace 2: hliněný render, opravený korvus, věž a vesla (zdarma)

Operátor: věž a padací most se slily, styl má zůstat původní („nechci styl plastikové hračky z Blenderu“), korvus má mířit k boku (otočný), vesla mají divný tvar.

- `render_glb.py --clay`: všechny materiály nahradí jedna matná šedá, takže render nese jen tvar a poměry. Styl dodá prompt (muzejní model / realistická malba), ne textura z TRELLIS.
- `scripts/3d/edits_kvinquerema.py` (`--edit`): výška paluby paprsky shora; vyřízne slitý panel u přídě a stavebnicová vesla (|y| > 0,118); postaví korvus podle Polybia 1.22 (sloup na přídi, most zvednutý na 70° lanem z vrcholu sloupu, natočený o 35° k boku), čtvercovou věž s cimbuřím před stěžněm a tři řady rovných vesel (22 na řadu a bok, porty přesazené, listy v jedné čáře na hladině).
- Pohled azimut 300°, elevace 25°: příď vpravo jako v původní infografice.
- Lokální FLUX s hliněným renderem jako `geometry` předlohou: muzejní model (job `20261023-121208-3e0076`) i realistická malba na moři (job `20261023-121455-0b517a`) drží tvar, korvus i pravidelná vesla. 0 USD.

![hlína](img/2026-10-23-3d/5-hlina-opraveno.jpg)
![muzejní model](img/2026-10-23-3d/6-muzejni-model.jpg)
![realistická ilustrace](img/2026-10-23-3d/7-realisticka-ilustrace.jpg)

Zbývá: plachta, rozměry podle rekonstrukce (vesla jsou zatím odhad), řez lodí (TRELLIS dělá jen skořepinu, vnitřek se musí postavit v Blenderu).

## Iterace 3: loď z rozměrů rekonstrukce + silnější modely (0,51 USD)

Operátor: realistická ilustrace z lokálního FLUX „stojí za hovno“ (stěžeň jako sloup, ráhno jako párátko). Příčiny: poměry ze stavebnicové předlohy (TRELLIS je věrně okopíroval) a malý lokální model. Schválil stavbu v Blenderu z rozměrů a srovnání 2× FLUX.2 pro + 2× Nano Banana Pro do 0,65 USD.

`scripts/3d/lod_kvinquerema.py`: celá loď z čísel, každé číslo se zdrojem v `DIM`.

| Rozměr | Hodnota | Zdroj |
|---|---|---|
| délka | 45 m | Coates 1995, s. 138 |
| šířka u hladiny | 5 m | Coates 1995 |
| paluba nad vodou | 3 m | Coates 1995 |
| ponor | 1,3 m | odhad (Olympias 1,25 m) |
| vesla | 3 patra, 30 v řadě, 90 na bok, 2–2–1 veslaři | Morrison 1995, s. 69 |
| rozestup vesel | 0,98 m | odhad (Olympias 0,89 m) |
| stěžeň / ráhno / plachta | 13 m / 14 m / 12 × 8 m | odhad |
| korvus | sloup 7,2 m, most 10,8 × 1,2 m | Polybios 1.22 |
| kloun | 2,4 m, tři žebra | odhad (Athlit 2,26 m) |

Srovnání na stejném hliněném renderu (`8-model-z-rozmeru.jpg`):
- **FLUX.2 pro** (fal, 2 × 0,18 USD): bohatý detail, ale z vrženého stínu plachty na palubě udělal vymyšlený spuštěný můstek přes celou palubu a přidal falešný podpis vpravo dole.
- **Nano Banana Pro** přes Google (`nb-pro`): 402 Payment Required (fakturace účtu Google), nic nestál. Přes fal (`fal:fal-ai/nano-banana-pro`, 0,15 USD) jen 1 obrázek, aby se nepřekročil schválený strop: **nejvěrnější tvar** (tři řady vesel, nástavec, věž, korvus, kloun se žebry), nic nepřidal, čistá kresba, výstup 2752 × 1536.

![model z rozměrů](img/2026-10-23-3d/8-model-z-rozmeru.jpg)
![FLUX.2 pro](img/2026-10-23-3d/10-flux2pro-a.jpg)
![Nano Banana Pro](img/2026-10-23-3d/12-nbpro.jpg)

Řez (`scripts/3d/rez_kvinquerema.py`): hliněný model hotový (trup s žebry a kýlem, 3 patra veslařů 2–2–1, podpalubí, paluba, věž), světlo ještě doladit, pak stejnou cestou přes Nano Banana Pro.

![řez v hlíně](img/2026-10-23-3d/13-rez-hlina.jpg)

## Iterace 4: realističtější poměry (0,30 USD)

Operátor: loď moc úzká, postavy moc velké. Postavy v modelu měly 1,7 m, ale Nano Banana Pro si je zvětšil asi o polovinu (poměr k lodi odpovídal 31 m místo 45 m); loď byla úzká, protože 5 m (Coates, šířka u hladiny) jsem vzal skoro jako největší šířku a trup se zužoval už od poloviny.

- Model: paluba 5,8 m, 7 m přes nástavce (délka : šířka 6,4, Olympias 6,7), rovné boky v pásmu veslařů (|x| < 14 m), postavy 1,72 m, slunce bez vržených stínů.
- Kontrola před placenou kresbou: ortogonální půdorys a bokorys s kótami a kontrolní postavou vedle přídě (`scripts/3d/dims_overlay.py`).
- Prompt: výslovně „a man is 1.7 metres tall, about one twenty-sixth of the ship's length … do not enlarge them“.
- Nano Banana Pro přes fal, 2 obrázky (job `20261023-124017-ae4f4c`): postavy v měřítku (~1/27 délky lodi), širší loď, tři řady vesel, korvus, věž; druhý obrázek fotorealistický.

![kontrola rozměrů](img/2026-10-23-3d/14-kontrola-rozmeru.jpg)
![Nano Banana Pro, poměry](img/2026-10-23-3d/15-nbpro-pomery-1.jpg)

Útrata spike celkem: 0,30 (TRELLIS) + 0,36 (FLUX.2 pro) + 0,15 + 0,30 (Nano Banana Pro) = 1,11 USD.
