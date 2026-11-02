# Spike 2026-11-02: primární zdroje ve volné rešerši

Navazuje na [rešerši pro osobu a zvíře](2026-11-02-resers-osoba-zvire.md). Otázka: vyplatí se do volné rešerše přidat Google Patents pro patenty osoby a IUCN nebo články z PMC pro zvíře? Jen bez klíče a bez obcházení ochran, 0 USD.

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
