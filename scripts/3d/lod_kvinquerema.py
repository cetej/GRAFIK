# Roman quinquereme built from reconstruction numbers (free):
#   blender -b -P scripts/3d/lod_kvinquerema.py -- out_prefix [--cutaway]
# --cutaway opens a window in the near (-y) side amidships, like the cutaway in a ship infographic:
# three levels of rowers on their oars (2-2-1, Morrison), floor, hold with water jars and ballast.
# Every size is in DIM (metres) with its source; "odhad" = our estimate, no published figure found.
# Rendered as matte clay so the image model takes shape and proportions from it, never texture.
# Axes: x towards the bow (ship centred on x = 0), y across, z up, waterline z = 0.
import math
import sys

import bmesh
import bpy
from mathutils import Vector

DIM = {
    "length": 45.0,          # Coates 1995, p. 138
    "beam_wl": 5.0,          # Coates 1995: beam at water level
    "beam_deck": 5.8,        # odhad: sides flare above the water
    "parallel": 14.0,        # odhad: straight sides along the rowing section (|x| < 14 m)
    "deck_z": 3.0,           # Coates 1995: deck about 3 m above water
    "draught": 1.3,          # odhad, Olympias 1.25 m
    "outrigger_y": 3.5,      # odhad: 7 m over the outriggers, L/B 6.4 like Olympias (36.9 / 5.5 = 6.7)
    "files": 30,             # Morrison 1995: files of 30, 2-2-1 rowers, 90 oars a side
    "room": 0.98,            # odhad: Olympias 0.89 m, widened after the sea trials
    "mast_x": 1.0,           # odhad
    "mast_h": 13.0,          # odhad: mast above deck
    "mast_d": 0.45,          # odhad
    "yard_l": 14.0,          # odhad
    "sail_w": 12.0, "sail_h": 8.0,   # odhad
    "artemon_l": 7.0,        # odhad: raked foremast
    "tower": (3.0, 3.0, 3.5),        # odhad: w, d, h above deck
    "corvus_pole": 7.2,      # Polybius 1.22: 24 ft
    "corvus_bridge": (10.8, 1.2),    # Polybius 1.22: 36 ft long, 4 ft wide
    "ram_l": 2.4,            # odhad (Athlit ram 2.26 m)
    "shield_d": 0.9,         # odhad
    "man": 1.72,             # odhad: height of a soldier or sailor
}

args = sys.argv[sys.argv.index("--") + 1:]
prefix, CUTAWAY = args[0], "--cutaway" in args[1:]
WINDOW = (-10.0, 8.0)     # x range of the cutaway window
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
L, H = DIM["length"] / 2, DIM["deck_z"]

# --- helpers --------------------------------------------------------------------------------
def link(bm, name):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    scene.collection.objects.link(o)
    return o


def box(c, s, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=c, rotation=rot)
    bpy.context.active_object.scale = s
    return bpy.context.active_object


def rod(a, b, r, r2=None, verts=10):
    a, b = Vector(a), Vector(b)
    d = b - a
    bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r, radius2=r if r2 is None else r2,
                                    depth=d.length, location=(a + b) / 2)
    bpy.context.active_object.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
    return bpy.context.active_object


def path(points, r, r2=None):
    n = len(points) - 1
    for i, (a, b) in enumerate(zip(points, points[1:])):
        ra = r if r2 is None else r + (r2 - r) * i / n
        rb = r if r2 is None else r + (r2 - r) * (i + 1) / n
        rod(a, b, ra, rb, 12)


def person(x, y, z):
    """A standing man DIM['man'] tall: legs, torso, head, spear."""
    m = DIM["man"]
    for dy in (-0.1, 0.1):
        rod((x, y + dy, z), (x, y + dy, z + 0.47 * m), 0.075, 0.09, 8)
    rod((x, y, z + 0.47 * m), (x, y, z + 0.82 * m), 0.17, 0.2, 10)
    ball((x, y, z + 0.92 * m), 0.12)
    rod((x + 0.25, y, z + 0.3), (x + 0.25, y, z + 1.3 * m), 0.02, None, 6)


