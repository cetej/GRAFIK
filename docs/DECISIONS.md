# Rozhodnutí operátora — GRAFIK

Nejnovější nahoře. Každé rozhodnutí: datum, co, proč, odkud.

## 2026-11-01 — Cizí vzor: nejdřív kopie přes 3D modely, česky, se správnými detaily

Operátor poslal vzory plakátů Nikoly Tesly a axolotla. Vlastní skladby odmítl („To se raději snaž udělat nejprve kopie a pak navrhni jejich vylepšení“).

- Kopie drží skladbu vzoru a jde přes 3D modely („já bych rád zase šel přes 3D modely“). Axolotl má být „detailní model, 3D realismus“.
- Texty jsou česky a věcné chyby vzoru se opravují už v kopii („Některé ty detaily u Tesly nejsou správně. A samozřejmě to má být česky“).
- Vylepšení se navrhují, staví se až po výběru.
- Placené modely: schváleno 0,75 USD (2 × Hunyuan 3.1 Pro, „udělej je, co nejlepší“), utraceno 0,75 USD. Další placený krok chce nový odhad a souhlas.
- Stejný obsah dvakrát na plakát nepatří (fotka věže vedle modelu věže) a ilustrace musí vysvětlit, jak věc funguje („Ilustraci vodní elektrárny nechápu“): vodní elektrárna je řez s popisky a šipkami toku.

Postup a měření: [spike](spikes/2026-11-01-plakaty-osoba-zvire.md).

## 2026-11-01 — Model stavby: z dílů s GPT-6.1 Terra

Na otázku „Mají se stavby dělat z dílů s modelem Terra?“ po tabulce měření operátor: „Ano, dokonči to“. Cesta C z plánu: model dodá jen JSON dílů, žádný generovaný kód se nespouští. Sonnet s prameny se ani jednou nepostavil (0,40 USD), Terra dala 49 dílů za 0,15 USD, Hunyuan z jedné fotky plochou desku. Měření: [spike](spikes/2026-11-01-model-cesty.md). Souhlas s dalším placeným během to není.

K rozpočtu měření operátor: „Klidně navyš rozpočet na dokončení“. Celkem 1,5248 USD.

Sochy, plachty a lidi v obraze chce operátor výslovně („malí lidičkové tomu také dodají hned lepší náboj“), takže model je smí obsahovat i bez doložené polohy. V popisu je napsané, co je oživení a co pramen; do rozměrů ani kontroly kontaktu se to nepočítá.
## 2026-11-01 — Jeden slovník výslovnosti v `ngm_shared`

Operátor slyšel v POHYB „mitokondrie“ a zeptal se, jestli jde výslovnost ošetřit obecně. Oprava slova má platit všude, proto jeden soubor místo dvou slovníků v NG-ROBOT a jednoho v POHYB.

- **Soubor je v balíčku a v gitu** (`shared/ngm_shared/vyslovnost_cz.json`), ne ve složce KNIHOVNA: ta je mimo git a bez zálohy a CI projektů by slovník neměla. Cena: „Opravit výslovnost“ zapisuje do hlavního checkoutu GRAFIK a zůstane tam necommitnutá změna, dokud ji někdo nepřevezme PR. Platí hned všude, ale do historie se dostane až s tím PR (CLAUDE.md).
- **Kmen je volba položky, ne nové výchozí chování.** Stávající položky platí dál jako přesný tvar, takže se jejich výstup nezměnil. Plošný převod na kmeny by změnil čtení jmen a zkratek, a to bez poslechu ověřit nejde.
- **Koncovky jsou seznam, ne libovolný konec slova.** Volný konec by z kmene dělal shodu uvnitř jiných slov. Přídavné jméno má proto vlastní položku (`mitochondriáln`).
- **Zpětný přepis jen hlásí.** `kandidati` slovník nemění: Whisper píše i podle pravopisu, takže odlišný přepis je nález, stejný důkaz není.
- **Bez plošného pravidla na „ch“.** Měření POHYB 2026-11-01: ze 19 slov s „ch“ Whisper napsal K jen u mitochondrie, mitochondrií a orchestru. Orchestr ve slovníku není, opravu nikdo neověřil poslechem.

## 2026-11-01 — Infografika z tématu: náčrt schválen, modely i od OpenAI

K náčrtu kroků Podklady a Návrhy skladby, tlačítka Do Knihovny a volby renderu z Blenderu operátor: „Schvaluji, stavět“. Souhlas s placením to není.

Během stavby operátor: „Nezapomínej, že máme možnost využít i jiné modely ChatGPT, pokud jsou na něco lepší a levnější.“ U placených kroků se tedy srovnávají i modely OpenAI. Krok návrhů jde přepnout (`ngm_shared.gpt`), [ceny a postup](spikes/2026-11-01-retezec.md).

K živému běhu Kolosea a srovnání pěti modelů za odhadem 0,43 USD operátor: „Ano, spustit“. Stálo to 0,1529 USD.

Volby níže jsou návrh session, operátor je ruší tady:

- **Výchozí model návrhů zůstává Claude Sonnet 5.5** po srovnání pěti modelů na Koloseu ([stránka](spikes/img/2026-11-01-navrhy-srovnani.html)). Dal nejbohatší návrhy a nejrychleji. GPT-6.1 Terra je za polovinu, ale rozdíl je 1,2 centu na běh. Přepnutí je jedna konstanta `proposals.DEFAULT_MODEL`.
- **Výběr návrhu jde změnit.** Kontrola logiky proběhne znovu v rámci schválené ceny, nad ní se řetězec zeptá.
- **Němčina a italština v dossieru.** Bez nich se rozpor u okulu neukáže, čeština a angličtina se v mezích zaokrouhlení shodnou.
- **Přerušený placený krok se po restartu sám nespustí.** Odhad se počítá do útraty a řetězec se zeptá.
- **Kontrola logiky je součást ceny řetězce a běží po výběru návrhu,** nad náčrtem a slovním popisem. Nic neblokuje.
- **Ke vzoru je potřeba napsat i téma.** Rozpoznání tématu z obrázku by byl další placený krok.

