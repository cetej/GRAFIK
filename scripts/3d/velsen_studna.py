# Blender: the well of Velsen in section, measured on the book's section fig. 2.1 with its own scale bar (250 px = 1 m, centre x = 312, -2.41 m at y = 815): barrels, block, head, stake, pot and the man's place.
#   blender -b --factory-startup -P scripts/3d/velsen_studna.py -- OUT_DIR [--w 1014] [--h 2200] [--samples 128]
# A slice of ground through the well, seen straight on from about 4 m at the height of the man's head: the drawing's own perspective, the rims sag above the eye and rise below it. No generator paints over it.
# Writes zadni.png (all behind the man, RGBA), predni.png (stake, pot and stones in front of him, RGBA) and body.json (anchors in pixels). The man is the picture from FLUX, put between the two by velsen_studna_stranka.py: his 3D model came out a mutant (the operator).
import json
import math
import random
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

ARGS = sys.argv[sys.argv.index("--") + 1:]
OUT = Path(ARGS[0]).resolve()


def arg(name, default):
    return type(default)(ARGS[ARGS.index(name) + 1]) if name in ARGS else default


W, H, SAMPLES = arg("--w", 1014), arg("--h", 2200), arg("--samples", 128)
OUT.mkdir(parents=True, exist_ok=True)
random.seed(1977)

T = 0.028                   # stave thickness
FLOOR = -4.02               # the man came to rest on the rim of barrel 3
B2 = (-2.41, -4.39, 0.47, 0.60)     # top, bottom, radius at the ends, at the belly
B3 = (-4.00, -5.80, 0.34, 0.46)
B1 = (-0.02, -2.41, 0.47, 0.67)    # the upper barrel: only fragments of an iron hoop survive, "plausible, similar to the second" (p. 30), as in the book's section fig. 2.1
WATER = -0.63               # as drawn in fig. 2.1; the Roman average highest groundwater -0.5 to -0.75 m NAP (Vos, p. 34)
X, D = 1.05, 1.5            # half width of the block as in fig. 2.1 (2.1 m), depth behind the cut
SURFACE = 0.03              # as drawn in fig. 2.1, the upper barrel's rim at it
BOTTOM = -5.95


def radius(z, b):
    top, bot, re, rb = b
    mid, half = (top + bot) / 2, (top - bot) / 2
    return re + (rb - re) * (1 - ((z - mid) / half) ** 2)


def outer(z):
    """Outer edge of the lining at height z, None above and below the barrels."""
    if z > B2[0]:
        return radius(z, B1) + T if z >= B1[1] else 0.56
    if B2[1] <= z <= B2[0]:
        return radius(z, B2) + T
    if B3[1] <= z < B2[1]:
        return radius(z, B3) + T
    return None


def obj(name, verts, faces, mat, smooth=False):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    if smooth:
        me.shade_smooth()
    me.materials.append(mat)
    o = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(o)
    return o


