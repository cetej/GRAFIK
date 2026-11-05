# Vyráběné díly legionáře nahrazené vymodelovanými (0 USD), položené přes původní tvar z generátoru:
# pugio v pochvě na levém boku (původní dýka zatlačena do boku), puklice štítu,
# kování zbroje jako kov (maska z barvy textury, malba štítu zůstane matná).
# blender -b --factory-startup --python dily_kov.py -- <in.glb> <out.glb> <render_dir> <hdri.exr>
import bpy, bmesh, sys, os
import numpy as np
from mathutils import Vector, Matrix

args = sys.argv[sys.argv.index("--") + 1:]
IN, OUT, RDIR, HDRI = (os.path.abspath(a) for a in args[:4])
os.makedirs(RDIR, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=IN)
body = max((o for o in bpy.context.scene.objects if o.type == "MESH"), key=lambda o: len(o.data.vertices))
bpy.context.view_layer.objects.active = body
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
me = body.data

# původní dýka z generátoru je srostlá s tělem (síť je jeden kus) a trčí šikmo z boku: zatlačit ji do povrchu
# (operátor: dýka zaražená v boku). Meč z generátoru zůstává, vymodelovaný přes něj dělal zdvojení.
bm = bmesh.new(); bm.from_mesh(me)
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)  # švy UV rozpojují síť, vyhlazení by ji roztrhlo


bm.verts.ensure_lookup_table()
P0 = np.array([v.co for v in bm.verts])


def push_radial(a0, a1, z0, z1, margin=0.006):
    """Body v úhlovém okně dál od osy než povrch boku (z okolních úhlů, jen r < 0,16 – štít ne) zatlačit dovnitř."""
    ang = np.degrees(np.arctan2(P0[:, 1] - 0.006, P0[:, 0] + 0.008)); rr = np.hypot(P0[:, 0] + 0.008, P0[:, 1] - 0.006)
    n_ = 0
    for zz in np.arange(z0, z1, 0.01):
        ring = (((ang > a0 - 8) & (ang < a0 - 2)) | ((ang > a1 + 2) & (ang < a1 + 8))) & (np.abs(P0[:, 2] - zz) < 0.005) & (rr < 0.16)
        if ring.sum() < 3: continue
        rb = float(np.percentile(rr[ring], 70))
        for k in np.where((ang > a0) & (ang < a1) & (np.abs(P0[:, 2] - zz) < 0.005) & (rr > rb + margin) & (rr < 0.16))[0]:  # štít leží dál než 0,16
            v = bm.verts[int(k)]; d = Vector((v.co.x + 0.008, v.co.y - 0.006, 0)).normalized()
            v.co.x = -0.008 + d.x * (rb - 0.002); v.co.y = 0.006 + d.y * (rb - 0.002); n_ += 1
    return n_


print("push dagger", push_radial(8.0, 28.0, 0.55, 0.71))
bm.to_mesh(me); bm.free()
co = np.array([v.co for v in me.vertices]); x, y, z = co.T


def metal(name, rgb, rough, metallic=1.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1); b.inputs["Metallic"].default_value = metallic
    b.inputs["Roughness"].default_value = rough
    return m


BRASS = metal("mosaz", (0.62, 0.38, 0.11), 0.45)
WOOD = metal("drevo", (0.30, 0.15, 0.07), 0.55, 0.0)
new = []


def place(o, mat, frame, origin):
    o.matrix_world = Matrix.Translation(origin) @ frame.to_4x4() @ o.matrix_world
    o.data.materials.append(mat); new.append(o)
    return o


# ---- 1) kování jako kov: maska z barvy, mimo štít ----
nt = me.materials[0].node_tree
bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
btex = next(n for n in nt.nodes if n.type == "TEX_IMAGE" and n.image.colorspace_settings.name != "Non-Color")
img = btex.image; w, h = img.size
px = np.array(img.pixels[:], np.float32).reshape(h, w, 4)[..., :3]


