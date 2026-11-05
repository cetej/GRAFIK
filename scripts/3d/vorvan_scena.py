# Blender: vorvaň s průsvitnou kůží, vnitřnostmi a potápěčem ve stejném měřítku, každá vrstva zvlášť (infografika „Spolkl by vorvaň člověka?“).
# Modely: vorvaň --vorvan (library/3d/<id>/<verze>; TRELLIS 2 měl vyhloubené čelo, Hunyuan 3.1 Pro je bez textury),
# potápěč library/3d/potapec-infografika-vorvan/v1/model.glb (TRELLIS 2). Kůže bez textury: skin_material.
# Vnitřnosti: library/plakaty/vorvan/obrazy/organy-vrstva.png jako plocha ve střední rovině těla, jícen jako 3D trubice.
# Pod zámkem těžké práce:  python scripts/3d/velsen_studna_run.py vorvan_scena.py OUT --fmt 16x9 [--w 2400 --h 1000 --samples 48]
# Výstup OUT/<fmt>/kuze.png, vnitrek.png, potapec.png (RGBA, stejná kamera) a body.json (body pro popisky v px).
import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Vector

DATA = Path(__file__).resolve().parents[2]
for up in [DATA, *DATA.parents]:
    if (up / "library" / "3d" / "vorvan-infografika").exists():
        DATA = up
        break
DIVER_GLB = DATA / "library/3d/potapec-infografika-vorvan/v1/model.glb"
ORGANS = DATA / "library/plakaty/vorvan/obrazy/organy-vrstva.png"

LENGTH, DIVER_LEN = 16.0, 2.3          # samec 16 m (Wikipedia), potápěč s ploutvemi 2,3 m
LAYER_PX = (1308, 307)                 # 2D vrstva vorvaně, ze které model vznikl: body z vorvan_stranka.py v jejích px
ORGAN_AT, ORGAN_K, ORGAN_PX = (385, 86), 0.44, (1295, 470)
CAVITY = (600, 200, 470, 108)
THROAT = [(228, 242), (300, 236), (360, 214), (412, 190)]
POINTS = {"Tlama": (150, 258), "Jícen": (345, 222), "Předžaludek": (520, 190), "Hlavní žaludek": (640, 186), "Střevo": (865, 186),
          "tlama_koutek": (290, 252)}


def args():
    p = argparse.ArgumentParser()
    p.add_argument("out")
    p.add_argument("--fmt", choices=("16x9", "9x16"), default="16x9")
    p.add_argument("--w", type=int, default=0)
    p.add_argument("--h", type=int, default=0)
    p.add_argument("--samples", type=int, default=48)
    p.add_argument("--vorvan", default="vorvan-infografika/v1", help="model v library/3d (TRELLIS: vorvan-infografika/v1)")
    p.add_argument("--celo", action="store_true", help="víčko přes prohlubeň v čele (jen model z TRELLIS)")
    p.add_argument("--laloky", action="store_true", help="srovnat zkroucené ocasní laloky do vodorovné roviny (Hunyuan)")
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


def to3d(px, py, lo, hi):
    """Bod 2D vrstvy vorvaně (hlava vlevo) na střední rovinu modelu: měřítko podle délky."""
    m = (hi.x - lo.x) / LAYER_PX[0]
    return Vector((lo.x + px * m, 0.0, hi.z - py * m))


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
    cx, cz = lo.x + CAVITY[0] * m, hi.z - CAVITY[1] * m
    rx, rz = CAVITY[2] * m, CAVITY[3] * m
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