def principled(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    n = m.node_tree.nodes
    return m, n, m.node_tree.links, n["Principled BSDF"]


def ramp(n, stops):
    r = n.new("ShaderNodeValToRGB")
    cr = r.color_ramp
    cr.elements[0].position, cr.elements[0].color = stops[0]
    cr.elements[1].position, cr.elements[1].color = stops[1]
    for pos, col in stops[2:]:
        e = cr.elements.new(pos)
        e.color = col
    return r


def rgb(h, a=1.0):
    def lin(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return (lin(int(h[1:3], 16) / 255), lin(int(h[3:5], 16) / 255), lin(int(h[5:7], 16) / 255), a)


def noise_mat(name, dark, light, scale, bump=0.5, rough=0.9, stretch=(1, 1, 1), detail=8.0):
    m, n, l, p = principled(name)
    tc, mp, nz = n.new("ShaderNodeTexCoord"), n.new("ShaderNodeMapping"), n.new("ShaderNodeTexNoise")
    mp.inputs["Scale"].default_value = (scale * stretch[0], scale * stretch[1], scale * stretch[2])
    nz.inputs["Detail"].default_value = detail
    l.new(tc.outputs["Object"], mp.inputs["Vector"])
    l.new(mp.outputs["Vector"], nz.inputs["Vector"])
    r = ramp(n, [(0.32, rgb(dark)), (0.68, rgb(light))])
    l.new(nz.outputs["Fac"], r.inputs["Fac"])
    info, mix = n.new("ShaderNodeObjectInfo"), n.new("ShaderNodeHueSaturation")
    tone = n.new("ShaderNodeMapRange")
    tone.inputs["To Min"].default_value, tone.inputs["To Max"].default_value = 0.78, 1.18
    l.new(info.outputs["Random"], tone.inputs["Value"])
    l.new(tone.outputs["Result"], mix.inputs["Value"])
    l.new(r.outputs["Color"], mix.inputs["Color"])
    l.new(mix.outputs["Color"], p.inputs["Base Color"])
    p.inputs["Roughness"].default_value = rough
    b = n.new("ShaderNodeBump")
    b.inputs["Strength"].default_value, b.inputs["Distance"].default_value = bump, 0.012
    l.new(nz.outputs["Fac"], b.inputs["Height"])
    l.new(b.outputs["Normal"], p.inputs["Normal"])
    return m


def soil_mat():
    """Cut face of the ground: strata by depth, a paler band where the pit was dug round the barrels (level 8)."""
    m, n, l, p = principled("Zemina")
    tc, nz, grain = n.new("ShaderNodeTexCoord"), n.new("ShaderNodeTexNoise"), n.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value, nz.inputs["Detail"].default_value = 2.2, 10.0
    grain.inputs["Scale"].default_value, grain.inputs["Detail"].default_value = 130.0, 6.0
    l.new(tc.outputs["Object"], nz.inputs["Vector"])
    l.new(tc.outputs["Object"], grain.inputs["Vector"])
    sep = n.new("ShaderNodeSeparateXYZ")
    l.new(tc.outputs["Object"], sep.inputs["Vector"])
    # depth with a wobble, so the strata do not run ruler straight
    wob = n.new("ShaderNodeMath")
    wob.operation = "MULTIPLY_ADD"
    wob.inputs[1].default_value, wob.inputs[2].default_value = 0.55, -0.27
    l.new(nz.outputs["Fac"], wob.inputs[0])
    depth = n.new("ShaderNodeMath")
    depth.operation = "ADD"
    l.new(sep.outputs["Z"], depth.inputs[0])
    l.new(wob.outputs["Value"], depth.inputs[1])
    scale = n.new("ShaderNodeMapRange")
    scale.inputs["From Min"].default_value, scale.inputs["From Max"].default_value = -7.0, -0.5
    l.new(depth.outputs["Value"], scale.inputs["Value"])
    strata = ramp(n, [(0.05, rgb("#4f6472")), (0.46, rgb("#566a78")), (0.66, rgb("#67737a")), (0.73, rgb("#74735f")), (0.84, rgb("#7f6c47")), (0.95, rgb("#6a5535")), (1.0, rgb("#3f3020"))])
    l.new(scale.outputs["Result"], strata.inputs["Fac"])
    # the dug pit: paler within about 0.8 m of the axis
    ab = n.new("ShaderNodeMath")
    ab.operation = "ABSOLUTE"
    l.new(sep.outputs["X"], ab.inputs[0])
    edge = n.new("ShaderNodeMath")
    edge.operation = "ADD"
    l.new(ab.outputs["Value"], edge.inputs[0])
    l.new(wob.outputs["Value"], edge.inputs[1])
    pit = n.new("ShaderNodeMapRange")
    pit.inputs["From Min"].default_value, pit.inputs["From Max"].default_value = 0.62, 0.86
    pit.inputs["To Min"].default_value, pit.inputs["To Max"].default_value = 0.4, 0.0
    l.new(edge.outputs["Value"], pit.inputs["Value"])
    mix = n.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    l.new(pit.outputs["Result"], mix.inputs["Factor"])
    l.new(strata.outputs["Color"], mix.inputs["A"])
    mix.inputs["B"].default_value = rgb("#6f6d57")
    # sand grains
    layers, stretch = n.new("ShaderNodeTexNoise"), n.new("ShaderNodeMapping")
    stretch.inputs["Scale"].default_value = (2.2, 2.2, 34.0)
    layers.inputs["Scale"].default_value, layers.inputs["Detail"].default_value = 1.0, 6.0
    l.new(tc.outputs["Object"], stretch.inputs["Vector"])
    l.new(stretch.outputs["Vector"], layers.inputs["Vector"])
    both = n.new("ShaderNodeMath")
    both.operation = "MULTIPLY_ADD"
    both.inputs[1].default_value, both.inputs[2].default_value = 0.32, 0.14
    l.new(layers.outputs["Fac"], both.inputs[0])
    plus = n.new("ShaderNodeMath")
    plus.operation = "MULTIPLY_ADD"
    plus.inputs[1].default_value = 0.55
    l.new(grain.outputs["Fac"], plus.inputs[0])
    l.new(both.outputs["Value"], plus.inputs[2])
    sp = ramp(n, [(0.42, (0.62, 0.62, 0.62, 1)), (0.68, (1.22, 1.22, 1.22, 1))])
    l.new(plus.outputs["Value"], sp.inputs["Fac"])
    mul = n.new("ShaderNodeMix")
    mul.data_type = "RGBA"
    mul.blend_type = "MULTIPLY"
    mul.inputs["Factor"].default_value = 1.0
    l.new(mix.outputs["Result"], mul.inputs["A"])
    l.new(sp.outputs["Color"], mul.inputs["B"])
    mottle, patches = n.new("ShaderNodeTexNoise"), ramp(n, [(0.36, (0.42, 0.42, 0.42, 1)), (0.66, (0.86, 0.86, 0.86, 1))])
    mottle.inputs["Scale"].default_value, mottle.inputs["Detail"].default_value = 3.4, 9.0
    l.new(tc.outputs["Object"], mottle.inputs["Vector"])
    l.new(mottle.outputs["Fac"], patches.inputs["Fac"])
    dark = n.new("ShaderNodeMix")
    dark.data_type = "RGBA"
    dark.blend_type = "MULTIPLY"
    dark.inputs["Factor"].default_value = 1.0
    l.new(mul.outputs["Result"], dark.inputs["A"])
    l.new(patches.outputs["Color"], dark.inputs["B"])
    l.new(dark.outputs["Result"], p.inputs["Base Color"])
    p.inputs["Roughness"].default_value = 0.95
    b = n.new("ShaderNodeBump")
    b.inputs["Strength"].default_value, b.inputs["Distance"].default_value = 0.5, 0.01
    l.new(grain.outputs["Fac"], b.inputs["Height"])
    l.new(b.outputs["Normal"], p.inputs["Normal"])
    return m


MAT = {
    "stave1": noise_mat("Dužiny 1", "#5a6554", "#a2ab94", 26, 0.35, 0.5, (14, 14, 0.12)),
    "stave2": noise_mat("Dužiny 2", "#212319", "#54563f", 26, 0.35, 0.5, (14, 14, 0.12)),
    "stave3": noise_mat("Dužiny 3", "#5c5a44", "#8f8d6c", 26, 0.35, 0.65, (14, 14, 0.12)),
    "hoop": noise_mat("Obruče", "#2f2619", "#6a5636", 40, 0.8, 0.8),
    "sand": noise_mat("Písek", "#66665a", "#8b8a79", 110, 1.2, 0.95),
    "quern": noise_mat("Žernov", "#5b5853", "#8e8a83", 260, 1.2, 0.92),
    "cobble": noise_mat("Kámen", "#45433e", "#6c6962", 40, 0.8, 0.9),
    "daub": noise_mat("Mazanice", "#463a30", "#685a4c", 70, 1.0, 0.9),
    "coal": noise_mat("Uhlí", "#0c0b0a", "#2a2725", 50, 1.0, 0.6),
    "stake": noise_mat("Kůl", "#231a10", "#4f3c25", 40, 0.6, 0.75, (10, 10, 0.25)),
    "iron": noise_mat("Železo", "#231a14", "#5a4030", 90, 1.0, 0.8),
    "shell": noise_mat("Mušle", "#5f5b50", "#857f71", 60, 0.3, 0.7),
    "cut": noise_mat("Řez dužin", "#5f5630", "#7c7245", 30, 0.2, 0.8),
    "beam": noise_mat("Trám", "#33261a", "#75603f", 7, 0.8, 0.8, (0.3, 6, 6)),
    "nut": noise_mat("Oříšek", "#2a1c10", "#46321c", 60, 0.3, 0.7),
    "pot": noise_mat("Nádoba", "#3a3026", "#6f5f45", 90, 0.4, 0.85),
    "soil": soil_mat(),
    "dirty": noise_mat("Špinavý písek", "#403b30", "#6f6853", 90, 1.4, 0.95),
    "surface": noise_mat("Povrch", "#5f5e48", "#7d7b60", 40, 1.0, 0.95),
    "fill": noise_mat("Výplň", "#4b4640", "#74695a", 22, 1.0, 0.95),
}
if "--zblizka" in ARGS:     # stones seen large: the fine grain of the big page reads as smooth plastic
    MAT["quern"] = noise_mat("Žernov", "#4d4a44", "#a09b91", 55, 3.0, 0.95, detail=12.0)
    MAT["cobble"] = noise_mat("Kámen", "#3d3b36", "#7f7b72", 45, 2.5, 0.92, detail=12.0)


def wash(mat, z0, z1, colour):
    """A dark stain on the staves that fades upwards from z0 to z1, its edge running up the grain."""
    n, l = mat.node_tree.nodes, mat.node_tree.links
    p = n["Principled BSDF"]
    base = p.inputs["Base Color"].links[0].from_socket
    tc, sep, nz, rng, add, mix = n.new("ShaderNodeTexCoord"), n.new("ShaderNodeSeparateXYZ"), n.new("ShaderNodeTexNoise"), n.new("ShaderNodeMapRange"), n.new("ShaderNodeMath"), n.new("ShaderNodeMix")
    l.new(tc.outputs["Object"], sep.inputs["Vector"])
    stretch = n.new("ShaderNodeMapping")
    stretch.inputs["Scale"].default_value = (22, 22, 0.8)
    l.new(tc.outputs["Object"], stretch.inputs["Vector"])
    l.new(stretch.outputs["Vector"], nz.inputs["Vector"])
    add.operation = "MULTIPLY_ADD"
    add.inputs[1].default_value = 0.7
    l.new(nz.outputs["Fac"], add.inputs[0])
    l.new(sep.outputs["Z"], add.inputs[2])
    rng.inputs["From Min"].default_value, rng.inputs["From Max"].default_value = z0 + 0.35, z1 + 0.35
    rng.inputs["To Min"].default_value, rng.inputs["To Max"].default_value = 0.9, 0.0
    l.new(add.outputs["Value"], rng.inputs["Value"])
    mix.data_type = "RGBA"
    l.new(rng.outputs["Result"], mix.inputs["Factor"])
    l.new(base, mix.inputs["A"])
    mix.inputs["B"].default_value = rgb(colour)
    l.new(mix.outputs["Result"], p.inputs["Base Color"])


wash(MAT["stave1"], -2.4, -1.75, "#2e3a24")
_pot = MAT["pot"].node_tree
_mix = _pot.nodes.new("ShaderNodeMix")
_mix.data_type = "RGBA"
_pot.links.new(_pot.nodes.new("ShaderNodeNewGeometry").outputs["Backfacing"], _mix.inputs["Factor"])
_pot.links.new(_pot.nodes["Principled BSDF"].inputs["Base Color"].links[0].from_socket, _mix.inputs["A"])
_mix.inputs["B"].default_value = rgb("#17120d")
_pot.links.new(_mix.outputs["Result"], _pot.nodes["Principled BSDF"].inputs["Base Color"])


def stave_barrel(name, b, mat, n_half=10):
    """A half barrel of separate staves, y >= 0, each with its own tone and a little gap."""
    top, bot = b[0], b[1]
    rows, cols = 28, 8
    def idx(side, r, c):
        return side * (rows + 1) * (cols + 1) + r * (cols + 1) + c
    for k in range(n_half):
        a0, a1 = math.pi * k / n_half + (0.004 if k else 0), math.pi * (k + 1) / n_half - (0.004 if k < n_half - 1 else 0)
        verts, faces = [], []
        for side in (0, 1):
            for r in range(rows + 1):
                z = top + (bot - top) * r / rows
                rad = radius(z, b) + (T if side else 0)
                for c in range(cols + 1):
                    a = a0 + (a1 - a0) * c / cols
                    verts.append((rad * math.cos(a), rad * math.sin(a), z))
        for side in (0, 1):
            for r in range(rows):
                for c in range(cols):
                    q = (idx(side, r, c), idx(side, r, c + 1), idx(side, r + 1, c + 1), idx(side, r + 1, c))
                    faces.append(q if side else q[::-1])
        for c in range(cols):
            faces.append((idx(0, 0, c), idx(0, 0, c + 1), idx(1, 0, c + 1), idx(1, 0, c)))
            faces.append((idx(0, rows, c + 1), idx(0, rows, c), idx(1, rows, c), idx(1, rows, c + 1)))
        for r in range(rows):
            faces.append((idx(0, r, 0), idx(0, r + 1, 0), idx(1, r + 1, 0), idx(1, r, 0)))
            faces.append((idx(0, r + 1, cols), idx(0, r, cols), idx(1, r, cols), idx(1, r + 1, cols)))
        o = obj(f"{name} dužina {k}", verts, faces, mat)
        o.data.materials.append(MAT["cut"])
        for f, pol in enumerate(o.data.polygons[-2 * rows:]):
            if (k == 0 and f % 2 == 0) or (k == n_half - 1 and f % 2 == 1):
                pol.material_index = 1


def backing(name, b):
    rows, seg = 28, 40
    top, bot = b[0], b[1]
    verts, faces = [], []
    for r in range(rows + 1):
        z = top + (bot - top) * r / rows
        rad = radius(z, b) + T * 0.6
        for i in range(seg + 1):
            a = math.pi * i / seg
            verts.append((rad * math.cos(a), rad * math.sin(a), z))
    n = seg + 1
    for r in range(rows):
        for i in range(seg):
            faces.append((r * n + i, r * n + i + 1, (r + 1) * n + i + 1, (r + 1) * n + i))
    obj(name, verts, faces, MAT["coal"])


def hoop(z, b, tube=0.013, arc=(0.0, 1.0)):
    """Half ring of hazel saplings on the outside; rods side by side, seen in the section as knobs."""
    rad = radius(z, b) + T + tube
    for j, dz in enumerate((-tube * 1.6, 0.0, tube * 1.6)):
        verts, faces = [], []
        seg, tseg = 48, 8
        for i in range(seg + 1):
            a = math.pi * (arc[0] + (arc[1] - arc[0]) * i / seg)
            c = Vector((rad * math.cos(a), rad * math.sin(a), z + dz))
            for t in range(tseg):
                ang = 2 * math.pi * t / tseg
                out = Vector((math.cos(a), math.sin(a), 0))
                p = c + out * tube * math.cos(ang) + Vector((0, 0, tube * math.sin(ang)))
                verts.append(tuple(p))
        for i in range(seg):
            for t in range(tseg):
                faces.append((i * tseg + t, i * tseg + (t + 1) % tseg, (i + 1) * tseg + (t + 1) % tseg, (i + 1) * tseg + t))
        faces += [tuple(range(tseg))[::-1], tuple(seg * tseg + t for t in range(tseg))]
        obj(f"Obruč {z:.2f} {j}", verts, faces, MAT["hoop"], smooth=True)


def ground():
    """The block: the cut face at y = 0 with the barrels' outline left open, the top and the right side going back."""
    rows = 320
    top, bot = SURFACE, BOTTOM
    verts, faces = [], []
    for r in range(rows + 1):
        z = top + (bot - top) * r / rows
        e = outer(z)
        xs = (-X, 0.0, 0.0, X) if e is None else (-X, -e, e, X)
        for x in xs:
            verts.append((x, 0.004, z))
    for r in range(rows):
        a, b = r * 4, (r + 1) * 4
        if outer(top + (bot - top) * r / rows) is None or outer(top + (bot - top) * (r + 1) / rows) is None:
            faces.append((a, a + 3, b + 3, b))
        else:
            faces.append((a, a + 1, b + 1, b))
            faces.append((a + 2, a + 3, b + 3, b + 2))
    obj("Zemina", verts, faces, MAT["soil"])
    # the right side with the same strata, the top of the ground with the well's mouth left open
    obj("Bok", [(X, 0.004, SURFACE), (X, D, SURFACE), (X, D, BOTTOM), (X, 0.004, BOTTOM)], [(0, 1, 2, 3)], MAT["soil"])
    obj("Spodek", [(-X, 0.004, BOTTOM), (X, 0.004, BOTTOM), (X, D, BOTTOM), (-X, D, BOTTOM)], [(0, 3, 2, 1)], MAT["soil"])
    seg = 28
    verts, faces = [(-X, 0.004, SURFACE), (X, 0.004, SURFACE), (X, D, SURFACE), (-X, D, SURFACE)], []
    edge = []
    for i in range(seg + 1):
        a = math.pi * i / seg
        edge.append(len(verts))
        verts.append((0.56 * math.cos(a), 0.56 * math.sin(a), SURFACE))
    # fan from the mouth to the outline
    outline = [(X, 0.004, SURFACE), (X, D, SURFACE), (0, D, SURFACE), (-X, D, SURFACE), (-X, 0.004, SURFACE)]
    base = len(verts)
    verts += outline
    n = len(outline)
    for i in range(seg):
        t0, t1 = i / seg * (n - 1), (i + 1) / seg * (n - 1)
        o0, o1 = base + round(t0), base + round(t1)
        faces.append((edge[i], o0, o1, edge[i + 1]) if o0 != o1 else (edge[i], o0, edge[i + 1]))
    obj("Povrch", verts, faces, MAT["surface"])


def well_head():
    """Above ground only a reconstruction (the book's section, fig. 2.1; p. 30: no trace survived): a wall of planks at the back, corner posts of stacked timbers leaning apart at the cut, flat stones at the sides."""
    def beam(c, size):
        bpy.ops.mesh.primitive_cube_add(size=1, location=c)
        o = bpy.context.object
        o.scale = size
        o.rotation_euler = (0, 0, random.uniform(-0.012, 0.012))
        o.data.materials.append(MAT["beam"])
    h = 0.135
    for k in range(7):
        z = SURFACE - 0.1 + h / 2 + k * h
        beam((0, 0.56, z), (1.1, 0.1, h * 0.96))
        if k < 5:
            for sx in (-1, 1):
                beam((sx * 0.52, 0.34, z), (0.1, 0.44, h * 0.96))
    for sx in (-1, 1):
        for k in range(9):
            beam((sx * (0.5 + 0.13 * k / 8), 0.12, SURFACE + 0.05 + k * 0.083), (0.17 if k % 2 else 0.14, 0.2, 0.078))
        chunk(f"Deska {sx}", (sx * 0.84, 0.06, SURFACE + 0.035), 0.3, MAT["fill"], (1.0, 0.3, 0.12), 3).rotation_euler = (0, 0, 0)


def sand_face():
    """The sand as a pale film over the cut, so the staves and the lower rim show through as in the drawing."""
    def film(name, z0, z1, rad_at, mat):
        rows = 40
        verts, faces = [], []
        for r in range(rows + 1):
            z = z0 + (z1 - z0) * r / rows
            rad = rad_at(z)
            verts += [(-rad, 0.002, z), (rad, 0.002, z)]
        for r in range(rows):
            faces.append((r * 2, r * 2 + 1, r * 2 + 3, r * 2 + 2))
        obj(name, verts, faces, mat)
    MAT["sand"].node_tree.nodes["Principled BSDF"].inputs["Alpha"].default_value = 0.55
    MAT["dirty"].node_tree.nodes["Principled BSDF"].inputs["Alpha"].default_value = 0.38
    film("Písek řez", B2[1], B3[1], lambda z: radius(z, B3), MAT["sand"])
    film("Špinavý písek", FLOOR, B2[1], lambda z: radius(z, B2) - 0.002, MAT["dirty"])
    # the floor going back inside the barrel, behind the cut
    seg = 24
    verts, faces = [(0, 0.003, FLOOR)], []
    rad = radius(FLOOR, B2)
    for i in range(seg + 1):
        a = math.pi * i / seg
        verts.append((rad * math.cos(a), rad * math.sin(a), FLOOR))
    for i in range(seg):
        faces.append((0, i + 1, i + 2))
    obj("Písek dno", verts, faces, MAT["dirty"])
    verts, faces = [(0, 0.003, B3[1])], []
    rad = radius(B3[1], B3)
    for i in range(seg + 1):
        a = math.pi * i / seg
        verts.append((rad * math.cos(a), rad * math.sin(a), B3[1]))
    for i in range(seg):
        faces.append((0, i + 1, i + 2))
    obj("Písek dno 3", verts, faces, MAT["surface"])


def inner(z):
    """Inner radius of the lining at height z."""
    return radius(z, B1) if z >= B1[1] else radius(z, B2)


def water():
    """The well full of water up to the groundwater level: a tinted pane with a flat front, IOR 1 so nothing behind it is bent, and its surface."""
    rows, seg = 90, 32
    z0, z1 = WATER, FLOOR
    verts, faces = [], []
    for r in range(rows + 1):
        z = z0 + (z1 - z0) * r / rows
        rad = inner(z) - 0.002
        for i in range(seg + 1):
            a = math.pi * i / seg
            verts.append((rad * math.cos(a), rad * math.sin(a), z))
    n = seg + 1
    for r in range(rows):
        for i in range(seg):
            faces.append((r * n + i, r * n + i + 1, (r + 1) * n + i + 1, (r + 1) * n + i))
        faces.append((r * n, (r + 1) * n, (r + 1) * n + seg, r * n + seg))
    faces.append(tuple(range(seg + 1)))
    m, _, _, p = principled("Voda")
    p.inputs["Base Color"].default_value = rgb("#dfe9e6")
    p.inputs["Transmission Weight"].default_value = 1.0
    p.inputs["IOR"].default_value = 1.0
    p.inputs["Roughness"].default_value = 0.0
    return obj("Voda", verts, faces, m)


def chunk(name, c, size, mat, squash=(1, 1, 1), cuts=3):
    """A broken stone: an icosphere cut by random planes, so it has the flat fractures the book's photograph shows."""
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=4, radius=size)
    for v in bm.verts:
        v.co.x *= squash[0] * (1 + 0.05 * math.sin(v.co.y * 7 / size + c[0] * 9))
        v.co.y *= squash[1] * (1 + 0.05 * math.sin(v.co.z * 6 / size + c[1] * 7))
        v.co.z *= squash[2] * (1 + 0.05 * math.sin(v.co.x * 5 / size + c[2] * 5))
    for _ in range(cuts):
        n = Vector((random.gauss(0, 1), random.gauss(0, 1), random.gauss(0, 1))).normalized()
        bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=n * size * random.uniform(0.35, 0.75), plane_no=n, clear_outer=True)
        edges = [e for e in bm.edges if e.is_boundary]
        if edges:
            bmesh.ops.holes_fill(bm, edges=edges, sides=0)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat)
    o = bpy.data.objects.new(name, me)
    o.location = c
    o.rotation_euler = (random.uniform(0, 3.1), random.uniform(0, 3.1), random.uniform(0, 3.1))
    bpy.context.collection.objects.link(o)
    return o