## 2026-11-01 — Cíl: projekt si sám dohledá data a obrazové podklady

Operátor 1. 11.: „aby projekt si byl schopen dohledat potřebná data i obrazové podklady, tak aby projekt fungoval co nejvíce automaticky“. Analýza a zadání pro samostatnou session: [plán](plans/2026-11-01-infografika-z-tematu.md).

K velké infografice Pantheonu operátor: „Celkově to vypadá moc pěkně - výborná práce“. Beru to jako přijetí vzhledu, fotorealistický průchod se bez pokynu nespouští.

Operátor k návrhu automaticky předělat hotovou infografiku na jiný formát: „Ano, přidat“. V plánu je to krok 3d, staví se až po dokumentu s panely (3c).

Operátor k „Další variantě“ u plakátu: „udělalo jen jiný obrázek základní budovy - To je pochopitelné u jednotlivého obrázku ne u infografiky.“ Varianta infografiky má být nová skladba, v plánu krok 3e. Do té doby hotový obrázek bez generátoru tlačítka pro generování nemá.

Volby níže jsou návrh session, operátor je ruší tady:

- **Přeformátování dělá nový dokument a nic neořezává.** Co se do formátu nevejde, ukáže hlášení a rozhodne operátor.
- **Nejdřív volné zdroje, placené hledání až na tlačítko s cenou.** Termdb zůstává bez placeného hledání (rozhodnutí 23. 10.), rešerše je samostatný krok.
- **Dvě zastávky pro člověka:** výběr návrhu a kontrola textů. Cena se schvaluje jednou na celý řetězec.
- **Rešerše patří do `ngm_shared`, převzatá z KLAPKY.** NG-ROBOT ani KLAPKA se v té session nemění.
- **Cesta k 3D modelu se rozhodne až po měření.** Doporučení: díly z `lod_pantheon.py` a JSON parametrů, protože nespouští vygenerovaný kód.

## 2026-11-01 — „Podobnou a vylepšenou“ infografiku: žánr vzoru, vlastní skladba, realistické 3D

Zadání operátora 1. 11.: složit v projektu infografiku podle vloženého vzoru Pantheonu a zkusit ji vylepšit. Operátor opravil směr třikrát:

- Na jediný řez 16:9: „pod instrukcí udělat podobnou a spíše vylepšenou infografiku by se měl skrývat jiný výsledek.“
- Na kvaš přes Nano Banana Pro: „Mělo by to být realistické 3D, ne ilustrace do staré dětské knížky.“
- Na plán s panely jedna ku jedné podle vzoru: „Chtěl jsem vylepšenou infografiku, ne kopii.“

Z toho plyne: u zadání „podobnou, vylepšenou“ drží výsledek žánr a bohatost vzoru a má vlastní skladbu. Výchozí vzhled staveb a objektů je realistické 3D. Zásady z 23. 10. o nekopírování platí dál.

Volby níže jsou návrh session, operátor je ruší tady:

- **Skladba:** velký řez s koulí, pod ním jen pohledy s novou informací: rozložení na díly, pohled k okulu, vrstvy betonu, proč stavba stojí, čísla, půdorys. Bez rámečků a panelů, jedna písmová rodina ve dvou řezech.
- **Render z Blenderu smí být konečný podklad**, u stavby se přesnými počty a nápisem. Patička říká pravdu o původu: upload s `blender_render: true` dá „Model a render: Blender, bez AI“ a `ai_generated: false`. Obrázek z počítače bez té volby zůstává označený jako AI, protože o něm nevíme, jak vznikl.
- **Hotový výsledek patří i do Knihovny** (`POST /api/v2/library/upload`). Operátor se 1. 11. ptal, proč tam první infografika není: Knihovna ukazuje jen úlohy druhu `image`, upload pro infografiku je `upload`.
- **Velká infografika zatím mimo editor Studia:** skládá ji skript a Chromium. Rozvržení do editoru přijde, až operátor vzhled schválí, a s náčrtem.
- **Popisky a objekty ve vrstvách pro VectorCraft** (operátor se ptal 1. 11.): Grafika s každým objektem zvlášť, Texty s každým popiskem zvlášť. Kopie pro okno se nepřepisuje.

## 2026-10-31 — Styly v šesti kategoriích, katalog v gitu

Zadání operátora 31. 10.: rozřídit styly do kategorií Fotografie, Historické (od pravěku po klasicismus), Ilustrace, 3D, Komiks, Film, navrhnout doplnění a vytvořit je s ukázkami. Volby níže jsou návrh session, operátor je ruší tady.

