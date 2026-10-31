# Jak psát `scripts/3d/lod_*.py`: render a měření v kole

Model z rozměrů se nehodnotí od oka na malých náhledech (slon s pátou nohou, LEARNINGS 2026-10-27). Po každé verzi skriptu běží kontrola, autor dostane čísla a obrázky a opraví skript. **Nejvýš 3 kola.** Konec, když je `problemy` prázdné, nebo po třetím kole: co zbylo, zapiš a předej operátorovi. Další kolo nedělej jen proto, že by něco šlo vylepšit.

```bash
python scripts/3d/lod_check.py VÝSTUP/kolo-1 --lod scripts/3d/lod_tatra87_v2.py --ref silueta.png
```

Na hotový model: `--glb model.glb --dim 4.74 1.67 1.50`. Skript si vezme zámek těžké práce (`blender`), 0 USD. Exit 0 = nic k opravě, 1 = viz `problemy`.

## Co dostaneš

`kontrola.json` a `inspect.json` ve výstupní složce, `pohledy.png` jako jeden arch. Vždy se dívej i na `side.png` a `persp-*.png` v plném rozlišení (1024 px).

| Kontrola | Hranice | Odkud hranice |
|---|---|---|
| šířka/délka a výška/délka proti `DIM` | ±5 % (`--tol`) | Tatra z rozměrů 1 % a 3,8 %, surový Hunyuan3D 50 % a 38 % |
| obrys proti siluetě (`--ref`), každá třetina délky | 2 % délky (`--tol-obrys`) | Blender po 1. kole 5,8 %, po 3. kole 1,4 %; natažený střed na zádi 5,6 % |
| díl bez kontaktu | žádný | mezera nad 0,3 % nejdelší strany; mamut: oba kly 7,6 cm, ocas 32 cm |
| těla v průřezu v dolní polovině (`--tel N`) | nejvýš N | mamut 4 nohy + chobot = 5; slon z Hunyuan3D 6, šesté na zádi |
| otevřené a víc sdílené hrany | jen informace | ploché díly je mají z principu |

Bez `DIM` s klíči `length`, `width`, `height` a bez `--dim` se poměry nekontrolují. Prázdné `bez_kontaktu` neznamená správný tvar, jen že nic neplave. Prázdné `problemy` bez `--ref` a `--tel` říká jen, že sedí poměry.

## Silueta skutečného objektu

Boční obrys, delší osa přes obrázek, alfa nebo bílé pozadí. Fotka zešikma lže v délce: nejdřív ji narovnej (příklad `docs/spikes/2026-10-31-tatra-silueta.py`, Tatra 87). Poměry drží `DIM`, silueta se bere jen jako tvar. `--zrcadlit`, když model v `side.png` míří opačně než silueta; podle překryvu se směr určit nedá (Tatra: špatný směr dal lepší shodu).

## Kontext při psaní

- Ověřené vzory: `scripts/3d/lod_tatra87_v2.py` (průřezy podle siluety a podsurf), `lod_kvinquerema.py` (mnoho přesných dílů), `lod_mamut.py` (metaballs, `threshold` 0,25), `lod_rotunda_martin.py` (válcové stavby).
- Každý rozměr v `DIM` se zdrojem; `odhad` = bez zdroje.
- Python API Blenderu 5.2: <https://docs.blender.org/api/5.2/>. Verzi Engine bere z `engine.config.find_blender`. Export glTF v 5.2: `export_texcoords` (LEARNINGS 2026-10-27).
- Hotové modely a skripty, ze kterých vznikly, nepřepisuj: novou verzi ulož vedle (`lod_tatra87_v2.py`).

Důkaz a srovnání bez smyčky a se smyčkou: [`spikes/2026-10-31-lod-smycka.md`](spikes/2026-10-31-lod-smycka.md).