def quern_piece(name, c, mat):
    """A broken sector of a rotary quern: a flat disc piece with a sloped top and a raw broken edge."""
    rmax, rmin = random.uniform(0.15, 0.23), random.uniform(0.025, 0.06)
    span, h = math.radians(random.uniform(45, 130)), random.uniform(0.05, 0.085)
    steps = 16
    def rim(radius_, jitter, z):
        out = []
        for i in range(steps + 1):
            a = span * i / steps
            r = radius_ * (1 + random.uniform(-jitter, jitter))
            out.append((r * math.cos(a), r * math.sin(a), z + random.uniform(-0.002, 0.002)))
        return out
    bottom_out, top_out = rim(rmax, 0.012, 0.0), rim(rmax, 0.012, h * 0.75)
    bottom_in, top_in = rim(rmin, 0.05, 0.0), rim(rmin, 0.05, h)
    verts = bottom_out + top_out + bottom_in + top_in
    n = steps + 1
    faces = []
    for i in range(steps):
        faces.append((i, i + 1, n + i + 1, n + i))                          # the worked outer rim
        faces.append((2 * n + i + 1, 2 * n + i, 3 * n + i, 3 * n + i + 1))  # the eye
        faces.append((n + i, n + i + 1, 3 * n + i + 1, 3 * n + i))          # the top
        faces.append((i + 1, i, 2 * n + i, 2 * n + i + 1))                  # the grinding face
    faces.append((0, n, 3 * n, 2 * n))                                      # the two broken sides
    faces.append((steps, 2 * n + steps, 3 * n + steps, n + steps))
    o = obj(name, verts, faces, mat)
    o.location = c
    o.rotation_euler = (random.uniform(-1.3, 1.3), random.uniform(-1.3, 1.3), random.uniform(0, 6.28))
    return o