- **Kategorie je pole karty** (`kategorie`, `poradi` v `styles/<slug>.yaml`, seznam `knihovna.STYLE_CATEGORIES`). Do promptu nejde. Slug zůstává identitou, žádný styl se nepřejmenoval, KLAPKA čte karty beze změny. Karta bez kategorie je ve Studiu ve skupině „Bez kategorie“.
- **Jeden styl, jedna kategorie.** Rozhoduje vzhled: Film je záběr z kamery nebo ručně kreslený film, 3D je počítačový render (i „3D animovaný film“). „Olejomalba v pohybu“ zůstala ve Filmu, klidná malba má vlastní styl „Barokní olejomalba“ v Historických.
- **Historické jdou po časové ose od pravěku po pop art.** První verze končila klasicismem podle doslovného zadání. Operátor ještě 31. 10. rozhodl: přidat romantismus, impresionismus a modernu a znovu projít, co chybí. Moderna končí pop artem, protože dál už malba nemá kam dát předmět obrázku. Mimoevropské styly: čínská tuš, perská miniatura, ukijo-e, mayská a aztécká malba.
- **Karta popisuje vzhled, obsah obrázku určuje zadání** (operátor 1. 11.: obraz se necenzuruje, svoboda projevu). Týká se hlavně propagandistických plakátů (operátor 31. 10.: sovětské, nacistické, čínské; session přidala americké a československé): karty nezakazují symboly, vlajky ani skutečné osoby. Nápisy a hesla zakázané zůstávají u všech stylů, protože je model neumí a doplňují se zvlášť. Ukázky mají neutrální motivy.
- **Doplnění nemá čekat na doslovný pokyn.** Zadání „navrhni doplnění“ znamená hledat i mimo výčet operátora; co jsem záměrně nepřidal a proč, je v [přehledu](spikes/2026-10-31-katalog-stylu.md).
- **Katalog je v gitu** (`styles/katalog.yaml`, `scripts/styles_katalog.py`), protože KNIHOVNA nemá zálohu. Skript existující karty nepřepisuje: doplní jim jen `kategorie`, `poradi` a chybějící `note`. Text promptu 15 stávajících stylů se nezměnil.
- **Ukázky jsou tři a srovnatelné:** společný motiv (farmář s koněm), portrét a motiv typický pro styl; první je náhled v knihovně. Motiv s koněm jde použít ve všech epochách. Styly, kde by nedával smysl (makro, mikroskop, muzejní předmět, letecký snímek, výkres, rentgen), mají jen vlastní motivy. Generuje lokální FLUX, 1024×768, 0 USD, po jedné úloze, aby se mezi ně vešly úlohy ostatních projektů.
- **Prompt jmenuje jen autory mrtvé déle než 70 let** (Monet, Mucha, Klimt, Munch, Mondrian). Živé a mladší autory, studia a chráněné značky nejmenuje a styl popisuje slovy (kubismus, surrealismus, pop art, anime). Poznámka na kartě, která do promptu nejde, autora zmínit smí (Josef Lada).
- „Karikatura 3D REAL“ má 5 vlastních vzorů od operátora, nové se k ní nepřidávají. „Dokumentární rekonstrukce“ a „… (éra a přístroj)“ mají stejný text; obě zůstávají kvůli projektům KLAPKY, poznámka to říká.

## 2026-10-31 — Převzetí ruční úpravy z VectorCraftu do exportů

Zadání od session `grafik-vectorcraft`, vzor NG-ROBOT `ngvector/export`. Operátor volby níže zatím neviděl, ruší je tady. Měření: [spike](spikes/2026-10-31-rucni-uprava-export.md).

- **Export dělá VectorCraft bez okna** (PNG, PDF, SVG), takže výsledek vypadá jako okno, ne jako Chromium. Pod zámkem těžké práce s vlastním vlastníkem `grafik-infografiky`: se stejným vlastníkem jako fronta Engine (`grafik-engine`) by zámek pokládal běžící FLUX za svůj a uvolnil by ho.
- **Požadavek čeká na zámek nejvýš 120 s**, pak `503` s tím, kdo stroj drží. Fronta úloh na to není: převzetí trvá okolo 4 s a operátor čeká na výsledek.
- **SVG je v křivkách**, jako v NG-ROBOT: kopie pro okno má rodiny `Bahnschrift SemiCondensed`, které jinde nemusí sedět. Upravitelný zůstává zdroj ve `vectorcraft/`.
- **Nic se nepřepisuje.** Zdroj se jen otevře, každé převzetí má vlastní `<čas>-rucni-<hex>.png|pdf|svg` a `.json`. Opakované převzetí přidá další trojici, Studio u úpravy napíše, že už převzatá je (podle sha256).
- **Označení AI**: převzetí odmítne soubor, kde věta `ai_note` není viditelně na prvním plátně. Provenience má texty přečtené ze souboru, popisky z editoru by úpravu nepopisovaly.
- **`reviewed_by` je `null`**, kontrola z editoru je v `document_reviewed_by`: kdo schválil dokument, neviděl ruční úpravu.
- Do polí editoru se úprava dál nevrací.

## 2026-10-31 — Infografika ve VectorCraftu: otevření z Studia, vrstvy, ruční úprava se nepřepisuje

Princip operátora 31. 10.: samostatné objekty mají být ve vrstvách a vrstvený obsah má jít otevřít v aplikacích Craft přímo z UI, jako mapy v NG-ROBOT. Po vyzkoušení v okně operátor doplnil: grafiku a texty držet odděleně v nadřízených vrstvách.

- **Vrstvy**: horní vrstvy `Grafika` (Podklad, Lišta, Vodítka, Schéma) a `Texty` (Nadpis, Fakta, Popisky, Popisky schématu, Patička). Vznikají ze `<g id>` v rendereru, takže je mají i SVG exporty. Vnořené `<g id>` VectorCraft čte jako pojmenované skupiny, ne jako podvrstvy. Popisky jsou od vodítek oddělené, text je vždy nad grafikou. PNG v Chromiu na kvinquereme beze změny (0 odlišných pixelů).
- **Bez zámku těžké práce**: zámek patří automatickým úlohám, okno může být otevřené hodiny a zastavilo by FLUX na celém stroji. Stejně to dělá NG-ROBOT. Cena: okno zabírá paměť grafiky i souběžně s FLUX.
- **Ruční úprava se nikdy nepřepíše**: každý stav dokumentu má vlastní kopii v `library/infographics/<id>/vectorcraft/`, Engine si pamatuje její sha256. Soubor, který se liší nebo přibyl (Uložit jako), je ruční úprava: tlačítko se zeptá (`409`), jestli otevřít ji, nebo novou kopii z editoru. Neuložené změny v otevřeném okně Engine nevidí.
- **Do okna jde upravená kopie písma**: VectorCraft ignoruje `font-stretch` (text o 15 % širší než náhled) a řez čte ze jména rodiny, takže kopie má `Bahnschrift SemiCondensed` a `Bahnschrift Bold SemiCondensed`. Mimo kopii pro okno se nic nemění.
- **Ruční úprava se do editoru nevrací.** Exporty z ní řeší rozhodnutí výše. Měření: [spike](spikes/2026-10-31-vectorcraft-okno.md).

## 2026-10-29 — Postavy, místa a rekvizity z KNIHOVNY jako předloha obrázku

Operátor 29. 10. schválil náčrt 2 („Ano, podle 2“) po připomínce, že postav a míst budou desítky a víc.

