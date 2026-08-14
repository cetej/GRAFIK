# Kling (fal.ai) — capability matrix pro per-element motion a kameru

**Task:** 1.4 z `docs/plans/2026-08-14-unified-editor.md` — "Schema-fetch Kling 2.1 Standard / 2.5 / 2.6 / 3.0 na fal.ai — má některý `dynamic_masks`?"
**Datum ověření:** 2026-08-14
**Metoda:** přímý `curl` fetch syrového OpenAPI JSON z `https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=<id>` do lokálního souboru, poté `grep` na přesné názvy polí (`dynamic_masks`, `static_mask_url`, `camera_control`, `advanced_camera_control`, `tail_image_url`/`end_image_url`, `duration`). Endpointy, které neexistují, vrací doslova `null` (4 byty).
**Metodická poznámka:** WebFetch (shrnutí přes malý model) se pro tento úkol ukázal částečně nespolehlivý u velkých schémat a WebSearch AI-souhrny obsahovaly zjevně nesprávná tvrzení (např. že "Kling 2.0 Master" má `static_mask_url`/`dynamic_mask_url` — v syrovém JSON nic takového není). Všechny nálezy níže jsou proto ověřené přímo v syrovém OpenAPI JSON, ne z vyhledávacích souhrnů.

## KRITICKÝ NÁLEZ — vyvrací předpoklad plánu

`docs/plans/2026-08-14-unified-editor.md` (řádek 32, sc-2, A3, task 1.2 smoke test) předpokládá, že **`fal-ai/kling-video/v1.6/pro/image-to-video`** má `dynamic_masks` + `static_mask_url` + `camera_control` + `advanced_camera_control`.

**K 2026-08-14 to neplatí.** Syrové schema `KlingVideoV16ProImageToVideoInput` obsahuje pouze: `prompt`, `image_url`, `duration` (5/10s), `aspect_ratio`, `tail_image_url`, `negative_prompt`, `cfg_scale`. Žádné maskové ani kamerové pole. Ověřeno dvakrát nezávisle (WebFetch shrnutí i syrový JSON přes curl+grep — shodný výsledek).

Toto přesně odpovídá riziku, které plán sám pojmenovává v Premortem #1 ("Kling 1.6 deprecation / motion brush nedoputuje do 2.x API") — jen o krok dřív, než plán počítal: pole chybí už na 1.6 samotné, ne až při přechodu na 2.x.

## Shrnutí — kde motion brush / kamera skutečně žijí

- **`dynamic_masks` + `static_mask_url`** (motion brush, mask_url + trajectories `[{x,y}]`) existují **pouze na dvou nejstarších image-to-video endpointech**: `v1/standard` a `v1.5/pro`. Od 1.6 výš (1.6, 2.0, 2.1, 2.5-turbo, 2.6, 3.0, O3 — všechny tiery, které existují) jsou pole pryč a nikde se nevrací.
- **`camera_control` + `advanced_camera_control`** existují na **jediném** endpointu z celého sweepu (17 image-to-video + 3 kontextové endpointy): `fal-ai/kling-video/v1/standard/text-to-video`. To je **text-to-video**, ne image-to-video — nepřijímá `image_url`. Kamerová kontrola tedy není (a nikdy nebyla, napříč verzemi 1.0–3.0) kombinovatelná se vstupním obrázkem na žádném Kling endpointu na fal.ai. I na text-to-video mizí od 1.6 výš (`v1.6/pro/text-to-video` už `camera_control` nemá).
- **Žádná verze ≥2.x nemá `dynamic_masks`** — takže se nic "nezapaluje" směrem nahoru. Problém je opačný: i předpokládaná 1.6 Pro ho nemá.

## Tabulka — image-to-video endpointy (17 ověřeno)

