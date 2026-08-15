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

## Box + multi-point (M5, 2026-08-15)

**Schema (raw OpenAPI, stejný zdroj jako výše):** `box_prompts`: pole `BoxPrompt {x_min: int, y_min: int, x_max: int, y_max: int, object_id}` — souřadnice v pixelech nahraného obrázku, stejný prostor jako `point_prompts`.

- `SegmentBox` (`grafik/api/models.py`) posílá jen `x_min/y_min/x_max/y_max` — `object_id` na úrovni boxu nevystavujeme (jeden box už pinuje celý objekt, na rozdíl od jednotlivých bodů).
- `SegmentPoint.object_id: int | None` — schema pole, které seskupuje víc bodů k JEDNOMU objektu (víc bodů se stejným `object_id` = jedna object-level maska místo part-level detekcí). Stejné pravidlo jako u `prompt`: `None` → klíč se do payloadu vůbec nepřidá (viz `_segment_remote` v `grafik/api/app.py`), nedosazuje se `object_id: null`.
- `prompt` klíč nadále VŽDY (i pro box/multi-point-only volání, jako `""`) — pravidlo č. 1 výše platí beze změny i pro boxy.

### Empirie (M5 E2E 2026-08-15, plátno 1792×2400 — socha lva; 5 placených callů à $0.005)

| Volání | Výsledek |
|---|---|
| box_prompts (427,598)–(1600,1759), `apply_mask` NEPOSLÁN (default true) | masks=1, ale **`masks[]` obsahuje VYŘÍZNUTÝ OBRAZ (cutout), ne masku** — `convert("L")` udělá alfu z JASU obsahu: Pearson korelace alfa vs. jas kompozitu **1.000** (499k px), tmavý bronz → medián alfa 59, „maska" s coverage >127 jen 2,47 % |
| box_prompts totéž + **`apply_mask: false`** | masks=1, **binární maska 0/255** (min=medián=max 255), celý lev: coverage 11,45 %, bbox (476,535,1593,1560) — objekt-level ✓ |
| point_prompts ×2 (hříva + bok), `object_id: 0` na obou, `apply_mask: false` | masks=1 — **jedna object-level maska** (ne dvě části): coverage 10,07 %, bbox (476,533,1260,1561) — proti boxu chybí část ocasu vpravo |
| point_prompts ×1 (bez object_id) | part-level chování dle M2.5 (dnešní jediný vzorek trefil budovu — velká part-detekce) |

**Pravidlo č. 4 (nové, rozšiřuje č. 1):** fal si podle vstupních flagů tiše mění i SÉMANTIKU výstupu — `apply_mask` default true znamená „masks = maskované obrazy". Každý klíč, který mění tvar/význam výstupu, posílat explicitně; `_segment_remote` posílá `apply_mask: false` VŽDY (fix `3a874d3`).
