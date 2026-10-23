# fal obrazové backendy Engine v2 — ověřená schémata a ceny

Staženo 2026-10-23: schéma z `https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=<id>`, cena z `GET https://api.fal.ai/v1/models/pricing?endpoint_id=<id>` (s klíčem). Katalog v kódu: `engine/backends.py` `FAL_CATALOG`. Volání `backend="fal:<endpoint>"` + `confirm_cost=true`; bez potvrzení Engine vrátí 402 s odhadem a nic nespustí. Automatický fallback na fal neexistuje.

| Endpoint | Edit varianta (s předlohami) | Cena | Velikost | Pozn. ze schématu |
|---|---|---|---|---|
| `fal-ai/nano-banana-pro` | `fal-ai/nano-banana-pro/edit` (`image_urls`) | 0,15 USD / obrázek | `aspect_ratio` (21:9 … 9:16) + `resolution` 1K/2K | 4K schéma umí, Engine ho neposílá (cena mimo pricing API); `output_format` default png |
| `fal-ai/flux-2-pro` | `fal-ai/flux-2-pro/edit` (`image_urls`) | 0,03 USD / **zpracovaný** MP (výstup + vstupy) | `image_size {width,height}`, násobky 16, max 2560 px, max plocha 4 194 304 | `output_format` default **jpeg** → posíláme png |
| `fal-ai/flux-pro/v1.1` | — | 0,04 USD / MP | `image_size {width,height}` | jpeg default → png |
| `fal-ai/flux/krea` | — | 0,025 USD / MP | `image_size {width,height}` | jpeg default → png |

## Odhad ceny (horní mez)

- MP se zaokrouhluje nahoru na celé MP za obrázek.
- U `flux-2-pro` se každá předloha počítá jako ~4,2 MP (Engine předlohy zmenšuje na nejvýš 2048 px), tedy 5 MP po zaokrouhlení. Skutečná cena bývá nižší.
- Do ledgeru (`library/costs.jsonl`) a provenience jde tento odhad, ne fakturovaná částka.

Ověřeno offline (mock `fal_client.SyncClient`); živé placené volání zatím neproběhlo.