def box_blur(a, rr):
    for ax in (0, 1):
        p = np.pad(a, [(rr + 1, rr) if i == ax else (0, 0) for i in range(a.ndim)], mode="edge")
        c = np.cumsum(p, axis=ax)
        a = (np.take(c, range(2 * rr + 1, c.shape[ax]), axis=ax) - np.take(c, range(0, c.shape[ax] - 2 * rr - 1), axis=ax)) / (2 * rr + 1)
    return a


ps = box_blur(px, 3)  # masky z rozmazané kopie: zrno textury jinak dělá z kovu „písek“
mx = ps.max(2); mn = ps.min(2); sat = (mx - mn) / np.maximum(mx, 1e-4)
r, g, b = ps[..., 0], ps[..., 1], ps[..., 2]
hue = np.degrees(np.arctan2(np.sqrt(3) * (g - b), 2 * r - g - b)) % 360
steel = (sat < 0.14) & (mx > 0.38)
uv = np.zeros((len(me.loops), 2)); me.uv_layers.active.data.foreach_get("uv", uv.ravel())
lv = np.zeros(len(me.loops), int); me.loops.foreach_get("vertex_index", lv)


def splat(vmask, grow):
    m = np.zeros((h, w), bool); on_ = vmask[lv]
    m[np.clip((uv[on_, 1] * h).astype(int), 0, h - 1), np.clip((uv[on_, 0] * w).astype(int), 0, w - 1)] = True
    for _ in range(grow):
        p = np.pad(m, 1); m = p[1:-1, 1:-1] | p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:]
    return m


# kování má stejný odstín jako obličej (18–23°), barva je nerozliší: béžové texely u oceli, na trupu, mimo kůži paží (<16°)
near_steel = steel.copy()
for _ in range(8):
    p = np.pad(near_steel, 1); near_steel = p[1:-1, 1:-1] | p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:]
torso = splat((z > 0.5) & (z < 0.84) & (np.abs(x) < 0.17), 7)
beige = (hue > 16) & (hue < 45) & (sat > 0.22) & (sat < 0.6) & (mx > 0.55)
print("beige %", round(beige.mean() * 100, 2), "near steel %", round((beige & near_steel).mean() * 100, 2),
      "torso %", round((beige & torso).mean() * 100, 2), "both %", round((beige & near_steel & torso).mean() * 100, 2))
gold = beige & torso
for op in ("dil", "dil", "ero", "ero"):  # uzavření: zaplnit tečky v lemech
    p = np.pad(gold, 1, constant_values=(op == "ero"))
    nb = (p[:-2, 1:-1], p[2:, 1:-1], p[1:-1, :-2], p[1:-1, 2:])
    gold = gold | np.logical_or.reduce(nb) if op == "dil" else gold & np.logical_and.reduce(nb)
gold &= torso & (hue > 14) & (mx > 0.45)
# přilba: lemy lícnic a týlního chrániče, čelní pásek, knoflík chocholu; obličej a krk vpředu vynechat
helmet = splat(z > 0.80, 7)
# v oblasti obličeje rozhoduje odstín: pleť 7–12°, lem lícnic a čela 15–23° (měřeno sondou)
face = splat((np.abs(x) < 0.045) & (z > 0.80) & (z < 0.937) & (y < 0.0), 2) & (hue < 15.5)
hgold = beige & helmet & ~face
gold |= hgold
print("helmet brass %", round(hgold.mean() * 100, 2))
# světlé narůžovělé šmouhy na přilbě a zbroji (zapečené odlesky) jsou taky ocel
pale = (sat < 0.26) & (helmet | torso) & ~face & ~gold  # i tmavé: černé skvrny jsou stín zapečený z fotky, ne barva
print("pale→steel %", round((pale & ~steel).mean() * 100, 2))
steel |= pale
# texely štítu (malba křídel a lemů je barva, ne kov): plochy se středem v oblasti štítu
shield_v = (x > 0.05) & (z < 0.585) & (y < 0.0)
on = shield_v[lv]
smask = np.zeros((h, w), bool)
uu = np.clip((uv[on, 0] * w).astype(int), 0, w - 1); vv = np.clip((uv[on, 1] * h).astype(int), 0, h - 1)
smask[vv, uu] = True
for _ in range(4):
    p = np.pad(smask, 1); smask = p[1:-1, 1:-1] | p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:]
