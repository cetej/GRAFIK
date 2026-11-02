# Spike 2026-11-02: volná rešerše pro osobu a zvíře

Plán [infografika z tématu](../plans/2026-11-01-infografika-z-tematu.md), oddíl 4a. Otázka: dá volná rešerše osobě a zvířeti aspoň tolik, co stavbám, aby se plakát typu Tesla nebo axolotl dal začít z Průvodce?

Závěr: ano. Tesla 28 z 35 údajů ruční rešerše (dřív 3), axolotl 34 ze 44 (dřív 4), 0 USD. Portrét i mapa výskytu jsou nabídnuté s autorem a licencí. Stavby dávají nad stejnými daty stejná fakta. Rešerše neříká, co je pravda: ukáže rozpor, jen když se volné zdroje liší, a chybu společnou všem volným zdrojům nepozná.

## Před a po

Měřítko je `scripts/research_kontrola.py`: 35 údajů z [ruční rešerše Tesly](2026-11-01-plakaty-fakta-tesla.md) a 44 z [ruční rešerše axolotla](2026-11-01-plakaty-fakta-axolotl.md). Údaj je nalezený, když ho jeden fakt dossieru říká v tvrzení nebo citaci a má URL. „Strop“ je počet údajů, které vůbec stojí na stažených stránkách.

| Dossier | Fakta | Rozpory | Obrázky | Z ruční rešerše | Strop |
|---|---|---|---|---|---|
| `nikola-tesla-v1` (před) | 9 | 0 | 21 | **3 z 35** | 31 z 35 |
| Nikola Tesla po změně | 120 | 5 | 26 | **28 z 35** | 33 z 35 |
| `axolotl-v1` (před) | 4 | 1 | 11 | **4 ze 44** | 39 ze 44 |
| axolotl po změně | 116 | 2 | 24 | **34 ze 44** | 40 ze 44 |

Měřítko jsem po prvním běhu opravil: vzory rozlišovaly velikost písmen, takže „Three pairs“ nesedělo na „three“. Teď se porovnává bez ohledu na velikost, před i po stejně, proto axolotl-v1 vyšel 4 místo původních 3.

Co chybí a proč:

- **Tesla, 7 údajů:** patenty 1. 5. 1888, Buffalo 1896, dvojitá expozice, stržení věže 1917, mezní vrstva, rozsudek Marconi 1943, vzdání se poplatků. Pět z nich na stránkách stojí, ale nevešly se do limitu vět. Dvě na žádné načtené stránce nejsou.
- **Axolotl, 10 údajů:** hmotnost 60 až 110 g, nadmořská výška 2 240 m a 100 až 300 vajec jsou z IUCN a ADW, tedy mimo volné zdroje. Chinampy, von Chauvin, Stock Center, divoký typ, leucistická forma, albín a 14 párů chromozomů na stránce jsou, nevešly se.

Limit je záměrný: 120 faktů na dossier, jinak by krok Návrhy platil za balast. Víc se vejde, když se limit zvedne, cena Návrhů roste zhruba o 0,0001 USD na fakt (odhad z délky řádku a ceníku, neměřeno).

## Co se změnilo

```
téma → Wikidata: P31 = člověk → osoba
                 P31 = taxon  → zvíře      vlastní slovníky a výběr v research_druhy.py
                 jinak        → věc        původní kód beze změny
```

- **Fakta z Wikidaty:** osoba narození a úmrtí s přesností na den, místa, občanství, povolání, vzdělání, ocenění. Zvíře stav ohrožení, areál, vědecké jméno, délka a hmotnost včetně palců a uncí.
- **Výběr vět:** po kolech přes oddíly hesla, z každého nejlepší, pak druhá nejlepší. Oddíly rozdělili redaktoři, tak žádná část života nebo biologie nezmizí. U stavby zůstal výběr podle slov o stavbě.
- **Podobné stránky:** odkazy „Hlavní článek“ v hesle, seznam patentů, podobná hesla. Stránka o jiném člověku se nebere, zvíře musí mít v úvodu přírodu (Axolotl je i šifrovací protokol).
- **Čísla:** u člověka je celek jen jeho výška, ostatní míry patří věcem kolem něj. U zvířete díly těla, mládě, délka života, vejce. Stopy se berou z metrů v závorce.
- **Obrázky:** portrét a mapa už nejsou odpad, hlavní obrázek a mapa z Wikidaty jdou první, mapa smí být SVG. Autor „NeznámýUnknown author“ je teď „autor neznámý“, adresa místo autora se neukáže.
- **Sketchfab:** u osoby se nevolá, u zvířete jen věcný model (sken, kostra, anatomie). Z 24 modelů axolotla nezbyl žádný, všechny jsou kreslené. U irbise zbyla jedna lebka.

