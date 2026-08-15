# LEARNINGS — GRAFIK

## 2026-08-15 — Qwen I2L decompose: vrstvy v nativním rozlišení (~0,4 MP), ne v rozlišení vstupu

**Kontext:** Obnova projektu openart (`75778f1bd1a4`): `decompose/file` auto-setuje canvas z uploadu (1792×2400), ale I2L vrátí vrstvy 544×736 (3:4) — `FalClient.decompose` nastavoval `layer.width/height` z fal výstupu a canvas už neměnil → kompozit měl obsah jen v bboxu (0,0,544,736) vlevo nahoře (~30 % plátna). Endpoint dekompozice z URL rozměry zdroje vůbec nezná (canvas přebírá z prvního fal PNG), proto starší projekty (e2e-sc1, decompose-test) mají canvas == 544×736 a bug se u nich neprojevil; kanonický ui-web flow (`createProject` 0×0 + drag&drop) byl postižený u každého velkého vstupu.

**Poučení:**
1. I2L (qwen-image-layered) resampluje výstup na nativní rozlišení modelu ~0,4 MP (544×736 pro 3:4 — stejná rodina omezení jako inpaint cap ~1536 px). Rozměry fal výstupu nikdy nebrat jako rozměry zdroje.
2. Fix = varianta (a): `FalClient.decompose` roztáhne layout vrstev (width/height) na canvas projektu; pixel data zůstávají nativní a composer resizuje při kompozici (width/height ≠ PNG umí od M2 hittest fixe). Stejná hranice jako resize-back u QwenInpaintProvider — výstup provideru se mapuje do geometrie projektu hned na hranici provideru. Zachovává plné rozlišení plátna (export, budoucí crop-based inpaint). Varianta (b) — canvas z fal výstupu — by plátno degradovala na ~0,4 MP a přepisovala explicitně zadané rozměry projektu.
3. Kompatibilita: canvas se z fal výstupu setuje jen když nebyl → staré projekty (canvas == vrstvy 544×736) jsou no-op, projekty na disku se nemění.
4. Testovací nuance: mock fal musí vracet záměrně JINÝ rozměr než upload — mock se shodnými rozměry by tuhle třídu regresí nikdy neodhalil. Testy `tests/test_api_decompose_canvas.py` (offline, včetně pixel-proof kompozitu: roh plátna mimo nativní box musí být neprůhledný).
5. Obnova openart proběhla ještě před fixem: layout vrstev narovnán ručně přes `POST /layers/{id}/transform` na rozměr plátna — kompozit pak pokrývá celé plátno, mean diff vs zdroj 6,08/255 (před narovnáním 4,78/255 po downscale, ale jen v rohu); drobné roztažení aspektu jen vrací fal deformaci 544×736 zpět na poměr zdroje.

## 2026-08-15 — INCIDENT: tichá ztráta projektu během E2E; destruktivní routy bez access logu = nulová forenzika

**Kontext:** M2.5 E2E. Během okna s ~2 min zaseknutým uvicornem (corrupt multipart upload, pre-fix éra) a dvěma restarty API zmizel z disku projekt `openart-…grafik`; současně se v UI objevil failnutý request, který nikdo vědomě neposlal. API tehdy běželo bez access logu (Start-Process bez redirectu), takže neexistuje záznam requestů. Detail: `docs/spikes/2026-08-15-m25-e2e.md` (sekce INCIDENT).

**Dořešeno (tatáž noc):** náhodně zachycený `/api/projects` response z okamžiku incidentu (soubor `-w` z nepovedeného curlu) ukázal openart s **novým id** — manifest přepsal pre-fix `create_project` při kolizi jmen adresářů (nejspíš souběžný ruční drop `openart-image_….png` z Downloads); „rozbitý" 0-vrstvý projekt byl pak smazán přes UI ještě před startem logu. Root cause = bug opravený v `0d14ed2`; žádný replay/misroute.

**Poučení:**
1. Jakmile API dostane destruktivní routu (DELETE projektu), access log není nice-to-have ale podmínka provozu — `uvicorn --access-log` s `-RedirectStandardOutput logs/uvicorn-out.log` od prvního startu. Bez něj se incident nedá ani vyšetřit, ani vyvrátit (tady zdržel diagnózu o hodiny; vyřešila ho až náhodná stopa).
2. Před E2E nad živými daty udělat zálohu `projects/` (copy je levná; forenzika po ztrátě nemožná). Záloha session: `projects-backup-<stamp>/`.
3. „Tichý přepis dat" vypadá zvenku stejně jako „tiché smazání" — při ztrátě dat nejdřív hledat write-cesty s kolizí identifikátorů (tady `safe_name` adresáře), ne jen delete-cesty.
4. Neznámé soubory nalezené po incidentu jsou potenciální evidence — archivovat, pak mazat (tady byl soubor po přečtení smazán; obsah přežil jen v transcriptu).
5. Kandidát M4: soft-delete (koš) místo okamžitého `rmtree`.

