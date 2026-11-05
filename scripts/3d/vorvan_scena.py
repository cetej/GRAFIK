# Blender: vorvaň s průsvitnou kůží, vnitřnostmi a potápěčem ve stejném měřítku, každá vrstva zvlášť (infografika „Spolkl by vorvaň člověka?“).
# Modely: vorvaň --vorvan (library/3d/<id>/<verze>; TRELLIS 2 měl vyhloubené čelo, Hunyuan 3.1 Pro je bez textury),
# potápěč library/3d/potapec-infografika-vorvan/v1/model.glb (TRELLIS 2). Kůže bez textury: skin_material.
# Vnitřnosti: 3D tělesa (organs3d: předžaludek, hlavní žaludek, komůrky, smotané střevo) a jícen jako trubice.
# Pod zámkem těžké práce:  python scripts/3d/velsen_studna_run.py vorvan_scena.py OUT --fmt 16x9 [--w 2400 --h 1000 --samples 48]
# Výstup OUT/<fmt>/kuze.png, vnitrek.png, potapec.png (RGBA, stejná kamera) a body.json (body pro popisky v px).
import argparse
import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Vector

DATA = Path(__file__).resolve().parents[2]
for up in [DATA, *DATA.parents]:
    if (up / "library" / "3d" / "vorvan-infografika").exists():
        DATA = up
        break
DIVER_GLB = DATA / "library/3d/potapec-infografika-vorvan/v1/model.glb"

LENGTH, DIVER_LEN = 16.0, 2.3          # samec 16 m (Wikipedia), potápěč s ploutvemi 2,3 m
LAYER_PX = (1308, 307)                 # 2D vrstva vorvaně, ze které model vznikl: body z vorvan_stranka.py v jejích px
CAVITY = (600, 200, 470, 108)
POINTS = {"Tlama": (150, 258), "Jícen": (349, 245), "Předžaludek": (520, 190), "Hlavní žaludek": (640, 186), "Střevo": (865, 186),
          "tlama_koutek": (290, 252)}


def args():
    p = argparse.ArgumentParser()
    p.add_argument("out")
    p.add_argument("--fmt", choices=("16x9", "9x16"), default="16x9")
    p.add_argument("--w", type=int, default=0)
    p.add_argument("--h", type=int, default=0)
    p.add_argument("--samples", type=int, default=48)
    p.add_argument("--vorvan", default="vorvan-lod/v2", help="model v library/3d; vorvan-lod/v2 z průřezů (lod_vorvan.py, skloněná ocasní ploutev), starší TRELLIS vorvan-infografika/v1")
    p.add_argument("--celo", action="store_true", help="víčko přes prohlubeň v čele (jen model z TRELLIS)")
    p.add_argument("--laloky", action="store_true", help="srovnat zkroucené ocasní laloky do vodorovné roviny (Hunyuan)")
    p.add_argument("--predloha", action="store_true", help="předlohy tvaru pro FLUX: neprůhledný vorvaň a vnitřnosti bez dutiny, světlá hlína")
    return p.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])


