# ngm_shared

Lehký sdílený kód projektů NGM, jeden zdroj místo kopií v každém projektu (rozhodnutí operátora 2026-10-29, `GRAFIK/docs/DECISIONS.md`). Žije v repu GRAFIK, opravuje se jedním PR v GRAFIKU a platí hned všude, kde je nainstalovaný editovatelně.

| Modul | Co | Závislosti |
|---|---|---|
| `ngm_shared.grafik_client` | klient GRAFIK Engine (`generate`, `submit(..., translate=)`, `variants`, `model3d`, `views`, `add_ref`, `ensure_engine`), CLI `python -m ngm_shared.grafik_client` | jen stdlib |
| `ngm_shared.variants_page` | stránka pro výběr z N variant; **kanonický zdroj je tady**, STOPA `scripts/manual/variants_page.py` je od 2026-10-29 jen re-export (úpravy se dělají v GRAFIKU) | jen stdlib |
| `ngm_shared.heavy_lock` | zámek těžké práce pro celý stroj (GPU, Blender, VectorCraft, přepis řeči, headless Chrome) | psutil, jen Windows |
| `ngm_shared.textlayer` | vrstva textu nad obrazem: pravidla NG pro popisky (`style`), rozložení (`layout`), pozadí pod textem (`raster`), složení ve VectorCraftu (`compose`, `vc_client` pod zámkem `vectorcraft`), kontroly vrstvy (`checks`); kopie z NG-ROBOT `ng_vector_labels` (commit v hlavičce modulu), bez zeměpisných poloh (ty má KARTOGRAF) | numpy, Pillow |
| `ngm_shared.textlayer.localize` | počeštění cizí infografiky: Claude přečte texty → `cv2.inpaint` vymaže → český text v původní velikosti → PNG a upravitelné SVG; mapa vrátí poradní upozornění „postaví KARTOGRAF“ | + opencv, anthropic |
| `ngm_shared.claude` | jedno volání Claude s cenou z `usage`; pod pytestem bez `GRAFIK_LIVE_TESTS=1` nic nezaplatí | anthropic |
| `ngm_shared.gpt` | jedno volání OpenAI se stejným rozhraním jako `claude.ask` a stejnou pojistkou v testech (`gpt.ask(content, system, what=, model=)`) | openai |
| `ngm_shared.research` | dossier faktů a obrazových podkladů z Wikidaty, Wikipedie a Commons (`free_dossier`, 0 USD); placené doplnění z webu (`web_research`) | anthropic jen pro placenou část |
| `ngm_shared.image_checks` | poradní kontrola obrázku proti zadání a kontrolnímu seznamu (`check_brief`, test T4) a kontrola logiky scény (`check_logic`: plán se skicou nebo hotový obrázek, „proč a kam děj směřuje“, fyzika, reálie, měřítko; test T7); Claude Opus 5.5 effort low, ~0,01 a ~0,05 USD | anthropic, Pillow |
| `ngm_shared.archive` | archiv výstupů fronty GRAFIK Engine s hledáním nad `GRAFIK/run/jobs.sqlite` (jen pro čtení, i bez běžícího Engine): slova bez diakritiky v zadání, promptu, stylu, počeštění; filtry volající, druh úlohy, datum, stav; cesta k obrázku a náhledu | jen stdlib (náhled Pillow) |
| `ngm_shared.knihovna` | sdílená knihovna postav, míst, rekvizit a stylů (složka `KNIHOVNA`, fáze 4): čtení, výpis, zápis pod zámkem karty a atomicky, předloha s původem a licencí, koš; společná karta stylu a text stylu do promptu obrázku (`image_text`) i videa (`video_lines`, `film_fields`) | PyYAML |
| `ngm_shared.knihovna_prevod` | převod KLAPKA `studio/library/` a GRAFIK `styles/` do knihovny: jen kopíruje, opakovatelný, `--dry-run`, při kolizi skončí bez zápisu | PyYAML |

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

Volitelné závislosti vrstvy textu: `pip install -e GRAFIK/shared[text]` (numpy, Pillow, opencv-python, anthropic).

## Vrstva textu a počeštění

```python
from ngm_shared.textlayer.localize import localize

r = localize("infografika-en.jpg", "vystup/")                           # placené čtení (~0,11–0,20 USD)
r = localize("infografika-en.jpg", "vystup/", texts=opravene_texty)     # znovu vysázet, zdarma
r["png"], r["svg"], r["warnings"], r["cost"]                              # cost = {model, in, out, usd} z usage
```

