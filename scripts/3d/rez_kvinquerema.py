# Cross-section of a Roman quinquereme, built from numbers (free):
#   blender -b -P scripts/3d/rez_kvinquerema.py -- out_prefix
# TRELLIS only makes an outer shell, so the inside is modelled here: a three-room slice of the hull
# amidships, cut open towards the camera. Rowing system after J. S. Morrison's reconstruction (same as
# schemas/rez-trupem-kvinquerema.svg): three levels, 2 men on the top oar (outrigger), 2 on the
# middle, 1 on the lowest. Metres; x = towards the bow, y = across, z = up, waterline z = 0.
# Rendered as matte clay: the image generator takes shape from it, colour from the prompt.
import math
import sys

import bmesh
import bpy
from mathutils import Vector

prefix = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

ROOM, ROOMS = 0.98, 3                     # interscalmium (oar spacing) and slice length in rooms
LEN = ROOM * ROOMS + 0.3
KEEL_Z, DECK_Z = -1.25, 3.0
WD, OUT = 2.9, 3.5     # deck half-width, outer face of the outrigger (lod_kvinquerema.py)
# outer half-width of the hull at height z (flared U, widest at the oar ports)
PROFILE = [(-1.25, 0.25), (-0.9, 1.35), (-0.5, 2.05), (0.0, 2.5), (0.6, 2.75), (1.4, 2.88), (2.3, 2.9)]
WALL = 0.12


def obj_from_bm(bm, name):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    scene.collection.objects.link(o)
    return o


def prism(poly_yz, x0, x1, name):
    """Extrude a closed polygon in the yz plane from x0 to x1."""
    bm = bmesh.new()
    vs = [bm.verts.new((x0, y, z)) for y, z in poly_yz]
    f = bm.faces.new(vs)
    ext = bmesh.ops.extrude_face_region(bm, geom=[f])
    for v in [e for e in ext["geom"] if isinstance(e, bmesh.types.BMVert)]:
        v.co.x = x1
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return obj_from_bm(bm, name)


def box(c, s, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=c, rotation=rot)
    bpy.context.active_object.scale = s
    return bpy.context.active_object


def rod(a, b, r, verts=10):
    a, b = Vector(a), Vector(b)
    d = b - a
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=d.length, location=(a + b) / 2)
    bpy.context.active_object.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
    return bpy.context.active_object


def ball(c, r):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=c, segments=16, ring_count=8)
    return bpy.context.active_object


def half_width(z):
    for (z0, w0), (z1, w1) in zip(PROFILE, PROFILE[1:]):
        if z0 <= z <= z1:
            return w0 + (w1 - w0) * (z - z0) / (z1 - z0)
    return PROFILE[-1][1]


# --- hull shell: U-shaped wall, ribs, keel, wales -------------------------------------------
outer = PROFILE
inner = [(z, max(w - WALL, 0.05)) for z, w in PROFILE]
inner[0] = (KEEL_Z + WALL, 0.12)
# one closed loop: right outer up, right inner down, left inner up, left outer down
loop = [(w, z) for z, w in outer] + [(w, z) for z, w in reversed(inner)][:-1]
loop += [(-w, z) for z, w in inner][1:] + [(-w, z) for z, w in reversed(outer)]
prism(loop, 0, LEN, "hull")
for i in range(int(LEN / 0.5) + 1):                      # ribs every half metre
    rib_in = [(z, max(w - WALL - 0.1, 0.05)) for z, w in inner]
    rl = [(w, z) for z, w in inner] + [(w, z) for z, w in reversed(rib_in)][:-1]
    rl += [(-w, z) for z, w in rib_in][1:] + [(-w, z) for z, w in reversed(inner)]
    prism(rl, i * 0.5 + 0.1, i * 0.5 + 0.2, "rib")
box((LEN / 2, 0, KEEL_Z - 0.12), (LEN, 0.3, 0.3))       # keel
for s in (-1, 1):
    for z in (0.15, 0.9):                                 # wales
        box((LEN / 2, s * (half_width(z) + 0.05), z), (LEN, 0.12, 0.16))

