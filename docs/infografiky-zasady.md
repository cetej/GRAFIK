# Zásady infografik

Operátor 2026-10-23: nejde o kopírování vzoru, ale o pochopení čistého grafického stylu, rovnováhy, informační hodnoty a čtenářského zážitku. Špatně je nesoulad, přeplácanost, stísněnost, rozháraný styl a špatné poměry, kdy čtenář neví, na co kouká. Vzor pro porovnání: „Anatomie langskipu“ (vložen 22. 10.; generovaný AI, takže jen pro kompozici a typografii, ne pro obsah).

## Čtyři zásady

1. **Čistý styl.** Jedna písmová rodina ve dvou řezech: tučný řez akcentovou barvou pro názvy a klíče, obyčejný řez světlou barvou pro vysvětlení a hodnoty. Kontrast vzniká tloušťkou a barvou, ne střídáním písem. V editoru: Bahnschrift, zúžený řez (je ve Windows, takže ho má náhled i export přes Playwright).
2. **Rovnováha.** Obraz, popisky a fakta tvoří jeden celek. Žádné prázdné pásy. Nadpis a podtitulek tam, kde má obraz volné místo (u kvinqueremy vlevo nahoře). Krátká fakta dole vlevo, každé na vlastním řádku, zarovnaná na prapor; podklad jen za nimi, ne pruh přes celý obraz. Doplňkový výřez (řez, detail) leží volně na obraze bez rámečku a panelu: obrázek vyříznutý s průhledným pozadím a ostrými okraji (nerozmazávat), popisky v něm na vodítkách jako u hlavního obrazu.
3. **Informační hodnota.** Každý popisek odpovídá na otázku, kterou si čtenář u té části položí. Každý výřez (řez, detail) musí ukázat něco, co hlavní obraz neukáže. Řez bokem lodi, který jen opakuje příčný řez, informační hodnotu nemá. Co nemá doklad, do obrazu nepatří (věž na lodi z 1. punské války).
4. **Čtenářský zážitek.** Popisek leží u věci, kterou popisuje. Vodítko je krátké, raději svislé nebo vodorovné (jednou zalomené), nekříží jiná vodítka a nevede přes to důležité. Písmo popisku čitelné na pozadí.

Úsudek o tom, co stojí za popisek a zda celek působí vyváženě, zůstává na člověku. Číselné kontroly jen upozorní na rozháranost.

## Stránka z víc obrazů (Koloseum, 1. 11., výtky operátora)

**Skladba**
- Než se začne skládat, napiš ke každému panelu otázku čtenáře, na kterou hlavní obraz neodpoví (`otazka`). Když je odpověď „totéž zblízka“, panel na stránku nepatří. Co jde říct přímo na hlavním obraze (kdo kde seděl), patří tam: číslované značky a legenda, ne další řez.
- Téma je víc než objekt. U stavby i to, co se v ní dělo a kdo v ní byl: Koloseum bez gladiátorů „nedává smysl“.

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
- Plný náhled vedle vzoru, a pak výřezy v plné velikosti. Postava se kreslí přes panely a kolizi s textem žádná kontrola nehledá („Proč jde text přes Teslův obličej“).
- Do Knihovny až po přijetí. Další verze je nová položka s vlastním názvem, soubory se nepřepisují.

## Měřitelné kontroly (editor, sekce Kontrola)

| Kontrola | Práh | Vzor | Kvinquerema před úpravou | Kvinquerema po úpravě |
|---|---|---|---|---|
| délka vodítka, medián | ≤ 6 % šířky | 3,5 % | 10,4 % | 4,2 % |
| nejdelší vodítko | ≤ 12 % šířky | 10,5 % | 17,7 % | 5,8 % |
| vodítka svislá/vodorovná nebo lomená | většina | 62 % | 0 % | 100 % |
| křížení vodítek | 0 | 0 | 0 | 0 |
| písmo popisku (název / popis) při šířce 1280 | ≥ 15 / 13 px | 16 / 14 | 13 / 11,5 | 16 / 14 |
| prázdná plocha (dál než 12 px od čehokoli) | orientačně ≤ 30 % | 20 % | 52 % | 39 % |

Měření: `scratchpad` skript `measure.py` z 23. 10. (vodítka vzoru odečtena od oka ±10 px; naše hodnoty přesně z dokumentu infografiky). Prázdnou plochu editor neměří (potřebuje pixely obrazu); řeší ji rozvržení „Lišta přes obraz“.

Po úpravě (export `20261023-141248.png`, rozvržení „Lišta přes obraz“, 1920×1080): vodítka a písmo splňují prahy. Prázdná plocha 39 % je dána obrazem (loď leží diagonálně na jednolitém pozadí), ne rozvržením; lišta i výřez už žádný prázdný pás nepřidávají. Lišta podkládá jen text (do ~70 % šířky), dál prosvítá obraz, aby nezakryla příď a kloun.

Operátor 23. 10. večer k verzi s lištou: řez ve „debilním boxu“ a natlačená fakta dole. Opraveno: výřez bez rámečku s vinětou, popisky řezu na vodítkách, nadpis vlevo nahoře, fakta jako krátké dvojice hodnota + slovo v jednom řádku (export `20261023-200046.png`). Vzor se nekopíruje: neber jeho rozvržení, ber z něj princip.
Druhá oprava týž večer: okraje řezu nerozmazávat, ale vyříznout pozadí i vodu (`scratchpad rez2/cut.py`: flood fill od okraje); fakta pod sebou, zarovnaná na prapor (export `20261023-200812.png`).
