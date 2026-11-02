# Blender: six stagings for the six scenarios of the Velsen book (ch. 11). Only a layout for FLUX (role geometry): camera, light, who stands where, the fort as the book describes it.
#   blender -b --factory-startup -P scripts/3d/velsen_sceny.py -- OUT_DIR [--jen 1,2] [--w 1024] [--h 624] [--samples 32] [--prazdne]
#   --prazdne: only the place, the people come as cut-outs (scripts/plakaty/velsen_skladba.py)
# Details from the book: plastered timber-framed buildings with thatch (p. 40-41), box rampart of earth and timber, well-head of timbers with two corner posts (fig. 2.1),
# off-duty tunic, cloak and belt with dagger (fig. 2.10), vine stick of a centurion (fig. 11.3).
import math
import random
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ARGS = sys.argv[sys.argv.index("--") + 1:]
OUT = Path(ARGS[0]).resolve()


def arg(name, default):
    return type(default)(ARGS[ARGS.index(name) + 1]) if name in ARGS else default


W, H, SAMPLES = arg("--w", 1024), arg("--h", 624), arg("--samples", 32)
ONLY = [int(x) for x in arg("--jen", "1,2,3,4,5,6").split(",")]
OUT.mkdir(parents=True, exist_ok=True)
UP = Vector((0, 0, 1))


def lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def rgb(h):
    return (lin(int(h[1:3], 16) / 255), lin(int(h[3:5], 16) / 255), lin(int(h[5:7], 16) / 255), 1)


MATS = {}


def mat(h, rough=0.85, metal=0.0, emit=0.0):
    key = (h, rough, metal, emit)
    if key not in MATS:
        m = bpy.data.materials.new(h)
        m.use_nodes = True
        p = m.node_tree.nodes["Principled BSDF"]
        p.inputs["Base Color"].default_value = rgb(h)
        p.inputs["Roughness"].default_value = rough
        p.inputs["Metallic"].default_value = metal
        if emit:
            p.inputs["Emission Color"].default_value = rgb(h)
            p.inputs["Emission Strength"].default_value = emit
        MATS[key] = m
    return MATS[key]


SKIN, TUNIC, RED, WOOL, WOOL2, MAIL, IRON, LEATHER, SILVER, HAIR = "#b98a6a", "#d8d0ba", "#7a1f1a", "#6a5a44", "#4c4436", "#6f7276", "#44464a", "#3f2c1c", "#b9b9b0", "#141210"
PLASTER, TIMBER, THATCH, EARTH, MUD = "#c9bda0", "#33261a", "#5e4f30", "#3c2f22", "#3b3024"


def limb(a, b, ra, rb, h, rough=0.85, metal=0.0, seg=14):
    """A tapered rounded limb from a to b."""
    a, b = Vector(a), Vector(b)
    axis = b - a
    if axis.length < 1e-4:
        axis = Vector((0, 0, 1e-3))
    n = axis.normalized()
    side = n.cross(Vector((0.31, 0.2, 0.93))).normalized()
    up = n.cross(side).normalized()
    profile = []
    for i in range(5):
        t = math.sin(i / 4 * math.pi / 2)
        profile.append((-ra * math.cos(i / 4 * math.pi / 2), ra * t, 0.0))
    for i in range(1, 5):
        profile.append((0.0, ra + (rb - ra) * i / 4, i / 4))
    for i in range(1, 5):
        t = math.cos(i / 4 * math.pi / 2)
        profile.append((rb * math.sin(i / 4 * math.pi / 2), rb * t, 1.0))
    verts, faces = [], []
    for off, rad, t in profile:
        c = a + axis * t + n * off
        for s in range(seg):
            ang = 2 * math.pi * s / seg
            verts.append(tuple(c + side * rad * math.cos(ang) + up * rad * math.sin(ang)))
    rows = len(profile)
    for r in range(rows - 1):
        for s in range(seg):
            faces.append((r * seg + s, r * seg + (s + 1) % seg, (r + 1) * seg + (s + 1) % seg, (r + 1) * seg + s))
    me = bpy.data.meshes.new("kus")
    me.from_pydata(verts, [], faces)
    me.shade_smooth()
    me.materials.append(mat(h, rough, metal))
    o = bpy.data.objects.new("kus", me)
    bpy.context.collection.objects.link(o)
    return o


def box(c, size, h, rot=0.0, rough=0.85, metal=0.0, emit=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=c, rotation=(0, 0, rot))
    o = bpy.context.object
    o.scale = size
    o.data.materials.append(mat(h, rough, metal, emit))
    return o


def _rot(v, axis, deg):
    from mathutils import Matrix
    return Matrix.Rotation(math.radians(deg), 3, axis) @ v


