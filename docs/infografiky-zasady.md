# Zásady infografik

Operátor 2026-10-23: nejde o kopírování vzoru, ale o pochopení čistého grafického stylu, rovnováhy, informační hodnoty a čtenářského zážitku. Špatně je nesoulad, přeplácanost, stísněnost, rozháraný styl a špatné poměry, kdy čtenář neví, na co kouká. Vzor pro porovnání: „Anatomie langskipu“ (vložen 22. 10.; generovaný AI, takže jen pro kompozici a typografii, ne pro obsah).

## Čtyři zásady

1. **Čistý styl.** Jedna písmová rodina ve dvou řezech: tučný řez akcentovou barvou pro názvy a klíče, obyčejný řez světlou barvou pro vysvětlení a hodnoty. Kontrast vzniká tloušťkou a barvou, ne střídáním písem. V editoru: Bahnschrift, zúžený řez (je ve Windows, takže ho má náhled i export přes Playwright).
2. **Rovnováha.** Obraz, popisky a fakta tvoří jeden celek. Žádné prázdné pásy. Nadpis a podtitulek tam, kde má obraz volné místo (u kvinqueremy vlevo nahoře). Krátká fakta dole vlevo, každé na vlastním řádku, zarovnaná na prapor; podklad jen za nimi, ne pruh přes celý obraz. Doplňkový výřez (řez, detail) leží volně na obraze bez rámečku a panelu: obrázek vyříznutý s průhledným pozadím a ostrými okraji (nerozmazávat), popisky v něm na vodítkách jako u hlavního obrazu.
3. **Informační hodnota.** Každý popisek odpovídá na otázku, kterou si čtenář u té části položí. Každý výřez (řez, detail) musí ukázat něco, co hlavní obraz neukáže. Řez bokem lodi, který jen opakuje příčný řez, informační hodnotu nemá. Co nemá doklad, do obrazu nepatří (věž na lodi z 1. punské války).
4. **Čtenářský zážitek.** Popisek leží u věci, kterou popisuje. Vodítko je krátké, raději svislé nebo vodorovné (jednou zalomené), nekříží jiná vodítka a nevede přes to důležité. Písmo popisku čitelné na pozadí.

Úsudek o tom, co stojí za popisek a zda celek působí vyváženě, zůstává na člověku. Číselné kontroly jen upozorní na rozháranost.

## Logika stránky (série o Teslovi, 2. 11., výtky operátora)

Stránka nezačíná tím, kam se vejdou popisky, ale dvěma otázkami: co má čtenář pochopit a co je na obraze hlavní. Operátor: „Zkus si z toho brát zkušenosti a zapracovat na logice vytváření infografik.“ Proto má každá výtka níž pravidlo a tam, kde to jde, měření v kódu. Laťka: [série o Teslovi](spikes/img/2026-11-02-serie-tesla-3d.png), operátor: „Ano, to je výrazně lepší.“ Měření v [spiku](spikes/2026-11-02-serie-mobil.md).

