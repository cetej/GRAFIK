# Blender: the bones of the pelvis and legs with the stab wounds. Bones: BodyParts3D (CC BY-SA 2.1 JP), a modern man, not the scan of the victim. Wounds: placed by eye on the book's scans fig. panev_leva and panev_prava, counts from the book: left at least 14 from behind, right 3 larger and 4 smaller from the front.
#   blender -b --factory-startup -P scripts/3d/velsen_kostra.py -- BP3D_DIR OUT_DIR [--w 1240] [--h 2000] [--samples 128] [--gpu] [--pohledy panev:-82:22] [--vyska 1.32] [--stred -0.42] [--kontrola]
# Red rods show the direction of each stab, the dark blade (23 cm, p. 68) stands in the largest wound as in the book's fig. Writes <view>.png (RGBA) and body.json.
import json
import math
import random
import sys
from pathlib import Path

import bmesh
import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

ARGS = sys.argv[sys.argv.index("--") + 1:]
SRC, OUT = Path(ARGS[0]).resolve(), Path(ARGS[1]).resolve()


def arg(name, default):
    return type(default)(ARGS[ARGS.index(name) + 1]) if name in ARGS else default


W, H, SAMPLES = arg("--w", 1240), arg("--h", 2000), arg("--samples", 128)
OUT.mkdir(parents=True, exist_ok=True)
random.seed(77)

# u, v in the frame of the bone as the book shows it (0 to 1 from the anterior, resp. posterior, end and from the crest), size of the slit in m
LEFT = [(0.37, 0.14, 0.034), (0.43, 0.23, 0.022), (0.47, 0.20, 0.014), (0.49, 0.24, 0.014), (0.52, 0.27, 0.014), (0.51, 0.32, 0.014), (0.47, 0.30, 0.012),
        (0.56, 0.21, 0.012), (0.60, 0.28, 0.014), (0.67, 0.32, 0.016), (0.72, 0.27, 0.016), (0.63, 0.20, 0.012), (0.55, 0.33, 0.012), (0.42, 0.33, 0.012)]
RIGHT = [(0.26, 0.17, 0.03), (0.28, 0.25, 0.028), (0.32, 0.21, 0.026), (0.39, 0.20, 0.012), (0.17, 0.21, 0.012), (0.22, 0.21, 0.012), (0.34, 0.27, 0.012)]
FROM_BEHIND = Vector((-0.6, -0.78, -0.18)).normalized()    # the way the blade travelled, person's left is +x, the front is -y
FROM_FRONT = Vector((-0.45, 0.88, -0.14)).normalized()


