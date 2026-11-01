# Realistic 3D models of Tesla's machines for scripts/plakaty/tesla_kopie.py, free, run through tesla_render.py under the heavy lock:
#   blender -b --factory-startup -P scripts/3d/tesla_stroje.py -- SHOT OUT_DIR [--samples 96] [--res W H]
# SHOT = motor | civka | vez | vez-nad | hala | turbina | elektrarna | transformator | prijimac | lod | trubice | trubice2. Writes OUT_DIR/SHOT/obraz.png (transparent, with a contact shadow) and body.json,
# which holds the canvas position of every named point, so a label sits exactly on the machine.
# Proportions follow the patent drawings and the sources in docs/spikes/2026-11-01-plakaty-osoba-zvire.md, details without a source are illustrative.
import json
import math
import random
import sys
from pathlib import Path

import bmesh
import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "engine" / "blender"))

import parts_materials as pm  # noqa: E402

args = sys.argv[sys.argv.index("--") + 1:]
SHOT, OUT = args[0], Path(args[1]).resolve() / args[0]   # Blender writes a relative render path somewhere else than the working directory


def opt(name, default, n=1):
    if name in args:
        i = args.index(name)
        return args[i + 1] if n == 1 else args[i + 1:i + 1 + n]
    return default


SAMPLES = int(opt("--samples", 96))
RES = [int(v) for v in opt("--res", (1400, 1400), 2)]
if "--res" not in args:
    RES = {"vez": [1300, 1800], "civka": [1200, 1400], "vez-nad": [900, 1600], "hala": [1600, 700], "prijimac": [1600, 800], "lod": [1600, 700], "trubice": [1600, 500], "trubice2": [800, 1400], "elektrarna": [1300, 1560]}.get(SHOT, RES)
TWO_PI = 2 * math.pi
POINTS = {}


def material(name, a, b=None, scale=200.0, rough=0.5, metal=0.0, dist=0.05, ao=0.6, bump=0.0, bevel=0.0):
    m, t, bsdf = pm.new_mat(name, rough, metal)
    co = pm.coords(t)
    fac = pm.noise_of(t, co, scale)
    pm.aged(t, bsdf, pm.ramp_of(t, fac, a, b or a), ao, dist, bevel)
    if bump:
        bp = t.nodes.new("ShaderNodeBump")
        bp.inputs["Strength"].default_value = bump
        bp.inputs["Distance"].default_value = 0.002
        t.links.new(pm.noise_of(t, co, scale * 4), bp.inputs["Height"])
        t.links.new(bp.outputs[0], bsdf.inputs["Normal"])
    return m


def emission(name, color, strength):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    t = m.node_tree
    t.nodes.clear()
    out = t.nodes.new("ShaderNodeOutputMaterial")
    em = t.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*color, 1)
    em.inputs["Strength"].default_value = strength
    t.links.new(em.outputs[0], out.inputs["Surface"])
    return m


def link(o):
    bpy.context.scene.collection.objects.link(o)
    return o


def mesh(name, verts, faces, mat, smooth=40, bevel=0.0):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    me.update()
    me.materials.append(mat)
    o = link(bpy.data.objects.new(name, me))
    if smooth:
        bpy.context.view_layer.objects.active = o
        o.select_set(True)
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(smooth))
        o.select_set(False)
    if bevel:
        mod = o.modifiers.new("bevel", "BEVEL")
        mod.width, mod.segments, mod.limit_method = bevel, 2, "ANGLE"
    return o


def to_axis(r, a, h, axis):
    x, y = r * math.cos(a), r * math.sin(a)
    return {"z": (x, y, h), "y": (x, h, y), "x": (h, x, y)}[axis]


def lathe(name, prof, mat, axis="z", n=128, a0=0.0, a1=TWO_PI, at=(0, 0, 0), smooth=40, bevel=0.0):
    """Revolves a closed profile of (r, h); a partial sweep gets flat ends."""
    whole = abs(a1 - a0) >= TWO_PI - 1e-6
    rings = n if whole else n + 1
    m = len(prof)
    v = [tuple(c + o for c, o in zip(to_axis(r, a0 + (a1 - a0) * i / n, h, axis), at)) for i in range(rings) for r, h in prof]
    f = [(i * m + j, i * m + (j + 1) % m, ((i + 1) % rings) * m + (j + 1) % m, ((i + 1) % rings) * m + j)
         for i in range(n) for j in range(m)]
    if not whole:
        f += [tuple(range(m)), tuple(range(n * m, n * m + m))]
    return mesh(name, v, f, mat, smooth, bevel)


