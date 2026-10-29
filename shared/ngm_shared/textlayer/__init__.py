"""Vrstva textu nad obrazem: sazba popisků podle pravidel NG a počeštění cizí infografiky.

Text v obraze nekreslí generátor, ale tahle vrstva (plán STOPA 2026-10-29 § 3 a § 9): je přesná,
opravitelná a jde zkontrolovat. Mapy z dat staví KARTOGRAF, sem patří jen sazba nad hotový obraz.

Kopie z NG-ROBOT `ng_vector_labels` (commit v hlavičce každého modulu, NG-ROBOT se nemění):
    style      pravidla NG pro popisky (písma, velikosti, barva podle pozadí, halo)
    layout     rozložení v2 (popisky, značky, trasy, legenda v procentech podkladu)
    raster     barva pozadí pod textem, voda / pevnina
    compose    složení vrstvy ve VectorCraftu → .vectorcraft/.pdf/.svg/.png/.ai
    vc_client  klient VectorCraftu (MCP), relace pod zámkem těžké práce
    checks     deterministické kontroly složené vrstvy (kolize, kontrast, okraje, typografie)

Nové v GRAFIKU:
    localize   počeštění cizí infografiky: přečíst (Claude) → vymazat (cv2.inpaint) → vysázet PNG a SVG

Závislosti: numpy, Pillow; `localize` navíc opencv-python a anthropic (`pip install -e GRAFIK/shared[text]`).
"""
