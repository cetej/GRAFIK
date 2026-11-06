# Postup B: vrstvená postava. Tělo MPFB (1,66 m, kostra s prsty), kov a výstroj z plného původního modelu jen posunuté a zmenšené,
# rukávy natočené do úhlu paží těla, tunika jako simulovaná látka se srážkou se skutečnými nohami.
# BLENDER_USER_RESOURCES=GRAFIK/run/mpfb_profil blender -b <postava>/telo_v1.blend --python postava_s_vystroji.py -- <postava>/kostra.blend <postava>/parts <out_dir> [<vystroj_dir>]
# Pod zámkem těžké práce (heavy_lock "blender"). Postup: docs/3d-postava-postup.md, oddíl „Postava s kostrou a výstrojí po dílech“.
import bpy, bmesh, sys, os, glob, math
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
TD = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(TD, "spolecny.py"), encoding="utf-8").read())
a = sys.argv[sys.argv.index("--") + 1:]; HB, PD, OUT = a[:3]; VYSTROJ = a[3] if len(a) > 3 else os.path.join(os.path.dirname(os.path.dirname(HB)), "vystroj")
sc = bpy.context.scene
body = bpy.data.objects["telo"]; rig = bpy.data.objects["kostra"]; rig.name = "kostra_mpfb"; RM = rig.matrix_world
for o in bpy.data.objects:
    if o.type == "MESH" and "short02" in o.name.lower(): o.hide_render = o.hide_viewport = True
with bpy.data.libraries.load(HB) as (src, dst): dst.objects = ["legionar", "kostra"]
for o in dst.objects: sc.collection.objects.link(o)
old = bpy.data.objects["legionar"]; orig = bpy.data.objects["kostra"]; old.name = "puvodni"; orig.name = "puvodni_kostra"
old.modifiers.clear(); old.parent = None
def sel(objs):
    for o in bpy.context.selected_objects: o.select_set(False)
    for o in objs: o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
def co(o):
    v = np.empty(len(o.data.vertices) * 3, np.float32); o.data.vertices.foreach_get("co", v); return v.reshape(-1, 3)
def mp(n): return RM @ rig.data.bones[n].head_local
def oldb(n): return orig.matrix_world @ orig.data.bones[n].head_local
def verts_world(o):
    m = o.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh(); v = np.array([o.matrix_world @ x.co for x in m.vertices]); return v
# --- paže těla do úhlu nadloktí původního modelu (klidová póza kostry), aby rukávy seděly bez otáčení ---
skinned = [o for o in bpy.data.objects if o.type == "MESH" and any(m.type == "ARMATURE" and m.object == rig for m in o.modifiers)]
# tělo jako muž z předlohy: širší hrudník a ramena (MPFB hmotnost; svalnatost už je nejvyšší). Klíče se zapečou níž.
MAKRO = {"$md-universal-$ma-$yn-max$mu-max$wg": 0.45, "$md-universal-$ma-$yn-max$mu-$av$wg": 0.52}
for o in skinned:
    if not o.data.shape_keys: continue
    for kn, kv in MAKRO.items():
        if kn in o.data.shape_keys.key_blocks: o.data.shape_keys.key_blocks[kn].value = kv
    vis = [(m, m.show_viewport) for m in o.modifiers]
    for m, _ in vis: m.show_viewport = False
    bpy.context.view_layer.update(); ev = o.evaluated_get(bpy.context.evaluated_depsgraph_get()); em = ev.to_mesh()
    Pk = np.empty(len(em.vertices) * 3, np.float32); em.vertices.foreach_get("co", Pk); ev.to_mesh_clear()
    for m, v in vis: m.show_viewport = v
    o.shape_key_clear(); o.data.vertices.foreach_set("co", Pk); o.data.update()
sel([rig]); bpy.ops.object.mode_set(mode="POSE"); Mi3 = RM.inverted().to_3x3()
for sd in ("L", "R"):
    pb = rig.pose.bones[f"upperarm01.{sd}"]; h = pb.head.copy(); t = rig.pose.bones[f"lowerarm01.{sd}"].head.copy()
    R = (t - h).normalized().rotation_difference((Mi3 @ (oldb(f"forearm.{sd}") - oldb(f"upperarm.{sd}"))).normalized()).to_matrix().to_4x4()
    pb.matrix = Matrix.Translation(h) @ R @ Matrix.Translation(-h) @ pb.matrix; bpy.context.view_layer.update()
bpy.ops.object.mode_set(mode="OBJECT")
def bake_rest():
    for o in skinned:
        am_ = next(m for m in o.modifiers if m.type == "ARMATURE" and m.object == rig); nm = am_.name
        sel([o]); bpy.ops.object.modifier_apply(modifier=nm)
        m2 = o.modifiers.new(nm, "ARMATURE"); m2.object = rig; m2.use_deform_preserve_volume = True
        while o.modifiers.find(nm) > 0: bpy.ops.object.modifier_move_up(modifier=nm)
    sel([rig]); bpy.ops.object.mode_set(mode="POSE"); bpy.ops.pose.armature_apply(selected=False); bpy.ops.object.mode_set(mode="OBJECT")
bake_rest()
print("INFO paze tela v uhlu puvodniho modelu", flush=True)
# --- štítky dílů na plochách plného modelu ---
OMW = old.matrix_world; OV = np.array([OMW @ v.co for v in old.data.vertices])
S = 1.5179; pv, pp, pl = [], [], []
for f in glob.glob(os.path.join(PD, "part_*.glb")):
    n = int(f.rsplit("_", 1)[1].split(".")[0]); before = set(bpy.data.objects); bpy.ops.import_scene.gltf(filepath=f)
    for o in [o for o in bpy.data.objects if o not in before]:
        if o.type == "MESH":
            M = Matrix.Diagonal((S, S, S, 1)) @ o.matrix_world; off = len(pv)
            pv += [tuple(M @ v.co) for v in o.data.vertices]
            for p_ in o.data.polygons: pp.append([off + i for i in p_.vertices]); pl.append(n)
    for o in [o for o in bpy.data.objects if o not in before]: bpy.data.objects.remove(o, do_unlink=True)