## Rozpory zůstávají vidět

| Tvrzení v dossieru | Zdroje a jejich hodnoty | Co říká ruční rešerše |
|---|---|---|
| Patent US 1,061,206 (Turbine): 21. 10. 1909 nebo 21. 10. 1913 | seznam patentů 1909, Tesla turbine 1913 | oboje špatně, uděleno 6. 5. 1913 |
| Patent s datem 25. 4. 1891: v seznamu patentů toto datum není. Stojí vedle US 454,622 z 23. 6. 1891 | Tesla coil, History of the Tesla coil, seznam patentů, World Wireless System | 25. 4. je podání, uděleno 23. 6. 1891 |
| Patent US 613,809: 1. 7. 1898 nebo 8. 11. 1898 | seznam patentů 1. 7., World Wireless System 8. 11. | uděleno 8. 11. 1898 |
| Patent s datem 2. 9. 1897: v seznamu patentů toto datum není. Stojí vedle US 645,576 a US 649,621 | History of the Tesla coil, seznam, World Wireless System | 2. 9. 1897 je podání |
| Počet 278 až 300 patentů | en 278 a 300, cs 300, de a it 280 | 278 ve 26 zemích, Wikipedie „kolem 300“ |
| axolotl: délka 0,15 až 0,46 m | Wikidata 18 palců, en 15 až 45 cm, de 23 až 28 cm | 15 až 45 cm |
| axolotl: délka života 10 až 25 let | en 10 až 15 v přírodě, de do 20, cs do 25 v zajetí | délka v přírodě nedoložená |

Hodnota se neprůměruje, každý zdroj nese svou. Datum nejde spočítat jako rozpětí, proto „nebo“. Správnou hodnotu kód nevybírá, u turbíny by ani neuměl: obě hodnoty jsou špatně. Rozhodl by Google Patents, ten mezi zdroji není.

**Co rešerše nepozná.** Ze šesti špatných dat v seznamu patentů jsou vidět dvě, u ostatních nemá s čím porovnat. Tyto věci dossier drží jako fakt z jednoho zdroje, i když je ruční rešerše vyvrátila nebo nedoložila:

- „The axolotl is unusual in that it has a lack of the thyroid-stimulating hormone“ (Voss 2019: zjednodušení).
- „Surveys conducted in 1998, 2003, and 2008“ (IUCN má 2004).
- „a shipment of 34 adult axolotls“ (zdroje se liší 33 a 34, volný je jen jeden).
- Wikidata: místo narození Tesly „Nikola Tesla Memorial Center“, občanství Maďarsko a Chorvatsko. Přesně to tam stojí, Smiljan je ve větách.

Před zveřejněním proto dál čte člověk a citace jsou u každého faktu.

## Kontrola čísel a vět

Všechny údaje s číslem nebo datem jsem prošel proti citaci. Konečný kód: **chyb přiřazení 0** u Tesly (11 údajů) i axolotla (4 údaje). Cestou se ukázaly a jsou opravené:

| Co vyšlo | Proč | Oprava |
|---|---|---|
| Nikola Tesla: délka 0,18 až 1,1 m | ponorka a oscilátor přiřazené člověku | u člověka je celek jen výška |
| Nikola Tesla: výška 1,88 až 20,73 m, šířka 590 m | věž a vzdálenost | totéž |
| irbis: výška 100 až 6 000 m | nadmořská výška | věta o výšce krajiny čísla nedává |
| irbis: hmotnost 1,5 až 76 kg | kořist a porce masa | totéž pro potravu |
| Ocas: délka 0,15 až 1,05 m | ocas mláděte a dospělce | věta o mláděti patří mláděti |
| Počet 112 až 300 patentů | USA a svět | „v USA“ je jiný údaj |
| Věty o Pierrovi Curiem u Marie Curie | stejné příjmení | životopis někoho jiného se nebere |
| „Tesla coil“ v každé větě technického hesla | jméno cívky není zmínka o člověku | název stránky se ze zmínky vynechá |