def rubble():
    """Behind and beside the man: quern fragments, stones and burnt daub, with the mass above him (level 4, p. 34)."""
    def place(n, size, mat, region, squash=(1, 0.8, 0.7), cuts=3, prefix="Kámen"):
        for i in range(n):
            x, z = random.uniform(*region[0]), random.uniform(*region[1])
            rad = radius(z, B2) - 0.05
            x = max(-rad, min(rad, x))
            ymax = math.sqrt(max(0.01, rad * rad - x * x))
            chunk(f"{prefix} {i}", (x, random.uniform(0.03, ymax), z), random.uniform(*size), mat, squash, cuts)
    def querns(k, region, prefix):
        for i in range(k):
            x, z = random.uniform(*region[0]), random.uniform(*region[1])
            rad = radius(z, B2) - 0.1
            x = max(-rad, min(rad, x))
            quern_piece(f"{prefix} {i}", (x, random.uniform(0.08, max(0.1, math.sqrt(max(0.01, rad * rad - x * x)))), z), MAT["quern"])
    querns(26, ((-0.46, -0.2), (-3.82, -3.3)), "Žernov L")
    querns(4, ((-0.46, -0.28), (-3.3, -3.18)), "Žernov H")
    place(24, (0.045, 0.09), MAT["cobble"], ((-0.55, -0.15), (-3.95, -3.3)), (1, 0.8, 0.65), 6, "Kámen")
    place(10, (0.03, 0.07), MAT["daub"], ((-0.55, -0.2), (-3.9, -3.3)), (1, 0.7, 0.6), 6, "Mazanice")
    place(8, (0.02, 0.05), MAT["coal"], ((-0.55, 0.2), (FLOOR, -3.5)), (1, 0.9, 0.7), 3, "Uhlí")


