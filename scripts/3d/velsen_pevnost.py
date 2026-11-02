# Blender: the Roman fort Velsen 1 and its harbour from the book's plan (phase 3 with wells, 1.92 px = 1 m). Ground, rampart, towers, jetties, aqueduct and wells lie where the plan has them; the houses in the blocks and the ships are a reconstruction, heights are twice real.
#   blender -b --factory-startup -P scripts/3d/velsen_pevnost.py -- LIB OUT_DIR [--w 1800] [--h 900] [--samples 128] [--gpu]
# Writes pevnost.png and body.json (the wells and the places of the scenarios in pixels).
import json
import math
import random
import sys
from pathlib import Path

import bmesh
import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector
from mathutils.geometry import tessellate_polygon

ARGS = sys.argv[sys.argv.index("--") + 1:]
LIB, OUT = Path(ARGS[0]).resolve(), Path(ARGS[1]).resolve()


def arg(name, default):
    return type(default)(ARGS[ARGS.index(name) + 1]) if name in ARGS else default


W, H, SAMPLES = arg("--w", 1800), arg("--h", 900), arg("--samples", 128)
OUT.mkdir(parents=True, exist_ok=True)
random.seed(28)
PX_M, RISE = 1.92, 2.0     # the plan's scale bar; heights exaggerated, or the rampart is a thread at this scale
LAND_Z, FORT_Z = 0.7, 1.0


def m(px, py, z=0.0):
    return Vector(((px - 400) / PX_M, (400 - py) / PX_M, z))


def zp(x, y, z=0.0):    # read from a zoom of the plan's west part
    return m(20 + x / 3, 130 + y / 3, z)


def vp(x, y, z=0.0):    # read from a zoom of the plan's east part
    return m(330 + x / 2.5, 120 + y / 2.5, z)


def rgb(h):
    def lin(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return (lin(int(h[1:3], 16) / 255), lin(int(h[3:5], 16) / 255), lin(int(h[5:7], 16) / 255), 1.0)


def noise_mat(name, dark, light, scale, bump=0.4, rough=0.9, stretch=(1, 1, 1), space="Object"):
    m_ = bpy.data.materials.new(name)
    m_.use_nodes = True
    n, l = m_.node_tree.nodes, m_.node_tree.links
    p = n["Principled BSDF"]
    tc, mp, nz, r = n.new("ShaderNodeTexCoord"), n.new("ShaderNodeMapping"), n.new("ShaderNodeTexNoise"), n.new("ShaderNodeValToRGB")
    mp.inputs["Scale"].default_value = (scale * stretch[0], scale * stretch[1], scale * stretch[2])
    nz.inputs["Detail"].default_value = 8.0
    l.new(tc.outputs[space], mp.inputs["Vector"])
    l.new(mp.outputs["Vector"], nz.inputs["Vector"])
    r.color_ramp.elements[0].position, r.color_ramp.elements[0].color = 0.34, rgb(dark)
    r.color_ramp.elements[1].position, r.color_ramp.elements[1].color = 0.66, rgb(light)
    l.new(nz.outputs["Fac"], r.inputs["Fac"])
    l.new(r.outputs["Color"], p.inputs["Base Color"])
    p.inputs["Roughness"].default_value = rough
    b = n.new("ShaderNodeBump")
    b.inputs["Strength"].default_value, b.inputs["Distance"].default_value = bump, 0.25
    l.new(nz.outputs["Fac"], b.inputs["Height"])
    l.new(b.outputs["Normal"], p.inputs["Normal"])
    return m_


MAT = {
    "water": noise_mat("Voda", "#3f6070", "#4b6f7f", 0.25, 0.04, 0.18),
    "fort": noise_mat("Pevnost", "#8d7a55", "#ab9a70", 0.35, 0.5, 0.95),
    "land": noise_mat("Kraj", "#565c38", "#7d8050", 0.09, 0.7, 0.95),
    "wall": noise_mat("Násep", "#6f6238", "#8d7f4e", 0.3, 0.7, 0.95),
    "bank": noise_mat("Břeh", "#4a4231", "#6a5f46", 0.8, 0.4, 0.95),
    "timber": noise_mat("Dřevo", "#3e2e1e", "#6d5535", 0.9, 0.5, 0.85, (1, 1, 5)),
    "top": noise_mat("Ochoz", "#6f5e3e", "#8c7a55", 1.2, 0.4, 0.9),
    "plaster": noise_mat("Omítka", "#b6ab93", "#d3cab3", 1.5, 0.15, 0.9),
    "thatch": noise_mat("Doškový", "#5e4d2c", "#8a7446", 2.5, 0.8, 0.95, (1, 1, 6)),
    "plank": noise_mat("Prkna", "#5c4a30", "#8a7450", 3.0, 0.4, 0.85),
    "rim": noise_mat("Roubení", "#2e2316", "#58452c", 3.0, 0.3, 0.85),
}


def obj(name, verts, faces, mat, smooth=False):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], faces)
    me.update()
    if smooth:
        me.shade_smooth()
    me.materials.append(mat)
    o = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(o)
    return o