Náhodné vzorky vět (seed 20261102), věty jsou doslovné citace, takže chyba znamená „mluví o něčem jiném“ nebo useknutá věta:

| Dossier | Vzorek | Chyb | Jaká |
|---|---|---|---|
| Tesla | 20 | 0 | |
| axolotl | 20 | 1, opraveno | „The Laboratorio de Restauracion Ecologica (transl.“ useknuté na zkratce; věta s nezavřenou závorkou se teď nebere. Další vzorek stejným seedem 0 z 20 |
| Marie Curie, mimo vzorek | 10 | 1, opraveno 1 | „In 1919 she took a course with Marie Curie“ o někom jiném opraveno; zůstává „Mărăcineanu wrote… Irene Joliot Curie“: podobná stránka a stejné příjmení |
| irbis, mimo vzorek | 10 | 0 | |

Vzorky nejsou nezávislé: po opravě jsem měřil znovu. Slabina se stejným příjmením zůstává a kód na ni nemá pravidlo.

## Stavby se nezhoršily

Starý kód (`origin/master`) a nový nad stejnými uloženými odpověďmi API:

| Téma | Fakta staré / nové | Obrázky staré / nové | Rozdíl |
|---|---|---|---|
| Pantheon, Řím | 84 / 84 | 33 / 33 | žádný |
| Koloseum | 44 / 44 | 32 / 32 | jen autor „Unknown authorUnknown author“ → „autor neznámý“ |
| Oppidum Závist | 6 / 6 | 8 / 8 | žádný |

Fakta jsou položka po položce stejná.

## Mimo měřený vzorek

| Téma | Druh | Fakta | Obrázky | Co je tam |
|---|---|---|---|---|
| Marie Curie | osoba | 99 | 24 | narození a úmrtí shoda ve 4 jazycích a Wikidatě, portréty s autorem, Nobelova cena, pomníky |
| irbis | zvíře | 114 | 19 | 2 mapy výskytu, 1 model lebky, CITES, hrozby; barevné formy chybí a je to v otázkách bez odpovědi |

Na těchto dvou tématech se ukázalo víc chyb než na Teslovi a axolotlovi dohromady (tabulka výše). Slovníky jsou ladění na čtyřech tématech. Rostlina jde cestou zvířete a neověřoval jsem ji.

## Co rešerše neumí

- **Krok Návrhy:** prompt v `engine/proposals.py` v poli `predloha` vyjmenovává role staveb. Pole se nikde dál nepoužívá a nové role nic nerozbijí, ale návrh pro osobu může vrátit `null`. Druh tématu v celém řetězci je samostatná práce, ne tahle změna.
- **Primární zdroje:** IUCN, PMC a Google Patents, ze kterých ruční rešerše čerpala hlavně, mezi volnými zdroji nejsou.
- **Věty nejsou přeložené**, jako u staveb.

## Kritérium, stanovené před změnou kódu

Zapsané v prvním commitu větve, před změnou kódu. Výchozí stav tehdy: Tesla 3 z 35, axolotl 3 ze 44.

Hotovo je, když:

1. **Pokrytí:** Tesla aspoň 24 z 35, axolotl aspoň 30 ze 44 (zhruba 70 %), při nejvýš 120 faktech na dossier, aby krok Návrhy neplatil za balast.
2. **Chyby:** každý údaj s číslem projdu proti citaci a vypíšu. Z náhodného vzorku 20 vět na dossier (seed 20261102) je nejvýš 2 špatně. Špatně = fakt neříká, co zdroj, nebo mluví o něčem jiném než o tématu. Správnost samotného zdroje to neměří, ta se vypíše zvlášť.
3. **Stavby se nezhorší:** nad stejnými odpověďmi API dá starý a nový kód na Pantheonu a Koloseu stejná fakta a stejné obrázky.
4. **Obrázky:** Tesla má portrét v roli `portret`, axolotl mapu výskytu v roli `mapa`, obojí s autorem a licencí. Žádný kreslený model ze Sketchfabu.
5. **Rozpory:** datum patentu na turbínu a datum u US 454,622 jsou v dossieru vidět jako rozpor, s hodnotou každého zdroje zvlášť, nic se neprůměruje.
6. **Mimo měřený vzorek:** jedna další osoba a jedno další zvíře, na kterých jsem kód neladil, dají použitelný dossier (počty a 10 faktů proti zdroji).
7. Testy projdou, změna je sloučená a ověřená v opravdovém Studiu.