def rower(seat, hand):
    """Seated rower facing the stern (-x), hands on the oar loom."""
    x, y, z = seat
    box((x, y, z - 0.08), (0.45, 0.42, 0.06))                      # bench
    hip, sh = Vector((x, y, z + 0.1)), Vector((x + 0.12, y, z + 0.6))
    rod(hip, sh, 0.15, 0.13, 10)
    ball((x + 0.14, y, z + 0.78), 0.11)
    knee, foot = Vector((x - 0.42, y, z + 0.12)), Vector((x - 0.5, y, z - 0.35))
    for dy in (-0.1, 0.1):
        rod(hip + Vector((0, dy, 0)), knee + Vector((0, dy, 0)), 0.06, None, 8)
        rod(knee + Vector((0, dy, 0)), foot + Vector((0, dy, 0)), 0.05, None, 8)
        rod(sh + Vector((0, dy * 1.7, -0.02)), Vector(hand) + Vector((0, dy, 0)), 0.04, None, 8)


def ball(c, r):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=c, segments=16, ring_count=8)
    return bpy.context.active_object


# --- hull: lofted from cross-sections ---------------------------------------------------------
# section half-widths at heights (z, w) amidships; w(0) = beam_wl / 2
WD = DIM["beam_deck"] / 2
SECTION = [(-1.3, 0.25), (-0.9, 1.35), (-0.45, 2.05), (0.0, 2.5), (0.7, 2.75), (1.5, 2.88), (2.3, WD), (3.0, WD)]


def taper(x):
    """1 along the parallel rowing section, then fining to the stem and the stern."""
    u = max(0.0, abs(x) - DIM["parallel"]) / (L - 0.4 - DIM["parallel"])
    return max(0.03, 1 - min(u, 1.0) ** 1.8) ** 0.7


def hw(z, x=0.0):
    """Outer half-width of the hull at height z (above the water only) and station x."""
    for (z0, w0), (z1, w1) in zip(SECTION, SECTION[1:]):
        if z0 <= z <= z1:
            return (w0 + (w1 - w0) * (z - z0) / (z1 - z0)) * taper(x)
    return WD * taper(x)


def sheer(x):
    z = H
    if x < -L + 7:
        z += ((-L + 7 - x) / 7) ** 2 * 1.4
    if x > L - 5:
        z += ((x - L + 5) / 5) ** 2 * 0.7
    return z


def keel(x):
    return -DIM["draught"] + 0.9 * (abs(x) / L) ** 5


bm = bmesh.new()
rings = []
for i in range(81):
    x = -L + 0.6 + i * (2 * L - 1.2) / 80
    t, top, bot = taper(x), sheer(x), keel(x)
    side = []
    for z, w in SECTION:
        zz = bot + (z + 1.3) / 4.3 * (top - bot) if z < 0 else z / H * top
        zz = z if -0.01 < z < 0.01 else zz
        side.append((w * t, zz))
    loop = [(w, z) for w, z in side] + [(-w, z) for w, z in reversed(side)]
    rings.append([bm.verts.new((x, y, z)) for y, z in loop])
n = len(rings[0])
for a, b in zip(rings, rings[1:]):
    for j in range(n):
        bm.faces.new((a[j], a[(j + 1) % n], b[(j + 1) % n], b[j]))
bm.faces.new(list(reversed(rings[0])))
bm.faces.new(rings[-1])
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
hull = link(bm, "hull")

# wales, bulwark with shields, eyes
for s in (-1, 1):
    for z in (0.35, 1.1):
        xs = list(range(-19, 21, 2))
        runs = [xs] if not (CUTAWAY and s < 0) else [[x for x in xs if x <= WINDOW[0]], [x for x in xs if x >= WINDOW[1]]]
        for run in runs:
            if len(run) > 1:
                path([(x, s * (hw(z, x) + 0.1), z) for x in run], 0.1)
    rail = [(x, s * WD * taper(x), sheer(x) + 0.9) for x in range(-18, 20, 1)]
    path(rail, 0.06)
    for x in range(-17, 19):
        rod((x, s * WD * taper(x), sheer(x)), (x, s * WD * taper(x), sheer(x) + 0.9), 0.05)
    for k in range(28):
        x = -14 + k * 1.0
        y = s * (WD * taper(x) + 0.06)
        rod((x, y, sheer(x) + 0.5), (x, y + s * 0.06, sheer(x) + 0.5), DIM["shield_d"] / 2, None, 24)
    ball((L - 2.6, s * hw(1.6, L - 2.6), 1.6), 0.35)

# outriggers (parexeiresia) carrying the top oars
oar_x0 = -DIM["files"] * DIM["room"] / 2
near_outrigger = []
for s in (-1, 1):
    a = box((0, s * (DIM["outrigger_y"] + WD) / 2, 2.25), (DIM["files"] * DIM["room"] + 1.5, DIM["outrigger_y"] - WD + 0.1, 0.35))
    b = box((0, s * DIM["outrigger_y"], 2.05), (DIM["files"] * DIM["room"] + 1.5, 0.12, 0.5))
    if s < 0:
        near_outrigger += [a, b]

