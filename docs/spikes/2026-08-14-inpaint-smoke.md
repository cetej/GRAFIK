# Spike: Inpaint smoke test (Task 1.3) — fal-ai/qwen-image-edit/inpaint

Datum: 2026-08-14
Skript: `scripts/smoke_inpaint.py` (`--dry-run` pro bezplatný test pipeline, bez flagu pro reálné volání)
Ověřuje: **falsifier A1** (`docs/plans/2026-08-14-unified-editor.md`, řádek 58):
> "upscale masky (bilinear + threshold/feather) produkuje viditelné švy na hranicích editů → nutný SAM 3 refine masky v plném rozlišení."

## Zdrojová data

`C:/Users/stock/Documents/000_NGM/GRAFIK/projects/decompose-test.grafik` — canvas 544×736, 4 RGBA vrstvy (bottom→top):

| vrstva | id | alpha (mean/nonzero) | obsah |
|---|---|---|---|
| 0 | `5588a9f356b6` | 99,8 % (opaque) | pozadí — bokeh, titulní karta "ANATOMIE SPIKNUTÍ" |
| 1 | `53602ec6840f` | 0,4 % / 2,5 % | téměř neviditelná "ghost" vrstva (slabý duplicitní text) |
| 2 | `e64e0a36cfa9` | 61,5 % / 82,0 % | ilustrace římského senátu (schodiště, socha, senátoři) + boční textový panel |
| 3 | `7d30fcc59fa3` | 9,9 % / 42,8 % | **cílová vrstva** — kompaktní shluk senátorů kolem Caesara/Bruta + 4 popiskové cedulky (roztroušené, ne jeden souvislý blob) |

Kompozit (`inpaint_input.png`) potvrdil scénu: infografika o atentátu na Julia Caesara (15. březen 44 př. n. l.), shluk senátorů je ve spodní třetině plátna.

## 1. Schéma endpointu (WebFetch)

`fal-ai/qwen-image-edit/inpaint` — OpenAPI:

**Povinné:** `prompt` (string), `image_url` (string), `mask_url` (string)

**Volitelné (default):**
- `strength` = 0.93 (0.01–1) — síla noisingu pro inpaint
- `guidance_scale` = 4 (0–20) — CFG adherence k promptu
- `num_inference_steps` = 30 (2–50)
- `image_size` — `{width,height}` objekt (default 512×512) nebo string preset, nullable
- `enable_safety_checker` = true
- `output_format` = "png" ("jpeg"/"png")
- `negative_prompt` = " "
- `seed`, `num_images`=1 (1–4), `acceleration`="regular", `sync_mode`=false

**Response:** `images[]` ({url, width, height, content_type}), `timings`, `seed`, `has_nsfw_concepts[]`, `prompt`

Schéma explicitně nepopisuje sémantiku masky (white=edit?), ale odpovídá fal.ai standardní konvenci (bílá = oblast k editaci). Empiricky potvrzeno metrikami níže (uvnitř masky výrazně větší změna než mimo).

Použité parametry: `image_size={544,736}` explicitně (aby výstup seděl 1:1 na canvas), `enable_safety_checker=True` na prvním volání, `output_format=png`. Ostatní ponechány na defaultech.

## 2. Prompt

Po vizuální kontrole kompozitu zvolen prompt nahrazující shluk senátorů/Caesara jiným, tematicky sedícím objektem:

```
prompt: "Replace this area with a large bronze Roman eagle standard (aquila)
mounted on a tall marble pedestal, dramatic warm side lighting, detailed
painterly illustration style matching a historical Roman infographic,
no text, no people"

negative_prompt: "text, watermark, blurry, low quality, cartoon, modern
objects, people"
```

## 3. Maska — simulace produkční cesty

Vzato z alpha kanálu vrstvy 3 (`7d30fcc59fa3.png`, plné rozlišení 544×736):

