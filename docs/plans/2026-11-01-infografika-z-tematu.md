# Infografika z tématu: analýza Pantheonu a zadání

Operátor 1. 11. 2026: „Zkušenost z vytvoření této infografiky analyzuj, zda odpovídá možnostem rozhraní projektu a jak ho případné vylěpšit. Jde mi o to, aby projekt si byl schopen dohledat potřebná data i obrazové podklady, tak aby projekt fungoval co nejvíce automaticky - následně vytvoř zadání pro samostatnou konverzaci pro implementaci vylepšení.“

Navazuje na operátorův algoritmus z 29. 10. (STOPA `outputs/plans/2026-10-29-algoritmus-tvorby-obrazku.md`), který už tehdy žádal „možnost dohledání informací a obrazových podkladů na internetu“ a v kroku 1 „návrhy s jednoduchým popisem, které editor schválí nebo upraví“. Postup Pantheonu: [spike](../spikes/2026-11-01-pantheon.md).

## 1. Závěr

**Velká infografika nešla přes Studio ani jedním krokem.** Fakta jsem hledal ručně v chatu, model a skladbu jsem napsal jednorázovými skripty: 1 758 řádků (`lod_pantheon.py` 1 248, `pantheon_plakat.py` 306, `pantheon_infografika.py` 204). Editorem prošla jen první verze 16:9, s podkladem ze skriptu.

**Dohledat data GRAFIK neumí, obrázky jen na kliknutí.** V kódu `engine/`, `studio/src` a `shared/` není jediné volání Wikipedie, Wikidaty ani hledání na webu. Commons se prohledává po jednom dotazu z okna předloh a průvodce historickým objektem se zastaví u každého výběru.

**Tři opravy směru vznikly přeskočením kroku 1 algoritmu.** Začal jsem pracovat bez návrhů ke schválení, rozhraní ten krok nemá, takže mě k němu nic nevedlo. Stálo to tři kola práce a 0,15 USD za odmítnutou malbu.

Základy v Engine jsou dobré a automatika na nich může stát: fronta s obnovou po restartu, zámek těžké práce, cena v tlačítku, jeden renderer PNG a PDF, VectorCraft, provenience. Chybí kroky před nimi a řetězec, který je spojí.

## 2. Krok po kroku