def rgb(h):
    def lin(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return (lin(int(h[1:3], 16) / 255), lin(int(h[3:5], 16) / 255), lin(int(h[5:7], 16) / 255), 1.0)


def bone_mat():
    """The brown of the bones in the book's photograph, a little mottled."""
    m = bpy.data.materials.new("Kost")
    m.use_nodes = True
    n, l = m.node_tree.nodes, m.node_tree.links
    p = n["Principled BSDF"]
    tc, nz, r = n.new("ShaderNodeTexCoord"), n.new("ShaderNodeTexNoise"), n.new("ShaderNodeValToRGB")
    nz.inputs["Scale"].default_value, nz.inputs["Detail"].default_value = 220.0, 8.0
    l.new(tc.outputs["Object"], nz.inputs["Vector"])
    r.color_ramp.elements[0].position, r.color_ramp.elements[0].color = 0.4, rgb("#9a7346")
    r.color_ramp.elements[1].position, r.color_ramp.elements[1].color = 0.62, rgb("#ae8654")
    l.new(nz.outputs["Fac"], r.inputs["Fac"])
    geo, cav, mul = n.new("ShaderNodeNewGeometry"), n.new("ShaderNodeValToRGB"), n.new("ShaderNodeMix")
    cav.color_ramp.elements[0].position, cav.color_ramp.elements[0].color = 0.46, (0.28, 0.24, 0.2, 1)
    cav.color_ramp.elements[1].position, cav.color_ramp.elements[1].color = 0.52, (1, 1, 1, 1)
    l.new(geo.outputs["Pointiness"], cav.inputs["Fac"])
    mul.data_type, mul.blend_type = "RGBA", "MULTIPLY"
    mul.inputs["Factor"].default_value = 1.0
    l.new(r.outputs["Color"], mul.inputs["A"])
    l.new(cav.outputs["Color"], mul.inputs["B"])
    l.new(mul.outputs["Result"], p.inputs["Base Color"])
    p.inputs["Roughness"].default_value = 0.62
    b = n.new("ShaderNodeBump")
    b.inputs["Strength"].default_value, b.inputs["Distance"].default_value = 0.35, 0.002
    l.new(nz.outputs["Fac"], b.inputs["Height"])
    l.new(b.outputs["Normal"], p.inputs["Normal"])
    return m


def flat_mat(name, colour, rough=0.5, metallic=0.0, glow=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = m.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = rgb(colour)
    p.inputs["Roughness"].default_value = rough
    p.inputs["Metallic"].default_value = metallic
    p.inputs["Emission Color"].default_value = rgb(colour)
    p.inputs["Emission Strength"].default_value = glow
    return m


def load_bones():
    """All parts in metres, Z up, centred on the pelvis. Returns {name: object}."""
    names = dict(line.split("\t") for line in (SRC / "nazvy.txt").read_text(encoding="utf-8").splitlines())
    mat, parts = bone_mat(), {}
    for fma, name in names.items():
        bpy.ops.wm.stl_import(filepath=str(SRC / f"{fma}.stl"), global_scale=0.001)
        o = bpy.context.object
        o.name = name
        o.data.transform(o.matrix_world)    # the importer may leave the scale on the object
        o.matrix_world = Matrix.Identity(4)
        bm = bmesh.new()
        bm.from_mesh(o.data)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.00002)
        bm.to_mesh(o.data)
        bm.free()
        o.data.shade_smooth()
        o.data.materials.append(mat)
        parts[name] = o
    bpy.context.view_layer.update()
    # the data's axes: find them from the bones, not from a guess
    def centre(o):
        return sum((o.matrix_world @ Vector(c) for c in o.bound_box), Vector()) / 8
    left, right, sac = centre(parts["left femur"]), centre(parts["right femur"]), centre(parts["sacrum"])
    hips = (centre(parts["left hip bone"]) + centre(parts["right hip bone"])) / 2
    sign_x = 1 if left.x > right.x else -1          # person's left must be +x
    lowest = min((o.matrix_world @ Vector(c)).z for o in parts.values() for c in o.bound_box)
    pubis_y = min((v.co.y for v in parts["left hip bone"].data.vertices), key=lambda y: y)
    back_y = max((v.co.y for v in parts["left hip bone"].data.vertices))
    sign_y = 1 if sac.y > (pubis_y + back_y) / 2 else -1     # the sacrum lies behind: behind must be +y
    print("OSY", "left.x", round(left.x, 3), "right.x", round(right.x, 3), "sign", sign_x, sign_y, "lowest", round(lowest, 3), "hips", [round(v, 3) for v in hips])
    fix = Matrix.Diagonal((sign_x, sign_y, 1, 1)) @ Matrix.Translation(-hips)
    for o in parts.values():
        o.data.transform(fix)
        if sign_x * sign_y < 0:     # a mirror turns the faces inside out
            o.data.flip_normals()
        o.data.update()
    bpy.context.view_layer.update()
    return parts


def frame_of_wing(hip, lateral):
    """The bone as the book shows it: a view along the outward normal of the iliac wing. Returns origin, right, up, normal and the extent in that frame."""
    verts = [v.co.copy() for v in hip.data.vertices]
    wing = [v for v in verts if v.z > sum(p.z for p in verts) / len(verts) + 0.015]
    c = sum(wing, Vector()) / len(wing)
    # the normal of the wing by least squares
    xx = xy = xz = yy = yz = zz = 0.0
    for v in wing:
        r = v - c
        xx += r.x * r.x; xy += r.x * r.y; xz += r.x * r.z; yy += r.y * r.y; yz += r.y * r.z; zz += r.z * r.z
    m = Matrix(((xx, xy, xz), (xy, yy, yz), (xz, yz, zz)))
    n = Vector((1, 0.3, 0.1))
    inv = m.inverted_safe()
    for _ in range(40):
        n = (inv @ n).normalized()
    if n.x * lateral < 0:
        n = -n
    up = (Vector((0, 0, 1)) - n * n.z).normalized()
    right = up.cross(n).normalized()
    us = [(v - c).dot(right) for v in verts]
    vs = [(v - c).dot(up) for v in verts]
    return c, right, up, n, (min(us), max(us), min(vs), max(vs))


def add_slit(name, at, normal, edge, size, mat):
    """The wound on the surface: a thin red lens along the blade's edge."""
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=3, radius=1.0)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.shade_smooth()
    me.materials.append(mat)
    o = bpy.data.objects.new(name, me)
    side = normal.cross(edge).normalized()
    x, y, z = edge * size / 2, side * size * 0.13, normal * 0.0009
    o.matrix_world = Matrix(((x.x, y.x, z.x, at.x), (x.y, y.y, z.y, at.y), (x.z, y.z, z.z, at.z), (0, 0, 0, 1)))
    bpy.context.collection.objects.link(o)
    return o