def organs_plane(lo, hi):
    m = (hi.x - lo.x) / LAYER_PX[0]
    w, h = ORGAN_PX[0] * ORGAN_K * m, ORGAN_PX[1] * ORGAN_K * m
    x0, z0 = lo.x + ORGAN_AT[0] * m, hi.z - ORGAN_AT[1] * m
    bpy.ops.mesh.primitive_plane_add(size=1)
    plane = bpy.context.active_object
    plane.name = "Vnitřnosti"
    plane.rotation_euler = (math.radians(90), 0, 0)
    plane.scale = (w, h, 1)
    plane.location = (x0 + w / 2, 0, z0 - h / 2)
    mat = bpy.data.materials.new("Vnitřnosti")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(str(ORGANS))
    em, tr, mix = nt.nodes.new("ShaderNodeEmission"), nt.nodes.new("ShaderNodeBsdfTransparent"), nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(tex.outputs["Color"], em.inputs["Color"])
    nt.links.new(tex.outputs["Alpha"], mix.inputs[0])
    nt.links.new(tr.outputs[0], mix.inputs[1])
    nt.links.new(em.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs[0])
    plane.data.materials.append(mat)
    return plane


def cavity_and_throat(lo, hi, far_y: float):
    m = (hi.x - lo.x) / LAYER_PX[0]
    cx, cz = lo.x + CAVITY[0] * m, hi.z - CAVITY[1] * m
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24)
    cav = bpy.context.active_object
    cav.name = "Tělní dutina"
    cav.scale = (CAVITY[2] * m * 0.86, 0.05, CAVITY[3] * m * 0.86)
    cav.location = (cx, far_y, cz)         # tenká tmavá stěna za vnitřnostmi, na odvrácené straně od kamery
    cav.data.materials.append(emission_mat("Dutina", (0.045, 0.012, 0.013)))
    curve = bpy.data.curves.new("Jícen", "CURVE")
    curve.dimensions = "3D"
    spline = curve.splines.new("BEZIER")
    spline.bezier_points.add(len(THROAT) - 1)
    for bp, (px, py) in zip(spline.bezier_points, THROAT):
        bp.co = to3d(px, py, lo, hi)
        bp.handle_left_type = bp.handle_right_type = "AUTO"
    curve.bevel_depth = 0.16
    curve.bevel_resolution = 6
    tube = bpy.data.objects.new("Jícen", curve)
    bpy.context.collection.objects.link(tube)
    mat = bpy.data.materials.new("Jícen")
    mat.use_nodes = True
    b = mat.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.62, 0.25, 0.21, 1)
    b.inputs["Roughness"].default_value = 0.35
    tube.data.materials.append(mat)
    return [cav, tube]


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
    skin_alpha(whale, lo, hi)
    side = -1 if a.fmt == "16x9" else 1                  # kamera na straně -Y (16:9), nebo +Y (9:16, břicho vpravo)
    inside = [organs_plane(lo, hi), *cavity_and_throat(lo, hi, far_y=-side * 0.5)]

    diver = import_glb(DIVER_GLB)
    dlo, dhi = normalize(diver, DIVER_LEN)
    if not head_is_min_x(diver, dlo, dhi):    # u potápěče je „vyšší“ konec hlava s lahví, ploutve jsou tenké
        diver.rotation_euler = (0, 0, math.radians(180))
        bpy.ops.object.transform_apply(rotation=True)
    mouth = to3d(*POINTS["tlama_koutek"], lo, hi)
    jaw_tip = to3d(40, 262, lo, hi)
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
    pts = {k: to3d(*v, lo, hi) for k, v in POINTS.items()}
    body = {}
    for k, p in pts.items():
        q = world_to_camera_view(scene, cam, p)
        body[k] = [round(q.x * w, 1), round((1 - q.y) * h, 1)]
    (out / "body.json").write_text(json.dumps({"points": body, "px_na_m_u_hlavy": None, "size": [w, h]}, ensure_ascii=False, indent=1), encoding="utf-8")

    skin = [whale, cap] if cap else [whale]
    layers = {"kuze": skin, "vnitrek": inside, "potapec": [diver]}
    for name, show in layers.items():
        for o in [*skin, diver, *inside]:
            o.hide_render = o not in show
        r.filepath = str((out / f"{name}.png").resolve())
        bpy.ops.render.render(write_still=True)
        print("hotovo", name, flush=True)


if __name__ == "__main__":
    main()
