# sd-server (stable-diffusion.cpp, commit a77d362 / „master-987“) — ověřené API

Ověřeno 2026-10-22 proti živému serveru na RTX 4060 Laptop 8 GB (G1 spike T2). Zdroj pravdy: `GET /sdcpp/v1/capabilities` + empirie, ne dokumentace.

## Start

```
sd/sd-server.exe --diffusion-model FLUX-3-Image-Klein-AD-Q4_K.gguf \
  --llm text_encoders/Qwen3-VL-4B-Instruct-AD-Q4_K.gguf --vae vae/ae.safetensors \
  --listen-port 8390 --steps 16 --cfg-scale 1.0 --sampling-method euler
```
cwd = `C:/Users/stock/models/flux3-klein`. Výchozí port je 1234, výchozí `--steps 20` a `--cfg-scale 7.0` (pro Klein špatně), proto je předáváme. Model se načítá líně při prvním jobu; `/v1/models` odpovídá do ~2 s po startu.

**Past:** sd-server píše průběh na stdout; když se stdout zavře (rouru nikdo nečte), proces panikne (`failed printing to stdout … os error 109`). Engine proto přesměrovává stdout/stderr do souboru (`logs/sd-server.log`), nikdy do roury.

## Endpointy

| Metoda | Cesta | Co |
|---|---|---|
| GET | `/v1/models` | health: `{"data":[{"id":"sd-cpp-local",…}]}` |
| GET | `/sdcpp/v1/capabilities` | defaulty, limity (max 4096², `max_queue_size` 64, `max_batch_count` 8), samplery, features (`ref_images`, `vae_tiling`, `cancel_queued`, `cancel_generating: false`) |
| POST | `/sdcpp/v1/img_gen` | `202 {"id","poll_url","status":"queued"}` |
| GET | `/sdcpp/v1/jobs/<id>` | `{"status": queued→running→completed|failed, "queue_position", "error", "result": {"images":[{"b64_json","index"}], "output_format"}}` |

## Payload `img_gen` (ověřené klíče)

```json
{"prompt": "…", "width": 1024, "height": 1024, "seed": 7,
 "sample_params": {"sample_steps": 16},
 "ref_images": ["<čistý base64 PNG bez data: prefixu>"],
 "vae_tiling_params": {"enabled": true}}
```
- `seed`, `width`, `height`, `sample_params.sample_steps` se propíšou (ověřeno v PNG tEXt `parameters`: „Steps: 12 … Seed: 7, Size: 512x512“).
- `ref_images` → log „EDIT mode“, prompt na ně odkazuje `<ref_image_0>`, `<ref_image_1>`…
- Výstupní PNG nese v tEXt `parameters` celý prompt a parametry → provenience je i v souboru.

## Měření (512², teplý server)

| Úloha | Čas od submitu |
|---|---|
| t2i 512², 16 kroků (první job, včetně načtení vah) | 12,2 s |
| edit 512² s 1 ref, 12 kroků | 14,2 s |

Edit „apple → bright green“: jablko přebarvené, stůl a světlo zachované (mean diff R 26,8 / G 33,1 / B 5,2).
