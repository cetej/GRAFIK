# Stav GRAFIK

Aktualizováno 2026-10-22.

## Teď

**GRAFIK v2 — G0 schváleno, G1 (Engine) hotové a ověřené na RTX 4060.**
Spec: [`docs/plans/2026-10-22-grafik-v2-greenfield.md`](plans/2026-10-22-grafik-v2-greenfield.md) · rozhodnutí: [`DECISIONS.md`](DECISIONS.md) · důkaz G1: [`spikes/2026-10-22-g1-engine.md`](spikes/2026-10-22-g1-engine.md).

- `engine/` — FastAPI na :8300 (`/api/v2/images`, `/jobs`, `/health`, `/costs`), fronta SQLite + jeden worker, správa sd-serveru jen podle vlastního PID (idle 10 min), zámek GPU (`~/.gpu-lock` + kontrola VRAM), provenience a `library/costs.jsonl`.
- `clients/grafik_client.py` — jeden soubor, jen stdlib; výchozí `flux-local`, placené jen `backend=` + `confirm_cost=True`.
- `start-grafik.bat`: Engine :8300, starý editor API :8301 + UI :5173.
- Testy: `tests/test_engine_v2.py` (24, offline s falešným sd-serverem).

## Další krok

- P1/P2: napojit KLAPKA a NG-ROBOT přes `grafik_client` (vlastní sessions v těch projektech; NG-ROBOT musí brát `~/.gpu-lock` i při dabingu).
- G2: nové studio UI (React, :5173 po vyřazení starého editoru) — rozpis podle specu § 7.
- G1 zbytky: fal backend, `supersample`, živé ověření popisu stylu přes Haiku (placené, jen se souhlasem).

## Starý GRAFIK (v1)

Unified Editor M2–M6-UX1 (vrstvy Qwen-Layered, SAM, motion, React editor `ui-web/`) — funkční, popsán v `CLAUDE.md`. Od 22. 10. jen reference; API přesunuto na :8301. O archivaci rozhodne operátor po G2.