pbvh = BVHTree.FromPolygons(pv, pp); pl = np.array(pl)
OC = np.empty(len(old.data.polygons) * 3); old.data.polygons.foreach_get("center", OC); OC = OC.reshape(-1, 3) @ np.array(OMW)[:3, :3].T + np.array(OMW)[:3, 3]
LAB = np.array([pl[pbvh.find_nearest(Vector(c))[2]] for c in OC])
# barva každé plochy z textury: kov rukávu patří k ramenním plátům, látka zůstane rukávu
_im = next(n.image for m in old.data.materials if m and m.node_tree for n in m.node_tree.nodes if n.type == "TEX_IMAGE" and n.image)
_tw, _th = _im.size; _tx = np.empty(_tw * _th * 4, np.float32); _im.pixels.foreach_get(_tx); _tx = _tx.reshape(_th, _tw, 4)
_uv = np.empty(len(old.data.loops) * 2); old.data.uv_layers.active.data.foreach_get("uv", _uv); _uv = _uv.reshape(-1, 2)
_lf = np.repeat(np.arange(len(old.data.polygons)), [p_.loop_total for p_ in old.data.polygons])
_fu = np.zeros((len(old.data.polygons), 2)); np.add.at(_fu, _lf, _uv); _fu /= np.bincount(_lf, minlength=len(old.data.polygons))[:, None]
FCOL = _tx[np.clip((_fu[:, 1] * _th).astype(int), 0, _th - 1), np.clip((_fu[:, 0] * _tw).astype(int), 0, _tw - 1), :3]
RED = FCOL[:, 0] > 1.8 * np.maximum(FCOL[:, 1], FCOL[:, 2])
SAT = (FCOL.max(1) - FCOL.min(1)) / np.maximum(FCOL.max(1), 1e-6)
LAB = np.where((LAB == 4) & ~RED, 20, LAB)
BRI = FCOL.max(1)
LAB = np.where(np.isin(LAB, [2, 5]) & RED, -1, LAB)                                           # látka tuniky v opasku
SKIN = (SAT > 0.25) & (BRI > 0.42) & ~RED
LAB = np.where(np.isin(LAB, [0, 7, 9, 19]) & SKIN, -1, LAB)                                   # kůže původní nohy v sandálu
print("INFO vyrazeno z opasku a sandalu", int((LAB == -1).sum()), flush=True)
print("INFO kov z rukavu k ramenum", int(((LAB == 20)).sum()), flush=True)
GROUPS = {"helma": [14, 17, 21, 11, 12], "zbroj": [6], "ramena": [20], "opasek": [2, 5], "satek": [15], "rukav": [4], "sandal_L": [7, 19], "sandal_R": [0, 9], "tunika": [8]}
parts = {}
for g, labs in GROUPS.items():
    bm = bmesh.new(); bm.from_mesh(old.data); bm.transform(OMW); bm.faces.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[bm.faces[i] for i in np.nonzero(~np.isin(LAB, labs))[0]], context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    me = bpy.data.meshes.new(g); bm.to_mesh(me); bm.free()
    for m in old.data.materials: me.materials.append(m)
    o = bpy.data.objects.new(g, me); sc.collection.objects.link(o); parts[g] = o
print("INFO dily", {g: len(o.data.vertices) for g, o in parts.items()}, flush=True)
# sandály: který je který podle polohy
for g in ("sandal_L", "sandal_R"): pass
K = 0.95
# --- nohy zesílit podle obvodu lýtek původního modelu (chodidla obvod nedědí) ---
def leg_w(Vv, zk, za, sg):
    zm = (zk + za) / 2; q = Vv[(np.abs(Vv[:, 2] - zm) < 0.01) & (Vv[:, 0] * sg > 0.02) & (np.abs(Vv[:, 0]) < 0.35)]
    return q[:, 0].max() - q[:, 0].min(), q[:, 1].max() - q[:, 1].min()
BVl = verts_world(body); rr = []
for sd, sg in (("L", 1), ("R", -1)):
    wo = leg_w(OV, oldb(f"shin.{sd}").z, oldb(f"foot.{sd}").z, sg); wn = leg_w(BVl, mp(f"lowerleg01.{sd}").z, mp(f"foot.{sd}").z, sg)
    rr.append(float(np.clip(np.sqrt(wo[0] * wo[1]) * K / np.sqrt(wn[0] * wn[1]), 1.0, 1.35)))
gs_ = sum(rr) / 2
sel([rig]); bpy.ops.object.mode_set(mode="EDIT")
for sd in ("L", "R"): rig.data.edit_bones[f"foot.{sd}"].inherit_scale = "NONE"
bpy.ops.object.mode_set(mode="POSE")
for sd in ("L", "R"):
    rig.data.bones  # stehno jen trochu, lýtko podle původního
    rig.pose.bones[f"upperleg01.{sd}"].scale = (1.06, 1, 1.06); rig.pose.bones[f"lowerleg01.{sd}"].scale = (gs_ / 1.06, 1, gs_ / 1.06)
bpy.context.view_layer.update(); bpy.ops.object.mode_set(mode="OBJECT"); bake_rest()
sel([rig]); bpy.ops.object.mode_set(mode="EDIT")
for sd in ("L", "R"): rig.data.edit_bones[f"foot.{sd}"].inherit_scale = "FULL"
bpy.ops.object.mode_set(mode="OBJECT")
print("INFO nohy obvod x", round(gs_, 2), "lytka L/R", [round(x, 2) for x in rr], flush=True)
# --- chodidla těla rozšířit na šířku původních nohou (sandály pak sedí bez deformace) ---
K = 0.95; BV0 = verts_world(body)
sel([rig]); bpy.ops.object.mode_set(mode="POSE")
for sd, sg in (("L", 1), ("R", -1)):
    so_ = [co(parts[g]) for g in ("sandal_L", "sandal_R")]; Cs = next(c for c in so_ if c[:, 0].mean() * sg > 0); sole = Cs[Cs[:, 2] < 0.03]
    F = BV0[(BV0[:, 2] < 0.09) & (BV0[:, 0] * sg > 0.03)]
    r = 1.0                                       # chodidla nerozšiřovat: sandály jsou nové a usadí se podle chodidla (dřív rozšíření pro staré vyříznuté)
    rig.pose.bones[f"foot.{sd}"].scale = (r, 1, 1); bpy.context.view_layer.update()
    print("INFO chodidlo", sd, "rozsireni", round(r, 2), flush=True)