def figure(pelvis, yaw=0.0, h=1.78, lean=0.0, sway=0.0, head=(0.0, 0.0), la=(10, 12, 15), ra=(10, 12, 15), ll=(0, 3, 0), rl=(0, 3, 0),
           outfit="tunic", cloak=None, helmet=None, hair=True, belt=True, hood=False, sheath=False, grounded=True):
    """Pelvis in world metres, yaw 0 = facing the camera (-Y). Arms and legs are (forward, outward, bend) in degrees. Returns the named joints, for props."""
    p = Vector(pelvis)
    fwd = Vector((math.sin(math.radians(yaw)), -math.cos(math.radians(yaw)), 0))
    right = fwd.cross(UP).normalized()    # the figure's own right
    if grounded:    # the lowest foot or knee on the ground, whatever the pose
        low = []
        for sign, a in ((1, rl), (-1, ll)):
            d = _rot(_rot(-UP, right, a[0]), fwd, -sign * a[1])
            k = d * 0.245 * h
            an = k + _rot(d, right, -a[2]) * 0.245 * h
            low += [k.z - 0.03 * h, an.z - 0.03 * h]
        p.z = -min(low)
    spine = _rot(_rot(UP, right, -lean), fwd, sway).normalized()
    fwd2 = _rot(_rot(fwd, right, -lean), fwd, sway).normalized()
    neck = p + spine * (0.30 * h)
    head_dir = _rot(_rot(spine, right, -head[0]), spine, 0).normalized()
    head_dir = _rot(head_dir, fwd2, head[1]).normalized()
    head_c = neck + head_dir * (0.085 * h)
    torso_color = {"mail": MAIL, "tunic": TUNIC, "wool": WOOL, "wool2": WOOL2, "torn": "#a89c7e"}[outfit]
    joints = {"pelvis": p, "neck": neck, "head": head_c}

    def arm(sign, a):
        s = neck - spine * 0.03 * h + right * sign * 0.125 * h
        d = -spine
        d = _rot(d, right, a[0])
        d = _rot(d, fwd2, -sign * a[1])
        e = s + d * 0.165 * h
        d2 = _rot(d, right, a[2])
        w = e + d2 * 0.145 * h
        hand = w + d2 * 0.05 * h
        return s, e, w, hand

    def leg(sign, a):
        s = p + right * sign * 0.055 * h
        d = -UP
        d = _rot(d, right, a[0])
        d = _rot(d, fwd, -sign * a[1])
        k = s + d * 0.245 * h
        d2 = _rot(d, right, -a[2])
        an = k + d2 * 0.245 * h
        toe = an + (fwd * 0.11 * h) - UP * 0.015 * h
        return s, k, an, toe

    # torso and skirt
    limb(p + spine * 0.04 * h, neck - spine * 0.04 * h, 0.085 * h, 0.098 * h, torso_color, 0.5 if outfit == "mail" else 0.9, 0.6 if outfit == "mail" else 0)
    if outfit == "mail":
        limb(neck - spine * 0.06 * h - right * 0.09 * h, neck - spine * 0.06 * h + right * 0.09 * h, 0.06 * h, 0.06 * h, MAIL, 0.5, 0.6)
    for sign, a in ((1, ra), (-1, la)):
        s, e, w, hand = arm(sign, a)
        limb(s, e, 0.034 * h, 0.03 * h, torso_color if outfit != "tunic" or True else SKIN, 0.9)
        limb(e, w, 0.028 * h, 0.022 * h, SKIN if outfit in ("tunic", "mail", "torn") else torso_color)
        limb(w, hand, 0.024 * h, 0.02 * h, SKIN)
        joints["rhand" if sign > 0 else "lhand"] = hand
        joints["rel" if sign > 0 else "lel"] = e
    knees = []
    for sign, a in ((1, rl), (-1, ll)):
        s, k, an, toe = leg(sign, a)
        knees.append(k)
        trousers = outfit in ("wool", "wool2")
        limb(s, k, 0.052 * h, 0.036 * h, torso_color if trousers else SKIN)
        limb(k, an, 0.034 * h, 0.024 * h, torso_color if trousers else SKIN)
        limb(an, toe, 0.026 * h, 0.022 * h, LEATHER)
        joints["rknee" if sign > 0 else "lknee"] = k
    # skirt of tunic or mail: from the waist to mid thigh, following the thighs
    hem = (p + (knees[0] + knees[1]) / 2) / 2
    limb(p + spine * 0.03 * h, hem, 0.10 * h, 0.125 * h, TUNIC if outfit == "mail" else torso_color)
    if outfit == "mail":
        limb(p + spine * 0.04 * h, p - spine * 0.02 * h + (hem - p) * 0.35, 0.095 * h, 0.108 * h, MAIL, 0.5, 0.6)
    if belt:
        limb(p + spine * 0.035 * h, p + spine * 0.055 * h, 0.098 * h, 0.098 * h, SILVER if outfit in ("mail", "tunic") else LEATHER, 0.4, 0.5 if outfit in ("mail", "tunic") else 0)
    if sheath:
        s0 = p + spine * 0.03 * h + right * 0.105 * h
        limb(s0, s0 - UP * 0.15 * h + fwd * 0.02, 0.022, 0.012, SILVER, 0.4, 0.6)
    # neck and head
    limb(neck, neck + head_dir * 0.05 * h, 0.03 * h, 0.03 * h, SKIN)
    limb(head_c - head_dir * 0.02 * h, head_c + head_dir * 0.03 * h, 0.05 * h, 0.05 * h, SKIN)
    if not hood:    # eyes and nose, so the generator knows which way the face looks
        face = _rot(fwd2, right, -head[0]).normalized()
        side = face.cross(head_dir).normalized()
        for sg in (-1, 1):
            e0 = head_c + face * 0.048 * h + head_dir * 0.018 * h + side * sg * 0.02 * h
            limb(e0, e0, 0.006 * h, 0.006 * h, "#0c0a08", seg=6)
        n0 = head_c + face * 0.05 * h
        limb(n0 + head_dir * 0.012 * h, n0 - head_dir * 0.012 * h + face * 0.012 * h, 0.008 * h, 0.01 * h, SKIN, seg=6)
    if hood:
        limb(head_c - head_dir * 0.03 * h, head_c + head_dir * 0.045 * h, 0.066 * h, 0.064 * h, WOOL2)
        limb(neck - spine * 0.02 * h, neck - spine * 0.02 * h, 0.1 * h, 0.1 * h, WOOL2)
    elif helmet:
        limb(head_c + head_dir * 0.01 * h, head_c + head_dir * 0.045 * h, 0.058 * h, 0.056 * h, IRON, 0.35, 0.8)
        back = head_c - _rot(fwd, right, 0) * 0.05 * h
        limb(back + head_dir * 0.005 * h, back - head_dir * 0.03 * h + -fwd * 0.03 * h, 0.03 * h, 0.02 * h, IRON, 0.35, 0.8)
        if helmet == "centurio":    # the crest across the helmet
            top = head_c + head_dir * 0.085 * h
            limb(top - right * 0.07 * h, top + right * 0.07 * h, 0.018 * h, 0.018 * h, "#8c2a22")
    elif hair:
        limb(head_c + head_dir * 0.012 * h - fwd * 0.012 * h, head_c + head_dir * 0.035 * h - fwd * 0.01 * h, 0.053 * h, 0.05 * h, "#3a2c20" if outfit.startswith("wool") else HAIR)
    if outfit.startswith("wool"):   # long hair and beard, Frisians
        limb(head_c - head_dir * 0.035 * h + fwd * 0.03 * h, head_c - head_dir * 0.07 * h + fwd * 0.03 * h, 0.03 * h, 0.018 * h, "#3a2c20")
        limb(head_c - fwd * 0.04 * h, head_c - fwd * 0.05 * h - head_dir * 0.07 * h, 0.04 * h, 0.03 * h, "#3a2c20")
    if cloak:
        a = neck - fwd * 0.05 * h
        b = p - fwd * 0.13 * h - UP * 0.26 * h
        limb(a, b, 0.11 * h, 0.17 * h, cloak)
        limb(neck - right * 0.09 * h, neck + right * 0.09 * h, 0.05 * h, 0.05 * h, cloak)
    return joints


