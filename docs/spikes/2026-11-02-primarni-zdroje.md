# Spike 2026-11-02: primární zdroje ve volné rešerši

Navazuje na [rešerši pro osobu a zvíře](2026-11-02-resers-osoba-zvire.md). Otázka: vyplatí se do volné rešerše přidat Google Patents pro patenty osoby a IUCN nebo články z PMC pro zvíře? Jen bez klíče a bez obcházení ochran, 0 USD.

Závěr:

| Zdroj | Verdikt | Proč |
|---|---|---|
| Google Patents | **v kódu** | 7 ze 7 známých chyb v datech s URL patentu, 111 ze 111 dat souhlasí s ruční rešerší |
| Články z PMC | ne | výběr naslepo vrací metody a jiné druhy (15 z 20 vět špatně) a neopravil žádnou známou chybu; články, které by pomohly, kód sám nenajde nebo nejsou volně k mání |
| IUCN | ne | API chce klíč, statická stránka dá 4 ze 44 údajů a podmínky zakazují komerční použití bez svolení |

## Google Patents: před a po

```
věta na Wikipedii      seznam na Wikipedii      Google Patents
21. 10. 1913           21. 10. 1909             6. 5. 1913  uděleno
                                                17. 1. 1911 podání
                                                21. 10. 1909 první přihláška

dossier: Patent US 1,061,206 (Turbine): uděleno 6. 5. 1913 podle Google Patents.
         Jiné zdroje: 21. 10. 1909 (první přihláška), 21. 10. 1913      stav: rozpor
```

| | Před (`nikola-tesla-v2`) | Po |
|---|---|---|
| Z ruční rešerše | 28 z 35 | **29 z 35** |
| Známé chyby v datech s datem z originálu | 0 ze 7 | **7 ze 7** |
| Rozpory | 5 | 9 |
| Fakta | 120 | 120, čtyři nejslabší věty ustoupily ověřeným patentům |
| Souhrn po letech | 1888: 14, 1889: 12, 1900: 4, 1901: 6, 1909: 2, 1913: 0 | 1888: 13, 1889: 13, 1900: 3, 1901: 7, 1913: 2, tedy přesně tabulka ruční rešerše |
| Čas navíc | | 111 dotazů po 1 s pauze, měřeno níž |

Měřítko: `python scripts/research_kontrola.py tesla <dossier.json>`, nově vypisuje i známé chyby.

Vyřešilo se i to, co dřív zůstalo jen jako poznámka bez čísla patentu: 25. 4. 1891 patří k US 454,622 a 2. 9. 1897 je podání US 645,576. Přibyl jeden údaj z měřítka, sedm patentů udělených 1. 5. 1888 (vedle sedmi z 16. 8. 1898).

**Podmínky a technika.** `robots.txt` má `Allow: /patent/`, ostatní cesty zakazuje. Podmínky Googlu zakazují automatický přístup jen v rozporu se strojově čitelnými pokyny webu. Klíč není třeba. Čte se jen prvních 64 kB stránky (celá má až 8 MB), jeden dotaz za sekundu. Oficiální API to není: když Google změní mikrodata, patent nedá datum a dossier řekne „ověřil jen 0 ze 111“, špatnou hodnotu to nevyrobí.

**Co se ukázalo až na datech:**

- U 29 ze 111 Teslových patentů mikrodata vynálezce neuvádějí a názvy jsou z OCR („Nikola tksla“, „Best available cop“). Patent ze seznamu osoby proto vynálezce mít nemusí, patent jen zmíněný ve větě ano. Název se bere ze seznamu, je-li.
- U 73 ze 111 chybí datum podání. US 454,622 ho nemá, proto se k němu věta z 25. 4. 1891 přiřadí přes číslo patentu ve stejném datu, ne přes podání.
- Heslo Tesla coil cituje cizí patenty (Armstrong, Stone). Z podobné stránky se bere číslo jen ve větě se jménem, jinak by vzniklo 11 zbytečných otázek a otázky jdou do placeného doplnění.

**Mimo vzorek:**

