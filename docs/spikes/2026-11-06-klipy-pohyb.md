# Klipy postavy podle pohybu (2026-11-06)

Cíl: z jednoho realistického statického obrázku legionáře a videa s pohybem vznikne klip 5–8 s, ve kterém postava drží vzhled a výstroj. Skript `scripts/video/klip_pohyb.py`.

## Modely na fal.ai (ověřeno na stránkách fal 6. 11. 2026)

| Model (endpoint) | Cena | 6 s klip | Vstup | Délka | Poznámka |
|---|---|---|---|---|---|
| Kling 2.6 Pro motion control `fal-ai/kling-video/v2.6/pro/motion-control` | 0,112 USD/s | **0,672 USD** | obrázek + video, `character_orientation` | `video` do 30 s, `image` do 10 s | výchozí ve skriptu; postava na obrázku > 5 % plochy, celé tělo, bez zakrytí |
| Kling 3.0 Pro motion control `fal-ai/kling-video/v3/pro/motion-control` | 0,168 USD/s | 1,008 USD | totéž + `elements` (vazba obličeje: čelní obrázek + 1–3 další pohledy, v promptu `@Element1`) | jako 2.6 | vazba obličeje jen s `character_orientation: video`; skript `--model kling3 --element ref-right.png ref-back.png` |
| Kling 3.0 Standard motion control `fal-ai/kling-video/v3/standard/motion-control` | 0,126 USD/s | 0,756 USD | jako v3 Pro | | ve skriptu není, kvalita pod Pro |
| Kling 2.6 Standard motion control `fal-ai/kling-video/v2.6/standard/motion-control` | 0,07 USD/s | 0,42 USD | jako 2.6 Pro | | nejlevnější, ve skriptu není |
| MiniMax H3 Max Recast `minimax/h3-max/recast` | 0,30 USD/s (768P), 0,45 USD/s (1080P) | 1,80 / 2,70 USD | video + 1 fotka na každou nahrazovanou osobu, prompt, `enhance_realism` | video 5–30 s, záběr nejvýš 15 s | nahradí lidi ve videu a **zachová kameru, střih, prostředí i zvuk zdrojového videa**; pozadí tedy přijde z videa, ne z obrázku |
| Wan 2.2 Animate Move `fal-ai/wan/v2.2-14b/animate/move` | 0,04–0,08 USD za „video sekundu“ (16 snímků) | | obrázek + video | | fal ho **ruší 4. 1. 2027**, na stránce doporučuje přejít na H3 Max Recast; nestavět na něm |

**Co je H3 Max Recast:** fal přetrénoval otevřený videomodel MiniMax H3 (post-training na kvalitu a poslušnost promptu) a vydává ho jako H3 Max; Recast je jeho video-to-video režim pro výměnu postavy. Je to náhrada Wan Animate **Replace** (výměna osoby ve videu), ne Wan Animate Move (oživení obrázku). Pro náš případ „postava z obrázku na neutrálním pozadí“ je přímou náhradou Kling motion control; Recast se hodí, když chceme zachovat scénu a kameru natočeného videa. Je asi 2,7× dražší než Kling 2.6 Pro.

Všechny tři použitelné modely mají na fal štítek komerčního použití. Účtuje se délka výstupu; skript počítá celé sekundy nahoru.

## Pohyb

`library/klipy/pohyby/pexels-8296233-chuze.mp4` (hlavní checkout): „A Man Walking Outdoors“, autor Mikhail Nilov, <https://www.pexels.com/video/a-man-walking-outdoors-8296233/>, 1080×1920, 25 fps, 13,1 s. **Licence Pexels**: komerční použití i úpravy povoleny, uvedení autora není povinné; nesmí se naznačovat, že osoba něco doporučuje, ani ji ukazovat v urážlivém světle. Z videa bereme jen pohyb, osoba ve výsledku není. Původ je v `pexels-8296233-chuze.mp4.puvod.json`.

Proč tenhle: jeden člověk, celá postava od hlavy po boty, chůze přímo ke kameře, klidné pozadí. Ze tří dalších kandidátů jeden ukazoval jen nohy, jeden malou postavu v dálce a jeden záda. Pozor: muž od ~2. sekundy drží ruce sepjaté na hrudi, legionář je zopakuje. Pro vojenskou chůzi s volnými pažemi bude lepší jiný záznam (hledat dál, nebo natočit vlastní).

Obrázek: `library/3d/rimsky-legionar-v-a-poze-zaklad-pro-kostru/v1/podklad/ref-front.png` (768×1152, A-póza, šedé studiové pozadí).

## Skript

```
python scripts/video/klip_pohyb.py --image <ref-front.png> --motion <chuze.mp4> --start 1 --duration 6 [--model kling26|kling3|recast]
```

- bez `--confirm-cost`: ořízne pohyb (`ffmpeg`, bez zvuku) do výstupní složky, vypíše cenu, nic neposílá a nic nezapíše do `costs.jsonl`;
- s `--confirm-cost`: nahraje vstupy, `submit`, **`request.json` s `request_id` zapíše hned po odeslání**, pak záznam `pending` do `C:/Users/stock/Documents/000_NGM/GRAFIK/library/costs.jsonl` (hlavní checkout), po výsledku `ok`/`failed`; stáhne `klip.mp4`, uloží `result.json` a 6 snímků + `prehled.jpg` do `snimky/`;
- `--dobrat <složka>`: když skript spadne po odeslání, stáhne hotový výsledek podle `request.json` bez nového placení.

Výchozí složka `library/klipy/<čas>-<model>/` v hlavním checkoutu.

Ověření zdarma (6. 11.): dry-run všech tří modelů vypsal 0,672 / 1,008 / 1,80 USD za 6,00 s, `costs.jsonl` beze změny; export snímků na oříznutém pohybu dal 6 snímků a přehled.

## Výsledek placeného testu

Zatím nespuštěno, čeká na souhlas operátora (Kling 2.6 Pro, 6 s, 0,672 USD).