MODELS = Path(r"C:/Users/stock/Documents/000_NGM/GRAFIK/library/3d")
LOADED = {}


def model(role, loc, yaw=0.0, ht=1.85, color="#9a948a"):
    """A paid figure (Hunyuan 3.1 Pro, scripts/plakaty/velsen_postavy.py) on the ground at `loc`. Copies share the mesh, so a rank of soldiers stays light. Yaw 0 = as in its picture, facing the camera."""
    if role not in LOADED:
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=str(MODELS / f"velsen-{role}" / "v1" / "model.glb"))
        new = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
        LOADED[role] = new[0].data
        for o in set(bpy.data.objects) - before:
            bpy.data.objects.remove(o)
    me = LOADED[role]
    me.materials.clear()
    me.materials.append(mat(color, 0.75))
    o = bpy.data.objects.new(role, me)
    bpy.context.collection.objects.link(o)
    bpy.context.view_layer.update()
    pts = [Vector(c) for c in o.bound_box]
    zs = [v.z for v in pts]
    k = ht / (max(zs) - min(zs))
    o.scale = (k, k, k)
    o.rotation_euler = (0, 0, math.radians(yaw))
    cx, cy = (min(v.x for v in pts) + max(v.x for v in pts)) / 2, (min(v.y for v in pts) + max(v.y for v in pts)) / 2
    a = math.radians(yaw)
    o.location = (loc[0] - k * (cx * math.cos(a) - cy * math.sin(a)), loc[1] - k * (cx * math.sin(a) + cy * math.cos(a)), (loc[2] if len(loc) > 2 else 0.0) - k * min(zs))
    return o