## 2026-08-15 — fal schema defaulty: vynechaný klíč ≠ „bez hodnoty" — server si default dosadí sám

**Kontext:** SAM-3 point mode. `point_prompts` bez klíče `prompt` → **0 masek**: schema deklaruje `prompt` default `"wheel"`, server ho při chybějícím klíči dosadí a textová detekce „wheel" nic nenajde. `prompt: ""` + bod → maska prvku pod bodem (part-level granularita ~jednotky % plátna; celý objekt = víc bodů se stejným `object_id` / box / text). Empirie + payload pravidla: `docs/capabilities/sam3-point.md`, fix `ccdf5a8`, test `test_segment_remote_point_only_sends_empty_prompt`.

**Poučení:** Rozšíření pravidla „jediný zdroj pravdy je raw OpenAPI": fal pole s defaultem se chová, jako by ho poslal klient. Při stavbě payloadu projít defaulty VŠECH vynechaných polí (stejná rodina jako `generate_audio:true` u Klingu — default umí změnit cenu, tady umí vynulovat výsledek).

## 2026-08-15 — FastAPI: neošetřená výjimka = 500 bez CORS hlaviček → frontend vidí jen „Failed to fetch"

**Kontext:** Drop poškozeného PNG → PIL výjimka v `decompose/file` → 500 mimo CORSMiddleware (výjimky obcházejí middleware stack) → banner „Network error … Failed to fetch" místo důvodu.

**Poučení:** Všechno, co může selhat na uživatelském vstupu (upload, parsování), balit do `HTTPException(4xx, důvod)` — ta projde exception handlerem UVNITŘ middleware stacku a prohlížeč důvod přečte. Vzor shodný s M2 „provider faily → 502 s důvodem". Fix `53a880b` + `test_decompose_file_not_an_image_400`.

## 2026-08-15 — claude-in-chrome (tato instance): ref-kliky lžou, souřadnice jsou screenshot-space, background tab rozbíjí ResizeObserver

Doplnění M3 zápisu o E2E automatizaci:
1. **Ref-based kliky** (`computer` + `ref`) hlásí úspěch, ale klik do stránky nedorazí (i s čerstvým `find`) — klikat na **souřadnice** odečtené ze screenshotu, nebo JS `.click()` (plnohodnotný DOM event přes React). Kalibrace: screenshot px = CSS px × (šířka_screenshotu / window.innerWidth) — zde ×0,8167; opačným směrem při přepočtu z `getBoundingClientRect`.
2. **Background tab**: reload stránky v tabu, který není aktivní, nechá Konva Stage na 1×1 — ResizeObserver callbacky jedou přes rAF a ten je v background tabu throttlovaný. Nejde o bug aplikace (viditelný tab se změří správně); pro programové exporty nutná ruční korekce (`stage.width/height` + layer transform + pozor na `strokeWidth: 1/fitScale` spočtený z 1×1 → 736px tah přes celé plátno).
3. **html2canvas nevykreslí Konva canvasy** (stacked canvas vrstvy) — kompozici exportovat přímo `stage.toDataURL()`; DOM chrome a plátno skládat zvlášť. Soubory na disk z prohlížeče: mini HTTP receiver (PowerShell HttpListener) + fetch POST base64 — `save_to_disk` u screenshotů nikam viditelně neukládá.
4. `window.confirm` nejde obsloužit přes CDP (nativní dialog) — pro E2E intercept `window.confirm = (msg) => {…; return true}` se záznamem zprávy; existenci dialogu dokládá zachycený text.

## 2026-08-14 — Servírování videa: FileResponse (206), a jak odlišit bug od rozbité media pipeline

**Kontext:** M3 E2E — `<video>` v editoru stál na readyState 0. Route vracela mp4 přes `Response(content=…)` (200 na všechno včetně Range probe). Fix: `FileResponse` (starlette ≥0.36 umí Range → 206), commit `a732042`.

**Poučení:**
1. Binární média vždy přes `FileResponse`/streaming s Range podporou — Chromium media stack bez 206 umí odmítnout hrát, i když `fetch()` téže URL funguje.
2. Diagnostický žebřík media problémů: (a) curl mimo prohlížeč → server OK?; (b) `fetch()` ze stránky → síť z prohlížeče OK?; (c) `blob:` URL s daty v paměti do `video.src` → pokud stall i tady a resource timing nemá pro media URL žádný záznam, je rozbitá media pipeline celé instance prohlížeče (environmentální — restart Chrome), ne aplikace. Přesně tenhle případ nastal: fetch 33 ms, blob stall, prázdný resource timing + opakované >30 s freezy rendereru.

