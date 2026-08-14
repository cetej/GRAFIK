# Ideal State — GRAFIK Unified Editor (obraz + video, per-element kontrola)

Vzniklo: 2026-08-14, /brainstorm session (STOPA). Rozšíření projektu GRAFIK (`C:\Users\stock\Documents\000_NGM\GRAFIK`), NE nový projekt.

## Zamčená rozhodnutí (scope doc)

- **Co:** Sjednocený AI editor obrázků a klipů: dekompozice obrazu na vrstvy → živá manipulace prvků na canvasu + per-prvek AI promptování; image-to-video s per-prvek pohybem (maska + trajektorie) a kamerou.
- **Pro koho:** Interaktivní osobní tvorba (UI first); knihovní použití sekundárně.
- **Proč teď:** Frustrace z Higgsfield/OpenArt/MJ — nízká přesnost interpretace promptů, false-positive moderace, žádná per-element kontrola.
- **Architektura:** JEDEN projekt = rozšíření GRAFIKu (vrstva+maska = sdílený objekt obou domén). Video jako modul `grafik/motion/`.
- **UI:** Nový canvas frontend React + Konva.js nad stávajícím FastAPI; Streamlit zůstává do náhrady.
- **Modely:** Provider abstrakce, obojí přepínatelné — hostované (Nano Banana Pro, Kling, Seedance) + open-weight přes fal.ai (Qwen-Image-Edit, FLUX Fill, Wan 2.x).
- **OUT of scope V1:** timeline/střih, audio, batch, text-to-video bez vstupního obrázku, obcházení moderace hostovaných API.

## Ideal State Criteria

- [ ] Obrázek se rozloží na RGBA vrstvy jednou akcí — eval: decompose API test (existuje, regrese)
- [ ] Vrstvu lze myší posunout a škálovat na canvasu — eval: manuální check v novém UI
- [ ] Vybranou vrstvu lze přepromptovat AI editem s její maskou — eval: API call, výsledek nahradí obsah vrstvy
- [ ] Stejná edit operace routuje na hostovaný i open-weight provider — eval: `provider` param v API, oba průchody
- [ ] Export PNG odpovídá náhledu kompozice — eval: export test, pixel diff vs composite
- [ ] Prvku lze nakreslit trajektorii pohybu na canvasu — eval: UI check + trajektorie persistovaná v project.json
- [ ] Video request nese masku vrstvy + trajektorii (Kling dynamic_masks) — eval: inspect request payloadu
- [ ] Pohyb kamery (pan/tilt/zoom/roll) nastavitelný per klip — eval: camera_control v payloadu
- [ ] Vygenerovaný klip se uloží k projektu a přehraje v UI — eval: manuální check
- [ ] Obraz i video režim fungují v jednom UI nad jedním projektem — eval: manuální E2E průchod sc-1→sc-2
- [ ] Selhání generace (moderace/timeout) zobrazí důvod a nepoškodí projekt — eval: mock-fail test, projekt reload OK
- [ ] Stávající .grafik projekty se načtou beze změny — eval: load test na existujícím projektu

## Success criteria V1 (binární)

- sc-1: obrázek → vrstvy → posun/scale prvku → per-prvek AI edit → export PNG
- sc-2: označení prvku + trajektorie + kamera → klip přes Kling API
- sc-3: sc-1 i sc-2 z jednoho UI

## Další kroky greenfield flow

1. Výzkum (běží): Kling/Seedance API motion+camera parametry; NB Pro/Qwen-Image-Edit/FLUX Fill mask editing; canvas frontend prior art.
2. /premortem na záměr.
3. Plán → `outputs/plans/2026-08-14-grafik-unified-editor.md` (Plan Format).
4. Exekuce v NOVÉ session v GRAFIK repu (fresh-session test).