# floor of the rowing space, hold beneath with water jars and ballast stones
box((LEN / 2, 0, -0.18), (LEN, 2 * half_width(-0.18) - 0.3, 0.08))
for i in range(5):
    for s in (-1, 1):
        x = 0.35 + i * 0.6
        rod((x, s * 0.55, -0.95), (x, s * 0.55, -0.35), 0.17, 14)
        ball((x, s * 0.55, -0.32), 0.09)
for i in range(14):
    ball((0.2 + (i * 0.37) % LEN, -0.25 + (i % 3) * 0.25, -1.05), 0.12 + (i % 2) * 0.04)

# --- deck, bulwark, shields, outriggers ------------------------------------------------------
box((LEN / 2, 0, DECK_Z), (LEN, 2 * WD, 0.1))
for i in range(ROOMS + 1):
    box((0.2 + i * ROOM, 0, DECK_Z - 0.15), (0.14, 2 * WD - 0.1, 0.2))     # deck beams
for s in (-1, 1):
    box((LEN / 2, s * WD, DECK_Z + 0.5), (LEN, 0.08, 1.0))           # bulwark
    for i in range(4):
        rod((0.45 + i * 0.8, s * (WD + 0.06), DECK_Z + 0.55), (0.45 + i * 0.8, s * (WD + 0.11), DECK_Z + 0.55), 0.38, 24)
    # outrigger (parexeiresia) carrying the top oars
    box((LEN / 2, s * (WD + OUT) / 2, 2.25), (LEN, OUT - WD, 0.1))
    box((LEN / 2, s * OUT, 2.0), (LEN, 0.08, 0.5))
    box((LEN / 2, s * WD, 2.55), (LEN, 0.08, 0.5))
    for i in range(ROOMS + 1):
        box((0.2 + i * ROOM, s * (WD + OUT) / 2, 2.0), (0.08, OUT - WD, 0.08))
# side wall between outrigger and deck
for s in (-1, 1):
    box((LEN / 2, s * WD, (2.3 + DECK_Z) / 2), (LEN, WALL, DECK_Z - 2.3))

# --- rowers ------------------------------------------------------------------------------------
def rower(seat, hand):
    """Seated rower facing the stern (-x), hands on the oar loom at `hand`."""
    x, y, z = seat
    box((x, y, z - 0.08), (0.45, 0.42, 0.06))                  # bench
    hip, sh = Vector((x, y, z + 0.1)), Vector((x + 0.12, y, z + 0.62))
    rod(hip, sh, 0.15, 12)                                       # torso
    ball((x + 0.14, y, z + 0.8), 0.11)                           # head
    knee, foot = Vector((x - 0.42, y, z + 0.12)), Vector((x - 0.5, y, z - 0.35))
    for dy in (-0.1, 0.1):
        rod(hip + Vector((0, dy, 0)), knee + Vector((0, dy, 0)), 0.06, 8)
        rod(knee + Vector((0, dy, 0)), foot + Vector((0, dy, 0)), 0.05, 8)
        rod(sh + Vector((0, dy * 1.7, -0.02)), Vector(hand) + Vector((0, dy, 0)), 0.04, 8)


# (thole y, thole z, slope, men, seat height above thole, x stagger)
LEVELS = {"thranite": (OUT, 1.95, 0.33, 2, -0.2, 0.0),
          "zygite": (half_width(1.2), 1.2, 0.35, 2, -0.2, 0.0),
          "thalamite": (half_width(0.45), 0.45, 0.42, 1, -0.2, ROOM / 2)}
