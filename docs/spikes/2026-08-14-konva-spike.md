# Konva spike — 5× 4K RGBA vrstev: FPS, hit-test, paměť (task 1.1)

**Datum:** 2026-08-14 · **Verdikt: GO na Konva** (falsifier A5 nevystřelil, PixiJS fallback netřeba)

## Setup

- `ui-web/` — Vite + React 19 + TypeScript strict + react-konva 19.2.5 / konva 10.3.0
- 5 vrstev **4096×2304 RGBA** generovaných za běhu (soft-edge bloby, alfa díry, per-pixel noise) — žádné binárky v repu
- 1 `Stage` 1600×900, 1 `Konva.Layer`, 5 draggable `Image` nodes
- Alfa hit-test: `node.cache({pixelRatio: 1})` + `node.drawHitFromCache(0)` — klik prochází průhlednými dírami na vrstvu pod nimi; `Transformer` (resize+rotate) na kliknutou vrstvu
- Měřeno: headed Chromium 151 (Playwright, `ui-web/bench-runner.mjs`) na stroji uživatele, devicePixelRatio 1.0

## Naměřené hodnoty (auto-benchmark, `window.__benchResults`)

| Fáze | Avg FPS | Min FPS | Pozn. |
|---|---|---|---|
| idle (force batchDraw, 3 s) | **56,9** | 11,4 | min = ojedinělý propad prvních frames |
| drag (sinusoida ±300 px, 5 s) | **50,0** | 20,0 | programový drag top vrstvy |
| transform (scale 1→1,3 + rotace 0→15°, 5 s) | **51,7** | 21,7 | bez re-cache — transformace cached bitmapy |
| po benchmarku (live overlay, klid) | ~212 | — | viz screenshot |

- **Hit-test:** 300× `stage.getIntersection()` = 6,30 ms/volání — OK pro klik; nevolat per-mousemove.
- **Paměť:** JS heap po doběhnutí ~16 MB (generační buffery uklizeny GC). Bitmapy žijí mimo JS heap — teoreticky **540 MB** (5 × 4096×2304×4 B × 3: source + cache scene + cache hit canvas).
- Důkazy: `scratch/smoke/konva_spike_bench.png`, `konva_spike_selected.png` (Transformer na vybrané vrstvě + výsledkový panel).

## GO/NO-GO

Práh z plánu (A5): < ~30 FPS na 5× 4K = NO-GO. Naměřeno 50+ FPS při drag/transform → **GO**. Konva + react-konva potvrzeno jako canvas stack pro ui-web.

## Rizika / doporučení pro M2+

1. **Paměť škáluje ~108 MB/4K vrstvu** (source + 2× cache). Pro projekty s >8 vrstvami zavést downsamplované proxy cache (plné rozlišení jen pro export) nebo cache eviction neviditelných vrstev.
2. Na displejích s dpr > 1 roste stage canvas (cache je pinnutá na pixelRatio 1) — mírný dopad, změřit až při reálném UI.
3. Min FPS propady (11–21) jsou first-frame hiccupy fází, ne trvalý stav; při reálném dragu myší neviditelné.
4. `Transformer` mění scaleX/Y (ne width/height) — počítat s tím při ukládání transformací do project.json (plán to zmiňuje).

## Reprodukce

```bash
npm --prefix ui-web run dev
node ui-web/bench-runner.mjs
```