def ground(h=MUD, size=120, rough=0.55):
    bpy.ops.mesh.primitive_plane_add(size=size, location=(0, 10, 0))
    bpy.context.object.data.materials.append(mat(h, rough))


def house(cx, cy, w, d, ht, yaw=0.0, burnt=False):
    """Timber frame filled with plastered daub, thatch (p. 40-41). `burnt`: only charred posts remain."""
    r = math.radians(yaw)
    dx, dy = Vector((math.cos(r), math.sin(r), 0)), Vector((-math.sin(r), math.cos(r), 0))
    c = Vector((cx, cy, 0))
    if not burnt:
        box(c + UP * ht / 2, (w, d, ht), PLASTER, r)
        for i in range(int(w / 1.3) + 1):
            x = -w / 2 + i * w / int(w / 1.3)
            box(c + dx * x - dy * (d / 2 + 0.02) + UP * ht / 2, (0.14, 0.05, ht), TIMBER, r)
        box(c - dy * (d / 2 + 0.02) + UP * (ht - 0.07), (w, 0.05, 0.14), TIMBER, r)
        box(c - dy * (d / 2 + 0.02) + UP * 0.1, (w, 0.05, 0.14), TIMBER, r)
        # gable roof
        rise = d * 0.62
        verts = [tuple(c + dx * sx * (w / 2 + 0.35) + dy * sy * (d / 2 + 0.5) + UP * ht) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        verts += [tuple(c + dx * sx * (w / 2 + 0.35) + UP * (ht + rise)) for sx in (-1, 1)]
        me = bpy.data.meshes.new("střecha")
        me.from_pydata(verts, [], [(0, 1, 5, 4), (2, 3, 4, 5), (0, 4, 3), (1, 2, 5)])
        me.materials.append(mat(THATCH, 0.95))
        o = bpy.data.objects.new("střecha", me)
        bpy.context.collection.objects.link(o)
    else:
        for i in range(int(w / 1.3) + 1):
            x = -w / 2 + i * w / int(w / 1.3)
            for sy in (-1, 1):
                top = random.uniform(0.6, ht + 0.4)
                box(c + dx * x + dy * sy * d / 2 + UP * top / 2, (0.18, 0.18, top), "#0e0c0b", r + random.uniform(-0.1, 0.1), 0.9)


def rampart(x0, x1, y, ht=3.0):
    """Box rampart: a timber face with posts, earth behind, a breastwork of posts on top."""
    box(((x0 + x1) / 2, y + 2.0, ht / 2), (x1 - x0, 4.0, ht), EARTH)
    n = int((x1 - x0) / 0.9)
    for i in range(n + 1):
        x = x0 + i * (x1 - x0) / n
        box((x, y, ht / 2), (0.16, 0.14, ht), TIMBER)
    for k in range(int(ht / 0.28)):
        box(((x0 + x1) / 2, y + 0.04, 0.14 + k * 0.28), (x1 - x0, 0.05, 0.25), "#46372a")
    for i in range(n * 3):
        x = x0 + i * (x1 - x0) / (n * 3)
        box((x, y + 0.12, ht + 0.6), (0.11, 0.1, 1.2 + random.uniform(-0.04, 0.04)), TIMBER)


def well_head(x, y, s=1.5, ht=0.62):
    """Square timbers with two corner posts, as on the book's section (fig. 2.1), and the dark barrel inside."""
    for i in range(3):
        z = 0.1 + i * 0.21
        box((x, y - s / 2, z), (s, 0.2, 0.2), "#4d3b28")
        box((x, y + s / 2, z), (s, 0.2, 0.2), "#3f3122")
        box((x - s / 2, y, z), (0.2, s, 0.2), "#463625")
        box((x + s / 2, y, z), (0.2, s, 0.2), "#463625")
    for sx in (-1, 1):
        box((x + sx * s / 2, y + s / 2, 0.68), (0.24, 0.24, 1.36), "#3a2c1f")
    box((x, y, ht - 0.05), (s - 0.2, s - 0.2, 0.02), "#040404", rough=0.15)


def stones(x, y, n, spread, z=0.0, seed=1, h="#403b39", size=(0.08, 0.2)):
    rnd = random.Random(seed)
    for _ in range(n):
        s = rnd.uniform(*size)
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=s, location=(x + rnd.uniform(-spread, spread), y + rnd.uniform(-spread / 2, spread / 2), z + s * 0.5 + rnd.uniform(0, 0.1)), rotation=(rnd.uniform(0, 3), rnd.uniform(0, 3), rnd.uniform(0, 3)))
        o = bpy.context.object
        o.scale = (1, rnd.uniform(0.6, 1), rnd.uniform(0.4, 0.8))
        o.data.materials.append(mat(h, 0.9))


