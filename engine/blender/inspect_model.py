# Numbers and views a script author can correct a model by (GRAFIK#71, free; driver: scripts/3d/lod_check.py):
#   blender -b --factory-startup -P engine/blender/inspect_model.py -- model.glb OUT_DIR [--size 1024] [--no-render]
# Writes OUT_DIR/inspect.json: bbox in model units (`delka` = longer horizontal side), parts, parts touching nothing,
# open and over-shared edges, and in `prurezy` how many separate bodies a horizontal cut at a share of the height finds
# (legs of an animal, wheels of a car). Vertices are welded by position first: generators write 3 vertices per face.
# Views: side, front, top (orthographic, side along the long axis), 2 perspective, one matte grey, transparent film, so
# the alpha of side.png is the model's outline; `ortho_m_na_px` turns its pixels into model units.
import json
import math
import sys

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

args = sys.argv[sys.argv.index("--") + 1:]
glb, out = args[0], args[1]
size_px = int(args[args.index("--size") + 1]) if "--size" in args else 1024
TOUCH = 0.003        # share of the longest side: closer than this counts as touching
MAX_PARTS = 40       # parts compared with each other; the rest are reported as fragments
CUTS = (0.05, 0.15, 0.25, 0.35, 0.5, 0.75)
CELL = 0.012         # share of the longest side: grid of the horizontal cuts

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=glb)
objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
if not objs:
    print("INSPECT " + json.dumps({"chyba": "GLB bez sítí"}))
    sys.exit(3)


def world_triangles(objs):
    """(N, 3) vertices and (M, 3) triangle indices of all meshes, in world coordinates."""
    verts, tris, base = [], [], 0
    for o in objs:
        m = o.data
        m.calc_loop_triangles()
        co = np.empty(len(m.vertices) * 3, dtype=np.float64)
        m.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        mw = np.array(o.matrix_world, dtype=np.float64)
        verts.append(co @ mw[:3, :3].T + mw[:3, 3])
        t = np.empty(len(m.loop_triangles) * 3, dtype=np.int64)
        m.loop_triangles.foreach_get("vertices", t)
        tris.append(t.reshape(-1, 3) + base)
        base += len(co)
    return np.vstack(verts), np.vstack(tris)


def weld(verts, tris, tol):
    _, first, inverse = np.unique(np.round(verts / tol).astype(np.int64), axis=0, return_index=True, return_inverse=True)
    return verts[first], inverse.ravel()[tris]


def islands(n, tris):
    """Label of every vertex: connected through triangles (union-find)."""
    parent = list(range(n))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for a, b, c in tris.tolist():
        ra, rb, rc = find(a), find(b), find(c)
        if ra != rb:
            parent[rb] = ra
        if ra != rc:
            parent[find(rc)] = ra
    return np.array([find(i) for i in range(n)])


def edge_counts(tris):
    e = np.vstack([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]])
    e.sort(axis=1)
    _, counts = np.unique(e, axis=0, return_counts=True)
    return int((counts == 1).sum()), int((counts > 2).sum())


def bvh(verts, tris):
    return BVHTree.FromPolygons([tuple(v) for v in verts.tolist()], [tuple(t) for t in tris.tolist()], epsilon=0.0)


def gap(sample, tree):
    best = math.inf
    for p in sample:
        hit = tree.find_nearest(Vector(p))
        if hit[0] is not None:
            best = min(best, hit[3])
    return best


