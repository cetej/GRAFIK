# Stav GRAFIK

Aktualizováno 2026-10-22.

## Teď

**GRAFIK v2 — fáze G0 (spec) čeká na schválení operátorem.**
Spec: [`docs/plans/2026-10-22-grafik-v2-greenfield.md`](plans/2026-10-22-grafik-v2-greenfield.md). Rozhodnutí 22. 10.: [`DECISIONS.md`](DECISIONS.md).
Větev `claude/grafik-rebuild-fb1f3e`. Implementace nezačala.

Otevřené otázky pro operátora (spec § 3): Q1 rozhraní studia, Q2 kde žijí výstupy, Q3 formát karty stylu, Q4 cesta předloh z Pinterestu, Q5 starý GRAFIK a port 8300.

## Další krok

Po schválení specu G1 — GRAFIK Engine: správa `sd-server.exe` (jen vlastní PID), fronta + zámek GPU, `POST /api/v2/images`, provenience a náklady, `clients/grafik_client.py`. Hotovo = sc-1…sc-9 ve specu + PR.

## Starý GRAFIK (v1)

Unified Editor M2–M6-UX1 (vrstvy Qwen-Layered, SAM, motion, React editor `ui-web/`) — hotový a funkční, popsán v `CLAUDE.md`. Od 22. 10. jen reference, nové featury se do něj nepřidávají.