def reeds(x0, x1, y0, y1, n, seed=3):
    rnd = random.Random(seed)
    for _ in range(n):
        x, y = rnd.uniform(x0, x1), rnd.uniform(y0, y1)
        lean = Vector((rnd.uniform(-0.2, 0.2), rnd.uniform(-0.2, 0.2), 1)).normalized()
        limb((x, y, 0), Vector((x, y, 0)) + lean * rnd.uniform(0.7, 1.5), 0.012, 0.003, rnd.choice(("#6a6238", "#7a7040", "#4e4a2c")), seg=5)


def spear(a, b):
    a, b = Vector(a), Vector(b)
    d = (b - a).normalized()
    limb(a, b, 0.016, 0.014, "#4a3722", seg=8)
    limb(b, b + d * 0.32, 0.03, 0.002, IRON, 0.35, 0.8, seg=8)


def shield_round(c, normal, r=0.42):
    c, n = Vector(c), Vector(normal).normalized()
    limb(c, c + n * 0.03, r, r, "#5f4a30", seg=28)
    limb(c + n * 0.03, c + n * 0.09, 0.07, 0.05, IRON, 0.35, 0.8, seg=12)


def dagger(hand, direction, length=0.3):
    a, d = Vector(hand), Vector(direction).normalized()
    limb(a - d * 0.05, a + d * 0.03, 0.018, 0.018, LEATHER, seg=8)
    limb(a + d * 0.03, a + d * length, 0.034, 0.002, "#a8a8a2", 0.25, 0.9, seg=6)


def setup(world, camera, target, lens, lights):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples, sc.cycles.use_denoising = SAMPLES, True
    sc.render.resolution_x, sc.render.resolution_y = W, H
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
    w = bpy.data.worlds.new("svět")
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = rgb(world[0])
    w.node_tree.nodes["Background"].inputs[1].default_value = world[1]
    sc.world = w
    for kind, loc, power, size, col in lights:
        d = bpy.data.lights.new(kind, kind)
        d.energy, d.color = power, rgb(col)[:3]
        if kind == "AREA":
            d.size = size
        if kind == "POINT":
            d.shadow_soft_size = size
        if kind == "SUN":
            d.angle = size
        o = bpy.data.objects.new(kind, d)
        o.location = loc
        o.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        bpy.context.collection.objects.link(o)
    cam = bpy.data.cameras.new("kamera")
    cam.lens = lens
    co = bpy.data.objects.new("kamera", cam)
    co.location = camera
    co.rotation_euler = (Vector(target) - Vector(camera)).to_track_quat("-Z", "Y").to_euler()
    bpy.context.collection.objects.link(co)
    sc.camera = co


def clear():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    for d in (bpy.data.lights, bpy.data.cameras, bpy.data.worlds):
        for x in list(d):
            d.remove(x)


def scene1():
    """Fallen in the fight with the Frisians: dawn on top of the rampart, smoke behind."""
    ground(EARTH)
    rampart(-14, 14, 3.6, 1.0)
    house(-8, 14, 9, 5, 2.6)
    house(7, 16, 10, 5, 2.6)
    # the victim, already struck, falling back to the right, bareheaded
    j = figure((0.5, 0.2, 0.88), yaw=-58, lean=-20, sway=-10, head=(-14, -8), la=(50, 45, 30), ra=(40, 60, 10), ll=(25, 8, 25), rl=(-8, 5, 15), outfit="mail", helmet=None, sheath=True)
    limb((1.3, -0.3, 0.05), (1.3, -0.3, 0.2), 0.11, 0.1, IRON, 0.35, 0.8)     # his helmet in the mud
    # Frisian thrusting a spear from the left
    a = figure((-1.2, -0.3, 0.86), yaw=62, lean=22, head=(5, 0), la=(70, 5, 10), ra=(55, 18, 25), ll=(28, 5, 18), rl=(-20, 4, 22), outfit="wool", cloak="#544935")
    spear(Vector(a["rhand"]) - Vector((0.9, 0, 0.1)), (0.45, 0.1, 1.15))
    # a second over the breastwork, a third behind with a shield
    figure((-3.0, 3.1, 1.5), yaw=30, lean=24, la=(80, 20, 20), ra=(60, 15, 40), ll=(50, 8, 60), rl=(10, 4, 20), outfit="wool2", cloak="#3f3a2d")
    b = figure((-3.2, 1.4, 0.92), yaw=40, lean=10, la=(70, 20, 60), ra=(60, 30, 30), outfit="wool", cloak="#544935")
    shield_round(Vector(b["lhand"]) + Vector((0.1, -0.1, 0)), (0.7, -0.7, 0))
    spear(Vector(b["rhand"]) - Vector((0.5, -0.1, 0.3)), Vector(b["rhand"]) + Vector((1.3, -0.3, 0.7)))
    # burning thatch on the far right
    for i in range(10):
        limb((5 + i * 0.5, 13, 3), (5 + i * 0.5, 13, 4 + random.uniform(0.2, 1.4)), 0.25, 0.03, "#ff8a2a", seg=6)
    setup(("#c98a58", 0.5), (0.1, -5.3, 1.05), (0.0, 0.6, 1.25), 38,
          [("SUN", (6, 18, 7), 4.5, 0.12, "#ffb070"), ("AREA", (-4, -5, 4), 110, 6, "#c4cde0")])


