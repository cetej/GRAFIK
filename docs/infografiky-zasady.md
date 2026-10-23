# Zásady infografik

Operátor 2026-10-23: nejde o kopírování vzoru, ale o pochopení čistého grafického stylu, rovnováhy, informační hodnoty a čtenářského zážitku. Špatně je nesoulad, přeplácanost, stísněnost, rozháraný styl a špatné poměry, kdy čtenář neví, na co kouká. Vzor pro porovnání: „Anatomie langskipu“ (vložen 22. 10.; generovaný AI, takže jen pro kompozici a typografii, ne pro obsah).

## Čtyři zásady

1. **Čistý styl.** Jedna písmová rodina ve dvou řezech: tučný řez akcentovou barvou pro názvy a klíče, obyčejný řez světlou barvou pro vysvětlení a hodnoty. Kontrast vzniká tloušťkou a barvou, ne střídáním písem. V editoru: Bahnschrift, zúžený řez (je ve Windows, takže ho má náhled i export přes Playwright).
2. **Rovnováha.** Obraz, popisky a fakta tvoří jeden celek. Žádné prázdné pásy; fakta a nadpis v liště přes spodek obrazu, doplňkový výřez v rohu obrazu.
3. **Informační hodnota.** Každý popisek odpovídá na otázku, kterou si čtenář u té části položí. Každý výřez (řez, detail) musí ukázat něco, co hlavní obraz neukáže. Řez bokem lodi, který jen opakuje příčný řez, informační hodnotu nemá. Co nemá doklad, do obrazu nepatří (věž na lodi z 1. punské války).
4. **Čtenářský zážitek.** Popisek leží u věci, kterou popisuje. Vodítko je krátké, raději svislé nebo vodorovné (jednou zalomené), nekříží jiná vodítka a nevede přes to důležité. Písmo popisku čitelné na pozadí.

Úsudek o tom, co stojí za popisek a zda celek působí vyváženě, zůstává na člověku. Číselné kontroly jen upozorní na rozháranost.

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