gold &= ~smask
print("steel %", round(steel.mean() * 100, 1), "gold %", round(gold.mean() * 100, 1), "shield texels %", round(smask.mean() * 100, 1))
base = px.copy()
for op in ("dil", "dil", "dil", "ero", "ero", "ero"):  # uzavření celé masky mosazi (i přilby), díry mají 2–3 px
    p = np.pad(gold, 1, constant_values=(op == "ero"))
    nb = (p[:-2, 1:-1], p[2:, 1:-1], p[1:-1, :-2], p[1:-1, 2:])
    gold = gold | np.logical_or.reduce(nb) if op == "dil" else gold & np.logical_and.reduce(nb)
# mosaz jednotným tónem (tečky v textuře generátoru by dělaly mozaiku), jen 30 % původní kresby
lum = base[gold].mean(1, keepdims=True)
base[gold] = np.clip(0.9 * np.array([0.80, 0.58, 0.28]) + 0.1 * lum * np.array([1.0, 0.75, 0.4]), 0, 1)
# ocel: zapečené odlesky a stíny z fotky dělají na kovu skvrny, jas stáhnout k šedé
sl = base[steel].mean(1, keepdims=True)
base[steel] = np.clip(0.55 + (sl - 0.55) * 0.3, 0, 1) * np.array([0.98, 1.0, 1.03])
img.pixels[:] = np.concatenate([base, np.ones((h, w, 1), np.float32)], 2).ravel(); img.pack()
metal_v = np.where(steel, 1.0, np.where(gold, 0.95, 0.0)); rough_v = np.where(steel, 0.28, np.where(gold, 0.3, 0.65))
mr = bpy.data.images.new("metal_rough_v4", w, h); mr.colorspace_settings.name = "Non-Color"
mr.pixels[:] = np.stack([np.zeros_like(rough_v), rough_v, metal_v, np.ones_like(rough_v)], 2).astype(np.float32).ravel(); mr.pack()
for l in list(nt.links):
    if l.to_node == bsdf and l.to_socket.name in ("Metallic", "Roughness"):
        nt.links.remove(l)
mt = nt.nodes.new("ShaderNodeTexImage"); mt.image = mr
if btex.inputs["Vector"].links:
    nt.links.new(btex.inputs["Vector"].links[0].from_socket, mt.inputs["Vector"])
sep = nt.nodes.new("ShaderNodeSeparateColor"); nt.links.new(mt.outputs["Color"], sep.inputs["Color"])
nt.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"]); nt.links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])

