# Model from a parts description (JSON, engine/parts_spec.py), no generated code runs. Free:
#   blender -b --factory-startup -P engine/blender/lod_parts.py -- out.glb spec.json
# Every part is a named object, so a later render can work object by object. Writes <out>.dily.json next to the GLB:
# name, material and bounding box of each part, and the parts that touch nothing. Geometry comes from
# scripts/3d/lod_pantheon.py, generalised to ellipses; the description is checked before it gets here
# (engine.parts_spec.validate). engine/blender/render_parts.py imports build() from this file.
import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils.bvhtree import BVHTree

N = 360
ARC_TABLE = 720
COLORS = {"travertin": "#d9cfbc", "tuf": "#a89a80", "cihla": "#a5573d", "beton": "#9a958c", "mramor": "#e6e2da", "zula": "#7d7f83",
          "bronz": "#6f5a35", "strecha": "#8f8778", "pisek": "#c9b38a", "kamen": "#b5ac9c"}


def material(name):
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
        if not mat.node_tree:
            mat.use_nodes = True
        h = COLORS.get(name, "#b5ac9c").lstrip("#")
        rgb = [(int(h[i:i + 2], 16) / 255) ** 2.2 for i in (0, 2, 4)]
        mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (*rgb, 1)
    return mat


def mesh_object(name, verts, faces, mat=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    me.update()
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    if mat:
        o.data.materials.append(material(mat))
    return o


def boolean(o, cutter):
    m = o.modifiers.new("cut", "BOOLEAN")
    m.operation, m.object, m.solver = "DIFFERENCE", cutter, "MANIFOLD"
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.modifier_apply(modifier=m.name)


def rotated(az):
    c, s = math.cos(math.radians(az)), math.sin(math.radians(az))
    return lambda x, y, z: (x * c - y * s, x * s + y * c, z)


class Geo:
    """Loose closed pieces merged into one mesh, each with its material: columns, porticoes, cutters."""

    def __init__(self, mat=None, place=None):
        self.v, self.f, self.tags = [], [], []
        self.mat = mat
        self.place = place or (lambda x, y, z: (x, y, z))

    def add(self, verts, faces):
        base = len(self.v)
        self.v.extend(self.place(*v) for v in verts)
        self.f.extend([i + base for i in f] for f in faces)
        self.tags.extend([self.mat] * len(faces))

    def box(self, lo, hi):
        (a, b, c), (d, e, f) = lo, hi
        self.add([(a, b, c), (d, b, c), (d, e, c), (a, e, c), (a, b, f), (d, b, f), (d, e, f), (a, e, f)],
                 [(3, 2, 1, 0), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)])

    def cyl(self, x, y, z0, z1, r0, r1, n=24):
        v = [(x + r * math.cos(2 * math.pi * i / n), y + r * math.sin(2 * math.pi * i / n), z) for z, r in ((z0, r0), (z1, r1)) for i in range(n)]
        f = [list(range(n - 1, -1, -1)), list(range(n, 2 * n))] + [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
        self.add(v, f)

    def prism_x(self, pts, x0, x1):
        n = len(pts)
        v = [(x0, y, z) for y, z in pts] + [(x1, y, z) for y, z in pts]
        f = [list(range(n - 1, -1, -1)), list(range(n, 2 * n))] + [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
        self.add(v, f)

    def object(self, name):
        o = mesh_object(name, self.v, self.f)
        slots = {}
        for mat in dict.fromkeys(self.tags):
            slots[mat] = len(slots)
            o.data.materials.append(material(mat))
        for poly, tag in zip(o.data.polygons, self.tags):
            poly.material_index = slots[tag]
        return o


def ring_solid(name, poly, axes, mat, n=N):
    """Closed polygon (offset, z) swept along the ellipse; no vertex on the azimuth 0 plane, a section stays clean."""
    a, b = axes
    m = len(poly)
    v = []
    for i in range(n):
        t = (i + 0.5) * 2 * math.pi / n
        v += [((a + d) * math.cos(t), (b + d) * math.sin(t), z) for d, z in poly]
    f = [(i * m + j, i * m + (j + 1) % m, ((i + 1) % n) * m + (j + 1) % m, ((i + 1) % n) * m + j) for i in range(n) for j in range(m)]
    return mesh_object(name, v, f, mat)


def disc_solid(name, axes, z0, z1, mat, n=N):
    a, b = axes
    v = [(a * math.cos((i + 0.5) * 2 * math.pi / n), b * math.sin((i + 0.5) * 2 * math.pi / n), z) for z in (z0, z1) for i in range(n)]
    f = [list(range(n - 1, -1, -1)), list(range(n, 2 * n))] + [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
    return mesh_object(name, v, f, mat)


def along_ellipse(axes, offset, count, phase=0.0):
    """count azimuth parameters t at equal arc length; a circle stays equal in angle."""
    a, b = axes[0] + offset, axes[1] + offset
    table, s = [0.0], 0.0
    for i in range(ARC_TABLE):
        t0, t1 = 2 * math.pi * i / ARC_TABLE, 2 * math.pi * (i + 1) / ARC_TABLE
        s += math.hypot(a * (math.cos(t1) - math.cos(t0)), b * (math.sin(t1) - math.sin(t0)))
        table.append(s)
    out, j = [], 0
    for k in range(count):
        want = (k + phase) % count * s / count
        j = 0 if want < table[j] else j
        while table[j + 1] < want:
            j += 1
        out.append(2 * math.pi * (j + (want - table[j]) / max(1e-9, table[j + 1] - table[j])) / ARC_TABLE)
    return sorted(out)


def excluded(t, intervals):
    deg = math.degrees(t)
    return any(lo <= deg + k * 360 <= hi for lo, hi in intervals for k in (-1, 0, 1))


def arch_outline(width, z0, height, shape):
    w = width / 2
    if shape == "obdelnik" or height <= w:
        return [(-w, z0), (w, z0), (w, z0 + height), (-w, z0 + height)]
    spring = z0 + height - w
    arc = [(w * math.cos(math.pi * i / 14), spring + w * math.sin(math.pi * i / 14)) for i in range(15)]
    return [(-w, z0), (w, z0)] + arc


def arcade_cutter(name, p):
    a, b = p["osy"]
    d0, d1 = p["odsazeni"]
    g = Geo()
    outline = arch_outline(p["sirka"], p["z0"], p["vyska"], p["tvar"])
    m = len(outline)
    for t in along_ellipse(p["osy"], d1, p["pocet"], p["faze"]):
        if excluded(t, p["vyjma"]):
            continue
        ca, cb = a + d1, b + d1
        nx, ny = cb * math.cos(t), ca * math.sin(t)
        k = math.hypot(nx, ny)
        nx, ny = nx / k, ny / k
        tx, ty = -ny, nx
        px, py = ca * math.cos(t), cb * math.sin(t)
        depth = d1 - d0
        v = []
        for off in (depth + 0.5, -0.5):     # cut from inside the wall to past both faces
            for u, z in outline:
                v.append((px - nx * off + tx * u, py - ny * off + ty * u, z))
        f = [list(range(m - 1, -1, -1)), list(range(m, 2 * m))] + [(i, (i + 1) % m, m + (i + 1) % m, m + i) for i in range(m)]
        g.add(v, f)
    return mesh_object(f"{name}_cut", g.v, g.f)


def column(g, x, y, z0, shaft, d, order):
    r = d / 2
    base, cap = d * 0.55, d * (1.05 if order == "korintsky" else 0.45)
    g.box((x - r * 1.3, y - r * 1.3, z0), (x + r * 1.3, y + r * 1.3, z0 + base * 0.35))
    g.cyl(x, y, z0 + base * 0.35, z0 + base, r * 1.2, r * 1.04)
    z = z0 + base
    g.cyl(x, y, z, z + shaft, r, r * 0.86, 32)
    z += shaft
    g.cyl(x, y, z, z + cap * 0.8, r * 0.88, r * 1.16)
    if order == "korintsky":
        for row, h0, h1 in ((0, 0.04, 0.42), (1, 0.34, 0.72)):
            for i in range(8):
                a = (i + 0.5 * row) * math.pi / 4
                rr = r * (1.0 + 0.1 * row)
                g.cyl(x + rr * math.cos(a), y + rr * math.sin(a), z + cap * h0, z + cap * h1, r * 0.2, r * 0.07, 6)
    g.box((x - r * 1.42, y - r * 1.42, z + cap * 0.84), (x + r * 1.42, y + r * 1.42, z + cap))


def columns(name, p, kept):
    g = Geo(p["material"])
    if "od" in p:
        (x0, y0), (x1, y1) = p["od"], p["to"]
        n = max(1, p["pocet"] - 1)
        spots = [(x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n) for i in range(p["pocet"])]
    else:
        a, b = p["osy"][0] + p["odsazeni"], p["osy"][1] + p["odsazeni"]
        spots = [(a * math.cos(t), b * math.sin(t)) for t in along_ellipse(p["osy"], p["odsazeni"], p["pocet"], p["faze"]) if not excluded(t, p["vyjma"])]
    for x, y in spots:
        if kept(x, y):
            column(g, x, y, p["z0"], p["drik"], p["d"], p["rad"])
    return g.object(name) if g.v else None


def portico(name, p):
    """Temple front facing -x at azimuth 0: steps, columns, entablature, pediment, roof, up to the wall at x_zed."""
    g = Geo(p["material"], rotated(p["azimut"]))
    w = p["sirka"] / 2
    x_col, x_wall, z_p = p["x_sloupy"], p["x_zed"], p["z0"]
    x_front = x_col - p["d"] * 0.9
    steps = p["schodu"]
    ys = [-w + p["sirka"] * i / (p["pocet"] - 1) for i in range(p["pocet"])]
    for y in ys:
        column(g, x_col, y, z_p, p["drik"], p["d"], "korintsky")
    for offset in p["zadni_rady"]:
        for i in p["zadni_indexy"] or range(p["pocet"]):
            if i < len(ys):
                column(g, x_col + offset, ys[i], z_p, p["drik"], p["d"], "korintsky")
    g.mat = "travertin"
    if z_p > 0:
        for i in range(steps):
            g.box((x_front - 0.5 * (steps - i), -w - p["d"], z_p * i / steps), (x_wall, w + p["d"], z_p * (i + 1) / steps))
    g.mat = "mramor"
    z_ent = z_p + p["drik"] + p["d"] * 1.6
    h = w + p["d"] * 0.7
    g.box((x_front + 0.3, -h, z_ent), (x_wall, h, z_ent + p["d"] * 0.7))
    g.box((x_front + 0.42, -h + 0.12, z_ent + p["d"] * 0.7), (x_wall, h - 0.12, z_ent + p["d"] * 1.5))
    z_roof = z_ent + p["d"] * 2.0
    g.box((x_front - 0.1, -h - 0.45, z_ent + p["d"] * 1.5), (x_wall, h + 0.45, z_roof))
    g.prism_x([(-h - 0.45, z_roof), (h + 0.45, z_roof), (0, z_roof + p["stit"])], x_front + 0.5, x_wall)
    g.mat = "strecha"
    g.prism_x([(-h - 0.9, z_roof + 0.05), (h + 0.9, z_roof + 0.05), (0, z_roof + p["stit"] + 0.25)], x_front + 0.15, x_wall + 0.3)
    return g.object(name)


def dome(name, p):
    """Hemisphere (optionally stretched in z) with thickness falling from base to top, oculus and coffers."""
    r_i, (t0, t1), r_oc, z_s, k = p["polomer"], p["tloustka"], max(p["okulus"], 0.02), p["z_patka"], p["vyska_ku_polomeru"]
    phi_max = math.acos(min(0.999, r_oc / r_i))
    phis = [phi_max * i / 90 for i in range(91)]

    def outer(ph):
        t = t0 + (t1 - t0) * ph / phi_max
        return (r_i + t) * math.cos(ph), z_s + k * (r_i + t) * math.sin(ph)

    poly = [outer(a) for a in phis] + [(r_i * math.cos(a), z_s + k * r_i * math.sin(a)) for a in reversed(phis)]
    o = ring_solid(name, poly, [0.0, 0.0], p["material"])
    if p.get("kazety"):
        cutter = coffer_cutter(name, p, r_i, z_s, k)
        boolean(o, cutter)
        bpy.data.objects.remove(cutter)
    return o


def coffer_cutter(name, p, r_i, z_s, k):
    cf = p["kazety"]
    sector = 2 * math.pi / cf["v_rade"]
    edges = [math.radians(cf["od_uhlu"])]
    for _ in range(cf["rad"]):
        edges.append(edges[-1] + sector * math.cos(edges[-1] + sector * 0.45))
    size, depth = (1.0, 0.86, 0.72, 0.58), [cf["hloubka"] * d for d in (0.3, 0.55, 0.8, 1.0)]
    v, f = [], []
    for pa, pb in zip(edges, edges[1:]):
        pc, hp = (pa + pb) / 2, (pb - pa) / 2 * 0.8
        for c in range(cf["v_rade"]):
            az, ha = c * sector, sector / 2 * 0.8
            rings = [(size[0], -0.4)]
            for s, d in zip(size, depth):
                rings += [(s, d)] if s == size[0] else [(s, rings[-1][1]), (s, d)]
            base = len(v)
            for s, d in rings:
                rho = r_i + d
                for sa, sp in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                    a, ph = az + sa * ha * s, pc + sp * hp * s
                    v.append((rho * math.cos(ph) * math.cos(a), rho * math.cos(ph) * math.sin(a), z_s + k * rho * math.sin(ph)))
            m = len(rings)
            f.append([base + 3, base + 2, base + 1, base])
            f.append([base + 4 * (m - 1) + j for j in range(4)])
            for i in range(m - 1):
                for j in range(4):
                    a, b = base + 4 * i + j, base + 4 * i + (j + 1) % 4
                    f.append((a, b, b + 4, a + 4))
    return mesh_object(f"{name}_cut", v, f)


def seating(name, p):
    """Stepped bank rising outwards: tread and riser for each step from the back of the bank down to the arena side."""
    n, d0, d1, z0, z1, base = p["stupnu"], p["od"], p["do"], p["z0"], p["z1"], p["z_dno"]
    poly = [(d0, base), (d1, base), (d1, z1)]
    for i in range(n, 0, -1):
        d = d0 + (d1 - d0) * (i - 1) / n
        poly += [(d, z0 + (z1 - z0) * i / n), (d, z0 + (z1 - z0) * (i - 1) / n)]
    if z0 == base:
        poly.pop()
    return ring_solid(name, poly, p["osy"], p["material"])


def box_solid(name, p, mat=None):
    g = Geo(place=rotated(p["azimut"]))
    g.box(p["od"], p["do"])
    return mesh_object(name, g.v, g.f, mat)


def wedge_cutter(name, span, z_range):
    a0, a1 = math.radians(span[0]), math.radians(span[1])
    n = max(2, int((a1 - a0) / math.radians(3)))
    r = 4000.0
    ring = [(0.0, 0.0)] + [(r * math.cos(a0 + (a1 - a0) * i / n), r * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]
    m = len(ring)
    v = [(x, y, z) for z in z_range for x, y in ring]
    f = [list(range(m - 1, -1, -1)), list(range(m, 2 * m))] + [(i, (i + 1) % m, m + (i + 1) % m, m + i) for i in range(m)]
    return mesh_object(f"{name}_cut", v, f)


def build(spec, kept=lambda x, y: True):
    """Named objects from the description; kept(x, y) says which loose columns stay (a section view)."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    objects = {}
    for part in spec["dily"]:
        kind, name = part["typ"], part["nazev"]
        if kind == "prstenec":
            objects[name] = ring_solid(name, [tuple(p) for p in part["profil"]], part["osy"], part["material"])
        elif kind == "hlediste":
            objects[name] = seating(name, part)
        elif kind == "kopule":
            objects[name] = dome(name, part)
        elif kind == "kvadr":
            objects[name] = box_solid(name, part, part["material"])
        elif kind == "disk":
            objects[name] = disc_solid(name, part["osy"], part["z0"], part["z1"], part["material"])
        elif kind == "sloupy":
            o = columns(name, part, kept)
            if o:
                objects[name] = o
        elif kind == "portik":
            objects[name] = portico(name, part)
        elif kind == "arkady":
            cutter = arcade_cutter(name, part)
            boolean(objects[part["cil"]], cutter)
            bpy.data.objects.remove(cutter)
        elif kind == "vyrez":
            cutter = box_solid(f"{name}_cut", part["kvadr"]) if "kvadr" in part else wedge_cutter(name, part["azimut"], part["z"])
            for target in part["cile"]:
                boolean(objects[target], cutter)
            bpy.data.objects.remove(cutter)
    bpy.context.view_layer.update()
    return objects


def bbox_of(o):
    xs, ys, zs = zip(*(o.matrix_world @ v.co for v in o.data.vertices))
    return [[round(min(xs), 3), round(min(ys), 3), round(min(zs), 3)], [round(max(xs), 3), round(max(ys), 3), round(max(zs), 3)]]


def loose_parts(objects, meta, tol):
    """Named parts not reaching the largest one, directly or through others. Pieces inside a part (a column's base and
    shaft) are built to touch, so the check that counts for a parts model is this one, not per fragment."""
    meshes = {}
    for name, o in objects.items():
        verts = [v.co.copy() for v in o.data.vertices]
        meshes[name] = (verts, BVHTree.FromPolygons(verts, [tuple(p.vertices) for p in o.data.polygons], epsilon=0.0), *meta[name]["bbox"])
    names = list(meshes)
    group = {n: n for n in names}

    def root(n):
        while group[n] != n:
            n = group[n]
        return n

    nearest = dict.fromkeys(names, math.inf)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            ma, mb = meshes[a], meshes[b]
            apart = max(0.0, *(max(ma[2][k] - mb[3][k], mb[2][k] - ma[3][k]) for k in range(3)))
            d = apart
            if apart <= tol:
                if ma[1].overlap(mb[1]):
                    d = 0.0
                else:
                    d = min(min(mb[1].find_nearest(v)[3] for v in ma[0][::max(1, len(ma[0]) // 300)]),
                            min(ma[1].find_nearest(v)[3] for v in mb[0][::max(1, len(mb[0]) // 300)]))
            nearest[a], nearest[b] = min(nearest[a], d), min(nearest[b], d)
            if d <= tol:
                group[root(a)] = root(b)

    def volume(n):
        lo, hi = meta[n]["bbox"]
        return (hi[0] - lo[0]) * (hi[1] - lo[1]) * (hi[2] - lo[2])

    main = root(max(names, key=volume))
    return [{"nazev": n, "mezera": round(nearest[n], 3)} for n in names if root(n) != main]


def main():
    args = sys.argv[sys.argv.index("--") + 1:]
    out, spec = args[0], json.loads(Path(args[1]).read_text(encoding="utf-8"))
    objects = build(spec)
    meta = {name: {"material": o.data.materials[0].name if o.data.materials else None, "bbox": bbox_of(o)} for name, o in objects.items()}
    report = {"dily": meta, "bez_kontaktu": loose_parts(objects, meta, 0.003 * max(spec["dim"].values()))}
    bpy.ops.object.select_all(action="DESELECT")
    bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", export_apply=True)
    Path(f"{out}.dily.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print("bbox target", spec["dim"])


if __name__ == "__main__":
    main()