def stake():
    """About 1.5 m, from the barrel's rim to the chest (p. 35); it stands in front of the man in the picture."""
    a, b = Vector((-0.43, 0.03, -2.42)), Vector((0.2, 0.03, -3.88))
    axis = b - a
    n = axis.normalized()
    side = n.cross(Vector((0, 1, 0))).normalized()
    up = n.cross(side).normalized()
    verts, faces = [], []
    rings, seg = 40, 12
    for r in range(rings + 1):
        t = r / rings
        c = a + axis * t
        rad = 0.03 * (1 + 0.1 * math.sin(t * 19) + 0.05 * math.sin(t * 47)) * (0.55 if t > 0.97 else 1)
        for s in range(seg):
            ang = 2 * math.pi * s / seg
            verts.append(tuple(c + side * (rad * math.cos(ang) + 0.006 * math.sin(t * 11)) + up * (rad * math.sin(ang) + 0.005 * math.cos(t * 7))))
    for r in range(rings):
        for s in range(seg):
            faces.append((r * seg + s, r * seg + (s + 1) % seg, (r + 1) * seg + (s + 1) % seg, (r + 1) * seg + s))
    faces.append(tuple(range(seg)))
    faces.append(tuple(rings * seg + s for s in range(seg - 1, -1, -1)))
    return obj("Kůl", verts, faces, MAT["stake"], smooth=True)


