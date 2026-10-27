# Spike 2026-10-27 — glTF Transform: optimalizovaná kopie pro prohlížeč 3D (cetej/GRAFIK#64)

Zadání: zmenšit GLB, které načítá prohlížeč 3D ve Studiu, bez přepsání originálu. Nic placeného (0 USD).

## Co prohlížeč načítá

Engine ukládá `library/3d/<id>/v<n>/model.glb` (z fal, nahraný nebo natažený). Úloha `viewer3d` z něj Blenderem vyrobí `viewer.glb`: 100k trojúhelníků, svařené, **bez materiálů, textur, UV i normál** (prohlížeč ukazuje hlínu, DECISIONS 2026-10-27). Prohlížeč modelu (`Viewer3d.tsx`) i prohlížeč scény (`SceneViewer3d.tsx`) načítají jen `viewer.glb`; Blender (sheet, render z kamery, scény) čte vždy `model.glb`.

Optimalizace se proto zapojuje za `viewer.glb`: vedle něj vznikne `viewer.opt.glb`. `model.glb` ani `viewer.glb` se nemění.

## Nastavení

`gltf-transform optimize viewer.glb viewer.opt.glb --compress meshopt --simplify false --join false --instance false --texture-compress webp --texture-size 2048` (`@gltf-transform/cli` 4.5.1 v `engine/gltf/`).

- `--simplify false`: kopie je už zmenšená v Blenderu.
- `--join false`: se spojením do jednoho meshe se loď z Blenderu (993 dílů, 48 m) kvantizuje přes celou délku a tenká vesla a lana se stínují jinak: 3,4 % pixelů s rozdílem > 32/255. Bez spojení 0,004 %.
- `--instance false`: jinak se opakovaná vesla stanou `InstancedMesh` a prohlížeč by počítal trojúhelníky jen za jeden exemplář (13 192 místo 43 036, tedy `flatShading` místo hladkého stínování).
- Textury: kopie pro prohlížeč dnes žádné nemá, WebP se stropem 2048 px platí, kdyby nějaké měla.

## Výsledek na reálných modelech

Kopie pěti modelů z `library/3d` ve zkušebním Engine (:8301, vlastní data) a Studiu (:5175). Doba načtení = `loadGlb()` ve Studiu (stažení z localhostu + rozbalení + parsování), medián ze 7 načtení. Rozdíl = stejný záběr (azimut 315°, výška 20°, 50 mm), hlína jako v prohlížeči, podíl pixelů s rozdílem > 32/255.

| Model | viewer.glb | viewer.opt.glb | poměr | optimalizace | načtení orig. → opt. | trojúhelníky | rozdíl pixelů |
|---|---:|---:|---:|---:|---:|---:|---:|
| Tatra 87 v2 (Hunyuan, natažená) | 1 200 464 B | 325 408 B | 3,7× | 1,0 s | 26 → 17 ms | 100 000 = | 0,001 % |
| Kvinquerema (TRELLIS 2) v1 | 1 152 028 B | 331 916 B | 3,5× | 1,6 s | 24 → 18 ms | 100 000 = | 0,006 % |
| Římská kvinquerema (Blender) v2 | 812 536 B | 286 800 B | 2,8× | 1,4 s | 48 → 27 ms | 43 036 = | 0,004 % |
| Amfora (zkouška KLAPKA) v1 | 1 200 736 B | 317 344 B | 3,8× | 0,8 s | 23 → 16 ms | 100 000 = | 0 % |
| Mamut (TRELLIS 2) v1, celá cesta | 1 058 248 B | 303 936 B | 3,5× | 0,9 s | 21 → 15 ms | 103 255 = | 0,001 % |

Obálka modelu se shoduje na ±2 mm (kvantizace). Mamut prošel celou cestou (Blender zmenšení + glTF Transform v jedné úloze `viewer3d`), ostatní `optimize_only` nad existující kopií. První běh po startu Engine trval 15,8 s (studený Node), další ~1 s.

Snímek originál × optimalizováno: [`img/2026-10-27-gltf-optimize.jpg`](img/2026-10-27-gltf-optimize.jpg).

Pro srovnání plný model s texturami: `kvinquerema-trellis2/v1/model.glb` 21,6 MB → 5,9 MB. Prohlížeč ho nenačítá, proto se `model.glb` neoptimalizuje.

## Záložní cesta

- Chyba nástroje (chybí Node, pád, výstup není GLB) se zapíše do `viewer.optimized.error`, úloha doběhne a stará `viewer.opt.glb` se smaže. Studio pak načte `viewer.glb`.
- Ověřeno ve Studiu: po smazání `viewer.opt.glb` vrátil Engine 404 a prohlížeč hned načetl `viewer.glb` (200), model se vykreslil.
- Starší modely dostanou kopii při prvním otevření (`POST …/viewer?optimize_only=true`, bez nového zmenšení v Blenderu).
