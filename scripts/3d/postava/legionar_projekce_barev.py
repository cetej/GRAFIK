# Barvy z podkladu operátora promítnuté na hotový model (vertex colors), geometrie beze změny. 0 USD.
# blender -b --factory-startup --python projekce_barev.py -- <model.glb> <ref_dir> <out.glb> <render_dir>
# Kamery (konvence GRAFIK render_views): voják hledí k -Y, jeho pravý bok je -X.
import bpy, sys, os
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

args = sys.argv[sys.argv.index("--") + 1:]
GLB, REFS, OUT_GLB, OUT_R = (os.path.abspath(a) for a in args[:4])
os.makedirs(OUT_R, exist_ok=True)
# pohled: (směr ke kameře, osa u v obrázku, váha)
VIEWS = {
    "front": (Vector((0, -1, 0)), np.array([1, 0, 0]), 1.0),
    "back": (Vector((0, 1, 0)), np.array([-1, 0, 0]), 1.0),
    "right": (Vector((-1, 0, 0)), np.array([0, -1, 0]), 1.0),
    "left": (Vector((1, 0, 0)), np.array([0, 1, 0]), 0.6),  # meč je v něm na špatném boku, proto menší váha
}

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)
obj = [o for o in bpy.context.scene.objects if o.type == "MESH"][0]
bpy.context.view_layer.objects.active = obj
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
me = obj.data
n = len(me.vertices)
co = np.empty(n * 3, np.float32); me.vertices.foreach_get("co", co); co = co.reshape(n, 3)
nr = np.empty(n * 3, np.float32); me.vertices.foreach_get("normal", nr); nr = nr.reshape(n, 3)
bvh = BVHTree.FromObject(obj, bpy.context.evaluated_depsgraph_get())
print("verts", n)


def load_ref(path):
    img = bpy.data.images.load(path)
    w, h = img.size
    px = np.array(img.pixels[:], np.float32).reshape(h, w, 4)[::-1]  # řádek 0 = horní okraj
    return px


acc = np.zeros((n, 3)); wsum = np.zeros(n)
for view, (tocam, uax, vw) in VIEWS.items():
    px = load_ref(os.path.join(REFS, f"ref-{view}.png"))
    h, w = px.shape[:2]
    alpha = px[..., 3] > 0.5
    ys, xs = np.where(alpha)
    u = co @ uax; z = co[:, 2]
    # lineární přiřazení obrysu modelu na obrys postavy v podkladu (zvlášť pro u a výšku)
    sx = (xs.max() - xs.min()) / (u.max() - u.min()); sy = (ys.max() - ys.min()) / (z.max() - z.min())
    pu0 = xs.min() + (u - u.min()) * sx
    pv0 = ys.min() + (z.max() - z) * sy
    # dorovnání podle shody obrysů: krajní body určuje hrot pila, ne tělo
    def dilate(m, it=2):
        for _ in range(it):
            p = np.pad(m, 1)
            m = p[1:-1, 1:-1] | p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:]
        return m
    sub = np.random.default_rng(0).choice(n, min(n, 60000), replace=False)
    cu, cv = pu0.mean(), pv0.mean()
    def score(p):
        ku, kv, du, dv = p
        qu = np.clip(((pu0[sub] - cu) * ku + cu + du).round().astype(int), 0, w - 1)
        qv = np.clip(((pv0[sub] - cv) * kv + cv + dv).round().astype(int), 0, h - 1)
        m = np.zeros((h, w), bool); m[qv, qu] = True
        m = dilate(m)
        return (m & alpha).sum() / (m | alpha).sum()
    # souřadnicový sestup s půlením kroku (bez pevné mřížky, optimum smí ležet daleko)
    p = [1.0, 1.0, 0.0, 0.0]; steps = [0.04, 0.04, 16.0, 16.0]; iou = score(p)
    while max(steps[2:]) >= 1:
        improved = False
        for k in range(4):
            for sgn in (1, -1):
                q = list(p); q[k] += sgn * steps[k]; s = score(q)
                if s > iou:
                    p, iou, improved = q, s, True
        if not improved:
            steps = [s / 2 for s in steps]
    ku, kv, du, dv = p
    print(view, "fit IoU", round(iou, 3), "k", round(ku, 3), round(kv, 3), "d", du, dv)
    pu = (pu0 - cu) * ku + cu + du; pv = (pv0 - cv) * kv + cv + dv
    iu = np.clip(pu.round().astype(int), 0, w - 1); iv = np.clip(pv.round().astype(int), 0, h - 1)
    facing = np.clip(nr @ np.array(tocam), 0, None)
    inside = alpha[iv, iu]
    vis = np.zeros(n, bool)
    cand = np.where((facing > 0.05) & inside)[0]
    for i in cand:
        p = Vector(co[i]) + tocam * 0.002
        hit = bvh.ray_cast(p, tocam, 10.0)
        vis[i] = hit[0] is None
    wgt = vw * facing ** 6 * vis  # skoro „vítěz bere vše“: míchání nesouhlasných pohledů rozmazává
    acc += px[iv, iu, :3] * wgt[:, None]; wsum += wgt
    print(view, "visible", int(vis.sum()))