def lower_finds():
    """In the sand of barrel 3 (p. 34): shells, a 72 cm chain of 21 links, hazelnuts. Half out of the cut face, or they would hide behind it."""
    for _ in range(90):
        z = random.uniform(B3[1] + 0.05, FLOOR - 0.05)
        rad = (radius(z, B3) if z < B2[1] else radius(z, B2)) - 0.03
        if random.random() < (z - B3[1]) / 1.8 * 0.8:     # most shells lie in the lower part
            continue
        bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8, radius=random.uniform(0.006, 0.012), location=(random.uniform(-rad, rad), 0.0, z))
        o = bpy.context.object
        o.scale = (1, 0.35, 0.75)
        o.rotation_euler = (0, random.uniform(0, 3.14), 0)
        o.data.materials.append(MAT["shell"])
    x0, z0 = -0.18, -5.22
    for i in range(21):
        t = i / 20
        bpy.ops.mesh.primitive_torus_add(major_radius=0.016, minor_radius=0.0035, major_segments=16, minor_segments=6, location=(x0 + 0.34 * t, 0.0, z0 + 0.09 * math.sin(t * 5.1)), rotation=(math.pi / 2, 0, 0.4 if i % 2 else -0.4))
        o = bpy.context.object
        o.scale = (1.2, 0.8, 1)
        o.data.materials.append(MAT["iron"])
    for _ in range(5):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8, radius=0.012, location=(random.uniform(-0.25, 0.25), 0.0, random.uniform(-4.9, -4.5)))
        bpy.context.object.data.materials.append(MAT["nut"])