- Zapíše `image-0.png` (česky), `image-0.svg` (každý popisek jako `<text>`, podklad `image-0-bez-textu.png` vedle) a `image-0.texty.json` (přečtené texty s rámečky v pixelech originálu; jde opravit a vysázet znovu zdarma).
- Barvu a rozsah písma měří kód z pixelů: rámeček a barva od Claude jsou jen výchozí bod (oprava vady z testu T2, kde zůstaly v obraze popisky v barvě podkladu). Velikost písma vychází z původního textu hned v prvním průchodu, i u otočených popisků.
- Upozornění jsou poradní (`severity`, `what`, `fix`): mapa („postaví KARTOGRAF z dat“), stopy po mazání, příliš dlouhý překlad. Nic se neblokuje.
- GRAFIK Engine to nabízí jako úlohu ve frontě: `POST /api/v2/localize` (402 s odhadem bez `confirm_cost`).
- Kopie z NG-ROBOT: opravu z originálu přenes diffem od commitu v hlavičce modulu (`git -C NG-ROBOT diff f27580e9 -- ng_vector_labels/<modul>.py`). NG-ROBOT sám knihovnu nepoužívá a neměnil se.

## Kontrola proti zadání a kontrola logiky

```python
from ngm_shared.image_checks import check_brief, check_logic

r = check_brief("obrazek.png", "Dvě zelené hrušky na modrém talíři.")            # ~0,01 USD
r = check_logic("skica.png", "Dělníci zvedají jeřábem kvádr.", phase="plan", layout="kolo vlevo, stožár…")
r["warnings"]   # [{"severity": "vysoká|střední|nízká", "what", "why", "fix"}], seřazené od nejvážnější
```

Výsledek je vždy poradní (`advisory: true`), nic neblokuje. GRAFIK Engine: `POST /api/v2/checks` (`kinds: ["brief", "logic"]`, 402 s odhadem bez `confirm_cost`, výsledek u obrázku z knihovny se připíše do `image-<n>.checks.jsonl`).

## Archiv s hledáním

```python
from ngm_shared import archive

archive.search("krkonose")                                   # bez diakritiky, všechna slova
archive.search("", caller="ng-robot", kind="image", since="2026-10-28", until="2026-10-29", limit=20)
archive.search("liska", thumbs=True)[0]["images"][0]         # {path, exists, url, thumb_path, thumb_url}
archive.facets()                                             # volající a druhy úloh s počty, první a poslední den
```

Databáze `GRAFIK_JOBS_DB` nebo `C:/Users/stock/Documents/000_NGM/GRAFIK/run/jobs.sqlite`; otevírá se jen pro čtení. GRAFIK Engine: `GET /api/v2/archive?q=&caller=&kind=&since=&until=&status=done|all&limit=` a `GET /api/v2/archive/facets`.

## Sdílená knihovna postav, míst, rekvizit a stylů

Jedna složka pro KLAPKU i GRAFIK (DECISIONS 2026-10-29, fáze 4), mimo git: `NGM_KNIHOVNA`, výchozí `C:/Users/stock/Documents/000_NGM/KNIHOVNA`. Zálohu nemá. Rozložení je převzaté z KLAPKY a slug (název složky nebo souboru) je identita, scény, projekty i objednávky NG-ROBOT se na něj odkazují.

```text
KNIHOVNA/
  characters/<slug>/card.yaml     postava + refs/ (předlohy), stylized/, figura/, sources/, voice/
  environments/<slug>/card.yaml   místo + refs/
  props/<slug>.yaml               rekvizita + props/<slug>/ (model/ …)
  styles/<slug>.yaml              společná karta stylu
  styles/<slug>.png               náhled stylu z KLAPKY (GRAFIK ho ukazuje jako vzorek nahled.png)
  styles/<slug>/samples/<n>.jpg   vzorky stylu z GRAFIKU; styles/<slug>/STYLE.md = karta pro lidi
  .locks/  .trash/                zámky karet; smazané položky (nic se nemaže natrvalo)
```

```python
from ngm_shared import knihovna

knihovna.slugs("character")                       # ["caesar", "delnik", …]
card = knihovna.read("character", "caesar")       # dict, None když není
knihovna.cards("style")                           # {slug: karta}
knihovna.write("prop", "amfora", {"name": "Amfora", "count": 1})
knihovna.update("character", "caesar", {"voice": "deep"})          # nebo funkce karta -> nová karta
with knihovna.lock("character", "caesar"):        # delší úprava víc souborů jedné položky
    ...
knihovna.add_ref("character", "caesar", "busta.png", puvod={"origin": "commons", "author": "…", "license": "CC BY-SA 4.0"})
knihovna.images("character", "caesar")            # [{file, path, label, primary}], hlavní předloha první
knihovna.trash("style", "stary-styl")             # → KNIHOVNA/.trash/styles/<čas>-stary-styl/
```

