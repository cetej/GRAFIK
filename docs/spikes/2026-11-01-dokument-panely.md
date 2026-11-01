# Dokument s panely: měření 3c (2026-11-01)

Plakát se dřív skládal jednorázovým skriptem (`scripts/3d/pantheon_plakat.py`). Teď ho umí Engine jako dokument: `schema_version: 2`, `panels[]`, `engine/panels.py`. Staré dokumenty beze změny, kreslí je dál Studio.

## Pantheon z dokumentu proti hotovému plakátu

`scripts/3d/pantheon_dokument.py pohledy` znovu vyrenderoval stejné pohledy, `dokument` z nich a ze stejných textů složil dokument. Porovnáno s `library/plakaty/pantheon/pantheon.png`, ten zůstal beze změny.

| Míra (1600 × 2400 px) | Hodnota |
|---|---|
| Průměrná odchylka kanálu | 0,199 z 255 |
| Pixelů s odchylkou nad 16 | 0,002 % |
| Pixelů s odchylkou nad 64 | 0,000 %, malé místo u nadpisu (x 1051 až 1065, y 101 až 105) |

První pokus měl 2,6 % pixelů nad 16 a odhalil dvě věci: rozložený pohled má 1020 × 1720 px, ne 1700 (odhad z měřítka), a patička se zalamovala o znak dřív. Obojí opravené.

Kontroly dokumentu ukázaly na hotovém plakátu to, co by v editoru vidět nebylo, protože plakát editorem neprošel: medián vodítek 8,4 % šířky (práh 6 %), 5 vodítek přes 12 %, 2× křížení. Plakát se proto nemění, je to podklad pro krok 3d.

## VectorCraft bez okna

Koloseum v opravdovém VectorCraftu (kopie 9 MB): bez varování a chybějících odkazů, plátno 1600 × 2400, vrstvy Grafika (12 skupin) a Texty (17 skupin), každý obraz, vodítko a popisek zvlášť. Převzetí ruční úpravy touž funkcí jako `POST …/vectorcraft/export`: změněný text se objevil v novém PNG, PDF a SVG, kontrola věty o AI prošla, 90 textů na plátně.

## Co Engine umí

- Panely `obraz`, `fakta`, `text`, `osa`, `kresba`. Obraz se v panelu nikdy neořízne, `poradi` je důležitost pro krok 3d.
- Popisek míří na název z `body.json`, nebo na bod [x, y, z] v metrech přes `origin` a `basis`.
- Číslované značky (`znacky`) přímo v obraze tam, kde by se popisky s vodítky nevešly; legenda je samostatný panel.
- Zdroj obrazu: render modelu, složka v knihovně, hotový obrázek (`obraz`, `ref_id`, volitelně `vyrez` a `vyriznout`, který odstraní studiové pozadí podle barvy rohů). Kopíruje se do dokumentu, pozdější render ho nezmění.
- Patička jmenuje po panelech, co je render bez AI, co je AI a čí je cizí obraz. Export pak nese `ai_generated` podle skutečnosti, ne podle hlavního obrazu.
- Kontroly stejné jako v editoru, přes všechny panely: `GET …/kontrola`.

## Meze

- **Studio dokument zatím nekreslí.** `GET /api/v2/infographics` ho proto bez `?panely=true` neukazuje, starý editor by ho otevřel špatně. Editor čeká na náčrt.
- **Rozměr textu je odhad** (0,47 em na znak), kontrola překrytí je proto jen orientační.
- **Automatické rozmístění popisků není.** `pos` zadává autor dokumentu; přijde s krokem 3d.