bpy.ops.object.mode_set(mode="OBJECT"); bake_rest()
# --- usazení: rovnoměrné zmenšení a posun (tvar plechu se nemění) ---
BV = verts_world(body)
def ycen(Vv, z, xm=0.12):
    q = Vv[(np.abs(Vv[:, 2] - z) < 0.01) & (np.abs(Vv[:, 0]) < xm)]; return (q[:, 1].max() + q[:, 1].min()) / 2
zo, zn = oldb("upperarm.L").z, mp("upperarm01.L").z
SRC, DST = Vector((0, ycen(OV, zo - 0.08), zo)), Vector((0, ycen(BV, zn - 0.08), zn))
def place(o, src, dst, k=K):
    o.data.transform(Matrix.Translation(dst) @ Matrix.Scale(k, 4) @ Matrix.Translation(-src)); o.data.update()
for g in ("zbroj", "ramena", "satek", "rukav"): place(parts[g], SRC, DST)
zo2, zn2 = oldb("thigh.L").z, mp("upperleg01.L").z
SRC2, DST2 = Vector((0, ycen(OV, zo2 + 0.05), zo2)), Vector((0, ycen(BV, zn2 + 0.05), zn2))
for g in ("opasek", "tunika"): place(parts[g], SRC2, DST2)
print("INFO kycle stary", round(zo2, 3), "novy", round(zn2, 3), "ramena stary", round(zo, 3), "novy", round(zn, 3), flush=True)
hz_ = BV[:, 2].max(); hy = ycen(BV, hz_ - 0.06, 0.09); Ch = co(parts["helma"])
kh = 0.268 / (Ch[:, 0].max() - Ch[:, 0].min()) * 1.0
place(parts["helma"], Vector((0, (Ch[:, 1].max() + Ch[:, 1].min()) / 2, Ch[:, 2].max())), Vector((0, hy + 0.032, hz_ + 0.04)), kh)
for sd, sg in (("L", 1), ("R", -1)):
    o = parts[f"sandal_{sd}"]; Cs = co(o)
    if Cs[:, 0].mean() * sg < 0: o = parts[f"sandal_{'R' if sd == 'L' else 'L'}"]; Cs = co(o)
    F = BV[(BV[:, 2] < 0.09) & (BV[:, 0] * sg > 0.03)]
    sole = Cs[Cs[:, 2] < 0.03]
    sx = (F[:, 0].max() - F[:, 0].min() + 0.016) / (sole[:, 0].max() - sole[:, 0].min()); sy = (F[:, 1].max() - F[:, 1].min() + 0.02) / (sole[:, 1].max() - sole[:, 1].min())
    sz = (sx + sy) / 2
    fo = oldb(f"foot.{sd}"); fn_ = mp(f"foot.{sd}")                    # sandál sedí kotníkem na kotníku
    c0 = Vector((fo.x, fo.y, 0)); c1 = Vector((fn_.x, fn_.y, 0))
    o.data.transform(Matrix.Translation(c1) @ Matrix.Diagonal((sx, sy, sz, 1)) @ Matrix.Translation(-c0)); o.data.update(); o["strana"] = sd
    Cn = co(o); front_s = Cn[Cn[:, 2] < 0.03][:, 1].min(); front_f = F[F[:, 2] < 0.05][:, 1].min() - 0.012
    if front_f < front_s:                                                 # prsty by trčely: podrážku prodloužit dopředu od kotníku
        k2 = (c1.y - front_f) / (c1.y - front_s); Cn[:, 1] = c1.y + (Cn[:, 1] - c1.y) * np.where(Cn[:, 1] < c1.y, k2, 1.0)
        o.data.vertices.foreach_set("co", Cn.ravel()); o.data.update(); print("INFO sandal", sd, "prodlouzen dopredu", round(k2, 3), flush=True)
    print("INFO sandal", sd, round(sx, 2), round(sy, 2), round(sz, 2), flush=True)
for x in (old, orig): bpy.data.objects.remove(x, do_unlink=True)
# --- připnutí ke kostře ---
bones = [b.name for b in rig.data.bones]
def rigid(o, bone):
    o.vertex_groups.clear(); g = o.vertex_groups.new(name=bone); g.add(list(range(len(o.data.vertices))), 1.0, "REPLACE")
def transfer(o, keep=None):
    o.vertex_groups.clear()
    for g in body.vertex_groups:
        if g.name in bones: o.vertex_groups.new(name=g.name)
    dt = o.modifiers.new("v", "DATA_TRANSFER"); dt.object = body; dt.use_vert_data = True; dt.data_types_verts = {"VGROUP_WEIGHTS"}
    dt.vert_mapping = "POLYINTERP_NEAREST"; dt.layers_vgroup_select_src = "ALL"; dt.layers_vgroup_select_dst = "NAME"
    sel([o]); bpy.ops.object.modifier_apply(modifier="v")
    if keep:
        for g in list(o.vertex_groups):
            if not g.name.startswith(keep): o.vertex_groups.remove(g)
SP = [(n, mp(n).z) for n in ("spine05", "spine04", "spine03", "spine02", "spine01")]
def spine(o, mask=None):
    C = co(o); idx = np.arange(len(C)) if mask is None else np.nonzero(mask)[0]
    for g in list(o.vertex_groups):
        g.remove(idx.tolist())
    for j, (n, z0) in enumerate(SP):
        z1 = SP[j + 1][1] if j + 1 < len(SP) else 9
        lo_ = np.clip((C[idx, 2] - (z0 - 0.02)) / 0.04, 0, 1) if j else np.ones(len(idx)); hi_ = np.clip(((z1 + 0.02) - C[idx, 2]) / 0.04, 0, 1)
        w = np.minimum(lo_, hi_); g = o.vertex_groups.get(n) or o.vertex_groups.new(name=n)
        for wv in np.unique(np.round(w, 2)):
            if wv > 0: g.add(idx[np.round(w, 2) == wv].tolist(), float(wv), "REPLACE")
