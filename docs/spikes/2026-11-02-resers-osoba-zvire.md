# Spike 2026-11-02: volná rešerše pro osobu a zvíře

Plán [infografika z tématu](../plans/2026-11-01-infografika-z-tematu.md), oddíl 4a. Otázka: dá volná rešerše osobě a zvířeti aspoň tolik, co stavbám, aby se plakát typu Tesla nebo axolotl dal začít z Průvodce?

## Kritérium, stanovené před změnou kódu

Měřítko je `scripts/research_kontrola.py`: 35 údajů z [ruční rešerše Tesly](2026-11-01-plakaty-fakta-tesla.md) a 44 z [ruční rešerše axolotla](2026-11-01-plakaty-fakta-axolotl.md). Údaj je nalezený, když ho jeden fakt dossieru říká v tvrzení nebo citaci a má URL. „Strop“ je počet údajů, které vůbec stojí na stažených stránkách.

Výchozí stav (dossiery `nikola-tesla-v1`, `axolotl-v1`):

| Dossier | Fakta | Obrázky | Z ruční rešerše | Strop |
|---|---|---|---|---|
| nikola-tesla-v1 | 9 | 21 | 3 z 35 | 31 z 35 |
| axolotl-v1 | 4 | 11 | 3 z 44 | 38 ze 44 |

Hotovo je, když:

1. **Pokrytí:** Tesla aspoň 24 z 35, axolotl aspoň 30 ze 44 (zhruba 70 %), při nejvýš 120 faktech na dossier, aby krok Návrhy neplatil za balast.
2. **Chyby:** každý údaj s číslem projdu proti citaci a vypíšu. Z náhodného vzorku 20 vět na dossier (seed 20261102) je nejvýš 2 špatně. Špatně = fakt neříká, co zdroj, nebo mluví o něčem jiném než o tématu. Správnost samotného zdroje to neměří, ta se vypíše zvlášť.
3. **Stavby se nezhorší:** nad stejnými odpověďmi API dá starý a nový kód na Pantheonu a Koloseu stejná fakta a stejné obrázky.
4. **Obrázky:** Tesla má portrét v roli `portret`, axolotl mapu výskytu v roli `mapa`, obojí s autorem a licencí. Žádný kreslený model ze Sketchfabu.
5. **Rozpory:** datum patentu na turbínu a datum u US 454,622 jsou v dossieru vidět jako rozpor, s hodnotou každého zdroje zvlášť, nic se neprůměruje.
6. **Mimo měřený vzorek:** jedna další osoba a jedno další zvíře, na kterých jsem kód neladil, dají použitelný dossier (počty a 10 faktů proti zdroji).
7. Testy projdou, změna je sloučená a ověřená v opravdovém Studiu.
