# GRAFIK v2 — obrazové studio + lokální obrazová služba (spec G0)

Stav: **návrh ke schválení operátorem** (2026-10-22). Nic neimplementováno.
Zdroje: `ZZZ_TEST/plan-flux-vychozi-vsude.md` (§ 2 architektura, § 4 zadání, § 5 licence), `ZZZ_TEST/plan-ngrobot-lokalni-flux.md` (ověřená fakta o sd-server), měření v `C:/Users/stock/models/flux3-klein/` (prompty, `out/server*.png`), formát stylů POHYB (`POHYB/styles/README.md`, PR #17).
Šablona: STOPA `docs/templates/greenfield-planning-prompt.md` (varianta „přestavba existujícího projektu“).

## 1. Goal

Jeden program na počítači, přes který jde **každé** generování obrázku ze všech projektů (NG-ROBOT, KLAPKA, KARTOGRAF, POHYB, HEGEMON, STOPA `/nano`) i z ruky operátora. Výchozí generátor je lokální FLUX 3 Klein (0 USD); placené generátory jen na výslovné přání a s cenou předem. Jedna GPU s 8 GB unese jeden FLUX, proto jedna fronta a jeden zámek GPU.

```
 NG-ROBOT ─┐                         ┌─ flux-local (sd-server :8390)   výchozí, 0 USD
 KLAPKA ───┤                         │
 KARTOGRAF ┼─▶ GRAFIK Engine :8300 ──┼─ nb-pro (Gemini)                jen backend="nb-pro", cena předem
 POHYB ────┤   /api/v2               │
 HEGEMON ──┤   fronta (SQLite)       └─ fal (krea, flux-pro, …)        jen výslovně, cena předem
 /nano ────┤   zámek GPU, provenience, náklady, knihovna stylů
 Studio UI ┘   (G2: prohlížeč, :5173)
```

## 2. Success criteria (binární, ověřitelné)

### G1 — Engine (napojitelné projekty)
- **sc-1** `python clients/grafik_client.py generate "red apple on a table" --size 1024x1024` na RTX 4060 vrátí PNG 1024×1024 do 120 s od studeného startu (sd-server neběžel); soubor > 100 kB, není jednobarevný (std pixelů > 10).
- **sc-2** Edit s referencí: `generate(prompt, refs=[{"path": …, "role": "subject"}])` vrátí PNG; v provenienci je ref se SHA-256 a rolí; pixel-diff vůči referenci > 0 a < plná změna (obraz vychází z reference — ověřeno okem + číslem v reportu).
- **sc-3** Dva souběžné požadavky (dva procesy klienta spuštěné naráz) oba skončí `done`, ve stejném pořadí, v jakém přišly; v logu Engine nikdy dva běžící joby současně; sd-server proces je po celou dobu jeden (stejné PID).
- **sc-4** Po `idle_timeout` (výchozí 10 min, v testu 5 s) Engine ukončí sd-server **jen podle svého PID** (ověřeno: ukončený PID = uložený PID a jeho create_time; jiný `sd-server.exe` spuštěný ručně běží dál).
- **sc-5** Když chybí volná VRAM (< 6,3 GB volných dle `nvidia-smi`) nebo sd-server nenaběhne, job skončí `failed` s českou čitelnou chybou; **žádný** placený backend se nespustí (test: mock nb-pro nebyl zavolán).
- **sc-6** `backend="nb-pro"` bez `confirm_cost=true` vrátí `402`-like odpověď s odhadem ceny a nic nespustí; s `confirm_cost=true` proběhne a zapíše cenu do ledgeru.
- **sc-7** Každý výstup má vedle sebe `*.json` provenience: backend, model, seed, steps, size, prompt (původní i odeslaný), refs (cesta/URL, sha256, role, licence), layout, `ai_generated: true`, `reviewed_by: null`, cena (`flux-local` = 0), časy (fronta, generování).
- **sc-8** Layout: požadavek s `layout=[{id, bbox:[top,left,bottom,right], desc}]` se přeloží do promptu ve formátu ověřeném 22. 10. (značky `<id>` + JSON seznam), unit test pinuje přesný řetězec.
- **sc-9** `pytest` zelený offline (falešný sd-server), CI není potřeba; `grafik_client.py` má jen stdlib importy (test: AST import scan).

### G2 — Studio UI
- **sc-10** V prohlížeči: napsat prompt → vidět stav fronty → výsledek v galerii, zvětšitelný náhled; vše klikáním, bez terminálu.
- **sc-11** Obraz → obraz: nahrát/přetáhnout obrázek, dát instrukci, dostat variantu; porovnání před/po (posuvník).
- **sc-12** N variant (2–4) jedním kliknutím, výběr „vítěze“, ostatní zůstávají v historii.
- **sc-13** Úprava v rámečku: nakreslit rámeček myší, zadat „odstranit / přidat / přesunout / přebarvit“, výsledek jako nová verze; mimo rámeček pixel-diff ≤ 1,0 průměr (paste-back).
- **sc-14** Historie verzí obrázku (strom: původní → edit → edit), návrat k libovolné verzi.
- **sc-15** „Rozepsat zadání“ (Claude) — krátké české zadání → anglický prompt FLUX; vidět a upravit před odesláním; cena Claude volání zobrazena předem.

### G3 — Předlohy a postupy
- **sc-16** Předloha z Wikimedia Commons hledáním v UI, uložená s licencí a autorem.
- **sc-17** Předloha z Pinterestu se dostane do knihovny předloh (cesta dle rozhodnutí Q4) s URL zdroje.
- **sc-18** Role předlohy (předmět / tvar / scéna) ovlivní prompt (unit test na překlad) a uloží se do provenience.
- **sc-19** Postup „historický objekt“ (předloha → čistý bokorys → oprava v rámečku → natočený pohled 3/4 shora → vykreslit výš a zmenšit) jde proklikat jako průvodce na lodi z `refs/ships` a výsledek se podobá testu z 22. 10.

### G4 — Styly
- **sc-20** Detekce: z obrázku vznikne karta stylu (`STYLE.md` + `style.json`), paleta změřená z pixelů (k-means, 5–8 barev, hex), popis média/techniky/světla/linky/kompozice od Claude.
- **sc-21** Uplatnění: zvolený styl se připojí k promptu **slovy** (nikdy jako obrazová reference); test pinuje, že style-ref se do `ref_images` nedostane.
- **sc-22** Vytvoření: styl z 2–5 vzorů nebo ručně; knihovna sdílená — jiný projekt ji přečte přes `GET /api/v2/styles` i přes klienta.
- **sc-23** Tři výchozí styly v knihovně: „NG infografika 3D“, „akvarel přírodovědný“, „karikatura 3D“, každý ověřen jedním vygenerovaným vzorem.

### G5 — Infografiky
- **sc-24** Ilustrace bez textu + vrstva českých popisků (HTML/SVG) s vodicími čarami k bodům na obrázku; editace popisků v UI bez nového generování.
- **sc-25** Export PNG, SVG, PDF; čeština bez chyb (diakritika vložená jako text, ne pixely modelu); v patičce zdroj a „Ilustrace vytvořena AI“.

### Napojení projektů (P1–P4, mimo GRAFIK — jen kontrakt)
- **sc-26** Každý projekt napojený přes `grafik_client` má výchozí `backend="flux-local"` a nikdy automaticky nepřepne na placený.

## 3. Decisions to Review (otevřené otázky pro operátora)

Viz zpráva operátorovi; po odpovědi se zapíší do `docs/DECISIONS.md`. Moje doporučení je vždy první volba.

- **Q1 Rozhraní studia:** (a) nový React+Vite web na :5173 (stack, který už znáte z ui-web; galerie, rámečky myší, porovnání) / (b) Streamlit (rychlejší, ale rámečky a porovnání jsou kostrbaté) / (c) jen API + Claude jako rozhraní.
- **Q2 Kde žijí výstupy:** (a) centrálně v GRAFIK `library/YYYY-MM/<job>/` + kopie se vrací volajícímu, který si ji uloží k sobě (NG-ROBOT dál ukládá přes `_save_generated`) / (b) jen u volajícího projektu, GRAFIK nic nedrží.
- **Q3 Karta stylu:** (a) stejný formát jako POHYB (`styles/<slug>/STYLE.md` + `style.json`, + `samples/`), knihovna v GRAFIK `styles/` a čtení přes API / (b) vlastní JSON jen pro obrázky.
- **Q4 Předlohy z Pinterestu:** (a) Claude in Chrome otevře pin a uloží obrázek + URL do „schránky předloh“ (GRAFIK `refs/inbox/`); vedle toho přetažení souboru do UI / (b) jen ruční přetažení / (c) záložka-bookmarklet v Chrome, která pošle obrázek do Engine.
- **Q5 Starý GRAFIK a port 8300:** (a) nový Engine převezme :8300, starý API se přesune na :8301 a zůstane spustitelný (`start-grafik-legacy.bat`) do konce G2, pak rozhodnete o archivaci / (b) nový Engine na jiném portu, starý beze změny.

### Rozhodnutí, která navrhuji udělat sám (falsifier = co by ukázalo, že je špatně)

| # | Volba | Alternativa | Falsifier |
|---|---|---|---|
| A1 | Nový kód v nových balících `engine/` (Python, FastAPI) a `clients/grafik_client.py`; starý `grafik/`, `ui/`, `ui-web/` beze změny | přepisovat uvnitř `grafik/` | importy nového kódu sahají do `grafik.*` → hranice nedrží |
| A2 | Asynchronní API: `POST /api/v2/images` → `202 {job_id}`, `GET /api/v2/jobs/{id}`, `GET /api/v2/jobs/{id}/images/{n}`; klient čeká pollováním | synchronní request 40–200 s | volající potřebují streaming průběhu (pak SSE) |
| A3 | Fronta = SQLite tabulka `jobs` + jeden worker thread v procesu Engine; přežije restart (běžící job po restartu → `failed: přerušeno restartem`) | in-memory queue | dva Engine procesy naráz → druhý start musí selhat na zámku portu/souboru; ověří sc-3 |
| A4 | sd-server: `subprocess.Popen` s uloženým `pid` + `create_time` (`run/sd-server.json`), health `GET /v1/models`, generování přes `POST /sdcpp/v1/img_gen` + poll `/sdcpp/v1/jobs/<id>` (t2i i edit stejnou cestou); kill jen `psutil.Process(pid)` po kontrole exe cesty a create_time | `/v1/images/generations` pro t2i | `/sdcpp/v1/img_gen` neumí vše, co potřebujeme (seed, steps, size) → G1 spike T2 to ověří proti živému serveru |
| A5 | Zámek GPU: Engine je jediný uživatel FLUX; před startem sd-serveru kontrola volné VRAM (`nvidia-smi`), plus kooperativní soubor `C:/Users/stock/.gpu-lock` (JSON {owner, pid, since}), který může držet dabing NG-ROBOT; Engine čeká max 10 min, pak `failed` | jen VRAM check | dabing začne až po startu FLUX a spadne na OOM → NG-ROBOT musí zámek brát taky (P2) |
| A6 | Style-ref nikdy jako obraz: `role=style` se převede na slova (karta stylu nebo popis Claude/Haiku) | posílat jako ref_image | nová verze FLUX přenos stylu obrazem zvládne (ověřit A/B, pak změnit) |
| A7 | Velikosti: násobky 16, max 1920×1088 (Q4, 8 GB), `--vae-tiling` nad 1280×1280; „render high then downscale“ jako volba `supersample` | libovolné | OOM pod hranicí → snížit strop |
| A8 | Náklady: `library/costs.jsonl` (append-only), `flux-local` = 0 USD, placené z odhadu backendu; `GET /api/v2/costs` | sdílet ledger NG-ROBOT | projekty potřebují jeden společný ledger → přidat export |
| A9 | Engine nikdy nepřepne backend sám (ani při chybě) | automatický fallback | — (rozhodnutí operátora, ne technická volba) |

## 4. Premortem — jak projekt selže

1. **GPU se pere s dabingem / Whisperem / jiným programem.** FLUX bere 5,9 GB; dabing NG-ROBOT a VoiceStudio taky. → A5 (VRAM check + kooperativní zámek), čitelná chyba místo pádu, P2 bere zámek i v NG-ROBOT.
2. **Zombie sd-server drží VRAM** po pádu Engine. → při startu Engine najde `run/sd-server.json`, ověří PID+create_time+exe, a jen ten ukončí; cizí `sd-server.exe` (ruční testy v `models/flux3-klein`) nikdy.
3. **Studený start + fronta = timeouty u volajících.** NG-ROBOT čeká 3 min a vzdá to. → async API (A2), klient má `timeout` per volání, Engine vrací pozici ve frontě a odhad času.
4. **Uživatel čeká kvalitu Banana Pro a FLUX ji nedá** (drobné postavy, historické reálie, text). → studio umí jedním klikem „pošli totéž do Banana Pro“ s cenou; výstupy FLUX označené `draft`, dokud je člověk neschválí (licence § 2e).
5. **Rozsah utíká** (styly, infografiky, Pinterest, průvodci) a Engine pro projekty se nedokončí. → pořadí G1 → P1/P2 napojení → G2…G5; G1 je malý a má vlastní PR.
6. **Přestavba zničí funkční starý editor dřív, než nový umí totéž.** → A1: starý kód beze změny, archivace až po G2 a se souhlasem.
7. **Tichá kapitulace na placené** (někdo v projektu dopíše fallback). → sc-5 + sc-26, test, že klient nemá žádnou cestu na placený bez `backend=`.
8. **Licence**: výstup FLUX odejde ven bez lidské kontroly. → `ai_generated`, `reviewed_by` v provenienci; publikační kroky projektů to kontrolují (P2).
9. **sd.cpp master-987 změní API** při aktualizaci. → binárka i verze pinnuté v configu, smoke test `engine doctor` po každé změně binárky.

Happy-path předpoklady k hlídání: Engine běží (start přes `start-grafik.bat` / Plánovač), jediný GPU uživatel je FLUX, 32 GB RAM stačí pro Engine + sd-server + projekty.

## 5. API kontrakt G1 (pro projekty)

```http
POST /api/v2/images
{
  "prompt": "…",                       // povinné
  "backend": "flux-local",             // výchozí; "nb-pro" | "fal:<endpoint>" jen výslovně
  "size": "1024x1024",                 // násobky 16, max 1920x1088 u flux-local
  "n": 1, "seed": null, "steps": 16,
  "refs": [{"b64"|"path"|"url": …, "role": "subject|geometry|scene|style", "license": "…", "source": "…"}],  // max 10 obrazových
  "layout": [{"id": "bike_1", "bbox": [430, 40, 920, 360], "desc": "…", "from": "ref_image_0", "tgt_bbox": […]}],
  "style": "akvarel-prirodovedny",      // slug z knihovny (G4), do G4 jen text
  "no_text": true,                      // výchozí; přidá „No text, no letters, no labels.“
  "caller": "ng-robot", "confirm_cost": false
}
→ 202 {"job_id", "position", "eta_s"}  |  402 {"estimate_usd", "backend"} u placeného bez confirm_cost
GET /api/v2/jobs/{id} → {status: queued|running|done|failed, images: [...], provenance, error}
GET /api/v2/jobs/{id}/images/{n} → image/png
GET /api/v2/health → {engine, sd_server: stopped|starting|ready, queue_len, gpu_free_mib}
```

Klient: `from grafik_client import generate` → `generate(prompt, refs=…, size=…, timeout=600) -> list[Path]`; CLI `python grafik_client.py generate …`; čistý stdlib (`urllib`, `json`, `base64`).

## 6. Fáze 1 (G1) — úkoly (2–5 min kroky)

| # | Úkol | Hotovo, když |
|---|---|---|
| T1 | `engine/config.py`: cesty k `sd-server.exe`, modelu `FLUX-3-Image-Klein-AD-Q4_K.gguf`, `--llm text_encoders/Qwen3-VL-4B-Instruct-AD-Q4_K.gguf`, `--vae vae/ae.safetensors`, port 8390, idle 600 s, sampler euler/steps 16/cfg 1.0 (= `run.sh`) | `python -c "import engine.config"` |
| T2 | Spike: spustit sd-server ručně dle `run.sh` argumentů, ověřit `/v1/models`, `/sdcpp/v1/img_gen` (seed, steps, width/height, ref_images), poll; zapsat payload do `docs/capabilities/sd-server-master-987.md` | t2i 512² + edit s 1 ref přes curl, JSON tvary zapsané |
| T3 | `engine/sdserver.py`: start/health/stop podle PID+create_time, VRAM check, kooperativní `.gpu-lock` | unit testy s falešným procesem; kill cizího PID odmítnut |
| T4 | `engine/prompt.py`: layout → `<id>` + JSON, no_text suffix, style-ref → text, ref role → pořadí `ref_image_n` | pinované testy (sc-8, sc-21) |
| T5 | `engine/queue.py`: SQLite jobs + worker thread, FIFO, restart = running→failed | test souběhu (sc-3) s falešným backendem |
| T6 | `engine/backends/flux_local.py` + `backends/nb_pro.py` (opt-in, odhad 0,134 USD) | sc-5, sc-6 offline testy |
| T7 | `engine/provenance.py` + `library/` výstupy + `costs.jsonl` | sc-7 test |
| T8 | `engine/app.py` FastAPI `/api/v2/*` na :8300 | `GET /api/v2/health` |
| T9 | `clients/grafik_client.py` (stdlib) + CLI | sc-9 AST test |
| T10 | Živé ověření na RTX 4060: sc-1, sc-2, sc-3, sc-4; report `docs/spikes/2026-10-22-g1-engine.md` s časy a VRAM | výstupy + čísla v reportu, PR |

Exekuční tier: T1, T7, T9 mechanické (Sonnet stačí); T3, T5 souběh a procesy (Opus); T2, T10 živé měření (hlavní session).

## 7. Milníky dalších fází (rozpis až s reálným kódem)

- **G2 Studio UI** (sc-10…15): nový web dle Q1, galerie, fronta, i2i, varianty, rámečkový edit s paste-back, historie verzí, „Rozepsat zadání“.
- **G3 Předlohy** (sc-16…19): Commons hledání, Pinterest dle Q4, role, průvodce „historický objekt“.
- **G4 Styly** (sc-20…23): karty dle Q3, detekce (Claude + k-means paleta), knihovna přes API, 3 výchozí styly.
- **G5 Infografiky** (sc-24…25): vrstva popisků HTML/SVG, export PNG/SVG/PDF, patička s AI označením.
- **P1–P4** v ostatních projektech (vlastní sessions/PR, mimo tento repozitář).

## 8. Out of scope (výslovně NE)

- Video osa (Kling, Wan, Seedance, motion, klipy) — nepřenáší se.
- Qwen-Image-Layered dekompozice, SAM segmentace, vrstvy jako hlavní model práce (starý editor je má; nový GRAFIK pracuje s celými obrázky a rámečky).
- Vykreslování textu generátorem — text vždy vrstva HTML/SVG.
- Upscale, hloubka, 3D, lipsync.
- Druhá GPU / vzdálený stroj, více souběžných FLUX instancí.
- Automatický fallback na placené generátory.
- Mazání starého kódu (až po G2 a se souhlasem).