def scene2():
    """Murder: night by the harbour, two men and the body over the kerb of the well, one small lamp."""
    ground("#2a241d", rough=0.95)
    well_head(0.2, 0.7)
    house(-6.8, 5.4, 8, 5, 2.6, yaw=-14)
    house(7.6, 6, 8, 5, 2.6, yaw=12)
    # jetty and a mast against the sky, the harbour is 4 m away (p. 30)
    box((0.8, 9.5, 0.5), (1.6, 7, 0.14), "#2a2118")
    limb((1.6, 13, 0), (1.5, 13, 8), 0.07, 0.04, "#1a1410")
    # the victim hanging over the kerb, feet already down, wrapped in the red cloak, head falling back to camera
    figure((0.2, 0.62, 0.6), yaw=4, lean=-6, sway=7, head=(34, 14), la=(35, 42, 12), ra=(30, 42, 12), ll=(0, 3, 0), rl=(0, 3, 0), outfit="tunic", cloak=RED, grounded=False, sheath=True)
    limb((-0.2, 0.42, 1.2), (0.55, 0.42, 1.15), 0.09, 0.09, RED)
    # two hooded men, one each side, hauling
    figure((-0.95, 0.15, 0.82), yaw=75, lean=38, head=(10, 0), la=(70, 10, 20), ra=(75, 2, 20), ll=(24, 4, 30), rl=(-6, 4, 12), outfit="wool2", cloak="#2c2a26", hood=True, belt=False)
    figure((1.3, 0.35, 0.84), yaw=-80, lean=32, head=(-12, 18), la=(70, 8, 20), ra=(65, 5, 30), ll=(10, 4, 14), rl=(18, 4, 24), outfit="wool2", cloak="#2c2a26", hood=True, belt=False)
    # the lamp on the kerb
    limb((0.72, -0.06, 0.64), (0.72, -0.06, 0.7), 0.05, 0.035, "#6a5533", seg=10)
    limb((0.72, -0.06, 0.74), (0.72, -0.06, 0.78), 0.012, 0.004, "#ffc070", seg=6)
    setup(("#1a2440", 0.9), (0.25, -4.3, 0.95), (0.2, 0.5, 1.0), 40,
          [("POINT", (0.72, -0.25, 1.0), 45, 0.05, "#ffb060"), ("SUN", (-8, -6, 14), 1.1, 0.03, "#7f9fd8")])


def scene3():
    """Disciplinary execution: a cold morning, ranks in the fog, the centurion and the prisoner."""
    ground("#4a4136")
    house(-11, 18, 10, 5, 2.6)
    house(2, 19, 12, 5, 2.6)
    rampart(-18, 24, 26, 3.0)
    # the prisoner kneeling, hands tied behind, his face to the camera (tall man: 1.27 m on his knees, the figure is cut at the shins)
    model("kneeling", (0.75, 0.2), yaw=-12, ht=1.3, color="#b8ae96")
    # two men hold him by the arms
    model("soldier", (-0.15, 0.55), yaw=-38, ht=1.8, color="#8c8c86")
    o = model("soldier", (1.65, 0.5), yaw=38, ht=1.8, color="#8c8c86")
    o.scale.x *= -1
    # the centurion in the left foreground, vine stick across
    model("centurion", (-1.75, -0.65), yaw=38, ht=1.85, color="#8c8c86")
    # the ranks behind
    for row in range(3):
        for i in range(10):
            model("soldier", (-4.6 + i * 1.05 + row * 0.2, 7.5 + row * 1.25), yaw=random.uniform(-3, 3), ht=1.76, color="#8c8c86")
    setup(("#9fa8ad", 1.05), (0.1, -4.6, 0.92), (0.05, 1.2, 1.15), 36,
          [("SUN", (-10, -8, 12), 0.9, 0.5, "#c8d2dc")])