- **Studio, okno Přidat předlohu, záložka „Postavy a místa“**: hledání podle jména a popisu karty, filtr Vše / Postavy / Místa / Rekvizity s počty, jedna dlaždice na položku s hlavní předlohou a „+ Použít“, další obrázky (boardy, pohledy místa, 3D pohledy rekvizity) až po rozkliknutí. Řazení podle poslední změny karty nebo jejích obrázků, položky bez obrázku na konci. Náhledy se načítají líně.
- **Hlavní předloha** = pravidlo KLAPKY (`primary` na kartě, jinak první obrázek v `refs/`); výchozí role postava a rekvizita = předmět, místo = scéna, bílý 3D pohled = tvar.
- **Engine** `GET /api/v2/knihovna`, v požadavku `Ref.knihovna`; provenience zapíše `<druh>/<slug>/<soubor>`, sha256 a původ z `.puvod.json`. NG-ROBOT beze změny (nové volitelné pole).
- **KLAPKA** u stylu bez vlastní ukázky ukáže první vzorek z GRAFIKU s popiskem „vzorek z GRAFIKU“; nabídka „Nakreslit chybějící ukázky“ ho dál počítá jako chybějící (jiná scéna).

## 2026-10-29 — Fáze 4: jedna sdílená složka postav, míst, rekvizit a stylů (KNIHOVNA)

Operátor 29. 10. na návrh STOPA `outputs/plans/2026-10-29-algoritmus-tvorby-obrazku.md` § 11: „Souhlasím, spusť“.

