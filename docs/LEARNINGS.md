# LEARNINGS — GRAFIK

## 2026-08-14 — fal.ai schema: jediný zdroj pravdy je syrový OpenAPI JSON

**Kontext:** Plánovací research (unified editor, 2026-08-14) tvrdil, že Kling 1.6 Pro má `dynamic_masks` + `advanced_camera_control`. Task 1.4 to vyvrátil raw fetchem: motion brush existuje jen na `v1/standard` a `v1.5/pro`, kamerová kontrola na žádném image-to-video endpointu (jen `v1/standard/text-to-video`). Detail: `docs/capabilities/kling-versions.md`.

**Poučení:**
1. Jediný zdroj pravdy o fal endpointu je syrový OpenAPI JSON: `curl "https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=<id>"` + grep na přesná jména polí. WebFetch/WebSearch AI souhrny si pole vymýšlejí (fabrikovaly `static_mask_url` u „Kling 2.0 Master", který nic takového nemá).
2. fal může neznámá pole v payloadu tiše ignorovat — „úspěšný" call nedokazuje, že feature fungovala. Před stavbou na parametru ověř jeho existenci ve schématu; jinak vzniká falešná evidence.
3. Neexistující endpoint vrací doslova `null` (4 byty) — levný existence check.

**Aplikace:** Provider capability map (`grafik/providers/`) plnit výhradně z raw schema fetchů s datem ověření; capability zápisy patří do `docs/capabilities/` s reprodukovatelnými URL.

## 2026-08-14 — Qwen inpaint: paste-back v pixel space je povinný

**Kontext:** Smoke test `fal-ai/qwen-image-edit/inpaint` (task 1.3): raw výstup endpointu má globální drift i mimo masku (mean diff ~20/255, 48 % pixelů), tj. endpoint překóduje celý obraz.

**Poučení:** Výsledek inpaintu nikdy nebrat celý — vždy kompozitovat zpět jen vnitřek masky (feather ~2 px, dilate ~4 px) nad originál. Pak je diff mimo masku ~0 a hranice bez švů (gradient ratio 1.035 @ 544×736). Před M2 přeměřit na 4K.