def scene4():
    """His own men: a narrow gap between barracks at night, one torch."""
    ground("#2b241c", rough=0.3)
    # the two walls of the alley, plaster and timber
    box((-3.4, 3.5, 1.5), (0.3, 12, 3.2), PLASTER)
    box((3.4, 3.5, 1.5), (0.3, 12, 3.2), PLASTER)
    for i in range(8):
        y = -2 + i * 1.5
        box((-3.22, y, 1.5), (0.06, 0.15, 3.2), TIMBER)
        box((3.22, y, 1.5), (0.06, 0.15, 3.2), TIMBER)
    box((0, 10, 1.5), (7, 0.3, 3.2), "#2a2019")
    # the crate
    box((-0.1, 0.25, 0.28), (0.95, 0.72, 0.56), "#4a3724", 0.1)
    # the victim forced to bend over it, big man, belt on, face to the camera
    v = figure((0.12, 0.7, 0.92), yaw=8, h=1.9, lean=78, head=(-58, -10), la=(65, 28, 15), ra=(60, 30, 10), ll=(-4, 7, 8), rl=(-4, 7, 8), outfit="tunic", sheath=True)
    # one grips his neck, one wrenches the arm
    figure((-1.05, 0.55, 0.95), yaw=55, lean=30, head=(20, 0), la=(60, 8, 30), ra=(55, 20, 25), ll=(18, 5, 18), rl=(-10, 5, 12), outfit="tunic", belt=True)
    figure((1.3, 0.55, 0.93), yaw=-55, lean=30, head=(10, 0), la=(58, 18, 30), ra=(65, 6, 25), ll=(-8, 5, 10), rl=(22, 5, 22), outfit="tunic", belt=True)
    # the third behind him raises the dagger
    t = figure((0.1, 1.6, 0.97), yaw=-3, lean=8, head=(8, 0), la=(40, 25, 25), ra=(160, 12, 30), outfit="tunic", belt=True)
    dagger(t["rhand"], (0.05, -0.25, 1))
    # broken vine stick and a helmet in the mud
    limb((-1.4, -0.75, 0.03), (-0.5, -0.92, 0.03), 0.012, 0.011, "#5a4326", seg=8)
    limb((-0.42, -0.88, 0.03), (0.05, -0.7, 0.04), 0.012, 0.011, "#5a4326", seg=8)
    limb((1.15, -0.72, 0.03), (1.15, -0.72, 0.19), 0.115, 0.1, IRON, 0.35, 0.8)
    # the torch on the left wall
    limb((-3.15, 0.9, 1.75), (-2.95, 0.9, 2.1), 0.025, 0.03, "#3a2a1a", seg=8)
    limb((-2.92, 0.9, 2.15), (-2.9, 0.9, 2.5), 0.09, 0.015, "#ffb050", seg=8)
    setup(("#141a2c", 0.5), (0.05, -3.9, 0.95), (0.0, 0.8, 1.05), 34,
          [("POINT", (-2.6, -0.4, 2.35), 260, 0.12, "#ff9a48"), ("AREA", (2, -4, 3.2), 40, 3, "#5b6f9a")])


def scene5():
    """Native retribution: mist on the tidal marsh at dusk, the captive and three Frisians."""
    bpy.ops.mesh.primitive_plane_add(size=300, location=(0, 60, -0.02))
    bpy.context.object.data.materials.append(mat("#4d5e68", 0.08))
    bpy.ops.mesh.primitive_plane_add(size=60, location=(0, 15, 0))
    bpy.context.object.data.materials.append(mat("#2a241b", 0.5))
    reeds(-9, -2.2, 0, 8, 240)
    reeds(2.6, 10, 1, 9, 200, 5)
    reeds(-9, 10, 9, 14, 160, 7)
    # the fort far away on the horizon
    box((-14, 62, 0.7), (26, 2, 1.4), "#242428")
    for i in range(3):
        box((-25 + i * 11, 62, 1.1), (1.2, 1.2, 2.2), "#26262a")
    # the captive kneeling, tunic torn, hands bound before him, bareheaded
    figure((0.05, 0.2, 0.66), yaw=-8, lean=14, head=(-12, 6), la=(25, 2, 62), ra=(25, 2, 62), ll=(18, 4, 112), rl=(18, 4, 110), outfit="torn", belt=False)
    # three Frisians, one holds the Roman dagger and the cloak taken from him
    a = figure((1.45, 0.55, 0.94), yaw=-48, lean=14, head=(14, 0), la=(30, 6, 62), ra=(40, 14, 38), outfit="wool", cloak="#544935", ll=(10, 5, 8), rl=(-8, 5, 8))
    dagger(a["rhand"], (-0.7, -0.4, 0.4))
    limb(a["lhand"], Vector(a["lhand"]) + Vector((0.08, -0.05, -0.55)), 0.09, 0.12, RED)
    figure((-1.45, 0.75, 0.94), yaw=48, lean=8, head=(10, 0), la=(12, 8, 18), ra=(30, 15, 40), outfit="wool2", cloak="#3f3a2d", ll=(6, 5, 6), rl=(-5, 5, 6))
    b = figure((-0.5, 2.0, 0.95), yaw=10, lean=2, la=(10, 10, 10), ra=(18, 14, 60), outfit="wool", cloak="#47402f")
    spear(Vector(b["rhand"]) - Vector((0, 0.05, 1.1)), Vector(b["rhand"]) + Vector((0, 0, 0.9)))
    setup(("#8ea0ae", 0.8), (0.15, -4.4, 0.75), (0.1, 1.2, 1.0), 36,
          [("SUN", (12, 30, 3.5), 2.0, 0.08, "#f0b48a"), ("AREA", (-3, -6, 3), 120, 6, "#a8bccc")])


