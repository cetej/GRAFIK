---
paths:
  - studio/src/Infographics.tsx
  - engine/infographics.py
  - engine/panels.py
  - engine/proposals.py
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

Web a telefon: infografika se čte hlavně na webu a na mobilu. Před skladbou spočítej písmo na šířce 390 px (aspoň 11 px, oddíl „Web a telefon“). Velkou plachtu s titěrným písmem raději rozděl na menší infografiky.

Stránka z víc obrazů: oddíl „Stránka z víc obrazů“ tamtéž. Každý panel říká, co hlavní obraz neřekne; stavby z modelu, slavné dílo v originále, lidé z fotorealistického generátoru; postavy na zeleném plátně se stínem z originálu. Výřez kontroluj ve zvětšení.

Plakát podle cizího vzoru: oddíl tamtéž. Nejdřív kopie přes 3D, česky a bez věcných chyb vzoru, vylepšení jen jako návrh. Render pro FLUX má paletu cíle a kameru ze vzoru. Jednotný styl není jeden tón a hustotu vzoru nepřebírej. Ilustrace vysvětluje, jak věc funguje. Před odesláním plný náhled vedle vzoru.

Scény k jednomu nálezu: oddíl tamtéž. Stejná věc vypadá na všech grafikách k článku stejně, zadání generátoru piš až po pohledu na přijatou grafiku a pramen.

Sazba a Knihovna: `write_poster` vypíše `SAZBA:` nálezy, ty oprav před odesláním. `check_layout` nevidí obrazy, popisek vedle postavy nebo modelu hlídá `text_over(…, margin=30)`. Přijatá stránka jde do Knihovny přes `python scripts/plakaty/sazba.py nahraj PAGE.png "Název"`, ne přes `--knihovna`: ten ji nejdřív složí znovu a přepíše.