# --- oars: 3 levels x 30 files a side, identical per level ------------------------------------
LEVELS = [  # (thole y, thole z, outboard length to the blade tip, drop to the water)
    (DIM["outrigger_y"], 2.0, 7.2),
    (hw(1.35), 1.35, 5.4),
    (hw(0.6), 0.6, 3.6),
]
for s in (-1, 1):
    for lvl, (ty, tz, out) in enumerate(LEVELS):
        for k in range(DIM["files"]):
            x = oar_x0 + (k + 0.5 + lvl * 0.33) * DIM["room"]
            tip = Vector((x - 0.9, s * (ty + math.sqrt(max(out ** 2 - (tz + 0.15) ** 2, 1))), -0.15))
            thole = Vector((x, s * ty, tz))
            u = (tip - thole).normalized()
            in_window = CUTAWAY and s < 0 and WINDOW[0] + 0.6 < x < WINDOW[1] - 0.6
            if not in_window:   # cutaway convention: the outboard oars in front of the window are left out
                rod(thole - u * 0.6, tip, 0.06, 0.05, 8)
                blade = tip - u * 0.75
                b = box(blade, (0.04, 1.5, 0.22))
                b.rotation_euler = u.to_track_quat("Y", "Z").to_euler()
            if in_window:
                men = 1 if lvl == 2 else 2
                rod(thole - u * 0.6, thole - u * (1.05 + 0.55 * men), 0.06, 0.06, 8)   # loom inside
                for m in range(men):
                    hand = thole - u * (1.0 + 0.55 * m)
                    rower((hand.x + 0.55, hand.y, hand.z - 0.5), hand)

# --- bow: stem, proembolion, ram with three fins -----------------------------------------------
path([(L - 0.9, 0, -0.6), (L - 0.4, 0, 1.0), (L - 0.2, 0, 2.6), (L - 0.3, 0, 3.8), (L - 0.8, 0, 4.6), (L - 1.4, 0, 4.8)], 0.38, 0.16)
rod((L - 1.0, 0, 1.6), (L + 1.2, 0, 1.6), 0.22, 0.18, 10)
rl = DIM["ram_l"]
bm = bmesh.new()
base = [bm.verts.new((L - 0.8, y, z)) for y, z in ((-0.4, -0.5), (0.4, -0.5), (0.4, 0.4), (-0.4, 0.4))]
tipv = [bm.verts.new((L - 0.8 + rl, y, z)) for y, z in ((-0.3, -0.35), (0.3, -0.35), (0.3, 0.25), (-0.3, 0.25))]
for j in range(4):
    bm.faces.new((base[j], base[(j + 1) % 4], tipv[(j + 1) % 4], tipv[j]))
bm.faces.new(list(reversed(base)))
bm.faces.new(tipv)
link(bm, "ram")
for z in (-0.25, 0.0, 0.22):
    box((L - 0.8 + rl - 0.45, 0, z), (0.9, 0.9, 0.05))

# --- stern: curved sternpost with the fan (aplustre), two steering oars ------------------------
post = [(-L + 1.2, 0, -0.4), (-L + 0.5, 0, 1.6), (-L + 0.1, 0, 3.2), (-L - 0.2, 0, 4.8), (-L - 0.1, 0, 6.0), (-L + 0.6, 0, 7.0), (-L + 1.4, 0, 7.3)]
path(post, 0.5, 0.16)
for k in range(5):
    a = math.radians(-30 + k * 15)
    path([(-L - 0.2, 0, 6.0), (-L - 0.6 - math.cos(a) * 1.2, math.sin(a) * 0.8, 6.9 + k * 0.15),
          (-L - 0.4 - math.cos(a) * 1.8, math.sin(a) * 1.2, 7.8 + k * 0.2)], 0.07, 0.03)
for s in (-1, 1):
    a, b = Vector((-L + 3.5, s * 2.3, sheer(-L + 3.5) + 0.6)), Vector((-L + 1.0, s * 3.4, -1.2))
    rod(a, b, 0.12, 0.1, 10)
    blade = b - (b - a).normalized() * 1.0
    bl = box(blade, (0.08, 0.6, 2.0))
    bl.rotation_euler = (b - a).to_track_quat("Z", "Y").to_euler()