# ---- 2) puklice štítu ----
# podložní deska je béžová skvrna uprostřed štítu: rovina desky z PCA, kopule = body vysoko nad rovinou
pc = np.zeros(len(co)); vcol = np.zeros((len(co), 3))
vcol[lv] = px[np.clip((uv[:, 1] * h).astype(int), 0, h - 1), np.clip((uv[:, 0] * w).astype(int), 0, w - 1)]
vmx = vcol.max(1); vsat = (vmx - vcol.min(1)) / np.maximum(vmx, 1e-4)
vhue = np.degrees(np.arctan2(np.sqrt(3) * (vcol[:, 1] - vcol[:, 2]), 2 * vcol[:, 0] - vcol[:, 1] - vcol[:, 2])) % 360
pl = (x > 0.18) & (z > 0.2) & (z < 0.36) & (vhue > 20) & (vhue < 50) & (vsat > 0.12) & (vsat < 0.5) & (vmx > 0.55)
P = co[pl]; pcen = P.mean(0); _, _, vt = np.linalg.svd(P - pcen); n_ = vt[2] if vt[2][1] < 0 else -vt[2]
hg = (P - pcen) @ n_
D = P[hg > 0.5 * hg.max()]; dc = D.mean(0); base_pt = dc - ((dc - pcen) @ n_) * n_
rad = float(np.percentile(np.linalg.norm((D - dc) - np.outer((D - dc) @ n_, n_), axis=1), 95))
R = max(rad, 0.022) * 1.5; Hd = float(hg.max()) + 0.004  # překrýt celé původní vyboulení
# osa = skutečná normála štítu (průměr normál prstence 5–7,5 cm kolem desky; PCA desky se lišila o 12° → nakřivo),
# střed = průmět vrcholu původního vyboulení do roviny prstence
nrv = np.array([v.normal for v in me.vertices])
dist_ = np.linalg.norm(co - pcen, axis=1)
ring_ = (dist_ > 0.05) & (dist_ < 0.075) & (x > 0.15) & (nrv[:, 0] > 0.3)
n_ = nrv[ring_].mean(0); n_[2] = 0.0; n_ /= np.linalg.norm(n_)
rc = co[ring_].mean(0)
core_ = (dist_ < 0.045) & (x > 0.15)
apex = co[core_][np.argmax((co[core_] - rc) @ n_)]
Hd = float((apex - rc) @ n_) + 0.003
nrm = Vector(n_.tolist()); surf = Vector((apex - (Hd - 0.003) * n_).tolist())
print("boss base", tuple(round(c, 3) for c in surf), "normal", tuple(round(c, 3) for c in nrm), "R", round(R, 4), "height", round(Hd, 4))
bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=R)
boss = bpy.context.object; boss.scale = (1, 1, Hd / R)
bpy.ops.object.transform_apply(scale=True)
for f in boss.data.polygons: f.use_smooth = True
frame = nrm.to_track_quat("Z", "Y").to_matrix()
place(boss, BRASS, frame, surf)  # bez rovného kroužku: na prohnutém štítu z jedné strany zapadal

# ---- 3) osa meče (jen pro kontrolní záběry) ----
# osa ze svislého profilu (levý okraj pochvy, střed jílce); přední plocha pochvy y ≈ -0,065 a výš mírně ustupuje
up = Vector((0.0, 0.05, 1.0)).normalized()
# po vyhlazení původního meče: přední povrch těla v ose pochvy, pochva (tloušťka 0,017) k němu přiléhá
col_ = (np.abs(x + 0.114) < 0.01) & (z > 0.36) & (z < 0.56) & (y < 0.0)
y_bg = float(np.median([y[col_ & (np.abs(z - zz) < 0.01)].min() for zz in np.arange(0.37, 0.56, 0.02) if (col_ & (np.abs(z - zz) < 0.01)).any()]))
c0 = Vector((-0.114, y_bg - 0.0085 - 0.002, 0.469))
print("sword surface y", round(y_bg, 4), "centre", tuple(round(c, 3) for c in c0))
def at(zz):
    return c0 + up * ((zz - c0.z) / up.z)
wdir = up.cross(Vector((0, 1, 0))).normalized()  # šířka pochvy ~ osa X
tdir = wdir.cross(up).normalized()
F = Matrix((wdir, tdir, up)).transposed()  # lokální X šířka, Y tloušťka, Z osa
z_top, z_bot = 0.610, 0.300
L = (z_top - z_bot) / up.z
# vymodelovaný gladius vyřazen (operátor: meč zdvojený); zůstává původní meč z generátoru, osa `at` jen pro kontrolní záběry

