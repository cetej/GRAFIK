# Kostra legionáře v A-póze: -- <in.glb> <out.blend> <out.glb>
# Klouby odečtené z pravoúhlých pohledů (jednotky modelu, voják hledí k -Y, +X = jeho levá), pak měřítko na metry.
# Váhy: automatické (bone heat) na uzavřené pomocné síti z voxel remesh, přenesené na model (nejbližší plocha).
import bpy, sys, os
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]
IN, BLEND, GLB = (os.path.abspath(a) for a in args[:3])
VYSKA = 1.74  # s helmou, m
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=IN)
body = [o for o in bpy.context.scene.objects if o.type == "MESH"][0]
body.name = "legionar"
h0 = max((body.matrix_world @ Vector(c)).z for c in body.bound_box)
S = VYSKA / h0
for o in bpy.context.scene.objects: o.select_set(False)
body.select_set(True); bpy.context.view_layer.objects.active = body
body.parent = None
body.scale = (S, S, S); bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
print("INFO meritko", round(S, 4))

C = {  # (x, y, z) v jednotkách modelu
    "pelvis": ((0, 0.01, 0.53), (0, 0.01, 0.60)),
    "spine": ((0, 0.01, 0.60), (0, 0.02, 0.72)),
    "chest": ((0, 0.02, 0.72), (0, 0.02, 0.88)),
    "neck": ((0, 0.01, 0.91), (0, -0.005, 0.97)),
    "head": ((0, -0.005, 0.97), (0, -0.005, 1.12)),
}
SIDE = {
    "clavicle": ((0.02, 0.01, 0.89), (0.13, 0.02, 0.89), "chest"),
    "upperarm": ((0.13, 0.02, 0.89), (0.21, 0.01, 0.755), "clavicle"),
    "forearm": ((0.21, 0.01, 0.755), (0.29, 0.0, 0.63), "upperarm"),
    "hand": ((0.29, 0.0, 0.63), (0.355, -0.01, 0.555), "forearm"),
    "thigh": ((0.085, 0.01, 0.53), (0.077, 0.025, 0.315), "pelvis"),
    "shin": ((0.077, 0.025, 0.315), (0.09, 0.04, 0.075), "thigh"),
    "foot": ((0.09, 0.04, 0.075), (0.10, -0.065, 0.02), "shin"),
}
PARENT = {"spine": "pelvis", "chest": "spine", "neck": "chest", "head": "neck"}

arm_data = bpy.data.armatures.new("kostra")
rig = bpy.data.objects.new("kostra", arm_data)
bpy.context.scene.collection.objects.link(rig)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode="EDIT")
eb = arm_data.edit_bones
v = lambda p: Vector(p) * S
for n, (a, b) in C.items():
    e = eb.new(n); e.head, e.tail = v(a), v(b)
for n, (a, b, par) in SIDE.items():
    for sfx, sx in ((".L", 1), (".R", -1)):
        e = eb.new(n + sfx)
        e.head = v((a[0] * sx, a[1], a[2])); e.tail = v((b[0] * sx, b[1], b[2]))
for n, par in PARENT.items():
    eb[n].parent = eb[par]; eb[n].use_connect = n != "neck"
for n, (a, b, par) in SIDE.items():
    for sfx in (".L", ".R"):
        p = par if par in C else par + sfx
        eb[n + sfx].parent = eb[p]; eb[n + sfx].use_connect = n not in ("clavicle", "thigh")
# role: ohyb kolene a lokte kolem osy X kosti míří stejně na obou stranách
for e in eb:
    e.align_roll(Vector((0, -1, 0)) if e.name.split(".")[0] in ("thigh", "shin", "foot") else Vector((0, 0, 1)) if e.name.split(".")[0] in ("upperarm", "forearm", "hand", "clavicle") else Vector((0, -1, 0)))
bpy.ops.object.mode_set(mode="OBJECT")

# pomocná uzavřená síť
bpy.ops.object.select_all(action="DESELECT")
body.select_set(True); bpy.context.view_layer.objects.active = body
bpy.ops.object.duplicate()
proxy = bpy.context.active_object; proxy.name = "proxy"
proxy.data.materials.clear()
rm = proxy.modifiers.new("remesh", "REMESH"); rm.mode = "VOXEL"; rm.voxel_size = 0.006
bpy.ops.object.modifier_apply(modifier="remesh")
print("INFO proxy", len(proxy.data.vertices))
bpy.ops.object.select_all(action="DESELECT")
proxy.select_set(True); rig.select_set(True); bpy.context.view_layer.objects.active = rig
bpy.ops.object.parent_set(type="ARMATURE_AUTO")
cnt = {g.index: 0 for g in proxy.vertex_groups}
nog = 0
for vv in proxy.data.vertices:
    gs = [x.group for x in vv.groups if x.weight > 0.01]
    nog += not gs
    for gi in gs: cnt[gi] += 1