## 2026-08-14 — Pixel-diff atribuce prvku nefunguje pod globálním pohybem kamery

**Kontext:** M3 E2E klip (Wan 2.6): socha se reálně hýbala (vizuální kontrola framů), ale kamera zoomovala mnohem silněji než „slowly" → global_motion 55/255, in/out ratio 0,95 → verdikt „weak".

**Poučení:** In-mask vs out-mask poměr měří *atribuci*, ne pohyb — jakmile kamera hýbe vším, poměr →1 a verdikt „weak" je pravdivé přiznání ne-atribuce (žádoucí chování closed-loop, ne bug). Pro čistou atribuci prvku: generovat verifikační klip s kamerou „Žádná", nebo (M4 kandidát) kompenzovat globální pohyb (optical flow / homografie) před diffem. Modely navíc interpretují adverbia intenzity („slowly") volně — kompilovaný prompt intenzitu kamery negarantuje.

## 2026-08-14 — Konva: „klik do prázdna" neexistuje na scéně s celoplošným pozadím

**Kontext:** M3 motion tool — gesto „klik na prázdný Stage přidá bod trajektorie" na reálném projektu nikdy nenastalo: spodní vrstva pokrývá celé plátno, alfa hit-test pohltí každý klik (výběr vrstvy místo bodu).

**Poučení:** Gesta na canvasu nesmí spoléhat na „klik mimo vrstvy", pokud scéna může mít opaque pozadí. Vzor: v režimu nástroje s aktivním výběrem interpretovat VŠECHNY kliky do plátna jako akci nástroje; změna výběru jde přes panel vrstev; overlay prvky (kotvy) chránit Konva `name` checkem v Stage handleru. Commit `01eb06a`.

## 2026-08-14 — E2E přes claude-in-chrome: zoom akce a syntetické dragy

1. Akce `zoom` (region screenshot) po timeoutu zanechala tab s device-metrics override (viewport 464×220 = rozměr regionu) → všechny další kliky/screenshoty mimo, `resize_window` ani Ctrl+0 to nevrátí. Oprava: nový tab (nový CDP target). Na Konva-heavy stránkách `zoom` nepoužívat.
2. Syntetický CDP drag (mousedown/move/up v jednom ticku) nespustí Konva drag (vrstvy ani kotvy) — reálná myš ano. Drag chování ověřovat Playwrightem (editor-verify.mjs vzor z M2) nebo nechat operátorovi; klikací E2E to má zapsat jako limitaci, ne FAIL.
3. Screenshot souřadnice ↔ CSS px: mapování se mění s viewportem (po reloadu jiné) — pro přesné kliky brát `getBoundingClientRect` přes JS, nebo klikat přes `find`→ref. Ref může po přerenderování ukazovat na odpojený uzel — před klikem vždy čerstvý `find`.

## 2026-08-14 — imageio_ffmpeg.read_frames: meta first-yield, konec streamu bez výjimky

`read_frames` generator: první yield je meta dict (`size` (w,h), `fps`, `duration`, …), pak syrové RGB24 bytes (w×h×3). Kratší stream než odhad `fps×duration` prostě skončí iteraci — žádná výjimka, netřeba try/except. Binárka bundlovaná ve wheelu (`site-packages/imageio_ffmpeg/binaries/`), ffmpeg na PATH není potřeba. (Empiricky ověřeno v grafik/motion/verify.py; testy test_motion_verify.py.)

## 2026-08-14 — API sémantika: /motion je full-replace, /transform je partial-patch

`POST /layers/{id}/motion` nahrazuje celý LayerMotion tím, co přišlo (vynechaná pole = Pydantic defaulty), zatímco `/transform` aplikuje jen poslaná pole. Klient proto u motion vždy posílá kompletní objekt (`persistMotion` v EditorApp). Past pro budoucí přispěvatele: nekopírovat transform vzor na motion (tiše by nuloval nedotčená pole).

## 2026-08-14 — Sdílené live fixtures: testy si musí pinovat baseline

M2 E2E posunula vrstvy ve sdíleném `projects/decompose-test.grafik` (gitignored, společný pro všechny worktrees) → 2 předexistující inpaint-behind testy spadly o den později. Fix: `api` fixture v `test_api_m2.py` po copytree pinuje geometrii/viditelnost známých vrstev (a maže `history.json`). Pravidlo: (a) testy nad živým sdíleným adresářem si baseline vynucují samy, nikdy mu nevěří; (b) živá UI práce patří do `e2e-*` projektů, ne do referenčních fixtures.

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
