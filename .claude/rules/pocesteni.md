---
paths:
  - shared/ngm_shared/textlayer/**
  - engine/localize.py
  - studio/src/Localize.tsx
  - shared/tests/test_tisk.py
  - tests/test_pocesteni_realne.py
---

# Počeštění cizí mapy nebo infografiky

Zdroj: operátor 2026-11-01 po mapě irbisů (`docs/LEARNINGS.md` téhož dne). Kód: `textlayer/localize.py` (čtení, výběr cesty, kontroly), `tisk.py` (tištěná mapa), `pcraft.py` (reliéf, fotka), `engine/localize.py`.

**Výsledek musí vypadat jako originál, jen česky.** Hotovo znamená, že operátor výsledek může rovnou použít. Zbytek anglického písmene, díra v ploše nebo přerušená hranice je chyba, ne upozornění.

## Vyřešeno platí jen pro ověřený druh obrázku

Oprava z 30. 10. se ověřila na jediné mapě (Everest, reliéf, šířka 769 px, barevné popisky) a zapsala se jako vyřešená. Mapa irbisů (sken, šířka 3072 px, černé písmo přes barevný areál) pak šla stejnou cestou a dopadla špatně: pixelové prahy byly vyladěné na Everest a kontrola zbytků vracela natvrdo 0, takže chybu nikdo nehlásil.

| Druh obrázku | Cesta | Ověřeno na |
|---|---|---|
| stínovaný reliéf, barevné popisky | `pcraft` (PhotoCraft) | Everest, 2026-10-30 |
| tištěný sken, černé písmo | `tisk` | irbis, 2026-11-01 |
| plochá infografika | `cv2.inpaint` | T2, 2026-10-29 |

- Druh mimo tabulku je neověřený: ber výsledek jako pokus a řekni to operátorovi, i když kód doběhne bez varování.
- Po ověření nového druhu přidej řádek sem a případ do `tests/test_pocesteni_realne.py`. Stávající případy musí dál procházet.
- Tichá kontrola je chyba: hodnota, která se neměří, se nesmí vracet jako výsledek měření. Nulové varování nedokazuje, že je obrázek v pořádku.
- V hlášení operátorovi jmenuj, na čem to bylo ověřené, ne „počeštění funguje“.

## Co se nesmí stát

- V obrazu nezůstane kus původního písma a nezmizí nic než písmo: plocha, hranice, řeky, pobřeží, měřítko, značky.
- Mapa drží údaje originálu. Maže se jen text; areál ani hranice se neupravují.
- Značky (hvězdy a tečky měst, kóty, křížky vrcholů) stojí v `markers`. Bez nich mazání značku v pásu popisku sebere.
- Popisek psaný po křivce nebo přes mapu má `path`. Rámeček a úhel ho nepopíšou. Když česká křivka leží jinde než původní, smaže se po `erase_path`.
- Když je černá jen písmo (`tisk.only_ink`), maže se po pixelech písma. Štětec PhotoCraftu patří na reliéf a fotku.
- Prahy v pixelech se vztahují k šířce obrázku. Sken 3000 px má jiná čísla než mapa 800 px.

## Sazba

- Velikost podle významu: titulek největší, rovnocenné popisky stejně (`~/.claude/rules/grafika-texty.md`). Žádné masky a lemy.
- Styl originálu: svislé patkové názvy zůstanou svislé (Peele), šikmé šikmé (Bumstead), prostrkané prostrkané. `spaced`, `size_px`, `offset` opravují jednotlivý popisek.
- Popisek se nesrazí se značkou ani se sousedem. Kóta patří nad svůj křížek.
- Jednotky metrické. U měřítka přepočítat i číslo (500 mil = 805 km), protože dílky zůstávají z originálu.
- Název zvířete, rostliny nebo místa jako v článku (zde irbis horský, ne levhart sněžný). Překlad zkontroluj proti textu článku.

## Kontrola před odevzdáním

1. Prohlédni originál a výsledek vedle sebe v celku.
2. Prohlédni výřezy ve 100 %: titulek s měřítkem, každé místo, kde popisek křižuje hranici, a nejhustší oblast. V náhledu chybějící hranice není vidět.
3. Projdi `warnings` a každé „Po mazání zůstaly stopy“ ověř ve výřezu. Tmavá hranice v rámečku hlásí zbytek taky, takže varování je podnět k pohledu, ne verdikt.
4. Spočítej značky proti originálu.
5. Výsledek se nikdy nepřepisuje: nová kopie `mapa_cs_NN`, oprava překladů a křivek jde zdarma přes `texts`.

Nesplněný bod se řekne operátorovi. Mapa, která neprojde, se neodevzdává jako hotová.

## VectorCraft

- SVG musí v okně vypadat jako PNG. VectorCraft čte řez jen ze jména rodiny (`_svg_family`, `NatGeo Bumstead Heavy`) a nezná `dominant-baseline` (účaří počítá `SVG_BASELINE`). Text za koncem křivky zahodí, proto má křivka rezervu (`_path_svg`).
- Vrstvy: `<g id="Podklad">` a `<g id="Texty">`, podklad přímo v kopii (`localize.for_window`). Otevírá `POST /api/v2/jobs/<job>/images/0/vectorcraft`, ruční úprava se nepřepisuje (409, volba otevřít úpravu nebo novou kopii).
- Po změně sazby ověř export z VectorCraftu proti PNG, ne jen v prohlížeči.
