# Vyráběné díly legionáře nahrazené vymodelovanými (0 USD), položené přes původní tvar z generátoru:
# gladius v pochvě (hlavice, rukojeť, záštita, pochva s kováním a koncovkou), puklice štítu,
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
co = np.array([v.co for v in me.vertices]); x, y, z = co.T


def metal(name, rgb, rough, metallic=1.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1); b.inputs["Metallic"].default_value = metallic
    b.inputs["Roughness"].default_value = rough
    return m


BRASS = metal("mosaz", (0.62, 0.38, 0.11), 0.45)
LEATHER = metal("pochva_kuze", (0.010, 0.011, 0.024), 0.8, 0.0)
WOOD = metal("drevo", (0.30, 0.15, 0.07), 0.55, 0.0)
BONE = metal("kost", (0.78, 0.70, 0.55), 0.5, 0.0)
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
nrm = Vector(n_.tolist()); surf = Vector(base_pt.tolist())
print("boss base", tuple(round(c, 3) for c in surf), "normal", tuple(round(c, 3) for c in nrm), "R", round(R, 4), "height", round(Hd, 4))
bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=R)
boss = bpy.context.object; boss.scale = (1, 1, (Hd + 0.002) / R)
bpy.ops.object.transform_apply(scale=True)
for f in boss.data.polygons: f.use_smooth = True
frame = nrm.to_track_quat("Z", "Y").to_matrix()
place(boss, BRASS, frame, surf)
bpy.ops.mesh.primitive_torus_add(major_radius=R * 1.04, minor_radius=0.003, major_segments=48, minor_segments=12)
rim = bpy.context.object
for f in rim.data.polygons: f.use_smooth = True
place(rim, BRASS, frame, surf + nrm * 0.001)

# ---- 3) gladius v pochvě ----
# osa ze svislého profilu (levý okraj pochvy, střed jílce); přední plocha pochvy y ≈ -0,065 a výš mírně ustupuje
up = Vector((0.0, 0.05, 1.0)).normalized()
c0 = Vector((-0.114, -0.061, 0.469))
def at(zz):
    return c0 + up * ((zz - c0.z) / up.z)
wdir = up.cross(Vector((0, 1, 0))).normalized()  # šířka pochvy ~ osa X
tdir = wdir.cross(up).normalized()
F = Matrix((wdir, tdir, up)).transposed()  # lokální X šířka, Y tloušťka, Z osa
z_top, z_bot = 0.610, 0.300
L = (z_top - z_bot) / up.z
# pochva: zužující se kvádr
bpy.ops.mesh.primitive_cube_add(size=1)
sc_ = bpy.context.object
bm = bmesh.new(); bm.from_mesh(sc_.data)
for v in bm.verts:
    v.co.x *= 0.048; v.co.y *= 0.021; v.co.z *= L
    if v.co.z < 0: v.co.x *= 0.78
bm.to_mesh(sc_.data); bm.free()
bpy.ops.object.modifier_add(type="BEVEL"); sc_.modifiers[-1].width = 0.004; sc_.modifiers[-1].segments = 3
bpy.ops.object.modifier_apply(modifier=sc_.modifiers[-1].name)
place(sc_, LEATHER, F, at((z_top + z_bot) / 2))
# kování pochvy: dvě objímky s kroužky nahoře, jedna uprostřed, koncovka dole
for zz, hh in ((0.598, 0.024), (0.548, 0.014), (0.47, 0.012), (0.395, 0.012)):
    bpy.ops.mesh.primitive_cube_add(size=1); band = bpy.context.object
    frac = (z_top - zz) / (z_top - z_bot); wfac = 1 - 0.22 * frac
    band.scale = (0.052 * wfac, 0.027, hh); bpy.ops.object.transform_apply(scale=True)
    bpy.ops.object.modifier_add(type="BEVEL"); band.modifiers[-1].width = 0.0035; band.modifiers[-1].segments = 4
    bpy.ops.object.modifier_apply(modifier=band.modifiers[-1].name)
    for f in band.data.polygons: f.use_smooth = True
    place(band, BRASS, F, at(zz))
for zz in (0.598, 0.548):  # kroužky závěsu po stranách
    for s in (-1, 1):
        bpy.ops.mesh.primitive_torus_add(major_radius=0.007, minor_radius=0.0018, major_segments=20, minor_segments=8)
        ring = bpy.context.object; ring.rotation_euler = (0, 1.5708, 0); bpy.ops.object.transform_apply(rotation=True)
        place(ring, BRASS, F, at(zz) + wdir * s * 0.03)
bpy.ops.mesh.primitive_cone_add(vertices=4, radius1=0.022, radius2=0.0, depth=0.035)
chape = bpy.context.object; chape.rotation_euler = (3.14159, 0, 0.785); chape.scale = (1, 0.5, 1)
bpy.ops.object.transform_apply(rotation=True, scale=True)
place(chape, BRASS, F, at(z_bot) - up * 0.008)
bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=0.007)
knob = bpy.context.object; place(knob, BRASS, F, at(z_bot) - up * 0.028)
# jílec: záštita, rukojeť s žebry, hlavice
bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=1)
guard = bpy.context.object; guard.scale = (0.03, 0.019, 0.012); bpy.ops.object.transform_apply(scale=True)
for f in guard.data.polygons: f.use_smooth = True
place(guard, WOOD, F, at(0.622))
bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.0115, depth=0.05)
grip = bpy.context.object
for f in grip.data.polygons: f.use_smooth = True
place(grip, BONE, F, at(0.659))
for zz in (0.645, 0.659, 0.673):
    bpy.ops.mesh.primitive_torus_add(major_radius=0.0118, minor_radius=0.0022, major_segments=24, minor_segments=8)
    rib = bpy.context.object; place(rib, BONE, F, at(zz))
bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=1)
pom = bpy.context.object; pom.scale = (0.021, 0.019, 0.016); bpy.ops.object.transform_apply(scale=True)
for f in pom.data.polygons: f.use_smooth = True
place(pom, WOOD, F, at(0.700))
bpy.ops.mesh.primitive_cone_add(vertices=16, radius1=0.004, radius2=0.002, depth=0.012)
nut = bpy.context.object; place(nut, BRASS, F, at(0.718))
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