def plate(name, polys, z, mat):
    """Land from the plan's polygons (with holes), with its bank down into the water."""
    verts, faces, bank_v, bank_f = [], [], [], []
    for loops in polys:
        pts = [[m(x, y, z) for x, y in loop] for loop in loops]
        start = len(verts)
        flat = [v for loop in pts for v in loop]
        verts += flat
        for tri in tessellate_polygon(pts):
            faces.append(tuple(start + i for i in tri))
        for loop in pts:
            s = len(bank_v)
            for v in loop:
                bank_v += [v, Vector((v.x, v.y, -2.0))]
            n = len(loop)
            for i in range(n):
                j = (i + 1) % n
                bank_f.append((s + 2 * i, s + 2 * j, s + 2 * j + 1, s + 2 * i + 1))
    obj(name, verts, faces, mat)
    obj(f"{name} břeh", bank_v, bank_f, MAT["bank"])


def ribbon(name, line, width, z0, z1, mat, top=None):
    """A wall along a polyline: both faces and the top."""
    vl, vr = [], []
    for i, p in enumerate(line):
        a = (p - line[i - 1]) if i else (line[1] - p)
        b = (line[i + 1] - p) if i < len(line) - 1 else a
        d = (a.normalized() + b.normalized()).normalized()
        side = Vector((-d.y, d.x, 0)) * (width / 2)
        cos = max(0.5, abs(side.normalized().dot(Vector((-a.y, a.x, 0)).normalized())))
        side /= cos
        vl.append(p + side)
        vr.append(p - side)
    verts, faces, faces_top = [], [], []
    n = len(line)
    for side_pts in (vl, vr):
        for q in side_pts:
            verts += [Vector((q.x, q.y, z0)), Vector((q.x, q.y, z1))]
    for i in range(n - 1):
        faces.append((2 * i, 2 * i + 2, 2 * i + 3, 2 * i + 1))
        faces.append((2 * n + 2 * i + 2, 2 * n + 2 * i, 2 * n + 2 * i + 1, 2 * n + 2 * i + 3))
        faces_top.append((2 * i + 1, 2 * i + 3, 2 * n + 2 * i + 3, 2 * n + 2 * i + 1))
    faces.append((0, 1, 2 * n + 1, 2 * n))
    faces.append((2 * n - 2, 2 * n + 2 * n - 2, 2 * n + 2 * n - 1, 2 * n - 1))
    o = obj(name, verts, faces + faces_top, mat)
    if top:
        o.data.materials.append(top)
        for pol in o.data.polygons[len(faces):]:
            pol.material_index = 1
    return o


def box(name, c, size, mat, rot=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=c)
    o = bpy.context.object
    o.name = name
    o.scale = size
    o.rotation_euler = (0, 0, rot)
    o.data.materials.append(mat)
    return o


