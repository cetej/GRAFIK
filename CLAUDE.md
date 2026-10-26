# GRAFIK — obrazové studio a lokální obrazová služba

GRAFIK Engine (lokální FLUX 3 Klein, placené modely jen se souhlasem) a GRAFIK Studio. Starý editor s vrstvami (v1: `grafik/`, `ui/`, `ui-web/`) operátor 2026-10-23 odložil; kód je v gitu pod tagem `v1-final`.

## Části

Rozhodnutí: `docs/DECISIONS.md` · stav: `docs/STAV.md` · spec: `docs/plans/2026-10-22-grafik-v2-greenfield.md`.
- `engine/` — GRAFIK Engine :8300 `/api/v2` (jediný uživatel GPU pro všechny projekty; lokální FLUX 3 Klein výchozí, 0 USD; placené jen `backend=` + `confirm_cost`, nikdy fallback). sd-server :8390 spouští a vypíná jen podle vlastního PID (`run/sd-server.json`).
- `clients/grafik_client.py` — klient pro projekty (jen stdlib), kopírovat do projektu.
- Varianty k výběru: `grafik_client.py variants "zadání" --count N [--style slug …]` (nebo `variants()`) vygeneruje dávku, `manifest.json` a `varianty.html` (zvětšení, oblíbené, kombinace parametrů, text zpět agentovi) a stránku otevře. Když operátor vybírá vzhled, nabídni dávku místo iterace po jednom obrázku. Stránku dělá `clients/variants_page.py` = kopie STOPA `scripts/manual/variants_page.py` (needitovat tady, změnu udělat ve STOPA a zkopírovat; testy jsou ve STOPA). Placená dávka chce `--confirm-cost`, odhad je za celou dávku (`docs/spikes/2026-10-26-varianty.md`).
- `studio/` — GRAFIK Studio (React + Vite) na :5174, `/api` proxy na Engine; spuštění `npm --prefix studio run dev` nebo `start-grafik.bat`. Česká zadání překládá Engine (`engine/translate.py`), cena v tlačítku = souhlas (DECISIONS 2026-10-23).
- Předlohy: knihovna `refs/library/` (`engine/reflib.py`), Wikimedia Commons (`engine/commons.py`, vždy `filetype:bitmap`), Pinterest přes operátorův Chrome (`docs/pinterest.md`); průvodce historickým objektem `engine/workflows.py`. Předlohy pro lokální FLUX mají dohromady rozpočet ~1,1 MP (VRAM, LEARNINGS 2026-10-23).
- Styly (G4): karty `styles/<slug>/` (`style.json` = zdroj pravdy, `STYLE.md` se přepisuje), `engine/styles.py`, `/api/v2/styles`; do generátoru jen slovy (`style: "<slug>"`).
- Infografiky (G5): `engine/infographics.py`, `/api/v2/infographics`, `studio/src/Infographics.tsx` (jeden SVG renderer, Engine převádí přes Playwright na PNG/PDF); šablony schémat `schemas/*.svg`; text nikdy z modelu.
- Termdb: `engine/termdb.py` čte `BIOLIB/termdb.db` (sdílená s NG-ROBOT, jen čtení, `GRAFIK_TERMDB`); jednoznačné termíny jdou do překladu jako nápověda, `/api/v2/terms/check` pro kontrolu infografiky.
- 3D (spike): `scripts/3d/` (výřez předlohy, TRELLIS 2 přes fal, render v Blenderu `C:/Users/stock/tools/blender-5.2.3-windows-x64/`), modely `library/3d/`; render jde do FLUX jako `geometry` předloha.

## Servery

- **Jedním klikem**: `start-grafik.bat` (Engine :8300 + Studio :5174, jen pokud neběží; Engine s `--access-log` do `logs/engine.log`)
- **Engine**: `python -m uvicorn engine.app:app --port 8300 --host 127.0.0.1 --access-log`
- **Studio**: `npm --prefix studio run dev` → port 5174
- Restart jen podle PID z portu (`netstat -ano | findstr ":8300 .*LISTENING"`), nikdy podle jména procesu.

## Testy

- `rtk proxy python -m pytest tests/ -q` (POZOR: bez `rtk proxy` hook maskuje výstup — viz LEARNINGS)
- Živé ověření Engine: `docs/spikes/2026-10-22-g1-engine.md`.

## Konvence

- Encoding: UTF-8 všude; cesty přes `pathlib.Path()`.
- Klíče jen v env nebo `.env` (`FAL_API_KEY`), nikdy v configu ani commitu.
