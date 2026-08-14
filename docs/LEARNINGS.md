# LEARNINGS — GRAFIK

## 2026-08-14 — fal I2V: jméno image pole driftuje mezi verzemi, defaulty umí zdvojnásobit cenu

**Kontext:** M3 příprava. Raw OpenAPI fetch (metodika viz níže „jediný zdroj pravdy") odhalil, že `fal-ai/kling-video/v2.6/pro/image-to-video` bere **`start_image_url`** (REQUIRED), zatímco v1.5/v1.6 i Wan/Seedance berou `image_url`. Sdílený `build_video_payload` z fáze 1 posílal `image_url` všem → na Kling 2.6 by submit spadl na validaci (latentní bug, nikdy nevolán naostro — mock testy tvar payloadu vůči schématu neověřují). Navíc rizikové defaulty: Kling 2.6 pro a Seedance 2.5 mají `generate_audio` **default True** (≈2× cena), Wan 2.6 má `resolution` default **1080p** ($0.15/s místo $0.10/s) a `enable_prompt_expansion` default True (model přepisuje náš prompt — proti smyslu kompilovaného MotionSpec promptu).

**Poučení:**
1. Payload builder pro video musí být **per-endpoint mapovaný z registry** (image_field + payload_defaults + duration_choices), ne sdílený tvar. Capability sweep má zaznamenávat i jména povinných polí a defaulty, ne jen existenci featur.
2. Schema defaulty jsou součást capability dat — default, který tiše zdvojnásobí cenu nebo přepíše prompt, je stejně důležitý jako existence pole.
3. Mock testy payload tvaru neodhalí drift vůči reálnému schématu — při přidání video providera vždy znovu fetchnout raw OpenAPI a diffnout povinná pole.

## 2026-08-14 — Hit-test musí sdílet transformační model s rendererem

**Kontext:** M2 E2E — serverová route `/hittest` predikovala „Layer 1", reálný klik v editoru vybral „Layer 0". Server testuje alfu v nativních pixelech PNG (`lx = x - layer.x`), klient renderuje protažené na `layer.width/height` (a decompose může uložit width/height ≠ rozměry PNG). Dvě „správné" odpovědi na tentýž bod.

**Poučení:** Jakákoli geometrická logika (hit-test, maska→souřadnice, budoucí trajektorie) musí explicitně říct, v jakém prostoru počítá (nativní PNG vs. layout width/height vs. canvas), a sdílet přepočet s composerem/rendererem. Pro UI výběr je autoritativní klientský Konva `drawHitFromCache`; `/transform` snapshot fix ukázal totéž z druhé strany — každá mutace stavu musí jít přes tentýž history mechanismus.

**Opraveno (2026-08-14):** `/hittest` invertuje forward model composeru v jeho pořadí: un-translate → inverzní rotace kolem kotvy (Konva cw, y-down) → rescale layout→nativní px (`math.floor`, ne `int()` — truncation k nule by pustila body těsně vlevo/nad vrstvou). Regresní testy `tests/test_api_hittest.py` mají ručně odvozenou geometrii (syntetická vrstva s levou půlkou opaque) a na starém kódu selhávaly přesně E2E symptomem (vrácen jiný layer). Pořadí operací pinuje test rotace+scale — scale-before-rotate by četl průhledný pixel.

## 2026-08-14 — Worktree session nemůže smazat vlastní adresář

Claude Code host drží Windows handle na cwd worktree po celou dobu session — `git worktree remove` odregistruje, ale smazání adresáře selže „Device or resource busy", i když procesy uvnitř skončily (obsah smazat jde, zbyde prázdná skořápka). Řešení: po merge hned smazat větev + `git worktree prune`, prázdný adresář smazat odloženě (detached retry skript) nebo z jiné session. Pozor: i wrapper `run_in_background` úlohy drží handle spawn-cwd — dlouhoběžící servery spouštět `Start-Process -WorkingDirectory <hlavní checkout>`, ne z worktree.

## 2026-08-14 — RTK hook blokuje víceřádkový `git commit -m`

Víceřádkový commit message v `-m` přes Bash selže ještě před spuštěním: RTK PreToolUse hook přepíše příkaz a přepsaný vstup neprojde schema validací („command contains control characters that would be hidden in the approval dialog"). Obejití: zapsat message do souboru (scratchpad) a `git commit -F <soubor>`.

## 2026-08-14 — RTK hook maskuje pytest výstup

`python -m pytest` přes Bash s RTK hookem hlásí „No tests collected", i když testy proběhly. Obejít: `rtk proxy python -m pytest tests/... -q` — ukáže reálný výstup. Platí pro celou session i subagenty.

## 2026-08-14 — fal.ai schema: jediný zdroj pravdy je syrový OpenAPI JSON

**Kontext:** Plánovací research (unified editor, 2026-08-14) tvrdil, že Kling 1.6 Pro má `dynamic_masks` + `advanced_camera_control`. Task 1.4 to vyvrátil raw fetchem: motion brush existuje jen na `v1/standard` a `v1.5/pro`, kamerová kontrola na žádném image-to-video endpointu (jen `v1/standard/text-to-video`). Detail: `docs/capabilities/kling-versions.md`.

**Poučení:**
1. Jediný zdroj pravdy o fal endpointu je syrový OpenAPI JSON: `curl "https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=<id>"` + grep na přesná jména polí. WebFetch/WebSearch AI souhrny si pole vymýšlejí (fabrikovaly `static_mask_url` u „Kling 2.0 Master", který nic takového nemá).
2. fal může neznámá pole v payloadu tiše ignorovat — „úspěšný" call nedokazuje, že feature fungovala. Před stavbou na parametru ověř jeho existenci ve schématu; jinak vzniká falešná evidence.
3. Neexistující endpoint vrací doslova `null` (4 byty) — levný existence check.

**Aplikace:** Provider capability map (`grafik/providers/`) plnit výhradně z raw schema fetchů s datem ověření; capability zápisy patří do `docs/capabilities/` s reprodukovatelnými URL.

## 2026-08-14 — Kling motion brush: mrtvá API cesta (gate Fáze 1)

**Kontext:** Smoke testy task 1.2. v1.6+ pole `dynamic_masks` nemá a **payload s neznámými poli tiše přijme** (klip se vygeneruje bez motion controlu — falešný „úspěch"). v1.5/pro pole má, ale efekt slabý (in/out diff 1,40×→1,04). Detail: `docs/spikes/2026-08-14-kling-smoke.md`, verdikt: `docs/plans/2026-08-14-phase1-gate.md`.

**Poučení:** Per-element video motion nestavět na API mask parametrech — kompilovat MotionSpec na strukturovaný prompt + pixel-diff verifikaci výsledného klipu vůči masce. Capability sweep je datovaný snapshot: discovery přes fal search je neúplná (Seedance 2.5 a GPT-Image 2 doplnil až uživatel) → capability map musí nést `verified_at` a jména modelů od uživatele brát jako discovery vstup.

## 2026-08-14 — Qwen inpaint: empirický output cap ~1536 px (4K re-test A1)

**Kontext:** Re-test A1 na 4K (`smoke_inpaint.py --long-edge 3872`, plátno 2862×3872 ≈ 11 MP). Endpoint vrátil **1536×1536 bez ohledu na požadované `image_size`** — schema přitom deklaruje max 14142 px (empirie ≠ schema). Paste-back metriky drží i na 4K: outside-mask diff po paste-backu 0.024 (baseline 0.095), boundary ratio 1.063, beze švů → **A1 PASS na 4K**.

**Poučení:**
1. Resize-back výsledku na vstupní rozměr (v `QwenInpaintProvider._run_remote`→`edit`) je **load-bearing** větev — nad ~1536 px dlouhé hrany by se bez ní výsledek vůbec nesložil s originálem.
2. Efektivní detail vygenerovaného obsahu uvnitř masky je na 4K plátně jen ~1.5K (upscale LANCZOS) → pro jemné edity na velkých plátnech zvážit crop-based workflow (poslat endpointu jen výřez kolem masky) — kandidát M3/M4, ne M2.
3. Schema `max` hodnoty jsou jen deklarace — ke capability ověření patří i empirický behavior test (rozšíření pravidla „jediný zdroj pravdy je raw OpenAPI": schema říká, co API *přijme*, ne co *udělá*).

Detail: `docs/spikes/2026-08-14-inpaint-4k.md`.

## 2026-08-14 — Qwen inpaint: paste-back v pixel space je povinný

**Kontext:** Smoke test `fal-ai/qwen-image-edit/inpaint` (task 1.3): raw výstup endpointu má globální drift i mimo masku (mean diff ~20/255, 48 % pixelů), tj. endpoint překóduje celý obraz.

**Poučení:** Výsledek inpaintu nikdy nebrat celý — vždy kompozitovat zpět jen vnitřek masky (feather ~2 px, dilate ~4 px) nad originál. Pak je diff mimo masku ~0 a hranice bez švů (gradient ratio 1.035 @ 544×736). Před M2 přeměřit na 4K.