def add_rod(name, a, b, radius, mat):
    axis = b - a
    bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=radius, depth=axis.length, location=(a + b) / 2)
    o = bpy.context.object
    o.name = name
    o.rotation_mode = "QUATERNION"
    o.rotation_quaternion = axis.to_track_quat("Z", "Y")
    o.data.materials.append(mat)
    return o


def add_blade(tip, direction, edge, mat, length=0.23, width=0.05, thick=0.007):
    """A tapering flat blade, its tip past the bone, the rest outside on the way it came."""
    d = direction.normalized()
    side = edge.normalized()
    flat = d.cross(side).normalized()
    rows = 16
    verts, faces = [], []
    for r in range(rows + 1):
        t = r / rows
        c = tip - d * length * t
        half = width / 2 * (t ** 0.85) * (1 - 0.18 * math.sin(math.pi * min(1, t * 1.3)))     # the waisted blade of a pugio
        th = thick / 2 * (t ** 0.7)
        verts += [tuple(c + side * half), tuple(c + flat * th), tuple(c - side * half), tuple(c - flat * th)]
    for r in range(rows):
        for k in range(4):
            faces.append((r * 4 + k, r * 4 + (k + 1) % 4, (r + 1) * 4 + (k + 1) % 4, (r + 1) * 4 + k))
    faces.append(tuple(rows * 4 + k for k in range(4)))
    me = bpy.data.meshes.new("Čepel")
    me.from_pydata(verts, [], faces)
    me.update()
    me.materials.append(mat)
    o = bpy.data.objects.new("Čepel", me)
    bpy.context.collection.objects.link(o)
    return o


def wounds(hip, marks, travel, from_inside, red, red_dark, steel, rod_len, blade=False):
    """Rays through the book's positions onto the wing; a slit and a rod at each. Returns the hit points, the largest first."""
    lateral = 1 if hip.name.startswith("left") else -1
    c, right, up, n, (u0, u1, v0, v1) = frame_of_wing(hip, lateral)
    tree = BVHTree.FromPolygons([v.co.copy() for v in hip.data.vertices], [tuple(p.vertices) for p in hip.data.polygons], all_triangles=False)
    # the anterior end must be u = 0: flip the frame when it is not
    front_is_low = (c + right * u0).y < (c + right * u1).y
    hits = []
    for i, (u, v, size) in enumerate(marks):
        uu = u0 + (u1 - u0) * (u if front_is_low else 1 - u)
        vv = v1 + (v0 - v1) * v
        point = c + right * uu + up * vv
        look = n if from_inside else -n
        loc, normal, _, _ = tree.ray_cast(point - look * 0.2, look, 0.4)
        if loc is None:
            print("VPICH MIMO KOST", hip.name, i, u, v)
            continue
        hits.append(loc)
        edge = (up.cross(normal)).normalized()
        add_slit(f"{hip.name} vpich {i}", loc, normal, edge, size, red_dark)
        add_rod(f"{hip.name} směr {i}", loc, loc - travel * rod_len * (0.8 + 0.3 * random.random()), 0.0014, red)
    # the blade in the largest wound
    if blade:
        add_blade(hits[0] + travel * 0.05, travel, up.cross(travel).normalized(), steel)
    return hits


def scene_setup():
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
    sc.render.film_transparent = True
    sc.render.image_settings.file_format, sc.render.image_settings.color_mode = "PNG", "RGBA"
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
    world = bpy.data.worlds.new("Svět")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.62, 0.6, 0.58, 1)
    world.node_tree.nodes["Background"].inputs[1].default_value = 0.28
    sc.world = world
    return sc


def light(name, loc, power, size, target=(0, 0, -0.2)):
    d = bpy.data.lights.new(name, "AREA")
    d.energy, d.size = power, size
    o = bpy.data.objects.new(name, d)
    o.location = loc
    o.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    bpy.context.collection.objects.link(o)
    return o