| Téma | Volání Google Patents | Výsledek |
|---|---|---|
| Alexander Graham Bell | 1 | US 174,465: 7. 3. 1876, stav `shoda` s Wikipedií |
| Hedy Lamarr | 1 | US 2,292,387 je na jméno Markey, kód ho nepřiřadil a ptá se, jestli patří k tématu |
| Thomas Edison | 5 | US 223,898 ověřený; US 90,646 bez vynálezce nepřiřazený, 3 čísla bez dat; otázka to říká |
| Marie Curie | 0 | fakta položka po položce stejná jako starý kód |

**Co to neřeší:** seznam Edisonových patentů má na Wikipedii jiný tvar, takže se ověří jen čísla z vět. Jméno se porovnává jen podle příjmení; nositel stejného příjmení by prošel, kdyby ho věta na stránce osoby jmenovala. Ostatní chyby z ruční rešerše (věk na desce, datum elektrárny Adams, pověst o rozsudku) patenty neopraví. Rozpor 278 až 300 patentů zůstává.

**Stavby:** starý kód (`origin/master`) a nový nad stejnými uloženými odpověďmi API: Pantheon 84 faktů a 33 obrázků, Koloseum 44 a 32, položka po položce stejné, stejné i otázky a zdroje. Axolotl beze změny, 34 ze 44.

## Články z PMC: proč ne

Strojově jdou číst přes API Europe PMC bez klíče (v dokumentaci jsem klíč ani limit nenašel). Podmínky PMC zakazují automatické stahování z hlavního webu, takže jiná cesta není.

| Výběr článků pro axolotla | Stojí v textu | Projde výběrem vět | Z 10 chybějících | Vzorek vět špatně |
|---|---|---|---|---|
| Nejcitovanější s přírodou v abstraktu, plný text (kód by to uměl) | 23 ze 44 | 11 ze 44 | 3 | 7 z 12 |
| Jen abstrakt a úvod, druh v názvu (kód by to uměl) | 5 ze 44 | 3 ze 44 | 0 | **15 z 20** |
| Články, které přečetla ruční rešerše (kód je nezná) | 33 ze 44 | 16 ze 44 | 5 | neměřeno |

Špatně znamená, že věta mluví o studii, metodě nebo jiném druhu: „Here we report unbiased single-cell RNA-sequencing…“, „the axolotl Ambystoma altamirani“. První dotaz vrátil i článek o lososovi. Nález „100 až 300 vajec“ v prvním řádku je falešný („One hundred eggs from a wildtype cross“), proto 3, ne 4. Vzorek v prvním řádku měl 12 vět, stejně je to přes limit.

Irbis dopadl lépe, ekologické články o něm mluví: 4 z 10 vět špatně, limit byl 1.

**Známé chyby.** V dossieru z nich skutečně stojí tři: TSH, průzkumy 1998/2003/2008 a 34 zvířat. Výběr naslepo neopravil žádnou, kritérium žádá 2 ze 6. Dvě by opravily články, které jsou volně ke stažení (TSH: PMC6473073, 33 zvířat: PMC10137446), ale kód na ně dotazem nenarazí, našel je člověk. Průzkumy stojí v „A Tale of Two Axolotls“ (PMC7051018), ten není open access a Europe PMC i E-utilities plný text odmítají („does not allow downloading of the full text in XML form“).

První řádek tabulky kritérium 3 z 10 těsně splnil. Nestačí to: podmínky platí zároveň a 7 z 12 vět je špatně při limitu 2 z 20.

**Místo a licence.** Axolotl má 116 faktů, 22 vět z článků by vytlačilo 18 vět z Wikipedie. Licence jsou smíšené (`cc by`, `cc by-nc-nd`), což pro ziskového vydavatele není jedno.

## IUCN: proč ne

| Cesta | Výsledek |
|---|---|
| API `api.iucnredlist.org` | 403 bez tokenu; token je mimo zadání „bez klíče“ |
| Statická stránka druhu | 200, ale jen kategorie a kritéria (`Critically Endangered A2abce`), text hodnocení v HTML není: 4 ze 44 údajů, 0 z 10 chybějících |
| `robots.txt` | blokuje jmenované AI crawlery, `ai-train=no`; WebFetch dostal 403 |
| Podmínky, § 3 a § 4 | komerční použití včetně použití, které „pomáhá činnosti ziskové entity“, jen s písemným svolením; přeposílání dat zakázané. Výjimka: kategorie ohrožení bez omezení |

