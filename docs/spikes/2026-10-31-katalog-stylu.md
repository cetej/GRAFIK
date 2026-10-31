# Katalog stylů: 144 stylů v šesti kategoriích, ukázky

2026-10-31 až 11-01. Rozhodnutí: [DECISIONS 2026-10-31](../DECISIONS.md). Katalog `styles/katalog.yaml`, skript `scripts/styles_katalog.py`.

| Kategorie | Stylů | z toho nových | Přehled ukázek |
|---|---:|---:|---|
| Fotografie | 19 | 19 | [obrázek](img/2026-10-31-styly-fotografie.jpg) |
| Historické (pravěk až pop art) | 51 | 51 | [obrázek](img/2026-10-31-styly-historicke.jpg) |
| Ilustrace | 24 | 22 | [obrázek](img/2026-10-31-styly-ilustrace.jpg) |
| 3D | 14 | 10 | [obrázek](img/2026-10-31-styly-3d.jpg) |
| Komiks | 11 | 10 | [obrázek](img/2026-10-31-styly-komiks.jpg) |
| Film | 25 | 17 | [obrázek](img/2026-10-31-styly-film.jpg) |
| **Celkem** | **144** | **129** | |

## Jak katalog rostl

1. **Podle zadání (67):** šest kategorií, Historické po klasicismus.
2. **Romantismus až moderna (21), na pokyn operátora:** romantická krajina a dějinná malba, realismus, akademismus, impresionismus, pointilismus, van Gogh, Gauguin, secese (Mucha), Klimt, expresionismus, fauvismus, kubismus, futurismus, geometrická abstrakce, konstruktivismus, art deco, americký realismus, surrealismus, socialistický realismus, pop art.
3. **Mezery po druhé analýze (23):**
   - Historické: kamenný reliéf, tapiserie, Leonardovy studie, mayská a aztécká malba.
   - Fotografie: architektura, podmořská, autochrom, družicový snímek, astrofotografie, světelný mikroskop. National Geographic bez nich není úplný.
   - Ilustrace: pérovka, přírodovědná tabule, naivní český venkov, vystřihovánka, technický řez.
   - 3D: vědecká vizualizace, drátěný model.
   - Komiks: pulpová obálka, novinová karikatura.
   - Film: německý expresionismus, filmový týdeník, stínová animace, anime.
4. **Propagandistické plakáty (5), na pokyn operátora:** sovětský, nacistický, čínský; session přidala americký a československý. Karta popisuje vzhled, obsah určuje zadání; nápisy zakázané jako všude. Zákaz symbolů, vlajek a skutečných osob, který session přidala sama, operátor 1. 11. zrušil. Ukázky 8 dotčených karet (5 plakátů, konstruktivismus, socialistický realismus, karikatura) vznikly ještě se zákazem, motivy mají neutrální a znovu se negenerovaly.
5. **Retro a vintage (13), na otázku operátora:** Polaroid, kolorovaná fotografie, mid-century, Bruselský styl, vintage reklama, retrofuturismus, 70. léta, retrowave, pixel art, risografie, hra z 90. let, kreslený film 30. let, večerníček.

**Retro není sedmá kategorie.** Dělí podle doby, ostatní kategorie podle vzhledu, a Polaroid má být mezi fotkami. Poznámka všech 25 retro stylů začíná „Retro a vintage“, hledání ve Studiu je tak najde bez nového kódu.

## Co jsem záměrně nepřidal

| Co | Proč |
|---|---|
| Abstraktní expresionismus (kapky, gesto) | předmět obrázku zmizí, nic by nepopisoval |
| Prerafaelité, vrcholná renesance, manýrismus | blízko severní renesance, quattrocenta a akademismu |
| Mughalská miniatura | blízko perské miniatury |
| Aboriginální tečkování a jiné posvátné tradice | citlivé kulturně, pro běžná témata nepoužitelné |
| Stará mapa, reliéfní mapa terénu | mapy dělá KARTOGRAF |
| Stavebnice typu LEGO | chráněná značka, blízko voxelu |
| Termokamera, novinářský blesk 40. let | malé využití, jde dodat, až bude téma |
| Underground komiks, webtoon | blízko novinového stripu a moderního komiksu |
| Italský neorealismus | blízko československé nové vlny |
| Psychedelický plakát, plakát 1. světové války, kubánský plakát | blízko pop-art komiksu, cestovního a propagandistických plakátů |
| Steampunk, dieselpunk | žánr a obsah, ne výtvarný styl; jde popsat v zadání s retrofuturismem |