# --- deck furniture: mast, yard, sail, rigging, artemon, tower, corvus, marines ----------------
mx, top = DIM["mast_x"], H + DIM["mast_h"]
rod((mx, 0, H), (mx, 0, top), DIM["mast_d"] / 2, DIM["mast_d"] / 3, 16)
yz = top - 0.8
half = DIM["yard_l"] / 2
for s in (-1, 1):
    rod((mx + 0.35, 0, yz), (mx + 0.35, s * half, yz), 0.17, 0.07, 12)
bm = bmesh.new()
sw, sh, nu, nv = DIM["sail_w"], DIM["sail_h"], 16, 10
grid = [[bm.verts.new((mx + 0.55 + 1.1 * math.sin(math.pi * i / nu) * math.sin(math.pi * (j + 0.5) / (nv + 1)),
                       -sw / 2 + sw * i / nu, yz - 0.2 - sh * j / nv)) for i in range(nu + 1)] for j in range(nv + 1)]
for j in range(nv):
    for i in range(nu):
        bm.faces.new((grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i]))
bmesh.ops.solidify(bm, geom=bm.faces[:], thickness=0.04)
link(bm, "sail")
rigging = [((mx, 0, top), (L - 1.0, 0, sheer(L - 1.0) + 0.5)), ((mx, 0, top), (-L + 3.0, 0, sheer(-L + 3.0) + 0.6))]
for s in (-1, 1):
    for dx in (-1.5, 1.0):
        rigging.append(((mx, 0, top - 1.0), (mx + dx, s * WD, H + 0.9)))
    rigging.append(((mx + 0.35, s * half, yz), (mx + 0.6, s * sw / 2, yz - sh - 0.2)))   # sheets/brails
for a, b in rigging:
    rod(a, b, 0.03, None, 6)
ab = Vector((L - 4.5, 0, H + 0.2))
at = ab + Vector((math.cos(math.radians(40)), 0, math.sin(math.radians(40)))) * DIM["artemon_l"]
rod(ab, at, 0.18, 0.1, 12)
for s in (-1, 1):
    rod(at + Vector((0.2, 0, -0.3)), at + Vector((0.2, s * 2.5, -0.3)), 0.08, 0.04, 8)

tw, td, th = DIM["tower"]
tx = 7.0
box((tx, 0, H + th / 2), (tw, td, th))
for k in range(5):
    off = -tw / 2 + tw * (k + 0.5) / 5
    for x, y in ((tx + off, td / 2 - 0.15), (tx + off, -td / 2 + 0.15), (tx + tw / 2 - 0.15, off), (tx - tw / 2 + 0.15, off)):
        box((x, y, H + th + 0.3), (0.32, 0.32, 0.6))

px = L - 3.0
pole_top = Vector((px, 0, H + DIM["corvus_pole"]))
rod((px, 0, H), pole_top, 0.22, 0.16, 12)
bl_, bw = DIM["corvus_bridge"]
pitch, yaw = math.radians(68), math.radians(-35)
pivot = Vector((px, 0, H + 1.0))
d = Vector((math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch)))
mid = pivot + d * (bl_ / 2)
box(mid, (bl_, bw, 0.15), (0, -pitch, yaw))
side = Vector((-math.sin(yaw), math.cos(yaw), 0))
for s in (-1, 1):
    box(mid + side * (s * bw / 2) + Vector((0, 0, 0.35)), (bl_, 0.06, 0.7), (0, -pitch, yaw))
ctip = pivot + d * bl_
rod(ctip, ctip - Vector((0, 0, 0.8)), 0.08, 0.02, 8)          # iron spike
rod(pole_top, ctip + Vector((0, 0, 0.2)), 0.04, None, 6)      # hauling rope

for k, (x, y) in enumerate([(-12, -1.2), (-10, 0.8), (-7, -0.5), (-4, 1.3), (-2, -1.6), (3, 1.0), (4, -1.3),
                            (10, 0.6), (11, -1.0), (13, 1.4), (15, -0.4), (-15, 0.2), (-16, -1.3), (12.5, 0)]):
    z = sheer(x)
    person(x, y, z)

