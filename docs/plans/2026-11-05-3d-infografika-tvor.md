# 3D infografika tvora přímo v Grafikovi (vorvaň jako vzor)

Operátor 5. 11.: „potřebujeme, aby šlo vytvářet infografiky v 3D podobně i přímo v Grafikovi … zkušenost z konverzace přenést do projektu“.
Vorvaň („Spolkl by vorvaň člověka?“) vznikl ručně skripty `scripts/3d/lod_vorvan.py`, `vorvan_scena.py`, `scripts/plakaty/vorvan_flux.py`,
`vorvan_stranka.py` za drahé ladění v chatu. Cíl: stejný druh stránky ze Studia, kroky jako obecné úlohy Engine, 0 USD kromě rešerše a návrhů.

Zkouška každé fáze: vorvaň znovu udělaný přes Engine musí odpovídat ruční stránce (obrys IoU, kontroly), pak druhé zvíře, ať kód není ušitý na vorvaně.

## Fáze 1 — tvar, vnitřek, render ve vrstvách (hotovo 5. 11.)

- `engine/silueta.py`, `POST /api/v2/models3d/silueta`: profil z boku (hřbet, břicho) a shora (šířka) z předloh, kontrolní obrázky s obrysem.
- Nové díly v `engine/parts_spec.py`, stavba `engine/blender/lod_parts.py`: `telo` (z profilu, rozloží se na průřezy už v Engine),
  `prurezy` (obecný loft superelips), `elipsoid` (ploutve, tmavá dutina), `deska` (ocas se sklonem), `zuby`, `trubice` (vnitřnosti jako jeden
  souvislý tvar, tkáň po úsecích, klubko střeva), `model` (postava v měřítku: vestavěná 1,72 m nebo GLB z knihovny 3D). Společné `otoceni`.
- Render `engine/blender/render_parts.py` + `POST …/render`: `perspektiva` (50 mm), `pruhledne` (okno v kůži s ostrým okrajem), `samostatne`
  (každá vrstva bez ostatních, kůže zvlášť od vnitřností). Materiály tkání a tmavé kůže `engine/blender/parts_materials.py`.
- Vorvaň jako data: `scripts/3d/dily/vorvan.py` → `vorvan.json` (popis + doporučený render).
- Měření: tvar z dílů proti siluetě IoU 0,57, odchylky obrysu 3,56 / 3,8 / 4,44 % délky, přesně jako ruční model; profil z boku z `silueta.py`
  shodný s ručním do posledního čísla. Render 2400 × 1000, 48 vzorků, 4 průchody na GPU 32 s.

## Fáze 2 — textura lokálním FLUXem jako úloha (hotovo 5. 11., kromě Studia)

- Render s `hlina` (matná světlá hlína) a `bez: ["dutina"]` se stejnou kamerou je předloha tvaru; v `vorvan.json` jako `predloha`.
- `engine/textura3d.py`, `POST /api/v2/models3d/<id>/<ver>/textura` (úloha `textura3d`): každá vrstva × každý seed jeden FLUX na
  zeleném plátně s rolí `geometry`, vystřižení, IoU obrysu proti předloze, doporučený seed. FLUX běží uvnitř úlohy (Worker.process),
  do Knihovny nic nepřibude. Předloha na výšku jde do FLUXu naležato a zpět.
- `POST …/textura/<id>/vyber`: složení `okno` (alfa FLUXu oříznutá oknem z barevného renderu) a `pod` (tmavá dutina pod orgány),
  `na_vysku` = překlopení podle úhlopříčky i s body popisků. Výsledek `renders/<r>/textura-<n>/hotovo-<k>/`.
- Recept vorvaně `vorvan.json` → `textura` (prompty z `vorvan_flux.py` beze změny).
- Zbývá: výběr seedu ve Studiu (jediné ruční rozhodnutí) patří do fáze 3 spolu s krokem v řetězci.

## Fáze 3 — krok „3D scéna“ v řetězci a stránka v Infografikách (čeká)

- Krok mezi Návrhy a Stránky v `engine/chain.py`; návrh zvířete s pojmy „vnitřek“, „figura v měřítku“.
- Panelový dokument s vrstvami kůže, vnitřku a postavy: vnitřek oříznutý obrysem těla, záře postavy, popisky na `body.json`.
- 16:9 i 9:16 ze stejných vrstev; záznam v Infografikách, VectorCraft, bez zdroje a kreditu na stránce (DECISIONS 2026-11-05).
- Dnes stránky ze skriptů (`sazba.py nahraj`) jdou jen do Knihovny, do Infografik žádná cesta nevede.