| Výtka operátora | Pravidlo | Kdo to hlídá |
|---|---|---|
| „Fakt myslíš, že všichni vědí, kde je Gospiče, nebo co znamená ta technická informace u motoru. Nebuď idiot - jde o popularizaci vědy.“ | Čtenář je zvědavý laik. Popisek odpovídá na „no a co?“: co věc dělá, proč je důležitá, co se tím změnilo. Technický parametr ani neznámé místo bez vysvětlení, tvrzení a čísla dál jen z faktu. | prompt `serie.SYSTEM` a `proposals.PRINCIPLES`; stroj srozumitelnost nezměří, každý popisek přečti jako laik |
| „Ty karty Tesly jsou hnusné, proč tam dáváš staré fotky“ | Vlastní 3D model nebo figura před dobovou fotkou. Fotka jde na stránku jen tam, kde vlastní obraz není. | `library/tema/<qid>/obrazy.json`, `serie.pick_images` |
| „U Tesly mají být biografická data.“ | Stránka s člověkem je životopisná: narození, smrt, místa a zlomy života. Dílo má vlastní stránky, ne výčet vedle portrétu. | prompt `proposals.KIND_RULES`, `serie.is_life_page`, hlášení „nemá narození ani smrt“ |
| „A co ty další dvě karty. Ty jsi je zahodil?“ | Série o člověku je celá: životopis a po stránce na každé stěžejní dílo s vlastním obrazem, 3 až 4 stránky. Co z vlastních obrazů stránku nemá, se řekne. Když má výsledek méně karet než schválená ukázka, řekni to dřív, než ho pošleš. | prompt `proposals.KIND_RULES`, `proposals.MAX_PAGES`, Studio u návrhu „Vlastní obrazy bez stránky“ (`bez_stranky`) |
| „Vrchole věže není vidět.“ (tmavá kupole na tmavé stránce) | Nic tmavého na tmavém. Obraz se nasvítí pro stránku, na které leží. | `panels.faint_parts`, kontrola „splývá s pozadím“: tenká část chce kontrast 2:1, velká plocha 1,2:1 |
| „Z té věže má být nejdůležitějším prvkem její podloží?“ | Hlavní věc má největší plochu a kontrast, okolí ustupuje. Podloží je pás, který vybledne, šachta z něj pokračuje a ztrácí se, skutečnou hloubku řekne popisek. | příprava obrazu (`scripts/3d/tesla_tema.py`), stroj to nezměří: prohlédni stránku |
| „Ten motor s tím prázdným pruhem je jako mávání hadrem býkovi před očima.“ | Prázdný pruh ani prázdná třetina stránky nejsou klid, ale chyba. Obraz roste, dokud se popisky vejdou, a když to na daném formátu nejde, změní se formát. | `panels.empty_share`: největší prázdný obdélník pod titulkem nejvýš 20 %; `serie.compose` zkusí stejně širokou stránku jiné výšky |
| „Často zmenšíš hlavní grafiku na úkor pitomých, blbě zalomených popisků s nulovou informační hodnotou.“ | Velikost obrazu se určí dřív než popisky. Kvůli popiskům se zmenší nejvýš na 70 %, pak vypadne nejméně důležitý popisek a hlášení to řekne. Holý název části bez vysvětlení na stránku nepatří. | `serie.SCALES`, `serie._compose`, prompt `serie.SYSTEM` |
| „Popisky jsou malé a divně nahloučené.“ | Název 1/20 šířky, text pod ním 86 % z toho. Popisky ve sloupci na společné svislici, název ve výšce své věci, mezera aspoň jedno písmo. Objekt přes celou šířku: popisky v řadě nad ním, čára rovně dolů z vlastního textu. Vyhrává to, co dá kratší vodítka. | `serie._column`, `serie._row_above`, `panels.MOBIL` |
| „Proč otrocky trváš na dlouhých řádcích třeba i ze dvou písem“ | Název a pod ním krátké vysvětlení, nikdy dvě písma na jednom řádku. Řádky vyrovnané, slovo nezůstane samo, jednopísmenná předložka nezůstane na konci řádku. Popisek na víc než 3 řádky se nevezme. | `serie._even_chars`, `serie._no_orphan`, `serie.MAX_FACT_LINES`, u faktů `stackedFacts` v editoru |
| „Vykašli se na ty drobounké popisky ZDROJ.“ | Na stránce jen označení AI (licence FLUX) a cizí autor. Zdroje jdou pod článek. | `panels.short_note`, Studio „Zdroje pod článek“ |
| „Jde o karty v rámci jednoho cyklu, tak by tam neměly být různé velikosti písem v titulcích a popiscích.“ | Karty jedné série mají stejné velikosti písma. Titulek určí ten nejdelší v sérii, popisky a text mají velikost z písma stránky. | `serie.series_title`, `chain._stranky`, test `test_cards_of_one_series_have_the_same_type_sizes` |

Rok nebo číslo patentu, které nepatří k části obrazu, nejsou volný lístek vedle obrazu: patří do věty pod titulkem (prompt `serie.SYSTEM`). Volný fakt obraz nezmenšuje. Když by se zalomil na víc než 3 řádky nebo se nevejde, vypadne a řekne to hlášení (`serie.MAX_FACT_LINES`).

Popisek od modelu má nejvýš 8 slov a 50 znaků (životopis 12 slov). Písmo se u nás nemění, takže dva popisky po třech řádcích dlouhých vět jsou širší než stránka, sloupec vedle objektu se nevejde a popisek vypadne nebo skončí jinde než u své věci. Název části je v běžných slovech už v `popisky` obrazu (Spodní cívka, ne Primár).