- **Složka `C:\Users\stock\Documents\000_NGM\KNIHOVNA\`** mimo git (obrázky, 3D), cesta přes `NGM_KNIHOVNA`. Zálohu nemá dnes ani po změně. Rozložení z KLAPKY (`characters/<slug>/card.yaml`, `environments/`, `props/`, `styles/`), slug zůstává identitou, takže scény, projekty a objednávky NG-ROBOT se nemění.
- **Čtení a zápis jen přes `ngm_shared.knihovna`**: zámek na kartu pro vlákna i procesy, atomický zápis. Neběží žádná služba.
- **Jedna karta stylu pro obraz i film**: `look` + oddíl `obraz` (GRAFIK) + oddíl `film` (KLAPKA) + `avoid`/`negative` jako jedno pole + `constraints`. Každý projekt bere svůj oddíl, styl bez něj se doplní z druhého. Text promptu stávajících stylů se převodem nemění (test na skutečných stylech).
- **GRAFIK čte styly z knihovny**, `/api/v2/styles` zůstává zpětně kompatibilní (cesty, parametry, tvar odpovědi). Tři výchozí styly zůstávají v gitu jako výchozí sada pro prázdnou knihovnu. Náhled stylu z KLAPKY ukazuje GRAFIK jako vzorek `nahled.png` jen ke čtení.
- **Převod jen kopíruje** (KLAPKA `studio/library/` celá, GRAFIK `styles/` bez koše), zdroje zůstávají jako záloha, dokud se převod neověří. Kolize slugů = konec bez zápisu.
- Styly POHYBU a katalog stylů NG-ROBOT zůstávají mimo knihovnu. NG-ROBOT se nemění. 3D modely zůstávají v GRAFIKU (karta na ně odkazuje jako dnes v KLAPCE).

## 2026-10-29 — Dělba práce mezi projekty: fronta těžké práce + dvě služby + jedna knihovna + sdílená data

Operátor 29. 10. na návrh STOPA `outputs/plans/2026-10-29-algoritmus-tvorby-obrazku.md` § 9: „souhlasím, můžeš to spustit“, s podmínkou „nechci, aby to narušilo nebo degradovalo fungování NG ROBOT, spíš jen vychytej možné chyby“.

- **Jedna fronta těžké práce pro celý stroj:** FLUX, Blender, VectorCraft, přepis řeči a headless Chrome se střídají přes jeden zámek (`ngm_shared.heavy_lock`, soubor `~/.gpu-lock`), nikdy neběží dvě těžké úlohy naráz. Důvod: měření 29. 10. ukázalo servery v klidu na desítkách až stovkách MB, zatížení dělá souběh těžkých úloh a dřív končil vyčerpáním RAM.
- **Služby jen dvě:** GRAFIK Engine (jeden model FLUX v GPU) a KARTOGRAF (geodata). Žádné další.
- **Jedna knihovna z jednoho zdroje:** `GRAFIK/shared` (`ngm_shared`), instalovaná do venv projektů editovatelně místo deseti kopií `grafik_client.py`. Projekty zůstávají samostatné aplikace.
- **Sdílená data místo služby** (knihovna postav, míst a stylů jako složka), návrh formátu ve fázi 4.
- **NG-ROBOT jen opravy chyb** s testem; žádné přepnutí na knihovnu ani zámek bez samostatného souhlasu. Engine zůstává pro NG-ROBOT zpětně kompatibilní (endpointy, parametry, výstupy).
- Fáze 1 (tento repozitář): knihovna, sloučený klient s `translate=`, zámek, Engine pod zámkem pro FLUX i všechny běhy Blenderu (i zmenšení pro prohlížeč a natažení, které dřív zámek nebraly). `GET /api/v2/health` má navíc `heavy_lock` (kdo zámek drží). Fáze 2 (přechod KLAPKY, KARTOGRAFU, POHYBU, HEGEMONU, RUKOPISU a STOPA na knihovnu) dělají samostatné sessions podle `shared/README.md`.

## 2026-10-28 — 3D modely jen přes GRAFIK Engine

3D modely jen přes GRAFIK Engine, pořadí Blender → Hunyuan 3.1 Pro → Hunyuan3D v3 → TRELLIS 2 → nahraný GLB; Hunyuan v2/v2 mini vyřazen; lokální Hunyuan3D-2 mini už není výchozí (licence Tencent nekryje EU). KLAPKA volá `fal-hunyuan31pro` přes `/api/v2/models3d` (cena předem z `/api/v2/models3d/estimate`, 402 bez `confirm_cost`, záznam útraty v GRAFIK) a nezkontrolovaný model nepřevezme.
Zdroj: operátor 2026-10-28 („Dodělej ty další doporučené akce“); návrh `KLAPKA/docs/3d-backendy-navrh.md`.

## 2026-10-27 — 3D: optimalizovaná kopie pro prohlížeč přes glTF Transform (cetej/GRAFIK#64)

Zadání operátora přes session „Open source nástroje pro Opus 5.5“ (schválené implementace z posouzení 20 nástrojů): optimalizace modelů glTF Transform, originály se nepřepisují, nic placeného.

- **Optimalizuje se `viewer.glb`, ne `model.glb`.** Prohlížeč modelu i scény načítá jen zmenšenou hliněnou kopii; Blender čte `model.glb`. Vedle `viewer.glb` vzniká `viewer.opt.glb` (meshopt, kvantizace, bez spojení a instancování, textury WebP ≤ 2048 px, kdyby nějaké byly). Kopie je ~3,5× menší (1,2 MB → 0,33 MB).
- **Prohlížeč ukazuje dál hlínu.** Textury do prohlížeče nepřibyly; srovnání textur proto není, plný model s texturami se neoptimalizuje (žádný spotřebitel).
- **Selhání nic nezastaví:** chyba se zapíše do `viewer.optimized`, Studio načte `viewer.glb`. Nástroj je Node balíček v `engine/gltf/` (`npm ci` ve složce `engine/gltf`, instaluje i `start-grafik.bat`).
- Žádná změna UI (stejný prohlížeč, jen menší soubor), proto bez náčrtu.

## 2026-10-27 — 3D scény: tenká vrstva v GRAFIK, Q2–Q5 podle doporučení

Operátor: „Schvaluji cestu (3) a náčrt, Q2–Q5 podle doporučení. Postav S1–S5.“ Návrh: `docs/plans/2026-10-27-3d-sceny.md`, náčrt `docs/spikes/img/2026-10-27-3d-sceny-nacrt.png`.

- **Cesta (3):** scény staví GRAFIK sám z vlastních částí (render z kamery prohlížeče, prohlížeč three.js, zámek GPU, předloha s kontrolou). KLAPKA se nemění; scéna KLAPKY je záběr videa a její render není bílý.
- **Q2:** ručně zadaný rozměr se uloží i k verzi modelu (`rozmer_m`, `rozmer_zdroj` v `model.json`), další scéna ho převezme.
- **Q3:** jednoduché tvary kvádr a válec (molo, terén, základy).
- **Q4:** kontrolní postava 1,72 m je ve scéně vždy, ve snímku pro FLUX jen na zaškrtnutí (výchozí vypnuto); věta o měřítku jde do zadání vždy.
- **Q5:** pravoúhlá kamera až s kótami, ne teď.
- Operátor 27. 10. během stavby: loď do scén je ta odladěná pro infografiku (`scripts/3d/lod_kvinquerema.py`), ne TRELLIS. V knihovně je jako `rimska-kvinquerema-blender-z-rozmeru-rekonstrukc` (v2 bez měřítkové postavy skriptu).

## 2026-10-27 — 3D: Hunyuan 3.1 Pro jako další volba

Operátor: „Dobře přidej tu metodu HunyuanPro jako další volbu.“ (KLAPKA ji 5. 10. vyhodnotila jako nejlepší z jedné fotky, `KLAPKA/docs/figury-3d.md`; návrh společného seznamu `KLAPKA/docs/3d-backendy-navrh.md`.)

- Metoda `fal-hunyuan31pro` (fal `fal-ai/hunyuan-3d/v3.1/pro/image-to-3d`, Geometry): 0,375 USD, s dalšími pohledy +0,15 USD (ceník fal 27. 10.). Ve Studiu je to další tlačítko metody. Doporučení se nemění, výchozí zůstává TRELLIS 2 pro jednu předlohu a Hunyuan3D v3 pro víc předloh.
- Hunyuan volání přestala posílat `face_count`, protože fal účtuje „vlastní počet ploch“ 0,15 USD navíc. Výchozí počet je stejný (500 tis.). Zda dřívější běhy s `face_count: 500000` fal naúčtoval dráž, není ověřeno.

## 2026-10-27 — 3D v2: náčrt prohlížeče schválen

Operátor na dotaz k náčrtu `docs/spikes/img/2026-10-27-3d-v2-nacrt-1.png` a `-2.png`: „Schvaluji, stavět“.

- Prohlížeč modelu je výchozí: pojmenované pohledy, čtvercový výřez předlohy, ohnisko 35/50/85 mm.
- Sheet 8 pohledů je pod prohlížečem a vzniká na tlačítko.
- „Použít tento pohled“ vpravo pošle render z kamery prohlížeče a ukáže náhled odeslané předlohy.
- Knihovna three.js 0.170.0, stejná verze jako KLAPKA `prototypy/threejs-kolo`. Prohlížeč dostává zmenšenou kopii modelu (100 000 trojúhelníků).
- Výsledek: `docs/spikes/2026-10-27-3d-v2-prohlizec.md`.

## 2026-10-27 — 3D: otáčení modelu výchozí, sheet pohledů na tlačítko

Operátor: „otáčení i pohledy – by měly existovat vedle sebe. Otáčení jako výchozí, pohledy generování sheetu na tlačítko.“

- V záložce 3D je výchozí prohlížeč modelu s otáčením. Arch 8 bílých pohledů vznikne až na tlačítko.
- Zadání pro další sessions (v2 prohlížeč, scény, napojení KLAPKY): `docs/plans/2026-10-27-3d-dalsi-zadani.md`.

## 2026-10-27 — 3D krok v1: náčrt i návrh schválen

Operátor: „Schvaluju náčrt i návrh 3D v1 s návrhy u Q1–Q4, stavěj.“ Návrh `docs/plans/2026-10-27-3d-v1.md` (#55), náčrt `docs/spikes/img/2026-10-27-3d-nacrt.png`.

- Q1: před renderem v Blenderu Engine zastaví vlastní sd-server (podle PID), render jde pod zámek GPU. Volba se potvrdí měřením v T1.
- Q2: výřez předloh se ukáže před placeným krokem a jde poopravit gumou.
- Q3: galerie 8 hotových pohledů, výška kamery nízko / 20° / shora; otáčení myší až ve v2.
- Q4: natažení na rozměry jen polem „d × š × v“ a volbou, kterou část protáhnout (střed / zadní část / celé).

## 2026-10-27 — 3D: Hunyuan3D v3 v nabídce

Operátor: „Doplň Hunyuan3D do nabídky.“ Po měření na Tatře, soše, slonovi a mostecké věži (`docs/spikes/2026-10-27-3d-trellis-vs-blender.md`, #51–#53).

Nabídka cest k 3D modelu (TRELLIS zůstává výchozí podle rozhodnutí níže):

| Cesta | Kdy | Cena |
|---|---|---|
| TRELLIS 2 (`scripts/3d/trellis_run.py`) | výchozí; jedna dobrá fotka | 0,30 USD |
| **Hunyuan3D v3 Geometry** (`scripts/3d/hunyuan_run.py`) | jsou fotky z víc stran (zepředu, zezadu, z boku); vrací rovnou bílý model bez úlomků | 0,225 USD z 1 pohledu, 0,375 USD s víc pohledy |
| Blender z rozměrů (`scripts/3d/lod_*.py`) | záloha; rozhodují poměry ze zdroje | 0 USD |
| Natažení modelu na rozměry (`scripts/3d/stretch_glb.py`) | doplněk ke generovanému modelu, když rozměry ze zdroje známe | 0 USD |

- Hunyuan3D ze **stavby** jen s víc pohledy (z jednoho si přidal celou věž navíc).
- U **zvířat** pohledy pokud možno od jednoho jedince; ve fotce zezadu nesmí být mezi zadníma nohama vidět chobot ani ocas (slon dostal pátou končetinu).
- Placené volání jen s cenou předem a potvrzením; bílý model se před FLUX kontroluje.

## 2026-10-27 — 3D: TRELLIS primárně, Blender jako záloha

Operátor po měření na třech objektech (`docs/spikes/2026-10-27-3d-trellis-vs-blender.md`, #48) upravil navržené pravidlo: „Trellis primárně, Blender jako záloha.“

- **Výchozí cesta k 3D modelu je TRELLIS 2** přes fal (0,30 USD za model, jen s cenou předem a potvrzením). Před odesláním zkontrolovat výřez předlohy (bez cedulek a pozadí), po něm nechat jen největší souvislou část modelu.
- **Blender ze zdrojových rozměrů je záloha**: když TRELLIS nedrží poměry (v měření Tatra 87: převzal zkrácení perspektivy z fotky), když není použitelná fotka, nebo když na poměrech podle zdrojů záleží víc než na detailu.
- Blender a FLUX nesmí běžet souběžně (měření: 7,2 z 8 GB VRAM, úloha FLUX spadla). Při napojení do Engine jde Blender pod zámek GPU.
- Operátor zároveň zadal průzkum dalších možností 3D modelování.

## 2026-10-26 — Dávka variant ve Studiu podle náčrtu

Operátor schválil náčrt (session z „Agent workflow best practices“, nápad z článku „How I work with Agents“): místo kol „zkus tohle… ne, tamto“ dávka a stránka pro výběr.

- Ve Studiu sekce „Dávka na výběr“ pod tlačítkem Vygenerovat: počet 6/8/12/16, zaškrtnuté styly, ve frontě řádek s odkazem na stránku výběru.
- Jen lokální FLUX (0 USD); Engine placený generátor v dávce odmítne. Cena za překlad české předlohy jde přes potvrzovací okno za celou dávku.
- Stránka je stejná jako z `grafik_client variants` a STOPA `/nano --variants` (`clients/variants_page.py` ze STOPA).

## 2026-10-23 — GRAFIK v1 z repa pryč

Operátor: „Starého grafika nepotřebuji.“

- Kód v1 (`grafik/`, `ui/`, `ui-web/`, `.streamlit/`, testy a skripty v1) odebrán; historie pod tagem `v1-final`.
- `start-grafik.bat` spouští jen Engine :8300 a Studio :5174; `pyproject.toml` balí jen `engine` (bez streamlit, typer, opencv).
- Uživatelská data (`projects/`, `library/`, `styles/`, `run/`, `logs/`) zůstala beze změny.

## 2026-10-23 — Zásady infografik místo kopírování vzoru

Operátor: „nejde o to sekat infografiky stejné jedna jako druhá, jako Baťa cvičky … jde o to pochopit, okoukat čistý grafický styl, rovnováhu, informační hodnotu a čtenářský zážitek.“ Pak „Dobře dotáhni to“.

- Zásady a měřitelné prahy v `docs/infografiky-zasady.md`, pravidlo `.claude/rules/infografiky.md`; úsudek o celku zůstává na člověku, čísla jen upozorní.
- Nové infografiky: rozvržení „Lišta přes obraz“ 1920×1080; staré dokumenty beze změny („Klasické“).
- Co nemá doklad, do obrazu nepatří: věž na lodi z 1. punské války odstraněna; řez boku bez informační hodnoty vynechán; moře pryč, protože zhoršovalo čitelnost popisků.
- Postup obrázku pro infografiku: model v Blenderu z rozměrů → hliněný render → pokusy na lokálním FLUX zdarma → konečná kresba placeným modelem jen se souhlasem a cenou předem.

## 2026-10-23 — 3D cesta: TRELLIS 2 + Blender jako předloha pro generátor

Operátor: TRELLIS má z dobrých předloh postavit správné 3D, z něj dostane správné zadání náš generátor; hodí se i pro 3D scény ve spolupráci s Blenderem. Schválil instalaci Blenderu a nejvýš 2 běhy TRELLIS 2 po 0,30 USD.

- TRELLIS 2 běží na fal.ai (`fal-ai/trellis-2`, 0,25/0,30/0,35 USD za 512p/1024p/1536p), lokálně ne (≥16 GB VRAM, Linux). Placený jako ostatní: cena předem, souhlas.
- Blender 5.2.3 LTS portable v `C:/Users/stock/tools/`, ovládaný skriptem headless; render jde do lokálního FLUX jako `geometry` předloha (zdarma).
- Spike: `docs/spikes/2026-10-23-3d-trellis-blender.md` (0,30 USD, tvar lodi držel). Napojení do Engine/Studia zatím ne.

## 2026-10-23 — Termdb v překladu a v kontrole infografiky

Operátor: „Napoj termdb na překlad i na kontrolu infografiky: zdarma a lokálně, jednoznačné termíny předat překladu jako nápovědu, neznámé označit ‚není v termdb‘, bez placeného vyhledávání na webu.“

- Termdb = `BIOLIB/termdb.db` (sdílená s NG-ROBOT), GRAFIK ji jen čte (`GRAFIK_TERMDB`, prázdná hodnota vypne). Placené vyhledávání na webu z NG-ROBOT se nepoužívá.
- **Nápověda do překladu jen pro jednoznačné odborné termíny** (biologie, zeměpis…): všechny odborné významy se shodují a slovníkový výklad nemluví o něčem jiném. Proto „liška obecná“ (v biologii houba, ve slovníku liška) ani „Most“ (město × most) nápovědu nedostanou. Nápověda je součástí klíče mezipaměti překladu a je v provenienci.
- **Kontrola infografiky:** „není v termdb“ se hlásí jen u nadpisu a hlavních textů popisků (1. pád); podtitulek, drobné texty, schéma a fakta jsou skloňovaná věta, tam jen nejednoznačné termíny.

## 2026-10-23 — G5 infografiky

- **Náčrt G5 schválen** („Schvaluji náčrt G5, stavěj.“): záložka Infografiky (obsah vlevo, živý náhled uprostřed, vzhled, kontrola a export vpravo), vstupy z kroku 5 Průvodce a tlačítkem „→ Infografika“, návrh popisků od Claude jen na kliknutí s cenou. Vzor: kvinquerema `overlay_quinq3.html` (do ~5 popisků, čáry mimo objekt, 3 fakta, vektorové schéma, tmavé pozadí, patička se zdroji a AI).
- **Text v infografice nikdy z modelu**: popisky, fakta i schéma píše redakce v editoru; Claude navrhuje jen názvy částí a místa, ne fakta.
- **Označení AI v patičce se doplní z provenience a nejde smazat**; export bez něj Engine odmítne. Kontrola člověkem (jméno) se zapíše do provenience exportu.
- **Jeden renderer:** studio kreslí SVG, Engine ho jen vyčistí (bez skriptů a odkazů ven) a převede na PNG/PDF stejným Chromiem. Exporty v `library/infographics/<id>/exports/`.
- Operátor 23. 10.: „Kloun? To je snad zobec“ a napojit ověření překladu na termdb (`BIOLIB/termdb.db`). Rozsah se domlouvá, viz STAV.

## 2026-10-23 — G4 styly

- **Náčrt G4 schválen** (`docs/spikes/img/g4-nacrt-1.png`, `-2.png`): záložka „Styly“ (knihovna vlevo, karta stylu vpravo), dialog „Nový styl z obrázků“ a výběr stylu v zadání ve studiu. Zadání předala zakládající session („pokračuj G4 … nejdřív mi ukaž náčrt UI“), schválení operátor dal přímo: „Schvaluji náčrt G4, stavěj.“
- **Styl jde do generátoru jen slovy**, ukázky slouží k náhledu a detekci. Paleta se měří z pixelů zdarma; popis slovy od Claude je placený (0,01 USD) a spustí ho jen tlačítko s cenou, kliknutí je souhlas jako u překladu.
- **`style.json` je zdroj pravdy**, `STYLE.md` se z něj přepisuje při každém uložení (upravovat ve studiu nebo ve `style.json`). Smazaný styl jde do `styles/.trash/`, ne pryč.
- Projekty posílají `style: "<slug>"`; volný text ve `style` zůstává volným textem.

## 2026-10-23 — Poznatky z PromptEnhancer (cetej/GRAFIK#9)

Zadání operátora přes session „PromptEnhancer analýza“ (ta byla mezitím archivovaná): co je nové oproti GRAFIK, připravit k testování a implementovat v projektu. Z Tencent PromptEnhancer přebíráme jen principy, vlastními slovy; kód ani text jejich promptů ne (licence v EU neplatí). Dataset T2I-Keypoints-Eval je apache-2.0.

- **C, překlad bez tichého pádu do češtiny:** prázdný překlad nebo překlad, ve kterém zůstala čeština, se neuloží do mezipaměti a úloha skončí čitelnou chybou. Za češtinu se počítá víc než pětina slov s diakritikou mimo uvozovky, takže místní jména („Kutná Hora“) a citované nápisy projdou.
- **Text v uvozovkách se nepřekládá** (#9 bod 1): nápis, který má být v obrázku, zůstává v původním jazyce a pravopisu v dvojitých uvozovkách. Platí pro překlad i „Rozepsat zadání“.
- **D, „Rozepsat zadání“ má pevnou stavbu:** celek → části v daném prostorovém pořadí s výslovnými slovy (vzadu, vlevo, před) → zase celek; poslední věta jmenuje styl a typ obrázku. K tomu pravidla z #9 bodu 2: fyzikální soudržnost, jen viditelné (žádné „krásný“), přesné počty, vágní přání → konkrétní změna.
- **B, překlad pokynu k úpravě vidí výřez rámečku** (≤ 512 px): objekt se pojmenuje podle toho, co v rámečku opravdu je, ne jen podle slova operátora. Klíč mezipaměti zahrnuje otisk výřezu. Výřez je v odhadu jako položka 0,002 USD (Haiku 5.5 za ~350 tokenů reálně ~0,0001 USD, odhad je s rezervou).
- **A, měření klíčových bodů** je skript `scripts/eval_keypoints.py`, ne funkce studia: vzorek anglických promptů, lokální FLUX zdarma, soudce Claude po bodech (verdikt = poslední accept/reject). Placený, bez `--confirm-cost` jen vypíše odhad. Při 20–30 promptech nečíst rozdíly pod ~10 p. b.

## 2026-10-23 — G3 předlohy a průvodce, karta Nastavení

- **Náčrty G3 schváleny:** okno „Přidat předlohu“ (Wikimedia Commons, Schránka předloh, soubor) a záložka „Průvodce“ historickým objektem (předlohy → bokorys → oprava v rámečku → natočený pohled 3/4 shora → popisky v G5).
- **Karta Nastavení** na přání operátora: ukazuje připojené služby a stav generátoru. Hesla ani klíče se v GRAFIK nezadávají ani nezobrazují; Pinterest nepotřebuje účet v GRAFIK, protože piny jdou přes operátorův přihlášený Chrome (přes Google) záložkou „→ GRAFIK“ nebo Claude in Chrome.
- Pinterest obrázky mají licenci „neznámá — jen předloha“: slouží jen jako předloha, nikdy jako součást výstupu.

## 2026-10-23 — G2 studio, čeština, cena v tlačítku

- **Náčrt studia schválen** (`docs/spikes/img/g2-nacrt.png`): vlevo zadání a předlohy, uprostřed náhled s porovnáním a úpravou v rámečku, dole fronta a galerie, vpravo historie verzí a údaje o obrázku.
- **Nové studio běží na :5174**, starý editor zůstává na :5173 do rozhodnutí operátora o archivaci.
- **Překladová vrstva:** FLUX česky rozumí jen zhruba (ověřeno: český pokyn úpravu neprovedl, z „majáku“ udělal dům). Engine proto překládá české zadání, pokyn i styl přes Claude do angličtiny laděné pro cílový generátor; opakovaný text z mezipaměti zdarma.
- **Cena překladu (~0,01 USD) se ukazuje v tlačítku a kliknutí je souhlas.** Dialog s cenou zůstává pro placené generátory. Operátor odsouhlasil živý test dvou překladů (~0,02 USD).
- Pokračovat podle plánu: supersample, fal jako volba s cenou předem, G2; napojení dalších projektů zatím ne (zpráva zakládající session, operátor „Tak pokračuj“).

## 2026-10-22 — GRAFIK v2: spec G0 schválen, odpovědi Q1–Q5

Operátor schválil spec `docs/plans/2026-10-22-grafik-v2-greenfield.md` a start G1 (Engine).


- **Q1 rozhraní:** nový React web (Vite, :5173), stejný stack jako dnešní `ui-web/`.
- **Q2 výstupy:** centrálně v GRAFIK `library/RRRR-MM/<job>/` s proveniencí; volající projekt dostane kopii a uloží si ji po svém.
- **Q3 karta stylu:** formát POHYB — `styles/<slug>/STYLE.md` + `style.json` + `samples/`; knihovna v GRAFIK, ostatní projekty čtou přes API.
- **Q5 port:** nový Engine převezme :8300 (projekty ho mají natvrdo); starý editor se přesune na :8301 a zůstane spustitelný do konce G2, pak operátor rozhodne o archivaci.
- **Q4 Pinterest:** všechny tři cesty — Claude in Chrome uloží pin (obrázek + URL) do `refs/inbox/`, přetažení souboru do UI, bookmarklet v Chrome posílající obrázek do Engine.

## 2026-10-22 — GRAFIK v2: lokální FLUX jako výchozí generátor

Zdroj: `ZZZ_TEST/plan-flux-vychozi-vsude.md`, rozhodnutí operátora 22. 10.

1. **FLUX 3 Klein lokálně je výchozí generátor obrázků** ve všech projektech (Q4 GGUF + encoder Qwen3-VL-4B Q4, stable-diffusion.cpp `master-987`, `C:/Users/stock/models/flux3-klein/`). Měřeno na RTX 4060 Laptop 8 GB: 1024² ~38 s, 1920×1088 ~95 s s `--vae-tiling`, edit s referencí ~70–90 s.
2. **Placené generátory (Nano Banana Pro, fal) jen na výslovné přání** a s cenou zobrazenou předem. Nikdy automatický fallback.
3. **Licence FLUX Kommunity v1.0 je splněná** (obrat skupiny < 5 M USD). Podmínka § 2e: před zveřejněním výstup zkontroluje člověk a nese označení „vytvořeno AI“, kde to vyžaduje zákon. Engine ukládá `ai_generated: true`, `reviewed_by: null`.
4. **GRAFIK se přestaví od nuly** jako obrazové studio operátora a jediná obrazová služba (GRAFIK Engine) pro NG-ROBOT, KLAPKA, KARTOGRAF, POHYB, HEGEMON a STOPA `/nano`. Důvod: jedna GPU s 8 GB neunese souběžné instance FLUX. Starý kód zůstává jako reference; mazat jen se souhlasem.
5. **Video osa se do nového GRAFIK nepřenáší.**

Ověřené poznatky z testů 22. 10., které spec přebírá:
- Přenos stylu obrazovou referencí ve FLUX nefunguje, styl je nutné popsat slovy.
- Reference předmětu a geometrie funguje velmi dobře.
- Drobné postavy se deformují: reference se správným měřítkem, generovat výš a zmenšit.
- Schválený postup pro historické objekty: předloha → čistý bokorys → oprava v rámečku → natočený pohled 3/4 shora → popisky jako vektorová vrstva.

## 2026-10-31 — Blender sdílený v AppData

Operátor sjednotil Blender všech projektů do jedné přenosné instalace `%LOCALAPPDATA%/Programs/Blender/blender-<ver>-windows-x64/`; Engine bez `GRAFIK_BLENDER` bere nejnovější 5.2.x odtud (jinou řadu sám nevybere) a `C:/Users/stock/tools/` zůstává jen záloha.