def main():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    parts = load_bones()
    red = flat_mat("Směr", "#c8101a", 0.5, 0, 0.35)
    red_dark = flat_mat("Vpich", "#8e0810", 0.5, 0, 0.3)
    steel = flat_mat("Čepel", "#55514d", 0.35, 0.9)
    left = wounds(parts["left hip bone"], LEFT, FROM_BEHIND, False, red, red_dark, steel, 0.11, blade=True)
    right = wounds(parts["right hip bone"], RIGHT, FROM_FRONT, False, red, red_dark, steel, 0.11)
    marks = {o.name: o for o in bpy.data.objects if "vpich" in o.name or "směr" in o.name or o.name == "Čepel"}
    sc = scene_setup()

    cam = bpy.data.cameras.new("Kamera")
    cam.sensor_fit = "VERTICAL"
    cam.clip_start = 0.02
    co = bpy.data.objects.new("Kamera", cam)
    bpy.context.collection.objects.link(co)
    sc.camera = co
    body = {}
    # one pelvis with all the wounds, seen from the front a little from above as in the book's fig.: the wounds of the right wing in plain sight, those on the back of the left wing go in <view>-duch.png, to shine through the bone on the page. Long lens, the wide one deformed the pelvis.
    #   --pohledy NAME:AZ:EL[,...] azimuth from the person's left towards the back, elevation; --vyska frame height in metres at the pelvis, --stred z of the middle of the frame
    dist, height, middle = arg("--dist", 3.2), arg("--vyska", 1.32), arg("--stred", -0.42)
    lens_all = cam.sensor_height * dist / height
    views = {}
    for spec in arg("--pohledy", "panev:-82:22").split(","):
        label, az, el = spec.split(":")
        a, e = math.radians(float(az)), math.radians(float(el))
        loc = Vector((dist * math.cos(e) * math.cos(a), dist * math.cos(e) * math.sin(a), middle + dist * math.sin(e)))
        side = Vector((-math.sin(a), math.cos(a), 0)) * 1.6
        views[label] = (tuple(loc), (0.0, 0.0, middle), lens_all, (tuple(loc * 0.9 + side + Vector((0, 0, 1.0))), tuple(loc * 0.8 - side * 1.3)))
    # straight on without perspective: the check of the model against the book's scan
    if "--kontrola" in ARGS:
        views = {"rovne_zepredu": ((0, -2.5, 0), (0, 0, 0), 0.0, ((-1.2, -2.6, 1.8), (2.4, -1.6, 0.0))),
                 "rovne_zezadu": ((0, 2.5, 0), (0, 0, 0), 0.0, ((1.8, 2.4, 1.8), (-2.4, 1.6, 0.0))),
                 "rovne_bok": ((2.5, 0, 0), (0, 0, 0), 0.0, ((2.4, 1.8, 1.8), (1.6, -2.4, 0.0)))}
    for name, (loc, target, lens, lamps) in views.items():
        if lens:
            cam.type, cam.lens = "PERSP", lens
        else:
            cam.type, cam.ortho_scale = "ORTHO", 0.46
        co.location = loc
        co.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        lights = [light(f"{name} hlavní", lamps[0], 260, 1.6), light(f"{name} výplň", lamps[1], 45, 2.5)]
        bpy.context.view_layer.update()

        def px(v):
            p = world_to_camera_view(sc, co, Vector(v))
            return (round(p.x * W, 1), round((1 - p.y) * H, 1))

        body[name] = {"res": [W, H], "levy": px(sum(left, Vector()) / len(left)), "levy_max": px(left[0]), "pravy": px(sum(right, Vector()) / len(right)), "pravy_max": px(right[0]),
                      "levy_handle": px(left[0] - FROM_BEHIND * 0.17), "pravy_handle": px(right[0] - FROM_FRONT * 0.17),
                      "koleno": px(sum((Vector(c) for c in parts["left patella"].bound_box), Vector()) / 8)}
        sc.render.filepath = str(OUT / f"{name}.png")
        bpy.ops.render.render(write_still=True)
        # the wounds on the far side alone
        for o in parts.values():
            o.hide_render = True
        for key, o in marks.items():
            o.hide_render = "right" in key
        sc.render.filepath = str(OUT / f"{name}-duch.png")
        bpy.ops.render.render(write_still=True)
        for o in list(parts.values()) + list(marks.values()):
            o.hide_render = False
        for o in lights:
            bpy.data.objects.remove(o)
    (OUT / "body.json").write_text(json.dumps(body, indent=1), encoding="utf-8")
    print("HOTOVO")


main()
