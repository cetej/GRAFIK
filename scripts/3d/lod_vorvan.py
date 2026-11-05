# Vorvaň (Physeter macrocephalus) z průřezů podle předloh, 0 USD (operátor 5. 11.: model z jedné fotky měl rovnou desku na čele,
# hřbet zepředu do špičky a špatný profil těla; „Stáhni si fotky, kolik potřebuješ a udělej ten model pořádně“):
#   blender -b -P scripts/3d/lod_vorvan.py -- out.glb [--tlama 15]
#   python scripts/3d/lod_check.py OUT_DIR --lod scripts/3d/lod_vorvan.py --ref library/plakaty/vorvan/predlohy/silueta-bok.png
# Hřbet a břicho: scripts/3d/vorvan_profily.json z kresby NOAA (předloha 01, public domain), vorvan_profily.py.
# Šířka shora: tabule od operátora (pohled shora 1.b), kontrola letecká fotka NOAA, Tim Cole (předloha 18, public domain).
# Průřez hlavy: nahoře široký a oblý, dolů k úzké čelisti se zužuje (fotky pod vodou G. Barathieu, předlohy 05–07, 22),
# čelo zepředu i shora zaoblené, ne deska. Předlohy a původ: library/plakaty/vorvan/predlohy/NN.puvod.json.
# Osy: x od špičky hlavy (0) k zářezu ocasní ploutve (L), y napříč, z nahoru. Rozměry v DIM se zdrojem, odhad = bez zdroje.
import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix, Vector

DIM = {
    "length": 16.0,       # samec, en.wikipedia Sperm whale
    "width": 1.92,        # 0,12 délky: tabule od operátora, pohled shora 1.b (fotka 18 zešikma dávala 0,15, přeceněno)
    "height": 2.7,        # 0,169 délky: předloha 01 (nejvyšší místo těla, vorvan_profily.py)
    "fluke_span": 3.8,    # 0,24 délky: mezi předlohou 18 (0,26, zešikma) a tabulí od operátora
    "jaw_tip": 0.075,     # podíl délky: špička dolní čelisti za čelem, předloha 01 a 03
    "jaw_hinge": 0.25,    # podíl délky: koutek tlamy, předloha 01 a 03
    "teeth": 24,          # na každé straně dolní čelisti 20–26 (FWC, Sperm whale)
    "flipper_x": 0.31,    # podíl délky: kořen prsní ploutve, předloha 01
    "flipper_len": 1.8,   # odhad podle předlohy 01 (ploutev kolem 0,11 délky)
}
ARGS = sys.argv[sys.argv.index("--") + 1:]
OUT = ARGS[0]
MOUTH = math.radians(float(ARGS[ARGS.index("--tlama") + 1])) if "--tlama" in ARGS else math.radians(15)
L = DIM["length"]
PROF = json.loads((Path(__file__).with_name("vorvan_profily.json")).read_text(encoding="utf-8"))
# šířka těla / délka podle tabule od operátora (pohled shora 1.b nad bokem 1.a, 5. 11.), předloha 18 jen kontrola; čelo shora zaoblené
SIRKA = [(0.0, 0.0), (0.01, 0.05), (0.03, 0.075), (0.06, 0.09), (0.1, 0.1), (0.2, 0.11), (0.3, 0.12), (0.4, 0.12),
         (0.5, 0.115), (0.6, 0.105), (0.7, 0.085), (0.8, 0.058), (0.88, 0.038), (0.94, 0.03), (0.985, 0.026), (1.0, 0.0)]
SEG = 48
FLUKE_PITCH = 35          # stupně, odhad: ocasní ploutev při záběru dolů; při 18° byla ze šikmé kamery jen břit
# hrb a hrbolky na hřbetě jen ve střední čáře: v průřezu by z nich byl prstenec kolem celého těla (kolo 3)
_H = PROF["hrbet"]
HRBET_S = [_H[i] if PROF["x"][i] < 0.1 else sum(_H[max(0, i - 6): i + 7]) / len(_H[max(0, i - 6): i + 7]) for i in range(len(_H))]


def interp(table, x):
    for (x0, y0), (x1, y1) in zip(table, table[1:]):
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return table[-1][1]


