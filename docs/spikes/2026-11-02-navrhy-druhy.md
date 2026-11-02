# Spike 2026-11-02: krok Návrhy podle druhu tématu

Plán [infografika z tématu](../plans/2026-11-01-infografika-z-tematu.md), oddíl 4a. Otázka: použije návrh pro osobu a zvíře role obrázků z dossieru, aniž by se zhoršily stavby?

Závěr: ano. Tesla a axolotl používají jen role, které dossier má, a žádný panel `rez` ani `pudorys`. Koloseum vyšlo stejně nebo lépe než běhy z 1. 11. Každý dossier běžel jednou a Sonnet dává pokaždé jiné návrhy, takže jde o vzorek, ne o důkaz. Předlohu zatím jen ukazuje Studio, generování obrazů ji začne číst v kroku 3f.

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

## Co měřítko nezachytilo

- **Portrét u Tesly je jen v jednom ze tří návrhů.** Hlavní obraz je pokaždé stroj nebo věž, dvě skladby Teslu vůbec neukazují. Zásada „ukaž, co člověk změnil“ tím vyhrála nad jeho podobou. Povinný portrét jsem nepřidal: prompt by se změnil bez dalšího placeného běhu.
- **Celé zvíře jako hlavní obraz dodržel jen první návrh axolotla.** Druhý začíná mapou, třetí bohem Xolotlem. Jako nápady dávají smysl, takže pravidlo je možná zbytečně přísné. Prompt zůstal v měřené podobě.
- **Fakta jsem proti zdrojům neověřoval.** Návrhy jen odkazují na id z dossieru, text na stránku se bere z dossieru a čte ho člověk.
- **Řetězec ze Studia na Teslovi naostro neběžel.** Běžel skript se stejnou funkcí `proposals.propose`. Studio jsem ověřil nad uloženým během Kolosea.
- **Rostlina jde cestou zvířete,** neověřeno.

## Ověření bez placení

- Testy `tests/test_chain_api.py`: role mimo dossier vypadnou, prompt podle druhu včetně dossieru bez `druh`, druhy panelů patří k rolím, odhad pokryje Teslu.
- Studio z worktree na :5179 nad uloženým během Kolosea: u panelu „Předloha: Řez“, konzole bez chyb. Uložené návrhy bez `neznama_predloha` se načtou.