def house(c, length, width, height, rot, roof_mat="thatch", z=FORT_Z):
    """Plastered walls and a thatched roof with a ridge along the length."""
    h = height * RISE
    box("Dům", (c.x, c.y, z + h / 2), (length, width, h), MAT["plaster"], rot)
    ca, sa = math.cos(rot), math.sin(rot)
    over, rise = 0.5, width * 0.55 * RISE * 0.6

    def at(u, v, w):
        return Vector((c.x + u * ca - v * sa, c.y + u * sa + v * ca, z + h + w))
    L, B = length / 2 + over, width / 2 + over
    verts = [at(-L, -B, -0.2), at(L, -B, -0.2), at(L, B, -0.2), at(-L, B, -0.2), at(-L + 1.2, 0, rise), at(L - 1.2, 0, rise)]
    obj("Střecha", verts, [(0, 1, 5, 4), (2, 3, 4, 5), (1, 2, 5), (3, 0, 4), (3, 2, 1, 0)], MAT[roof_mat])


def fill_block(q, width=7.0, gap=4.5):
    """Rows of long houses over a block of the plan: corners a, b, c, d, with the length along a to b."""
    a, b, c, d = q
    across = max((d - a).length, (c - b).length)
    rows = max(1, int((across - 2) // (width + gap)))
    rot = math.atan2((b - a).y, (b - a).x)
    for i in range(rows):
        t = (i + 0.5) / rows
        p0, p1 = a.lerp(d, t), b.lerp(c, t)
        length = (p1 - p0).length * 0.86
        centre = p0.lerp(p1, 0.5)
        house(centre, length, width, random.uniform(2.6, 3.1), rot)


def tower(c, side=4.6, height=7.5, rot=0.0):
    h = height * RISE
    box("Věž", (c.x, c.y, FORT_Z + h / 2), (side, side, h), MAT["timber"], rot)
    box("Ochoz věže", (c.x, c.y, FORT_Z + h + 0.15), (side + 1.0, side + 1.0, 0.3), MAT["top"], rot)


def jetty(line, width=4.0):
    ribbon("Molo", [p + Vector((0, 0, 0)) for p in line], width, 1.5, 1.9, MAT["plank"])
    total = 0.0
    for a, b in zip(line, line[1:]):
        steps = max(1, int((b - a).length // 6))
        side = Vector((-(b - a).y, (b - a).x, 0)).normalized() * (width / 2 - 0.3)
        for i in range(steps):
            p = a.lerp(b, i / steps)
            for s in (side, -side):
                box("Pilota", (p.x + s.x, p.y + s.y, 0.7), (0.35, 0.35, 1.6), MAT["timber"])
        total += (b - a).length


def ship(c, rot, length=20.0, beam=4.2):
    """A plain hull with a bare mast at a jetty: a reconstruction, the plan has only the jetties."""
    ca, sa = math.cos(rot), math.sin(rot)

    def at(u, v, w):
        return (c.x + u * ca - v * sa, c.y + u * sa + v * ca, w)
    rows, verts, faces = 16, [], []
    for i in range(rows + 1):
        t = i / rows
        half = beam / 2 * math.sin(math.pi * t) ** 0.6
        u = (t - 0.5) * length
        sheer = 2.2 + 1.2 * abs(2 * t - 1) ** 3
        verts += [at(u, -half, sheer), at(u, -half * 0.6, 0.0), at(u, half * 0.6, 0.0), at(u, half, sheer)]
    for i in range(rows):
        a = i * 4
        for k in range(3):
            faces.append((a + k, a + k + 1, a + 4 + k + 1, a + 4 + k))
        faces.append((a + 3, a, a + 4, a + 7))     # the deck
    obj("Loď", verts, faces, MAT["timber"])
    x, y, _ = at(0, 0, 0)
    box("Stěžeň", (x, y, 2.4 + 5.0), (0.25, 0.25, 10.0), MAT["timber"])


def well(px_py, big=False):
    c = m(*px_py)
    s = 2.6 if big else 1.8
    for dx, dy, sx, sy in ((0, s / 2, s, 0.35), (0, -s / 2, s, 0.35), (s / 2, 0, 0.35, s), (-s / 2, 0, 0.35, s)):
        box("Roubení", (c.x + dx, c.y + dy, FORT_Z + 0.6), (sx, sy, 1.2), MAT["rim"])
    box("Otvor", (c.x, c.y, FORT_Z + 0.1), (s, s, 0.05), MAT["rim"])


WELLS_RED = {"W.2": (449.2, 304), "W.5": (430, 317.2), "W.8": (496.4, 337.6), "W.1": (570.8, 518.8), "W.20": (377.6, 504), "W.24": (373.6, 540), "W.16": (484.4, 557.6), "S221": (223.3, 442.7), "S190": (119, 457.7)}
WELLS_DARK = [(453.6, 318), (438.4, 333), (448, 370.8), (354.8, 506), (488.4, 577.6), (199.3, 215.3), (209, 218.3), (172.3, 276), (121, 286.7), (96.7, 289.3), (66.7, 283), (302, 296.3),
              (169.7, 370.7), (192.3, 369.3), (221, 427.3), (110, 376.3), (125, 411.3), (133, 423.7), (149.3, 437.3), (133, 448), (159, 446.7), (129, 469.7)]


def build():
    shapes = json.loads((LIB / "pevnost/plan.json").read_text(encoding="utf-8"))
    bpy.ops.mesh.primitive_plane_add(size=1600, location=(0, 0, 0))
    bpy.context.object.data.materials.append(MAT["water"])
    plate("Kraj", shapes["land"], LAND_Z, MAT["land"])
    plate("Kraj za plánem", [[[(-900, 640), (760, 640), (760, 1500), (-900, 1500)]], [[(-900, -300), (2, -300), (2, 660), (-900, 660)]]], LAND_Z - 0.02, MAT["land"])
    plate("Pevnost", shapes["fort"], FORT_Z, MAT["fort"])
    plate("Násep", shapes["wall"], FORT_Z + 2.4, MAT["wall"])
    # the box rampart, with gaps at the gates
    h = FORT_Z + 3.6 * RISE
    west = [[zp(245, 70), zp(165, 180)],
            [zp(145, 205), zp(100, 255), zp(88, 300), zp(230, 510), zp(320, 640), zp(405, 775), zp(470, 870), zp(570, 960), zp(640, 950), zp(775, 885)],
            [zp(805, 870), zp(980, 785)]]
    east = [[vp(50, 680), vp(178, 765), vp(298, 852), vp(420, 935), vp(543, 973), vp(650, 910), vp(725, 820), vp(820, 848)]]
    inner = [[vp(45, 675), vp(45, 590)], [vp(60, 545), vp(90, 425), vp(190, 400)]]
    for line in west + east + inner:
        ribbon("Val", line, 5.2, 0.2, h, MAT["timber"], MAT["top"])
    for p in (zp(92, 282), zp(232, 513), zp(403, 775), zp(578, 958), vp(178, 765), vp(298, 852), vp(420, 935), vp(543, 973), vp(650, 910), vp(820, 848)):
        tower(p)
    for p in (zp(165, 180), zp(145, 205), zp(775, 885), zp(805, 870), vp(45, 590), vp(60, 545), vp(190, 400)):
        tower(p, 4.2, 8.0)
    # the blocks of the west fort: only their outline is on the plan, the houses are a reconstruction
    for q in (((295, 92), (680, 360), (620, 490), (205, 212)), ((170, 252), (290, 335), (290, 455), (122, 312)), ((312, 352), (622, 520), (505, 712), (312, 570)),
              ((632, 585), (745, 665), (635, 820), (522, 735)), ((350, 660), (610, 860), (578, 912), (330, 700)), ((715, 395), (780, 470), (765, 615), (640, 525)),
              ((715, 245), (780, 290), (780, 400), (715, 360)), ((797, 305), (855, 345), (860, 462), (800, 420)), ((875, 360), (975, 432), (945, 510), (880, 480))):
        fill_block([zp(*p) for p in q])
    fill_block([vp(155, 440), vp(200, 480), vp(135, 565), vp(90, 525)], 10.0, 2.0)
    house(zp(555, 505), 12, 9, 4.0, math.radians(35))     # the granary
    # the shipshed: a long roof on posts
    a, b, c, d = vp(140, 560), vp(178, 565), vp(160, 668), vp(122, 660)
    centre = (a + b + c + d) / 4
    rot = math.atan2((c - b).y, (c - b).x)
    house(centre, (c - b).length, (b - a).length, 3.2, rot)
    # the aqueduct on trestles
    p0, p1 = zp(945, 505), zp(615, 935)
    ribbon("Akvadukt", [p0, p1], 1.0, FORT_Z + 3.0, FORT_Z + 3.7, MAT["timber"])
    steps = int((p1 - p0).length // 9)
    for i in range(steps + 1):
        q = p0.lerp(p1, i / steps)
        box("Podpěra", (q.x, q.y, FORT_Z + 1.5), (0.5, 0.5, 3.0), MAT["timber"])
    # jetties and the mole
    jetty([vp(545, 75), vp(625, 100), vp(675, 150)])
    jetty([vp(625, 390), vp(880, 355)])
    jetty([vp(645, 650), vp(820, 545), vp(915, 518)])
    jetty([vp(900, 1100), vp(1125, 985)])
    ribbon("Hráz", [vp(525, 250), vp(540, 60)], 4.5, -1.0, FORT_Z + 0.6, MAT["wall"])
    for a, b, off, t in ((vp(625, 390), vp(880, 355), -7.5, 0.45), (vp(625, 390), vp(880, 355), 7.5, 0.72), (vp(645, 650), vp(820, 545), 7.5, 0.6), (vp(900, 1100), vp(1125, 985), -7.5, 0.5)):
        d = (b - a).normalized()
        ship(a.lerp(b, t) + Vector((-d.y, d.x, 0)) * off, math.atan2(d.y, d.x))
    for px_py in WELLS_DARK:
        well(px_py)
    for name, px_py in WELLS_RED.items():
        well(px_py, name == "W.2")


def setup():
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    c = sc.cycles
    c.samples, c.use_denoising, c.device = SAMPLES, True, "CPU"
    if "--gpu" in ARGS:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "OPTIX"
        prefs.get_devices()
        gpus = [d for d in prefs.devices if d.type == "OPTIX"]
        for d in prefs.devices:
            d.use = d in gpus
        c.device = "GPU" if gpus else "CPU"
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = W, H, 100
    sc.render.image_settings.file_format, sc.render.image_settings.color_mode = "PNG", "RGB"
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
    world = bpy.data.worlds.new("Svět")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.62, 0.66, 0.72, 1)
    world.node_tree.nodes["Background"].inputs[1].default_value = 0.55
    sc.world = world
    sun = bpy.data.lights.new("Slunce", "SUN")
    sun.energy, sun.angle = 3.2, math.radians(4)
    s = bpy.data.objects.new("Slunce", sun)
    s.rotation_euler = (math.radians(58), 0, math.radians(-40))
    bpy.context.collection.objects.link(s)
    cam = bpy.data.cameras.new("Kamera")
    cam.sensor_fit = "HORIZONTAL"
    cam.lens = arg("--lens", 58.0)
    cam.clip_end = 5000
    co = bpy.data.objects.new("Kamera", cam)
    bpy.context.collection.objects.link(co)
    target = Vector((arg("--tx", -18.0), arg("--ty", 16.0), 0.0))
    el, az = math.radians(arg("--el", 42.0)), math.radians(arg("--az", 8.0))
    dist = arg("--dist", 560.0)
    co.location = target + Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el))) * dist
    co.rotation_euler = (target - co.location).to_track_quat("-Z", "Y").to_euler()
    sc.camera = co
    return sc, co


def main():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    build()
    sc, co = setup()
    bpy.context.view_layer.update()

    def px(v):
        p = world_to_camera_view(sc, co, Vector(v))
        return (round(p.x * W, 1), round((1 - p.y) * H, 1))

    points = {name: px(m(*xy, FORT_Z)) for name, xy in WELLS_RED.items()}
    # the places of the scenarios are illustrative, the book does not locate them
    places = {"1": zp(790, 878), "2": m(434, 296), "3": zp(460, 520), "4": zp(740, 330), "5": m(250, 500), "6": m(466, 296)}
    points.update({f"misto{k}": px(Vector((v.x, v.y, FORT_Z))) for k, v in places.items()})
    (OUT / "body.json").write_text(json.dumps({"res": [W, H], "points": points}, indent=1), encoding="utf-8")
    sc.render.filepath = str(OUT / "pevnost.png")
    bpy.ops.render.render(write_still=True)
    print("HOTOVO")


main()
