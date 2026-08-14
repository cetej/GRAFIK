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
- Další: M2 (mask brush, SAM segmentace v UI, per-prvek edit UI, export) → M3 (trajektorie UI, kamera panel, job status + přehrávač, klip verifikace)

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

> GRAFIK Unified Editor — M2 (obrazová osa komplet, sc-1).
>
> Fáze 1 walking skeleton je HOTOVÁ a ověřená (viz sekce Unified Editor výše + `docs/plans/2026-08-14-phase1-gate.md`).
> Klíčová fakta: motion = prompt-compiled + verifikace (Kling dynamic_masks je mrtvá cesta); inpaint vždy s paste-backem; capability data v `docs/capabilities/` (raw OpenAPI, verified_at).
>
> **Co implementovat (M2):**
> 1. Mask brush tool v ui-web (offscreen canvas ~50 řádků dle plánu)
> 2. SAM 3 segmentace z textu v UI (route `/segment` existuje)
> 3. Per-prvek AI edit v UI (route `/layers/{id}/ai-edit` existuje; provider switch qwen/flux/gpt-image-2)
> 4. Inpaint pozadí za vyjmutým prvkem
> 5. Propojení na existující ops/undo-redo, export PNG = náhled (pixel diff test)
> 6. Re-test A1 paste-back na 4K obrázku (zatím ověřeno jen na 544×736)