def parts_report(verts, tris, labels, longest):
    """Parts largest first; those not reaching the largest one, directly or through others, are `bez_kontaktu`."""
    ids, face_counts = np.unique(labels[tris[:, 0]], return_counts=True)
    order = ids[np.argsort(-face_counts)]
    top = order[:MAX_PARTS]
    meshes, trees = [], []
    for part in top:
        t = tris[labels[tris[:, 0]] == part]
        used, remap = np.unique(t, return_inverse=True)
        v = verts[used]
        meshes.append((v, t, v.min(axis=0), v.max(axis=0)))
        trees.append(bvh(v, remap.reshape(-1, 3)))
    tol = TOUCH * longest
    group = list(range(len(top)))

    def root(a):
        while group[a] != a:
            a = group[a]
        return a

    nearest = [math.inf] * len(top)
    for i in range(len(top)):
        for j in range(i + 1, len(top)):
            a, b = meshes[i], meshes[j]
            apart = float(np.maximum(np.maximum(a[2] - b[3], b[2] - a[3]), 0).max())
            d = apart
            if apart <= tol:
                if trees[i].overlap(trees[j]):
                    d = 0.0
                else:
                    step_a, step_b = max(1, len(a[0]) // 300), max(1, len(b[0]) // 300)
                    d = min(gap(a[0][::step_a], trees[j]), gap(b[0][::step_b], trees[i]))
            nearest[i], nearest[j] = min(nearest[i], d), min(nearest[j], d)
            if d <= tol:
                group[root(i)] = root(j)
    main = root(0)
    loose = [{
        "trojuhelniku": len(m[1]),
        "stred": [round(float(x), 3) for x in (m[2] + m[3]) / 2],
        "rozmer": [round(float(x), 3) for x in m[3] - m[2]],
        "mezera": round(float(nearest[i]), 3),
    } for i, m in enumerate(meshes) if root(i) != main]
    return {"celkem": len(order), "porovnano": len(top), "fragmentu_navic": len(order) - len(top), "bez_kontaktu": loose}


def cut_bodies(verts, tris, lo, longest, z):
    """Centres (x, y) of the separate bodies in a horizontal cut at height z, on a grid of CELL * longest (8-connected
    flood fill)."""
    zs = verts[tris][:, :, 2]
    hit = tris[(zs.min(axis=1) <= z) & (zs.max(axis=1) >= z)]
    cell = CELL * longest
    filled = set()
    for tri in verts[hit]:
        pts = []
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            if (a[2] - z) * (b[2] - z) <= 0 and a[2] != b[2]:
                pts.append(a + (b - a) * (z - a[2]) / (b[2] - a[2]))
        if len(pts) < 2:
            continue
        p, q = pts[0], pts[1]
        steps = max(1, int(np.hypot(*(q - p)[:2]) / cell) + 1)
        for s in range(steps + 1):
            c = (p + (q - p) * s / steps - lo)[:2] / cell
            filled.add((int(c[0]), int(c[1])))
    if not filled:
        return []
    # the cut draws outlines: what the outside cannot reach (4-connected, walls are 8-connected) is solid, so a part
    # sunk into another is not a body of its own
    xs, ys = [c[0] for c in filled], [c[1] for c in filled]
    x0, x1, y0, y1 = min(xs) - 1, max(xs) + 1, min(ys) - 1, max(ys) + 1
    outside, stack = {(x0, y0)}, [(x0, y0)]
    while stack:
        x, y = stack.pop()
        for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if x0 <= n[0] <= x1 and y0 <= n[1] <= y1 and n not in filled and n not in outside:
                outside.add(n)
                stack.append(n)
    solid = {(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)} - outside
    bodies = []
    while solid:
        stack = [solid.pop()]
        cells = [stack[0]]
        while stack:
            x, y = stack.pop()
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    n = (x + dx, y + dy)
                    if n in solid:
                        solid.remove(n)
                        stack.append(n)
                        cells.append(n)
        if len(cells) >= 3:  # a stray cell or two is a fragment, not a limb
            c = np.mean(cells, axis=0) * cell + lo[:2]
            bodies.append([round(float(c[0]), 3), round(float(c[1]), 3)])
    return bodies


verts, tris = world_triangles(objs)
lo, hi = verts.min(axis=0), verts.max(axis=0)
extent = hi - lo
longest = float(extent.max())
weld_tol = max(longest * 1e-6, 1e-7)
w_verts, w_tris = weld(verts, tris, weld_tol)
w_tris = w_tris[(w_tris[:, 0] != w_tris[:, 1]) & (w_tris[:, 1] != w_tris[:, 2]) & (w_tris[:, 0] != w_tris[:, 2])]
labels = islands(len(w_verts), w_tris)
open_edges, shared_edges = edge_counts(w_tris)
long_ax = 0 if extent[0] >= extent[1] else 1
report = {
    "bbox": [round(float(x), 4) for x in extent],
    "delka": round(float(extent[long_ax]), 4), "sirka": round(float(extent[1 - long_ax]), 4),
    "vyska": round(float(extent[2]), 4), "delka_osa": "xy"[long_ax],
    "trojuhelniku": len(w_tris), "vrcholu": len(w_verts),
    "casti": parts_report(w_verts, w_tris, labels, longest),
    "hrany_otevrene": open_edges, "hrany_sdilene_vic_nez_2": shared_edges,
    "prurezy": {f"{c:.2f}": cut_bodies(w_verts, w_tris, lo, longest, lo[2] + c * extent[2]) for c in CUTS},
}

if "--no-render" not in args:
    for o in objs:
        o.data.materials.clear()
    mat = bpy.data.materials.new("clay")
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.62, 0.6, 0.56, 1)
    bsdf.inputs["Roughness"].default_value = 0.9
    for o in objs:
        o.data.materials.append(mat)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 16
    scene.cycles.use_denoising = True
    scene.render.resolution_x = scene.render.resolution_y = size_px
    scene.render.film_transparent = True
    scene.view_settings.view_transform = "Standard"
    world = bpy.data.worlds.new("w")
    scene.world = world
    world.node_tree.nodes["Background"].inputs[1].default_value = 2.0
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    scene.collection.objects.link(sun)
    sun.data.energy = 5.0
    sun.data.angle = math.radians(20)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.data.clip_end = longest * 50
    center = Vector(((lo + hi) / 2).tolist())
    # long axis across the frame in `side`, along the view in `front`
    side = Vector((0, -1, 0)) if long_ax == 0 else Vector((1, 0, 0))
    along = Vector((1, 0, 0)) if long_ax == 0 else Vector((0, 1, 0))
    ortho_scale = longest * 1.1
    report["ortho_m_na_px"] = round(ortho_scale / size_px, 6)
    views = {
        "side": (side, True), "front": (along, True), "top": (Vector((0, 0, 1)), True),
        "persp-a": ((side + along + Vector((0, 0, 0.45))).normalized(), False),
        "persp-b": ((side - along + Vector((0, 0, 0.45))).normalized(), False),
    }
    for name, (direction, ortho) in views.items():
        cam.data.type = "ORTHO" if ortho else "PERSP"
        if ortho:
            cam.data.ortho_scale = ortho_scale
        else:
            cam.data.lens = 50
        cam.location = center + direction * (longest * (5 if ortho else 2.2))
        cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
        light = (center - cam.location + Vector((0, 0, -0.6 * longest))).normalized()
        sun.rotation_euler = light.to_track_quat("-Z", "Y").to_euler()
        sun.rotation_euler.z += math.radians(25)
        scene.render.filepath = f"{out}/{name}.png"
        bpy.ops.render.render(write_still=True)
        print(f"VIEW {name}", flush=True)
    report["pohledy"] = [f"{name}.png" for name in views]

report["blender"] = bpy.app.version_string
with open(f"{out}/inspect.json", "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=1)
print("INSPECT " + json.dumps({k: report[k] for k in ("delka", "sirka", "vyska", "hrany_otevrene")}), flush=True)
