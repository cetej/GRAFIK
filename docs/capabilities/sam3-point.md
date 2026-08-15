# SAM-3 point prompty (fal-ai/sam-3/image) — ověřeno 2026-08-15

**Schema (raw OpenAPI, jediný zdroj pravdy):**
`curl "https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/sam-3/image"`

- `point_prompts`: pole `PointPrompt {x: int, y: int, label: 0|1, object_id, frame_index}` — souřadnice v pixelech nahraného obrázku (fal upload rozměry zachovává, takže canvas px == composite px == upload px)
- `box_prompts`: pole `BoxPrompt {x_min, y_min, x_max, y_max, object_id}` (zatím nevyužito)
- `prompt`: string, **schema default `"wheel"`** ← past, viz níže
- `return_multiple_masks` (default false), `max_masks` (1–32, default 3), `apply_mask` (default true)
- výstup: `masks[]` (Image objekty s url), `image` (preview), volitelně `scores`/`boxes`

## Empirické chování point módu (2 placené cally, composite e2e-sc1 544×736, bod (272,400) = socha)

| Varianta payloadu | Výsledek |
|---|---|
| A) `point_prompts` bez klíče `prompt` | **masks=0, image=null** — server dosadí default `"wheel"`, textová detekce nenajde nic a body se nemají k čemu vztáhnout |
| B) `point_prompts` + `prompt: ""` | **masks=1**, bbox (255,377,285,422), klik uvnitř bboxu — čistá point segmentace funguje |

**Pravidla pro implementaci (`grafik/api/app.py::_segment_remote`):**
1. Klíč `prompt` posílat VŽDY — pro point-only mód explicitně `""`. Vynechání klíče ≠ „bez text promptu"; schema default se tiše dosadí (rozšíření pravidla „fal tiše ignoruje neznámá pole": fal si i tiše *doplňuje* známá pole).
2. Granularita: point mask je **part-level** (těsně kolem kliknutého detailu, zde ~30×45 px na soše ~11 % plátna) — SAM s jedním bodem vrací část objektu, ne celý objekt. Pro objekt-level masku: více bodů se stejným `object_id`, box prompt, nebo textový prompt (kandidát M4+).
3. Text mód (`prompt: "socha"`) beze změny — masky per detekce, cap 8 v routě.