col = np.zeros((n, 3)); has = wsum > 1e-4
col[has] = acc[has] / wsum[has, None]
print("colored", int(has.sum()), "of", n)

# nebarvená místa (temeno, podpaží) dopočítat z barevných sousedů
ed = np.empty(len(me.edges) * 2, np.int32); me.edges.foreach_get("vertices", ed); ed = ed.reshape(-1, 2)
for it in range(200):
    miss = ~has
    if not miss.any():
        break
    s = np.zeros((n, 3)); c = np.zeros(n)
    for a_, b_ in ((ed[:, 0], ed[:, 1]), (ed[:, 1], ed[:, 0])):
        m = has[b_]
        np.add.at(s, a_[m], col[b_[m]]); np.add.at(c, a_[m], 1)
    new = miss & (c > 0)
    col[new] = s[new] / c[new, None]; has = has | new
print("after fill", int(has.sum()), "of", n)

col = np.where(col <= 0.04045, col / 12.92, ((col + 0.055) / 1.055) ** 2.4)  # PNG je sRGB, atribut lineární
attr = me.color_attributes.new("barva", "FLOAT_COLOR", "POINT")
rgba = np.concatenate([col, np.ones((n, 1))], axis=1).astype(np.float32)
attr.data.foreach_set("color", rgba.ravel())
me.color_attributes.active_color = attr

mat = bpy.data.materials.new("barva_z_podkladu"); mat.use_nodes = True
nt = mat.node_tree; bsdf = nt.nodes["Principled BSDF"]
ca = nt.nodes.new("ShaderNodeVertexColor"); ca.layer_name = "barva"
nt.links.new(ca.outputs["Color"], bsdf.inputs["Base Color"])
bsdf.inputs["Roughness"].default_value = 0.6
me.materials.clear(); me.materials.append(mat)

bpy.ops.export_scene.gltf(filepath=OUT_GLB, export_format="GLB", use_selection=False)
print("exported", OUT_GLB)

# kontrolní rendery
sc = bpy.context.scene
sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = 32; sc.cycles.use_denoising = True
sc.render.resolution_x = sc.render.resolution_y = 1024
sc.view_settings.view_transform = "Standard"
wd = bpy.data.worlds.new("w"); sc.world = wd; wd.use_nodes = True
wd.node_tree.nodes["Background"].inputs[0].default_value = (0.8, 0.8, 0.8, 1)
wd.node_tree.nodes["Background"].inputs[1].default_value = 0.6
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); sun.data.energy = 1.8
sun.rotation_euler = (0.8, 0, -0.5); sc.collection.objects.link(sun)
mn = co.min(0); mx = co.max(0); ctr = Vector(((mn + mx) / 2).tolist()); size = float((mx - mn).max())
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); cam.data.type = "ORTHO"
cam.data.ortho_scale = size * 1.1; sc.collection.objects.link(cam); sc.camera = cam
for name, d in {"zepredu": (0, -1, 0.15), "zezadu": (0, 1, 0.15), "zprava": (-1, 0, 0.15), "zleva": (1, 0, 0.15), "sikmo": (-0.7, -0.7, 0.3)}.items():
    dv = Vector(d).normalized()
    cam.location = ctr + dv * size * 3
    cam.rotation_euler = (-dv).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = os.path.join(OUT_R, f"{name}.png")
    bpy.ops.render.render(write_still=True)
print("DONE")