# ---- 4) pugio v pochvě na levém boku (původní dýka trčela šikmo z boku, čepel v těle) ----
# povrch boku v úhlu 17° (měřeno): tunika dole r 0,124, pas 0,098, opasek 0,115, zbroj 0,13 → pochva dole u tuniky,
# rukojeť venku před zbrojí (jinak je uvnitř a „chybí“), k opasku dvě kožená poutka (jinak „visí ve vzduchu“)
IRON = metal("zelezo_pugio", (0.38, 0.38, 0.40), 0.4)
LEATH = metal("kuze_poutko", (0.16, 0.09, 0.05), 0.7, 0.0)
th = np.radians(17.0)
out_ = Vector((np.cos(th), np.sin(th), 0.0)); tan_ = Vector((0, 0, 1)).cross(out_).normalized()
ang_ = np.degrees(np.arctan2(y - 0.006, x + 0.008)); rr = np.hypot(x + 0.008, y - 0.006)
def r_at(zz):
    s_ = (np.abs(ang_ - 17.0) < 4) & (np.abs(z - zz) < 0.008) & (rr < 0.16)
    return float(np.percentile(rr[s_], 90))
pz_top, pz_bot = 0.585, 0.455
def P(r, zz):
    return Vector((-0.008 + r * out_.x, 0.006 + r * out_.y, zz))
Pb = P(r_at(0.46) + 0.008, pz_bot); Pt = P(r_at(0.60) + 0.0065 + 0.004, 0.615)
up_p = (Pt - Pb).normalized()
yp = up_p.cross(tan_).normalized() * -1
if yp.dot(out_) < 0: yp = -yp
Fp = Matrix((tan_, yp, up_p)).transposed()  # X šířka, Y ven, Z podél osy
def pat(zz):
    return Pb + up_p * ((zz - Pb.z) / up_p.z)
print("pugio bottom", tuple(round(c, 3) for c in Pb), "hilt", tuple(round(c, 3) for c in Pt), "belt r", round(r_at(0.58), 3))
bpy.ops.mesh.primitive_cube_add(size=1); sh = bpy.context.object
bm = bmesh.new(); bm.from_mesh(sh.data)
for v in bm.verts:
    v.co.x *= 0.034; v.co.y *= 0.012; v.co.z *= (pz_top - pz_bot)
    if v.co.z < 0: v.co.x *= 0.55
bm.to_mesh(sh.data); bm.free()
bpy.ops.object.modifier_add(type="BEVEL"); sh.modifiers[-1].width = 0.003; sh.modifiers[-1].segments = 3
bpy.ops.object.modifier_apply(modifier=sh.modifiers[-1].name)
place(sh, IRON, Fp, pat((pz_top + pz_bot) / 2))
for zz, hh, wf in ((0.578, 0.008, 1.0), (0.548, 0.006, 0.9), (0.515, 0.006, 0.8)):
    bpy.ops.mesh.primitive_cube_add(size=1); bd = bpy.context.object
    bd.scale = (0.037 * wf, 0.015, hh); bpy.ops.object.transform_apply(scale=True)
    place(bd, BRASS, Fp, pat(zz))
for sgn in (-1, 1):  # kroužky závěsu a poutka k opasku
    bpy.ops.mesh.primitive_torus_add(major_radius=0.005, minor_radius=0.0014, major_segments=16, minor_segments=8)
    rg = bpy.context.object; rg.rotation_euler = (1.5708, 0, 0); bpy.ops.object.transform_apply(rotation=True)
    ring_pos = pat(0.565) + tan_ * sgn * 0.021
    place(rg, BRASS, Fp, ring_pos)
    belt_pt = P(r_at(0.58) + 0.002, 0.582) + tan_ * sgn * 0.016
    seg = belt_pt - ring_pos; L_ = seg.length
    bpy.ops.mesh.primitive_cube_add(size=1); st = bpy.context.object
    st.scale = (0.006, 0.002, L_ + 0.004); bpy.ops.object.transform_apply(scale=True)
    Fs = Matrix((tan_, seg.normalized().cross(tan_).normalized(), seg.normalized())).transposed()
    place(st, LEATH, Fs, (belt_pt + ring_pos) / 2)
