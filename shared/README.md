# ngm_shared

Lehký sdílený kód projektů NGM, jeden zdroj místo kopií v každém projektu (rozhodnutí operátora 2026-10-29, `GRAFIK/docs/DECISIONS.md`). Žije v repu GRAFIK, opravuje se jedním PR v GRAFIKU a platí hned všude, kde je nainstalovaný editovatelně.

| Modul | Co | Závislosti |
|---|---|---|
| `ngm_shared.grafik_client` | klient GRAFIK Engine (`generate`, `submit(..., translate=)`, `variants`, `model3d`, `views`, `add_ref`, `ensure_engine`), CLI `python -m ngm_shared.grafik_client` | jen stdlib |
| `ngm_shared.variants_page` | stránka pro výběr z N variant; **kanonický zdroj je tady**, STOPA `scripts/manual/variants_page.py` je od 2026-10-29 jen re-export (úpravy se dělají v GRAFIKU) | jen stdlib |
| `ngm_shared.heavy_lock` | zámek těžké práce pro celý stroj (GPU, Blender, VectorCraft, přepis řeči, headless Chrome) | psutil, jen Windows |

Staré cesty `GRAFIK/clients/grafik_client.py` a `GRAFIK/clients/variants_page.py` zůstávají jako re-export, CLI i `import grafik_client` fungují beze změny.

## Instalace do projektu (fáze 2)

1. Do venv projektu nainstaluj knihovnu editovatelně **z hlavního checkoutu GRAFIK** (ne z worktree, ten se smaže):

   ```bash
   <projekt>/.venv/Scripts/python -m pip install -e C:/Users/stock/Documents/000_NGM/GRAFIK/shared
   ```

   Projekt bez venv (systémový Python): `python -m pip install -e C:/Users/stock/Documents/000_NGM/GRAFIK/shared`.
2. Ověř, že se načte z GRAFIKU:

   ```bash
   <projekt>/.venv/Scripts/python -c "import ngm_shared.grafik_client as g, ngm_shared.heavy_lock as h; print(g.__file__, h.holder())"
   ```

   Cesta musí končit `GRAFIK\shared\ngm_shared\grafik_client.py`; `holder()` vrátí `None` (volno) nebo kdo zámek drží.
3. V kódu nahraď kopii klienta importem a kopii smaž:

   ```python
   from ngm_shared.grafik_client import generate, submit, wait, download, ensure_engine
   ```

   Kopie v KARTOGRAFU a HEGEMONU měly navíc jen `translate=` v `submit()`; to knihovna umí.
4. Těžkou práci (Blender, VectorCraft, Whisper/TTS, headless Chrome render) obal zámkem:

   ```python
   from ngm_shared.heavy_lock import HeavyBusy, heavy

   with heavy("blender", owner="klapka", caller="scena-12", wait_s=600):
       subprocess.run([...])
   ```

   Druhy: `gpu`, `blender`, `vectorcraft`, `speech`, `chrome-render`. Po `wait_s` přijde `HeavyBusy` s čitelnou zprávou a `.holder` (kdo drží). Obrázky přes GRAFIK Engine zámek neberou, Engine si ho bere sám.
5. Do `requirements.txt` projektu (nebo do dokumentace instalace) zapiš řádek `-e C:/Users/stock/Documents/000_NGM/GRAFIK/shared`, ať nový venv knihovnu dostane.
6. Zděděný soubor, který nejde přepsat (RUKOPIS: kopie z NG-ROBOT synchronizace, STOPA: cesta volaná skillem), nahraď tenkým průchodem podle `clients/grafik_client.py` (`sys.modules[__name__] = ngm_shared.grafik_client`) a v RUKOPIS ho dej do `owned` v `upstream/policy.toml`. Repo s CI mimo tento stroj (STOPA) přidá do CI requirements `ngm-shared @ git+https://github.com/cetej/GRAFIK.git@master#subdirectory=shared` (GRAFIK je veřejné repo).

## Zámek těžké práce

- Soubor `~/.gpu-lock` (JSON `{owner, pid, since, kind, caller}`), stejná cesta a formát jako dřívější zámek GPU v GRAFIK Engine. Změny jdou přes krátký zámek OS na `~/.gpu-lock.mutex` a soubor se mění atomicky, takže ho dva procesy nikdy nevezmou zároveň.
- Opuštěný zámek (proces skončil, nebo jeho PID mezitím dostal jiný, později spuštěný proces) převezme další volající.
- Prázdný nebo rozepsaný soubor zámku se 10 s počítá jako obsazený.
- `holder()` vrací držitele pro UI; GRAFIK Engine ho ukazuje v `GET /api/v2/health` → `heavy_lock`.

## Testy

```bash
python -m pytest GRAFIK/shared/tests -q
```
