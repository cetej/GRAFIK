# Spike 2026-11-02: krok Návrhy podle druhu tématu

Plán [infografika z tématu](../plans/2026-11-01-infografika-z-tematu.md), oddíl 4a. Otázka: použije návrh pro osobu a zvíře role obrázků z dossieru, aniž by se zhoršily stavby?

Závěr: ano. Tesla a axolotl používají jen role, které dossier má, a žádný panel `rez` ani `pudorys`. Koloseum vyšlo stejně nebo lépe než běhy z 1. 11. Každý dossier běžel jednou a Sonnet dává pokaždé jiné návrhy, takže jde o vzorek, ne o důkaz. Předlohu zatím jen ukazuje Studio, generování obrazů ji začne číst v kroku 3f.

Druhé kolo přidalo zásadu, že každá skladba ukáže, o kom je. Portrét má teď 3 ze 3 návrhů Tesly, celé zvíře 3 ze 3 u axolotla podle obsahu.

## Co se změnilo

- `predloha` smí být jen role z řádku OBRÁZKY K DISPOZICI. Kód roli, kterou dossier nemá, zahodí a spočítá v `neznama_predloha`, stejně jako neznámé fakty.
- Prompt skládá `system_prompt(kind)` z obecných zásad, zásad druhu tématu (`KIND_RULES`) a odpovědi s druhy panelů (`PANEL_KINDS`). Dossier bez `entita.druh` jde jako `vec`. Věty o stavbách zůstaly doslova, přesunuly se jen do zásad pro `vec`.
- Studio píše u panelu „Předloha: Portrét“, předtím nebyla vidět nikde.
- Odhad kroku 0,04 → 0,057 USD, viz cena níže.

## Měřítko, zapsané před placeným během

| Kritérium | Hranice |
|---|---|
| Panely s předlohou z dossieru | aspoň 2 v každém návrhu |
| Stavba, podíl panelů s platnou předlohou | aspoň 50 % (běhy z 1. 11.: 6 z 10 a 6 ze 12) |
| Tesla a axolotl, panely `rez` a `pudorys` | 0 |
| Odkazy na fakta, která dossier nemá | 0 |
| Fakta a témata v každém návrhu | aspoň 6 faktů a 2 témata |

## Výsledek

Claude Sonnet 5.5, effort medium, každý dossier jednou, `scripts/navrhy_srovnani.py`. Tři čísla v buňce patří třem návrhům.

| | Tesla `nikola-tesla-v2` | axolotl `axolotl-v2` | Koloseum `koloseum-v1` | Koloseum 1. 11. řetězec / srovnání |
|---|---|---|---|---|
| Panely s předlohou z dossieru | 3, 2, 3 | 4, 3, 3 | 3, 2, 2 | 1, 3, 2 / 2, 2, 2 |
| Podíl panelů s předlohou | 8 z 16 | 10 z 16 | 7 ze 14 (50 %) | 6 z 10 / 6 ze 12 |
| Role mimo dossier | 0 | 0 | 0 | 1 / 1 (`material`) |
| Panely `rez`, `pudorys` | 0 | 0 | nesleduje se | nesleduje se |
| Vypadlá fakta | 0 | 0 | 0 | 0 / 0 |
| Fakta v návrhu | 19, 12, 15 | 25, 29, 23 | 16, 12, 12 | 6, 7, 6 / 14, 10, 7 |
| Témata v návrhu | 3, 3, 4 | 4, 6, 4 | 3, 2, 3 | 2, 1, 2 / 2, 2, 2 |

Stránky s náčrty a fakty: [Tesla](img/2026-11-02-navrhy-tesla.html), [axolotl](img/2026-11-02-navrhy-axolotl.html), [Koloseum](img/2026-11-02-navrhy-koloseum.html).

Použité role:

- **Tesla:** dílo 4, památka 2, portrét 1, místo 1.
- **Axolotl:** zvíře 2, detail 2, ilustrace 2, mapa 1, forma 1, vývoj 1, prostředí 1.
- **Koloseum:** průčelí 2, půdorys 2, řez 1, detail 1, interiér 1.

Běhy z 1. 11. vznikly ještě bez polí `otazka` a `obrazek`, proto srovnání není úplně čisté.

## Cena

| Dossier | Fakta | Vstup | Výstup | USD |
|---|---|---|---|---|
| Tesla | 120 | 10 550 | 3 398 | 0,0551 |
| axolotl | 116 | 9 109 | 3 452 | 0,0527 |
| Koloseum | 44 | 3 992 | 2 946 | 0,0374 |
| **Celkem** | | | | **0,1452** |

