# GRAFIK — Modulární grafický editor s vrstvami

Univerzální nástroj pro práci s obrázky rozloženými na RGBA vrstvy pomocí Qwen-Image-Layered (fal.ai API).

## Architektura

```
GRAFIK/
├── grafik/                  # Python package (pip install -e .)
│   ├── core/                # Layer, LayerProject, Composer
│   ├── fal/                 # fal.ai klient (decompose I2L, upload)
│   ├── ops/                 # ⏳ operace (recolor, transform, blend, mask)
│   ├── workflows/           # ⏳ předpřipravené workflow (map localization, hero edit)
│   ├── export/              # ⏳ PNG, PSD export
│   ├── api/                 # FastAPI backend (port 8100)
│   └── cli/                 # Typer CLI → `grafik` command
├── ui/                      # Streamlit frontend (port 8501)
└── projects/                # .grafik project directories
```

## Stav implementace

### Fáze 1 — MVP (HOTOVO)
- [x] Core: Layer model (Pydantic), LayerProject (.grafik formát), Composer (Pillow)
- [x] fal.ai: FalClient (decompose I2L, upload, download)
- [x] API: FastAPI — projects CRUD, decompose, layers, composite, export PNG
- [x] CLI: decompose, layers, composite, serve, ui
- [x] UI: Streamlit — 3-sloupcový layout (vrstvy | náhled | inspector)
- [x] Ověřeno: pip install, importy, kompozice, API start

### Fáze 2 — Operace + Workflows (HOTOVO)
- [x] `grafik/ops/recolor.py` — hue/sat/lum shift, grayscale, invert
- [x] `grafik/ops/transform.py` — resize, scale, rotate, flip, crop
- [x] `grafik/ops/blend.py` — blend modes (multiply, screen, overlay, soft_light) via numpy
- [x] `grafik/ops/mask.py` — alpha mask: feather, threshold, set_opacity, apply_mask, extract
- [x] `grafik/ops/replace.py` — náhrada obsahu vrstvy (cover/contain/stretch/none)
- [x] `grafik/core/history.py` — undo/redo (JSON snapshot stack, max 20, persist to file)
- [x] `grafik/core/composer.py` — blend modes integrated (NORMAL + 4 advanced)
- [x] `grafik/workflows/base.py` — WorkflowBase pipeline runner
- [x] `grafik/workflows/map_localization.py` — dekompozice mapy → identifikace textu → swap → composite
- [x] `grafik/workflows/hero_edit.py` — separace subject/background → swap → composite
- [x] `grafik/export/png.py` — composite + individual layers + export_all
- [x] `grafik/export/psd.py` — PSD export (psd-tools, optional dependency)
- [x] API: 28 routes — recolor, blend_mode, flip, scale, mask, undo/redo, workflows/run, export/layers
- [x] UI: inspector (recolor sliders, blend mode, transform, flip, scale, mask ops), workflow panel, undo/redo

### Unified Editor — Fáze 1 walking skeleton (HOTOVO, 2026-08-14)
Plán: `docs/plans/2026-08-14-unified-editor.md` · Gate: `docs/plans/2026-08-14-phase1-gate.md` · Capability data: `docs/capabilities/`
- [x] Konva spike GO (50 FPS drag na 5× 4K RGBA) → ui-web/ (Vite+React+react-konva)
- [x] Inpaint smoke PASS — **paste-back povinný** (viz LEARNINGS)
- [x] Kling motion smoke FAIL — `dynamic_masks` je mrtvá API cesta; **motion = prompt-compiled + pixel-diff verifikace** (upravená A3)
- [x] `grafik/providers/` — capability registry (verified_at per endpoint), QwenInpaintProvider
- [x] MotionSpec + project.json **v2** (schema_version, Layer.motion, clips[]) — v1 projekty se načtou beze změny
- [x] `grafik/motion/` — prompt compiler + async video jobs (persistovaný request_id)
- [x] API: `/layers/{id}/ai-edit`, `/segment` (SAM 3), `/video/jobs` (+ mock-fail test — selhání nepoškodí projekt)
- [x] ui-web editor MVP: load projektu, Transformer + alfa hit-test, persistence transformací
- **Pravidlo: Streamlit UI je zmrazený (bugfix-only). Nové featury jen ui-web (React).**

