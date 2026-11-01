# Plakáty osoby a zvířete podle cizího vzoru: Nikola Tesla a axolotl

Datum 2026-11-01. Operátor poslal dva vzory a zeptal se, jestli takové infografiky projekt udělá. Vlastní skladby odmítl („To, co jsi splácal…“), chtěl nejdřív kopie vzorů, přes 3D modely, česky a se správnými detaily. Vylepšení zatím jen jako návrh.

## Co projekt dnes umí

| Krok | Stav | Měření |
|---|---|---|
| Věrný vzhled podle vzoru | funguje | lokální FLUX se vzorem jako `--ref …:geometry` nebo `:subject`, 0 USD, 5 až 10 min, 896 × 1600 a 1024 × 1360. Drobný text vyjde jako paskvil, proto se sází vektorově |
| Rešerše k osobě a zvířeti | slabá | Tesla 9 faktů a 21 obrázků, axolotl 4 fakty a 11 obrázků, stavby 44 až 84 faktů. `ROLES`, `PARTS` a `WD_*` míří na stavby, `_NOT_PICTURE` vyřazuje portrét a mapu, Sketchfab vrací kreslené modely. Dossiery `nikola-tesla-v1`, `axolotl-v1` |
| Skladba plakátu | jen skriptem | `scripts/plakaty/tesla_kopie.py`, `axolotl_kopie.py`, společné `sazba.py`. Ve Studiu to nejde, stejně jako u Pantheonu (fáze 3 plánu) |
| 3D model postavy a zvířete | funguje | Hunyuan 3.1 Pro, 2 × 0,375 USD = **0,75 USD**, schválil operátor. Modely `library/3d/nikola-tesla-postava-v-obleku/v1`, `library/3d/axolotl-mexicky-leucisticky/v1` |

Všechno ostatní stálo 0 USD.

## Postup, který zůstal

**Stroje (Tesla):** modely v Blenderu `scripts/3d/tesla_stroje.py`, render Cycles přes OptiX, `scripts/3d/tesla_render.py` pod zámkem těžké práce.

**Postava a zvíře:** geometrie Hunyuan, nad ní render, a teprve ten jde do FLUX jako `geometry`. Přímá projekce barev na model (`scripts/3d/glb_projekce.py`) na obličeji a rukou nechala fleky a na axolotlovi záplaty.

**Stránka:** Tesla je vektorová sazba změřená na vzoru. Axolotl má „desku“: FLUX překreslí stránku vzoru bez zvířete, vymyšlená slova zmizí přes `cv2.inpaint`, navrch jde vektorový text a zvíře.

## Co bylo na vzorech špatně a co je teď

Fakta a zdroje vznikaly mimo repo; do plakátu šly jen údaje dohledané v primárních nebo opakovaných zdrojích.

**Tesla**

| Vzor | Kopie | Zdroj |
|---|---|---|
| tři věže Wardenclyffe | jedna věž v řezu, 57 m, kupole asi 20 m | Wikipedie „Wardenclyffe Tower“, Tesla Science Center |
| stejnosměrný proud jako vlna | vodorovná čára | definice |
| polární diagram, póly N/E/S/W | dvě fáze posunuté o 90°, prstenec se dvěma póly | Tesla 1888, AIEE |
| železné jádro a popisek „spark gap“ u cívky | vlastní obvod cívky bez železa: kondenzátor, jiskřiště, primár, sekundár | patent US 454,622 |
| komíny na vodní elektrárně | vodopád a skutečná hala Adams | Westinghouse Works 1904 |
| televizní anténa na přijímači | jen stožár | dobově nesmysl |
| loď s komínem a okénky | nízká loď na baterie s tyčemi a lampami | Tesla, Century 1900; patent US 613,809 |

Rozpory, které zůstaly otevřené: patent na turbínu má datum udělení 6. 5. 1913 (Wikipedie uvádí 21. 10. 1913, to je chyba), kupole 68 stop proti 55 stopám (na plakátu „asi 20 m“).

**Axolotl**

| Vzor | Kopie | Zdroj |
|---|---|---|
| „regeneruje části očí“ | výčet končetina, ocas, mícha, srdce, sítnice; čočka ne | Joven a kol. 2019 |
| drápy na prstech | prsty bez drápů, vpředu 4, vzadu 5 | Shono a kol. 2026, Boulenger 1911 |
| „parts of eyes“, „neotenic“ | české popisky a věta o neotenii bez TSH | Crowner a kol. 2019 |

## Výtky operátora a co z nich plyne

- **„Proč jde text přes Teslův obličej“:** poznámku o šachtě jsem dal na levý okraj panelu, kam potom přišla hlava. Text u postavy se staví až s jejím obrysem; panely pod ní mají text mimo její plochu.
- **„Ta věž nahoře je tam ještě jednou na umrněné fotce“:** fotku z roku 1903 jsem přidal jako doklad, na plakátu ale jen opakovala model. Pryč. Stejný obsah dvakrát na jednom plakátu nepatří.
- **„A ta podoba Axolotla se moc nepovedla“:** render s červenými vlákny a leskem vrátil FLUX jako červené ostny a gumu, malá hlava vzešla z dlouhého ohniska. FLUX si z předlohy `geometry` bere i barvy, proto musí mít render paletu cíle. Kamera se bere ze vzoru (krátké ohnisko, hlava vpředu).

## Zůstává

Plakát neví o své postavě: kolize textu s figurou hledá zatím jen oko. Návrh vylepšení a rozhodnutí operátora jsou v [DECISIONS](../DECISIONS.md).