rigid(parts["helma"], "head"); rigid(parts["opasek"], "root")
# tloušťka plechu (Solidify) na rozsypané síti z generátoru dělá zmačkanou fólii: nepoužívat
o = parts["ramena"]; C = co(o); o.vertex_groups.clear()
for nm, m in (("shoulder01.L", C[:, 0] > 0.045), ("shoulder01.R", C[:, 0] < -0.045), ("spine01", np.abs(C[:, 0]) <= 0.045)):
    o.vertex_groups.new(name=nm).add(np.nonzero(m)[0].tolist(), 1.0, "REPLACE")
transfer(parts["zbroj"]); spine(parts["zbroj"])
transfer(parts["rukav"]); transfer(parts["satek"])
for sd in ("L", "R"):
    o = parts[f"sandal_{sd}"]; transfer(o, keep=("foot", "lowerleg", "toe"))
for o in parts.values():
    if o.name == "tunika": continue
    o.parent = rig; am = o.modifiers.new("kostra", "ARMATURE"); am.object = rig
    for f in o.data.polygons: f.use_smooth = True
# --- tunika jako jeden oděv: trup od krku po lem + dva rukávy, sloučené do jedné sítě, simulovaná látka ---
# (dřív sukně, zvlášť rukávy a přebarvená kůže pod loricou: tři kusy, které na sebe nenavazovaly)
tun = parts["tunika"]
# výšky podle předlohy ve stejném měřítku (ref-front vedle renderu, 2026-11-06): spodek loriky 0,99 m, střed opasku 0,98 m,
# lem tuniky 0,575 m u postavy s kolenem 0,483 m; rukáv 17 cm od ramenního kloubu.
KOLENO = mp("lowerleg01.L").z; BELT_C = KOLENO + 0.497; HEM = KOLENO + 0.102; LORICA_DOLE = KOLENO + 0.507   # HEM +1 cm na prověšení látky
RUKAV = 0.24; ZTOP = mp("neck01").z - 0.015
z0 = HEM; z1 = BELT_C + 0.01; hzp = z1; NA = 96
_em = body.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh(); _polys = [p_.vertices[:] for p_ in _em.polygons]
def _sd(P_, a_, b_):
    ab = b_ - a_; t = np.clip(((P_ - a_) @ ab) / (ab @ ab), 0, 1); return np.linalg.norm(P_ - (a_ + t[:, None] * ab), axis=1)
armv = np.zeros(len(BV), bool)
for sd in ("L", "R"):
    for b0, b1 in ((f"upperarm01.{sd}", f"lowerarm01.{sd}"), (f"lowerarm01.{sd}", f"wrist.{sd}"), (f"wrist.{sd}", f"finger3-3.{sd}")):
        armv |= _sd(BV, np.array(mp(b0)), np.array(RM @ rig.data.bones[b1].tail_local if b1.startswith("finger") else mp(b1))) < 0.075
bvb = BVHTree.FromPolygons([tuple(x) for x in BV], [p_ for p_ in _polys if not armv[list(p_)].any()])   # trup a nohy bez paží
abvh = BVHTree.FromPolygons([tuple(x) for x in BV], _polys)                                               # celé tělo (rukávy)
def _ray_far(bvh, c, d, lim):                     # nejvzdálenější zásah těla do vzdálenosti lim (prsty u boků a druhá paže leží dál)
    far = 0.0; o_ = c
    while True:
        h = bvh.ray_cast(o_ + d * 0.0005, d, 0.45)
        if h[0] is None: break
        dd = (h[0] - c).length; o_ = h[0]
        if dd < lim: far = dd
    return far
rings = np.arange(ZTOP, z0 - 0.03 - 1e-6, -0.01); C0 = []          # 3 cm pod lem: řez rovinou pak nejde přes zaoblený roh po remeshi (lem se stahoval dovnitř)
for z in rings:
    q = BV[(np.abs(BV[:, 2] - z) < 0.01) & (np.abs(BV[:, 0]) < 0.2)]; C0.append(float((q[:, 1].max() + q[:, 1].min()) / 2) if len(q) else (C0[-1] if C0 else 0.0))
RB = np.array([[_ray_far(bvb, Vector((0, C0[i], z)), Vector((math.cos(2 * math.pi * j / NA), math.sin(2 * math.pi * j / NA), 0)), 0.22) for j in range(NA)] for i, z in enumerate(rings)])
sk = rings < BELT_C                                               # pod opaskem sukně: přes boky 1,5 cm, k lemu o 10 % širší
_hip = np.percentile(RB[sk], 90, axis=0) + 0.025; _hip = np.max([np.roll(_hip, k) for k in range(-6, 7)], axis=0); _t = np.clip((BELT_C - rings) / max(BELT_C - z0, 1e-6), 0, 1)   # max přes ±22°: látka přes hýždě napnutá, ne vtažená do rýhy
_ib = int(np.argmin(np.abs(rings - BELT_C))); _Rb = RB[_ib] + 0.015                       # sukně do A (předloha): od opasku přímka k lemu,
_Rh = _hip * 1.12; Rsk = np.maximum(_Rb[None, :] + (_Rh - _Rb)[None, :] * _t[:, None], RB + 0.02); Rup = RB + 0.01   # přes boky a hýždě po těle; mimo kolizní zónu těla (0,6 + 0,8 cm), jinak ji simulace hned odhodí a roztrhá
_w = np.clip((BELT_C + 0.01 - rings) / 0.05, 0, 1)[:, None]          # nad opaskem těsně na těle, pod ním plynule do sukně
R = Rup * (1 - _w) + Rsk * _w
def _tube(name, centers, dirs_u, dirs_v, radii):                  # uzavřená trubice (víčka na koncích) pro sloučení
    n = radii.shape[1]; vs_ = []
    for c, u, v, rr in zip(centers, dirs_u, dirs_v, radii):
        for j in range(n):
            a_ = 2 * math.pi * j / n; vs_.append(tuple(c + (u * math.cos(a_) + v * math.sin(a_)) * float(rr[j])))
    k = len(centers); fs_ = [(i * n + j, i * n + (j + 1) % n, (i + 1) * n + (j + 1) % n, (i + 1) * n + j) for i in range(k - 1) for j in range(n)]
    vs_ += [tuple(centers[0]), tuple(centers[-1])]; c0, c1 = len(vs_) - 2, len(vs_) - 1
    fs_ += [(c0, (j + 1) % n, j) for j in range(n)] + [(c1, (k - 1) * n + j, (k - 1) * n + (j + 1) % n) for j in range(n)]
    me_ = bpy.data.meshes.new(name); me_.from_pydata(vs_, [], fs_); me_.update(); ob_ = bpy.data.objects.new(name, me_); sc.collection.objects.link(ob_); return ob_