for name, (ty, tz, slope, men, seat_dz, stagger) in LEVELS.items():
    for i in range(ROOMS):
        ox = 0.35 + i * ROOM + stagger
        for s in (-1, 1):
            hand_z = tz + 0.42
            hy = ty - (hand_z - tz) / slope                  # where the first man holds the loom
            inner_y = hy - 0.55 * (men - 1) - 0.25
            tip_y = ty + (tz + 0.1) / slope
            a = Vector((ox, s * inner_y, tz + slope * (ty - inner_y)))
            b = Vector((ox, s * tip_y, -0.1))
            rod(a, b, 0.045, 10)                             # oar
            blade = b - (b - a).normalized() * 0.4
            box(blade, (0.04, 0.8, 0.16), ((b - a).to_track_quat("Y", "Z").to_euler()))
            rod((ox, s * (ty - 0.06), tz), (ox, s * (ty + 0.06), tz), 0.08, 12)   # port / thole sleeve
            for m in range(men):
                yy = hy - 0.55 * m
                rower((ox + 0.55, s * (yy - 0.05), tz + seat_dz - (0.25 if name != "thranite" else 0.0)),
                      (ox, s * yy, tz + slope * (ty - yy)))

# --- marines on deck (no tower: not attested for the First Punic War, see lod_kvinquerema.py) ------
for i, (x, y) in enumerate([(0.6, -1.6), (0.9, -0.6), (1.4, 0.7), (0.7, 1.6), (1.9, -1.2), (2.2, 1.1)]):
    z = DECK_Z + 0.05
    rod((x, y, z), (x, y, z + 1.25), 0.17, 12)
    ball((x, y, z + 1.42), 0.13)
    rod((x - 0.25, y, z + 0.75), (x - 0.3, y, z + 0.75), 0.33, 20)    # shield facing the bow end
    rod((x - 0.1, y + 0.25, z), (x - 0.1, y + 0.25, z + 2.2), 0.025, 6)  # spear

# --- sea, cut open on the same plane as the hull ---------------------------------------------
water = box((LEN / 2, 0, -0.9), (LEN, 22, 1.8))
solid = prism([(w, z) for z, w in PROFILE] + [(-w, z) for z, w in reversed(PROFILE)], -0.1, LEN + 0.1, "solid")
mod = water.modifiers.new("cut", "BOOLEAN")
mod.operation, mod.object = "DIFFERENCE", solid
bpy.context.view_layer.objects.active = water
bpy.ops.object.modifier_apply(modifier="cut")
bpy.data.objects.remove(solid)

# --- clay, light, camera -----------------------------------------------------------------------
clay = bpy.data.materials.new("clay")
clay.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.62, 0.6, 0.56, 1)
clay.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.9
sea = bpy.data.materials.new("sea")
sea.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.16, 0.26, 0.36, 1)
for o in scene.objects:
    if o.type == "MESH":
        o.data.materials.clear()   # the boolean leaves an empty slot that the faces point to
        o.data.materials.append(sea if o.name == water.name else clay)

engines = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engines else "BLENDER_EEVEE"
scene.render.resolution_x, scene.render.resolution_y = 1280, 900
scene.render.film_transparent = True
scene.view_settings.view_transform = "Standard"
world = bpy.data.worlds.new("w"); scene.world = world
world.node_tree.nodes["Background"].inputs[1].default_value = 0.9
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); scene.collection.objects.link(sun)
sun.data.energy = 1.6
sun.data.use_shadow = False
fill = bpy.data.objects.new("fill", bpy.data.lights.new("fill", "AREA")); scene.collection.objects.link(fill)
fill.data.energy, fill.data.size = 250, 8
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); scene.collection.objects.link(cam); scene.camera = cam
cam.data.lens = 35
target = Vector((1.0, 0, 0.9))
for name, loc in {"front": (-13.0, -5.0, 4.5), "straight": (-15.0, 0.0, 3.2)}.items():
    cam.location = loc
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    sun.rotation_euler = (target - cam.location + Vector((0, 4, -6))).to_track_quat("-Z", "Y").to_euler()
    fill.location = Vector(loc) * 0.6 + target * 0.4
    fill.rotation_euler = (target - fill.location).to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = f"{prefix}-{name}.png"
    bpy.ops.render.render(write_still=True)
