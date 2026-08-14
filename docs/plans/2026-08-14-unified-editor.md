# Plán: GRAFIK Unified Editor — obraz + video s per-element kontrolou

Datum: 2026-08-14 · Plánovací session: STOPA (greenfield šablona, varianta „rozšíření existujícího projektu")
Cílový projekt: **GRAFIK** (`C:\Users\stock\Documents\000_NGM\GRAFIK`) · Exekuce: NOVÁ session v GRAFIK repu
Ideal-state kritéria: `STOPA/.claude/memory/intermediate/ideal-state-grafik-unified-editor.md` (12 binárních kritérií — akceptační testy)

## Goal

Rozšířit GRAFIK na sjednocený AI editor obrázků a klipů: obraz rozložený na vrstvy/prvky → živá manipulace na canvasu + per-prvek AI promptování; image-to-video režim, kde uživatel označí, které prvky se hýbou (maska + trajektorie) a jak se hýbe kamera. Motivace: web appky (Higgsfield/OpenArt/MJ) nedávají per-element kontrolu, interpretují mega-prompty nepřesně a blokují false-positives; úzké maskované operace obojí strukturálně zlepšují.

## Success Criteria (binární)

- **sc-1**: obrázek → vrstvy → posun/scale prvku na canvasu → per-prvek AI edit (mask inpaint) → export PNG odpovídající náhledu
- **sc-2**: označení prvku + nakreslená trajektorie + kamera → klip vygenerovaný přes Kling API (dynamic_masks), uložený k projektu, přehratelný v UI
- **sc-3**: sc-1 i sc-2 proveditelné z jednoho UI nad jedním `.grafik` projektem
- **sc-4**: stávající `.grafik` projekty se načtou beze změny (backward compat)

## Zamčená rozhodnutí (z /brainstorm 2026-08-14, potvrzeno uživatelem)

1. **Jeden projekt = rozšíření GRAFIKu**, ne nový projekt. Vrstva s alfa maskou je sdílený objekt obou domén (edit prvek ↔ motion region).
2. **UI first** (interaktivní osobní tvorba); knihovní použití sekundárně.
3. **Nový canvas frontend React + react-konva** nad stávajícím FastAPI; Streamlit freeze (bugfix-only) do parity.
4. **Provider abstrakce, hostované + open-weight přepínatelné** (NB Pro, Kling, Seedance / Qwen-Image-Edit, FLUX Fill, Wan, SAM 3 — vše kromě NB Pro přes fal.ai, kde GRAFIK už má klienta i účet).
5. **OUT V1**: timeline/střih, audio, batch, text-to-video bez vstupního obrázku, obcházení moderace hostovaných API.

## Research findings (3 subagent reporty, 2026-08-14; plné verze v session transkriptu)

### Video/motion API — gating fakta

| Model | Per-element motion | Kamera | Cena 5s |
|---|---|---|---|
| **Kling 1.6 Pro** (fal.ai `fal-ai/kling-video/v1.6/pro/image-to-video`) | ✅ `dynamic_masks` (mask_url + trajectories [{x,y}]), `static_mask_url` | ✅ enum `camera_control` + `advanced_camera_control` (pan/tilt/roll/zoom/horizontal/vertical + movement_value) | ~$0.28 / 720p |
| Kling 2.1 Pro (fal.ai) | ❌ pole v schema chybí (ověřeno fetchem) | ❌ chybí | — |
| Kling 2.5/2.6/3.0 | ❓ neověřeno (task 1.4) | ❓ | — |
| Seedance 2.0 (fal.ai) | ❌ (negativní zjištění, kompletní schema bez mask polí) | jen textový prompt | ~$1.51 |
| Wan 2.2 A14B (fal.ai) | ❌ (Fun/VACE varianty = video-to-video control; VACE deprecated) | jen prompt | ~$0.40 |

→ **Per-element motion control má jedinou potvrzenou API cestu: Kling 1.6 Pro přes fal.ai.** Ceny z fal.ai (statické, ověřitelné); oficiální kling.ai docs nefetchnutelné (HTTP 446) — fal wrapper bereme jako zdroj pravdy o schématu.

### Obrazové API

- **Nano Banana Pro (Gemini API): pixel masku NEBERE** (oficiální docs: jen sémantické edity textem + až 14 ref. obrázků; $0.134/obr 1–2K, $0.24/4K, SynthID watermark). Role: generace celých obrázků / globální edity, NE per-prvek.
- **Per-prvek edit: Qwen-Image-Edit inpaint** (fal, `mask_url`, $0.03/MP, `enable_safety_checker` param) **a FLUX.1 Fill [pro]** (fal, `mask_url`, $0.05/MP) — obě potvrzené mask-based cesty.
- **SAM 3** (fal, `fal-ai/sam-3/image`): text-prompted segmentace („the dog" → maska), $0.005/request, až 32 masek. Druhá, jemnější cesta k prvkům vedle dekompozice.
- **Qwen-Image-Layered**: rekurzivní dekompozice ✅; **preferované rozlišení 640 px**; text-to-layers režim autoři sami označují za nekvalitní → nepoužívat.

### Canvas frontend

- **React + react-konva pokrývá ~90 % nativně**: `Transformer` (drag/resize/rotate; pozor — mění scaleX/Y, ne width/height), `image.cache()` + `drawHitFromCache(alphaThreshold)` (výběr klikem přes alfu), oficiální vzor bezier křivky s draggable anchor pointy (trajektorie). Vlastní práce: brush-mask tool (~50 řádků, offscreen canvas) + TrajectoryPath komponenta (~1 den).
- Polotno SDK zamítnut ($899+); tldraw/Excalidraw špatný fit; PixiJS = výkonový fallback (ale bez hotového Transformer/hit-test).
- Referenční UX + pravděpodobně i stack: **InvokeAI Unified Canvas** (Apache 2.0) — před stavbou nahlédnout do frontend zdrojáku.

## Architektura (rozhodnutí + alternativa + falsifier)

### A1. Masky jako lingua franca, plné rozlišení jako plátno pravdy
Dekompozice (640 px) a SAM 3 produkují **masky a navigaci**; generativní edity (inpaint) běží **nad originálem v plném rozlišení** s upscalovanou maskou. Pixel data vrstvy z dekompozice se do finálního exportu dostanou jen u transform-only operací.
- Alternativa: editovat přímo 640px vrstvy a upscalovat výsledek (jednodušší, ale ztrátové).
- **Falsifier**: upscale masky (bilinear + threshold/feather) produkuje viditelné švy na hranicích editů → nutný SAM 3 refine masky v plném rozlišení.

### A2. Provider vrstva s capability map
`grafik/providers/`: `ImageEditProvider.edit(image, mask, prompt)`, `VideoProvider.generate(image, MotionSpec)`, `SegmentProvider.segment(image, text)`. Registry deklaruje capabilities (`supports_mask`, `supports_dynamic_masks`, `supports_camera_params`, `supports_camera_prompt`). UI degraduje podle capability (model bez masek → prompt-based motion).
- Alternativa: přímé volání fal endpointů z API routes (méně kódu, ale video fallback a přepínání modelů by prorostlo do routes).
- **Falsifier**: capabilities se ukážou být per-verze-endpointu tak fragmentované, že map nestačí a potřebujeme per-provider UI větve → přehodnotit na provider-driven UI schema.

### A3. MotionSpec jako kompilovaný meziformát
Pydantic model: per-layer `trajectory: [{x,y}]` (souřadnice v plném rozlišení), `static: bool`, globální `camera: {type, magnitude} | prompt`, `duration`. Kompiluje se na: (a) Kling payload — alfa masky vrstev → binární `dynamic_masks.mask_url`, union statických → `static_mask_url`, kamera → `camera_control`/`advanced_camera_control`; (b) **textový popis pohybu** pro prompt-only modely (Seedance/Wan/Kling 2.x fallback).
- Alternativa: ukládat rovnou Kling payload (méně vrstev, ale zamyká na jednoho providera a jednu verzi).
- **Falsifier**: Kling 1.6 odmítne masky odvozené z alfa kanálů (formát/hodnoty/rozměry) → zjistí smoke test task 1.2 první den.

### A4. Video joby jako async fronta s persistencí
`grafik/motion/jobs.py`: submit → job record v projektu (status, params, cost) → polling → výsledek (mp4) do `.grafik/clips/`. Žádný sync čekající request (generace = minuty).
- **Falsifier**: fal queue API nedává stabilní job-id napříč restarty → lokální mapping file.

### A5. Frontend `ui-web/` (Vite + React + react-konva), Streamlit freeze
Nová funkcionalita jen v React UI; Streamlit jen bugfix, sunset po paritě (M5).
- **Falsifier**: Konva spike (task 1.1) < ~30 FPS na 5× 4K RGBA vrstvách → PixiJS fallback (a přepis transform/hit-test toolingu — dražší, proto spike PRVNÍ).

### A6. project.json schema v2
`Layer.motion` pole + `clips[]` + `schema_version`. Loader v1 projekty čte beze změny (sc-4).

## Premortem (co projekt zabije)

1. **Kling 1.6 deprecation / motion brush nedoputuje do 2.x API** → celá per-element video osa stojí na jednom endpointu jedné starší verze. Mitigace: A3 prompt-fallback od začátku; task 1.4 ověří 2.1 Standard/2.5/2.6 schémata; sledovat fal changelog. Reziduum: kvalita 1.6 < 2.x — uživatel musí vidět trade-off „kontrola vs. kvalita" v UI.
2. **Konva výkon na 4K vrstvách** → spike je task 1.1, PŘED zafixováním stacku (falsifier A5).
3. **Kvalita dekompozice** (640 px, halucinovaný obsah za objekty, hraniční artefakty) → A1 dělá z dekompozice navigaci, ne zdroj pravdy; SAM 3 jako alternativní cesta k prvkům; rekurzivní dekompozice až M4.
4. **Frontend scope creep** (editor UI je bezedná jáma) → V1 přísně: jen operace z ideal-state kritérií; žádné filtry, žádný timeline; každý PR proti kritériím.
5. **Async video ekonomika** (minuty latence, fail rate, kredity) → A4 job queue + cost log per job; mock-fail test (ideal-state #11); zobrazená odhadovaná cena PŘED submitem.
6. **Happy-path assumption: fal proxy Kling parametrů je věrná** (oficiální docs 446) → smoke test 1.2 s reálným callem je v prvním týdnu; dokud neprojde, nestavět motion UI.
7. **Two-frontend drift** (Streamlit vs React) → freeze pravidlo v GRAFIK CLAUDE.md, nová funkce = jen React.
8. **Moderace očekávání**: open-weight cesta snižuje false-positives, ale fal.ai ToS a moderace hostovaných modelů platí dál — nástroj to komunikuje (fail message s důvodem, ideal-state #11), neslibuje „vše projde".

## Tasks — Fáze 1: Walking skeleton (exekuce v GRAFIK repu, nová session)

Cíl fáze: E2E důkaz obou os (obraz-edit, video-motion) dřív, než se investuje do UI.

1. **Konva spike** — `ui-web/` Vite scaffold, 5 vrstev 4K RGBA + Transformer + alfa hit-test, změřit FPS/paměť. Výstup: čísla do `docs/` + GO/NO-GO na Konva. (1–2 d)
2. **Kling smoke test** — skript `scripts/smoke_kling_motion.py`: existující GRAFIK vrstva → alfa → binární maska → `dynamic_masks` + trajektorie + `advanced_camera_control` na `fal-ai/kling-video/v1.6/pro/image-to-video` → klip. Ověří A3 falsifier. (~0,5 d + jednotky $ kreditů)
3. **Inpaint smoke test** — skript: maska vrstvy (upscale na plné rozlišení) + prompt → `fal-ai/qwen-image-edit/inpaint` → diff s originálem mimo masku. Ověří A1 falsifier. (~0,5 d)
4. **Schema-fetch Kling 2.1 Standard / 2.5 / 2.6 / 3.0** na fal.ai — má některý `dynamic_masks`? Výsledek do capability map. (30 min)
5. **`grafik/providers/` skeleton** — base classes + capability map + registrace Qwen-Image-Edit, FLUX Fill, Kling 1.6, SAM 3. (1 d)
6. **MotionSpec model + project.json v2** — Pydantic + loader backward-compat test na existujícím projektu (sc-4). (0,5 d)
7. **API routes** — `POST /layers/{id}/ai-edit` (provider param), `POST /segment` (SAM 3), `POST /video/jobs` + `GET /video/jobs/{id}`. (1 d)
8. **ui-web MVP canvas** — load projektu přes API, vrstvy s Transformer + alfa hit-test, uložení transformů. (2 d)

Gate fáze 1: tasky 1–3 prošly → architektura potvrzena; jinak zpět k A1/A3/A5 falsifierům.

## Milestones M2–M5

- **M2 — obrazová osa komplet** (sc-1): mask brush, SAM 3 segmentace z textu, per-prvek AI edit v UI, inpaint pozadí za vyjmutým prvkem, propojení na existující ops/undo-redo, export. 
- **M3 — motion osa komplet** (sc-2): TrajectoryPath tool, camera panel, MotionSpec kompilace, job queue + status UI + přehrávač, cost display.
- **M4 — provider šíře**: NB Pro (generace vstupu, globální edity), FLUX Fill jako druhý inpaint, Seedance/Wan prompt-based fallback, rekurzivní dekompozice, cost tracking souhrnně.
- **M5 — konsolidace**: Streamlit sunset po paritě, GRAFIK CLAUDE.md update, `/grafik` STOPA skill, NG-ROBOT knihovní API.

## Out of Scope (V1)

Timeline/vícezáběrový střih · audio · batch processing · text-to-video bez vstupního obrázku · trénink/fine-tuning modelů · obcházení moderace hostovaných API · mobilní UI.

## Exekuční tier doporučení

| Fáze | Tier / model |
|---|---|
| Tasky 1.1–1.4 (spiky, smoke testy) | přímo v GRAFIK session, Sonnet |
| Tasky 1.5–1.8 + M2 (module-bounded) | `/orchestrate-mezo` (Sonnet workeři) |
| M3 (motion UI, cross-module integrace) | `/orchestrate-deep` nebo `/build-project` v GRAFIK repu (Opus main loop, Sonnet/Haiku workeři) |
| M4–M5 | `/orchestrate-mezo` per modul |

## Fresh-session handoff prompt (pro novou session v GRAFIK repu)

> GRAFIK Unified Editor — Fáze 1 (walking skeleton). Přečti plán `STOPA/outputs/plans/2026-08-14-grafik-unified-editor.md` a ideal-state kritéria `STOPA/.claude/memory/intermediate/ideal-state-grafik-unified-editor.md`. Proveď tasky 1.1–1.4 (spike + smoke testy) NEJDŘÍV — jsou to falsifiery architektury; teprve po jejich průchodu pokračuj 1.5–1.8. Nestav nic z M2+ dokud gate fáze 1 neprojde. FAL_API_KEY je v GRAFIK `.env`.