bpy.ops.mesh.primitive_uv_sphere_add(segments=20, ring_count=10, radius=0.007)
tk = bpy.context.object; place(tk, BRASS, Fp, pat(pz_bot - 0.004))
bpy.ops.mesh.primitive_cube_add(size=1); gd = bpy.context.object  # záštita
gd.scale = (0.032, 0.013, 0.007); bpy.ops.object.transform_apply(scale=True); place(gd, IRON, Fp, pat(pz_top + 0.004))
bpy.ops.mesh.primitive_cylinder_add(vertices=20, radius=0.007, depth=0.042); gr = bpy.context.object
for f in gr.data.polygons: f.use_smooth = True
place(gr, WOOD, Fp, pat(pz_top + 0.029))
bpy.ops.mesh.primitive_uv_sphere_add(segments=20, ring_count=10, radius=1); sw = bpy.context.object  # zesílení uprostřed rukojeti
sw.scale = (0.0105, 0.009, 0.0075); bpy.ops.object.transform_apply(scale=True)
for f in sw.data.polygons: f.use_smooth = True
place(sw, IRON, Fp, pat(pz_top + 0.029))
bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.015, depth=0.007); pm = bpy.context.object  # plochá hlavice
pm.rotation_euler = (1.5708, 0, 0); bpy.ops.object.transform_apply(rotation=True)
place(pm, IRON, Fp, pat(pz_top + 0.057))
for sgn in (-1, 0, 1):  # mosazné nýty v hlavici
    bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=6, radius=0.0028); rv = bpy.context.object
    place(rv, BRASS, Fp, pat(pz_top + 0.057) + tan_ * sgn * 0.009 + yp * 0.004)
for o in new:
    o.name = "dily_kov"
print("parts", len(new))

bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB")
print("exported", OUT)

sc = bpy.context.scene
sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = 48; sc.cycles.use_denoising = True
sc.render.resolution_x = sc.render.resolution_y = 1024
wd = bpy.data.worlds.new("w"); sc.world = wd; wd.use_nodes = True
env = wd.node_tree.nodes.new("ShaderNodeTexEnvironment"); env.image = bpy.data.images.load(HDRI)
wd.node_tree.links.new(env.outputs["Color"], wd.node_tree.nodes["Background"].inputs["Color"])
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); cam.data.type = "ORTHO"; sc.collection.objects.link(cam); sc.camera = cam
ctr = Vector(((co.min(0) + co.max(0)) / 2).tolist()); size = float((co.max(0) - co.min(0)).max())
shots = {"zepredu": ((0, -1, 0.15), ctr, size * 1.1),
         "mec": ((-0.6, -1, 0.15), at(0.5), 0.36),
         "mec_zboku": ((-1, 0, 0.1), at(0.52), 0.42),
         "mec_zezadu": ((-0.6, 1, 0.2), at(0.52), 0.42),
         "dyka_zboku": ((1, 0.2, 0.1), pat(0.56), 0.3),
         "dyka_zezadu": ((0.6, 1, 0.3), pat(0.56), 0.3),
         "puklice_zepredu": ((0, -1, 0.05), surf, 0.3),
         "puklice_zboku": ((1, 0, 0.05), surf, 0.3),
         "dyka_zepredu": ((0.3, -1, 0.1), pat(0.55), 0.3),
         "mec_shora": ((-0.5, -0.6, 1.0), at(0.6), 0.42),
         "puklice": (tuple(nrm + Vector((0, 0, 0.2))), surf, 0.3),
         "zbroj": ((0.25, -1, 0.2), Vector((0.0, -0.05, 0.75)), 0.34),
         "prilba": ((-0.5, -1, 0.35), Vector((0.0, 0.0, 0.91)), 0.22),
         "prilba_zezadu": ((0.4, 1, 0.3), Vector((0.0, 0.0, 0.9)), 0.24),
         "sikmo": ((-0.7, -0.7, 0.3), ctr, size * 1.1)}
for name, (dvec, tgt, scale) in shots.items():
    dv = Vector(dvec).normalized(); cam.data.ortho_scale = scale
    cam.location = tgt + dv * size * 3
    cam.rotation_euler = (-dv).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = os.path.join(RDIR, f"{name}.png")
    bpy.ops.render.render(write_still=True)
print("DONE")