### Unified Editor — M2 obrazová osa komplet, sc-1 (HOTOVO, 2026-08-14)
E2E důkaz: `docs/spikes/2026-08-14-m2-e2e-sc1.md` (13/13 kroků klikáním v UI) · 4K re-test: `docs/spikes/2026-08-14-inpaint-4k.md`
- [x] API: `GET /api/providers` (capabilities + has_impl), `ai-edit` s volitelnou `mask_b64` (brush maska → MERGE do vrstvy; bez masky replace jako dřív), `POST /layers/{id}/inpaint-behind` (vyplnění pozadí za prvkem do nejnižší viditelné vrstvy), `POST /layers/{id}/reorder`, provider/segment faily → 502 s důvodem, `/transform` snapshotuje pro undo (E2E nález)
- [x] Composer: rotace = Konva sémantika (cw kolem kotvy x,y, offset z rotovaných rohů)
- [x] ui-web editor: toolbar (Select/Brush/Segment, Undo/Redo, Inpaint behind, Export PNG, New from image → dekompozice), panel vrstev (z-order ▲▼, delete, sam badge), brush tool (offscreen canvas v plném rozlišení, export jako mask_b64), inspector (AI edit prompt + provider switch dle registry, inpaint-behind, SAM segment z textu), busy/error stavy, png cache-busting po mutacích
- [x] E2E sc-1 klikáním: dekompozice → výběr klikem → posun/scale → AI edit → inpaint pozadí → export; pixel-diff export vs composite **0,0**, export vs živý náhled mean **0,72** (kritérium #5); 4 placená volání, 0 console errors
- [x] A1 paste-back re-test na 4K (2862×3872): PASS (outside 0,024, ring 1,063) + **empirický nález: qwen inpaint vrací max ~1536 px → resize-back v provideru je load-bearing** (viz LEARNINGS)
- Testy: 67 pytest (offline, monkeypatched) + `node ui-web/editor-verify.mjs` (potřebuje běžící servery; placené kroky jen 1×, `--skip-paid` reuse)
- Známé limity: undo/redo vrací jen metadata (project.json), ne pixely vrstev (AI edit je pixel-nevratný — kandidát M3+); SAM může validně vrátit 0 masek
- Fix (2026-08-14): `/hittest` nyní invertuje transformační model composeru (un-translate → inverzní rotace kolem kotvy → rescale layout→nativní px) — shoduje se s klientským Konva hit-testem i při width/height ≠ rozměry PNG a rotaci; regresní testy `tests/test_api_hittest.py`

### Unified Editor — M3 motion osa komplet, sc-2 (HOTOVO, 2026-08-14)
E2E důkaz: `docs/spikes/2026-08-14-m3-e2e-sc2.md` (klikáním v reálném Chrome, 1 placený klip $0.50) · master `071dc56` + `01eb06a` + `a732042`
- [x] Providers registry: per-endpoint payload mapping — `image_field` (Kling 2.6 pro bere **start_image_url**!), `payload_defaults` (`generate_audio:false` u Kling/Seedance — default true = 2× cena; `resolution:"720p"` + `enable_prompt_expansion:false` u Wan), `duration_choices`, `est_cost_usd_per_second`; nový **wan-26** entry (`wan/v2.6/image-to-video`, slug bez `fal-ai/`); vše z raw OpenAPI, viz addenda v `docs/capabilities/`
- [x] API: `POST/DELETE /layers/{id}/motion` (persist Layer.motion + undo snapshot), `POST /video/compile` (prompt preview + odhad ceny PŘED submitem), `VideoJobRequest.prompt_override` (editovaný prompt), `POST /clips/{id}/verify`, `LayerResponse.motion`; `/clips/{id}/video` přes FileResponse (**Range/206 — bez toho Chromium `<video>` nehraje**)
- [x] `grafik/motion/verify.py`: pixel-diff verifikace klipu — imageio-ffmpeg streaming sampling (5 framů), maska prvku přes single-layer compose (sdílí transformační model s rendererem), in/out mask diff → verdikt yes/weak/no per prvek (wanted move/still), česká summary; ClipRecord.verification
- [x] ui-web: Motion tool (klik do plátna přidá bod trajektorie — výběr přes panel vrstev, celoplošné pozadí pohltí „klik do prázdna"; Konva Arrow tension 0.5 + tažitelné kotvy), MotionPanel (kamera typ+velikost / vlastní prompt, provider+duration z registry, kompilovaný prompt editovatelný + cena), ClipsPanel (status chipy, polling 15 s, auto-verify po dokončení, verdikt chipy dle wanted, `<video>` přehrávač, Retry předvyplní), status strip počet běžících
- [x] E2E sc-2 klikáním nad `e2e-sc1.grafik` (tentýž projekt jako sc-1 → sc-3 ✓): trajektorie 3 body persistovaná → kamera zoom_in 0,25 → preview „~$0.50" → prompt edit (override) → Wan 2.6 720p/5 s → polling → mp4 v `.grafik/clips/` → auto-verifikace (in 52,5 / out 55,5 / ratio 0,95 → „hýbalo se slabě" — poctivá ne-atribuce pod globálním zoomem, viz LEARNINGS) → přehrání (5,01 s, readyState 4)
- Testy: 107 pytest (offline; test_api_m3 19, test_motion_verify 15; fixture test_api_m2 pinuje baseline sdíleného decompose-test projektu)
- Známé limity: atribuce prvku pod globální kamerou → verdikt „weak" (kompenzace = M4 kandidát); tažení kotvy trajektorie neověřeno syntetickým CDP dragem (Konva potřebuje reálný pointer stream — vzor shodný s M2-ověřeným dragem vrstev); verifikační maska = aktuální stav vrstvy (verify hned po dokončení)
- Další: M4 (provider šíře + cost tracking)

### Unified Editor — M2.5 UX/discoverability (HOTOVO, 2026-08-15)
E2E důkaz: `docs/spikes/2026-08-15-m25-e2e.md` (klikáním v reálném Chrome, 4 placené SAM cally ~$0.02) · master `540f196`…`049fc6d`
- [x] Onboarding: empty-state dropzone na plátně („Začněte obrázkem" + Nahrát nový obrázek), drag&drop obrázku kamkoliv na canvas → nový projekt + dekompozice; „Nový z obrázku" primární tlačítko; label „Rozložit na N vrstvy/vrstev"
- [x] Správa projektů v panelu: řazení dle updated_at desc + datum, inline přejmenování (✎), duplikace (⧉ — nové id, bez history.json: snapshoty nesou zdrojové id), mazání (🗑 + potvrzení); backend PATCH /api/projects/{id}, POST /duplicate, DELETE + _histories cleanup; create_project uniquifikuje adresář (2× stejné jméno ≠ přepsaný manifest)
- [x] **Klik-segmentace**: Segment mód → klik do plátna → SAM-3 point_prompts → nová vrstva (vybraná); **past: klíč `prompt` VŽDY, pro point-only `""`** — vynechaný klíč = server dosadí schema default „wheel" → 0 masek (raw OpenAPI + empirie: `docs/capabilities/sam3-point.md`); point maska je part-level (celý objekt = víc bodů/box/text — M4 kandidát)
- [x] Layer rename dvojklikem (inline, persist + undo snapshot); Inspector sekce „Segmentace textem" + tip na klik-segmentaci
- [x] Počeštění celého ui-web (nástroje Výběr/Štětec/Segmentace/Pohyb, Zpět/Znovu/Vyplnit pozadí, statusy, bannery, potvrzení; vykání)
- [x] First-run hint overlay (jednorázový, localStorage `grafik.firstRunHint.v1`)
- [x] Upload chybová cesta: nevalidní obrázek → čitelný 400 (neošetřený 500 obchází CORSMiddleware → „Failed to fetch")
- Testy: 119 pytest (12 nových `tests/test_api_m25.py` — synteticky, bez fixture závislosti)
- ⚠️ Incident: během E2E ztracen projekt openart (mechanismus neprokázán; záloha `projects-backup-*`, API nově s access logem `logs/uvicorn-*.log`, zdroják v Downloads → obnovitelný re-decompose) — viz spike + LEARNINGS; M4 kandidát soft-delete
- Provoz: uvicorn spouštět s access logem (`--access-log` + redirect do `logs/`)
- Fix (2026-08-15): decompose velkého obrázku už nenechává obsah v levém horním rohu — I2L vrací vrstvy v nativním rozlišení (~0,4 MP, 544×736 pro 3:4), ne v rozlišení uploadu; `FalClient.decompose` nyní roztáhne layout vrstev (width/height) na canvas projektu (pixel data nativní, composer resizuje — stejná hranice jako inpaint resize-back), canvas z fal výstupu jen když nebyl → staré projekty (canvas == 544×736) beze změny. Testy `tests/test_api_decompose_canvas.py` (123 pytest celkem), viz LEARNINGS „Qwen I2L decompose: vrstvy v nativním rozlišení"

### Unified Editor — M4 provider šíře + ochrana dat + cost tracking (HOTOVO, 2026-08-15)
E2E důkaz: `docs/spikes/2026-08-15-m4-e2e.md` (klikáním v reálném Chrome, 5 placených volání $0.34 dle vlastního ledgeru — self-test trackingu) · master `063ec66`…
- [x] **Koš (soft-delete)**: DELETE projektu → `projects/.trash/<ts>-<dir>/` (žádné rm; history.json + costs.jsonl putují s adresářem), `GET /api/trash`, `POST /api/trash/{entry}/restore` (uniquifikace jména; openart-defense: kolize id → nové id), `DELETE /api/trash` (vysypat), auto-úklid >30 dní při listingu; destruktivní operace → `logs/destructive.jsonl`; UI sekce Koš (počet po sbalení, obnovit ↩, vysypat s potvrzením). Incident zálohy `projects-backup-*` smazány po ověření koše.
- [x] **Cost tracking**: `grafik/core/costs.py` — per-projekt `.grafik/costs.jsonl` + in-process session akumulátor; jediný zápisový bod `tracked_subscribe` (`grafik/fal/client.py`) + `record_paid_call` pro async submit (video) a NB Pro; atribuce = explicitní project_dir NEBO contextvar nastavený v `_load_project` (per-request context); odhady z registry — nová pole `est_cost_usd_per_mp/_per_call` (fal model pages + ai.google.dev, fetch 2026-08-15: I2L $0.05/call, qwen-inpaint $0.03/MP, flux-fill $0.05/MP, SAM $0.005/req, NB Pro $0.134/img 1K-2K); routy `GET /projects/{id}/costs`, `GET /costs/session`, `POST /projects/{id}/costs` (attach před-projektové generace); duplicate čistí costs.jsonl kopie; UI panel Útrata (projekt + session + poslední položky) + chip ve status stripu; neznámá sazba → est_usd=null, nikdy odhad vydávaný za fakt.
- [x] **NB Pro (image_gen)**: nový kind `image_gen`, `NanoBananaProProvider` — Gemini REST přes httpx (bez SDK závislosti), stabilní alias `nano-banana-pro-preview`, klíč GEMINI_API_KEY/GOOGLE_API_KEY/GOOGLE_GEMINI_API_KEY + **read-only fallback na NG-ROBOT `.env`** (dotenv_values, nic se nekopíruje); chybějící klíč → čitelná 503; `POST /api/generate-image` (aspect_ratio, image_size 1K/2K — 4K jen API, jiná cena mimo registry est); UI modal Vygenerovat (toolbar + empty-state) → náhled → Převzít = create + attach cost + standardní decompose flow. POZOR: nebere pixel masku, vkládá SynthID → jen vstupní generace, ne per-prvek edit.
- [x] **FLUX Fill impl**: `FluxFillProvider` — payload dle raw OpenAPI (2026-08-15): required prompt+image_url+mask_url, output_format default jpeg → posíláme png, safety_tolerance "2", bez image_size pole (resize-back guard); sdílí dilate/feather/paste-back helpery s qwen. **Fill sémantika: model NEVIDÍ obsah masky → prompt popisuje cílový obsah díry; na recolor je qwen-inpaint (edit-style)** — viz LEARNINGS.
- [x] **Rekurzivní dekompozice**: `POST /layers/{id}/decompose` — I2L nad pixel daty vrstvy, podvrstvy zdědí layout quad (x/y/w/h/rotation) a nahradí původní v z-orderu (splice + reindex); původní PNG zůstává na disku → undo (metadata snapshot) je i pixelově úplné; UI Inspector sekce Rozložit vrstvu (2–6 podvrstev, cena v hintu).
- [x] **Fix (E2E nález)**: ai-edit a inpaint-behind stavěly masku/crop-back v NATIVNÍM prostoru PNG — po M2.5 fixu (nativní ~0,4 MP ≠ layout na canvas) maska mířila do levého horního rohu a vrstvu přepsal zmenšený výřez; opraveno na layout-space (`f6a0cba`) + 2 regresní testy s native≠layout. Třetí výskyt této třídy (hittest M2, decompose M2.5) → pravidlo v LEARNINGS „Layout quad".
- Testy: 147 pytest (24 nových `tests/test_api_m4.py`).
- Známé limity: generate modal bez referenčních obrázků (NB Pro je umí — M5 kandidát); session útrata se nuluje s restartem API procesu (ledger na disku drží); rotace vrstvy se v ai-edit masce neřeší (dekompozice startuje na rotation 0); SynthID watermark ve vygenerovaných vstupech.

### Unified Editor — M5 přesnost výběru + kvalita editů (HOTOVO, 2026-08-15)
E2E důkaz: `docs/spikes/2026-08-15-m5-e2e.md` (klikáním v reálném Chrome, $0.88 dle vlastního ledgeru) · master `705b887`…`3a874d3` + doc commity
- [x] **SAM celý objekt**: box-drag (dashed overlay) → `box_prompts`, Shift+klik multi-point + Enter (`object_id: 0` seskupí body k jednomu objektu), Escape čistí; **`apply_mask: false` VŽDY** — s defaultem true vrací `masks[]` CUTOUT obrazu, ne masku (Pearson alfa×jas 1.000; třetí člen rodiny „fal tiché defaulty", viz LEARNINGS + `docs/capabilities/sam3-point.md`); box → celý lev binárně 11,45 %, 2 body → 10,07 %, single point zůstává part-level
- [x] **Crop-based inpaint** (qwen + flux-fill): maska bbox <25 % plochy a plátno >1536 px → crop bbox+margin (max(64, 25 % delší strany)) v plném rozlišení, resize-back guard vůči cropu, paste do kopie, povinný paste-back beze změny; kw `crop_inpaint=True` (UI checkbox v inspektoru); E2E na 2K: ledger mp 1.264 (vs 4.30 plné plátno), diff mimo masku 0.0000, mech ostrý (crop 1225 px < 1536 → žádný upscale)
- [x] **Kamerově kompenzovaná verifikace klipu**: ORB+RANSAC po sousedních párech (RANSAC vyřazuje pohybující se prvky) → kompozice na frame 0 → ECC refinement; 13 vzorků, jasový offset z mediánu pozadí, validity mask okrajů; `global_motion` zůstává RAW, nově `residual_global_motion`, `camera_compensated`, `compensated_frames`, `mask_source`; ECC-only slepá ulička zdokumentována (near-identity minimum na ~3,5× generativním zoomu — LEARNINGS)
- [x] **Verifikační maska ze submitu**: jobs.py mintí clip_id před submitem, ukládá `clips/<id>-mask-<layer>.png`, `ClipRecord.mask_paths`; verify je preferuje (fallback current pro staré klipy)
- [x] **NB Pro reference**: `generate(reference_images=…)` max 3, downscale 1536, PNG inlineData parts za textem; routa `reference_b64` (400 >3/nevalidní); modal: soubor/„+ kompozit projektu"/„+ vybraná vrstva", náhledy s ×, klientský downscale 1024; E2E: tentýž lev v zimě, ledger note „+1 ref"
- [x] **Koš per-entry**: `DELETE /api/trash/{entry}` + UI 🗑 per položka (destructive log `trash-purge-entry`); undo po restore FUNGUJE (history.json cestuje s adresářem — ověřeno testem, ne jen tvrzením)
- [x] **UI hinty**: fill-vs-edit u přepínače provideru (qwen = ÚPRAVA stávajícího / flux-fill = co má VZNIKNOUT), segment lišta „Klik = část · tažení = rámeček · Shift+klik = víc bodů, Enter potvrdí"
- [x] **Failed video job E2E**: bogus request_id → poll → karta SELHALO s verbatim důvodem (`{"status":"NOT_FOUND"}`)
- E2E akceptace: klip s kamerou zoom_in 0,25 + pohyb lva → **„hýbalo se ✓" (in 46,4/out 33,7/ratio 1,38, maska ze submitu, 12/12 snímků)**; M3 klip re-verify: 0,95 „weak" → 1,94 „yes"
- Testy: 193 pytest (46 nových: crop 17, verify 11, api 14, nbpro 4)
- Známé limity: velký objekt (lev, bbox 26,6 %) crop nespustí — práh 0.25 konzervativní (M6 zvednout dle potřeby); session útrata se nuluje restartem API (projektový ledger drží); residual na generativním footage neklesá k nule (obsah morfuje — atribuce funguje i tak); poll klipů jede nad in-memory seznamem (externě dopsaný klip až po reloadu projektu)

### Fáze 3 — Pokročilé (TODO)
- [ ] T2L (text-to-layers) mód v fal klientu
- [ ] Mask painting (streamlit-drawable-canvas)
- [ ] STOPA skill (`/grafik`)
- [ ] Batch workflow (složka obrázků)
- [ ] Integrace do NG-ROBOT

## Konvence

- Python package `grafik`, importovatelný z jiných projektů (`from grafik import LayerProject, FalClient, compose`)
- Formát projektu: `.grafik` adresář (project.json + layers/*.png)
- API je stateless — každý request načte/uloží projekt z disku
- Pixel data se nedrží v Pydantic modelech — načítají se on-demand přes `layer.load_image()`
- fal.ai API klíč v `.env` nebo `FAL_API_KEY` env var
- Encoding: UTF-8 všude
- Cesty: `pathlib.Path()`

## Servery

- **API**: `uvicorn grafik.api.app:app --port 8300` nebo `grafik serve`
- **ui-web (React editor)**: `npm --prefix ui-web run dev` → port 5173 (primární UI)
- **UI (Streamlit, frozen)**: `streamlit run ui/app.py --server.port 8501` nebo `grafik ui`

## Testy

- `rtk proxy python -m pytest tests/ -q` (POZOR: bez `rtk proxy` hook maskuje výstup — viz LEARNINGS)

## Použití jako knihovna

```python
from grafik import LayerProject, compose
from grafik.fal.client import FalClient

client = FalClient()  # čte FAL_API_KEY z env
project = LayerProject.new("moje-mapa", 1920, 1080)
layers = client.decompose("https://example.com/map.jpg", num_layers=4, project=project, project_dir=path)
project.save(path)
composite = compose(project, path)
composite.save("output.png")
```

## Resume prompt

> GRAFIK Unified Editor — M6 (režim „používat a ladit z reálné potřeby").
>
> M2–M5 jsou HOTOVÉ a ověřené E2E klikáním — viz sekce „Unified Editor — M2…M5" výše a `docs/spikes/2026-08-15-m5-e2e.md`.
> Klíčová fakta: capability tvrzení JEN z raw OpenAPI + empirie — fal (1) tiše ignoruje neznámá pole, (2) tiše doplňuje vynechané klíče (SAM `prompt` VŽDY), (3) **flagy tiše mění SÉMANTIKU výstupu (SAM `apply_mask: false` VŽDY — jinak `masks[]` = cutout obrazy, ne masky)**; **každá canvas-space operace nad vrstvou používá LAYOUT quad, nikdy nativní rozměr PNG** (fix `f6a0cba`); fill modely (flux-fill) NEVIDÍ obsah masky — prompt popisuje cílový obsah díry, na recolor qwen-inpaint (edit-style); qwen inpaint cap ~1536 px → crop-based inpaint default on (práh bbox <25 % plochy, `crop_inpaint` kw); verifikace klipu = ORB+RANSAC řetěz + ECC refinement + jasový offset, masky ze submitu (`ClipRecord.mask_paths`), magnitude kamery je přání ne měřítko (0,25 → model klidně 3,5×); NB Pro $0.134/img, reference max 3 (`reference_b64`), bez pixel masky, SynthID; placené cally jediným zápisovým bodem `tracked_subscribe`/`record_paid_call` → `.grafik/costs.jsonl`. Testy jen `rtk proxy python -m pytest tests/ -q` (193). UI verifikace v reálném Chrome (claude-in-chrome MCP: `window.confirm` → ()=>true; Konva gesta syntetickými MouseEventy na `.konvajs-content` s čerstvým getBoundingClientRect + sleep mezi eventy — CDP drag nefunguje, layout se hint řádkem posouvá; úspěch přes `window.__editorState.busy`; CDP screenshot umí 1× timeoutnout — retry). Servery z hlavního checkoutu, uvicorn vždy `--access-log` do `logs/`. Živá UI práce nad `e2e-*` projekty.
>
> **Kandidáti M6 (vybírat dle reálné potřeby při používání, ne dopředu):**
> 1. T2L (text-to-layers) experiment — srovnat kvalitu/cenu s pipeline NB Pro→I2L
> 2. Mask painting (pokročilejší malování masek)
> 3. Batch workflow (složka obrázků)
> 4. STOPA skill `/grafik`
> 5. Integrace do NG-ROBOT
> 6. Zbytky z M5: práh crop-inpaintu pro velké objekty (0.25 → ?), obnova in-memory undo po restore (id-kolizní edge), rotace vrstvy v ai-edit masce, per-entry purge → hromadný výběr, NB Pro 4K (jiná cena, mimo registry est)
