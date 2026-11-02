---
paths:
  - studio/src/Infographics.tsx
  - engine/infographics.py
  - engine/panels.py
  - engine/proposals.py
  - engine/serie.py
  - studio/src/Navrhy.tsx
  - scripts/3d/*infografika*.py
  - scripts/3d/*dokument*.py
  - scripts/3d/*plakat*.py
  - scripts/3d/tesla_*.py
  - scripts/3d/axolotl_*.py
  - scripts/3d/velsen_*.py
  - scripts/plakaty/*.py
---

# Infografiky: zásady

Před změnou vzhledu infografik přečti `docs/infografiky-zasady.md` (čistý styl, rovnováha, informační hodnota, čtenářský zážitek; měřitelné prahy). Vzor nekopíruj, ale drž jeho principy: jedna písmová rodina ve dvou řezech, popisky u věci s krátkými lomenými vodítky, nadpis tam, kde má obraz místo, krátká fakta dole vlevo pod sebou, zarovnaná na prapor, výřez bez rámečku jako vyříznutý obrázek s ostrými okraji, žádné prázdné pásy. Co nemá doklad, do obrazu nepatří.

Logika stránky: oddíl tamtéž, čti první. Co má čtenář pochopit a co je hlavní? Hlavní věc má největší plochu a kontrast, okolí ustupuje, nic tmavého na tmavém. Člověk = životopisná data, dílo na vlastních stránkách. Prázdný pruh nebo třetina stránky je chyba (`panels.empty_share`, práh 20 %), formát se řídí obrazem. Popisky velké, ve výšce své věci, název a pod ním text. Výtku operátora převeď na měření v kódu, ne jen na opravu ukázky.

Web a mobil: oddíl tamtéž, platí pro každou infografiku pro web (výchozí; jen tisková příloha `urceni: "tisk"` má volnost) a počítá se před skladbou. Čtenář je často na telefonu, stránka se zmenší na 360 px a větší plátno nepomůže. Nejmenší text aspoň 1/30 šířky stránky, titulek 1/15. Na stránku 4:5 se vejde kolem 80 slov, na 2:3 kolem 120, jeden hlavní obraz a nejvýš 3 další panely. Velkou plachtu s titěrným písmem rozděl na sérii menších stránek, každou s vlastním titulkem. Řádek Zdroj na stránce není: jen označení AI a cizí autor, plný výčet patří pod článek. Porušení písma hlásí `write_poster` (`SAZBA: na mobilu…`) a `GET …/kontrola`.

Stránka z víc obrazů: oddíl „Stránka z víc obrazů“ tamtéž. Každý panel říká, co hlavní obraz neřekne; stavby z modelu, slavné dílo v originále, lidé z fotorealistického generátoru; postavy na zeleném plátně se stínem z originálu. Výřez kontroluj ve zvětšení.

Plakát podle cizího vzoru: oddíl tamtéž. Nejdřív kopie přes 3D, česky a bez věcných chyb vzoru, vylepšení jen jako návrh. Render pro FLUX má paletu cíle a kameru ze vzoru. Jednotný styl není jeden tón a hustotu vzoru nepřebírej. Ilustrace vysvětluje, jak věc funguje. Před odesláním plný náhled vedle vzoru.

Scény k jednomu nálezu: oddíl tamtéž. Stejná věc vypadá na všech grafikách k článku stejně, zadání generátoru piš až po pohledu na přijatou grafiku a pramen.

Sazba a Knihovna: `write_poster` vypíše `SAZBA:` nálezy, ty oprav před odesláním. `check_layout` nevidí obrazy, popisek vedle postavy nebo modelu hlídá `text_over(…, margin=30)`. Přijatá stránka jde do Knihovny přes `python scripts/plakaty/sazba.py nahraj PAGE.png "Název"`, ne přes `--knihovna`: ten ji nejdřív složí znovu a přepíše.