1. downscale → 272×368 (bilinear)
2. upscale zpět → 544×736 (bilinear)
3. threshold @128 → binární (`binary`) — bbox alpha>12: `[34, 219, 332, 666]`, pokrytí 9,84 %
4. dilate ~4 px (`MaxFilter(9)`) → `dilated`, pokrytí 12,29 % — **tato binární verze poslána do API** (`inpaint_mask.png`)
5. feather ~2 px (`GaussianBlur(2)`) → `feathered` — použita jen pro paste-back, ne pro API

Vizuální kontrola `inpaint_mask.png` odhalila důležitý detail: maska **není jeden kompaktní blob** — alpha vrstvy 3 zahrnuje jak ilustraci (hlavní shluk), tak 4 samostatné popiskové cedulky ("Socha Pompeia Velikého", "Gaius Iulius Caesar", "Marcus Iunius Brutus", "Pompeiovo kurie") jako oddělené bílé oblasti. To je očekávané chování produkční cesty (maska = celý alpha kanál vrstvy), ne chyba skriptu.

## 4. API volání

1 z povolených 3 volání, uspělo napoprvé (`enable_safety_checker=True`, žádný retry nebyl potřeba):

- `seed`: 3197583600
- `has_nsfw_concepts`: `[false]`
- `timings.inference`: 6,17 s
- vrácená velikost: 544×736 — **shoda s canvasem, resize nebyl potřeba**

## 5. Metriky

### a) Raw diff mimo masku (`result` vs `input`, mimo `dilated` masku)
```
mean_abs_diff = 19,96   max_abs_diff = 251,0   pct_pixels_diff>8 = 47,88 %
```
→ Velký globální drift MIMO masku. Toto **není FAIL** (viz zadání) — je to očekávaný architektonický důsledek A1: paste-back je povinný krok, model nevrací čistě lokální edit.

### a2) Doplňkově — diff UVNITŘ masky (post-hoc, ze stejných souborů)
```
INSIDE  : mean=44,24  max=251,33  pct>8=82,3 %  pct>30=48,9 %  (n=49203 px)
OUTSIDE : mean=19,96  max=226,00  pct>8=47,9 %  pct>30=20,8 %  (n=351181 px)
```
→ Uvnitř masky je změna ~2,2× silnější než mimo ni (mean) a pct>30 je 2,35× vyšší → maska nebyla ignorována, měla reálný, měřitelný, silnější efekt v cílové oblasti.

### b) Paste-back sanity check (`final = input*(1-feathered) + result*feathered`)
```
mean_abs_diff = 0,095   max_abs_diff = 101,0   pct_pixels_diff>8 = 0,30 %
```
→ Prakticky nula, jak má být "by construction". Zbytkový `max=101` pochází z ~2px feather bleedu těsně za hranou `dilated` masky, kde surový diff byl lokálně extrémní (až 251) — očekávaný, zanedbatelný okrajový jev (0,3 % pixelů mimo masku).

### c) Seam check — gradient v hraničním prstenci
Prstenec = `dilate(dilated,+4px) AND NOT erode(dilated,-4px)` (~8px pás na hranici masky, 16 805 px):
```
final_grad_mean  = 9,64
input_grad_mean  = 9,32
ratio             = 1,035   (práh pro OK: < ~1,5)
```
→ Gradient na hranici po paste-backu je prakticky totožný s originálem → žádný ostrý šev.

## 6. Vizuální kontrola

**`inpaint_result_raw.png`** (surový výstup): Model změnil **celé plátno**, ne jen masku — titulek "ANATOMIE SPIKNUTÍ", boční seznam s odrážkami i popisky mimo masku jsou po výstupu vizuálně rozostřené/rozházené (nečitelné, "glitch" text), celý obraz má jiný barevný grading (tmavší, teplejší kontrast). Shluk senátorů uvnitř masky **nebyl nahrazen** orlicí dle promptu — kompozice (senátoři + Caesar + červená šipka) zůstala rozpoznatelně stejná, jen restylovaná/rozostřená. Prompt tedy dosáhl slabé adherence k požadované záměně objektu.