tubes = [_tube("tunika_trup", [Vector((0, C0[i], z)) for i, z in enumerate(rings)], [Vector((1, 0, 0))] * len(rings), [Vector((0, 1, 0))] * len(rings), R)]
SLV = {}
for sd in ("L", "R"):
    S0 = mp(f"upperarm01.{sd}"); ax = (mp(f"lowerarm01.{sd}") - S0).normalized(); u = ax.cross(Vector((0, 1, 0))).normalized(); v_ = ax.cross(u).normalized()
    ts = np.arange(-0.06, RUKAV + 1e-6, 0.01); cs = [S0 + ax * float(t) for t in ts]
    rr = np.array([[min(_ray_far(abvh, c, (u * math.cos(2 * math.pi * j / 48) + v_ * math.sin(2 * math.pi * j / 48)).normalized(), 0.07) or 0.05, 0.07) + 0.03 + 0.025 * max(float(t), 0) / RUKAV for j in range(48)] for c, t in zip(cs, ts)])   # volný rukáv, k okraji širší (předloha)
    tubes.append(_tube(f"tunika_rukav_{sd}", cs, [u] * len(ts), [v_] * len(ts), rr)); SLV[sd] = (S0, ax)
sel(tubes); bpy.ops.object.join(); cl = bpy.context.view_layer.objects.active; cl.name = "tunika_latka"
rm_ = cl.modifiers.new("slouceni", "REMESH"); rm_.mode = "VOXEL"; rm_.voxel_size = 0.010; sel([cl]); bpy.ops.object.modifier_apply(modifier="slouceni")
# otvory: krk, lem a konce rukávů odříznout rovinou (mazání ploch podle normály nechalo na zaobleném okraji cáry a díry)
bm = bmesh.new(); bm.from_mesh(cl.data); kill = []
cuts = [(Vector((0, 0, ZTOP - 0.008)), Vector((0, 0, 1)), None), (Vector((0, 0, z0)), Vector((0, 0, -1)), None)]
cuts += [(S0 + ax * (RUKAV - 0.008), ax, (S0, ax)) for S0, ax in SLV.values()]
for co_, no_, arm in cuts:
    if arm is None:
        g = bm.verts[:] + bm.edges[:] + bm.faces[:]
    else:                                         # rovina rukávu je nekonečná: řezat jen rukáv, ne sukni na stejné straně
        S0, ax = arm; vin = {v for v in bm.verts if (v.co - S0).dot(ax) > 0.05 and (v.co - (S0 + ax * (v.co - S0).dot(ax))).length < 0.12}
        g = list(vin) + [e for e in bm.edges if all(v in vin for v in e.verts)] + [f for f in bm.faces if all(v in vin for v in f.verts)]
    bmesh.ops.bisect_plane(bm, geom=g, plane_co=co_, plane_no=no_, clear_outer=True)
bm.to_mesh(cl.data); bm.free(); cl.data.update()
print("INFO tunika jeden kus: vrcholu", len(cl.data.vertices), flush=True)
bpy.data.objects.remove(tun, do_unlink=True)
transfer(cl)                                                      # váhy z těla; pod opaskem jen pánev (látka tam visí volně)
sel([cl]); bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.object.vertex_group_smooth(group_select_mode="ALL", factor=0.5, repeat=15)   # v podpaží skáčou váhy z paže na trup a látka se trhá
bpy.ops.object.mode_set(mode="OBJECT")
_Ct = co(cl); below = np.nonzero(_Ct[:, 2] < BELT_C - 0.02)[0].tolist()
for g in list(cl.vertex_groups): g.remove(below)
(cl.vertex_groups.get("root") or cl.vertex_groups.new(name="root")).add(below, 1.0, "REPLACE")
cl.parent = rig; am = cl.modifiers.new("kostra", "ARMATURE"); am.object = rig
pin = cl.vertex_groups.new(name="pin")
for v in cl.data.vertices: pin.add([v.index], float(np.clip((v.co.z - (BELT_C - 0.09)) / 0.07, 0, 1)), "REPLACE")   # nad opaskem drží tělo
cm = cl.modifiers.new("latka", "CLOTH"); s_ = cm.settings
s_.quality = 12; s_.mass = 0.25; s_.tension_stiffness = 80; s_.compression_stiffness = 80; s_.shear_stiffness = 20; s_.bending_stiffness = 2.0   # tužší: měkká látka se prověsila o 9 cm
s_.air_damping = 2.0; s_.vertex_group_mass = "pin"; s_.pin_stiffness = 1.0
cm.collision_settings.distance_min = 0.006; cm.collision_settings.collision_quality = 4; cm.point_cache.frame_start = 1; cm.point_cache.frame_end = 60
so = cl.modifiers.new("tloustka", "SOLIDIFY"); so.thickness = 0.003; so.offset = 1
sb = cl.modifiers.new("hladka", "SUBSURF"); sb.levels = 1; sb.render_levels = 2
mt = bpy.data.materials.new("tunika_vlna"); mt.use_nodes = True; bs = mt.node_tree.nodes["Principled BSDF"]
bs.inputs["Base Color"].default_value = (0.20, 0.008, 0.016, 1); bs.inputs["Roughness"].default_value = 1.0
for nm_, v_ in (("Sheen Weight", 0.12), ("Sheen Roughness", 0.8), ("Specular IOR Level", 0.05), ("Coat Weight", 0.0)):   # matná vlna, ne lesklá guma
    if nm_ in bs.inputs: bs.inputs[nm_].default_value = v_