Operátor schválil 0,14 USD. Po Teslovi a axolotlovi bylo jasné, že Koloseum může celek překročit, proto jsem se zeptal znovu a schválil do 0,15 USD. Ceny jsou v `library/costs.jsonl`.

Starý odhad 0,04 USD vycházel z dossieru se 44 fakty. S rešerší z 2. 11. mají dossiery fakt až trojnásobně víc, takže Tesla překročila odhad o 38 %. Řetězec by se pak zastavil před kontrolou logiky, protože 0,0551 + 0,07 USD se nevejde do schválených 0,11 USD. Nový odhad 0,057 USD je podle největšího dossieru (11 000 a 3 500 tokenů), Koloseum vyšlo o 34 % levněji. Cena řetězce z tématu je teď 0,127 USD místo 0,11 USD.

## Druhé kolo: každá skladba ukáže, o kom je

První kolo mělo dvě vady, které měřítko nezachytilo. Portrét byl jen v jednom ze tří návrhů Tesly, hlavní obraz byl pokaždé stroj nebo věž. Pravidlo „hlavní obraz je celé zvíře“ dodržel jen první návrh axolotla, druhý začínal mapou a třetí bohem Xolotlem.

Operátor schválil doladění za 0,11 USD. Zásady pro osobu a zvíře teď žádají panel s podobou tématu v každé skladbě a hlavní obraz nechávají na myšlence skladby, u zvířete výslovně i mapu. Prompt pro stavby se nezměnil, proto Koloseum znovu neběželo.

Kritérium zapsané před během: panel s `predloha` `portret` ve 3 ze 3 návrhů Tesly a `zvire` ve 3 ze 3 u axolotla, ostatní hranice stejné jako v prvním kole.

| | Tesla 1. kolo | Tesla 2. kolo | axolotl 1. kolo | axolotl 2. kolo |
|---|---|---|---|---|
| Návrhy s panelem podoby | 1 ze 3 | **3 ze 3** | 2 ze 3 | **2 ze 3 podle role, 3 ze 3 podle obsahu** |
| Panely s předlohou z dossieru | 3, 2, 3 | 5, 4, 3 | 4, 3, 3 | 3, 2, 3 |
| Role mimo dossier, vypadlá fakta | 0, 0 | 0, 0 | 0, 0 | 0, 0 |
| Panely `rez`, `pudorys` | 0 | 0 | 0 | 0 |
| Fakta v návrhu | 19, 12, 15 | 23, 20, 15 | 25, 29, 23 | 29, 20, 27 |
| Témata v návrhu | 3, 3, 4 | 4, 4, 2 | 4, 6, 4 | 4, 2, 5 |
| Cena USD | 0,0551 | 0,0581 | 0,0527 | 0,0508 |

Druhé kolo stálo 0,1089 USD (vstup 10 583 a 9 152 tokenů, výstup 3 697 a 3 251), obě kola dohromady 0,2541 USD. Stránky: [Tesla](img/2026-11-02-navrhy-tesla-2.html), [axolotl](img/2026-11-02-navrhy-axolotl-2.html).

U axolotla kritérium podle role doslova neprošlo. Návrh „Regenerace pod lupou“ má jako hlavní obraz celé zvíře s dorůstající nohou, ale s předlohou `forma` místo `zvire`. Podle obsahu zvíře ukazuje, proto jsem prompt dál neměnil. Hlavní obraz je teď celé zvíře ve dvou návrzích a mapa v jednom, což zásada dovoluje.

Vedlejší účinky, oba z jediného běhu:

- Portrét stojí u Tesly ve všech třech návrzích na druhém místě a jeho popis opakuje zadání („z dossieru beze změny“). Skladby jsou si v tomhle bodě podobnější než v prvním kole.
- U axolotla zmizel kulturní návrh (Xolotl, bankovka). Jde spíš o rozptyl modelu než o zásadu, nedoložil jsem to.

## Co měřítko nezachytilo

- **Fakta jsem proti zdrojům neověřoval.** Návrhy jen odkazují na id z dossieru, text na stránku se bere z dossieru a čte ho člověk.
- **Řetězec ze Studia na Teslovi naostro neběžel.** Běžel skript se stejnou funkcí `proposals.propose`. Studio jsem ověřil nad uloženým během Kolosea.
- **Rostlina jde cestou zvířete,** neověřeno.

## Ověření bez placení

- Testy `tests/test_chain_api.py`: role mimo dossier vypadnou, prompt podle druhu včetně dossieru bez `druh`, druhy panelů patří k rolím, odhad pokryje Teslu.
- Studio z worktree na :5179 nad uloženým během Kolosea: u panelu „Předloha: Řez“, konzole bez chyb. Uložené návrhy bez `neznama_predloha` se načtou.