**`inpaint_final.png`** (paste-back): Mimo masku je obraz **beze změny** — titulek, boční panel i cedulka "Pompeiovo kurie (vpravo)" (mimo masku) jsou opět ostré a čitelné přesně jako v originále. Uvnitř masky je vidět jemně rozostřená/restylovaná verze shluku senátorů (barevně teplejší, měkčí), dvě cedulky uvnitř masky ("Gaius Iulius Caesar", "Marcus Iunius Brutus") mají nečitelný/rozsypaný text — očekávané, prompt nežádal jejich zachování. **Na hranici masky není vidět žádný ostrý lem, halo ani duchová kontura** — přechod mezi vygenerovanou oblastí a okolním mramorovým schodištěm je hladký (obě strany sdílí podobnou teplou kamennou paletu). Jediný postřehnutelný rozdíl zblízka je mírně nižší ostrost/detail uvnitř masky oproti okolní originální ilustraci — to je otázka kvality obsahu, ne artefakt švu.

**`inpaint_diff_heatmap.png`** (|raw−input|×4): Prakticky **celé plátno "svítí"** — hrany titulku, bočního panelu i pozadí jsou zvýrazněné stejně intenzivně jako oblast masky. Vizuálně potvrzuje metriku (a): drift je globální, ne lokalizovaný na masku.

## 7. Verdikt A1

Kritéria ze zadání:
- (i) oblast se reálně změnila dle promptu → **částečně**: uvnitř masky je změna ~2,2× silnější než mimo (maska evidentně nebyla ignorována), ale požadovaná záměna objektu (orlice) se plně neprosadila — model spíš restyloval než nahradil obsah.
- (ii) paste-back má nulový diff mimo masku → **ANO** (mean 0,095; 0,30 % px >8 — v podstatě nula, drobný feather-bleed na okraji)
- (iii) žádný viditelný šev + gradient ratio < 1,5 → **ANO** (ratio 1,035; vizuálně čistý přechod)
- FAIL podmínky (viditelný šev/halo po paste-backu, nebo maska ignorována) → **nenastaly**

## VERDICT: A1 PASS

Paste-back v pixel prostoru **je povinný** (přesně jak plán předpokládal jako "expected architecture consequence") — surový výstup endpointu kontaminuje celé plátno včetně vzdáleného textu, ne jen okolí masky. Po paste-backu s feather 2px + dilate 4px je hranice needitelná od originálu (gradient ratio 1,035, žádný vizuální lem). **SAM 3 refine masky není nutný kvůli kvalitě švu** na tomto rozlišení (544×736) — bilineární upscale + threshold + dilate 4px + feather 2px stačí.

## Doporučení pro M2

1. **Paste-back mandatory** — nikdy nespoléhat na přímý výstup endpointu jako finální vrstvu; vždy vrátit editovaný obsah zpět do canvasu přes feathered masku v pixel prostoru klienta.
2. **Feather 2px + dilate 4px stačí** na 544×736; při vyšších rozlišeních (4K vrstvy z M2) doporučeno ověřit stejný test znovu — gradient ratio je citlivý na rozlišení masky vs. canvasu.
3. **Prompt adherence pro plnou záměnu objektu je slabá** při defaultech (`strength=0.93`, `guidance_scale=4`) — pro budoucí per-prvek "replace" workflow (sc-1) zvážit vyšší `guidance_scale` (~7–10) a/nebo explicitnější prompt ("empty pedestal, no figures, remove all people") — doporučen follow-up smoke test před spoléháním na čistou záměnu objektu.
4. **Text/cedulky uvnitř masky nejsou zachovány** (očekávané, ne bug) — pokud budoucí per-prvek edit sdílí masku s popiskem, který má zůstat čitelný, je potřeba masku zúžit (SAM 3 nebo ruční refine), jinak se popisky poškodí jako vedlejší efekt.

## Výstupní soubory

- `scratch/smoke/inpaint_input.png` — kompozit 4 vrstev (RGB, 544×736)
- `scratch/smoke/inpaint_mask.png` — maska poslaná do API (dilated hard binary)
- `scratch/smoke/inpaint_result_raw.png` — surový výstup endpointu
- `scratch/smoke/inpaint_final.png` — paste-back výsledek (feathered mask)
- `scratch/smoke/inpaint_diff_heatmap.png` — |raw−input|×4 heatmapa
