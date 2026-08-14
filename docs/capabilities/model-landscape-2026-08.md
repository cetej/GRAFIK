# fal.ai model landscape 2026-08 — per-element motion (video) a mask inpaint (image edit)

**Navazuje na:** `docs/capabilities/kling-versions.md` (task 1.4 — Kling verze). Tento dokument rozšiřuje sweep na CELÝ aktuální katalog fal.ai mimo Kling.
**Datum ověření:** 2026-08-14
**Metoda:** stejná jako u Kling — přímý `curl` fetch syrového OpenAPI JSON z `https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=<id>`, `grep` na přesné názvy polí. `null` (4 byty) = endpoint neexistuje. WebSearch/WebFetch AI-souhrny použity **jen** k dohledání kandidátních endpoint ID (discovery), NIKDY jako zdroj pravdy o polích schématu — to platí i v tomto kole (viz metodická poznámka v kling-versions.md, kde se souhrny prokázaly nespolehlivé).
**Rozsah:** 18 Kling endpointů (viz kling-versions.md) + **60 dalších endpointů** v tomto kole = 78 endpointů celkem. Video: Wan (5), Seedance (6), Veo (5), MiniMax/Hailuo (5), Luma (2), LTX (1), Pixverse (3), Vidu (2), Hunyuan (2) + wan-motion (kontext). Image edit: Qwen-Image-Edit (5), FLUX (6), Seedream/SeedEdit (3), Nano-Banana/Gemini (4), Ideogram (2), GPT-Image (3), legacy inpaint (1). Plus SAM-3 (2) a qwen-image-layered (1) re-ověřeno.

## TOP-LINE ODPOVĚĎ

**Ano, Kling `v1/standard/image-to-video` + `v1.5/pro/image-to-video` zůstávají JEDINÉ endpointy z celého sweepu (78 endpointů, 10 video-rodin) s pravým per-element mask+trajectory motion control (`dynamic_masks`).** Žádný z 32 dalších prověřených image-to-video endpointů (Wan 2.2/2.5/2.6/Pro, Seedance 1.0/2.0/2.5, Veo 2/3/3.1, MiniMax Hailuo 02/2.3, Luma Ray 2, LTX, Pixverse v4.5/v5/v5.5, Vidu Q1/Q2, Hunyuan v1/v1.5) nemá `dynamic_masks`, `static_mask`, `trajectory`, `brush`, `drag`, `puppet` ani `region` pole. Nic se tedy nemění na doporučení z kling-versions.md — spíš se posiluje: i mimo Kling je motion brush u aktuálních modelů nulový.

**Kamera** je fragmentovaná do dvou slabých náhrad, žádná srovnatelná s Kling `advanced_camera_control`: `camera_movement` (bohatý enum, 19 hodnot: horizontal_left, zoom_in, whip_pan, hitchcock, …) na **Pixverse v4.5** — ale zmizel z v5 i v5.5 (novější tiery), a je to globální (celý klip), ne per-region. `camera_fixed` (bool) na **Seedance 1.0** (pro/lite/pro-fast) — zmizel v Seedance 2.0. Žádný z nich nemá magnitude/directional kontrolu jako Kling `advanced_camera_control` (movement_type + movement_value -10..10).

**Image edit (mask inpaint) je naopak živé a rozšířené** napříč aktuálními modely — na rozdíl od video-motion zde NENÍ jediná cesta. `mask_url`/`mask_image_url` mají: celá FLUX Fill rodina (pro, pro-finetuned, dev/lora), `fal-ai/qwen-image-edit/inpaint` (dedikovaný sub-endpoint), `fal-ai/ideogram/v3/edit`, a GPT-Image `1.5/edit` (`mask_image_url`) + `2/edit` (`mask_url`) — ne 1.0, ne mini. Trend u nejnovějších "instrukčních" editorů (Qwen-Image-Edit-2509/2511/Plus hlavní endpoint, FLUX Kontext, Seedream 4.5/5.0, SeedEdit v3, VŠECHNY Nano-Banana/Gemini varianty, GPT-Image-1/1-mini) je ale mask úplně vynechat ve prospěch textového popisu regionu — mask inpaint přežívá jako dedikovaný/staršího-stylu sub-endpoint, ne jako hlavní vlajková loď.

## Tabulka — VIDEO (image-to-video), mask-motion a kamera