- **Zápis jen přes tyto funkce.** Zámek karty platí pro vlákna i procesy (KLAPKA a GRAFIK Studio zapisují souběžně, test: 6 procesů × 25 úprav jedné karty bez ztráty), je re-entrantní ve vlákně jako `card_lock` v KLAPCE. Soubor se mění atomicky (dočasný soubor a `os.replace`), YAML píše stejně jako KLAPKA (`yaml.safe_dump`, diakritika, pořadí polí).
- **Předloha s původem**: `add_ref` zkopíruje obrázek do `refs/`, jiný soubor stejného jména nepřepíše (`-2`, `-3`), stejný soubor nepřidá podruhé. Původ a licence jdou do `<soubor>.puvod.json` s poli schránky předloh GRAFIKU (`origin, title, source_url, page_url, author, license, license_url, sha256, width, height, added`; `sha256` vždy ze souboru). Karta se nemění, hlavní předlohu volí projekt.
- **Obrázky položky jako předloha** (`images`): hlavní první jako KLAPKA `engine.load_entry` (výčet `refs:` z karty, jinak `refs/` podle abecedy bez `state-*` a `view-*` a s `primary` vpředu), za nimi stavy postavy a pohledy místa z karty. Rekvizita: obrázek, ze kterého je 3D model (`model/obrazek.*`, hlavní), `refs/` a bílé pohledy modelu. GRAFIK Engine je vypisuje na `GET /api/v2/knihovna` a do obrázku je bere jako předlohu `{"knihovna": "character/caesar"}` (hlavní) nebo `"character/caesar/refs/board-1.png"`; provenience zapíše celou cestu, původ a licenci z `.puvod.json`.
- **Společná karta stylu** (`styles/<slug>.yaml`): `name`, `note`, `look` (společný popis), `obraz` (`medium, light, line, composition, palette, signature` z GRAFIKU), `film` (`lens, grade`, případně `ref_style` z KLAPKY), `avoid` (GRAFIK `avoid` = KLAPKA `negative`), `constraints` (jen video; chybí-li, platí výchozí věta KLAPKY), `origin, puvod, created, updated`.
  - `knihovna.image_text(card)` = slova za „Style:“ v promptu obrázku: `look`, oddíl obraz (bez něj objektiv a barevné podání z oddílu film), paleta, „avoid …“. Pro styl z GRAFIKU stejný text jako dřív `engine/styles.py`.
  - `knihovna.video_lines(card)` = řádky stylu v promptu videa jako KLAPKA `engine.build_shot` („Style: look, lens, grade.“, constraints, „Avoid: ….“); `knihovna.film_fields(card)` = pole třídy `Style` v KLAPCE. Styl z GRAFIKU bez popisu filmu dostane `look` z média, světla a linky.
  - Převody: `knihovna.from_grafik(style_json)`, `knihovna.from_klapka(yaml_karty)`.
- **Převod** (jen kopíruje, zdroje zůstanou jako záloha; opakované spuštění nic nezmění; kolize = konec bez zápisu):

  ```bash
  python -m ngm_shared.knihovna_prevod --dry-run
  python -m ngm_shared.knihovna_prevod [--klapka KLAPKA/studio/library] [--grafik GRAFIK/styles] [--cil DIR]
  ```

- **Testy** si knihovnu přesměrují samy (`shared/tests/conftest.py`, `tests/conftest.py` nastaví `NGM_KNIHOVNA` už při načtení). Projekt, který knihovnu použije, musí ve svých testech udělat totéž, jinak zapíše do skutečné KNIHOVNY (LEARNINGS 2026-10-29).

## Placená volání v testech

`ngm_shared.claude.ask` pod pytestem bez `GRAFIK_LIVE_TESTS=1` skončí chybou, ještě než vytvoří klienta: testy předávají vlastní `ask`, zapomenutý mock nestojí peníze. Živý test jen výslovně: `GRAFIK_LIVE_TESTS=1 python -m pytest …`.

## Zámek těžké práce

- Soubor `~/.gpu-lock` (JSON `{owner, pid, since, kind, caller}`), stejná cesta a formát jako dřívější zámek GPU v GRAFIK Engine. Změny jdou přes krátký zámek OS na `~/.gpu-lock.mutex` a soubor se mění atomicky, takže ho dva procesy nikdy nevezmou zároveň.
- Opuštěný zámek (proces skončil, nebo jeho PID mezitím dostal jiný, později spuštěný proces) převezme další volající.
- Prázdný nebo rozepsaný soubor zámku se 10 s počítá jako obsazený.
- `holder()` vrací držitele pro UI; GRAFIK Engine ho ukazuje v `GET /api/v2/health` → `heavy_lock`.

## Testy

```bash
python -m pytest GRAFIK/shared/tests -q
```

Skutečný VectorCraft (těžká práce, až ~1,2 GB paměti grafiky) jen výslovně: `GRAFIK_VECTORCRAFT_TESTS=1`.
