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

- **API**: `uvicorn grafik.api.app:app --port 8200` nebo `grafik serve`
- **UI**: `streamlit run ui/app.py --server.port 8501` nebo `grafik ui`

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

> GRAFIK — Session 3: Implementace Fáze 3 (pokročilé funkce).
>
> Fáze 1 (MVP) + Fáze 2 (ops, workflows, export) jsou kompletní a ověřené.
> Package `grafik` v0.2.0 — 28 API routes, 5 ops modulů, 2 workflows, undo/redo, Streamlit UI.
>
> **Co implementovat (Fáze 3):**
> 1. T2L (text-to-layers) mód v fal klientu
> 2. Rekurzivní dekompozice (rozložit vrstvu dál)
> 3. Mask painting (streamlit-drawable-canvas)
> 4. fal.ai cost tracking
> 5. Batch workflow (složka obrázků)
> 6. Integrace do NG-ROBOT