Popisek obrazu má přednost před volným faktem, i když ho model dal níž, a formát stránky vybírá nejdřív podle popisků a velikosti obrazu, volné fakty až potom (`serie.compose`). Vedle obrazu s popisky je nejvýš jeden volný fakt, čtyři bloky kolem věže nikdo nečte, zbytek vypadne a řekne to hlášení (`serie._compose`). Čára k textu nevede přes hlavní věc, nejvýš 1,5 písma (`serie._crosses_object`, `LEADER_OVER`): když se to nedá, obraz se o krok zmenší, nebo je špatně položený bod (věž: bod na pravé noze, popisek vpravo). Všechen text stránky má jedno řádkování a volný fakt vedle popisku sedí na stejném účaří (`serie.LABEL_LINE`, `_free_panels`).

**Než stránku pošleš:** prohlédni ji sám v plné velikosti a řekni si, co je na ní hlavní a jestli to tak na první pohled vypadá. Kontrola najde díru a splývání, ale ne to, že největší je podloží. Výtku převeď na měření v kódu nebo pravidlo tady, ne jen na opravu ukázky: operátor nemá vychytávat každou grafiku zvlášť.

## Web a mobil (operátor 2. 11., platí pro každou infografiku)

Operátor k plakátům o vojákovi ve studni: grafiky jsou fajn, ale „na webu v těch poměrech velikosti nejdou nic úžasného“. Infografiku čtenář vidí v článku, velmi často na mobilu. Stránka se tam zmenší na šířku displeje a většina lidí ji nezvětšuje, takže větší plátno nepomůže: o čitelnosti rozhoduje jen poměr písma k šířce stránky.

**Volba: web, nebo tisková příloha.** Operátor 2. 11.: „De facto by tam mělo být rozhodování / možnost, zda vytváříme tiskovou přílohu, nebo infografiky pro web, které budou defaultním požadavkem.“ Výchozí je web a platí vše v tomto oddílu. Tisková příloha (`urceni: "tisk"`, přepínač „Kam to půjde“) se čte z papíru, smí být bohatá a kontrola mobilu pro ni neplatí.

**Navrhuj pro telefon široký 360 px, a to před skladbou.** Hotovou stránku už to nezachrání.

| Text | Na telefonu | Podíl šířky stránky | Stránka 1080 px | Stránka 1800 px |
|---|---|---|---|---|
| titulek | ≥ 24 px | 1/15 | 72 px | 120 px |
| nadpis panelu | ≥ 18 px | 1/20 | 54 px | 90 px |
| věta, vysvětlení | ≥ 14 px | 1/26 | 42 px | 70 px |
| popisek u věci, nejmenší text | ≥ 12 px | 1/30 | 36 px | 60 px |
| zdroj, označení AI | ≥ 9 px | 1/40 | 27 px | 45 px |