| Endpoint ID | Existuje | dynamic_masks | static_mask_url | camera_control | advanced_camera_control | Poznámka |
|---|---|---|---|---|---|---|
| `fal-ai/kling-video/v1/standard/image-to-video` | ano | **ANO** | **ANO** | ne | ne | nejstarší I2V; + `tail_image_url`; duration 5/10s |
| `fal-ai/kling-video/v1/pro/image-to-video` | **ne** (`null`) | — | — | — | — | tier "pro" pro v1 neexistuje |
| `fal-ai/kling-video/v1.5/pro/image-to-video` | ano | **ANO** | **ANO** | ne | ne | + `tail_image_url`; duration 5/10s |
| `fal-ai/kling-video/v1.6/standard/image-to-video` | ano | ne | ne | ne | ne | jen prompt/image_url/duration/negative_prompt/cfg_scale, ani tail_image_url |
| `fal-ai/kling-video/v1.6/pro/image-to-video` | ano | **ne** | **ne** | ne | ne | **předpoklad plánu vyvrácen** (viz výše); + tail_image_url, aspect_ratio; duration 5/10s |
| `fal-ai/kling-video/v1.6/standard/elements` | ano | ne | ne | ne | ne | multi-image-to-video (až 4 vstupní obrázky), NENÍ motion brush |
| `fal-ai/kling-video/v2/master/image-to-video` | ano | ne | ne | ne | ne | jen prompt/image_url/duration/negative_prompt/cfg_scale |
| `fal-ai/kling-video/v2.1/standard/image-to-video` | ano | ne | ne | ne | ne | jen základní pole, ani tail_image_url |
| `fal-ai/kling-video/v2.1/pro/image-to-video` | ano | ne | ne | ne | ne | **re-ověřeno** (background úkolu) — potvrzeno chybí; + tail_image_url |
| `fal-ai/kling-video/v2.1/master/image-to-video` | ano | ne | ne | ne | ne | jen základní pole |
| `fal-ai/kling-video/v2.5-turbo/pro/image-to-video` | ano | ne | ne | ne | ne | + tail_image_url |
| `fal-ai/kling-video/v2.6/pro/image-to-video` | ano | ne | ne | ne | ne | + end_image_url, generate_audio, voice_ids; duration 5/10s |
| `fal-ai/kling-video/v2.6/standard/image-to-video` | **ne** (`null`) | — | — | — | — | pro 2.6 I2V existuje jen "pro" tier |
| `fal-ai/kling-video/v3/standard/image-to-video` | ano | ne | ne | ne | ne | + `elements` (postava/objekt reference), `multi_prompt`, `shot_type`, `generate_audio`, `end_image_url`; duration 3–15s |
| `fal-ai/kling-video/v3/pro/image-to-video` | ano | ne | ne | ne | ne | shodné schema jako v3/standard; duration 3–15s |
| `fal-ai/kling-video/v3/4k/image-to-video` | ano | ne | ne | ne | ne | shodné schema jako v3/pro (4K = jiné rozlišení výstupu, ne jiná schema) |
| `fal-ai/kling-video/o3/standard/image-to-video` | ano | ne | ne | ne | ne | `multi_prompt`, `shot_type`, `generate_audio`, `end_image_url`; duration 3–15s |
| `fal-ai/kling-video/o3/pro/image-to-video` | ano | ne | ne | ne | ne | shodné schema jako o3/standard; pole `image_url` (ne `start_image_url` jako u v3) |

## Kontext — jiné modality (ne image-to-video, ověřeno pro úplnost)

| Endpoint ID | Modalita | camera_control | advanced_camera_control | Poznámka |
|---|---|---|---|---|
| `fal-ai/kling-video/v1/standard/text-to-video` | text-to-video | **ANO** | **ANO** | jediný endpoint z celého sweepu s kamerou; `camera_control` = enum `down_back`\|`forward_up`\|`right_turn_forward`\|`left_turn_forward`; `advanced_camera_control` = objekt `{movement_type: horizontal\|vertical\|pan\|tilt\|roll\|zoom, movement_value: integer -10..10}`. Nepřijímá `image_url`. |
| `fal-ai/kling-video/v1.6/pro/text-to-video` | text-to-video | ne | ne | potvrzuje, že kamera zmizela i z T2V od 1.6 výš |
| `fal-ai/kling-video/v2.6/pro/motion-control` | video-to-video | n/a | n/a | jiná funkce: přenáší pohyb z referenčního `video_url` na obrázek postavy (`image_url`, `character_orientation`, `keep_original_sound`) — NENÍ mask-based per-element control, nesrovnatelné s `dynamic_masks` |

## Cena (orientačně — ze sekundárních zdrojů, OpenAPI schema cenu neobsahuje)

Nejsou ověřeno stejnou metodou jako schema (fal OpenAPI JSON cenu vůbec nenese) — jen dohledáno webem, brát jako orientační:
- Kling 2.6 Pro: ~$0.07/s bez audia, ~$0.14/s s audiem (native audio generation)
- Kling 2.5 Turbo Pro: ~$0.35 za 5s (~$0.07/s dodatečně), bez audio syncu
- Kling 1.6 Pro, 2.1, 3.0: přesná cena z fal.ai modelové stránky nebyla v tomto sweepu spolehlivě dohledána (search výsledky byly řídké/nekonzistentní) — pro přesnou cenu doporučeno ověřit přímo na `https://fal.ai/models/<endpoint-id>` před rozpočtováním.

