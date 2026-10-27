# 3D v2: prohlížeč modelu, sheet na tlačítko, render z kamery prohlížeče (2026-10-27)

Zadání A z [`plans/2026-10-27-3d-dalsi-zadani.md`](../plans/2026-10-27-3d-dalsi-zadani.md), rozhodnutí operátora z 27. 10. (DECISIONS). Náčrt [1](img/2026-10-27-3d-v2-nacrt-1.png), [2](img/2026-10-27-3d-v2-nacrt-2.png) operátor schválil beze změn.

## Co vzniklo

- **Prohlížeč** (`studio/src/Viewer3d.tsx`): three.js 0.170.0 jako KLAPKA `prototypy/threejs-kolo` (OrbitControls, GLTFLoader). Táhnout = otočit, kolečko = přiblížit, Shift+táhnout nebo pravé tlačítko = posunout. Pohledy jedním klikem: Zepředu (270°), Z boku (0°), Zezadu (90°), Šikmo (315°/20°), Shora. Ohnisko 35/50/85 mm, čárkovaný čtverec = výřez předlohy. Klik na snímek sheetu natočí prohlížeč na jeho úhel.
- **Zmenšená kopie** `viewer.glb` (`engine/blender/decimate.py`, úloha `viewer3d`, CPU, bez zámku GPU): svaření vrcholů, collapse na 100 000 trojúhelníků, jen geometrie. Tatra 87 v2: 42 MB / 500k ploch → **1,2 MB za 10 s**; kvinquerema 21,6 MB → 1,15 MB za 6 s. Po novém modelu, nahrání i natažení vznikne sama; starší modely ji dostanou při prvním otevření (0 USD).
- **Sheet** 8 bílých pohledů jen na tlačítko „Vygenerovat sheet pohledů · 0 USD · ~40 s“, pod prohlížečem, zvětšitelný.
- **„Použít tento pohled“** (`POST /api/v2/models3d/<id>/<v>/camera`, úloha `camera3d`, `render_views.py --camera`): Cycles na CPU pod zámkem GPU, 8,3 s za obraz; soubor `camera/cam-<hash>.png` + `.json` s kamerou, stejná kamera = stejný soubor (žádný druhý render). Do Studia jde jako předloha „tvar“ přes `as-ref?cam=`. Brána „Model zkontrolován“ platí pro render i předlohu; zaškrtnout jde po prohlédnutí v prohlížeči (sheet už není podmínka).

## Ověření

- Reálné Studio z větve na :5175 nad Engine z větve (`GRAFIK_DATA_DIR` = hlavní checkout): [z boku](img/2026-10-27-3d-v2-studio-z-boku.png), [šikmo](img/2026-10-27-3d-v2-studio-sikmo.png), [předloha ve Studiu](img/2026-10-27-3d-v2-studio-predloha.png), [odeslaný náhled ve 3D](img/2026-10-27-3d-v2-studio-odeslano.png).
- **Prohlížeč = render**: [amfora](img/2026-10-27-3d-v2-srovnani-amfora.png) otočená myší ve Studiu (azimut 243°, výška 33°), výřez plátna proti renderu Engine: shoda obrysů **99,4 %**. [Tatra 87 v2](img/2026-10-27-3d-v2-srovnani-tatra-pan.png) s posunutým cílem (pan) a ohniskem 85 mm, tentýž výpočet kamery v three.js proti `render_views.py --camera` nad plným `model.glb`: shoda **99,9 %**. Zmenšená kopie tedy nemění obrys ani polohu.
- Testy: `tests/test_models3d.py` 21 (7 nových pro v2), celá sada viz STAV.
- 0 USD, žádné placené volání.

## Hranice

- Natočení „zepředu“ předpokládá, že generátor otočil předek k +Z glTF (TRELLIS, Hunyuan3D); u nahraného GLB z jiného nástroje může být předek jinde, pak stačí dotočit myší.
- Světlo prohlížeče je jen orientační (MeshStandardMaterial), render má Cycles; shoduje se úhel a výřez, ne odstín.