def side(x):
    """Hřbet a břicho v metrech z kresby; pod hlavou je v obrysu i zavřená čelist, ta se odečte."""
    xs = PROF["x"]
    top = interp(list(zip(xs, HRBET_S)), x) * L
    bot = interp(list(zip(xs, PROF["bricho"])), x) * L
    jt, jh = DIM["jaw_tip"], DIM["jaw_hinge"]
    if jt - 0.02 < x < jh + 0.06:
        bot += jaw_depth(min(max(x, jt), jh)) * smooth((x - (jt - 0.02)) / 0.03) * (1 - smooth((x - (jh - 0.05)) / 0.07))
    return top, bot


def smooth(t):
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def jaw_depth(x):
    """Výška dolní čelisti v metrech: u špičky 0,2 m, u kloubu 0,45 m (odhad podle předlohy 01, 20 a 03)."""
    t = (x - DIM["jaw_tip"]) / (DIM["jaw_hinge"] - DIM["jaw_tip"])
    return 0.2 + 0.25 * t


DOME = 0.05     # podíl délky: čelo vyklenuté shora i z boku jako polovina elipsoidu (tabule 1.a a 1.b, fotky 05–07), ne deska


def section(x):
    k_dome = 1.0
    if x < DOME:                                         # průřez z konce klenby, zmenšený k její špičce
        k_dome = max(math.sqrt(1 - ((DOME - x) / DOME) ** 2), 0.02)
        x_s = DOME
    else:
        x_s = x
    top, bot = side(x_s)
    zc, hh = (top + bot) / 2 + 0.12 * (1 - k_dome) * (top - bot), max((top - bot) / 2 * k_dome, 0.005)   # špička klenby nad středem: spodek hlavy ustupuje k tlamě
    hw = max(interp(SIRKA, x_s) * L / 2 * k_dome, 0.005)
    if x_s > 0.9:                                        # v boku kresby je u ocasu i ploutev z hrany; násada do ní plynule přechází, bez víčka
        hh *= 1 - 0.55 * smooth((x_s - 0.9) / 0.085)
    ridge = max(interp(list(zip(PROF["x"], PROF["hrbet"])), x_s) - interp(list(zip(PROF["x"], HRBET_S)), x_s), 0) * L if x_s > 0.45 else 0.0
    head = 1 - smooth((x_s - 0.15) / 0.35)               # 1 v hlavě, 0 za ploutvemi; dlouhý přechod, jinak je za hlavou vidět hrana
    n = 2.0 + 1.0 * head                                 # hlava hranatější nahoře, tělo kulaté
    taper = 0.15 + 0.4 * head                            # dole se hlava zužuje k čelisti, tělo jen málo
    pts = []
    for i in range(SEG):
        a = 2 * math.pi * i / SEG
        c, s = math.cos(a), math.sin(a)
        k = 1 - taper * (-s) ** 1.3 if s < 0 else 1.0
        y = hw * k * math.copysign(abs(c) ** (2 / n), c)
        z = zc + hh * math.copysign(abs(s) ** (2 / n), s)
        if s > 0:                                        # hrb a hrbolky jen ve střední čáře hřbetu (předloha 01, tabule 1.a)
            z += ridge * s ** 12
        pts.append((x * L, y, z))
    return pts


def loft(name, rings, cap_front=True, cap_back=True):
    bm = bmesh.new()
    vr = [[bm.verts.new(p) for p in r] for r in rings]
    n = len(rings[0])
    for a, b in zip(vr, vr[1:]):
        for i in range(n):
            bm.faces.new((a[i], a[(i + 1) % n], b[(i + 1) % n], b[i]))
    if cap_front:
        bm.faces.new(list(reversed(vr[0])))
    if cap_back:
        bm.faces.new(vr[-1])
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    for p in mesh.polygons:
        p.use_smooth = True
    return obj


def body():
    xs = [0.0, 0.002, 0.005, 0.009, 0.014, 0.02, 0.028, 0.038, 0.05, 0.065]
    xs += [0.08 + 0.015 * i for i in range(int((0.985 - 0.08) / 0.015) + 1)]
    obj = loft("Tělo", [section(x) for x in xs])
    obj.modifiers.new("hladko", "SUBSURF").levels = 2
    return obj