def box(name, lo, hi, mat, bevel=0.0, place=None):
    (x0, y0, z0), (x1, y1, z1) = lo, hi
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    f = [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    o = mesh(name, v, f, mat, 0, bevel)
    if place is not None:
        o.matrix_world = place
    return o


def beam(name, p, q, w, mat, depth=None):
    """A square timber or bar between two points."""
    p, q = Vector(p), Vector(q)
    d = q - p
    rot = d.to_track_quat("Z", "Y").to_matrix().to_4x4()
    return box(name, (-w / 2, -(depth or w) / 2, 0), (w / 2, (depth or w) / 2, d.length), mat, 0, Matrix.Translation(p) @ rot)


def tube(name, pts, r, mat, cyclic=False, shadow=True):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions, cu.bevel_depth, cu.bevel_resolution, cu.resolution_u, cu.fill_mode = "3D", r, 2, 1, "FULL"
    sp = cu.splines.new("POLY")
    sp.points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        sp.points[i].co = (*p, 1)
    sp.use_cyclic_u = cyclic
    cu.materials.append(mat)
    o = link(bpy.data.objects.new(name, cu))
    o.visible_shadow = shadow
    return o


def laminated(r0, r1, h0, h1, count):
    """Profile of a stack of sheets: the rim shows every sheet."""
    prof = [(r0, h0)]
    step = (h1 - h0) / count
    for i in range(count):
        h = h0 + i * step
        prof += [(r1, h + 0.08 * step), (r1, h + 0.82 * step), (r1 - 0.0012, h + 0.9 * step), (r1 - 0.0012, h + step)]
    prof.append((r0, h1))
    return prof


# ---------------------------------------------------------------- motor: two phases, four coils, patent US 381,968
def motor():
    cast = material("cast", "#2c332f", "#232926", 90, 0.48, bump=0.25, bevel=0.002)
    sheet = material("sheet", "#7f8488", "#75797d", 700, 0.36, 0.9, dist=0.03, ao=0.45)
    copper = material("copper", "#c47b43", "#a95f2e", 260, 0.3, 1.0, dist=0.012, ao=0.55)
    steel = material("steel", "#c4c7cb", "#aeb2b6", 400, 0.2, 1.0, dist=0.02, ao=0.3)
    brass = material("brass", "#c9a64f", "#b08d3e", 300, 0.28, 1.0, dist=0.02)
    ebonite = material("ebonite", "#17171b", "#101014", 200, 0.22, dist=0.02)

    r_i, r_o, y0, y1 = 0.15, 0.19, 0.0, 0.12
    cut0, cut1 = math.pi, math.pi + 1.5 * math.pi        # the upper left quarter is cut away
    lathe("stator", laminated(r_i, r_o, y0, y1, 34), sheet, "y", 120, cut0, cut1, smooth=0)
    lathe("frame", [(r_o, y0), (0.212, y0), (0.212, y1 + 0.006), (r_o, y1 + 0.006)], cast, "y", 120, cut0, cut1, smooth=30, bevel=0.0012)
    lathe("rear", [(0.0, y1 + 0.006), (0.212, y1 + 0.006), (0.212, y1 + 0.03), (0.0, y1 + 0.03)], cast, "y", 160, smooth=30, bevel=0.0015)
    lathe("boss", [(0, y1 + 0.03), (0.075, y1 + 0.03), (0.042, y1 + 0.075), (0.042, y1 + 0.115), (0, y1 + 0.115)], cast, "y", 96, smooth=30, bevel=0.0015)

    wt, wire = 0.027, 0.0031
    pole_angles = [math.radians(a) for a in (45, 135, 225, 315)]
    for k, a in enumerate(pole_angles):
        if k == 1:      # the quarter that is cut away
            continue
        er = Vector((math.cos(a), 0, math.sin(a)))
        et = Vector((-math.sin(a), 0, math.cos(a)))
        ey = Vector((0, 1, 0))
        centre = Vector((0, (y0 + y1) / 2, 0))
        rot = Matrix((et, ey, er)).transposed().to_4x4()   # local x = tangent, y = axis, z = radial
        box(f"pole{k}", (-wt, -0.056, 0.086), (wt, 0.056, r_i + 0.002), sheet, 0.001, Matrix.Translation(centre) @ rot)
        lathe(f"shoe{k}", [(0.0785, y0 + 0.004), (0.094, y0 + 0.004), (0.094, y1 - 0.004), (0.0785, y1 - 0.004)], sheet, "y", 24, a - math.radians(31), a + math.radians(31), smooth=0, bevel=0.0008)
        pts = []
        turns, layers = 9, 3
        for layer in range(layers):
            half_t = wt + wire * (1.15 + 2.1 * layer)
            half_y = 0.056 + wire * (1.15 + 2.1 * layer)
            corner = wire * 2.2
            loop = []
            for sx, sy, start in ((1, 1, 0), (-1, 1, 90), (-1, -1, 180), (1, -1, 270)):
                for s in range(5):
                    ang = math.radians(start + s * 22.5)
                    loop.append((sx * (half_t - corner) + corner * math.cos(ang), sy * (half_y - corner) + corner * math.sin(ang)))
            for t in range(turns * len(loop)):
                q = t / len(loop)
                z = 0.1 + (0.143 - 0.1) * (q / turns if layer % 2 == 0 else 1 - q / turns)
                u, v = loop[t % len(loop)]
                pts.append(tuple(centre + et * u + ey * v + er * z))
        tube(f"coil{k}", pts, wire, copper)
        POINTS.setdefault(f"civka{k}", tuple(centre + er * 0.122 + et * (wt + 0.012) - ey * (0.056 + 0.01)))
        POINTS.setdefault(f"pol{k}", tuple(centre + er * 0.09 - ey * 0.056))

    # rotor: a sheet stack with copper bars closed by two rings, on a steel shaft
    lathe("rotor", laminated(0.018, 0.0725, -0.002, 0.122, 30), sheet, "y", 128, smooth=0)
    for i in range(28):
        a = TWO_PI * i / 28
        c, s = math.cos(a), math.sin(a)
        tube(f"bar{i}", [(0.0725 * c, -0.009, 0.0725 * s), (0.0725 * c, 0.129, 0.0725 * s)], 0.0031, copper)
    for name, h0, h1 in (("end_f", -0.014, -0.004), ("end_b", 0.124, 0.134)):
        lathe(name, [(0.063, h0), (0.0755, h0), (0.0755, h1), (0.063, h1)], copper, "y", 96, smooth=30, bevel=0.001)
    lathe("shaft", [(0, -0.2), (0.012, -0.2), (0.0155, -0.196), (0.0155, -0.03), (0.021, -0.03), (0.021, 0.3), (0, 0.3)], steel, "y", 64, smooth=30)
    lathe("pulley", [(0, 0.248), (0.055, 0.248), (0.06, 0.258), (0.06, 0.29), (0.055, 0.3), (0, 0.3)], cast, "y", 96, smooth=30, bevel=0.001)
    box("key", (-0.0035, -0.19, 0.0125), (0.0035, -0.09, 0.0185), steel, 0.0005)

    # stand and terminals: four binding posts, two for each phase
    base_z = -0.27
    box("foot", (-0.27, -0.09, base_z), (0.27, 0.27, base_z + 0.026), cast, 0.004)
    box("stand", (-0.17, 0.0, base_z + 0.02), (0.17, y1 + 0.03, -0.17), cast, 0.004)
    for sx in (-1, 1):
        for y in (-0.05, 0.2):
            lathe(f"bolt{sx}{y}", [(0, base_z + 0.026), (0.016, base_z + 0.026), (0.016, base_z + 0.036), (0, base_z + 0.036)], steel, "z", 6, at=(sx * 0.235, y, 0), smooth=0)
    box("block", (0.0, 0.015, 0.196), (0.15, 0.105, 0.214), ebonite, 0.002)
    for i, x in enumerate((0.021, 0.057, 0.093, 0.129)):
        lathe(f"post{i}", [(0, 0.214), (0.0085, 0.214), (0.0085, 0.226), (0.0052, 0.226), (0.0052, 0.238), (0.0098, 0.238), (0.0098, 0.246), (0, 0.246)], brass, "z", 24, at=(x, 0.06, 0), smooth=30)
        c = pole_angles[0]
        end = (0.12 * math.cos(c), -0.005, 0.12 * math.sin(c))
        mid = ((x + end[0]) / 2, -0.005, 0.2)
        tube(f"lead{i}", [(x, 0.03, 0.22), (x, -0.008, 0.215), mid, end], 0.0018, copper)
    c45 = math.cos(math.radians(135))
    POINTS.update(svorky=(0.075, 0.06, 0.246), rotor=(0.0725 * c45, 0.05, -0.0725 * c45), hridel=(0.0, -0.17, 0.016), kostra=(-0.205, 0.0, -0.09), plech=(0.15, 0.0, 0.09),
                  rez=(-0.17, 0.05, 0.0))
    if SHOT == "motor":
        mirror = Matrix.Scale(-1, 4, (1, 0, 0))
        for o in bpy.context.scene.objects:
            o.matrix_world = mirror @ o.matrix_world
        for k, v in POINTS.items():
            POINTS[k] = (-v[0], v[1], v[2])
    return {"dir": (0.62, -1.0, 0.42), "lens": 90, "floor": base_z, "soft": 1.0}


# ---------------------------------------------------------------- coil: a tabletop resonance transformer, patent US 454,622
def spark(rng, start, heading, length, step, mat, name, branch=True):
    p = Vector(start)
    heading = Vector(heading).normalized()
    pts = [tuple(p)]
    walked = 0.0
    index = 0
    while walked < length:
        turn = Vector((rng.gauss(0, 1), rng.gauss(0, 1), rng.gauss(0, 1))) * 0.75
        p = p + (heading + turn).normalized() * step
        pts.append(tuple(p))
        walked += step
        index += 1
        if branch and index % 5 == 2 and rng.random() < 0.8:
            side = (heading + Vector((rng.gauss(0, 1), rng.gauss(0, 1), rng.gauss(0, 1))) * 0.9).normalized()
            spark(rng, p, side, (length - walked) * rng.uniform(0.3, 0.6), step * 0.7, mat, f"{name}-{index}", False)
    tube(name, pts, 0.0042 if branch else 0.0021, mat, shadow=False)


def civka():
    wood = material("wood", "#5a341e", "#3f2413", 18, 0.42, dist=0.05, bevel=0.002)
    shellac = material("shellac", "#2a1b12", "#1e130c", 40, 0.28, dist=0.03)
    copper = material("copper", "#c9834a", "#ad6431", 240, 0.28, 1.0, dist=0.02, ao=0.4)
    alu = material("alu", "#d9dbde", "#c9cbce", 500, 0.16, 1.0, dist=0.03, ao=0.2)
    brass = material("brass", "#c9a64f", "#b08d3e", 300, 0.28, 1.0, dist=0.02)
    ebonite = material("ebonite", "#17171b", "#101014", 200, 0.22, dist=0.02)
    glass = material("glassy", "#2d3d44", "#223038", 120, 0.08, dist=0.03, ao=0.3)
    foil = material("foil", "#b9bcc0", "#a4a7ab", 300, 0.3, 1.0, dist=0.03, ao=0.3)
    arc = emission("arc", (0.72, 0.68, 1.0), 26.0)

    box("base", (-0.36, -0.36, 0.0), (0.36, 0.36, 0.085), wood, 0.006)
    lathe("collar", [(0, 0.085), (0.11, 0.085), (0.11, 0.105), (0.083, 0.115), (0, 0.115)], ebonite, smooth=30)
    lathe("secondary", [(0, 0.11), (0.074, 0.11), (0.074, 0.87), (0, 0.87)], shellac, smooth=30)
    pts = []
    turns, per = 210, 44
    for i in range(turns * per):
        a = TWO_PI * i / per
        pts.append((0.0758 * math.cos(a), 0.0758 * math.sin(a), 0.135 + (0.84 - 0.135) * i / (turns * per)))
    tube("wire", pts, 0.00135, copper)
    lathe("cap", [(0, 0.87), (0.08, 0.87), (0.08, 0.885), (0.035, 0.9), (0.03, 0.935), (0, 0.935)], brass, smooth=30)
    r_major, r_minor, z_top = 0.165, 0.052, 0.945
    lathe("torus", [(r_major + r_minor * math.cos(TWO_PI * i / 48), z_top + r_minor * math.sin(TWO_PI * i / 48)) for i in range(48)], alu, n=128, smooth=60)
    lathe("web", [(0, z_top - 0.006), (r_major, z_top - 0.006), (r_major, z_top + 0.006), (0, z_top + 0.006)], alu, smooth=30)

    # primary: a few thick turns low down
    pts = []
    turns_p, per_p = 6, 72
    for i in range(turns_p * per_p + 1):
        a = TWO_PI * i / per_p
        r = 0.135 + (0.25 - 0.135) * i / (turns_p * per_p)
        pts.append((r * math.cos(a), r * math.sin(a), 0.155))
    tube("primary", pts, 0.0072, copper)
    for i in range(4):
        a = math.radians(45 + 90 * i)
        beam(f"rib{i}", (0.12 * math.cos(a), 0.12 * math.sin(a), 0.143), (0.27 * math.cos(a), 0.27 * math.sin(a), 0.143), 0.022, ebonite)
        lathe(f"leg{i}", [(0, 0.085), (0.013, 0.085), (0.013, 0.135), (0, 0.135)], ebonite, n=20, at=(0.25 * math.cos(a), 0.25 * math.sin(a), 0), smooth=30)

    # two Leyden jars and a spark gap at the front
    for name, x in (("jar_l", -0.27), ("jar_r", -0.13)):
        lathe(name, [(0, 0.085), (0.044, 0.085), (0.044, 0.235), (0.018, 0.27), (0, 0.27)], glass, n=48, at=(x, -0.27, 0), smooth=35)
        lathe(name + "f", [(0, 0.09), (0.0452, 0.09), (0.0452, 0.19), (0, 0.19)], foil, n=48, at=(x, -0.27, 0), smooth=30)
        lathe(name + "r", [(0, 0.27), (0.004, 0.27), (0.004, 0.31), (0, 0.31)], brass, n=12, at=(x, -0.27, 0), smooth=30)
    for sx in (-1, 1):
        x = 0.14 + sx * 0.068
        lathe(f"gap_post{sx}", [(0, 0.085), (0.016, 0.085), (0.008, 0.11), (0.008, 0.2), (0, 0.2)], ebonite, n=20, at=(x, -0.27, 0), smooth=30)
        tube(f"gap_arm{sx}", [(x, -0.27, 0.2), (0.14 + sx * 0.03, -0.27, 0.2)], 0.004, brass)
        lathe(f"gap_ball{sx}", [(0.018 * math.sin(math.pi * i / 16), 0.018 * math.cos(math.pi * i / 16)) for i in range(17)], brass, n=24, at=(0.14 + sx * 0.024, -0.27, 0.2), smooth=60)
    tube("gap_arc", [(0.126, -0.27, 0.2), (0.135, -0.27, 0.206), (0.141, -0.27, 0.196), (0.154, -0.27, 0.2)], 0.0022, arc, shadow=False)
    tube("lead1", [(-0.27, -0.27, 0.31), (-0.27, -0.2, 0.33), (-0.13, -0.2, 0.33), (-0.13, -0.27, 0.31)], 0.0022, copper)
    tube("lead2", [(-0.13, -0.27, 0.31), (0.02, -0.27, 0.32), (0.072, -0.27, 0.2)], 0.0022, copper)
    tube("lead3", [(0.208, -0.27, 0.2), (0.27, -0.2, 0.17), (0.25, 0.0, 0.155)], 0.0022, copper)

    rng = random.Random(1891)
    for i, (a, z) in enumerate(() if SHOT == "civka-bez" else ((20, 0.25), (72, 0.05), (130, 0.3), (205, 0.12), (262, -0.1), (318, 0.2), (160, 0.55), (345, 0.5))):
        c, s = math.cos(math.radians(a)), math.sin(math.radians(a))
        spark(rng, ((r_major + r_minor) * c, (r_major + r_minor) * s, z_top + 0.01), (c, s, z), rng.uniform(0.5, 0.82), 0.03, arc, f"arc{i}")
    POINTS.update(sekundar=(0.0536, -0.0536, 0.55), primar=(0.0, -0.25, 0.155), vrchol=(0.0, -(r_major + r_minor), z_top), jiskriste=(0.14, -0.27, 0.206), kondenzator=(-0.2, -0.315, 0.16))
    return {"dir": (0.3, -1.0, 0.2), "lens": 85, "floor": 0.0, "soft": 1.0, "margin": [(sx * 0.72, sy * 0.36, z) for sx in (-1, 1) for sy in (-1, 1) for z in (0.0, 1.5)]}


# ---------------------------------------------------------------- tower: Wardenclyffe, section through the ground
TOWER = {"h": 57.0, "dome_d": 20.7, "shaft": 37.0, "pipes": 16, "pipes_depth": 91.0, "hall": 28.6}


def hall_only(brick, roof, window, stone, ground):
    # the laboratory: 94 ft square brick hall by Stanford White, low roof, a row of arched windows, a chimney in the middle
    hall = TOWER["hall"]
    x0, y0 = 15.0, 2.0
    h_wall = 7.2
    box("hall", (x0, y0, 0.25), (x0 + hall, y0 + hall, h_wall), brick, 0)
    box("base_course", (x0 - 0.2, y0 - 0.2, 0.25), (x0 + hall + 0.2, y0 + hall + 0.2, 1.0), stone, 0)
    box("cornice", (x0 - 0.5, y0 - 0.5, h_wall - 0.5), (x0 + hall + 0.5, y0 + hall + 0.5, h_wall), stone, 0)
    roof_h = 2.8
    v = [(x0 - 0.5, y0 - 0.5, h_wall), (x0 + hall + 0.5, y0 - 0.5, h_wall), (x0 + hall + 0.5, y0 + hall + 0.5, h_wall), (x0 - 0.5, y0 + hall + 0.5, h_wall),
         (x0 + hall / 2 - 5, y0 + hall / 2, h_wall + roof_h), (x0 + hall / 2 + 5, y0 + hall / 2, h_wall + roof_h)]
    mesh("roof", v, [(0, 1, 5, 4), (1, 2, 5), (2, 3, 4, 5), (3, 0, 4)], roof, 0)
    box("chimney", (x0 + hall / 2 - 1.2, y0 + hall / 2 - 1.2, h_wall), (x0 + hall / 2 + 1.2, y0 + hall / 2 + 1.2, h_wall + roof_h + 6.5), brick, 0)
    box("chimney_cap", (x0 + hall / 2 - 1.6, y0 + hall / 2 - 1.6, h_wall + roof_h + 6.5), (x0 + hall / 2 + 1.6, y0 + hall / 2 + 1.6, h_wall + roof_h + 7.0), stone, 0)
    count = 11
    for i in range(count):
        wx = x0 + 1.3 + (hall - 4.0) * i / (count - 1)
        if i == count // 2:
            continue
        ww = 1.4
        arc = [(wx + ww / 2 + ww / 2 * math.cos(math.pi * q / 10), 3.9 + ww / 2 * math.sin(math.pi * q / 10)) for q in range(11)]
        pts = [(wx, 1.6)] + [(wx + ww, 1.6)] + arc + [(wx, 3.9)]
        mesh(f"win{i}", [(x, y0 - 0.04, z) for x, z in pts] + [(x, y0 + 0.02, z) for x, z in pts],
             [tuple(range(len(pts))), tuple(range(len(pts), 2 * len(pts)))] + [(j, (j + 1) % len(pts), len(pts) + (j + 1) % len(pts), len(pts) + j) for j in range(len(pts))], window, 0)
        box(f"sill{i}", (wx - 0.15, y0 - 0.14, 1.4), (wx + ww + 0.15, y0 + 0.02, 1.6), stone, 0)
    dx = x0 + hall / 2 - 1.4
    box("door_frame", (dx - 0.35, y0 - 0.12, 0.25), (dx + 2.8 + 0.35, y0 + 0.02, 5.0), stone, 0)
    box("door", (dx, y0 - 0.2, 0.25), (dx + 2.8, y0 + 0.02, 4.6), window, 0)
    return {"dir": (-0.25, -1.0, 0.1), "lens": 200, "floor": 0.25, "soft": 1.0}


def vez(ground=True, tower=True, lab=True):
    timber = material("timber", "#a48a68", "#7f6849", 2.2, 0.75, dist=0.8, ao=0.5, bevel=0.03)
    iron = material("iron", "#3a3d40", "#2b2e31", 3.0, 0.5, 0.75, dist=0.7, ao=0.4)
    brick = material("brick", "#8c4a35", "#6e3828", 5.0, 0.8, dist=1.2, ao=0.65, bump=0.2)
    roof = material("roof", "#3f4347", "#33373a", 3.0, 0.7, dist=1.0, ao=0.5)
    window = material("window", "#1a2228", "#141b20", 3.0, 0.2, dist=0.5, ao=0.2)
    stone = material("stone", "#b9b2a4", "#a29b8d", 3.0, 0.8, dist=0.6, ao=0.5)
    topsoil = material("topsoil", "#4a3a26", "#352818", 1.2, 0.95, dist=1.0, ao=0.3)
    sand = material("sand", "#b49a6c", "#9c8256", 0.9, 0.95, dist=1.0, ao=0.3)
    gravel = material("gravel", "#8f8069", "#6f6250", 2.4, 0.95, dist=1.0, ao=0.3)
    grass = material("grass", "#56683a", "#44552c", 2.0, 0.95, dist=0.8, ao=0.3)
    lining = material("lining", "#6f665a", "#59514a", 3.0, 0.8, dist=0.8, ao=0.5)

    legs, levels = 8, 8
    if not tower:
        return hall_only(brick, roof, window, stone, ground)
    h_top = 46.0
    radius = lambda z: 11.0 - (11.0 - 3.4) * z / h_top
    corner = lambda i, z: (radius(z) * math.cos(TWO_PI * i / legs + math.pi / 8), radius(z) * math.sin(TWO_PI * i / legs + math.pi / 8), z)
    zs = [h_top * j / levels for j in range(levels + 1)]
    for i in range(legs):
        beam(f"leg{i}", corner(i, 0), corner(i, h_top), 0.62, timber)
        for j in range(levels):
            beam(f"x{i}{j}a", corner(i, zs[j]), corner(i + 1, zs[j + 1]), 0.2, timber)
            beam(f"x{i}{j}b", corner(i + 1, zs[j]), corner(i, zs[j + 1]), 0.2, timber)
        for j in range(1, levels + 1):
            beam(f"ring{i}{j}", corner(i, zs[j]), corner(i + 1, zs[j]), 0.34, timber)
    beam("mast", (0, 0, 0), (0, 0, h_top + 1), 1.0, iron)
    lathe("deck", [(0, h_top), (4.6, h_top), (4.6, h_top + 0.35), (0, h_top + 0.35)], timber, n=32, smooth=0)

    # the cap: an open steel frame on a platform, never fully clad
    r = TOWER["dome_d"] / 2
    z_c = TOWER["h"] - r * 0.86
    ribs = 18
    arc = [(r * math.cos(math.radians(a)), z_c + r * 0.86 * math.sin(math.radians(a))) for a in range(-25, 91, 7)]
    for i in range(ribs):
        c, s = math.cos(TWO_PI * i / ribs), math.sin(TWO_PI * i / ribs)
        tube(f"rib{i}", [(x * c, x * s, z) for x, z in arc], 0.13, iron)
        tube(f"strut{i}", [(arc[0][0] * c, arc[0][0] * s, arc[0][1]), (4.0 * c, 4.0 * s, h_top + 0.2)], 0.11, iron)
    for x, z in arc[1::3]:
        tube(f"hoop{z:.1f}", [(x * math.cos(TWO_PI * k / 72), x * math.sin(TWO_PI * k / 72), z) for k in range(72)], 0.1, iron, cyclic=True)
    if ground:
        # section block: the ground in front of the plane y = 0 is gone, so the shaft shows
        w, d_back = 28.0, 26.0
        depth = TOWER["pipes_depth"] * 0.0 + TOWER["shaft"] + 8.0
        layers = ((grass, -0.0, 0.25), (topsoil, -2.6, 0.0), (sand, -18.0, -2.6), (gravel, -depth, -18.0))
        for k, (mat, z0, z1) in enumerate(layers):
            box(f"earth{k}", (-w, 0.0, z0), (w + 20.0, d_back, z1), mat, 0)
        # the shaft in front of the block: a lined pit with an iron pipe down the middle
        sw = 1.85
        box("shaft_back", (-sw, -0.3, -TOWER["shaft"]), (sw, -0.02, 0.26), lining)
        for sx in (-1, 1):
            box(f"shaft_wall{sx}", (sx * sw - 0.35, -1.2, -TOWER["shaft"]), (sx * sw + 0.35, -0.02, 0.26), stone)
        box("shaft_floor", (-sw - 0.35, -1.2, -TOWER["shaft"] - 0.6), (sw + 0.35, -0.02, -TOWER["shaft"]), stone)
        box("pipe", (-0.45, -0.9, -TOWER["shaft"]), (0.45, -0.32, 0.3), iron)
        for rung in range(1, 12):
            box(f"rung{rung}", (-sw + 0.3, -0.72, -TOWER["shaft"] * rung / 12), (sw - 0.3, -0.32, -TOWER["shaft"] * rung / 12 + 0.25), timber)

    if lab:
        hall_only(brick, roof, window, stone, ground)
    x0, y0 = 15.0, 2.0
    POINTS.update(kopule=(r * 0.5, 0, z_c + r * 0.72), vez=corner(4, 22), dilna=(x0 + 6, y0 - 0.1, 5.5), sachta=(-2.2, -0.3, -TOWER["shaft"] * 0.6), trubka=(0.45, -0.6, -TOWER["shaft"] * 0.35),
                  vrchol=(0, 0, TOWER["h"]), pata=(0, 0, 0), dno=(0, 0, -TOWER["shaft"]), zem=(-34, 0, -0.1))
    if not ground:
        return {"dir": (-0.25, -1.0, 0.1), "lens": 200, "floor": 0.0, "soft": 1.0}
    return {"dir": (-0.07, -1.0, 0.03), "lens": 400, "floor": None, "soft": 1.0}


# ---------------------------------------------------------------- the Adams plant in section, not to scale: the water falls down a pit onto the turbine, a long shaft turns the generator in the hall
def falling_water(name):
    """White streaks stretched along the fall."""
    m, t, bsdf = pm.new_mat(name, 0.35)
    mapping = t.nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (2.2, 2.2, 0.05)
    t.links.new(pm.coords(t), mapping.inputs["Vector"])
    t.links.new(pm.ramp_of(t, pm.noise_of(t, mapping.outputs[0], 1.0), "#7fa3b4", "#f4f7f8", 0.34, 0.62), bsdf.inputs["Base Color"])
    return m


def elektrarna():
    grass = material("grass", "#56683a", "#44552c", 2.0, 0.95, dist=0.8, ao=0.3)
    topsoil = material("topsoil", "#4a3a26", "#352818", 1.2, 0.95, dist=1.0, ao=0.3)
    rock = material("rock", "#b3a68c", "#9a8d74", 0.9, 0.95, dist=1.0, ao=0.3)
    shale = material("shale", "#857b69", "#6d6455", 2.4, 0.95, dist=1.0, ao=0.3)
    stone = material("stone", "#c8c1b2", "#aea798", 3.0, 0.8, dist=0.6, ao=0.5)
    lining = material("lining", "#5f584e", "#4c463e", 3.0, 0.8, dist=0.8, ao=0.5)
    roof = material("roof", "#3f4347", "#33373a", 3.0, 0.7, dist=1.0, ao=0.5)
    window = material("window", "#d9dcd6", "#c6c9c3", 3.0, 0.3, dist=0.5, ao=0.2)
    water = material("water", "#2f7fa8", "#256a90", 1.5, 0.2, dist=0.5, ao=0.2)
    steel = material("steel", "#8f959b", "#767c82", 8.0, 0.32, 0.9, dist=0.5, ao=0.4)
    copper = material("copper", "#b4683a", "#96532c", 30.0, 0.35, 0.85, dist=0.5, ao=0.5)
    dark = material("dark", "#3a3d40", "#2b2e31", 5.0, 0.45, 0.7, dist=0.6, ao=0.4)

    left, cliff, right, back, bottom = -35.0, 22.0, 35.0, 18.0, -66.0
    shaft_x, pit = 1.5, 7.5
    wheel_z, tunnel_z = -48.0, -56.0
    # the ground, cut at y = 0; the canal takes its top on the left
    box("grass", (-12, 0, 0), (cliff, back, 0.3), grass, 0)
    box("topsoil", (-12, 0, -2.6), (cliff, back, 0), topsoil, 0)
    box("rock", (-12, 0, -22), (cliff, back, -2.6), rock, 0)
    box("rock_canal", (left, 0, -22), (-12, back, -5.5), rock, 0)
    box("shale", (left, 0, bottom), (cliff, back, -22), shale, 0)
    box("bed", (cliff, 0, bottom), (right, back, -63), shale, 0)
    box("canal", (left, -1.5, -5.5), (-12, back, -1.2), water, 0)
    box("canal_wall", (-13, -1.7, -5.8), (-12, back, 0.3), stone, 0)
    # the lower river and the falls behind the cut
    box("river", (cliff, -3, -63), (right, back, tunnel_z - 2), water, 0)
    box("falls_top", (cliff, 12, -1.2), (right, back, 0), water, 0)
    box("falls", (cliff, 11.7, tunnel_z - 2), (right, 12, 0), falling_water("falling"), 0)
    # the pit in front of the cut
    box("pit_back", (-pit, -0.3, tunnel_z), (pit, -0.02, 0.3), lining, 0)
    for sx in (-1, 1):
        box(f"pit_wall{sx}", (shaft_x - 1.5 + sx * pit - 0.6, -1.2, tunnel_z), (shaft_x - 1.5 + sx * pit + 0.6, -0.02, 0.3), stone, 0)
    # supply pipe from the canal down to the turbine
    box("pipe_top", (-13, -1.9, -4.4), (-2.5, -1.3, -2.2), water, 0)
    box("pipe_fall", (-4.7, -1.9, wheel_z), (-2.5, -1.3, -2.2), water, 0)
    for zb in (-14, -26, -38):
        box(f"pipe_band{zb}", (-5.0, -2.0, zb), (-2.2, -1.25, zb + 0.5), dark, 0)
    box("gate", (-13.4, -2.0, -4.8), (-12.6, -1.25, -1.8), dark, 0)
    # shaft, its bearings, the turbine at the bottom, the water leaving under it
    lathe("shaft", [(0, wheel_z), (0.42, wheel_z), (0.42, 5.5), (0, 5.5)], steel, at=(shaft_x, -0.9, 0), n=32, smooth=60)
    for zb in (-11, -23, -35):
        box(f"bearing{zb}", (shaft_x - 6, -1.2, zb), (shaft_x + 6, -0.7, zb + 0.7), dark, 0)
        lathe(f"collar{zb}", [(0, zb - 0.5), (0.85, zb - 0.5), (0.85, zb + 1.2), (0, zb + 1.2)], dark, at=(shaft_x, -0.9, 0), n=32, smooth=60)
    wheel = [(0, wheel_z - 2.2), (3.6, wheel_z - 2.2), (4.2, wheel_z - 1.4), (4.2, wheel_z + 0.8), (3.0, wheel_z + 1.7), (0, wheel_z + 1.7)]
    lathe("turbine", wheel, copper, at=(shaft_x, -0.9, 0), n=64, smooth=45)
    box("outflow", (shaft_x - 2.6, -1.1, tunnel_z), (shaft_x + 2.6, -0.5, wheel_z - 2.2), water, 0)
    # tail tunnel to the river below the falls
    box("tunnel_roof", (-pit + 1.0, -1.3, tunnel_z + 0.0), (cliff, -0.02, tunnel_z + 0.8), stone, 0)
    box("tunnel_water", (-pit + 1.0, -1.3, tunnel_z - 3.6), (cliff + 0.4, -0.02, tunnel_z), water, 0)
    box("tunnel_floor", (-pit + 1.0, -1.3, tunnel_z - 4.4), (cliff, -0.02, tunnel_z - 3.6), stone, 0)
    # the hall: stone walls and gable cut open, the windows of the back wall, the generator on the floor at the head of the shaft
    x0, x1, wall = -11.0, 14.0, 13.0
    box("floor", (x0 - 1, -7.5, 0), (x1 + 1, 11, 0.45), stone, 0)
    box("back", (x0, 10, 0.45), (x1, 11, wall), stone, 0)
    for sx, xw in ((-1, x0), (1, x1)):
        box(f"wall{sx}", (xw - 0.5, -7.5, 0.45), (xw + 0.5, 11, wall), stone, 0)
    ridge = (x0 + x1) / 2
    for y0, y1, name in ((10, 11, "gable"), ):
        mesh(name, [(x0 - 0.5, y0, wall), (x1 + 0.5, y0, wall), (ridge, y0, wall + 6.0), (x0 - 0.5, y1, wall), (x1 + 0.5, y1, wall), (ridge, y1, wall + 6.0)],
             [(0, 1, 2), (3, 4, 5), (0, 1, 4, 3), (1, 2, 5, 4), (2, 0, 3, 5)], stone, 0)
    for sx, xa, xb in ((-1, x0 - 1.3, ridge), (1, x1 + 1.3, ridge)):
        mesh(f"roof{sx}", [(xa, -8.0, wall - 0.2), (xa, 11.4, wall - 0.2), (xb, 11.4, wall + 6.4), (xb, -8.0, wall + 6.4),
                           (xa, -8.0, wall + 0.5), (xa, 11.4, wall + 0.5), (xb, 11.4, wall + 7.1), (xb, -8.0, wall + 7.1)],
             [(0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)], roof, 0)
    for i in range(5):
        wx = x0 + 2.0 + i * 4.6
        arc = [(wx + 1.1 + 1.1 * math.cos(math.pi * q / 10), 9.0 + 1.1 * math.sin(math.pi * q / 10)) for q in range(11)]
        pts = [(wx, 3.0), (wx + 2.2, 3.0)] + arc
        mesh(f"win{i}", [(x, 9.96, z) for x, z in pts] + [(x, 9.98, z) for x, z in pts],
             [tuple(range(len(pts))), tuple(range(len(pts), 2 * len(pts)))] + [(j, (j + 1) % len(pts), len(pts) + (j + 1) % len(pts), len(pts) + j) for j in range(len(pts))], window, 0)
    # Westinghouse's generator has its field turning outside, like an umbrella on the shaft
    gen = [(0, 0.45), (4.4, 0.45), (4.4, 2.8), (0, 2.8)]
    lathe("armature", gen, dark, at=(shaft_x, -0.9, 0), n=96, smooth=40)
    field = [(0, 3.4), (5.5, 3.4), (5.7, 2.4), (5.7, 1.6), (5.9, 1.6), (5.9, 4.0), (5.2, 4.9), (2.0, 5.6), (0, 5.6)]
    lathe("field", field, copper, at=(shaft_x, -0.9, 0), n=96, smooth=40)
    POINTS.update(kanal=(left + 7, -1.5, -3.2), privadec=(-3.6, -1.9, -18), hridel=(shaft_x + 0.42, -0.9, -29), turbina=(shaft_x + 4.2, -0.9, wheel_z), generator=(shaft_x + 5.8, -0.9, 3.4),
                  tunel=(14, -1.3, tunnel_z - 1.8), reka=(cliff + 6, -3, tunnel_z - 3.5), vodopad=(cliff + 7, 11.7, -22),
                  kanal_a=(-31, -1.5, -3.3), kanal_b=(-16, -1.5, -3.3), trubka_a=(-3.6, -1.9, -20), trubka_b=(-3.6, -1.9, -36),
                  tunel_a=(4, -1.3, tunnel_z - 1.8), tunel_b=(19, -1.3, tunnel_z - 1.8))
    return {"dir": (-0.05, -1.0, 0.02), "lens": 400, "floor": None, "soft": 1.0}


# ---------------------------------------------------------------- turbine: smooth discs, no blades, patent US 1,061,206
def turbina():
    cast = material("cast", "#3a4044", "#2e3337", 80, 0.42, 0.3, bump=0.25, bevel=0.002)
    steel = material("steel", "#cdd0d3", "#b9bcbf", 500, 0.17, 1.0, dist=0.015, ao=0.45)
    shaftm = material("shaft", "#c4c7cb", "#aeb2b6", 400, 0.2, 1.0, dist=0.02, ao=0.3)
    brass = material("brass", "#c9a64f", "#b08d3e", 300, 0.3, 1.0, dist=0.02)

    r_d, y_half, count = 0.23, 0.1, 25
    # one disc: rim, spokes and hub; the steam leaves through the openings around the hub
    n = 144
    v, f = [], []

    def add_ring(r0, r1, a0, a1, segs, t):
        base = len(v)
        for i in range(segs + 1):
            a = a0 + (a1 - a0) * i / segs
            for r, h in ((r0, -t), (r1, -t), (r1, t), (r0, t)):
                v.append((r * math.cos(a), h, r * math.sin(a)))
        for i in range(segs):
            for j in range(4):
                f.append((base + i * 4 + j, base + i * 4 + (j + 1) % 4, base + (i + 1) * 4 + (j + 1) % 4, base + (i + 1) * 4 + j))
        f.append(tuple(base + j for j in range(4)))
        f.append(tuple(base + segs * 4 + j for j in range(4)))

    t = 0.0013
    add_ring(0.075, r_d, 0, TWO_PI, n, t)
    add_ring(0.024, 0.042, 0, TWO_PI, 48, t)
    for i in range(6):
        a = TWO_PI * i / 6
        add_ring(0.04, 0.078, a - 0.11, a + 0.11, 3, t)
    me = bpy.data.meshes.new("disc")
    me.from_pydata(v, [], f)
    me.update()
    me.materials.append(steel)
    for k in range(count):
        o = link(bpy.data.objects.new(f"disc{k}", me))
        o.location = (0, -y_half + 2 * y_half * k / (count - 1), 0)
    for k in range(6):
        a = TWO_PI * k / 6 + TWO_PI / 12
        tube(f"tie{k}", [(0.1 * math.cos(a), -y_half - 0.004, 0.1 * math.sin(a)), (0.1 * math.cos(a), y_half + 0.004, 0.1 * math.sin(a))], 0.0028, shaftm)
    lathe("hub", [(0, -y_half - 0.012), (0.03, -y_half - 0.012), (0.03, y_half + 0.012), (0, y_half + 0.012)], shaftm, "y", 64, smooth=30)
    lathe("shaft", [(0, -0.36), (0.021, -0.36), (0.021, 0.36), (0, 0.36)], shaftm, "y", 64, smooth=30)

    # casing: the upper half is cut away, the stack of discs lies open
    a0, a1 = math.pi, TWO_PI
    r_c0, r_c1 = r_d + 0.008, r_d + 0.034
    y_c = y_half + 0.022
    lathe("shell", [(r_c0, -y_c), (r_c1, -y_c), (r_c1, y_c), (r_c0, y_c)], cast, "y", 120, a0, a1, smooth=30, bevel=0.0015)
    lathe("rear", [(0.05, y_c), (r_c1, y_c), (r_c1, y_c + 0.018), (0.05, y_c + 0.018)], cast, "y", 120, a0, a1, smooth=30, bevel=0.0015)
    lathe("front", [(0.05, -y_c - 0.018), (r_c1, -y_c - 0.018), (r_c1, -y_c), (0.05, -y_c)], cast, "y", 120, a0, a1, smooth=30, bevel=0.0015)
    for sy, y0, y1 in ((-1, -0.25, -y_c - 0.018), (1, y_c + 0.018, 0.25)):
        lathe(f"bearing{sy}", [(0.021, y0), (0.044, y0), (0.044, y1), (0.021, y1)], cast, "y", 64, smooth=30, bevel=0.0015)
    # nozzle: enters on the tangent, low on the right
    a = math.radians(205)
    p = Vector((r_c0 * math.cos(a), 0, r_c0 * math.sin(a)))
    tangent = Vector((math.sin(a), 0, -math.cos(a)))
    out = p - tangent * 0.2
    tube("nozzle", [tuple(p), tuple(p - tangent * 0.08), tuple(out)], 0.03, cast)
    tube("flange", [tuple(out), tuple(out - tangent * 0.016)], 0.046, brass)
    # stand
    base_z = -0.37
    box("foot", (-0.34, -0.3, base_z), (0.34, 0.3, base_z + 0.024), cast, 0.004)
    box("stand", (-0.2, -y_c - 0.018, base_z + 0.02), (0.2, y_c + 0.018, -r_c1 + 0.03), cast, 0.004)
    for sy in (-1, 1):
        box(f"ped{sy}", (-0.05, sy * 0.21 - 0.03, base_z + 0.02), (0.05, sy * 0.21 + 0.03, -0.04), cast, 0.004)
    POINTS.update(disky=(0.11, -y_half, 0.17), hridel=(0.0, -0.33, 0.021), tryska=tuple(p - tangent * 0.12), odtok=(0.06, -y_half, 0.06), kryt=(-0.17, -y_c - 0.018, -0.16), hrana=(0.12, y_half * 0.3, 0.197),
                  stred=(0, -y_half, 0), okraj=(r_d, -y_half, 0), horni=(0, -y_half, r_d))
    return {"dir": (-0.72, -0.95, 0.62), "lens": 85, "floor": base_z, "soft": 1.0}



# ---------------------------------------------------------------- transformer: core, two coils, wooden base
def transformator():
    sheet = material("sheet", "#7f8488", "#75797d", 700, 0.36, 0.9, dist=0.03, ao=0.45)
    copper = material("copper", "#c47b43", "#a95f2e", 260, 0.3, 1.0, dist=0.012, ao=0.55)
    wood = material("wood", "#7a5230", "#5e3d22", 16, 0.45, dist=0.05, bevel=0.002)
    brass = material("brass", "#c9a64f", "#b08d3e", 300, 0.28, 1.0, dist=0.02)
    w, h, leg, depth = 0.2, 0.34, 0.05, 0.05
    box("base", (-0.34, -0.14, 0.0), (0.34, 0.14, 0.05), wood, 0.004)
    z0 = 0.05
    for name, lo, hi in (("top", (-w, -depth, z0 + h - leg), (w, depth, z0 + h)), ("bottom", (-w, -depth, z0), (w, depth, z0 + leg)),
                         ("left", (-w, -depth, z0 + leg), (-w + leg, depth, z0 + h - leg)), ("right", (w - leg, -depth, z0 + leg), (w, depth, z0 + h - leg))):
        box(name, lo, hi, sheet, 0.0012)
    wire = 0.0062
    for name, cx in (("c1", -w + leg / 2), ("c2", w - leg / 2)):
        pts = []
        per = 28
        for layer in range(2):
            half_x, half_y = leg / 2 + wire * (1.2 + 2.1 * layer), depth + wire * (1.2 + 2.1 * layer)
            turns = 13
            for t in range(turns * per):
                a = TWO_PI * t / per
                z = z0 + leg + 0.012 + (h - 2 * leg - 0.024) * (t / (turns * per) if layer == 0 else 1 - t / (turns * per))
                pts.append((cx + half_x * 1.12 * math.cos(a), half_y * 1.04 * math.sin(a), z))
        tube(name, pts, wire, copper)
    for sx in (-1, 1):
        lathe(f"post{sx}", [(0, 0.05), (0.012, 0.05), (0.012, 0.075), (0.007, 0.075), (0.007, 0.09), (0.012, 0.09), (0.012, 0.098), (0, 0.098)], brass, n=20, at=(sx * 0.29, -0.09, 0), smooth=30)
    POINTS.update(primar=(-w + leg / 2 - 0.05, -depth - 0.012, z0 + h / 2), sekundar=(w - leg / 2 + 0.05, -depth - 0.012, z0 + h / 2), jadro=(0, -depth, z0 + h - leg / 2))
    return {"dir": (0.0, -1.0, 0.2), "lens": 120, "floor": 0.0, "soft": 1.0}


# ---------------------------------------------------------------- wireless sets: a receiver with dials, its aerial and a key box
def prijimac():
    wood = material("wood", "#7a4a28", "#5c3519", 16, 0.42, dist=0.05, bevel=0.002)
    face = material("face", "#2b211a", "#21190f", 80, 0.35, dist=0.03)
    brass = material("brass", "#c9a64f", "#b08d3e", 300, 0.26, 1.0, dist=0.02)
    steel = material("steel", "#c4c7cb", "#aeb2b6", 400, 0.22, 1.0, dist=0.02, ao=0.3)
    ivory = material("ivory", "#d9cfb8", "#cfc4aa", 200, 0.4, dist=0.02)
    box("case", (-0.17, -0.1, 0.0), (0.17, 0.1, 0.25), wood, 0.004)
    box("panel", (-0.15, -0.104, 0.03), (0.15, -0.098, 0.22), face, 0.001)
    for i, (x, z, r) in enumerate(((-0.075, 0.15, 0.04), (0.075, 0.15, 0.04), (-0.095, 0.06, 0.016), (-0.03, 0.06, 0.016), (0.03, 0.06, 0.016), (0.095, 0.06, 0.016))):
        depth = 0.008 if r > 0.03 else 0.02
        lathe(f"ring{i}", [(0, 0), (r, 0), (r, -depth * 0.7), (r * 0.82, -depth), (0, -depth)], brass, "y", 40, at=(x, -0.104, z), smooth=30)
        if r > 0.03:
            lathe(f"dial{i}", [(0, -depth - 0.001), (r * 0.78, -depth - 0.001), (r * 0.78, -depth + 0.001), (0, -depth + 0.001)], ivory, "y", 40, at=(x, -0.104, z), smooth=30)
            tube(f"needle{i}", [(x, -0.104 - depth - 0.002, z), (x + r * 0.5, -0.104 - depth - 0.002, z + r * 0.45)], 0.0012, face)
    # aerial on its own foot
    ax = 0.33
    lathe("foot", [(0, 0), (0.07, 0), (0.07, 0.012), (0.02, 0.03), (0.012, 0.03), (0, 0.03)], brass, n=40, at=(ax, 0.0, 0), smooth=30)
    tube("mast", [(ax, 0, 0.03), (ax, 0, 0.36)], 0.006, steel)
    lathe("ball", [(0.014 * math.sin(math.pi * q / 12), 0.014 * math.cos(math.pi * q / 12)) for q in range(13)], brass, n=20, at=(ax, 0, 0.372), smooth=60)
    tube("lead", [(0.17, -0.02, 0.05), (0.21, -0.1, 0.012), (0.27, -0.06, 0.01), (ax - 0.06, 0, 0.01)], 0.003, material("cord", "#2a2420", "#201b18", 200, 0.6, dist=0.02))
    # key box
    kx = 0.68
    box("key_case", (kx - 0.14, -0.1, 0.0), (kx + 0.14, 0.1, 0.1), wood, 0.004)
    box("key_top", (kx - 0.12, -0.08, 0.1), (kx + 0.12, 0.08, 0.108), face, 0.001)
    tube("key_lever", [(kx - 0.09, 0, 0.14), (kx + 0.1, 0, 0.15)], 0.005, brass)
    lathe("key_knob", [(0, 0), (0.014, 0), (0.016, 0.01), (0.012, 0.02), (0, 0.022)], face, n=24, at=(kx + 0.1, 0, 0.15), smooth=40)
    lathe("key_post", [(0, 0.108), (0.012, 0.108), (0.008, 0.15), (0, 0.15)], brass, n=20, at=(kx - 0.02, 0, 0), smooth=30)
    for i, x in enumerate((-0.09, 0.09)):
        pts = [(kx + x + 0.022 * math.cos(TWO_PI * t / 20), -0.05 + 0.022 * math.sin(TWO_PI * t / 20), 0.11 + 0.05 * t / 160) for t in range(160)]
        tube(f"key_coil{i}", pts, 0.0028, material(f"c{i}", "#c47b43", "#a95f2e", 260, 0.3, 1.0, dist=0.012))
        lathe(f"key_top{i}", [(0, 0.16), (0.024, 0.16), (0.024, 0.166), (0, 0.166)], brass, n=24, at=(kx + x, -0.05, 0), smooth=30)
    POINTS.update(krabice=(0, -0.1, 0.22), kl=(kx + 0.1, 0, 0.17))
    return {"dir": (-0.22, -1.0, 0.34), "lens": 110, "floor": 0.0, "soft": 1.0}


# ---------------------------------------------------------------- the telautomaton, hull plan after patent US 613,809
def lod():
    hull = material("hull", "#55626c", "#46525b", 40, 0.42, 0.25, dist=0.05, ao=0.5, bevel=0.001)
    boot = material("boot", "#7c3b2d", "#673022", 40, 0.5, dist=0.05, ao=0.5)
    deck = material("deck", "#b08a5a", "#97764b", 30, 0.55, dist=0.05, bevel=0.001)
    cabin = material("cabin", "#8c6a44", "#775836", 30, 0.5, dist=0.04, bevel=0.002)
    brass = material("brass", "#c9a64f", "#b08d3e", 300, 0.26, 1.0, dist=0.02)
    glass = material("glass", "#1e2a30", "#182228", 100, 0.15, dist=0.02)
    length, beam_h = 1.3, 0.13
    width = lambda t: 0.17 * min(1.0, (1 - t) ** 0.62 * 1.12) * (0.82 + 0.18 * min(1, t * 6))      # t = 0 stern, 1 bow
    keel = lambda t: 0.02 + 0.04 * max(0, t - 0.7) / 0.3
    stations = 48
    v, f = [], []
    for i in range(stations + 1):
        t = i / stations
        x = -length / 2 + length * t
        hw = max(width(t), 0.001)
        for u, z in ((-1.0, beam_h), (-0.92, beam_h * 0.55), (-0.62, keel(t) + 0.02), (0.0, keel(t)), (0.62, keel(t) + 0.02), (0.92, beam_h * 0.55), (1.0, beam_h)):
            v.append((x, hw * u, z + 0.12 * max(0, t - 0.55) ** 2))
    m = 7
    for i in range(stations):
        for j in range(m - 1):
            f.append((i * m + j, i * m + j + 1, (i + 1) * m + j + 1, (i + 1) * m + j))
    mesh("hull", v, f, hull, 50)
    stripe = [(p[0], p[1] * 1.002, p[2]) for k, p in enumerate(v) if k % m in (1, 2, 3, 4, 5)]
    fs = [(i * 5 + j, i * 5 + j + 1, (i + 1) * 5 + j + 1, (i + 1) * 5 + j) for i in range(stations) for j in range(4)]
    mesh("boot", [(p[0], p[1], p[2] - 0.0005) for p in stripe], fs, boot, 50)
    dv, df = [], []
    for i in range(stations + 1):
        t = i / stations
        x = -length / 2 + length * t
        hw = max(width(t), 0.001) * 0.98
        z = beam_h + 0.002 + 0.12 * max(0, t - 0.55) ** 2
        dv += [(x, -hw, z), (x, hw, z)]
    df = [(2 * i, 2 * i + 1, 2 * i + 3, 2 * i + 2) for i in range(stations)]
    mesh("deck", dv, df, deck, 50)
    box("hatch", (-0.2, -0.07, beam_h), (0.12, 0.07, beam_h + 0.035), cabin, 0.003)
    box("hatch_top", (-0.21, -0.078, beam_h + 0.035), (0.13, 0.078, beam_h + 0.041), deck, 0.002)
    tube("mast", [(-0.04, 0, beam_h + 0.04), (-0.04, 0, beam_h + 0.3)], 0.0045, brass)
    for name, x, top in (("rod_a", -0.42, 0.2), ("rod_b", 0.32, 0.17)):
        tube(name, [(x, 0, beam_h), (x, 0, beam_h + top)], 0.003, brass)
        lathe(name + "_lamp", [(0.012 * math.sin(math.pi * q / 10), 0.012 * math.cos(math.pi * q / 10)) for q in range(11)], glass, n=16, at=(x, 0, beam_h + top + 0.01), smooth=60)
    w = bpy.data.materials.new("water")
    w.use_nodes = True
    t = w.node_tree
    b = t.nodes["Principled BSDF"]
    b.inputs["Roughness"].default_value = 0.12
    b.inputs["Base Color"].default_value = (0.13, 0.16, 0.15, 1)
    co = t.nodes.new("ShaderNodeTexCoord")
    grad = t.nodes.new("ShaderNodeTexGradient")
    grad.gradient_type = "SPHERICAL"
    sc = t.nodes.new("ShaderNodeMapping")
    sc.inputs["Scale"].default_value = (1.2, 3.4, 1.0)
    t.links.new(co.outputs["Object"], sc.inputs[0])
    t.links.new(sc.outputs[0], grad.inputs[0])
    ramp = t.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position, ramp.color_ramp.elements[1].position = 0.0, 0.6
    t.links.new(grad.outputs[0], ramp.inputs[0])
    t.links.new(ramp.outputs[0], b.inputs["Alpha"])
    bump = t.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.5
    bump.inputs["Distance"].default_value = 0.01
    wave = t.nodes.new("ShaderNodeTexNoise")
    wave.inputs["Scale"].default_value = 26.0
    t.links.new(co.outputs["Object"], wave.inputs["Vector"])
    t.links.new(wave.outputs[0], bump.inputs["Height"])
    t.links.new(bump.outputs[0], b.inputs["Normal"])
    lathe("water", [(0, 0.06), (1.6, 0.06), (1.6, 0.0605), (0, 0.0605)], w, n=64, smooth=30)
    POINTS.update(lod=(0.2, -0.13, 0.1))
    return {"dir": (0.45, -1.0, 0.3), "lens": 120, "floor": None, "soft": 1.0, "skip": ("water",)}


# ---------------------------------------------------------------- glowing tubes: the gas column is the light source
def gas_column(name, pts, r, colors, strength):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    t = m.node_tree
    t.nodes.clear()
    out = t.nodes.new("ShaderNodeOutputMaterial")
    em = t.nodes.new("ShaderNodeEmission")
    em.inputs["Strength"].default_value = strength
    co = t.nodes.new("ShaderNodeTexCoord")
    sep = t.nodes.new("ShaderNodeSeparateXYZ")
    t.links.new(co.outputs["Object"], sep.inputs[0])
    span = t.nodes.new("ShaderNodeMapRange")
    lo, hi = min(p[0] for p in pts), max(p[0] for p in pts)
    axis = "X"
    if hi - lo < 1e-4:
        lo, hi = min(p[2] for p in pts), max(p[2] for p in pts)
        axis = "Z"
    span.inputs["From Min"].default_value, span.inputs["From Max"].default_value = lo, hi
    t.links.new(sep.outputs[axis], span.inputs["Value"])
    ramp = t.nodes.new("ShaderNodeValToRGB")
    els = ramp.color_ramp.elements
    els[0].position, els[0].color = 0.0, (*colors[0], 1)
    els[1].position, els[1].color = 1.0, (*colors[-1], 1)
    for i, c in enumerate(colors[1:-1], 1):
        el = els.new(i / (len(colors) - 1))
        el.color = (*c, 1)
    t.links.new(span.outputs[0], ramp.inputs[0])
    t.links.new(ramp.outputs[0], em.inputs["Color"])
    t.links.new(em.outputs[0], out.inputs["Surface"])
    return tube(name, pts, r, m, shadow=False)


def clear_glass(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Roughness"].default_value = 0.03
    b.inputs["IOR"].default_value = 1.45
    b.inputs["Transmission Weight"].default_value = 1.0
    b.inputs["Base Color"].default_value = (0.92, 0.97, 0.96, 1)
    return m


def trubice():
    glass = clear_glass("glass")
    steel = material("steel", "#c4c7cb", "#aeb2b6", 400, 0.25, 1.0, dist=0.02, ao=0.3)
    wood = material("wood", "#7a5230", "#5e3d22", 16, 0.45, dist=0.05, bevel=0.002)
    wire = material("wire", "#3a2c20", "#2d2219", 200, 0.5, dist=0.02)
    L, R = 0.42, 0.035
    prof = [(0.0, -L - 0.06), (0.02, -L - 0.055), (R * 0.9, -L - 0.03), (R, -L), (R, L), (R * 0.9, L + 0.03), (0.02, L + 0.055), (0.0, L + 0.06)]
    lathe("tube", prof, glass, "x", 64, at=(0, 0, 0.2), smooth=60)
    gas_column("gas", [(x / 40 * L, 0, 0.2) for x in range(-40, 41)], R * 0.42,
               [(0.8, 0.1, 0.65), (0.95, 0.35, 0.45), (0.95, 0.75, 0.15), (0.25, 0.9, 0.25), (0.1, 0.7, 0.95), (0.45, 0.2, 0.9)], 1.5)
    for sx in (-1, 1):
        tube(f"pin{sx}", [(sx * (L + 0.02), 0, 0.2), (sx * (L + 0.1), 0, 0.2), (sx * (L + 0.1), 0, 0.07)], 0.003, wire)
        lathe(f"elec{sx}", [(0, sx * L - 0.012), (0.012, sx * L - 0.012), (0.012, sx * L + 0.012), (0, sx * L + 0.012)], steel, "x", 20, at=(0, 0, 0.2), smooth=30)
        box(f"foot{sx}", (sx * (L + 0.1) - 0.04, -0.04, 0.0), (sx * (L + 0.1) + 0.04, 0.04, 0.07), wood, 0.002)
    return {"dir": (0.0, -1.0, 0.12), "lens": 120, "floor": 0.0, "soft": 1.0}


def trubice2():
    glass = clear_glass("glass")
    steel = material("steel", "#c4c7cb", "#aeb2b6", 400, 0.25, 1.0, dist=0.02, ao=0.3)
    L, R = 0.26, 0.04
    for name, x, colors in (("a", -0.085, [(0.35, 0.5, 0.95), (0.6, 0.72, 1.0), (0.35, 0.5, 0.95)]), ("b", 0.085, [(0.7, 0.35, 0.85), (0.9, 0.6, 0.95), (0.7, 0.35, 0.85)])):
        prof = [(0.0, -L - 0.06), (0.018, -L - 0.05), (R * 0.9, -L - 0.03), (R, -L), (R, L), (R * 0.9, L + 0.03), (0.018, L + 0.05), (0.0, L + 0.06)]
        lathe(f"tube{name}", prof, glass, "z", 64, at=(x, 0, L + 0.09), smooth=60)
        gas_column(f"gas{name}", [(x, 0, L + 0.09 + z / 30 * L) for z in range(-30, 31)], R * 0.34, colors, 1.2)
        for z in (0.015, 2 * L + 0.165):
            lathe(f"cap{name}{z:.2f}", [(0, z), (0.02, z), (0.02, z + 0.02), (0, z + 0.02)], steel, n=24, at=(x, 0, 0), smooth=30)
    return {"dir": (0.0, -1.0, 0.06), "lens": 120, "floor": 0.0, "soft": 1.0}


def setup_render():
    scene = bpy.context.scene
    r = scene.render
    r.engine, r.film_transparent = "CYCLES", True
    r.resolution_x, r.resolution_y = RES
    r.image_settings.file_format, r.image_settings.color_mode = "PNG", "RGBA"
    c = scene.cycles
    c.samples, c.use_denoising, c.denoiser = SAMPLES, True, "OPENIMAGEDENOISE"
    c.max_bounces, c.diffuse_bounces, c.glossy_bounces = 10, 4, 6
    prefs = bpy.context.preferences.addons["cycles"].preferences
    if "--gpu" in args:
        prefs.compute_device_type = "OPTIX"
        prefs.get_devices()
        gpus = [d for d in prefs.devices if d.type == "OPTIX"]
        for d in prefs.devices:
            d.use = d in gpus
        c.device = "GPU" if gpus else "CPU"
    scene.view_settings.view_transform = "AgX"
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    return c.device


def studio(camera_dir):
    """Metal looks like metal only with something to reflect: a bright overhead sheet, a dim floor, no visible backdrop."""
    scene = bpy.context.scene
    world = bpy.data.worlds.new("w")
    scene.world = world
    world.use_nodes = True
    t = world.node_tree
    bg = t.nodes["Background"]
    co = t.nodes.new("ShaderNodeTexCoord")
    sep = t.nodes.new("ShaderNodeSeparateXYZ")
    t.links.new(co.outputs["Generated"], sep.inputs[0])
    grad = t.nodes.new("ShaderNodeValToRGB")
    ramp = grad.color_ramp
    ramp.elements[0].position, ramp.elements[0].color = 0.0, (0.2, 0.2, 0.22, 1)
    ramp.elements[1].position, ramp.elements[1].color = 1.0, (1.5, 1.52, 1.55, 1)
    mid = ramp.elements.new(0.52)
    mid.color = (0.42, 0.43, 0.46, 1)
    map_ = t.nodes.new("ShaderNodeMath")
    map_.operation = "MULTIPLY_ADD"
    map_.inputs[1].default_value, map_.inputs[2].default_value = 0.5, 0.5
    t.links.new(sep.outputs["Z"], map_.inputs[0])
    t.links.new(map_.outputs[0], grad.inputs[0])
    t.links.new(grad.outputs[0], bg.inputs[0])
    bg.inputs[1].default_value = 0.85
    az = math.atan2(camera_dir.y, camera_dir.x)
    for name, offset, el, energy, angle, color in (("key", -48, 52, 3.4, 24, (1.0, 0.96, 0.9)), ("fill", 62, 18, 0.7, 70, (0.9, 0.95, 1.0)), ("rim", 158, 34, 2.0, 16, (1.0, 0.98, 0.95))):
        sun = link(bpy.data.objects.new(name, bpy.data.lights.new(name, "SUN")))
        sun.data.energy, sun.data.angle, sun.data.color = energy, math.radians(angle), color
        a, e = az + math.radians(offset), math.radians(el)
        sun.rotation_mode = "QUATERNION"
        sun.rotation_quaternion = Vector((math.cos(a) * math.cos(e), math.sin(a) * math.cos(e), math.sin(e))).to_track_quat("Z", "Y")


def main():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    info = {"motor": motor, "civka": civka, "civka-bez": civka, "vez": vez, "turbina": turbina, "elektrarna": elektrarna, "vez-nad": lambda: vez(False, True, False), "hala": lambda: vez(False, False, True),
            "transformator": transformator, "prijimac": prijimac, "lod": lod, "trubice": trubice, "trubice2": trubice2}[SHOT]()
    scene = bpy.context.scene
    device = setup_render()
    d = Vector(info["dir"]).normalized()
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    coords, lo, hi = [], Vector((1e9, 1e9, 1e9)), Vector((-1e9, -1e9, -1e9))
    for o in scene.objects:
        if o.type in ("MESH", "CURVE") and not o.name.startswith("arc") and o.name not in info.get("skip", ()):
            for b in o.bound_box:
                p = o.matrix_world @ Vector(b)
                coords += list(p)
                lo = Vector(map(min, lo, p))
                hi = Vector(map(max, hi, p))
    for corner in info.get("margin", ()):
        coords += list(corner)
    if info["floor"] is not None:
        span = max(hi - lo)
        centre = (lo + hi) / 2
        g = mesh("floor", [(centre.x - 4 * span, centre.y - 4 * span, info["floor"]), (centre.x + 4 * span, centre.y - 4 * span, info["floor"]),
                           (centre.x + 4 * span, centre.y + 4 * span, info["floor"]), (centre.x - 4 * span, centre.y + 4 * span, info["floor"])], [(0, 1, 2, 3)], material("catch", "#888888"), 0)
        g.is_shadow_catcher = True
    cam = link(bpy.data.objects.new("cam", bpy.data.cameras.new("cam")))
    scene.camera = cam
    cam.data.lens, cam.data.clip_end = info["lens"], 100000
    cam.rotation_mode = "QUATERNION"
    cam.rotation_quaternion = (-d).to_track_quat("-Z", "Y")
    bpy.context.view_layer.update()
    loc, _scale = cam.camera_fit_coords(dg, coords)
    centre = (lo + hi) / 2
    cam.location = centre + (Vector(loc) - centre) * 1.05
    studio(d)
    bpy.context.view_layer.update()

    def uv(p):
        q = world_to_camera_view(scene, cam, Vector(p))
        return [round(q.x * RES[0], 1), round((1 - q.y) * RES[1], 1)]

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "body.json").write_text(json.dumps({"res": RES, "points": {k: uv(p) for k, p in POINTS.items()}, "device": device}, ensure_ascii=False, indent=1), encoding="utf-8")
    scene.render.filepath = str(OUT / "obraz.png")
    bpy.ops.render.render(write_still=True)
    print("STATS", json.dumps({"shot": SHOT, "device": device, "objects": len(scene.objects), "lo": [round(v, 3) for v in lo], "hi": [round(v, 3) for v in hi]}))


main()
