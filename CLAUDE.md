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
- Známé limity: undo/redo vrací jen metadata (project.json), ne pixely vrstev (AI edit je pixel-nevratný — kandidát M3+); `/hittest` ignoruje width/height škálování vrstvy (task chip založen); SAM může validně vrátit 0 masek
- Další: M3 (trajektorie UI, kamera panel, prompt-compiled joby + pixel-diff verifikace klipu, přehrávač)

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

> GRAFIK Unified Editor — M3 (motion osa, sc-2 v prompt-compiled podobě).
>
> M2 (obrazová osa, sc-1) je HOTOVÁ a ověřená E2E klikáním v UI — viz sekce „Unified Editor — M2" výše, `docs/spikes/2026-08-14-m2-e2e-sc1.md` a `docs/plans/2026-08-14-phase1-gate.md`.
> Klíčová fakta: motion = prompt-compiled + pixel-diff verifikace (Kling dynamic_masks je mrtvá API cesta); qwen inpaint vrací max ~1536 px (resize-back povinný, viz LEARNINGS); `scripts/pixel_diff.py` existuje (reuse pro klip verifikaci); capability tvrzení jen z raw OpenAPI + empirického testu; fal tiše ignoruje neznámá pole. Testy jen přes `rtk proxy python -m pytest tests/ -q`.
>
> **Co implementovat (M3, ideal-state kritéria #6–#10 + video část #11):**
> 1. TrajectoryPath tool v ui-web — bezier křivka s draggable anchory na vybraném prvku (oficiální Konva vzor), persistence do Layer.motion (MotionSpec model existuje, project.json v2)
> 2. Camera panel (typ + velikost pohybu | volný prompt) → MotionSpec.camera
> 3. Kompilace MotionSpec → strukturovaný prompt (grafik/motion/compiler.py existuje) + zobrazená odhadovaná cena PŘED submitem
> 4. Job queue UI: submit → status polling → přehrávač klipu (routes `/video/jobs` + `GET /clips/{id}/video` existují; ClipRecord persistuje request_id)
> 5. Pixel-diff verifikace klipu vůči masce prvku („hýbalo se to, co mělo") + verifikační report u jobu + retry nabídka
> 6. Selhání jobu: čitelný důvod v UI, projekt nepoškozen (mock-fail test existuje — rozšířit o UI stav)