# --- cutaway: open the near side amidships, show the floor, hold, frames and deck beams ---------
if CUTAWAY:
    x0, x1 = WINDOW
    cutter = box(((x0 + x1) / 2, -2.6, 0.85), (x1 - x0, 5.2, 3.7))      # y -5.2 .. 0, z -1.0 .. 2.7
    for o in [hull] + near_outrigger:
        mod = o.modifiers.new("cutaway", "BOOLEAN")
        mod.operation, mod.object = "DIFFERENCE", cutter
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.modifier_apply(modifier="cutaway")
    bpy.data.objects.remove(cutter)
    box(((x0 + x1) / 2, -1.2, -0.2), (x1 - x0, 2.4, 0.08))              # rowers' floor
    for i in range(int((x1 - x0) / DIM["room"])):
        x = x0 + 0.5 + i * DIM["room"]
        box((x, -1.4, 2.62), (0.16, 2.9, 0.16))                          # deck beams
        box((x + 0.45, -0.02, 0.85), (0.14, 0.1, 3.6))                   # frames on the cut face
        rod((x, -0.7, -0.95), (x, -0.7, -0.35), 0.17, 0.12, 14)          # water jars in the hold
        ball((x, -0.7, -0.32), 0.08)
        ball((x + 0.5, -0.35, -0.85), 0.16)                              # ballast stones
        ball((x + 0.3, -1.0, -0.8), 0.13)

# --- scale figure on a float beside the bow, for the dimension check ---------------------------
before = set(scene.objects)
box((L + 4.0, -6.0, 0.05), (2.0, 2.0, 0.1))
person(L + 4.0, -6.0, 0.1)
scale_figure = [o for o in scene.objects if o not in before]

# --- sea, clay, light, camera ------------------------------------------------------------------
bpy.ops.mesh.primitive_plane_add(size=400, location=(0, 0, 0))
sea = bpy.context.active_object
if CUTAWAY:   # open the sea in front of the window too, so the hold below the waterline shows
    cutter = box(((WINDOW[0] + WINDOW[1]) / 2, -6.0, 0.0), (WINDOW[1] - WINDOW[0], 12.0, 1.0))
    mod = sea.modifiers.new("cutaway", "BOOLEAN")
    mod.operation, mod.object = "DIFFERENCE", cutter
    bpy.context.view_layer.objects.active = sea
    bpy.ops.object.modifier_apply(modifier="cutaway")
    bpy.data.objects.remove(cutter)
clay = bpy.data.materials.new("clay")
clay.use_nodes = True
clay.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.6, 0.58, 0.54, 1)
clay.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.9
water = bpy.data.materials.new("sea")
water.use_nodes = True
water.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.12, 0.2, 0.28, 1)
water.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.6
for o in scene.objects:
    if o.type == "MESH":
        o.data.materials.clear()   # a boolean leaves an empty slot that the faces point to
        o.data.materials.append(water if o.name == sea.name else clay)

if CUTAWAY:   # path tracing: sky light shades the inside of the window without hard cast shadows
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 64
engines = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
if not CUTAWAY:
    scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engines else "BLENDER_EEVEE"
scene.render.resolution_x, scene.render.resolution_y = 1280, 720
scene.view_settings.view_transform = "Standard"
world = bpy.data.worlds.new("w"); scene.world = world; world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.15, 0.2, 0.25, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = 1.4
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); scene.collection.objects.link(sun)
sun.data.energy = 3.0
sun.data.use_shadow = False   # cast shadows turn into invented objects in the image model (LEARNINGS)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); scene.collection.objects.link(cam); scene.camera = cam
cam.data.lens = 50
target = Vector((0, 0, 4.0))
VIEWS = {"tri": (300, 13 if CUTAWAY else 24, 72.0), "bok": (270, 6, 80.0)}   # azimuth, elevation, distance
for o in scale_figure:
    o.hide_render = True
for name, (az, el, dist) in VIEWS.items():
    a, e = math.radians(az), math.radians(el)
    cam.location = target + Vector((math.cos(a) * math.cos(e), math.sin(a) * math.cos(e), math.sin(e))) * dist
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    sun.rotation_euler = (target - cam.location + Vector((0, 0, -30))).to_track_quat("-Z", "Y").to_euler()
    sun.rotation_euler.z += math.radians(30)
    scene.render.filepath = f"{prefix}-{name}.png"
    bpy.ops.render.render(write_still=True)

# orthographic plan and side view for the dimension check (px per metre printed for the overlay)
cam.data.type, cam.data.ortho_scale = "ORTHO", 56.0
for o in scale_figure:
    o.hide_render = False
for name, loc, rot in (("plan", (2.0, 0, 60), (0, 0, 0)), ("profil", (2.0, -60, 4.0), (math.radians(90), 0, 0))):
    cam.location, cam.rotation_euler = loc, rot
    scene.render.filepath = f"{prefix}-{name}.png"
    bpy.ops.render.render(write_still=True)
print("ortho px_per_m", scene.render.resolution_x / cam.data.ortho_scale, "centre_x", 2.0)