Mez 12 px je hranice mobilního auditu [Lighthouse](https://developer.chrome.com/docs/lighthouse/seo/font-size) (v Lighthouse 13 audit zmizel, hranice zůstává rozumná). Ostatní řádky jsou odstupňované od ní. Operátor s nimi přijal první sérii (Studna, 2. 11.).

**Kolik se vejde.** Při 12 px je na šířku stránky zhruba 60 znaků. Na 4:5 (na telefonu 360 × 450 px) s obrazem přes půl stránky zbývá kolem 80 slov, na 2:3 kolem 120. Popisky na obraze se počítají do toho. Dnešní plakáty, změřené 2. 11. ze SVG (`library/plakaty/`):

| Stránka | Rozměr | Slov | Text pod 12 px na telefonu | Nejmenší / nejčastější na telefonu |
|---|---|---|---|---|
| Muž na dně studny (`velsen/hotovo4`) | 1800 × 2400 | 239 | 32 z 33 | 4,0 / 5,2 px |
| Kdo ho zabil? (`velsen/hotovo-scenare`) | 1800 × 2400 | 273 | 49 z 50 | 4,0 / 4,8 px |
| Tesla (`tesla-kopie-v2`) | 1472 × 2616 | 352 | 90 z 91 | 3,0 / 3,8 px |
| Axolotl (`axolotl-kopie`) | 1500 × 2000 | 140 | 39 z 39 | 4,6 / 5,3 px |
| Pantheon (`pantheon`) | 1600 × 2400 | 262 | 68 z 69 | 3,8 / 4,7 px |

**Velká plachta se dělí.** Kde by text vyšel pod práh, písmo se nezmenšuje a stránka se rozdělí na víc menších.
- Dělí se podle otázek čtenáře: jedna stránka, jedna otázka, jeden hlavní obraz a nejvýš 3 další panely. Studna a scénáře jsou tak rozdělené už teď, jen každá z nich nese ještě dvakrát až třikrát víc textu, než se vejde.
- Každá stránka obstojí sama: vlastní titulek a řádek se zdrojem. V článku stojí u jiného odstavce a čtenář ji může poslat dál samotnou.
- **Řádek Zdroj na stránce není (operátor 2. 11., novější než věta dál).** Renderer dokumentu i editor kreslí jen označení AI a cizího autora. Starší znění: **Zdroj je jeden krátký řádek pod obrazem** („Proč jsou tam drobným ty obrovské popisky o zdrojích“, operátor 2. 11.): autor a rok, co je AI, nejvýš jedna výhrada, která mění čtení obrazu. Licence, kresby, modely a postup patří pod článek, skript je zapíše do `zdroje.txt` vedle stránek. Vzor `scripts/plakaty/velsen_studna_mobil.py`.
- Série drží stejné písmo, barvy a velikosti, stejný objekt vypadá na všech stránkách stejně.
- Souhrnný plakát na jedné ploše vznikne navíc jen na přání operátora, pro tisk nebo stažení. Do článku jde série.
- Věrná kopie husté předlohy pravidlo poruší. Řekni to operátorovi předem a navrhni rozdělení.

**Formát.** Výchozí je 4:5 (1080 × 1350) nebo 2:3. Delší stránka než 9:16 se nevejde na jednu obrazovku telefonu. Formát 16:9 je na telefonu 360 × 202 px: jeden obraz a několik popisků, žádné panely.

**Hotovou stránku neděl mechanicky.** Automat, který rozdělil plakát a zachoval každé slovo, operátor odmítl (2. 11.): zmenšoval hlavní obraz kvůli popiskům bez informační hodnoty. Nejdřív jedna věta, co má čtenář pochopit, pak obraz co největší a jen popisky, které k té větě pomáhají. Co vypadne, řekni operátorovi. Ukaž jednu stránku, až po souhlasu další.

**Kontrola.** `write_poster` vypíše `SAZBA: na mobilu…` a `GET …/kontrola` hlásí totéž (Engine, panely), editor má stejný řádek v Kontrole. Nový dokument s panely (`panels.MOBIL`) i nový dokument v editoru (`pismo: "mobil"`) mají velikosti podle tabulky. Starý dokument se kreslí beze změny, porovnáno bajt po bajtu ([spike](spikes/2026-11-02-serie-mobil.md)), a dostane jen nález.

**Vzor série.** `scripts/plakaty/velsen_studna_mobil.py`: plakát Muž na dně studny (239 slov) jako tři stránky 1080 × 1620 po 72, 42 a 45 slovech bez zdroje. Fakta zůstala všechna, zmizel jen metrový pruh, který hloubky na okraji nahrazují. Co bylo na plakátu malé, je na stránce velké a vady jsou vidět: pánev a výřez chtěly nový render ve větší velikosti, hladké kameny hrubší povrch (`velsen_studna.py --zblizka`). Výřez z renderu plakátu nestačí.

## Stránka z víc obrazů (Koloseum, 1. 11., výtky operátora)

**Skladba**
- Než se začne skládat, napiš ke každému panelu otázku čtenáře, na kterou hlavní obraz neodpoví (`otazka`). Když je odpověď „totéž zblízka“, panel na stránku nepatří. Co jde říct přímo na hlavním obraze (kdo kde seděl), patří tam: číslované značky a legenda, ne další řez.
- Téma je víc než objekt. U stavby i to, co se v ní dělo a kdo v ní byl: Koloseum bez gladiátorů „nedává smysl“.
- U osoby a zvířete má každá skladba panel s jejich podobou (portrét, celé zvíře). Hlavní obraz určuje myšlenka skladby, může to být stroj nebo mapa.

**Odkud obraz vznikne**
- Stavby a stroje: model z dílů v Blenderu.
- Slavné volné dílo: originál, celé. Generátor z něj dělá „rádoby kopii“. Výřez, který je skoro stejně velký jako obraz vedle, nemá smysl.
- Lidé a zvířata: fotorealistický generátor. Tělo z kapslí v Blenderu je „komiks“, ani mramor to nezachrání.
- Série postav: každá jiné semínko, tělo a postoj, výbava podle pramene (`grafik_client.figures`). Stejné semínko dá šestkrát stejného člověka.
- Jedna věc v několika pozicích (ruka): stejná osoba a velikost, předloha `subject`, a anatomicky správně. Pravá ruka s palcem dolů ukazuje hřbet, ne dlaň.

**Výřez a stín**
- Postava s kovem jen na zeleném plátně (`zdroj.vyriznout`): na tmavém pozadí se kov ztrácí. Klíč je změřený na obrázku, ne odhadnutý.
- Stín se nevyrábí, bere se z originálu (`zdroj.stin`). Skvrna pod nohama je levitace, vržený stín jedním směrem nesedí na světlo.
- Výřez kontroluj ve zvětšení: zubaté okraje a sežraný kov na zmenšené stránce nejsou vidět.

**Text**
- Spor v pramenech a populární mýtus: verze vedle sebe, u každé kdo ji tvrdí, a rozdíl musí být vidět na první pohled. Dvě gesta se stejným významem čtenáři nic neřeknou. Verzi od operátora dohledej a uveď, jak je doložená.
- Zlatá a tučná jen pro názvy. Popisek pod obrazem je obyčejné písmo v barvě textu.
- Na barevné stránce popisky bez černého obrysu, jen měkký stín (`template: "ruda"`).
- Vodítko nesmí přeškrtnout text: bod vpravo od textu chce text zarovnaný doprava. Hlídá to `GET …/kontrola`.

## Plakát podle cizího vzoru (Tesla, axolotl, 1. 11., výtky operátora)

Postup a zdroje: [spike](spikes/2026-11-01-plakaty-osoba-zvire.md), skripty `scripts/plakaty/`.

**Postup**
- Nejdřív kopie, česky a s opravenými věcnými chybami vzoru. Vylepšení jen jako návrh, vlastní skladbu bez výběru operátor odmítl.
- Kopie jde přes 3D: zvíře a postava z modelu Hunyuan 3.1 Pro (placené, cena předem), stroje z Blenderu. FLUX s renderem jako `geometry` dá vzhled a drží tvar.
- FLUX si z `geometry` bere i barvy a povrch. Render má mít paletu a matnost cíle: červená vlákna vrátil jako ostny, lesk jako gumu. Kameru změř na vzoru, dlouhé ohnisko hlavu zmenšilo.
- Výřez vzoru jako `subject` přenese vzhled zvířete, ne u věcí, které má vzor špatně (tři věže).
- Výřez na stránce vypadá nalepeně. Vlož ho do stránky a projeď jedním průchodem FLUX přes celou scénu, zvíře pak sedí v akvarelu a rostlinách. Text zůstává vektorový.
- FLUX přidává díly (trubka, ústí tunelu). Každý výsledek prohlédni v plném rozlišení.

**Vzhled**
- Jednotný styl neznamená jeden tón. „Mít všechno zatažené do jednoho tónu“ plakát zploští: světlý papír, tmavé stíny, barevné akcenty, klidně jeden tmavý panel, kde něco svítí. Sépii vzoru nepřebírej mechanicky.
- Hustotu vzoru taky ne. Text nemusí být natěsnaný, světlo a prostor mají význam, cílem je vyvážení příjemné na pohled.
- Ilustrace vysvětluje, jak věc funguje („Ilustraci vodní elektrárny nechápu“): řez, popisky, šipky toku. Pěkný vodopád s fotkou haly nevysvětlí nic.
- Stejný obsah dvakrát nepatří na stránku (fotka věže vedle modelu věže).

**Před odesláním**
- Plný náhled vedle vzoru, a pak výřezy v plné velikosti. Postava se kreslí přes panely: u plakátu s postavou zavolej `sazba.text_over` a při nálezu nic neukládej („Proč jde text přes Teslův obličej“). Viz `scripts/plakaty/tesla_kopie.py`.
- Do Knihovny až po přijetí, přijatý soubor beze změny: `python scripts/plakaty/sazba.py nahraj PAGE.png "Název"` (`--bez-ai` u čistého renderu). `--knihovna` stránku nejdřív složí znovu. Další verze je nová položka s vlastním názvem, soubory se nepřepisují.
- `write_poster` vypíše `SAZBA:`, když je text přes text, mimo stránku nebo když dva popisky čtou jako jedna věta. Obrazy tahle kontrola nevidí: popisek vedle kostí nebo modelu hlídej přes `text_over(…, margin=30)` (`scripts/plakaty/velsen_studna_stranka.py`) a přes celou stránku se podívej i po každém přeskupení.

## Scény k jednomu nálezu (Velsen, 2. 11.)

- Stejná věc vypadá na všech grafikách k článku stejně: ústí studny ve scéně má tvar jako na přijatém řezu. Zadání generátoru piš až po pohledu na přijatou grafiku a pramen.
- Tvar věci popiš fyzicky a řekni, co to není („úlomek s čerstvým lomem, ne celý kámen“). Postavám dej práci rukama, ne gesto.

## Řez podle přesné předlohy (Velsen, 2. 11., výtky operátora)

- Předloha s měřítkem se měří v pixelech, rozměry z textu nestačí. Render polož přes ni, teprve pak stavěj stránku (`scripts/plakaty/velsen_srovnani.py`). Přečti i perspektivu: prohnuté okraje prozradí, odkud se kreslíř díval.
- Hlavní obraz má celou výšku stránky a je na ní jednou. Zvětšenina čitelné věci nic neřekne.
- Popisky: nadpis a nejvýš jeden řádek, zalomení ručně, nad 60 px od obrazu. Co se nevejde, patří do patičky nebo pryč.
- Kosti a jiné přesné tvary dlouhým objektivem. Široký objektiv zblízka pánev zdeformoval tak, že vypadala jako špatný model. Podezřelý model nejdřív rovně vedle skenu.
- Jedna věc se všemi nálezy je čitelnější než dva pohledy. Nález na odvrácené straně kresli průsvitně přes kost a v patičce to řekni.

## Měřitelné kontroly (editor, sekce Kontrola)

| Kontrola | Práh | Vzor | Kvinquerema před úpravou | Kvinquerema po úpravě |
|---|---|---|---|---|
| délka vodítka, medián | ≤ 6 % šířky | 3,5 % | 10,4 % | 4,2 % |
| nejdelší vodítko | ≤ 12 % šířky | 10,5 % | 17,7 % | 5,8 % |
| vodítka svislá/vodorovná nebo lomená | většina | 62 % | 0 % | 100 % |
| křížení vodítek | 0 | 0 | 0 | 0 |
| písmo popisku (název / popis) při šířce 1280 | ≥ 15 / 13 px | 16 / 14 | 13 / 11,5 | 16 / 14 |
| prázdná plocha (dál než 12 px od čehokoli) | orientačně ≤ 30 % | 20 % | 52 % | 39 % |

Řádek o písmu je z 23. 10. a platí jen pro počítač. Od 2. 11. platí práh z oddílu Web a mobil, kontrola v Engine jiný nepoužívá.

Měření: `scratchpad` skript `measure.py` z 23. 10. (vodítka vzoru odečtena od oka ±10 px; naše hodnoty přesně z dokumentu infografiky). Prázdnou plochu editor neměří (potřebuje pixely obrazu); řeší ji rozvržení „Lišta přes obraz“.

Po úpravě (export `20261023-141248.png`, rozvržení „Lišta přes obraz“, 1920×1080): vodítka a písmo splňují prahy. Prázdná plocha 39 % je dána obrazem (loď leží diagonálně na jednolitém pozadí), ne rozvržením; lišta i výřez už žádný prázdný pás nepřidávají. Lišta podkládá jen text (do ~70 % šířky), dál prosvítá obraz, aby nezakryla příď a kloun.

Operátor 23. 10. večer k verzi s lištou: řez ve „debilním boxu“ a natlačená fakta dole. Opraveno: výřez bez rámečku s vinětou, popisky řezu na vodítkách, nadpis vlevo nahoře, fakta jako krátké dvojice hodnota + slovo v jednom řádku (export `20261023-200046.png`). Vzor se nekopíruje: neber jeho rozvržení, ber z něj princip.
Druhá oprava týž večer: okraje řezu nerozmazávat, ale vyříznout pozadí i vodu (`scratchpad rez2/cut.py`: flood fill od okraje); fakta pod sebou, zarovnaná na prapor (export `20261023-200812.png`).