Kategorii už dává Wikidata (P141), nic by nepřibylo. **Pozor pro plakát:** ruční rešerše axolotla bere z IUCN i počet dospělců a rozsah výskytu. Pokud plakát vyjde u ziskového vydavatele, podle § 3 to chce svolení IUCN nebo jiný zdroj. Rozhoduje operátor, kód to neřeší.

## Vedle zadání

- **AmphibiaWeb** přesměruje na `/cgi/auth/challenge`, kontrolu „jste člověk“. Neobcházel jsem ji.
- **Animal Diversity Web** je sekundární zdroj, proto mimo toto zadání. Změřil jsem ho jen jednou na axolotlovi: dá 5 z 10 chybějících (hmotnost 60 až 110 g, 100 až 300 vajec, nadmořská výška, divoký typ, albín) a druhou hodnotu k 34 zvířatům (33). `robots.txt` ho dovoluje s pauzou 8 s. Irbis pod `Panthera_uncia` nemá stránku (404), pokrytí ani licenci jsem neověřoval.

## Kritérium, stanovené před změnou kódu

Výchozí stav změřený `scripts/research_kontrola.py` nad `nikola-tesla-v2` a `axolotl-v2`: Tesla 28 z 35, axolotl 34 ze 44.

Známé chyby, které má zdroj vyřešit:

- **Tesla, 7 patentů** (ruční rešerše, oddíl 0): US 396,121; 685,012; 1,061,142; 1,061,206 (i věta v hesle Tesla turbine); 613,809; 655,838; 454,622 (věta v hesle Tesla coil).
- **Axolotl, 6 tvrzení** (ruční rešerše, oddíl 0, a předchozí spike): chybějící TSH, kostra z chrupavky, regenerace čočky, průzkumy 1998/2003/2008, 34 nebo 33 zvířat, kritéria IUCN.

Zdroj se přidá, když splní všechno, co se ho týká:

1. **Podmínky a technika:** strojové čtení bez klíče, bez obcházení kontroly, robots.txt a podmínky ho dovolují. Co neprojde, se nepřidává bez ohledu na přínos.
2. **Google Patents:**
   - všech 7 známých chyb má v dossieru správné datum udělení s URL patentu a stav `rozpor` s hodnotou každého zdroje;
   - dat udělení ze 111 souhlasí s tabulkou v příloze ruční rešerše 111, tedy 0 chyb;
   - měřítko neklesne pod 28 z 35;
   - u osoby bez patentů 0 volání, výpadek zdroje dossier neshodí a dossier řekne, kolik patentů ověřil;
   - dossier Tesly se prodlouží nejvýš o 3 minuty.
3. **Zdroj pro zvíře (PMC přes povolenou službu, IUCN):**
   - přidá aspoň 3 z 10 chybějících údajů axolotla jako fakta s URL, nebo aspoň 2 ze 6 známých chyb dostanou v dossieru větu, která je opraví;
   - zároveň nejvýš 120 faktů, měřítko neklesne pod 34 ze 44, ze vzorku 20 vět nového zdroje (seed 20261102) nejvýš 2 špatně;
   - na dalším zvířeti, na kterém jsem neladil (irbis), je vzorek 10 vět nejvýš 1 špatně.
4. **Stavby beze změny:** starý a nový kód dají nad stejnými odpověďmi API na Pantheonu a Koloseu stejná fakta a stejné obrázky.
5. **Mimo vzorek:** dvě další osoby s patenty (Hedy Lamarr, Alexander Graham Bell) nedostanou cizí patent ani špatné datum, Marie Curie zůstane bez volání.
6. Testy projdou, změna je sloučená a ověřená na běžícím Engine.

Když zdroj nesplní, zapíšu sem změřený důvod a do kódu nejde.
