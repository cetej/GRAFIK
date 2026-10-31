# Katalog stylů: 82 stylů v šesti kategoriích, ukázky

2026-10-31. Rozhodnutí: [DECISIONS 2026-10-31](../DECISIONS.md). Katalog `styles/katalog.yaml`, skript `scripts/styles_katalog.py`.

| Kategorie | Stylů | z toho nových | Přehled ukázek |
|---|---:|---:|---|
| Fotografie | 11 | 11 | [obrázek](img/2026-10-31-styly-fotografie.jpg) |
| Historické | 21 | 21 | [obrázek](img/2026-10-31-styly-historicke.jpg) |
| Ilustrace | 11 | 9 | [obrázek](img/2026-10-31-styly-ilustrace.jpg) |
| 3D | 11 | 7 | [obrázek](img/2026-10-31-styly-3d.jpg) |
| Komiks | 9 | 8 | [obrázek](img/2026-10-31-styly-komiks.jpg) |
| Film | 19 | 11 | [obrázek](img/2026-10-31-styly-film.jpg) |
| **Celkem** | **82** | **67** | |

## Jak vznikly ukázky

Přes běžící Engine :8300, lokální FLUX, 1024×768, seed 42, po jedné úloze. Nové styly mají 3 ukázky, stávající 2 (`karikatura-3d-real` žádnou, má 5 vlastních vzorů operátora). Plán 229 ukázek, hotovo 229, žádná úloha neselhala, jedna ukázka trvala 28 až 33 s bez cizích úloh ve frontě. Cena: všech 261 úloh s `caller` `styl:*` v `run/jobs.sqlite` má backend `flux-local` a součet `cost_usd` 0,0.

## Co se opravilo po prohlédnutí

Všechny přehledy jsem prošel očima, podezřelé kusy zvlášť ve větším. Opravy textu karty, ukázky pak znovu:

| Styl | Vada | Oprava karty |
|---|---|---|
| Jeskynní malba | lampa na skále | pryč slovo o lampě |
| Ligne claire | auta na polní cestě | pryč „vehicles“ |
| Studiový portrét | softbox v obraze | pryč slovo softbox |
| Kodachrome | rámeček diapozitivu | „no slide mount“ |
| Holandský žánr | kůň v kuchyni | interiér pryč z kompozice |
| Gotická vitráž | realistický obraz uprostřed okna | celý obraz ze skla |
| Moderní komiks | malba nebo fotka místo komiksu | pevná linka, tvrdé stíny |
| Čínská tuš | spíš rytina | řídké tahy štětcem |
| Spaghetti western | koláž tří záběrů | „one unbroken frame“ místo „close-ups mixed with long shots“ |
| Přírodopisný dokument | kamera nad vodou | pryč „stabilised mount“ |
| Němý film | kamera na stativu vedle sedláka | pryč „camera“ a „tripod“ |
| Encyklopedická rytina | nástroje na cestě u koně | dole „details of the same subject“ místo „tools“ |

Jen jiný seed (srostlá postava s koněm, cizí tvar v obraze): raná renesance a klasicismus 43, barok 43, rokoko a plochá vektorová 45. Stav je v `run/katalog-ukazky.json`. U baroka seed 45 dopadl hůř, zůstal 43. Muzejní předmět dostal místo meče korintskou přilbu.

## Co zůstává

- **Sedlák u koně je těžký motiv.** U několika stylů (komiksový strip, noir) jsou na obrázku dva sedláci místo jednoho. Styl to nekazí, nechal jsem to. Němý film má na první ukázce oči, které připomínají tmavé brýle.
- **Stávající karty lampy kreslí dál:** `anticke-drama` má v trávě svíčky, `malovany-epos` lampu na pařezu. Text těch karet je z KLAPKY a nesahal jsem na něj.
- **`dokumentarni-rekonstrukce` a `-era`** dávají stejný obraz, mají stejný text.
- **Text stávajících karet se nezměnil:** `image_text` a `video_lines` 11 karet z KLAPKY sedí na `KLAPKA/studio/library/styles`, pole 3 karet z GRAFIKU na `styles/<slug>/style.json` v gitu. U `karikatura-3d-real` starší kopie k porovnání není; skript jí doplnil jen `kategorie` a `poradi`.
- **Nové karty sedí na katalog:** 67 z 67, nikdo je mezitím ručně neupravil.