print("INFO skupiny proxy", {g.name: cnt[g.index] for g in proxy.vertex_groups}, "bez vahy", nog)

# přenos vah na model
for n in [b.name for b in arm_data.bones]:
    body.vertex_groups.new(name=n)
dt = body.modifiers.new("vahy", "DATA_TRANSFER"); dt.object = proxy
dt.use_vert_data = True; dt.data_types_verts = {"VGROUP_WEIGHTS"}; dt.vert_mapping = "POLYINTERP_NEAREST"
dt.layers_vgroup_select_src = "ALL"; dt.layers_vgroup_select_dst = "NAME"
bpy.ops.object.select_all(action="DESELECT")
body.select_set(True); bpy.context.view_layer.objects.active = body
bpy.ops.object.modifier_apply(modifier="vahy")
bpy.ops.object.vertex_group_normalize_all(lock_active=False)
bpy.data.objects.remove(proxy, do_unlink=True)

# úprava vah v numpy: strana, tunika, vyhlazení
import numpy as np
names = [g.name for g in body.vertex_groups]
gi = {n: i for i, n in enumerate(names)}
me = body.data; nv = len(me.vertices)
W = np.zeros((nv, len(names)), np.float32)
for v_ in me.vertices:
    for g in v_.groups: W[v_.index, g.group] = g.weight
co = np.empty(nv * 3, np.float32); me.vertices.foreach_get("co", co); co = co.reshape(-1, 3) / S  # jednotky modelu
x, z = co[:, 0], co[:, 2]
L = np.array([n.endswith(".L") for n in names]); R = np.array([n.endswith(".R") for n in names])
W[np.ix_(x > 0.02, R)] = 0; W[np.ix_(x < -0.02, L)] = 0          # levá strana nebere pravé kosti a naopak
# tunika má dvojitou stěnu a uvnitř jsou stehna: v jejím pásu váhy jen podle polohy, ať se vnitřek
# a látka kolem pohnou stejně (jinak stehno látku prorazí)
LO, HI = 0.34, 0.66
band = (z > LO - 0.03) & (z < HI + 0.03) & (np.abs(x) < 0.21)
k = np.clip((HI - z) / (HI - LO), 0, 1) ** 0.8 * 0.95 + 0.05     # podíl stehna: u opasku 5 %, u lemu 100 %
side = 1 / (1 + np.exp(-x / 0.035))                              # 1 = levá
P = np.zeros_like(W)
P[:, gi["pelvis"]] = 1 - k
P[:, gi["thigh.L"]] = k * side
P[:, gi["thigh.R"]] = k * (1 - side)
a = np.clip(np.minimum((z - (LO - 0.03)) / 0.04, ((HI + 0.03) - z) / 0.04), 0, 1)[:, None]
W[band] = (a * P + (1 - a) * W)[band]
e = np.empty(len(me.edges) * 2, np.int32); me.edges.foreach_get("vertices", e); e = e.reshape(-1, 2)
# body bez váhy by zůstaly v klidové poloze (trny mezi chodidly): váhu převezmou od sousedů
empty = W.sum(1) < 0.3
print("INFO bez vahy pred", int(empty.sum()))
for _ in range(200):
    if not empty.any(): break
    acc = np.zeros_like(W); np.add.at(acc, e[:, 0], W[e[:, 1]]); np.add.at(acc, e[:, 1], W[e[:, 0]])
    fill = empty & (acc.sum(1) > 0)
    W[fill] = acc[fill] / acc[fill].sum(1, keepdims=True)
    empty = W.sum(1) < 0.3
print("INFO bez vahy po", int(empty.sum()))
W /= np.maximum(W.sum(1, keepdims=True), 1e-6)
for g in body.vertex_groups: body.vertex_groups.remove(g)
for n in names: body.vertex_groups.new(name=n)
for j, n in enumerate(names):
    vg = body.vertex_groups[n]
    idx = np.nonzero(W[:, j] > 0.002)[0]
    for wv in np.unique(np.round(W[idx, j], 3)):
        sel = idx[np.round(W[idx, j], 3) == wv]
        vg.add(sel.tolist(), float(wv), "REPLACE")
print("INFO vahy upraveny, pas tuniky", int(band.sum()))
body.parent = rig
am = body.modifiers.new("kostra", "ARMATURE"); am.object = rig
bpy.ops.wm.save_as_mainfile(filepath=BLEND)
bpy.ops.object.select_all(action="SELECT")
bpy.ops.export_scene.gltf(filepath=GLB, export_format="GLB", export_skins=True)
print("DONE")
