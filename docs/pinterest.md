# Předlohy z Pinterestu do GRAFIK

Všechny tři cesty končí ve **Schránce předloh** (`refs/library/`, `GET /api/v2/refs`). Ve studiu: Předlohy → „Schránka předloh“. Obrázky z Pinterestu mají licenci „neznámá — jen předloha“: slouží jako předloha pro generování, ne jako součást hotového obrázku.

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