def import_glb(path: Path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    meshes = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    world = obj.matrix_world.copy()
    obj.parent = None
    obj.matrix_world = world            # bez rodiče, ale se stejnou polohou
    obj.rotation_mode = "XYZ"           # glTF dává kvaterniony; rotation_euler by jinak nic nedělal
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    for o in [o for o in bpy.data.objects if o not in before and o.type == "EMPTY"]:
        bpy.data.objects.remove(o)
    return obj


def bbox(obj):
    vs = [obj.matrix_world @ v.co for v in obj.data.vertices]
    lo = Vector((min(v.x for v in vs), min(v.y for v in vs), min(v.z for v in vs)))
    hi = Vector((max(v.x for v in vs), max(v.y for v in vs), max(v.z for v in vs)))
    return lo, hi


def normalize(obj, length: float):
    """Nejdelší osa na X, délka `length`, střed v počátku. Vrací (lo, hi)."""
    lo, hi = bbox(obj)
    size = hi - lo
    bpy.ops.object.select_all(action="DESELECT")       # transform_apply působí jen na vybrané
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    if size.y > size.x and size.y >= size.z:
        obj.rotation_euler = (0, 0, math.radians(90))
        bpy.ops.object.transform_apply(rotation=True)
    lo, hi = bbox(obj)
    k = length / (hi.x - lo.x)
    obj.scale = (k, k, k)
    bpy.ops.object.transform_apply(scale=True)
    lo, hi = bbox(obj)
    obj.location = -(lo + hi) / 2
    bpy.ops.object.transform_apply(location=True)
    return bbox(obj)


def skin_material(obj) -> None:
    """Model bez textury (Hunyuan Geometry): tmavě šedá kůže s jemnou vrásčitou strukturou, ať funguje průhlednost i světlo."""
    has_tex = any(n.type == "TEX_IMAGE" for m in obj.data.materials if m and m.node_tree for n in m.node_tree.nodes)
    if has_tex:
        return
    mat = bpy.data.materials.new("Kůže")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 6.0
    noise.inputs["Detail"].default_value = 8.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.028, 0.027, 0.027, 1)
    ramp.color_ramp.elements[1].color = (0.075, 0.072, 0.07, 1)
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.25
    wr = nt.nodes.new("ShaderNodeTexWave")
    wr.inputs["Scale"].default_value = 3.0
    wr.inputs["Distortion"].default_value = 9.0
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(wr.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    bsdf.inputs["Roughness"].default_value = 0.42
    obj.data.materials.clear()
    obj.data.materials.append(mat)


def flatten_flukes(obj, lo, hi, start=0.82, full=0.9, keep=0.18) -> None:
    """Hunyuan zkroutil ocasní laloky (jeden nahoru, druhý dolů, z boku rybí ocas). Vorvaň je má vodorovné:
    zadní část těla se stlačí ke střední výšce ocasního kořene, rozpětí do stran zůstane."""
    span = hi.x - lo.x
    stock = [v.co.z for v in obj.data.vertices if lo.x + (start - 0.02) * span < v.co.x < lo.x + start * span]
    zc = sorted(stock)[len(stock) // 2]
    for v in obj.data.vertices:
        t = (v.co.x - lo.x) / span
        if t > start:
            k = 1 - (1 - keep) * min(1.0, (t - start) / (full - start))
            v.co.z = zc + (v.co.z - zc) * k
    obj.data.update()


def brow_cap(obj, lo, hi):
    """Model z TRELLIS má v čele hlavy hlubokou prohlubeň; po natočení hlavou k divákovi by byla vidět.
    Víčko ve tvaru průřezu hlavy těsně před ní, tmavá kůže; jen nad čelistí, ať nezakryje tlamu."""
    jaw_z = to3d(0, 262, lo, hi).z
    vs = [obj.matrix_world @ v.co for v in obj.data.vertices]
    upper = [v for v in vs if v.z > jaw_z + 0.35]
    front = min(v.x for v in upper)
    ring = [v for v in upper if v.x < front + 0.6]
    y0, y1 = min(v.y for v in ring), max(v.y for v in ring)
    z0, z1 = min(v.z for v in ring), max(v.z for v in ring)
    bpy.ops.mesh.primitive_cube_add(size=1)
    cap = bpy.context.active_object
    cap.name = "Čelo"
    cap.scale = (0.12, (y1 - y0) * 0.92, (z1 - z0) * 0.92)
    cap.location = (front + 0.1, (y0 + y1) / 2, (z0 + z1) / 2)
    bev = cap.modifiers.new("zaobleni", "BEVEL")
    bev.width, bev.segments = min(y1 - y0, z1 - z0) * 0.3, 8
    mat = bpy.data.materials.new("Čelo")
    mat.use_nodes = True
    b = mat.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.05, 0.048, 0.047, 1)
    b.inputs["Roughness"].default_value = 0.55
    cap.data.materials.append(mat)
    return cap


def head_is_min_x(obj, lo, hi) -> bool:
    """Hranatá hlava vorvaně je u konce s větší výškou těla v posledních 12 % délky."""
    vs = [obj.matrix_world @ v.co for v in obj.data.vertices]
    span = hi.x - lo.x

    def height(sel):
        zs = [v.z for v in vs if sel(v.x)]
        return max(zs) - min(zs) if zs else 0
    return height(lambda x: x < lo.x + 0.12 * span) > height(lambda x: x > hi.x - 0.12 * span)


KZ = 1.0     # svislé měřítko vnitřností: 2D vorvaň byl hlubší než model, main() ho změří podle břicha modelu


def belly_kz(obj, lo, hi) -> float:
    """Dutina z 2D vrstvy má sahat do 92 % hloubky těla modelu v jejím středu (jinak vnitřnosti trčí z břicha)."""
    m = (hi.x - lo.x) / LAYER_PX[0]
    cx = lo.x + CAVITY[0] * m
    zs = [(obj.matrix_world @ v.co).z for v in obj.data.vertices if abs((obj.matrix_world @ v.co).x - cx) < 0.25]
    return 0.92 * (hi.z - min(zs)) / ((CAVITY[1] + CAVITY[3]) * m)


def to3d(px, py, lo, hi, kz=None):
    """Bod 2D vrstvy vorvaně (hlava vlevo) na střední rovinu modelu: měřítko podle délky, výška vnitřností × KZ."""
    m = (hi.x - lo.x) / LAYER_PX[0]
    return Vector((lo.x + px * m, 0.0, hi.z - py * m * (KZ if kz is None else kz)))


def emission_mat(name, color, strength=1.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*color, 1)
    em.inputs["Strength"].default_value = strength
    nt.links.new(em.outputs[0], out.inputs[0])
    return mat


def skin_alpha(obj, lo, hi, keep=0.14):
    """Kůže zprůhledněná nad tělní dutinou (elipsa v souřadnicích X, Z jako ve 2D vrstvě), k okraji plynule celá."""
    m = (hi.x - lo.x) / LAYER_PX[0]
    cx, cz = lo.x + CAVITY[0] * m, hi.z - CAVITY[1] * m * KZ
    rx, rz = CAVITY[2] * m, CAVITY[3] * m * KZ
    for mat in obj.data.materials:
        nt = mat.node_tree
        bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
        tc = nt.nodes.new("ShaderNodeTexCoord")
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(tc.outputs["Object"], sep.inputs[0])

        def op(kind, a, b):
            n = nt.nodes.new("ShaderNodeMath")
            n.operation = kind
            for i, v in enumerate((a, b)):
                if isinstance(v, (int, float)):
                    n.inputs[i].default_value = v
                else:
                    nt.links.new(v, n.inputs[i])
            return n.outputs[0]
        dx = op("DIVIDE", op("SUBTRACT", sep.outputs["X"], cx), rx)
        dz = op("DIVIDE", op("SUBTRACT", sep.outputs["Z"], cz), rz)
        d = op("SQRT", op("ADD", op("MULTIPLY", dx, dx), op("MULTIPLY", dz, dz)), 0)
        fade = op("MINIMUM", op("MAXIMUM", op("DIVIDE", op("SUBTRACT", d, 0.92), 0.08), 0.0), 1.0)     # ostrý okraj řezu, ne šmouha (operátor 5. 11.)
        alpha = op("ADD", keep, op("MULTIPLY", fade, 1 - keep))
        nt.links.new(alpha, bsdf.inputs["Alpha"])


def organ_mat(name, color, bump_kind="NOISE", scale=6.0, strength=0.5):
    """Tkáň: barva, podpovrchový rozptyl a reliéf (svalové pruhy nebo záhyby sliznice), světlo jako na těle."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = 0.38
    b.inputs["Subsurface Weight"].default_value = 0.25
    b.inputs["Subsurface Radius"].default_value = (0.3, 0.08, 0.06)
    tex = nt.nodes.new("ShaderNodeTexWave" if bump_kind == "WAVE" else "ShaderNodeTexNoise")
    tex.inputs["Scale"].default_value = scale
    if bump_kind == "WAVE":
        tex.inputs["Distortion"].default_value = 2.0
    else:
        tex.inputs["Detail"].default_value = 6.0
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = strength
    nt.links.new(tex.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    return mat


# Trávicí trubice jako jeden souvislý tvar (operátor 5. 11.: oddělené koule vypadaly jako „rozházené hračky“ a potrava se
# „teleportuje“). Body ve 2D vrstvě vorvaně (px, jako POINTS) a poloměr v metrech: jícen, předžaludek, krček, hlavní žaludek,
# dvě spojovací komůrky, střevo; to pak pokračuje do klubka. Velikosti odhad podle délky 16 m, komory zjednodušené.
TRACT = [(300, 274, 0.2), (328, 262, 0.16), (370, 228, 0.16), (412, 192, 0.17),     # jícen z hltanu za koutkem tlamy (operátor 5. 11.)
         (450, 184, 0.34), (490, 186, 0.6), (530, 192, 0.64), (570, 198, 0.44), (600, 196, 0.22),
         (625, 190, 0.48), (655, 186, 0.56), (688, 190, 0.38), (708, 195, 0.18),
         (726, 198, 0.29), (746, 200, 0.14), (766, 200, 0.27), (786, 198, 0.11), (806, 194, 0.09)]
PART = [("Jícen", 4), ("Předžaludek", 9), ("Hlavní žaludek", 18)]      # do kterého klíčového bodu sahá která tkáň


def catmull(ps, n=10):
    out = []
    ext = [ps[0]] + ps + [ps[-1]]
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
        for k in range(n):
            s = k / n
            out.append(tuple(0.5 * ((2 * b) + (-a + c) * s + (2 * a - 5 * b + 4 * c - d) * s * s + (-a + 3 * b - 3 * c + d) * s ** 3)
                             for a, b, c, d in zip(p0, p1, p2, p3)) + (i - 1 + s,))
    out.append(tuple(ps[-1]) + (len(ps) - 1,))
    return out


def tract(lo, hi):
    keys = []
    for px, py, r in TRACT:
        v = to3d(px, py, lo, hi)
        keys.append((v.x, v.y, v.z, r))
    path = [(x, y, z, r, k) for x, y, z, r, k in catmull(keys, 12)]
    # klubko střeva navazuje na konec: smyčky kolem bodu Střevo, poloměr trubice 0,085 m
    gut = to3d(*POINTS["Střevo"], lo, hi)
    last = Vector(path[-1][:3])
    coil = []
    n = 900
    for i in range(1, n):
        s = 2 * math.pi * i / n * 12
        c = Vector((math.sin(s * 0.97 - 1.3) * math.cos(s * 0.31), 0.32 * math.sin(s * 1.23 + 1.0) * math.cos(s * 0.17),
                    0.45 * math.cos(s * 0.89) * math.sin(s * 0.43 + 0.5)))
        q = gut + c * 0.95              # hustší klubko, ne řídké drátěné kroužky
        w = min(i / 40, 1.0)                     # prvních 40 bodů plynule od konce komůrek do klubka
        q = last.lerp(q, w)
        coil.append((q.x, q.y, q.z, 0.1, len(TRACT) + i / n))
    path += coil
    # trubice podél cesty: kruhový průřez (napříč těla stlačený), rámy bez kroucení (parallel transport)
    seg = 20
    bm = bmesh.new()
    rings, mats = [], []
    normal = None
    for i, (x, y, z, r, k) in enumerate(path):
        c = Vector((x, y, z))
        nxt = Vector(path[min(i + 1, len(path) - 1)][:3])
        prv = Vector(path[max(i - 1, 0)][:3])
        tan = (nxt - prv).normalized()
        if normal is None:
            normal = tan.cross(Vector((0, 1, 0))).normalized()
        normal = (normal - tan * normal.dot(tan)).normalized()
        bin_ = tan.cross(normal)
        ring = []
        for j in range(seg):
            a = 2 * math.pi * j / seg
            off = normal * (r * math.cos(a)) + bin_ * (r * math.sin(a))
            off.y *= 0.8 if r > 0.25 else 1.0
            ring.append(bm.verts.new(c + off))
        rings.append(ring)
        mats.append(next((m for m, (_, upto) in enumerate(PART) if k < upto), len(PART)))
    for i in range(len(rings) - 1):
        for j in range(seg):
            f = bm.faces.new((rings[i][j], rings[i][(j + 1) % seg], rings[i + 1][(j + 1) % seg], rings[i + 1][j]))
            f.material_index = mats[i]
            f.smooth = True
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])
    mesh = bpy.data.meshes.new("Trávicí trubice")
    bm.to_mesh(mesh)
    obj = bpy.data.objects.new("Trávicí trubice", mesh)
    bpy.context.collection.objects.link(obj)
    for mat in (organ_mat("Jícen", (0.6, 0.26, 0.22), "WAVE", 6.0, 0.4),
                organ_mat("Předžaludek", (0.56, 0.2, 0.19), "WAVE", 3.0, 0.6),          # svalová stěna, bez trávicích šťáv
                organ_mat("Hlavní žaludek", (0.66, 0.33, 0.27), "NOISE", 9.0, 0.8),     # záhyby sliznice, tady se tráví
                organ_mat("Střevo", (0.76, 0.46, 0.39), "NOISE", 14.0, 0.3)):
        obj.data.materials.append(mat)
    return obj


def organs3d(lo, hi):
    """Vnitřnosti: jedna souvislá trávicí trubice od tlamy po klubko střeva."""
    return [tract(lo, hi)]


def cavity(lo, hi, far_y: float):
    m = (hi.x - lo.x) / LAYER_PX[0]
    cx, cz = lo.x + CAVITY[0] * m, hi.z - CAVITY[1] * m * KZ
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24)
    cav = bpy.context.active_object
    cav.name = "Tělní dutina"
    cav.scale = (CAVITY[2] * m * 0.86, 0.05, CAVITY[3] * m * 0.86 * KZ)
    cav.location = (cx, far_y, cz)         # tenká tmavá stěna za vnitřnostmi, na odvrácené straně od kamery
    cav.data.materials.append(emission_mat("Dutina", (0.045, 0.012, 0.013)))
    return [cav]


def look(cam, pos: Vector, target: Vector, up: Vector):
    f = (target - pos).normalized()
    r = f.cross(up).normalized()
    u = r.cross(f)
    cam.matrix_world = Matrix((r, u, -f)).transposed().to_4x4() @ Matrix.Identity(4)
    cam.matrix_world.translation = pos


def frame(scene, cam, objs, pos_dir: Vector, target: Vector, up: Vector, fill=0.9):
    """Kamera ve směru `pos_dir` od cíle, vzdálenost a posun tak, aby obsah vyplnil `fill` snímku."""
    pts = [o.matrix_world @ v.co for o in objs for i, v in enumerate(o.data.vertices) if i % 25 == 0]
    dist = 40.0
    for _ in range(6):
        look(cam, target + pos_dir.normalized() * dist, target, up)
        cam.data.shift_x = cam.data.shift_y = 0
        bpy.context.view_layer.update()
        q = [world_to_camera_view(scene, cam, p) for p in pts]
        xs, ys = [p.x for p in q], [p.y for p in q]
        span = max((max(xs) - min(xs)), (max(ys) - min(ys)))
        dist *= span / fill
    look(cam, target + pos_dir.normalized() * dist, target, up)
    bpy.context.view_layer.update()
    q = [world_to_camera_view(scene, cam, p) for p in pts]
    xs, ys = [p.x for p in q], [p.y for p in q]
    aspect = scene.render.resolution_x / scene.render.resolution_y
    big = max(aspect, 1.0)
    cam.data.shift_x = ((min(xs) + max(xs)) / 2 - 0.5) * (aspect / big)
    cam.data.shift_y = ((min(ys) + max(ys)) / 2 - 0.5) / big


def main():
    a = args()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    w, h = (a.w or 2400, a.h or 1000) if a.fmt == "16x9" else (a.w or 900, a.h or 2200)
    r = scene.render
    r.engine, r.film_transparent = "CYCLES", True
    r.resolution_x, r.resolution_y, r.resolution_percentage = w, h, 100
    scene.cycles.samples, scene.cycles.use_denoising = a.samples, True
    scene.cycles.device = "CPU"
    scene.cycles.transparent_max_bounces = 24
    world = bpy.data.worlds.new("Moře")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.11, 0.26, 0.34, 1)    # světlejší voda (operátor 5. 11.)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.9
    scene.world = world
    sun = bpy.data.objects.new("Slunce", bpy.data.lights.new("Slunce", "SUN"))
    sun.data.energy, sun.data.angle = 3.2, math.radians(12)
    sun.rotation_euler = (math.radians(30), math.radians(-20), math.radians(10))
    bpy.context.collection.objects.link(sun)

    whale = import_glb(DATA / "library" / "3d" / a.vorvan / "model.glb")
    lo, hi = normalize(whale, LENGTH)
    if not head_is_min_x(whale, lo, hi):
        whale.rotation_euler = (0, 0, math.radians(180))
        bpy.ops.object.transform_apply(rotation=True)
        lo, hi = bbox(whale)
    skin_material(whale)
    if a.laloky:
        flatten_flukes(whale, lo, hi)
        lo, hi = bbox(whale)
    cap = brow_cap(whale, lo, hi) if a.celo else None
    global KZ
    KZ = belly_kz(whale, lo, hi)
    print("KZ", round(KZ, 3), flush=True)
    if a.predloha:     # světlá matná hlína: FLUX z ní čte tvar a světlo, kůži dodá sám (operátor 5. 11.: model vypadal jako z gumy)
        for mat in whale.data.materials:
            b = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
            for link in list(b.inputs["Base Color"].links):
                mat.node_tree.links.remove(link)
            b.inputs["Base Color"].default_value = (0.42, 0.42, 0.42, 1)
            b.inputs["Roughness"].default_value = 0.8
    else:
        skin_alpha(whale, lo, hi)
    side = -1 if a.fmt == "16x9" else 1                  # kamera na straně -Y (16:9), nebo +Y (9:16, břicho vpravo)
    inside = [*organs3d(lo, hi), *cavity(lo, hi, far_y=-side * 0.6)]

    diver = import_glb(DIVER_GLB)
    dlo, dhi = normalize(diver, DIVER_LEN)
    if not head_is_min_x(diver, dlo, dhi):    # u potápěče je „vyšší“ konec hlava s lahví, ploutve jsou tenké
        diver.rotation_euler = (0, 0, math.radians(180))
        bpy.ops.object.transform_apply(rotation=True)
    mouth = to3d(*POINTS["tlama_koutek"], lo, hi)
    jaw_tip = to3d(40, 262, lo, hi, kz=1.0)
    if a.fmt == "16x9":
        diver.rotation_euler = (0, 0, math.radians(180))           # hlavou k vorvani (+X), lahev nahoru
        diver.location = (lo.x - DIVER_LEN / 2 - 0.15, -0.2, jaw_tip.z)     # ve stejné vzdálenosti od kamery jako vorvaň
        pos_dir, up = Vector((-0.62, -1.0, 0.12)), Vector((0, 0, 1))       # natočený hlavou k divákovi (~32°)
        light = Vector((0.3, 1.0, -1.0))                            # shora zepředu
    else:
        # před tlamou ve stejné rovině jako vorvaň (jinak ho perspektiva zvětší), na stránce nad čelistí hlavou dolů k ní
        diver.rotation_euler = (0, 0, math.radians(180))
        diver.location = (lo.x - DIVER_LEN / 2 - 0.15, 0.2, jaw_tip.z)
        pos_dir, up = Vector((-0.62, 1.0, 0.0)), Vector((-1, 0, 0))     # svisle hlavou nahoru, břicho vpravo, hlavou k divákovi
        light = Vector((1.0, -1.0, -0.3))                           # „shora“ stránky = od hlavy, zepředu
    sun.rotation_euler = (-light).to_track_quat("Z", "Y").to_euler()
    bpy.context.view_layer.update()

    cam = bpy.data.objects.new("Kamera", bpy.data.cameras.new("Kamera"))
    cam.data.lens = 50
    bpy.context.collection.objects.link(cam)
    scene.camera = cam
    target = Vector(((lo.x + hi.x) / 2, 0, (lo.z + hi.z) / 2))
    frame(scene, cam, [whale, diver], pos_dir, target, up)

    out = Path(a.out) / a.fmt
    out.mkdir(parents=True, exist_ok=True)
    pts = {k: to3d(*v, lo, hi, kz=1.0 if k in ("Tlama", "tlama_koutek") else None) for k, v in POINTS.items()}
    body = {}
    for k, p in pts.items():
        q = world_to_camera_view(scene, cam, p)
        body[k] = [round(q.x * w, 1), round((1 - q.y) * h, 1)]
    (out / "body.json").write_text(json.dumps({"points": body, "px_na_m_u_hlavy": None, "size": [w, h]}, ensure_ascii=False, indent=1), encoding="utf-8")

    skin = [whale, cap] if cap else [whale]
    layers = {"kuze": skin, "vnitrek": inside, "potapec": [diver]}
    if a.predloha:
        layers = {"predloha-kuze": skin, "predloha-vnitrek": [o for o in inside if o.name != "Tělní dutina"]}
    for name, show in layers.items():
        for o in [*skin, diver, *inside]:
            o.hide_render = o not in show
        r.filepath = str((out / f"{name}.png").resolve())
        bpy.ops.render.render(write_still=True)
        print("hotovo", name, flush=True)


if __name__ == "__main__":
    main()