def pot():
    """The handmade vessel with lugs (p. 37), broken at the front, at the lower right as in the book's section. Its inside is dark, the hole has a jagged edge."""
    prof = [(0.0, 0.0), (0.09, 0.008), (0.15, 0.08), (0.17, 0.17), (0.14, 0.27), (0.11, 0.31), (0.125, 0.35)]
    rows, seg = 170, 300
    zs, rs = [z for _, z in prof], [r for r, _ in prof]
    verts, faces = [], []
    for k in range(rows + 1):
        z = zs[-1] * k / rows
        r = float(np.interp(z, zs, rs))
        for i in range(seg):
            a = 2 * math.pi * i / seg
            verts.append((r * math.cos(a), r * math.sin(a), z))
    for k in range(rows):
        z = zs[-1] * k / rows
        for i in range(seg):
            a = 2 * math.pi * i / seg
            du, dv = (a - 4.35) / 0.8, (z - 0.2) / 0.11
            if du * du + dv * dv < 1 + 0.4 * math.sin(a * 17 + z * 40) + 0.25 * math.sin(a * 41 - z * 90):
                continue
            faces.append((k * seg + i, k * seg + (i + 1) % seg, (k + 1) * seg + (i + 1) % seg, (k + 1) * seg + i))
    o = obj("Nádoba", verts, faces, MAT["pot"], smooth=True)
    o.location = (0.3, -0.02, -4.5)
    o.rotation_euler = (0.16, 0.14, 0)
    return o


def front_stones():
    """A few fragments on his lap and shoulder, in front of him in the picture. Seen large (--zblizka) the two on the hand and the foot of the picture look pasted on."""
    spots = ((-0.36, -3.86, 0.07, "quern"), (-0.38, -3.68, 0.06, "quern"), (-0.42, -3.5, 0.05, "cobble"))
    spots = spots[2:] if "--zblizka" in ARGS else spots
    return [chunk(f"Přední {i}", (x, -0.06, z), s, MAT[m], (1, 0.7, 0.65), 6) for i, (x, z, s, m) in enumerate(spots)]