_ntm = mt.node_tree; _nz = _ntm.nodes.new("ShaderNodeTexNoise"); _nz.inputs["Scale"].default_value = 35; _nz.inputs["Detail"].default_value = 6
_bp = _ntm.nodes.new("ShaderNodeBump"); _bp.inputs["Strength"].default_value = 0.25; _bp.inputs["Distance"].default_value = 0.004   # drobné záhyby a vazba látky
_ntm.links.new(_nz.outputs["Fac"], _bp.inputs["Height"]); _ntm.links.new(_bp.outputs["Normal"], bs.inputs["Normal"])
cl.data.materials.append(mt)
for f in cl.data.polygons: f.use_smooth = True
body.modifiers.new("srazka", "COLLISION"); body.collision.thickness_outer = 0.008

# červené kusy rukávu na boku staré loriky a původní rukáv pryč (rukávy má tunika)
zb = parts["zbroj"]; IMG = next(n.image for m in zb.data.materials if m and m.node_tree for n in m.node_tree.nodes if n.type == "TEX_IMAGE" and n.image)
TWD, TH = IMG.size; TEX = np.empty(TWD * TH * 4, np.float32); IMG.pixels.foreach_get(TEX); TEX = TEX.reshape(TH, TWD, 4)
uvz = zb.data.uv_layers.active.data; UV = np.empty(len(uvz) * 2); uvz.foreach_get("uv", UV); UV = UV.reshape(-1, 2)
LFz = np.repeat(np.arange(len(zb.data.polygons)), [p_.loop_total for p_ in zb.data.polygons])
fuv = np.zeros((len(zb.data.polygons), 2)); np.add.at(fuv, LFz, UV); fuv /= np.bincount(LFz, minlength=len(zb.data.polygons))[:, None]
px = TEX[np.clip((fuv[:, 1] * TH).astype(int), 0, TH - 1), np.clip((fuv[:, 0] * TWD).astype(int), 0, TWD - 1), :3]
redall = px[:, 0] > 1.8 * np.maximum(px[:, 1], px[:, 2])
bm = bmesh.new(); bm.from_mesh(zb.data); bm.faces.ensure_lookup_table()
bmesh.ops.delete(bm, geom=[bm.faces[i] for i in np.nonzero(redall)[0]], context="FACES"); bm.to_mesh(zb.data); bm.free(); zb.data.update()
bpy.data.objects.remove(parts["rukav"], do_unlink=True)
hm = parts["helma"]; _eb = body.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh()
fbvh = BVHTree.FromPolygons([tuple(body.matrix_world @ v.co) for v in _eb.vertices], [p_.vertices[:] for p_ in _eb.polygons])
hc = [p_.center for p_ in hm.data.polygons]
_hu = np.empty(len(hm.data.loops) * 2); hm.data.uv_layers.active.data.foreach_get("uv", _hu); _hu = _hu.reshape(-1, 2)
_hl = np.repeat(np.arange(len(hm.data.polygons)), [p_.loop_total for p_ in hm.data.polygons]); _hf = np.zeros((len(hm.data.polygons), 2)); np.add.at(_hf, _hl, _hu); _hf /= np.bincount(_hl, minlength=len(hm.data.polygons))[:, None]
_hc = _tx[np.clip((_hf[:, 1] * _th).astype(int), 0, _th - 1), np.clip((_hf[:, 0] * _tw).astype(int), 0, _tw - 1), :3]
skinlike = ((_hc.max(1) - _hc.min(1)) / np.maximum(_hc.max(1), 1e-6) > 0.25) & (_hc[:, 0] > 0.35)
onface = np.array([(fbvh.find_nearest(c)[3] or 1) < 0.008 and c.z < mp("head").z + 0.10 and c.y < mp("head").y for c in hc]) & skinlike
bm = bmesh.new(); bm.from_mesh(hm.data); bm.faces.ensure_lookup_table()
bmesh.ops.delete(bm, geom=[bm.faces[i] for i in np.nonzero(onface)[0]], context="FACES")
bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
bm.to_mesh(hm.data); bm.free(); hm.data.update()   # vyhlazení okraje na rozsypané síti trhá přilbu (praskliny): nepoužívat
print("INFO prilba zbytky obliceje", int(onface.sum()), flush=True)
# drobné odtržené kousky (třísky plechu po vyříznutí látky a obličeje) pryč
def drop_islands(o, frac=0.004, minf=40):
    bm = bmesh.new(); bm.from_mesh(o.data); bm.faces.ensure_lookup_table(); seen = set(); kill = []
    lim = max(minf, int(len(bm.faces) * frac))
    for f0 in bm.faces:
        if f0.index in seen: continue
        st = [f0]; comp = []
        while st:
            f = st.pop()
            if f.index in seen: continue
            seen.add(f.index); comp.append(f)
            for e in f.edges:
                for g in e.link_faces:
                    if g.index not in seen: st.append(g)
        if len(comp) < lim: kill += comp
    bmesh.ops.delete(bm, geom=kill, context="FACES"); bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    bm.to_mesh(o.data); bm.free(); o.data.update(); return len(kill)
# drop_islands nepoužívat: původní model je z tisíců samostatných kousků (vyzkoušeno, roztrhá zbroj)
exec(open(os.path.join(TD, "nahrad_vystroj.py"), encoding="utf-8").read())
# tělo pod plechem a přilbou skrýt (obličej, paže a nohy ne)
_PL = [parts[g] for g in ("zbroj", "ramena", "helma", "opasek") if g in parts]
BVa = BVHTree.FromPolygons(sum([[tuple(o.matrix_world @ v.co) for v in o.data.vertices] for o in _PL], []),
                           [[i + off for i in p_.vertices] for off, o in zip(np.cumsum([0] + [len(o.data.vertices) for o in _PL[:-1]]), _PL) for p_ in o.data.polygons])
GI = {g.index: g.name for g in body.vertex_groups}; ids = []; BONES_ = set(b.name for b in rig.data.bones)
zneck = mp("neck01").z; zhip = mp("upperleg01.L").z; MWb = body.matrix_world
for vb in body.data.vertices:                                   # původní síť, ne vyhodnocená (jiné pořadí vrcholů)
    bg = [g for g in vb.groups if GI[g.group] in BONES_]                # jen skupiny kostí (MPFB má i skupiny Left/Right přes celou polovinu těla)
    top = GI[max(bg, key=lambda g: g.weight).group] if bg else ""
    z = (MWb @ vb.co).z
    if top.startswith("upperarm"):                                # nadloktí pod rukávem tuniky: látka tuniky, kdyby kůže rukávem prošla
        S0_, ax_ = SLV["L" if (MWb @ vb.co).x > 0 else "R"]
        if ((MWb @ vb.co) - S0_).dot(ax_) < RUKAV - 0.015: ids.append(vb.index)
        continue
    if not top or top.startswith(("upperarm", "lowerarm", "wrist", "finger", "metacarpal", "neck", "head", "upperleg", "lowerleg", "foot", "toe")): continue
    if zhip < z < zneck: ids.append(vb.index)                   # trup od boků ke krku je pod tunikou