| Krok | Co umí rozhraní | Co se stalo u Pantheonu | Mezera |
|---|---|---|---|
| Zadání a vzor | Pole Zadání; infografika chce hotový obrázek a nadpis | Vzor v chatu, tři opravy směru | Návrhy skladby ke schválení |
| Fakta se zdroji | Nic. `sources` je volný text, kontrola jen hlídá, že je vyplněný | Ručně Moore 2002, Wikipedia, Newton Excel Bach; 8 faktických oprav vzoru | Rešerše, rozpory mezi zdroji |
| Obrazové podklady | Commons na kliknutí s licencí a autorem; Pinterest jen příjem URL | Žádné, model vznikl z rozměrů | Hledání podle tématu a role obrázku; autoři v patičce (dnes se nikam netisknou) |
| 3D model | fal 0,30 až 0,375 USD, nebo nahraný GLB | Ručně psaný skript, kola s `lod_check`, kontrola dílů bez kontaktu nesplněná | Cesta od rozměrů k modelu |
| Render | Bílý render z kamery prohlížeče | Barevný render, 6 pohledů, `--vrstvy` jen ve skriptu | Barevný render a vrstvy jako úloha Engine |
| Skladba stránky | 3 rozměry, 1 obraz a 1 výřez | 1600 × 2400, 14 obrazů, SVG ze skriptu | Panely a volný formát v dokumentu |
| Popisky | Ručně v editoru; „Navrhnout popisky“ přes Claude naostro neklikáno | Promítnutí bodů modelu ve skriptu | Kotvy na bodech modelu |
| Kontroly | Délka popisků, vodítka a termdb v editoru; poradní `POST /checks` | Plakát editorem neprošel, takže ani kontrolami | Kontroly i mimo editor |
| Výstup | Export a VectorCraft z editoru; Knihovna jen přes API přidané 1. 11. | Skript, pak upload, který na 4 minuty shodil Studio (GRAFIK#105) | Tlačítko, klient, `blender_render` ze Studia |

## 3. Co už existuje a nepíše se znovu

- **KLAPKA `klapka/research.py`:** Sonnet 5.5 s nástrojem `web_search_20260209`, nejvýš 8 hledání, česká odpověď se seznamem zdrojů, cena do ledgeru po každé odpovědi. Naměřeno 0,45 USD (STOPA plán § 2). Vrací prózu, GRAFIK potřebuje navíc jednotlivá fakta.
- **NG-ROBOT `claude_processor/phases/phase_4_fact_checker.py`:** audit, hledání na webu, oprava; řádky verdiktu `URL | úryvek`. Svázané s pipeline článků a NG-ROBOT se nemění (podmínka operátora 29. 10.), takže jen vzor formátu.
- **NG-ROBOT `ng_vector_labels/objects.py` (NG-ROBOT#984):** objekty do vrstev VectorCraftu. Přečíst před stavbou vrstev v Engine.
- **`ngm_shared.image_checks`:** kontrola proti zadání a kontrola logiky, naměřeno 0,0072 a 0,0426 USD.
- **Test T1 z 29. 10.:** návrhy k článku od Claude, 0,16 USD, fungují.
- **`engine/jobs.py`, `engine/workflows.py`:** fronta s `handlers[kind]`, stav průvodce v JSON. Po restartu fronta pokračuje, průvodce sám ne a běžící úloha skončí jako selhaná.
- **Termdb:** operátor 23. 10. „bez placeného vyhledávání na webu“. Platí pro kontrolu termínů a ta se nemění. Rešerše je samostatný krok s cenou v tlačítku.

## 4. Návrh

```
Téma nebo vzor → Podklady → Návrhy skladby → Model a render → Stránka a popisky → Kontroly → Výstup
                  (samo)     (operátor vybere)                                               (operátor zkontroluje texty)
```

Člověk zastaví řetězec dvakrát: vybere návrh a zkontroluje texty. Cena se schválí jednou na celý řetězec, krok nad rozpočet se zastaví.

- **Nejdřív zdarma.** Wikidata, Wikipedia a Commons bez klíče. Placené hledání na webu přijde až jako tlačítko s cenou, když volné zdroje nestačí.
- **Každý fakt nese zdroj a stav:** shoda, rozpor, jediný zdroj, nedohledáno. Rozpor se ukáže a nerozhoduje se potichu (okulus 8,2 až 9,1 m). Chybějící hodnota zůstane prázdná, odhad se označí jako `odhad` stejně jako v `DIM` u Pantheonu.
- **Obrázky mají roli:** půdorys, řez, průčelí, interiér, detail, materiál. Nejistá role zůstane `nezarazeno`. Licence neblokuje použití jako předlohy (`engine/reflib.py`), ale obrázek přímo v infografice má autora v patičce.
- **Text jde na stránku z dossieru s odkazem na zdroj.** Obrazový model dál text nekreslí a `reviewed_by` dál vyplňuje člověk.

### Odhad ceny jednoho běhu

Složeno z naměřených kroků, skutečnou cenu změří první běh.

| Krok | USD |
|---|---|
| Volné zdroje | 0 |
| Placená rešerše, jen na tlačítko | 0,45 |
| Návrhy z dossieru | 0,16 |
| Kontroly | 0,05 |
| Model: skript nebo díly (tokeny neměřené), nebo Hunyuan 3.1 Pro | 0 až 0,375 |
| **Celkem** | **0,21 až 1,04** |

### Co automatika neslíbí

- **Model složité stavby na úrovni Pantheonu.** Ten skript vznikal ručně a placené modely si u staveb vymýšlejí části (měření 27. 10.). Proto fáze 3 začíná měřením.
- **Úsudek o skladbě.** Zásady infografik ho nechávají na člověku, číselné kontroly jen upozorní.
- **Správnost faktů.** Rešerše zkrátí hledání, před zveřejněním texty dál čte člověk.

## 5. Zadání pro samostatnou session

**Cíl:** z tématu nebo vloženého vzoru dojde GRAFIK sám k dossieru faktů a obrazových podkladů, k návrhům skladby a dál k hotové infografice, se dvěma zastávkami pro operátora. Pracuj po fázích, každá je vlastní PR. Přečti `docs/STAV.md`, `docs/infografiky-zasady.md`, `.claude/rules/infografiky.md`, `docs/spikes/2026-11-01-pantheon.md`, DECISIONS 2026-11-01 a 2026-10-27 a tento plán.

### Fáze 0: pojistky

- Error boundary kolem obsahu záložek Studia (`studio/src/App.tsx`): chyba v jednom panelu ukáže českou hlášku, ostatní záložky běží dál. 1. 11. jeden krátký záznam o původu shodil celou aplikaci.
- `HistoryPanel` (`studio/src/panels.tsx`) přečte krátký záznam bez pádu. 10 záznamů druhu `localize` a `upload` je krátkých, dnes se k nim výběrem nedá dostat.
- `blender_render` z uploadu ve Studiu (`studio/src/api.ts`), tlačítko „Do Knihovny“ u exportu infografiky, `grafik_client.library_upload()`.
- **Hotovo:** vadný záznam v dočasných datech ukáže v opravdovém Studiu hlášku místo bílé stránky; export z editoru jde jedním klikem do Knihovny.

### Fáze 1: podklady (jádro zadání)

- `shared/ngm_shared/research.py`: volné zdroje bez klíče (Wikidata, Wikipedia cs a en, Commons z kategorie entity a z hledání) a placená část převzatá z KLAPKA `klapka/research.py`, doplněná o jednotlivá fakta. KLAPKU neměň, na její přechod založ issue v KLAPCE.
- Dossier `library/research/<id>/dossier.json`: `facts` (`tvrzeni`, `hodnota`, `jednotka`, `zdroje` s URL, názvem, citací a datem, `stav`), `images` (role, licence, autor, URL, rozměry), `otazky_bez_odpovedi`. Dossier se nepřepisuje, nový běh je nová verze.
- `engine/research.py`, `POST /api/v2/research` (úloha `research` ve frontě), `GET /api/v2/research/<id>`, `GET /api/v2/research/estimate`. Placená část 402 bez `confirm_cost`, cena do ledgeru. Klient `grafik_client.research()` a CLI.
- Obrazové podklady: z dossieru sám hledá v Commons, třídí do rolí a importuje přes `engine/reflib.py` s licencí a autorem, nejvýš N kandidátů na roli. Přehled přes stránku `variants_page`. Pinterest zůstává přes operátorův Chrome.
- Autoři a licence obrázků použitých přímo jdou do patičky infografiky.
- Studio: nový průvodce v záložce Průvodce, ne nová záložka. Krok Podklady ukáže rozpory nahoře, fakta se zdroji a obrázky po rolích se zvětšením. **Náčrt operátorovi před stavbou.**
- **Hotovo, 0 USD:**
  - Dossier „Pantheon, Řím“ z volných zdrojů změřený proti tabulce „Co vzor měl špatně“ ve spike Pantheonu (8 faktických řádků): kolik jich doloží URL, cíl aspoň 5. Okulus musí vyjít jako rozpor nebo rozpětí. Co nenajde, napiš.
  - Dossier „Koloseum“ pro kontrolu, že kód nesedí jen na Pantheon: počet faktů, zdrojů a obrázků po rolích. Člověk nebo session projde 10 náhodných faktů proti zdroji a počet chyb zapíše do spike.
  - V opravdovém Studiu se krok otevře a konzole je bez chyb.
  - Placený běh jen se souhlasem operátora, odhad 0,45 USD.

### Fáze 2: návrhy a řetězec

- `engine/workflows.py`: průvodce `infografika`, téma nebo vzor → podklady → návrhy skladby → výběr.
- Návrhy z dossieru od Claude (odhad 0,16 USD): 3 skladby, každá s jednou větou a hrubým náčrtem panelů (SVG, 0 USD). Volitelně dávka vzhledu na lokálním FLUX. U vloženého vzoru rozbor, co držet a co změnit (DECISIONS 2026-11-01: žánr a bohatost vzoru, vlastní skladba, realistické 3D).
- Jedna cena předem na celý řetězec, krok nad rozpočet se zastaví a zeptá.
- Po restartu Engine řetězec naváže. Dnes běžící úloha skončí jako selhaná a průvodce stojí.
- Kontrola logiky `ngm_shared.image_checks` poradně po návrhu a po výstupu, nic neblokuje (algoritmus, test T7).
- **Hotovo:** z tématu „Koloseum“ řetězec doběhne bez dalšího kliknutí k výběru návrhu, přežije restart Engine uprostřed běhu, cena v ledgeru sedí s odhadem do ±50 %. Placené volání jen se souhlasem operátora.

### Fáze 3: model, render, stránka (každá část vlastní PR, UI s náčrtem)

- **3a Měření cest k modelu na novém objektu**, cenu odsouhlasí operátor předem. (A) Hunyuan 3.1 Pro s nalezenými předlohami, 0,375 USD. (B) Claude napíše `lod_*.py` z dossieru podle `docs/3d-lod-postup.md`, nejvýš 3 kola. (C) díly vytažené z `lod_pantheon.py` (rotunda, kupole s kazetami, portik, sloupy, zeď), Claude dodá jen JSON parametrů. Změř `lod_check`, cenu, čas a vady ve 4 pohledech. Moje doporučení je C pro stavby, protože nespouští vygenerovaný kód; rozhodne operátor podle měření.
- **3b Barevný render jako úloha Engine:** `engine/blender/` z pojmenovaných pohledů a po objektech (`is_holdout`) pro model s pojmenovanými díly, `body.json` s kotvami. Zobecni postup z `lod_pantheon.py`, ten skript nepřepisuj. Pod zámkem těžké práce.
- **3c Dokument s panely:** `panels[]` (obraz, rámec, popisky), volný formát včetně 1600 × 2400, kotvy popisků na bodech z `body.json`, vrstvy po objektech pro VectorCraft a `vectorcraft/export` i pro ně, kontroly pro všechny panely. Staré dokumenty beze změny, `schema_version`.
- **Hotovo:** Pantheon vyjde z dokumentu v editoru, odchylka proti `library/plakaty/pantheon/pantheon.png` změřená a zapsaná, ve VectorCraftu jsou vrstvy Grafika a Texty. Hotový plakát se nepřepisuje.

### Krok 3d: přeformátování hotové infografiky (po 3c, vlastní PR, UI s náčrtem)

Operátor 1. 11.: „Máme tam možnos hotovou infografiku automaticky předělat na jiný formát?“ a na návrh tohoto kroku „Ano, přidat“. Dnes editor jen přepne plátno a obraz ořízne, plakát má formát napevno ve skriptu.

- Editor: tlačítko „Předělat na formát“ s volbou cíle (16:9, 4:5, 1:1, 2:3, vlastní rozměr). Cena v tlačítku, bez placeného kroku 0 USD. Stávající přepínač formátu plátna se nemění.
- Engine: `POST /api/v2/infographics/<id>/reformat` se `size`, úloha ve frontě. Vznikne nový dokument. Původní dokument, jeho exporty ani kopie ve VectorCraftu se nemění.
- Panely se znovu rozmístí podle pořadí důležitosti uloženého v dokumentu. Žádný se neořízne ani potichu nezahodí: co se do formátu nevejde, ukáže hlášení a rozhodne operátor.
- Popisky se znovu dosadí z bodů v `body.json`. Pohled, který se do nového rámu nehodí, se znovu vyrenderuje v Blenderu ze stejného modelu pod zámkem těžké práce (0 USD). Panel bez modelu se zmenší celý, bez ořezu.
- Po přeskládání běží stejné kontroly jako u dokumentu a výsledek má vrstvy Grafika a Texty pro VectorCraft.
- **Hotovo, 0 USD:** Pantheon z 2:3 na 16:9 a 4:5. Stejný počet panelů a textů jako originál, žádný objekt oříznutý okrajem rámu, medián vodítek do 6 %, 0 křížení, originál bajtově beze změny. Ověřeno v opravdovém Studiu a ve VectorCraftu bez okna. Vzhled posoudí operátor, číselné kontroly jen upozorní.

### Pravidla pro všechny fáze

- Placené operace jen s výslovným souhlasem operátora a cenou předem. Testy nic neplatí (`GRAFIK_LIVE_TESTS`).
- NG-ROBOT a KLAPKA se v této session nemění. Změna `ngm_shared` zůstane zpětně kompatibilní, testy `shared/tests`.
- Co čte Studio, ověř otevřením opravdového Studia (LEARNINGS 2026-11-01). Test API nestačí.
- Česky, tlačítko je odlišené od informace, náhledy jdou zvětšit, před změnou UI náčrt.
- Ruční úpravy a hotové výstupy se nepřepisují.
- Testy `rtk proxy python -m pytest tests/ shared/tests -q`. Restart Engine jen podle PID z portu při prázdné frontě a mimo strom session (`Invoke-CimMethod Win32_Process Create`, příkaz z `start-grafik.bat`).
- Vlastní PR bez konfliktu slouč a ukliď. Na konci přepiš `docs/STAV.md`, rozhodnutí operátora zapiš do `docs/DECISIONS.md`.
