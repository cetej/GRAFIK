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

### Fáze 2 — Operace + Workflows (TODO)
- [ ] `grafik/ops/recolor.py` — hue/sat/lum shift
- [ ] `grafik/ops/transform.py` — resize, rotate, translate
- [ ] `grafik/ops/blend.py` — blend modes (multiply, screen, overlay, soft_light)
- [ ] `grafik/ops/mask.py` — alpha mask editace
- [ ] `grafik/ops/replace.py` — náhrada obsahu vrstvy
- [ ] `grafik/core/history.py` — undo/redo (JSON snapshot stack, max 20)
- [ ] `grafik/workflows/base.py` — WorkflowBase pipeline runner
- [ ] `grafik/workflows/map_localization.py` — dekompozice mapy → swap textových vrstev → CZ
- [ ] `grafik/workflows/hero_edit.py` — separace subject/background → swap → composite
- [ ] `grafik/export/png.py` — composite + individual layers
- [ ] `grafik/export/psd.py` — PSD export (psd-tools)
- [ ] UI: inspector panel (recolor sliders, transform), workflow panel, undo/redo

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

- **API**: `uvicorn grafik.api.app:app --port 8100` nebo `grafik serve`
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

> GRAFIK — Session 2: Implementace Fáze 2 (ops + workflows).
>
> Fáze 1 MVP je kompletní a ověřená. Package `grafik` nainstalovaný, core/fal/api/cli/ui fungují.
>
> **Co implementovat:**
> 1. `grafik/ops/` — recolor, transform, blend, mask, replace (Pillow operace nad vrstvami)
> 2. `grafik/core/history.py` — undo/redo stack
> 3. `grafik/workflows/base.py` + `map_localization.py` + `hero_edit.py`
> 4. `grafik/export/` — PNG batched, PSD (psd-tools)
> 5. Nové API endpointy pro operace a workflows
> 6. UI rozšíření: inspector (recolor/transform), workflow panel, undo/redo
>
> Vzor pro API: `grafik/api/app.py` (stateless, load/save per request)
> Vzor pro UI: `ui/app.py` (httpx → FastAPI, st.session_state)
