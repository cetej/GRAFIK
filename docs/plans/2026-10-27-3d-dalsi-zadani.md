# 3D: zadání pro další sessions (po v1)

Připraveno 2026-10-27 na pokyn operátora: „otáčení i pohledy by měly existovat vedle sebe. Otáčení jako výchozí, pohledy generování sheetu na tlačítko. Společně s dalšími body připrav zadání pro další konverzace.“ Rozhodnutí: `DECISIONS.md` 2026-10-27 (Otáčení výchozí). Stav v1: `STAV.md`, `plans/2026-10-27-3d-v1.md`, #56, #57.

**Předem zjištěno:** KLAPKA už má 3D, a to hlouběji než GRAFIK:
- `KLAPKA/docs/figury-3d.md`: figury z obrázku. Porovnání backendů 5. 10.: fal **Hunyuan 3.1 Pro** Geometry 0,375 USD vyšel „nejlepší“, lokální Hunyuan3D-2 mini 0 USD na RTX 4060 (špička VRAM 4,5 GB).
- `KLAPKA/docs/sceny-3d.md`: scény s figurami, rekvizitami a parametrickými stroji, rozmístění formulářem, kamera a světlo scény.
- `KLAPKA/prototypy/threejs-kolo/`: scéna v three.js renderovaná v headless Chrome.

GRAFIK nesmí postavit druhou kopii téhož. Pořadí: **A** a **C** mohou běžet souběžně (různá repa), **B** až po A (stejná záložka 3D).

## A. GRAFIK 3D v2: otáčení modelu jako výchozí, sheet pohledů na tlačítko (repo GRAFIK)

- Záložka 3D: místo galerie 8 pohledů je výchozí **prohlížeč modelu**. Myší otáčet, kolečkem přibližovat, tažením s klávesou posouvat. Pojmenované pohledy jedním klikem (zepředu, z boku, zezadu, šikmo, shora).
- **„Vygenerovat sheet pohledů“** na tlačítko: dnešních 8 bílých pohledů (Cycles na CPU, 0 USD, ~38 s) jako arch, zvětšitelný.
- **„Použít tento pohled“**: Engine vyrenderuje bílý obraz přesně z kamery prohlížeče (azimut, výška, vzdálenost, ohnisko) a ten jde jako tvarová předloha. Brána „Model zkontrolován“ platí dál. Kontrola probíhá v prohlížeči i na sheetu.
- Vyber knihovnu prohlížeče: nejdřív se podívej, co používá `KLAPKA/prototypy/threejs-kolo/` (three.js), a sjednoť ji. GLB servírovat zmenšený (decimace) kvůli RAM.
- Před stavbou ukaž operátorovi **náčrt** (vzor `docs/spikes/img/2026-10-27-3d-nacrt.png`).
- Hotovo: otočení, výběr pohledu a předloha v reálném Studiu (screenshot na :5174/:5175), render z kamery prohlížeče odpovídá náhledu (stejný úhel, ověřeno srovnáním), pytest zelený, PR mergnutý, STAV a DECISIONS přepsané.

## B. 3D scény pro infografiky (repo GRAFIK, čte KLAPKA)

- Cíl: víc objektů v jedné scéně (loď v přístavu, stroje na staveništi, zvířata ve stádu) jako bílý tvarový podklad pro FLUX a infografiky.
- **Nejdřív mapovat, nestavět:** `KLAPKA/docs/sceny-3d.md`, `klapka/mechanisms`, rozmístění formulářem, kamera a světlo scény, three.js render. Rozhodni a operátorovi předlož s doporučením: (1) GRAFIK volá KLAPKA přes `docs/service-api.md`, (2) sdílený modul, (3) vlastní tenká vrstva v GRAFIK jen pro statický snímek. Kritérium: nic nepsat dvakrát. Výsledek zapiš do `docs/plans/`.
- Měřítko objektů ze zdrojových rozměrů (`model.json`, natažení `stretch_glb`) a kontrolní postava 1,72 m (LEARNINGS: generátor zvětšuje postavy).
- Blender nebo Chrome jen pod zámkem GPU, nebo na CPU (#56 měřilo 38 s / 8 pohledů na CPU).
- Až po A. Návrh a náčrt nechat schválit operátorem, teprve pak stavět.

## C. KLAPKA ↔ GRAFIK 3D (repo KLAPKA)

- Model z GRAFIK knihovny (`library/3d/<id>/v<n>/`, zkontrolovaný) jde do KLAPKY jako rekvizita nebo figura: import GLB s proveniencí, cenou a stavem kontroly. Nekopírovat ručně, KLAPKA čte přes GRAFIK API (`/api/v2/models3d`, klient `model3d()`, `views()`).
- Klíčové snímky klipů: stejný objekt ze sledu kamer (KLAPKA má kameru scény) jako `role: geometry` do GRAFIK Engine. Jeden svět, stejné poměry ve všech záběrech.
- Sjednotit volbu backendu 3D mezi projekty. KLAPKA označila fal Hunyuan 3.1 Pro za nejlepší, GRAFIK měřil Hunyuan3D v3 a TRELLIS 2. Navrhni operátorovi jeden společný seznam a jedno místo, kde se volá. Placené volání jen s cenou předem.
- **Otevřená otázka licence:** průzkum 27. 10. (`docs/capabilities/3d-moznosti-2026-10-27.md`) uvádí, že licence Tencent Hunyuan 3D 2.0 Community vylučuje EU. KLAPKA spouští Hunyuan3D-2 mini lokálně. Text licence ověř ze zdroje a operátorovi předlož, nic nevypínej sám.
- Napojení projektů dělat jen se souhlasem operátora (GRAFIK STAV: „Napojení projektů až na pokyn operátora“). Tohle zadání je ten pokyn pro KLAPKU.
- Hotovo: v KLAPCE se dá vybrat model z GRAFIK knihovny a z něj udělat snímek záběru, ověřeno na ostrém KLAPKA :8320 bez placení (nahraný GLB). PR v KLAPCE mergnutý, KLAPKA STAV a DECISIONS přepsané.

## Pravidla pro všechny

- Česky v UI, tlačítko je odlišené od informace, náhledy jdou zvětšit. Placené akce jen s cenou předem a výslovným souhlasem operátora.
- Restart serveru jen podle PID z portu. Server spuštěný ze session s ní zanikne (GRAFIK LEARNINGS).
- 3D model hodnotit na velkých renderech po končetinách a částech, ne z náhledů (LEARNINGS 2026-10-27).