def scene_setup():
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    c = sc.cycles
    c.samples, c.use_denoising = SAMPLES, True
    c.device = "CPU"
    if "--gpu" in ARGS:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "OPTIX"
        prefs.get_devices()
        gpus = [d for d in prefs.devices if d.type == "OPTIX"]
        for d in prefs.devices:
            d.use = d in gpus
        c.device = "GPU" if gpus else "CPU"
    sc.render.resolution_x, sc.render.resolution_y = W, H
    sc.render.resolution_percentage = 100
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
    world = bpy.data.worlds.new("Svět")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.6, 0.62, 0.66, 1)
    world.node_tree.nodes["Background"].inputs[1].default_value = 0.7
    sc.world = world
    # key from the upper left in front of the cut, a weak fill from the right
    for name, loc, power, size, col in (("Hlavní", (-3.5, -8.5, 1.5), 2200, 8, (1, 0.97, 0.92)), ("Výplň", (6, -7, -4.5), 1300, 9, (0.92, 0.95, 1))):
        d = bpy.data.lights.new(name, "AREA")
        d.energy, d.size, d.color = power, size, col
        o = bpy.data.objects.new(name, d)
        o.location = loc
        o.rotation_euler = (Vector((0, 0, -3.5)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        bpy.context.collection.objects.link(o)
    cam = bpy.data.cameras.new("Kamera")
    cam.sensor_fit = "VERTICAL"
    dist = arg("--cam", 4.4)
    cam.lens = cam.sensor_height * dist / 6.944     # the cut plane fills the height of fig. 2.1: 1736 px at 250 px/m
    cam.clip_start = 0.1
    co = bpy.data.objects.new("Kamera", cam)
    co.location = (0.0, -dist, -2.622)              # the middle of fig. 2.1
    co.rotation_euler = (math.pi / 2, 0, 0)
    bpy.context.collection.objects.link(co)
    sc.camera = co
    return sc, co


def render(sc, path, transparent=False):
    sc.render.film_transparent = transparent
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def main():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    ground()
    well_head()
    stave_barrel("Sud 1", B1, MAT["stave1"])
    backing("Za dužinami 1", B1)
    for z in (-0.36, -0.43, -0.50, -0.57, -0.92, -1.0, -1.7, -1.78, -2.13, -2.2, -2.27, -2.34):
        hoop(z, B1)
    stave_barrel("Sud 2", B2, MAT["stave2"])
    backing("Za dužinami 2", B2)
    for z in (-2.46, -2.53, -2.60, -2.67, -3.06, -3.14, -3.66, -3.74, -4.13, -4.20, -4.27, -4.34):
        hoop(z, B2)
    stave_barrel("Sud 3", B3, MAT["stave3"], 8)
    backing("Za dužinami 3", B3)
    for z in (-4.48, -4.55, -4.62, -4.69, -4.9, -5.3, -5.5, -5.58, -5.65, -5.72):
        hoop(z, B3, 0.011)
    sand_face()
    lower_finds()
    rubble()
    pot()
    water()
    stk = stake()
    front = front_stones()
    jar = pot()
    sc, co = scene_setup()
    bpy.context.view_layer.update()

    def px(v):
        c = world_to_camera_view(sc, co, Vector(v))
        return (round(c.x * W, 1), round((1 - c.y) * H, 1))

    points = {"hlava": (0.62, 0.0, 0.14), "hladina": (0.42, 0.3, WATER), "sud1": (0.5, 0.2, -1.5), "kul": (-0.41, 0.03, -2.47), "kameny": (-0.42, 0.0, -3.3), "kameny_nad": (-0.42, 0.0, -2.72),
              "muz": (0.37, 0.0, -3.35), "bota": (-0.2, 0.0, -3.96), "bota_pod": (-0.2, 0.0, -4.1), "nadoba": (0.47, 0.0, -4.38), "sud3": (0.28, 0.0, -4.9),
              "povrch": (-X, 0.0, SURFACE), "ret": (-X, 0.0, -2.41), "floor": (-X, 0.0, -4.0), "dno": (-X, 0.0, -5.8), "metr0": (-X + 0.1, 0.0, -5.45), "metr1": (-X + 0.1, 0.0, -4.45),
              "plast0": (-0.5, 0.0, -3.5), "plast1": (0.3, 0.0, -2.5), "muz0": (0.0, 0.0, FLOOR - 0.06), "muz1": (0.0, 0.0, FLOOR + 1.25)}
    zs = [B2[0] + (FLOOR - B2[0]) * i / 24 for i in range(25)]
    outline = [px((radius(z, B2), 0, z)) for z in zs] + [px((-radius(z, B2), 0, z)) for z in reversed(zs)]
    (OUT / "body.json").write_text(json.dumps({"res": [W, H], "points": {k: px(v) for k, v in points.items()}, "sud2": outline}, indent=1), encoding="utf-8")
    keep = {stk.name, jar.name, *(f.name for f in front)}
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    for o in meshes:
        o.hide_render = o.name in keep
    render(sc, OUT / "zadni.png", transparent=True)
    for o in meshes:
        o.hide_render = o.name not in keep
    render(sc, OUT / "predni.png", transparent=True)
    print("HOTOVO")


main()