## Závěr a dopad na provider capability map

1. **Per-element motion (`dynamic_masks`) má potvrzenou API cestu jen na `v1/standard` a `v1.5/pro`** — obě starší a kvalitativně slabší než 1.6/2.x/3.0. `supports_dynamic_masks=True` smí registry nastavit **jen** pro tyto dva endpointy, ne pro `v1.6/pro` jak plán předpokládal.
2. **`supports_camera_params` (camera_control/advanced_camera_control) nesmí být `True` pro žádný image-to-video endpoint** — kombinace "vstupní obrázek + kamerová kontrola" na Kling/fal aktuálně neexistuje vůbec. Jediný nositel je `v1/standard/text-to-video`, což je jiný pipeline (bez `image_url`) a pro GRAFIK use-case (edit existující vrstvy → klip) nepoužitelný beze změny architektury.
3. **A3 (MotionSpec → Kling payload)** je nutné přepočítat: kompilace `camera → camera_control/advanced_camera_control` nemá na I2V žádný cílový endpoint. Buď (a) zahodit kamerovou složku MotionSpec pro Kling a nechat ji jen jako textový prompt fallback (`"camera slowly pans left"` v `prompt` poli — všechny I2V endpointy mají `prompt`), nebo (b) prozkoumat, zda existuje ekvivalent mimo fal.ai wrapper (mimo scope task 1.4).
4. **Task 1.2 (Kling smoke test)** v plánu cílí na `v1.6/pro/image-to-video` s `dynamic_masks` + `advanced_camera_control` — to selže na validaci vstupu (pole ve schema neexistují). Smoke test je nutné přesměrovat na `v1/standard/image-to-video` nebo `v1.5/pro/image-to-video` (jen `dynamic_masks`/`static_mask_url`, bez kamery) NEBO scope task 1.2 zúžit jen na masky bez kamery.
5. **Premortem #1 rizikový scénář ("motion brush nedoputuje do 2.x") se fakticky již naplnil** — motion brush nedoputoval ani do 1.6, natož do 2.x/3.0. Mitigace "A3 prompt-fallback od začátku" z premortem #1 by měla být povýšena z fallbacku na primární cestu pro cokoliv nad 1.5, ne jen záložní plán.

## Reprodukovatelnost — fetchnuté schema URL (2026-08-14)

Image-to-video:
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/kling-video/v1/standard/image-to-video
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/kling-video/v1/pro/image-to-video (→ null)
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/kling-video/v1.5/pro/image-to-video
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/kling-video/v1.6/standard/image-to-video
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/kling-video/v1.6/pro/image-to-video
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/kling-video/v1.6/standard/elements
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/kling-video/v2/master/image-to-video
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/kling-video/v2.1/standard/image-to-video
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/kling-video/v2.1/pro/image-to-video
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/kling-video/v2.1/master/image-to-video
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/kling-video/v2.5-turbo/pro/image-to-video
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/kling-video/v2.6/pro/image-to-video
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/kling-video/v2.6/standard/image-to-video (→ null)
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/kling-video/v3/standard/image-to-video
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/kling-video/v3/pro/image-to-video
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/kling-video/v3/4k/image-to-video
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/kling-video/o3/standard/image-to-video
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/kling-video/o3/pro/image-to-video

Kontext (jiné modality):
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/kling-video/v1/standard/text-to-video
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/kling-video/v1.6/pro/text-to-video
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/kling-video/v2.6/pro/motion-control

Discovery (WebSearch, ne schema — použito jen k dohledání kandidátních endpoint ID, ne jako zdroj pravdy o polích):
- "fal.ai kling video image-to-video 2.6 3.0 site:fal.ai"
- "fal.ai kling "camera-control" endpoint image-to-video site:fal.ai"
- "fal.ai kling "motion brush" OR "dynamic_masks" model endpoint"
- ""fal-ai/kling-video" "camera_control" endpoint_id"
- "fal.ai kling "advanced_camera_control" OR "camera_control" schema horizontal vertical pan tilt roll zoom"
- "fal.ai kling-video v1 pro image-to-video camera control"
- "fal.ai kling video pricing per second 1.6 2.1 2.6 3.0 image-to-video"