## Jak vznikly ukázky

Přes běžící Engine :8300, lokální FLUX, 1024×768, seed 42, po jedné úloze. Nové styly mají 3 ukázky, stávající 2 (`karikatura-3d-real` žádnou, má 5 vlastních vzorů operátora). Plán 415 ukázek. Žádná úloha neselhala, jedna ukázka trvá 28 až 33 s bez cizích úloh ve frontě. Cena viz STAV: všechny úlohy `styl:*` mají backend `flux-local` a `cost_usd` 0.

## Co se opravilo po prohlédnutí

Všechny přehledy jsem prošel očima, podezřelé kusy zvlášť ve větším. Opravy textu karty, ukázky pak znovu:

| Styl | Vada | Oprava karty |
|---|---|---|
| Jeskynní malba | lampa na skále | pryč slovo o lampě |
| Ligne claire | auta na polní cestě | pryč „vehicles“ |
| Studiový portrét | softbox v obraze | pryč slovo softbox |
| Kodachrome | rámeček diapozitivu | „no slide mount“ |
| Holandský žánr | kůň v kuchyni | interiér pryč z kompozice |
| Gotická vitráž | realistický obraz uprostřed okna | celý obraz ze skla |
| Moderní komiks | malba nebo fotka místo komiksu | pevná linka, tvrdé stíny |
| Čínská tuš | spíš rytina | řídké tahy štětcem |
| Spaghetti western | koláž tří záběrů | „one unbroken frame“ místo „close-ups mixed with long shots“ |
| Přírodopisný dokument | kamera nad vodou | pryč „stabilised mount“ |
| Němý film | kamera na stativu vedle sedláka | pryč „camera“ a „tripod“ |
| Encyklopedická rytina | nástroje na cestě u koně | dole „details of the same subject“ místo „tools“ |
| Renesanční studie | čtyři stejní koně, sedlák zmizel | jedna hlavní studie a menší detaily |
| Mayská a aztécká malba | realistický strom a kůň v rámu | vše ploše, bez hloubky krajiny |
| Surrealismus | obyčejná krajina | balvan ve vzduchu a dveře na pláni přímo v kartě |
| Družicový snímek | mapa z ilustrace, červené skvrny | skutečné barvy místo nepravých |
| Vědecká vizualizace | plochá pestrá ilustrace | fotorealistický render, tři barvy |
| Novinová karikatura | malé postavy | postavy přes celý obraz |
| Astrofotografie | místo Měsíce Mléčná dráha | karta už nejmenuje galaxii, jen černý prostor |
| Budovatelský plakát | šátky i na mužích | pryč „headscarves“ |
| Kolorovaná fotografie | skoro bez barev | barvy vyjmenované přímo v kartě |
| Hra z 90. let | fotka v mlze | hrubé trojúhelníky, 320 × 240; výsledek je spíš pixelový |

Jen jiný seed (srostlá postava s koněm, cizí tvar v obraze): raná renesance, klasicismus, barok a romantická dějinná malba 43, rokoko a plochá vektorová 45. Stejně potápěč bez dýchacího přístroje a falešný podpis na fauvistickém obraze, oba 43. Stav je v `run/katalog-ukazky.json`. U baroka seed 45 dopadl hůř, zůstal 43. Muzejní předmět dostal místo meče korintskou přilbu, přírodovědná tabule má jako první medúzy místo sedláka.

## Co zůstává

- **Sedlák u koně je těžký motiv.** U několika stylů (komiksový strip, noir, tapiserie) jsou na obrázku dva sedláci místo jednoho, někde sedlák na koni jede. Styl to nekazí, nechal jsem to. Němý film má na první ukázce oči, které připomínají tmavé brýle.
- **Stávající karty lampy kreslí dál:** `anticke-drama` má v trávě svíčky, `malovany-epos` lampu na pařezu. Text těch karet je z KLAPKY a nesahal jsem na něj.
- **`dokumentarni-rekonstrukce` a `-era`** dávají stejný obraz, mají stejný text.
- **Text stávajících karet se nezměnil:** `image_text` a `video_lines` 11 karet z KLAPKY sedí na `KLAPKA/studio/library/styles`, pole 3 karet z GRAFIKU na `styles/<slug>/style.json` v gitu. U `karikatura-3d-real` starší kopie k porovnání není; skript jí doplnil jen `kategorie` a `poradi`.