ids_s = set(ids); body.data.materials.append(mt); mi = len(body.data.materials) - 1
for f in body.data.polygons:
    if all(i in ids_s for i in f.vertices): f.material_index = mi
# trup a ramena u plechu zatlačit 8 mm pod jeho vnitřní stranu. Směr bere paprsek od osy těla (páteř, u ramene ramenní kloub) přes vrchol:
# první zásah do plechu blíž než vrchol + 8 mm = vrchol je vně nebo těsně pod plechem. Normály z generátoru nejsou spolehlivé.
MWi = MWb.inverted(); npush = 0; ZBELT = float(co(parts["opasek"])[:, 2].max()) + 0.02
_s0, _s1 = mp("root"), mp("neck01"); _sa = (_s1 - _s0).normalized()
for i in ids:
    v = body.data.vertices[i]; p_ = MWb @ v.co
    if p_.z < ZBELT: continue                                   # u boků ne: rozhodí látku sukně
    c = mp("upperarm01.L") if p_.x > 0.12 else mp("upperarm01.R") if p_.x < -0.12 else _s0 + _sa * (p_ - _s0).dot(_sa)
    L_ = (p_ - c).length
    if L_ < 1e-4: continue
    d = (p_ - c) / L_; hit = BVa.ray_cast(c, d, L_ + 0.008)[0]
    if hit is not None:
        v.co = MWi @ (hit - d * 0.012); npush += 1
body.data.update(); print("INFO trup zatlacen pod plech", npush, flush=True)
# tunika pod plechem stejně: 5 mm pod jeho vnitřní stranou (tělo je 12 mm pod ním, zůstane uvnitř tuniky)
ntp = 0; MWt = cl.matrix_world; MWti = MWt.inverted()
bpy.context.view_layer.update(); _eb2 = body.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh()   # tělo už zatlačené pod plech, bez pomocné geometrie
abvh2 = BVHTree.FromPolygons([tuple(MWb @ v.co) for v in _eb2.vertices], [p_.vertices[:] for p_ in _eb2.polygons])
_op = parts["opasek"]; BVo = BVHTree.FromPolygons([tuple(_op.matrix_world @ v.co) for v in _op.data.vertices], [p_.vertices[:] for p_ in _op.data.polygons])
ZPAS = ZBELT - 0.02 - 0.05 * 1.35 - 0.005                         # spodní hrana pásu opasku (pás 5 cm × 1,35 v nahrad_vystroj)
for v in cl.data.vertices:
    p_ = MWt @ v.co
    if p_.z < ZPAS: continue
    if p_.z < ZBELT:                                    # pod pásem opasku: látka nesmí prolézt přes jeho spodní hranu
        c = _s0 + _sa * (p_ - _s0).dot(_sa); L_ = (p_ - c).length
        if L_ < 1e-4: continue
        d = (p_ - c) / L_; hit = BVo.ray_cast(c, d, L_ + 0.005)[0]
        if hit is not None:
            rb_ = _ray_far(abvh2, c, d, L_ + 0.02); v.co = MWti @ (c + d * max((hit - c).length - 0.004, rb_ + 0.006)); ntp += 1
        continue
    c = mp("upperarm01.L") if p_.x > 0.12 else mp("upperarm01.R") if p_.x < -0.12 else _s0 + _sa * (p_ - _s0).dot(_sa)
    L_ = (p_ - c).length
    if L_ < 1e-4: continue
    d = (p_ - c) / L_; hit = BVa.ray_cast(c, d, L_ + 0.005)[0]
    if hit is not None:                               # pod plech, ale nikdy pod kůži (u podpaží leží plech těsně u paže)
        rb_ = _ray_far(abvh2, c, d, L_ + 0.02); tgt_ = max((hit - c).length - 0.005, rb_ + 0.008)
        v.co = MWti @ (c + d * tgt_); ntp += 1
cl.data.update(); print("INFO tunika zatlacena pod plech", ntp, flush=True)
print("INFO trup jako tunika vrcholu", len(ids), flush=True)
# kůže: póry a méně vosku (MPFB textura je jen barva)
for m in body.data.materials:
    if not (m and m.use_nodes): continue
    def walk(nt, seen):
        for n in nt.nodes:
            if n.type == "BSDF_PRINCIPLED":
                for nm_, v_ in (("Subsurface Weight", 0.12), ("Roughness", 0.5)):
                    if nm_ in n.inputs and not n.inputs[nm_].is_linked: n.inputs[nm_].default_value = v_
                if not n.inputs["Normal"].is_linked:
                    nz = nt.nodes.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 900; nz.inputs["Detail"].default_value = 6
                    vz = nt.nodes.new("ShaderNodeTexVoronoi"); vz.inputs["Scale"].default_value = 450
                    mx_ = nt.nodes.new("ShaderNodeMath"); mx_.operation = "ADD"
                    bp = nt.nodes.new("ShaderNodeBump"); bp.inputs["Strength"].default_value = 0.25; bp.inputs["Distance"].default_value = 0.0006
                    nt.links.new(nz.outputs["Fac"], mx_.inputs[0]); nt.links.new(vz.outputs["Distance"], mx_.inputs[1]); nt.links.new(mx_.outputs[0], bp.inputs["Height"]); nt.links.new(bp.outputs["Normal"], n.inputs["Normal"])
            if n.type == "GROUP" and n.node_tree and n.node_tree.name not in seen:
                seen.add(n.node_tree.name); walk(n.node_tree, seen)
    walk(m.node_tree, set())
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "postup_b.blend"))
# --- simulace pro každou pózu: klid (snímek 1) -> póza (30), usadit do 50 ---
def prep(pn):
    rig.animation_data_clear(); P = rig.pose.bones; target = {pb.name: pb.matrix_basis.copy() for pb in P}
    for pb in P:
        pb.matrix_basis = Matrix.Identity(4)
        for k in ("location", "rotation_quaternion", "scale"): pb.keyframe_insert(k, frame=1)
        pb.matrix_basis = target[pb.name]
        for k in ("location", "rotation_quaternion", "scale"): pb.keyframe_insert(k, frame=30)
    sc.frame_start, sc.frame_end = 1, 50
    for f in range(1, 51): sc.frame_set(f)
