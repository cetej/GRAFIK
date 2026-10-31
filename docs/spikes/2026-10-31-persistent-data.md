# Cycles `use_persistent_data` při renderu 8 pohledů (2026-10-31)

Hypotéza: `scene.render.use_persistent_data = True` nechá mezi pohledy BVH a synchronizovanou scénu, takže list 8 pohledů (dnes 37 až 52 s) zrychlí.

## Nastavení

Blender 5.2.3 LTS, `-b --factory-startup -P render_views.py -- model.glb OUT 20 --cpu` (Cycles CPU, 32 vzorků, denoising), bez Engine a FLUXu. Varianta „on" = kopie skriptu s jedním řádkem `scene.render.use_persistent_data = True` v bloku `if cpu:`. Modely: `tatra-87/v1` (Hunyuan, 500 000 ploch) a `tatra-87-trellis-2-commons-ntm/v1` (TRELLIS). Každá varianta 2×, střídavě off, off, on, on. Čas = čas posledního „Saved" v logu Blenderu (celý běh bez ~1 s ukončení), první pohled a průměr dalších 7.

## Čísla

| Model | Varianta | Běh | Celkem | 1. pohled | Dalších 7 (průměr) |
|---|---|---|---|---|---|
| tatra-87 (Hunyuan) | off | 1 | 36,6 s | 6,0 s | 4,4 s |
| tatra-87 (Hunyuan) | off | 2 | 37,1 s | 6,0 s | 4,4 s |
| tatra-87 (Hunyuan) | on | 1 | 37,3 s | 6,0 s | 4,5 s |
| tatra-87 (Hunyuan) | on | 2 | 35,7 s | 7,0 s | 4,1 s |
| tatra-87-trellis-2-commons-ntm | off | 1 | 39,4 s | 6,4 s | 4,7 s |
| tatra-87-trellis-2-commons-ntm | off | 2 | 35,6 s | 5,8 s | 4,3 s |
| tatra-87-trellis-2-commons-ntm | on | 1 | 34,7 s | 5,8 s | 4,1 s |
| tatra-87-trellis-2-commons-ntm | on | 2 | 35,5 s | 5,9 s | 4,2 s |

Průměr off / on: Hunyuan 36,9 / 36,5 s (−1 %), TRELLIS 37,5 / 35,1 s (−6 %, ale off 1 je 39,4 s proti 35,6 s u off 2, takže šum mezi běhy je sám ~10 %).

Pixely: 8 pohledů obou modelů, off 1 proti off 2 a proti oběma on: podíl odlišných pixelů 0,000 % (render je deterministický, PNG shodné bit po bitu).

## Verdikt

Zrychlení 1 až 6 % je v šumu a pod prahem 15 %. Hypotéza neplatí: `bpy.ops.render.render` mezi pohledy zřejmě nestaví BVH znovu draho (první pohled 6 s, další 4,1 až 4,5 s, vzorkování dominuje). `use_persistent_data` v kódu zapnuté NENÍ.