def scene6():
    """A ritual: twilight in the burned-out fort, the well closed with the dead and broken querns."""
    ground("#26211c")
    well_head(0.1, 0.8)
    for x, y, w_, d in ((-8, 8, 10, 5), (8, 9, 10, 5), (-1, 15, 12, 5)):
        house(x, y, w_, d, 2.6, burnt=True)
    rampart(-20, 20, 24, 2.4)
    stones(0.75, -0.25, 34, 0.75, seed=11, size=(0.08, 0.2))
    stones(-0.7, -0.3, 12, 0.5, seed=12, size=(0.07, 0.17))
    # embers
    rnd = random.Random(4)
    for _ in range(90):
        x, y = rnd.uniform(-9, 9), rnd.uniform(2.5, 14)
        limb((x, y, 0.02), (x, y, 0.05), 0.05, 0.03, "#ff6a20", seg=6)
    # the dead man hanging in the sling, sitting slumped, at the height of the kerb
    v = figure((0.1, 0.8, 0.95), yaw=-5, lean=22, sway=8, head=(40, 12), la=(25, 22, 28), ra=(22, 24, 28), ll=(78, 6, 88), rl=(80, 6, 90), outfit="tunic", cloak=RED, sheath=True, grounded=False)
    # four men round the kerb, an old man with raised hands
    figure((-1.35, 0.35, 0.92), yaw=70, lean=22, head=(16, 0), la=(70, 8, 25), ra=(62, 10, 25), outfit="wool2", cloak="#3b362b", ll=(16, 5, 15), rl=(-6, 5, 10))
    figure((1.55, 0.3, 0.92), yaw=-72, lean=24, head=(18, 0), la=(60, 10, 28), ra=(70, 8, 22), outfit="wool", ll=(-6, 5, 10), rl=(14, 5, 14))
    figure((-0.85, 2.15, 0.97), yaw=8, lean=6, head=(16, 0), la=(16, 10, 28), ra=(22, 10, 40), outfit="wool", cloak="#47402f")
    figure((0.95, 2.2, 0.97), yaw=-8, lean=4, head=(14, 0), la=(14, 8, 40), ra=(18, 10, 24), outfit="wool2")
    figure((2.5, 1.25, 0.95), yaw=-62, lean=-3, head=(-10, 0), la=(115, 28, 20), ra=(120, 25, 15), outfit="wool", cloak="#5c5240")
    setup(("#6a5a88", 0.55), (0.1, -4.6, 1.15), (0.1, 1.0, 1.05), 36,
          [("SUN", (-10, 20, 5), 1.2, 0.2, "#c79ab4"), ("AREA", (0, 5, 0.4), 40, 16, "#ff6a20"), ("AREA", (-3, -5, 4), 170, 6, "#a4a8c8")])


SCENES = {1: scene1, 2: scene2, 3: scene3, 4: scene4, 5: scene5, 6: scene6}
if "--prazdne" in ARGS:
    class _Hands(dict):
        def __missing__(self, key):
            return (0.0, 0.0, 0.0)

    _limb, _box = limb, box
    figure = lambda *a, **k: _Hands()  # noqa: E731
    model = lambda *a, **k: bpy.data.objects.new("x", None)  # noqa: E731
    spear = shield_round = dagger = lambda *a, **k: None  # noqa: E731
    limb = lambda a, b, *r, **k: None if len(r) > 2 and r[2] in (RED, "#ff8a2a", "#ff6a20") else _limb(a, b, *r, **k)  # noqa: E731
    stones = lambda *a, **k: None  # noqa: E731
    box = lambda loc, size, col, *r, **k: None if col == "#4a3724" else _box(loc, size, col, *r, **k)  # noqa: E731
for n in ONLY:
    clear()
    random.seed(n)
    SCENES[n]()
    bpy.context.view_layer.update()
    sc = bpy.context.scene
    sc.render.filepath = str(OUT / f"scena-{n}.png")
    sc.render.image_settings.file_format = "PNG"
    bpy.ops.render.render(write_still=True)
    print("HOTOVO", n)