| Rodina / Endpoint | mask-motion (dynamic_masks/trajectory) | kamera | duration | audio | Poznámka |
|---|---|---|---|---|---|
| **Kling** — viz `kling-versions.md` | jen v1/standard, v1.5/pro | jen v1/standard/**text**-to-video (ne I2V) | 5/10s (staré) až 3-15s (v3/O3) | v2.6+/v3/O3: generate_audio | plný detail v samostatném souboru |
| `fal-ai/wan/v2.2-5b/image-to-video` | ne | ne | num_frames/fps (ne enum) | ne | interpolator_model, guidance_scale |
| `fal-ai/wan/v2.2-a14b/image-to-video` | ne | ne | num_frames/fps | ne | + end_image_url, guidance_scale_2 |
| `fal-ai/wan-25-preview/image-to-video` | ne | ne | ano (enum) | **audio_url (vstup)** | enable_prompt_expansion |
| `fal-ai/wan-pro/image-to-video` | ne | ne | — | ne | minimální schema (prompt, image_url, seed) |
| `wan/v2.6/image-to-video` (POZOR: slug BEZ `fal-ai/` prefixu — `fal-ai/wan/v2.6/...` je `null`) | ne | ne | ano | audio_url (vstup) | + multi_shots (podobné Kling v3 shot_type) |
| _(kontext)_ `fal-ai/wan-motion` | ne (jiná funkce: `adapt_motion` bool přenáší pohyb z `video_url` na `image_url`, pose retargeting) | n/a | n/a | n/a | video-to-video, ne I2V — analog Kling motion-control |
| `fal-ai/bytedance/seedance/v1/pro/image-to-video` | ne | **camera_fixed** (bool, jen zapnout/vypnout) | ano | ne | + end_image_url |
| `fal-ai/bytedance/seedance/v1/lite/image-to-video` | ne | camera_fixed (bool) | ano | ne | |
| `fal-ai/bytedance/seedance/v1/pro/fast/image-to-video` | ne | camera_fixed (bool) | ano | ne | bez end_image_url |
| `bytedance/seedance-2.0/image-to-video` | ne | **ne** (camera_fixed v 2.0 zmizel) | ano | **generate_audio** | + bitrate_mode |
| `bytedance/seedance-2.0/fast/image-to-video` | ne | ne | ano | generate_audio | |
| `bytedance/seedance-2.0/reference-to-video` | ne | ne | ano | generate_audio | multi-ref (image_urls, video_urls, audio_urls) |
| `bytedance/seedance-2.5/image-to-video` | ne | ne | ano | generate_audio | **ADDENDUM** — nejnovější tier, + end_image_url, resolution; žádná mask/camera pole |
| `bytedance/seedance-2.5/reference-to-video` | ne | ne | ano | generate_audio | **ADDENDUM** — multi-ref jako 2.0; `/fast` varianta pro 2.5 neexistuje (404) |
| `fal-ai/veo2/image-to-video` | ne | ne | ano | ne | minimální (prompt, image_url, duration) |
| `fal-ai/veo3/image-to-video`, `fal-ai/veo3/fast/image-to-video`, `fal-ai/veo3.1/image-to-video` | ne | ne | ano | **generate_audio** | resolution, safety_tolerance |
| `fal-ai/veo3.1/fast/first-last-frame-to-video` | ne | ne | ano | generate_audio | first_frame_url + last_frame_url (tail-frame ekvivalent) |
| `fal-ai/minimax/hailuo-02/pro/image-to-video`, `/standard/`, `-fast/` | ne | ne | ano/fixed | ne | end_image_url (pro/standard); prompt_optimizer |
| `fal-ai/minimax/hailuo-2.3/pro/image-to-video`, `/standard/` | ne | ne | ano | ne | prompt_optimizer |
| `fal-ai/luma-dream-machine/ray-2/image-to-video`, `ray-2-flash/` | ne | ne | ano | ne | end_image_url (dual-image interpolation), loop bool |
| `fal-ai/ltx-video/image-to-video` | ne | ne | — | ne | jednoduchá schema (num_inference_steps, guidance_scale) |
| `fal-ai/pixverse/v4.5/image-to-video` | ne | **camera_movement** enum (19 hodnot: horizontal_left/right, vertical_up/down, zoom_in/out, crane_up, whip_pan, hitchcock, pan_left/right, fix_bg, …) — globální, ne per-region | ano | ne | nejbohatší kamerový enum ze všech ne-Kling modelů |
| `fal-ai/pixverse/v5/image-to-video` | ne | **ne** (camera_movement v5 zmizel) | ano | ne | |
| `fal-ai/pixverse/v5.5/image-to-video` | ne | ne | ano | generate_audio_switch | generate_multi_clip_switch, thinking_type |
| `fal-ai/vidu/q1/image-to-video` | ne | ne (jen `movement_amplitude` — globální intenzita pohybu, ne prostorová kontrola) | — | ne | |
| `fal-ai/vidu/q2/image-to-video/pro` | ne | ne (movement_amplitude) | ano | bgm | end_image_url |
| `fal-ai/hunyuan-video-image-to-video` | ne | ne | — | ne | i2v_stability |
| `fal-ai/hunyuan-video-v1.5/image-to-video` | ne | ne | — | ne | enable_prompt_expansion |

**Shrnutí video:** 0/32 ne-Kling endpointů má `dynamic_masks`/trajectory. 2 mají alespoň nějaké kamerové pole (Pixverse v4.5 enum, Seedance 1.0 bool) — ale ani jeden per-region, ani jeden na aktuální/nejnovější tier vlastní rodiny (Pixverse v5+ a Seedance 2.0 kamerové pole naopak ODEBRALY oproti předchozí verzi).

## Tabulka — IMAGE EDIT, mask inpaint

| Rodina / Endpoint | mask inpaint? | ref images | Poznámka |
|---|---|---|---|
| `fal-ai/qwen-image-edit-2509` | ne (instrukční) | image_urls (multi) | hlavní Qwen-Image-Edit tier |
| `fal-ai/qwen-image-edit-2511` | ne (instrukční) | image_urls | nejnovější Qwen (2511) |
| `fal-ai/qwen-image-edit-plus`, `-plus-lora` | ne (instrukční) | image_urls | plus-lora = + LoRA váhy |
| **`fal-ai/qwen-image-edit/inpaint`** | **ANO** `mask_url` + `strength` | — (1 image_url) | dedikovaný inpaint sub-endpoint, oddělený od hlavní řady |
| `fal-ai/flux-pro/kontext` | ne (instrukční) | — (1 image_url) | vlajkový Kontext, žádná mask |
| **`fal-ai/flux-pro/v1/fill`** | **ANO** `mask_url` | — | FLUX.1 [pro] Fill — dedikovaný inpaint model |
| **`fal-ai/flux-pro/v1/fill-finetuned`** | **ANO** `mask_url` | — | + finetune_id/finetune_strength |
| **`fal-ai/flux-lora-fill`** | **ANO** `mask_url` | — | FLUX.1 [dev] Fill (open-weight); + paste_back, fill_image |
| **`fal-ai/flux-kontext-lora/inpaint`** | **ANO** `mask_url` | reference_image_url | Kontext-LoRA inpaint varianta |
| **`fal-ai/flux-general/inpainting`** | **ANO** `mask_image_url` + `mask_threshold` | control_image_url | ControlNet-style, nejsložitější schema (ControlNet + LoRA sloty) |
| `fal-ai/bytedance/seedream/v4.5/edit`, `v5/lite/edit` | ne (instrukční) | image_urls | Seedream — bez mask |
| `fal-ai/bytedance/seededit/v3/edit-image` | ne (instrukční) | — (1 image_url) | jen prompt + guidance_scale |
| `fal-ai/gemini-3-pro-image-preview/edit` (Nano Banana Pro) | ne | image_urls | |
| `fal-ai/gemini-3.1-flash-image-preview/edit` | ne | image_urls | |
| `fal-ai/nano-banana/edit`, `nano-banana-lite/edit` (google/), `nano-banana-pro/edit` | ne (žádná varianta) | image_urls | celá Nano-Banana rodina bez mask |
| **`fal-ai/ideogram/v3/edit`** | **ANO** `mask_url` | image_url | |
| `fal-ai/ideogram/v3/replace-background` | ne (auto-segmentace pozadí, bez uživatelské masky) | image_url | |
| `fal-ai/gpt-image-1/edit-image` | ne | image_urls | GPT-Image 1.0 — bez mask |
| **`fal-ai/gpt-image-1.5/edit`** | **ANO** `mask_image_url` | image_urls | jen 1.5, verzí-specifické |
| `fal-ai/gpt-image-1-mini/edit` | ne | image_urls | mini tier bez mask |
| **`fal-ai/gpt-image-2/edit`** | **ANO** `mask_url` | image_urls | **ADDENDUM** — nejnovější GPT-Image drží mask (pozor: 1.5 má `mask_image_url`, 2 má `mask_url` — schema drift mezi verzemi); gen endpoint `fal-ai/gpt-image-2` bez mask; `gpt-image-2-mini/edit` neexistuje (404) |
| `fal-ai/inpaint` (legacy SD/SDXL) | ANO `mask_url` | — | starší technologie (model_name param), ne 2025/2026 flagship, jen pro úplnost |

**Shrnutí image edit:** 10 z ~26 prověřených edit-endpointů má mask inpaint. Rozdělení je čisté podle designu: "instrukční" hlavní modely (Qwen main, Kontext, Seedream, SeedEdit, Nano-Banana/Gemini vše, GPT-Image 1/mini) mask nemají; mask žije na dedikovaných "fill"/"inpaint" sub-endpointech nebo verzově-gated (GPT-Image: 1.5 a 2 ano, 1.0 a mini ne — 2.0 trend „mask vynechat" vyvrací, mask u OpenAI edit endpointu drží).

## Segmentace a decompose — re-ověřeno

| Endpoint | Existuje | Poznámka |
|---|---|---|
| `fal-ai/sam-3/image` | ano | vstup: `image_url` + `prompt`/`text_prompt`/`point_prompts`/`box_prompts`; výstup: `masks` (+ scores, boxes). Pro GRAFIK A1 alternativu (SAM 3 jako cesta k prvkům místo/vedle dekompozice). |
| `fal-ai/sam-3/image-rle` | ano | stejný vstup, výstup `rle` (kompaktní RLE formát) místo syrových mask obrázků |
| `fal-ai/qwen-image-layered` | **ano, potvrzeno** | GRAFIK core dependency žije: `prompt`, `image_url`, `negative_prompt`, `num_inference_steps`, `guidance_scale`, `seed`, `sync_mode`, `num_layers`, `enable_safety_checker`, `output_format`, `acceleration`. Žádná změna oproti očekávání. |

## Dopad na GRAFIK provider capability map (task 1.5)

Doporučené hodnoty pro `grafik/providers/` registry (`supports_mask`, `supports_dynamic_masks`, `supports_camera_params`, `supports_camera_prompt`):

**`supports_dynamic_masks=True`** (per-element mask+trajectory motion, video): **pouze** `fal-ai/kling-video/v1/standard/image-to-video` a `fal-ai/kling-video/v1.5/pro/image-to-video`. Vše ostatní (celý zbytek Kling + všech 32 prověřených ne-Kling I2V endpointů) → `False`.

**`supports_camera_params=True`** (strukturovaná, per-region/magnitude kamera jako Kling `advanced_camera_control`): **nikdo** mezi image-to-video endpointy — tato kombinace na fal.ai neexistuje vůbec (viz kling-versions.md). Pro `fal-ai/pixverse/v4.5/image-to-video` (camera_movement enum) a `fal-ai/bytedance/seedance/v1/{pro,lite,pro/fast}/image-to-video` (camera_fixed bool) doporučuji **novou, slabší kategorii** místo natvrdo False, např. `supports_camera_preset` (globální enum/bool, ne per-region) — jinak se ztratí informace, že aspoň hrubá kamerová kontrola existuje. Pokud se do capability map nezavádí nová kategorie, dát `supports_camera_params=False` + poznámku v metadata, ne mlčky ignorovat.

**`supports_camera_prompt=True`** (textový fallback popis kamery v `prompt` poli): prakticky všechny video endpointy mají `prompt` string → lze nastavit `True` plošně jako univerzální fallback vrstvu (přesně A3 fallback z plánu). Toto je jediná kamerová cesta funkční napříč celým katalogem mimo Kling v1/text-to-video.

**`supports_mask=True`** (image edit inpaint): `fal-ai/flux-pro/v1/fill`, `fal-ai/flux-pro/v1/fill-finetuned`, `fal-ai/flux-lora-fill`, `fal-ai/flux-kontext-lora/inpaint`, `fal-ai/flux-general/inpainting`, `fal-ai/qwen-image-edit/inpaint`, `fal-ai/ideogram/v3/edit`, `fal-ai/gpt-image-1.5/edit`, `fal-ai/gpt-image-2/edit` (ADDENDUM). GRAFIK už pravděpodobně registruje Qwen-Image-Edit a FLUX Fill (viz CLAUDE.md `ops/`) — doporučeno mapovat konkrétně na tyto **dedikované** endpoint ID, ne na obecné "qwen-image-edit"/"flux" jméno, protože hlavní tiery (2509/2511/Plus/Kontext) mask nemají.

**`supports_mask=False`** (instrukční edit, textový popis regionu místo pixel masky): `fal-ai/qwen-image-edit-2509/-2511/-plus/-plus-lora`, `fal-ai/flux-pro/kontext`, Seedream v4.5/v5-lite, SeedEdit v3, celá Nano-Banana/Gemini rodina, `fal-ai/gpt-image-1/edit-image`, `fal-ai/gpt-image-1-mini/edit`, `fal-ai/ideogram/v3/replace-background`.

**Segmentace pro A1 (SAM 3 jako cesta k prvkům):** registrovat `fal-ai/sam-3/image` (masks) nebo `fal-ai/sam-3/image-rle` (kompaktnější) — oba potvrzeny živé.

**Nezměněno:** `fal-ai/qwen-image-layered` (dekompozice) funguje beze změny, žádný dopad na A1/provider layer z tohoto sweepu.

## ADDENDUM 2026-08-14 (pozdější ověření) — neúplnost discovery

Uživatel upozornil na chybějící **Seedance 2.5** a **GPT-Image 2** — obojí na fal.ai EXISTUJE a bylo doplněno výše (raw OpenAPI ověření, stejná metoda):
- `bytedance/seedance-2.5/image-to-video` + `/reference-to-video` — žádná mask/camera pole (závěr o motion se nemění).
- `fal-ai/gpt-image-2` (gen) + **`fal-ai/gpt-image-2/edit` s `mask_url`** — nový mask-inpaint kandidát pro provider registry.

**Poučení o metodě:** discovery přes fal search stránky je neúplná (stránkování, rate limit 429 při sweepu, nová vydání průběžně) — sweep je datovaný snapshot, NE vyčerpávající katalog. Capability map v `grafik/providers/` proto musí nést `verified_at` per endpoint a ověření se musí dát levně přehrát (existence = 1 GET; `null`/404 = neexistuje). Jména modelů známá uživateli jsou cenný nezávislý vstup do discovery.

## Reprodukovatelnost — fetchnuté schema URL (2026-08-14, toto kolo)

Video:
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/wan/v2.2-5b/image-to-video
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/wan-25-preview/image-to-video
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/wan-pro/image-to-video
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/wan/v2.6/image-to-video (→ null)
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=wan/v2.6/image-to-video (funguje, bez fal-ai/ prefixu)
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/wan/v2.2-a14b/image-to-video
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/wan-motion
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/bytedance/seedance/v1/pro/image-to-video
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=bytedance/seedance-2.0/image-to-video
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=bytedance/seedance-2.0/fast/image-to-video
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=bytedance/seedance-2.0/reference-to-video
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/bytedance/seedance/v1/pro/fast/image-to-video
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/bytedance/seedance/v1/lite/image-to-video
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/veo3/image-to-video
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/veo3/fast/image-to-video
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/veo3.1/image-to-video
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/veo3.1/fast/first-last-frame-to-video
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/veo2/image-to-video
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/minimax/hailuo-02/pro/image-to-video
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/minimax/hailuo-02/standard/image-to-video
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/minimax/hailuo-02-fast/image-to-video
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/minimax/hailuo-2.3/pro/image-to-video
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/minimax/hailuo-2.3/standard/image-to-video
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/luma-dream-machine/ray-2-flash/image-to-video
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/luma-dream-machine/ray-2/image-to-video
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/ltx-video/image-to-video
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/pixverse/v5/image-to-video
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/pixverse/v4.5/image-to-video
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/pixverse/v5.5/image-to-video
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/vidu/q1/image-to-video
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/vidu/q2/image-to-video/pro
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/hunyuan-video-image-to-video
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/hunyuan-video-v1.5/image-to-video

Image edit:
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/qwen-image-edit-2509
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/qwen-image-edit/inpaint
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/qwen-image-edit-plus-lora
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/qwen-image-edit-plus
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/qwen-image-edit-2511
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/flux-pro/kontext
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/flux-pro/v1/fill
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/flux-pro/v1/fill-finetuned
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/flux-lora-fill
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/flux-kontext-lora/inpaint
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/flux-general/inpainting
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/bytedance/seedream/v4.5/edit
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/bytedance/seedream/v5/lite/edit
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/bytedance/seededit/v3/edit-image
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/gemini-3-pro-image-preview/edit
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/nano-banana/edit
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=google/nano-banana-lite/edit
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/nano-banana-pro/edit
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/gemini-3.1-flash-image-preview/edit
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/ideogram/v3/edit
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/ideogram/v3/replace-background
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/gpt-image-1/edit-image
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/gpt-image-1.5/edit
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/gpt-image-1-mini/edit
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/inpaint

Segmentace / decompose:
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/sam-3/image
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/sam-3/image-rle
- https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/qwen-image-layered

Kling endpointy (18) — viz seznam v `docs/capabilities/kling-versions.md`, zde neopakováno.

Discovery (WebSearch, jen k dohledání kandidátních ID, ne jako zdroj pravdy o polích):
- "fal.ai wan 2.5 image-to-video endpoint id site:fal.ai"
- "fal.ai seedance 2.0 OR 1.0 pro image-to-video endpoint id site:fal.ai"
- "fal.ai veo3 OR veo2 image-to-video endpoint site:fal.ai"
- "fal.ai minimax hailuo 02 image-to-video endpoint site:fal.ai"
- "fal.ai luma ray2 OR pixverse OR vidu OR ltx-video OR hunyuan-video image-to-video endpoint site:fal.ai"
- "fal.ai "motion brush" OR trajectory OR drag OR puppet image-to-video endpoint 2026"
- "fal.ai pixverse v5 OR v4.5 image-to-video endpoint id site:fal.ai"
- "fal.ai vidu q1 OR vidu 2.0 image-to-video endpoint id site:fal.ai"
- "fal.ai hunyuan-video image-to-video endpoint id site:fal.ai"
- "fal.ai qwen-image-edit inpaint plus endpoint id site:fal.ai"
- "fal.ai flux fill OR flux kontext inpaint endpoint id site:fal.ai"
- "fal.ai seedream seededit inpaint endpoint id site:fal.ai"
- "fal.ai nano-banana gemini image edit endpoint id site:fal.ai"
- "fal.ai sam 3 segmentation endpoint id site:fal.ai OR fal-ai/qwen-image-layered"
- "fal.ai ideogram v3 edit inpaint endpoint id site:fal.ai"
- "fal.ai recraft v3 inpaint OR replace-background endpoint id site:fal.ai" (Recraft V3 nemá dedikovaný inpaint endpoint dohledatelný — jen text-to-image; nezahrnuto do sweepu)
- "fal.ai gpt-image-1 edit endpoint id site:fal.ai"
- "fal.ai wan-motion endpoint OR fal-ai/qwen-image-layered api"

**Poznámka k Recraft:** nebyl dohledán žádný dedikovaný Recraft V3 inpaint/edit endpoint (jen `fal-ai/recraft/v3/text-to-image`), proto vynechán z hlavní tabulky — pokud GRAFIK Recraft potřebuje, doporučeno ověřit přímo na fal.ai/models před spoléháním na tento nález.

## Addendum 2026-08-14 (M3) — payload detaily video endpointů pro registry

Re-fetch při stavbě payload builderu (stejná curl metodika; viz analogický addendum v `kling-versions.md`):

- **`wan/v2.6/image-to-video`**: `image_url` + `prompt` REQUIRED; `duration` enum "5"|"10"|"15" (default "5"); **`resolution` enum 720p|1080p default `1080p`** → pro levný běh posílat `"720p"`; **`enable_prompt_expansion` default `true`** → posílat `false` (kompilovaný MotionSpec prompt má být autoritativní, expanze ho přepisuje). Cena (fal model page, 2026-08-14, sekundární): 720p $0.10/s, 1080p $0.15/s.
- **`bytedance/seedance-2.5/image-to-video`**: `image_url` + `prompt` REQUIRED; `duration` enum "auto","4".."30" (default "auto"); `resolution` 480p|720p default 720p; **`generate_audio` default `true`** → posílat `false`.

Registry od M3 nese `image_field`, `payload_defaults`, `duration_choices`, `est_cost_usd_per_second` per endpoint.