MAP = {"hips": "root", "chest": "spine03", "neck": "neck01"}
for q in ("L", "R"):
    MAP.update({f"{q}_arm": f"upperarm01.{q}", f"{q}_fore": f"lowerarm01.{q}", f"{q}_hand": f"wrist.{q}", f"{q}_upleg": f"upperleg01.{q}", f"{q}_leg": f"lowerleg01.{q}", f"{q}_foot": f"foot.{q}", f"{q}_toe": f"toe3-1.{q}"})
def seg_d(P_, a_, b_):
    ab = b_ - a_; t = np.clip(((P_ - a_) @ ab) / (ab @ ab), 0, 1); return np.linalg.norm(P_ - (a_ + t[:, None] * ab), axis=1)
dl = np.minimum(seg_d(BV, np.array(mp("upperleg01.L")), np.array(mp("lowerleg01.L"))), seg_d(BV, np.array(mp("upperleg01.R")), np.array(mp("lowerleg01.R"))))
skin = np.nonzero((BV[:, 2] > z0 - 0.06) & (BV[:, 2] < hzp) & (dl < 0.11))[0]
run_all({"rig": rig, "MAP": MAP, "body": body, "cloth": cl, "skin_idx": skin, "name": "B", "out_dir": OUT, "prep_pose": prep, "ground_objs": [body] + [parts[g] for g in ("sandal_L", "sandal_R") if g in parts]})
# --- detailní kontrola: klid a běh z 8 stran a výřezy ---
P_ = Poser(rig, MAP); DD = os.path.join(OUT, "detail"); os.makedirs(DD, exist_ok=True)
VIEWS8 = {f"{i:02d}": (math.sin(math.radians(a_)), -math.cos(math.radians(a_)), 0.08) for i, a_ in enumerate(range(0, 360, 45))}
CROPS = {"hlava": (1.52, 0.42), "trup": (1.18, 0.62), "pas": (0.86, 0.62), "nohy": (0.42, 0.75), "chodidla": (0.1, 0.42)}
for pn, pf in (("klid", POSES[0][1]), ("beh_C", POSES[3][1])):
    P_.reset(); pf(P_); P_.ground([body] + [parts[g] for g in ("sandal_L", "sandal_R") if g in parts]); prep(pn); rig.animation_data_clear()
    for vn, d in VIEWS8.items(): shot(sc, os.path.join(DD, f"{pn}-cela-{vn}.png"), d, 2.0, (0, 0, 0.86))
    if pn == "klid":                                    # přesně zepředu a z boku, bez natočení: srovnání s předlohou ve stejném měřítku
        Mi3_ = rig.matrix_world.inverted().to_3x3()        # paže jako na předloze: 55° pod vodorovnou (jen póza pro srovnání)
        _pm0 = {sd: rig.pose.bones[f"upperarm01.{sd}"].matrix.copy() for sd in ("L", "R")}
        for sd, sg in (("L", 1), ("R", -1)):
            pb = rig.pose.bones[f"upperarm01.{sd}"]; h_ = pb.head.copy(); cur = (rig.pose.bones[f"lowerarm01.{sd}"].head - h_).normalized()
            tgt = (Mi3_ @ Vector((sg * math.cos(math.radians(55)), 0, -math.sin(math.radians(55))))).normalized()
            pb.matrix = Matrix.Translation(h_) @ cur.rotation_difference(tgt).to_matrix().to_4x4() @ Matrix.Translation(-h_) @ pb.matrix; bpy.context.view_layer.update()
        def _rovny_loket():                                # v klidové póze je loket ohnutý: předloktí do směru nadloktí
            for sd in ("L", "R"):
                ua, la = rig.pose.bones[f"upperarm01.{sd}"], rig.pose.bones[f"lowerarm01.{sd}"]; h2 = la.head.copy()
                cur2 = (rig.pose.bones[f"wrist.{sd}"].head - h2).normalized(); tgt2 = (h2 - ua.head).normalized()
                la.matrix = Matrix.Translation(h2) @ cur2.rotation_difference(tgt2).to_matrix().to_4x4() @ Matrix.Translation(-h2) @ la.matrix; bpy.context.view_layer.update()
        _rovny_loket()
        shot(sc, os.path.join(OUT, "presne-zepredu.png"), (0, -1, 0), 2.0, (0, 0, 0.86))
        for sd, sg in (("L", 1), ("R", -1)):              # na boční fotce předlohy visí paže podél těla
            pb = rig.pose.bones[f"upperarm01.{sd}"]; h_ = pb.head.copy(); cur = (rig.pose.bones[f"lowerarm01.{sd}"].head - h_).normalized()
            tgt = (Mi3_ @ Vector((sg * 0.12, 0, -1))).normalized()
            pb.matrix = Matrix.Translation(h_) @ cur.rotation_difference(tgt).to_matrix().to_4x4() @ Matrix.Translation(-h_) @ pb.matrix; bpy.context.view_layer.update()
        _rovny_loket(); shot(sc, os.path.join(OUT, "presne-zprava.png"), (-1, 0, 0), 2.0, (0, 0, 0.86))   # předloha ref-right je fotka z pravého boku (-x)
    hipz = (rig.matrix_world @ rig.pose.bones["root"].head).z - mp("root").z
    for cn, (cz, cs_) in CROPS.items():
        for vn, d in (("predek", (0.15, -1, 0.05)), ("bok", (1, 0, 0.05)), ("zada", (-0.15, 1, 0.05)), ("bok2", (-1, 0, 0.05))):
            shot(sc, os.path.join(DD, f"{pn}-{cn}-{vn}.png"), d, cs_, (0, (rig.matrix_world @ rig.pose.bones["root"].head).y, cz + hipz))
print("INFO DONE", flush=True)