def jaw():
    """Úzká dolní čelist se zuby, otevřená o MOUTH kolem kloubu u koutku."""
    jt, jh = DIM["jaw_tip"], DIM["jaw_hinge"]
    rings = []
    for i in range(16):
        x = jt + (jh + 0.05 - jt) * i / 15                 # za kloubem pokračuje do hlavy, ne jen dosedá zespodu
        xx = min(x, jh)
        d = jaw_depth(xx)
        w = 0.12 + 0.2 * (xx - jt) / (jh - jt)        # polovina šířky: 0,12 m u špičky, 0,32 m u kloubu (odhad, předloha 20)
        if i == 0:
            d, w = d * 0.6, w * 0.6
        _, bot = side(xx)
        z0 = interp(list(zip(PROF["x"], PROF["bricho"])), xx) * L + max(x - jh, 0) * L * 0.6
        ring = []
        for k in range(24):
            a = 2 * math.pi * k / 24
            c, s = math.cos(a), math.sin(a)
            ring.append((x * L, w * math.copysign(abs(c) ** 0.8, c), z0 + d / 2 + d / 2 * s))
        rings.append(ring)
    obj = loft("Čelist", rings)
    teeth = []
    for side_y in (-1, 1):
        for t in range(DIM["teeth"]):
            x = jt + 0.01 + (jh - jt - 0.04) * t / (DIM["teeth"] - 1)
            w = 0.12 + 0.2 * (x - jt) / (jh - jt)
            z0 = interp(list(zip(PROF["x"], PROF["bricho"])), x) * L + jaw_depth(x)
            bpy.ops.mesh.primitive_cone_add(vertices=8, radius1=0.045, radius2=0.012, depth=0.13,
                                            location=(x * L, side_y * w * 0.7, z0 + 0.05))
            teeth.append(bpy.context.active_object)
    for o in teeth:
        o.select_set(True)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.join()
    # otevřít kolem kloubu (koutek tlamy, spodní hrana hlavy)
    hx = jh * L
    hz = interp(list(zip(PROF["x"], PROF["bricho"])), jh) * L + jaw_depth(jh) * 0.7
    pivot = Vector((hx, 0, hz))
    obj.matrix_world = Matrix.Translation(pivot) @ Matrix.Rotation(-MOUTH, 4, "Y") @ Matrix.Translation(-pivot)   # špička dolů
    return obj


def flipper(side_y):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=1)
    f = bpy.context.active_object
    f.name = "Ploutev"
    x = DIM["flipper_x"]
    top, bot = side(x)
    hw = interp(SIRKA, x) * L / 2
    ln = DIM["flipper_len"]
    f.scale = (ln / 2, 0.06, 0.32)
    f.location = (x * L + ln * 0.35, side_y * hw * 0.72, bot + (top - bot) * 0.3 - 0.2)     # kořen v těle
    f.rotation_euler = (side_y * math.radians(-25), math.radians(25), side_y * math.radians(-12))
    return f


def flukes():
    """Ocasní ploutev shora (předloha 18 a 08): rozpětí 4,2 m, náběžná hrana šikmo dozadu, zářez uprostřed odtokové hrany."""
    half = DIM["fluke_span"] / 2
    x0 = 0.935 * L                                    # kořen náběžné hrany
    outline = [(x0, 0.0), (x0 + 0.25, 0.45), (x0 + 0.55, 1.1), (x0 + 0.85, 1.7), (L + 0.25, half),
               (L + 0.35, half - 0.12), (L + 0.2, 1.4), (L + 0.08, 0.7), (L, 0.12), (L - 0.12, 0.0)]
    pts = outline + [(x, -y) for x, y in reversed(outline[1:-1])]
    top, bot = side(0.975)
    zc = (top + bot) / 2
    bm = bmesh.new()
    vs = [bm.verts.new((x, y, zc)) for x, y in pts]
    bm.faces.new(vs)
    mesh = bpy.data.meshes.new("Ocas")
    bm.to_mesh(mesh)
    obj = bpy.data.objects.new("Ocas", mesh)
    bpy.context.scene.collection.objects.link(obj)
    sol = obj.modifiers.new("tloušťka", "SOLIDIFY")
    sol.thickness, sol.offset = 0.16, 0.0
    # sklon o FLUKE_PITCH dolů jako při záběru: přesně vodorovná ploutev je ze šikmé kamery jen tenká jehla (render 5. 11.)
    pivot = Vector((x0, 0, zc))
    obj.matrix_world = Matrix.Translation(pivot) @ Matrix.Rotation(math.radians(FLUKE_PITCH), 4, "Y") @ Matrix.Translation(-pivot)
    obj.modifiers.new("hladko", "SUBSURF").levels = 2
    return obj


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    parts = [body(), jaw(), flipper(-1), flipper(1), flukes()]
    for p in parts:
        p.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.export_scene.gltf(filepath=str(Path(OUT).resolve()), export_format="GLB", export_apply=True)
    print("bbox L W H", L, DIM["width"], DIM["height"])


main()
