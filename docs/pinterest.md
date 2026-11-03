# Předlohy z Pinterestu do GRAFIK

Všechny tři cesty končí ve **Schránce předloh** (`refs/library/`, `GET /api/v2/refs`). Ve studiu: Předlohy → „Schránka předloh“. Obrázky z Pinterestu mají licenci „neznámá — jen předloha“: slouží jako předloha pro generování, ne jako součást hotového obrázku.

## K zadání obrázku patří obrazové podklady (operátor 3. 11.)

Operátor: „Při vytváření obrázků se zpravidla posílají kromě textového promptu i vhodné obrazové podklady - zpravidla z Pinterest.“

- Než něco vygeneruješ, najdi přes operátorův Chrome (Claude in Chrome) piny k tomu, jak má obraz vypadat: skladba, pohled, světlo, materiál. Ulož je do Schránky předloh nebo k dossieru (níž) a pošli je se zadáním v `refs`. Zadání jen textem je výjimka a řekni ji operátorovi.
- Tvar a stavbu nese vlastní render nebo model v roli `geometry`. Pin jde jako `subject` nebo `scene`, to jsou role, které jdou do generátoru jako obraz. Role `style` jde jen slovy: připiš k ní `text`, jinak ji Engine popíše přes Claude API.
- Lokální FLUX snese všechny obrazové předlohy dohromady kolem 1,1 MP (LEARNINGS 2026-10-23), Engine jich vezme nejvýš 10 (`MAX_IMAGE_REFS`). Vyber pár nejlepších pinů, ne celou zeď.
- Z pinu se berou skladba a vzhled, fakta nikdy. Oděv a výbava historických postav jdou nejdřív z pramene.

## K podkladům tématu

Dossier nese `pinterest`: hotové dotazy z anglického názvu (`3D reconstruction`, `construction model`, `infographic`, `cross section`). Engine sám na Pinterest nemůže, bez přihlášení dostane jen zeď. Claude in Chrome v operátorově prohlížeči projde výsledky a vybrané piny pošle k dossieru:

```bash
curl -X POST http://127.0.0.1:8300/api/v2/research/<id>/inspirace -H "Content-Type: application/json" -d '{"piny": [{"pin": "https://cz.pinterest.com/pin/1/", "obrazek": "https://i.pinimg.com/736x/aa/bb/cc/a.jpg", "nazev": "popis", "dotaz": "Colosseum infographic"}]}'
```

Obrázek se stáhne jen z `i.pinimg.com`, nejvýš 60 pinů naráz, dossier se nemění (`inspirace.json` vedle něj). Ve Studiu oddíl „Inspirace z Pinterestu“ pod obrázky. Hodně pinů je generovaných: skladba a vzhled ano, fakta nikdy.

## 1. Claude in Chrome

Řekněte Claude v Chrome na stránce pinu: „ulož tenhle pin do GRAFIK“. Claude přečte adresu obrázku (`og:image` nebo největší `i.pinimg.com` obrázek) a zavolá:

```bash
python C:/Users/stock/Documents/000_NGM/GRAFIK/clients/grafik_client.py ref-add "<adresa obrázku>" --page "<adresa pinu>" --title "<název pinu>"
```

Stačí i jen adresa pinu: Engine si `og:image` najde sám. Pinterest ale někdy robotům stránku nevydá, a pak je spolehlivější adresa obrázku.

## 2. Přetažení

Ve studiu otevřete Předlohy a přetáhněte obrázek z jiné záložky prohlížeče (nebo soubor z počítače) do pole „Přetáhněte obrázek“. Obrázek z webu jde do schránky s adresou zdroje.

## 3. Záložka „→ GRAFIK“ v liště Chrome

Ve studiu v okně Předlohy → Schránka přetáhněte odkaz **→ GRAFIK** do lišty záložek. Na stránce pinu na něj klikněte: otevře se studio a obrázek se uloží do schránky. Funguje i na jiných webech (vezme `og:image`, jinak největší obrázek na stránce).
