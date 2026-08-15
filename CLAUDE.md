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

### Fáze 3 — Pokročilé (TODO)
- [ ] T2L (text-to-layers) mód v fal klientu
- [ ] Rekurzivní dekompozice (rozložit vrstvu dál)
- [ ] Mask painting (streamlit-drawable-canvas)
- [ ] fal.ai cost tracking
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

> GRAFIK Unified Editor — M4 (provider šíře + cost tracking).
>
> M2 (obrazová osa, sc-1) i M3 (motion osa, sc-2) jsou HOTOVÉ a ověřené E2E klikáním v UI — viz sekce „Unified Editor — M2/M3" výše, `docs/spikes/2026-08-14-m2-e2e-sc1.md`, `docs/spikes/2026-08-14-m3-e2e-sc2.md`, `docs/plans/2026-08-14-phase1-gate.md`.
> Klíčová fakta: capability tvrzení JEN z raw OpenAPI fetche + empirického testu (fal tiše ignoruje neznámá pole; jména polí driftují mezi verzemi — Kling 2.6 bere start_image_url; defaulty umí zdvojnásobit cenu — generate_audio:true); registry nese image_field/payload_defaults/duration_choices/est_cost_usd_per_second per endpoint; qwen inpaint vrací max ~1536 px (resize-back load-bearing); I2L decompose vrací vrstvy ~0,4 MP nativně — layout se škáluje na canvas ve `FalClient.decompose` (fix 2026-08-15); binární média přes FileResponse (Range/206); pixel-diff atribuce prvku nefunguje pod globální kamerou (viz LEARNINGS). Testy jen přes `rtk proxy python -m pytest tests/ -q`. Živá UI práce nad `e2e-*` projekty (decompose-test je testovací fixture).
>
> **Co implementovat (M4):**
> 1. NB Pro (Gemini) provider — generace vstupního obrázku / globální edity textem (pixel masku NEBERE — role: vstup, ne per-prvek edit); pozor SynthID watermark
> 2. FLUX Fill jako druhý inpaint provider (registry entry `flux-fill` existuje bez impl — doplnit impl třídu, stejný paste-back vzor jako QwenInpaintProvider) + UI přepínání už funguje přes registry
> 3. Rekurzivní dekompozice (rozložit existující vrstvu dál na sub-vrstvy)
> 4. Cost tracking souhrnně: per-projekt log placených volání (decompose/edit/segment/video) + zobrazení v UI
> 5. Kandidáti z M3 nálezů (vybrat dle priority): kamerově kompenzovaná verifikace klipu (optical flow / homografie před diffem), crop-based inpaint workflow pro jemné edity na velkých plátnech (qwen 1536px cap), verifikační maska ze stavu vrstvy v čase submitu
> 6. Selhání video jobu v UI: mock-fail test existuje (backend), rozšířit o UI stav (failed karta s důvodem se zobrazuje — přidat E2E/Playwright krok)
