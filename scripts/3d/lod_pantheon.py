# The Pantheon, Rome, built from published numbers (free):
#   blender -b -P scripts/3d/lod_pantheon.py -- out.glb
#   blender -b -P scripts/3d/lod_pantheon.py -- out.glb --render DIR [--samples 96] [--res 1920 1080] [--az -122] [--el 10]
# --render: axial section through the rotunda (near half removed), portico whole, real materials, sun through the oculus.
# Writes DIR/rez.png (RGBA) and DIR/body.json: canvas positions of named 3D points, so labels and the sphere are exact.
# Every size is in DIM (metres) with its source; "odhad" = our estimate, no published figure found.
# Axes: x from the portico to the apse, y across, z up, rotunda floor z = 0.
import json
import math
import os
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Vector

DIM = {
    "length": 79.5,         # steps to the outer band of the rotunda, from the sizes below
    "width": 56.5,          # inner_d + 2 * wall + outer bands
    "height": 48.8,         # foundation to the oculus lip, 44.1 of it above the floor
    "inner_d": 43.3,        # Wikipedia Pantheon, Rome
    "oculus_d": 9.0,        # 30 Roman feet, Wikipedia; other sources 8.2 to 9.1
    "wall": 6.2,            # Moore 2002: about 20 ft at the piers; Wikipedia 2nd-century domes: 6 m
    "wall_h": 31.7,         # Moore 2002: 104 ft
    "dome_t_base": 6.4,     # Wikipedia Pantheon, Rome
    "dome_t_top": 1.2,      # Wikipedia Pantheon, Rome
    "coffer_rings": 5,      # Moore 2002
    "coffer_per_ring": 28,  # Wikipedia Pantheon, Rome
    "coffer_steps": 4,      # Moore 2002
    "coffer_depth": 1.15,   # odhad
    "step_rings": 7,        # Moore 2002
    "step_rise": 0.6,       # odhad: seven rings end on the dome curve
    "step_run": 0.95,       # odhad
    "found_w": 7.2,         # about 7.2 by 4.7 m, secondary sources disagree by 0.1 m
    "found_h": 4.7,
    "col_shaft": 11.9,      # Wikipedia Pantheon, Rome
    "col_d": 1.5,           # Wikipedia Pantheon, Rome
    "col_base": 0.85,       # odhad
    "col_cap": 1.6,         # odhad
    "door_h": 6.4,          # Moore 2002: bronze doors 21 ft
    "portico_w": 33.6,      # odhad: column axes, from photographs
    "portico_d": 14.2,      # odhad: front column axis to the block wall
    "block_d": 5.15,        # odhad: block wall to the outer rotunda on the axis
    "steps_h": 1.3,         # odhad
    "cornice_1": 13.0,      # odhad: outer rotunda bands
    "cornice_2": 23.0,      # odhad
    "order_h": 9.9,         # odhad: inner order, floor to entablature
    "entab_h": 2.7,         # odhad
    "exedra_w": 8.6,        # odhad
    "exedra_d": 3.7,        # odhad
    "module": 3.0,          # odhad: floor grid
}

args = sys.argv[sys.argv.index("--") + 1:]
out = args[0]


def opt(name, default, n=1):
    if name not in args:
        return default
    i = args.index(name)
    return args[i + 1] if n == 1 else args[i + 1:i + 1 + n]


RENDER = opt("--render", None)
SAMPLES = int(opt("--samples", 96))
RES = [int(v) for v in opt("--res", (1920, 1080), 2)]
CAM_AZ = float(opt("--az", -122))
CAM_EL = float(opt("--el", 10))
CAM_SCALE = float(opt("--scale", 120))
CAM_DX = float(opt("--dx", 12.75))
CAM_DZ = float(opt("--dz", 15.46))

R_I = DIM["inner_d"] / 2
R_O = R_I + DIM["wall"]
Z_S = R_I                                      # springing: interior height = diameter, so a sphere fits
R_OC = DIM["oculus_d"] / 2
PHI_MAX = math.acos(R_OC / R_I)
N = 192
SECTOR = 2 * math.pi / DIM["coffer_per_ring"]
X_WALL = -(R_O + DIM["block_d"])               # block front
X_COL = X_WALL - DIM["portico_d"]              # front column axis
X_CUT = X_WALL + 1.4                           # near half is removed behind this plane
BLOCK_Y = DIM["portico_w"] / 2 + 1.0
Z_P = DIM["steps_h"]
Z_ENT = Z_P + DIM["col_base"] + DIM["col_shaft"] + DIM["col_cap"]
Z_ROOF = Z_ENT + 3.0
Z_APEX = Z_ROOF + 7.55                         # odhad
R_FOUND_I = R_I - 0.4
R_FOUND_O = R_FOUND_I + DIM["found_w"]
Z_EARTH = -8.0
INSCRIPTION = "M\u00b7AGRIPPA\u00b7L\u00b7F\u00b7COS\u00b7TERTIVM\u00b7FECIT"

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene


# -- geometry helpers -----------------------------------------------------------------------------------------------
class Geo:
    """Loose parts collected per material, one mesh object each at the end."""

    def __init__(self):
        self.parts = {}

    def add(self, mat, verts, faces):
        p = self.parts.setdefault(mat, ([], []))
        base = len(p[0])
        p[0].extend(tuple(v) for v in verts)
        p[1].extend([i + base for i in f] for f in faces)

    def box(self, mat, lo, hi):
        (a, b, c), (d, e, f) = lo, hi
        self.add(mat, [(a, b, c), (d, b, c), (d, e, c), (a, e, c), (a, b, f), (d, b, f), (d, e, f), (a, e, f)],
                 [(3, 2, 1, 0), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)])

    def rbox(self, mat, az, rho0, rho1, t0, t1, z0, z1):
        """Box in the frame of an azimuth: rho along the radius, t across it."""
        c, s = math.cos(az), math.sin(az)
        p = lambda r, t, z: (r * c - t * s, r * s + t * c, z)
        self.add(mat, [p(rho0, t0, z0), p(rho1, t0, z0), p(rho1, t1, z0), p(rho0, t1, z0),
                       p(rho0, t0, z1), p(rho1, t0, z1), p(rho1, t1, z1), p(rho0, t1, z1)],
                 [(3, 2, 1, 0), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)])

    def cyl(self, mat, x, y, z0, z1, r0, r1, n=24):
        v = [(x + r * math.cos(2 * math.pi * i / n), y + r * math.sin(2 * math.pi * i / n), z)
             for z, r in ((z0, r0), (z1, r1)) for i in range(n)]
        f = [list(range(n - 1, -1, -1)), list(range(n, 2 * n))]
        f += [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
        self.add(mat, v, f)

    def sector(self, mat, r0, r1, z0, z1, a0, a1):
        """Closed block of a ring between two azimuths."""
        n = max(1, int(abs(a1 - a0) / (2 * math.pi) * N))
        v = []
        for i in range(n + 1):
            a = a0 + (a1 - a0) * i / n
            c, s = math.cos(a), math.sin(a)
            v += [(r0 * c, r0 * s, z0), (r1 * c, r1 * s, z0), (r1 * c, r1 * s, z1), (r0 * c, r0 * s, z1)]
        f = [(0, 1, 2, 3), (4 * n + 3, 4 * n + 2, 4 * n + 1, 4 * n)]
        for i in range(n):
            for j in range(4):
                a, b = 4 * i + j, 4 * i + (j + 1) % 4
                f.append((b, a, a + 4, b + 4))
        self.add(mat, v, f)

    def prism_x(self, mat, pts, x0, x1):
        """Convex polygon in (y, z) extruded along x."""
        n = len(pts)
        v = [(x0, y, z) for y, z in pts] + [(x1, y, z) for y, z in pts]
        f = [list(range(n - 1, -1, -1)), list(range(n, 2 * n))] + [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
        self.add(mat, v, f)

    def rprism(self, mat, az, rho0, rho1, pts):
        """Convex polygon in (t, z) extruded along the radius at an azimuth."""
        c, s = math.cos(az), math.sin(az)
        p = lambda r, t, z: (r * c - t * s, r * s + t * c, z)
        n = len(pts)
        v = [p(rho0, t, z) for t, z in pts] + [p(rho1, t, z) for t, z in pts]
        f = [list(range(n - 1, -1, -1)), list(range(n, 2 * n))] + [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
        self.add(mat, v, f)


def mesh_object(name, verts, faces):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    me.update()
    o = bpy.data.objects.new(name, me)
    scene.collection.objects.link(o)
    return o


def ring_solid(name, poly, n=N):
    """Closed polygon (r, z) revolved around z, no vertex on the azimuth 0 plane (the section stays clean)."""
    m = len(poly)
    v = []
    for i in range(n):
        a = (i + 0.5) * 2 * math.pi / n
        v += [(r * math.cos(a), r * math.sin(a), z) for r, z in poly]
    f = [(i * m + j, i * m + (j + 1) % m, ((i + 1) % n) * m + (j + 1) % m, ((i + 1) % n) * m + j) for i in range(n) for j in range(m)]
    return mesh_object(name, v, f)


def disc_solid(name, r, z0, z1, n=N):
    v = [(r * math.cos((i + 0.5) * 2 * math.pi / n), r * math.sin((i + 0.5) * 2 * math.pi / n), z) for z in (z0, z1) for i in range(n)]
    f = [list(range(n - 1, -1, -1)), list(range(n, 2 * n))] + [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
    return mesh_object(name, v, f)


def box_object(name, lo, hi):
    g = Geo()
    g.box("n", lo, hi)
    return mesh_object(name, *g.parts["n"])


def boolean(o, cutter):
    before = len(o.data.polygons)
    m = o.modifiers.new("cut", "BOOLEAN")
    m.operation, m.object, m.solver = "DIFFERENCE", cutter, "MANIFOLD"
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.modifier_apply(modifier=m.name)
    if not o.data.polygons:
        raise RuntimeError(f"boolean emptied {o.name} ({before} faces before)")


def clip(poly, lo, hi):
    """Sutherland-Hodgman against two horizontal planes; the wall section never splits in two."""
    def half(pts, keep, z_cut):
        res = []
        for i, a in enumerate(pts):
            b = pts[(i + 1) % len(pts)]
            if keep(a[1]):
                res.append(a)
            if keep(a[1]) != keep(b[1]):
                t = (z_cut - a[1]) / (b[1] - a[1])
                res.append((a[0] + (b[0] - a[0]) * t, z_cut))
        return res
    return half(half(poly, lambda z: z >= lo, lo), lambda z: z <= hi, hi)


def extrados(phi):
    t = DIM["dome_t_base"] + (DIM["dome_t_top"] - DIM["dome_t_base"]) * phi / PHI_MAX
    return (R_I + t) * math.cos(phi), Z_S + (R_I + t) * math.sin(phi)


def section_polygon():
    """Half section of the rotunda: outer wall, seven step rings, dome curve, oculus, coffered side is smooth here."""
    p = [(R_O, 0.0), (R_O, DIM["wall_h"])]
    r, z = R_O - 0.6, DIM["wall_h"]
    p.append((r, z))
    for _ in range(DIM["step_rings"]):
        z += DIM["step_rise"]
        p.append((r, z))
        r -= DIM["step_run"]
        p.append((r, z))
    phis = [PHI_MAX * i / 90 for i in range(91)]
    p += [extrados(a) for a in phis if extrados(a)[0] < r and extrados(a)[1] > z]
    p.append((R_OC, extrados(PHI_MAX)[1]))
    p += [(R_I * math.cos(a), Z_S + R_I * math.sin(a)) for a in reversed(phis)]
    p.append((R_I, 0.0))
    return p


SECTION = section_polygon()
ZONES = (("wall", 0.0, Z_S), ("dome_low", Z_S, 33.0), ("dome_top", 33.0, 99.0))


def coffer_rings():
    """Five rings, each coffer about square: height follows the shrinking width of the sector towards the oculus."""
    edges = [math.radians(8.0)]
    for _ in range(DIM["coffer_rings"]):
        edges.append(edges[-1] + SECTOR * math.cos(edges[-1] + SECTOR * 0.45))
    return list(zip(edges, edges[1:]))


def coffer_cutter():
    size = (1.0, 0.86, 0.72, 0.58)
    depth = [DIM["coffer_depth"] * d for d in (0.3, 0.55, 0.8, 1.0)]
    v, f = [], []
    for pa, pb in coffer_rings():
        pc, hp = (pa + pb) / 2, (pb - pa) / 2 * 0.8
        for k in range(DIM["coffer_per_ring"]):
            az, ha = k * SECTOR, SECTOR / 2 * 0.8
            rings = [(size[0], -0.4)]
            for s, d in zip(size, depth):
                rings += [(s, d)] if s == size[0] else [(s, rings[-1][1]), (s, d)]
            base = len(v)
            for s, d in rings:
                rho = R_I + d
                for sa, sp in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                    a, ph = az + sa * ha * s, pc + sp * hp * s
                    v.append((rho * math.cos(ph) * math.cos(a), rho * math.cos(ph) * math.sin(a), Z_S + rho * math.sin(ph)))
            m = len(rings)
            f.append([base + 3, base + 2, base + 1, base])
            f.append([base + 4 * (m - 1) + j for j in range(4)])
            for i in range(m - 1):
                for j in range(4):
                    a, b = base + 4 * i + j, base + 4 * i + (j + 1) % 4
                    f.append((a, b, b + 4, a + 4))
    return mesh_object("coffers_cut", v, f)


EXEDRAE = ((0, "semi"), (45, "rect"), (90, "semi"), (135, "rect"), (-45, "rect"), (-90, "semi"), (-135, "rect"))


def niche_cutter():
    g = Geo()
    w, d, h = DIM["exedra_w"] / 2, DIM["exedra_d"], DIM["order_h"]
    for deg, kind in EXEDRAE:
        az = math.radians(deg)
        if kind == "rect":
            g.rbox("n", az, R_I - 1.0, R_I + d, -w, w, -0.5, h)
        else:
            g.rbox("n", az, R_I - 1.0, R_I + d - w + 0.01, -w, w, -0.5, h)
            c, s = math.cos(az), math.sin(az)
            g.cyl("n", (R_I + d - w) * c, (R_I + d - w) * s, -0.6, h + 0.1, w, w, 48)
    # hidden chambers in the wall above the openings (Moore 2002: cavities on different levels; sizes odhad)
    for deg in (0, 45, 90, 135, 180):
        g.rbox("n", math.radians(deg), R_I + 1.6, R_O - 1.4, -3.4, 3.4, 13.6, 17.6)
    return mesh_object("niches_cut", *g.parts["n"])


# -- building ---------------------------------------------------------------------------------------------------------
def column(g, mat, x, y, z0, shaft, d):
    r, k = d / 2, d / 1.5
    base, cap = DIM["col_base"] * k, DIM["col_cap"] * k
    g.box("marble", (x - r * 1.3, y - r * 1.3, z0), (x + r * 1.3, y + r * 1.3, z0 + base * 0.35))
    g.cyl("marble", x, y, z0 + base * 0.35, z0 + base, r * 1.2, r * 1.04)
    z = z0 + base
    g.cyl(mat, x, y, z, z + shaft, r, r * 0.86, 32)
    z += shaft
    g.cyl("marble", x, y, z, z + cap * 0.8, r * 0.88, r * 1.16)
    for row, h0, h1 in ((0, 0.04, 0.42), (1, 0.34, 0.72)):
        for i in range(8):
            a = (i + 0.5 * row) * math.pi / 4
            rr = r * (1.0 + 0.1 * row)
            g.cyl("marble", x + rr * math.cos(a), y + rr * math.sin(a), z + cap * h0, z + cap * h1, r * 0.2, r * 0.07, 6)
    for i in range(4):   # volutes at the corners of the abacus
        a = math.pi / 4 + i * math.pi / 2
        g.cyl("marble", x + r * 1.22 * math.cos(a), y + r * 1.22 * math.sin(a), z + cap * 0.68, z + cap * 0.84, r * 0.17, r * 0.17, 8)
    g.box("marble", (x - r * 1.42, y - r * 1.42, z + cap * 0.84), (x + r * 1.42, y + r * 1.42, z + cap))


def portico(g):
    w = DIM["portico_w"] / 2
    x_front = X_COL - 1.3
    for i in range(5):   # steps
        k = 5 - i
        g.box("travertine", (x_front - 0.55 * k, -w - 1.3, Z_P * i / 5), (X_WALL, w + 1.3, Z_P * (i + 1) / 5))
    ys = [-w + DIM["portico_w"] * i / 7 for i in range(8)]
    for y in ys:
        column(g, "granite_grey", X_COL, y, Z_P, DIM["col_shaft"], DIM["col_d"])
    # behind the front row: two groups of four (Wikipedia), in line with columns 1, 3, 6, 8
    for x in (X_COL + 4.8, X_COL + 9.6):
        for j, i in enumerate((0, 2, 5, 7)):
            column(g, "granite_pink" if j in (1, 2) else "granite_grey", x, ys[i], Z_P, DIM["col_shaft"], DIM["col_d"])
    h = w + 1.0
    g.box("marble", (x_front + 0.3, -h, Z_ENT), (X_WALL, h, Z_ENT + 1.05))             # architrave
    g.box("marble", (x_front + 0.42, -h + 0.12, Z_ENT + 1.05), (X_WALL, h - 0.12, Z_ENT + 2.25))  # frieze
    g.box("marble", (x_front - 0.1, -h - 0.45, Z_ENT + 2.25), (X_WALL, h + 0.45, Z_ROOF))  # cornice
    rake = [(-h - 0.45, Z_ROOF), (h + 0.45, Z_ROOF), (0, Z_APEX)]
    g.prism_x("marble", rake, x_front + 0.5, X_WALL)                                    # tympanum
    th = 0.85
    g.prism_x("marble", [(-h - 0.55, Z_ROOF), (-h - 0.55, Z_ROOF + th), (0, Z_APEX + th), (0, Z_APEX - 0.25)], x_front - 0.1, X_WALL)
    g.prism_x("marble", [(h + 0.55, Z_ROOF), (0, Z_APEX - 0.25), (0, Z_APEX + th), (h + 0.55, Z_ROOF + th)], x_front - 0.1, X_WALL)
    g.prism_x("lead", [(-h - 0.9, Z_ROOF + th - 0.05), (h + 0.9, Z_ROOF + th - 0.05), (0, Z_APEX + th + 0.2)], x_front + 0.15, X_WALL + 0.3)
    # block wall behind the columns stays on both sides; second, blind pediment above the roof (odhad)
    z = Z_APEX + th + 0.2
    g.prism_x("marble", [(-h, DIM["wall_h"] - 5.0), (h, DIM["wall_h"] - 5.0), (0, DIM["wall_h"] - 0.2)], X_WALL - 0.25, X_WALL + 0.1)
    g.box("bronze", (X_WALL + 1.3, -3.2, Z_P), (X_WALL + 1.75, 3.2, Z_P + DIM["door_h"]))   # bronze door leaves
    return z


def rotunda_details(g, cut):
    """Inner order, attic and outer bands. With the near half cut away only the far half is built."""
    a0, a1 = (0.0, math.pi) if cut else (-math.pi, math.pi)
    half = math.asin(DIM["exedra_w"] / 2 / R_I)
    h, e = DIM["order_h"], DIM["entab_h"]
    azs = [0, 45, 90, 135, 180] + ([] if cut else [-45, -90, -135])
    for deg in azs:   # piers between the openings, with an aedicula each
        if cut and deg == 180:
            continue
        pa, pb = math.radians(deg) + half, math.radians(deg + 45) - half
        g.sector("giallo", R_I - 0.12, R_I, 0.0, h, pa, pb)
        g.sector("pavon", R_I - 0.2, R_I - 0.1, 0.0, 0.9, pa, pb)
        for edge in (pa, pb - 1.2 / R_I):   # pilasters at the opening
            g.sector("pavon", R_I - 0.28, R_I, 0.9, h, edge, edge + 1.2 / R_I)
        mid = math.radians(deg + 22.5)
        g.rbox("pavon", mid, R_I - 1.05, R_I, -2.7, 2.7, 0.0, 2.1)
        for t in (-1.95, 1.95):
            c, s = math.cos(mid), math.sin(mid)
            x, y = (R_I - 0.75) * c - t * s, (R_I - 0.75) * s + t * c
            column(g, "porphyry", x, y, 2.1, 3.1, 0.55)
        g.rbox("marble", mid, R_I - 1.15, R_I, -2.65, 2.65, 5.8, 6.3)
        g.rprism("marble", mid, R_I - 1.15, R_I, [(-2.7, 6.3), (2.7, 6.3), (0, 7.5)])
    for deg, kind in EXEDRAE:   # two columns in the mouth of each opening
        if cut and not 0 < deg < 180:
            continue
        az = math.radians(deg)
        for t in (-1.9, 1.9):
            c, s = math.cos(az), math.sin(az)
            x, y = (R_I + 0.1) * c - t * s, (R_I + 0.1) * s + t * c
            column(g, "pavon", x, y, 0.0, h - 0.6 - DIM["col_cap"] * 0.6, 0.9)
    z = h
    g.sector("marble", R_I - 0.3, R_I, z, z + 0.9, a0, a1)
    g.sector("porphyry", R_I - 0.2, R_I, z + 0.9, z + 1.8, a0, a1)
    g.sector("marble", R_I - 0.75, R_I, z + 1.8, z + e, a0, a1)
    z += e
    top = Z_S - 0.4
    g.sector("attic", R_I - 0.06, R_I, z, top, a0, a1)
    for i in range(16 if not cut else 8):   # attic: blind windows with panels between
        a = (i + 0.5) * math.pi / 8 if cut else (i + 0.5) * math.pi / 8 - math.pi
        d = 1.2 / R_I
        g.sector("marble", R_I - 0.16, R_I - 0.05, z + 1.5, z + 6.2, a - d, a + d)
        g.sector("window", R_I - 0.19, R_I - 0.13, z + 1.9, z + 5.8, a - d * 0.72, a + d * 0.72)
        g.rprism("marble", a, R_I - 0.34, R_I - 0.05, [(-1.5, z + 6.2), (1.5, z + 6.2), (0, z + 7.0)])
        m = a + math.pi / 16
        if m < a1:
            g.sector("porphyry", R_I - 0.1, R_I - 0.05, z + 2.2, z + 5.6, m - 0.8 / R_I, m + 0.8 / R_I)
    g.sector("marble", R_I - 0.55, R_I, top, Z_S, a0, a1)
    lip = extrados(PHI_MAX)[1]
    g.sector("bronze", R_OC - 0.06, R_OC + 0.36, lip - 0.08, lip + 0.1, a0, a1)
    g.sector("bronze", R_OC - 0.06, R_OC + 0.02, lip - 1.2, lip, a0, a1)
    for z in (DIM["cornice_1"], DIM["cornice_2"], DIM["wall_h"] - 0.5):   # outer bands
        g.sector("marble", R_O - 0.02, R_O + 0.4, z, z + 0.6, a0, a1)


def build(cut):
    g = Geo()
    portico(g)
    rotunda_details(g, cut)
    solids = {}
    for name, lo, hi in ZONES:
        solids[name] = ring_solid(name, clip(SECTION, lo, hi))
    coffers, niches = coffer_cutter(), niche_cutter()
    for name in ("dome_low", "dome_top"):
        boolean(solids[name], coffers)
    boolean(solids["wall"], coffers)
    boolean(solids["wall"], niches)
    door = box_object("door_cut", (X_WALL - 1.0, -4.0, -0.5), (-R_I + 1.0, 4.0, 9.5))
    boolean(solids["wall"], door)
    # foundation ring, floor slab and, only in the section, the ground with the blue clay under it (Moore 2002)
    solids["found"] = ring_solid("found", [(R_FOUND_I, -DIM["found_h"]), (R_FOUND_O, -DIM["found_h"]), (R_FOUND_O, 0.0), (R_I + 0.01, 0.0),
                                           (R_I + 0.01, -0.6), (R_FOUND_I, -0.6)])
    solids["floor"] = disc_solid("floor", R_I + 0.01, -0.6, 0.01)
    solids["block"] = box_object("block", (X_WALL, -BLOCK_Y, 0.0), (-R_I + 2.0, BLOCK_Y, DIM["wall_h"]))
    drum = disc_solid("drum", R_O - 0.01, -1, 60)
    boolean(solids["block"], drum)
    boolean(solids["block"], door)
    cutters = [coffers, niches, door, drum]
    if cut:
        solids["under"] = disc_solid("under", R_FOUND_I, Z_EARTH, -0.6)
        solids["under2"] = ring_solid("under2", [(R_FOUND_I, Z_EARTH), (R_FOUND_O, Z_EARTH), (R_FOUND_O, -DIM["found_h"]), (R_FOUND_I, -DIM["found_h"])])
        solids["ground"] = box_object("ground", (-59, -27, Z_EARTH), (37, 34, 0))
        hole = disc_solid("hole", R_FOUND_O, Z_EARTH - 1, 1)
        boolean(solids["ground"], hole)
        near = box_object("near_cut", (X_CUT, -200, -50), (200, 0, 150))
        for o in solids.values():
            boolean(o, near)
        cutters += [hole, near]
    for o in cutters:
        bpy.data.objects.remove(o)
    return g, solids


def inscription():
    cu = bpy.data.curves.new("nápis", "FONT")
    cu.body = INSCRIPTION
    font = Path("C:/Windows/Fonts/times.ttf")
    if font.exists():
        cu.font = bpy.data.fonts.load(str(font))
    cu.align_x, cu.align_y = "CENTER", "CENTER"
    cu.size = 1.0
    cu.extrude = 0.03
    o = bpy.data.objects.new("nápis", cu)
    scene.collection.objects.link(o)
    bpy.context.view_layer.update()
    o.scale = (27.0 / o.dimensions.x,) * 3
    # text left to right along -y, seen from -x; its back sinks into the frieze
    o.rotation_mode = "QUATERNION"
    o.rotation_quaternion = Matrix(((0, 0, -1), (-1, 0, 0), (0, 1, 0))).to_quaternion()
    o.location = (X_COL - 1.3 + 0.41, 0, Z_ENT + 1.65)
    return o


# -- plain model for the library ------------------------------------------------------------------------------------------
def export_glb():
    g, _ = build(cut=False)
    for mat, (v, f) in g.parts.items():
        mesh_object(mat, v, f)
    inscription()
    bpy.ops.object.select_all(action="DESELECT")
    bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", export_apply=True)
    print("bbox target", DIM["length"], DIM["width"], DIM["height"])


# -- materials ---------------------------------------------------------------------------------------------------------
def srgb(hexs):
    c = [int(hexs[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return tuple((x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4) for x in c) + (1.0,)


def new_mat(name, rough=0.7, metal=0.0):
    m = bpy.data.materials.new(name)
    if not m.node_tree:
        m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    return m, m.node_tree, bsdf


def coords(tree):
    n = tree.nodes.new("ShaderNodeTexCoord")
    return n.outputs["Object"]


def noisy(name, a, b, scale=1.2, rough=0.7, metal=0.0, detail=6.0, lo=0.35, hi=0.65):
    m, t, bsdf = new_mat(name, rough, metal)
    tex = t.nodes.new("ShaderNodeTexNoise")
    tex.inputs["Scale"].default_value, tex.inputs["Detail"].default_value = scale, detail
    t.links.new(coords(t), tex.inputs["Vector"])
    ramp = t.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position, ramp.color_ramp.elements[1].position = lo, hi
    ramp.color_ramp.elements[0].color, ramp.color_ramp.elements[1].color = srgb(a), srgb(b)
    t.links.new(tex.outputs[0], ramp.inputs[0])
    t.links.new(ramp.outputs[0], bsdf.inputs["Base Color"])
    return m


def aggregate(name, mortar, rocks, scale, rough=0.92):
    """Section through concrete: broken rock in mortar. The grain is drawn larger than life so it reads at this scale."""
    m, t, bsdf = new_mat(name, rough)
    co = coords(t)
    warp = t.nodes.new("ShaderNodeTexNoise")
    warp.inputs["Scale"].default_value, warp.inputs["Detail"].default_value = 2.2, 3.0
    t.links.new(co, warp.inputs["Vector"])
    mix = t.nodes.new("ShaderNodeVectorMath")
    mix.operation = "ADD"
    t.links.new(co, mix.inputs[0])
    scale_w = t.nodes.new("ShaderNodeVectorMath")
    scale_w.operation = "SCALE"
    scale_w.inputs[3].default_value = 0.12
    t.links.new(warp.outputs["Color"], scale_w.inputs[0])
    t.links.new(scale_w.outputs[0], mix.inputs[1])
    vor = t.nodes.new("ShaderNodeTexVoronoi")
    vor.inputs["Scale"].default_value = scale
    t.links.new(mix.outputs[0], vor.inputs["Vector"])
    ramp = t.nodes.new("ShaderNodeValToRGB")
    cr = ramp.color_ramp
    cr.interpolation = "CONSTANT"
    while len(cr.elements) < len(rocks):
        cr.elements.new(0.5)
    for i, c in enumerate(rocks):
        cr.elements[i].position, cr.elements[i].color = i / len(rocks), srgb(c)
    sep = t.nodes.new("ShaderNodeSeparateColor")
    t.links.new(vor.outputs["Color"], sep.inputs[0])
    t.links.new(sep.outputs[0], ramp.inputs[0])
    # distance to the cell edge: mortar between the stones
    edge = t.nodes.new("ShaderNodeTexVoronoi")
    edge.feature = "DISTANCE_TO_EDGE"
    edge.inputs["Scale"].default_value = scale
    t.links.new(mix.outputs[0], edge.inputs["Vector"])
    mask = t.nodes.new("ShaderNodeValToRGB")
    mask.color_ramp.elements[0].position, mask.color_ramp.elements[1].position = 0.05, 0.085
    t.links.new(edge.outputs["Distance"], mask.inputs[0])
    mixc = t.nodes.new("ShaderNodeMix")
    mixc.data_type = "RGBA"
    mixc.inputs["A"].default_value = srgb(mortar)
    t.links.new(mask.outputs[0], mixc.inputs["Factor"])
    t.links.new(ramp.outputs[0], mixc.inputs["B"])
    t.links.new(mixc.outputs["Result"], bsdf.inputs["Base Color"])
    # the section is what the picture explains: it stays readable while the room around it goes dim
    t.links.new(mixc.outputs["Result"], bsdf.inputs["Emission Color"])
    bsdf.inputs["Emission Strength"].default_value = 0.26
    return m


def soil():
    """Fill over blue clay (Moore 2002), by height."""
    m, t, bsdf = new_mat("soil", 0.95)
    co = coords(t)
    sep = t.nodes.new("ShaderNodeSeparateXYZ")
    t.links.new(co, sep.inputs[0])
    noise = t.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value, noise.inputs["Detail"].default_value = 1.4, 8.0
    t.links.new(co, noise.inputs["Vector"])
    add = t.nodes.new("ShaderNodeMath")
    add.operation = "ADD"
    t.links.new(sep.outputs["Z"], add.inputs[0])
    wob = t.nodes.new("ShaderNodeMath")
    wob.operation = "MULTIPLY"
    wob.inputs[1].default_value = 1.6
    t.links.new(noise.outputs[0], wob.inputs[0])
    t.links.new(wob.outputs[0], add.inputs[1])
    ramp = t.nodes.new("ShaderNodeMapRange")
    ramp.inputs["From Min"].default_value, ramp.inputs["From Max"].default_value = -8.0, 0.8
    t.links.new(add.outputs[0], ramp.inputs["Value"])
    cr = t.nodes.new("ShaderNodeValToRGB").color_ramp
    node = t.nodes[-1]
    cr.elements[0].position, cr.elements[0].color = 0.3, srgb("#39454f")
    cr.elements[1].position, cr.elements[1].color = 0.42, srgb("#44382d")
    e = cr.elements.new(0.92)
    e.color = srgb("#54463a")
    t.links.new(ramp.outputs[0], node.inputs[0])
    t.links.new(node.outputs[0], bsdf.inputs["Base Color"])
    t.links.new(node.outputs[0], bsdf.inputs["Emission Color"])
    bsdf.inputs["Emission Strength"].default_value = 0.3
    return m


def floor_mat():
    """The real pattern: a grid of squares holding circles and squares in porphyry, giallo antico, pavonazzetto and granite."""
    size = 4096
    span = 2 * (R_I + 1)
    ys, xs = np.mgrid[0:size, 0:size]
    x = (xs + 0.5) / size * span - span / 2
    y = (ys + 0.5) / size * span - span / 2
    mod = DIM["module"]
    i, j = np.floor(x / mod + 0.5), np.floor(y / mod + 0.5)
    u, v = x - i * mod, y - j * mod
    even = (i + j) % 2 == 0
    col = lambda h: np.array([int(h[k:k + 2], 16) / 255 for k in (1, 3, 5)])
    pav, giallo, porf, gran, serp = col("#d9d2c8"), col("#c79a55"), col("#6e2a2b"), col("#6e7072"), col("#3e5147")
    img = np.zeros((size, size, 3))
    img[even] = giallo
    img[~even] = gran
    circle = even & (np.hypot(u, v) < mod * 0.4)
    img[circle] = porf
    inner = ~even & (np.maximum(np.abs(u), np.abs(v)) < mod * 0.33)
    img[inner] = pav
    inner2 = ~even & (np.maximum(np.abs(u), np.abs(v)) < mod * 0.23)
    tone = ((i * 2 + j) % 4 < 2)[..., None]
    img[inner2] = (tone * porf + (1 - tone) * serp)[inner2]
    band = np.maximum(np.abs(u), np.abs(v)) > mod * 0.47
    img[band] = pav
    rng = np.random.default_rng(7)
    img *= 1 + (rng.random((64, 64))[(i.astype(int) + 32) % 64, (j.astype(int) + 32) % 64] - 0.5)[..., None] * 0.14
    img *= 1 + (rng.random(img.shape[:2]) - 0.5)[..., None] * 0.05
    px = np.ones((size, size, 4), dtype=np.float32)
    px[..., :3] = np.clip(img, 0, 1)
    im = bpy.data.images.new("floor", size, size, alpha=False)
    im.pixels.foreach_set(px.ravel())
    im.pack()
    m, t, bsdf = new_mat("floor_tex", 0.3)
    tex = t.nodes.new("ShaderNodeTexImage")
    tex.image = im
    mp = t.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1 / span, 1 / span, 1)
    mp.inputs["Location"].default_value = (0.5, 0.5, 0)
    t.links.new(coords(t), mp.inputs["Vector"])
    t.links.new(mp.outputs[0], tex.inputs["Vector"])
    t.links.new(tex.outputs[0], bsdf.inputs["Base Color"])
    return m


def material_library():
    mats = {
        "marble": noisy("marble", "#d8d3c8", "#efece4", 0.9, 0.6),
        "travertine": noisy("travertine", "#b9ad97", "#d4cab6", 2.0, 0.8),
        "attic": noisy("attic", "#cbbfa8", "#ddd3bf", 1.0, 0.5),
        "giallo": noisy("giallo", "#b2925f", "#c9ab7a", 1.6, 0.35),
        "pavon": noisy("pavon", "#b9aeb0", "#e6e1da", 2.4, 0.3),
        "porphyry": noisy("porphyry", "#54201f", "#7c3331", 7.0, 0.3),
        "window": noisy("window", "#191a1f", "#25262c", 3.0, 0.8),
        "granite_grey": noisy("granite_grey", "#5f6264", "#898b8b", 14.0, 0.4),
        "granite_pink": noisy("granite_pink", "#8d6a60", "#b08b7f", 14.0, 0.4),
        "dome": noisy("dome", "#b5ad9d", "#c3bbab", 0.35, 0.85),
        "lead": noisy("lead", "#6b7175", "#777d81", 0.8, 0.5, 0.3),
        "stepring": noisy("stepring", "#a9a59b", "#c0bcb2", 1.5, 0.9),
        "brick": noisy("brick", "#8d5238", "#a86a4a", 3.5, 0.9),
        "bronze": noisy("bronze", "#6b5230", "#9c7a44", 5.0, 0.35, 0.9),
        "chamber": noisy("chamber", "#2a2622", "#35302a", 3.0, 0.95),
        "paving": noisy("paving", "#5a5852", "#6c6962", 9.0, 0.85),
        "sec_found": aggregate("sec_found", "#b5ab9a", ("#d8cfb9", "#c9bda2", "#e2dac6", "#bfb39a"), 2.6),
        "sec_wall": aggregate("sec_wall", "#a89a88", ("#d0c5ae", "#8e7c68", "#a4563c", "#b9ac94", "#7f6d5b"), 2.6),
        "sec_dome_low": aggregate("sec_dome_low", "#b0a18f", ("#a2523a", "#b6654a", "#8d4630", "#c07658"), 2.6),
        "sec_dome_top": aggregate("sec_dome_top", "#c4bbab", ("#ded8cb", "#8f8778", "#cfc8b9", "#a89f8f", "#ebe6da"), 3.2),
        "soil": soil(),
        "floor": floor_mat(),
        "figure": noisy("figure", "#2c3038", "#3b3f48", 5.0, 0.9),
    }
    return mats


def paint(o, rule, mats):
    o.data.materials.clear()
    idx = {}
    for p in o.data.polygons:
        name = rule(p.center, p.normal)
        if name not in idx:
            idx[name] = len(idx)
            o.data.materials.append(mats[name])
        p.material_index = idx[name]


def is_cap(c, n):
    return abs(n.y) > 0.99 and abs(c.y) < 0.02


def smooth(o, deg=28):
    bpy.ops.object.select_all(action="DESELECT")
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.shade_smooth_by_angle(angle=math.radians(deg))
    o.select_set(False)


# -- render -------------------------------------------------------------------------------------------------------------
def figures():
    """The 1.72 m control figure from engine/assets, for scale."""
    glb = Path(__file__).resolve().parents[2] / "engine" / "assets" / "postava-172.glb"
    spots = [(-7.2, 9.5), (-5.8, 10.3), (3.0, 14.0), (6.5, 6.0), (-12.5, 4.5), (11.0, 12.0), (X_COL - 3.7, -9.0), (X_COL - 4.8, 6.0), (X_COL - 5.2, -13.0)]
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(glb))
    imported = [o for o in bpy.data.objects if o not in before]
    src = next(o for o in imported if o.type == "MESH")
    src.parent = None
    src.matrix_world = src.matrix_world.copy()
    res = []
    for k, (x, y) in enumerate(spots):
        o = src.copy()
        o.data = src.data
        scene.collection.objects.link(o)
        lo = min((src.matrix_world @ Vector(b)).z for b in src.bound_box)
        o.location = (x, y, o.location.z - lo + 0.012)
        o.rotation_mode = "XYZ"
        o.rotation_euler.z += k * 1.3
        res.append(o)
    for o in imported:
        bpy.data.objects.remove(o)
    return res


def sun_vector():
    return Vector((-0.38, -0.22, 1.0)).normalized()


def render():
    g, solids = build(cut=True)
    mats = material_library()
    keep_details = {}
    for name, (v, f) in g.parts.items():
        o = mesh_object(name, v, f)
        o.data.materials.append(mats[name])
        keep_details[name] = o
    ins = inscription()
    ins.data.materials.append(mats["bronze"])

    def rule_wall(c, n):
        r = math.hypot(c.x, c.y)
        if is_cap(c, n):
            return "sec_wall"
        if r > R_O - 0.05:
            return "brick"
        if 13.5 < c.z < 17.7 and r > R_I + 1.0:
            return "chamber"
        if c.z > Z_S - 0.5:
            return "dome"
        return "giallo" if c.z < DIM["order_h"] + 0.1 else "attic"

    def rule_dome(cap):
        def rule(c, n):
            r = math.hypot(c.x, c.y)
            rho = (Vector((c.x, c.y, c.z - Z_S))).length
            if is_cap(c, n):
                return cap
            if rho < R_I + DIM["coffer_depth"] + 0.4 and n.dot(Vector((c.x, c.y, c.z - Z_S))) < 0.5 * rho:
                return "dome"
            if r > R_O - 0.05:
                return "brick"
            return "stepring" if c.z < 36.2 else "lead"
        return rule

    def rule_block(c, n):
        if is_cap(c, n):
            return "sec_wall"
        if n.z > 0.9 and c.z > 30:
            return "lead"
        if abs(c.y) < 4.01 and c.z < 9.51:
            return "travertine"
        return "brick" if c.z > Z_ROOF else "travertine"

    def rule_found(c, n):
        if is_cap(c, n):
            return "sec_found"
        return "pavon" if c.z > -0.01 else "soil"

    def rule_ground(c, n):
        return "paving" if n.z > 0.9 and c.z > -0.01 else "soil"

    def rule_floor(c, n):
        if is_cap(c, n):
            return "sec_found"
        return "floor" if n.z > 0.9 else "soil"

    paint(solids["wall"], rule_wall, mats)
    paint(solids["dome_low"], rule_dome("sec_dome_low"), mats)
    paint(solids["dome_top"], rule_dome("sec_dome_top"), mats)
    paint(solids["block"], rule_block, mats)
    paint(solids["found"], rule_found, mats)
    paint(solids["floor"], rule_floor, mats)
    for name in ("under", "under2"):
        paint(solids[name], lambda c, n: "soil", mats)
    paint(solids["ground"], rule_ground, mats)
    for o in list(solids.values()):
        smooth(o)
    for name in ("granite_grey", "granite_pink", "marble", "giallo", "pavon", "porphyry"):
        if name in keep_details:
            smooth(keep_details[name], 40)

    people = figures()
    for o in people:
        o.data.materials.clear()
        o.data.materials.append(mats["figure"])

    # the removed half only stops the sun, so that it comes in through the oculus alone
    m = len(SECTION)
    n = N // 2
    v = []
    for i in range(n + 1):
        a = -math.pi * i / n
        v += [(r * math.cos(a), r * math.sin(a), z) for r, z in SECTION]
    f = [(i * m + j, i * m + (j + 1) % m, (i + 1) * m + (j + 1) % m, (i + 1) * m + j) for i in range(n) for j in range(m)]
    caster = mesh_object("caster", v, f)
    caster.location.y = -0.05
    caster.visible_camera = False
    caster.visible_diffuse = False
    caster.visible_glossy = False
    caster.visible_transmission = False
    caster.visible_volume_scatter = False

    real = bpy.data.collections.new("real")
    scene.collection.children.link(real)
    for o in list(scene.collection.objects):
        if o is not caster and o.type in ("MESH", "FONT"):
            real.objects.link(o)

    sv = sun_vector()
    # light shaft: only the sun lights it, along the path of the oculus
    lip = extrados(PHI_MAX)[1]
    length = 44.0 / sv.z
    v, f = [], []
    k = 48
    top = Vector((0, 0, lip))
    for t in (0.0, length):
        for i in range(k):
            a = 2 * math.pi * i / k
            pt = top - sv * t + Vector((R_OC * math.cos(a), R_OC * math.sin(a), 0))
            v.append(tuple(pt))
    f = [list(range(k - 1, -1, -1)), list(range(k, 2 * k))] + [(i, (i + 1) % k, k + (i + 1) % k, k + i) for i in range(k)]
    shaft = mesh_object("shaft", v, f)
    sm = bpy.data.materials.new("shaft")
    sm.use_nodes = True
    t = sm.node_tree
    t.nodes.clear()
    o_ = t.nodes.new("ShaderNodeOutputMaterial")
    vol = t.nodes.new("ShaderNodeVolumeScatter")
    vol.inputs["Color"].default_value = (1.0, 0.93, 0.8, 1)
    vol.inputs["Density"].default_value = 0.012
    vol.inputs["Anisotropy"].default_value = 0.3
    # mostly a soft glow: thick enough air to show the shaft by scattering alone would dim the patch on the floor
    glow_v = t.nodes.new("ShaderNodeEmission")
    glow_v.inputs["Color"].default_value = (1.0, 0.9, 0.72, 1)
    glow_v.inputs["Strength"].default_value = 0.034
    both = t.nodes.new("ShaderNodeAddShader")
    t.links.new(vol.outputs[0], both.inputs[0])
    t.links.new(glow_v.outputs[0], both.inputs[1])
    t.links.new(both.outputs[0], o_.inputs["Volume"])
    shaft.data.materials.append(sm)

    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    scene.collection.objects.link(sun)
    sun.data.energy, sun.data.angle = 8.5, math.radians(0.6)
    sun.data.color = (1.0, 0.93, 0.82)
    sun.rotation_mode = "QUATERNION"
    sun.rotation_quaternion = sv.to_track_quat("Z", "Y")

    fill = bpy.data.objects.new("fill", bpy.data.lights.new("fill", "SUN"))
    scene.collection.objects.link(fill)
    fill.data.energy, fill.data.angle = 0.3, math.radians(30)
    fill.data.color = (0.92, 0.96, 1.0)
    a, e = math.radians(CAM_AZ - 18), math.radians(32)
    fill.rotation_mode = "QUATERNION"
    fill.rotation_quaternion = Vector((math.cos(a) * math.cos(e), math.sin(a) * math.cos(e), math.sin(e))).to_track_quat("Z", "Y")
    fill.light_linking.blocker_collection = real
    fill.light_linking.receiver_collection = real

    # warm glow of the room: daylight from the oculus bounced around, stronger than one bounce of the patch would give
    glow = bpy.data.objects.new("glow", bpy.data.lights.new("glow", "POINT"))
    scene.collection.objects.link(glow)
    glow.location = (2.0, 4.0, 15.0)
    glow.data.energy, glow.data.shadow_soft_size = 2300.0, 7.0
    glow.data.color = (1.0, 0.8, 0.58)
    glow.light_linking.receiver_collection = real
    glow.light_linking.blocker_collection = real

    world = bpy.data.worlds.new("w")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.62, 0.7, 0.85, 1)
    bg.inputs[1].default_value = 0.55

    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = CAM_SCALE
    cam.data.clip_end = 2000
    a, e = math.radians(CAM_AZ), math.radians(CAM_EL)
    d = Vector((math.cos(a) * math.cos(e), math.sin(a) * math.cos(e), math.sin(e)))
    target = Vector((0, 0, CAM_DZ)) + Vector((d.y, -d.x, 0)).normalized() * CAM_DX
    cam.location = target + d * 400
    cam.rotation_mode = "QUATERNION"
    cam.rotation_quaternion = (-d).to_track_quat("-Z", "Y")

    r = scene.render
    r.engine = "CYCLES"
    r.resolution_x, r.resolution_y = RES
    r.film_transparent = True
    r.image_settings.file_format = "PNG"
    r.image_settings.color_mode = "RGBA"
    c = scene.cycles
    c.samples, c.use_denoising = SAMPLES, True
    c.denoiser = "OPENIMAGEDENOISE"
    c.max_bounces = 6
    c.volume_bounces = 0
    c.volume_step_rate = 2.0
    if os.environ.get("GRAFIK_RENDER_CPU") != "1":
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "OPTIX"
        prefs.get_devices()
        gpus = [d_ for d_ in prefs.devices if d_.type == "OPTIX"]
        for d_ in prefs.devices:
            d_.use = d_ in gpus
        c.device = "GPU" if gpus else "CPU"
    scene.view_settings.view_transform = "AgX"
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass

    base = Path(RENDER)
    base.mkdir(parents=True, exist_ok=True)
    r.filepath = str(base / "rez.png")
    bpy.context.view_layer.update()

    def uv(p):
        q = world_to_camera_view(scene, cam, Vector(p))
        return [round(q.x * RES[0], 1), round((1 - q.y) * RES[1], 1)]

    at = lambda phi, rho: (rho * math.cos(math.radians(phi)), 0, Z_S + rho * math.sin(math.radians(phi)))
    mid = lambda deg: R_I + (DIM["dome_t_base"] + (DIM["dome_t_top"] - DIM["dome_t_base"]) * math.radians(deg) / PHI_MAX) / 2 + 0.3
    points = {
        "okulus": (R_OC, 0, extrados(PHI_MAX)[1]),
        "vrchol_koule": (0, 0, 2 * Z_S),
        "kazeta_vlevo": tuple(Vector((0, 0, Z_S)) + R_I * Vector((math.cos(math.radians(39)) * math.cos(math.radians(141.4)), math.cos(math.radians(39)) * math.sin(math.radians(141.4)), math.sin(math.radians(39))))),
        "vrchol_rez": at(62, mid(62)),
        "stred_rez": at(22, mid(22)),
        "stupne": (R_O - 3.0, 0, DIM["wall_h"] + 1.5),
        "stena_rez": (R_I + 3.1, 0, 19.0),
        "komora": (R_I + 3.1, 0, 15.6),
        "exedra": (R_I + 1.0, 0, 5.0),
        "zaklad": (R_FOUND_I + 3.6, 0, -2.4),
        "jil": (R_FOUND_I + 3.6, 0, -6.8),
        "podlaha": (6.0, 8.0, 0),
        "svetlo": (16.3 * 0.55, 9.5 * 0.55, 44 * 0.45),
        "sloup": (X_COL, -DIM["portico_w"] / 2 + 2 * DIM["portico_w"] / 7, Z_P + 6.0),
        "napis": (X_COL - 0.9, 8.0, Z_ENT + 1.65),
        "stit": (X_COL - 0.5, 0, Z_ROOF + 2.6),
        "dvere": (X_WALL + 1.3, 0, Z_P + 3.0),
        "stred_koule": (0, 0, Z_S),
        "podlaha_stred": (0, 0, 0),
        "pata_l": (-R_I, 0, Z_S),
        "pata_p": (R_I, 0, Z_S),
    }
    circle = [uv((R_I * math.cos(i * math.pi / 180), 0, Z_S + R_I * math.sin(i * math.pi / 180))) for i in range(360)]
    (base / "body.json").write_text(json.dumps({
        "res": RES, "sun": list(sv), "points": {k_: uv(p) for k_, p in points.items()}, "kruh": circle,
        "m_px": round(RES[0] / CAM_SCALE, 3), "dim": {k_: v_ for k_, v_ in DIM.items()}}, ensure_ascii=False, indent=1), encoding="utf-8")
    bpy.ops.render.render(write_still=True)
    print("rendered", r.filepath)


if RENDER:
    render()
else:
    export_glb()
