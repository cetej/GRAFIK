# Legionář na tažení: opotřebení zapečené do textur (0 USD).
# Ocel matnější se špínou v záhybech a ostrůvky rzi, mosaz zašlá, prach všude, bláto odspodu; vymodelované díly ztlumené.
# blender -b --factory-startup --python opotrebeni.py -- <in.glb> <out.glb> <render_dir> <hdri.exr>
import bpy, sys, os
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]
IN, OUT, RDIR, HDRI = (os.path.abspath(a) for a in args[:4])
os.makedirs(RDIR, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=IN)
meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
body = max(meshes, key=lambda o: len(o.data.vertices))
sc = bpy.context.scene
sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"

# špína v prohlubních: vertex dirt (tmavé = záhyby)
bpy.ops.object.select_all(action="DESELECT"); body.select_set(True); bpy.context.view_layer.objects.active = body
dirt = body.data.color_attributes.new("dirt", "FLOAT_COLOR", "POINT")  # BYTE_COLOR se čte jako sRGB→lineár: rovná plocha 0,5 by byla 0,21 = „záhyb“ všude
body.data.color_attributes.active_color = dirt
bpy.ops.object.mode_set(mode="VERTEX_PAINT")
bpy.ops.paint.vertex_color_dirt(blur_strength=1.0, blur_iterations=2, clean_angle=3.14159, dirt_angle=0.0, dirt_only=False, normalize=True)
bpy.ops.object.mode_set(mode="OBJECT")
import numpy as np
_dv = np.zeros(len(body.data.vertices) * 4, np.float32); dirt.data.foreach_get("color", _dv)
P3, P25 = (float(v) for v in np.percentile(_dv.reshape(-1, 4)[:, 0], [3, 25]))
print("dirt p3 / p25", round(P3, 4), round(P25, 4))  # medián ~0,06: pevný práh by označil za záhyb celý model

mat = body.data.materials[0]; nt = mat.node_tree; N = nt.nodes; L = nt.links
bsdf = next(n for n in N if n.type == "BSDF_PRINCIPLED")
base_tex = next(n for n in N if n.type == "TEX_IMAGE" and n.image.colorspace_settings.name != "Non-Color")
mr_tex = next(n for n in N if n.type == "TEX_IMAGE" and n.image.colorspace_settings.name == "Non-Color" and any(l.to_node.type == "SEPARATE_COLOR" for l in n.outputs["Color"].links))
W, H = base_tex.image.size
print("texture", W, H)


def node(t, **kw):
    n = N.new(t)
    for k, v in kw.items():
        setattr(n, k, v)
    return n


def math(op, a, b=None, clamp=True):
    m = node("ShaderNodeMath", operation=op, use_clamp=clamp)
    for i, v in enumerate((a, b)):
        if v is None: continue
        if isinstance(v, (int, float)): m.inputs[i].default_value = v
        else: L.new(v, m.inputs[i])
    return m.outputs[0]


def mixc(fac, a, b):
    m = node("ShaderNodeMix", data_type="RGBA", blend_type="MIX", clamp_factor=True)
    L.new(fac, m.inputs["Factor"]) if not isinstance(fac, float) else setattr(m.inputs["Factor"], "default_value", fac)
    for sock, v in ((m.inputs[6], a), (m.inputs[7], b)):
        if isinstance(v, tuple): sock.default_value = (*v, 1)
        else: L.new(v, sock)
    return m.outputs[2]


def noise(scale, detail=6.0, rough=0.6):
    tc = node("ShaderNodeTexCoord")
    nz = node("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = scale
    nz.inputs["Detail"].default_value = detail; nz.inputs["Roughness"].default_value = rough
    L.new(tc.outputs["Object"], nz.inputs["Vector"])
    return nz.outputs["Fac"]


sep = next(n for n in N if n.type == "SEPARATE_COLOR")
metal0 = sep.outputs["Blue"]; rough0 = sep.outputs["Green"]
base0 = base_tex.outputs["Color"]
attr = node("ShaderNodeVertexColor", layer_name="dirt")
cav = math("MULTIPLY", math("SUBTRACT", P25, attr.outputs["Color"]), 1.0 / max(P25 - P3, 1e-4))  # záhyb = nejnižší čtvrtina
geo = node("ShaderNodeNewGeometry"); xyz = node("ShaderNodeSeparateXYZ"); L.new(geo.outputs["Position"], xyz.inputs[0])
zpos = xyz.outputs["Z"]
low = math("POWER", math("SUBTRACT", 1.0, math("DIVIDE", zpos, 0.32)), 1.6)  # 1 u země, 0 nad koleny
# místně, ne plošně (operátor): bláto ve skvrnách u země, prach v ostrůvcích, odspodu o něco víc
mud = math("MULTIPLY", math("POWER", low, 1.2), math("MULTIPLY", math("SUBTRACT", noise(7.0), 0.47), 3.0))
dust = math("ADD", math("MULTIPLY", math("SUBTRACT", noise(2.5, 4.0), 0.56), 2.5), math("MULTIPLY", low, 0.25))
steel = math("GREATER_THAN", metal0, 0.97)  # ocel 1,0; mosaz 0,95
brass = math("MULTIPLY", math("GREATER_THAN", metal0, 0.5), math("SUBTRACT", 1.0, steel))
rust = math("MULTIPLY", steel, math("MULTIPLY", math("SUBTRACT", noise(45.0, 8.0, 0.7), 0.62), 6.0))
rust = math("MULTIPLY", rust, math("ADD", 0.3, cav))
rust = math("MULTIPLY", rust, 0.8)
# barva
c = mixc(math("MULTIPLY", brass, 0.45), base0, (0.33, 0.24, 0.12))           # zašlá mosaz
c = mixc(math("MULTIPLY", steel, 0.2), c, (0.30, 0.30, 0.31))                # ocel bez zrcadlového jasu
c = mixc(math("MULTIPLY", cav, 0.4), c, (0.10, 0.08, 0.06))                  # špína v záhybech (0,6 dělalo na tunice „mramor“)
c = mixc(rust, c, (0.36, 0.17, 0.07))                                         # rez
c = mixc(math("MULTIPLY", dust, 0.35), c, (0.48, 0.42, 0.34))                 # prach v ostrůvcích
c = mixc(math("MULTIPLY", mud, 0.8), c, (0.28, 0.22, 0.15))                   # bláto u země
# drsnost a kov
rough = math("ADD", rough0, math("MULTIPLY", steel, math("ADD", 0.14, math("MULTIPLY", noise(20.0), 0.18))), clamp=True)
rough = math("MAXIMUM", rough, math("MULTIPLY", math("ADD", math("ADD", rust, mud), math("MULTIPLY", cav, 0.4)), 0.95))
rough = math("ADD", rough, math("MULTIPLY", brass, 0.2))
metal = math("MULTIPLY", metal0, math("SUBTRACT", 1.0, math("ADD", rust, math("MULTIPLY", mud, 0.8))))
comb = node("ShaderNodeCombineColor"); L.new(rough, comb.inputs["Green"]); L.new(metal, comb.inputs["Blue"])

# zapéct barvu a kov/drsnost přes emisi
emit = node("ShaderNodeEmission"); outn = next(n for n in N if n.type == "OUTPUT_MATERIAL")
orig_surface = outn.inputs["Surface"].links[0].from_socket
L.new(emit.outputs["Emission"], outn.inputs["Surface"])
sc.cycles.samples = 1; sc.render.bake.margin = 8
results = {}
for name, src, cs in (("base_opotrebeni", c, "sRGB"), ("mr_opotrebeni", comb.outputs["Color"], "Non-Color")):
    img = bpy.data.images.new(name, W, H, float_buffer=(cs == "Non-Color")); img.colorspace_settings.name = cs
    tn = node("ShaderNodeTexImage"); tn.image = img; N.active = tn
    L.new(src, emit.inputs["Color"])
    bpy.ops.object.bake(type="EMIT")
    img.pack(); results[name] = tn
    print("baked", name)
import numpy as np
a0 = np.array(base_tex.image.pixels[:], np.float32).reshape(-1, 4)[:, :3]
a1 = np.array(results["base_opotrebeni"].image.pixels[:], np.float32).reshape(-1, 4)[:, :3]
red = (a0[:, 0] > 0.45) & (a0[:, 1] < 0.15) & (a0[:, 2] < 0.2)
print("mean before", a0.mean(0).round(3), "after", a1.mean(0).round(3), "| red texels before", a0[red].mean(0).round(3), "after", a1[red].mean(0).round(3))
# nový materiál: zapečené textury
L.new(orig_surface, outn.inputs["Surface"])
L.new(results["base_opotrebeni"].outputs["Color"], bsdf.inputs["Base Color"])
uvn = base_tex.inputs["Vector"].links[0].from_socket if base_tex.inputs["Vector"].links else None
for tn in results.values():
    if uvn: L.new(uvn, tn.inputs["Vector"])
sep2 = node("ShaderNodeSeparateColor"); L.new(results["mr_opotrebeni"].outputs["Color"], sep2.inputs["Color"])
L.new(sep2.outputs["Green"], bsdf.inputs["Roughness"]); L.new(sep2.outputs["Blue"], bsdf.inputs["Metallic"])
for n in (base_tex, mr_tex):
    N.remove(n)
body.data.color_attributes.remove(body.data.color_attributes["dirt"])

# vymodelované díly: ztlumit
parts_mats = {m for o in meshes if o is not body for m in o.data.materials}  # sdílené materiály jen jednou
for m in parts_mats:
        if m is None: continue
        b = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if not b: continue
        col = b.inputs["Base Color"].default_value
        if b.inputs["Metallic"].default_value > 0.5:  # mosaz, železo: zašlé a matné
            b.inputs["Base Color"].default_value = (col[0] * 0.7, col[1] * 0.68, col[2] * 0.65, 1)
            b.inputs["Roughness"].default_value = min(1.0, b.inputs["Roughness"].default_value + 0.25)
        else:  # kůže pochvy, dřevo, kost: prach
            b.inputs["Base Color"].default_value = tuple(0.75 * col[i] + 0.25 * (0.42, 0.37, 0.30)[i] for i in range(3)) + (1,)
            b.inputs["Roughness"].default_value = min(1.0, b.inputs["Roughness"].default_value + 0.2)

bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB")
print("exported", OUT)

sc.cycles.samples = 48; sc.cycles.use_denoising = True
sc.render.resolution_x = sc.render.resolution_y = 1024
wd = bpy.data.worlds.new("w"); sc.world = wd; wd.use_nodes = True
env = wd.node_tree.nodes.new("ShaderNodeTexEnvironment"); env.image = bpy.data.images.load(HDRI)
wd.node_tree.links.new(env.outputs["Color"], wd.node_tree.nodes["Background"].inputs["Color"])
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); cam.data.type = "ORTHO"; sc.collection.objects.link(cam); sc.camera = cam
pts = [o.matrix_world @ Vector(cc) for o in meshes for cc in o.bound_box]
lo = Vector([min(p[i] for p in pts) for i in range(3)]); hi = Vector([max(p[i] for p in pts) for i in range(3)])
ctr = (lo + hi) / 2; size = max(hi - lo)
for name, (dvec, tgt, scale) in {"zepredu": ((0, -1, 0.15), ctr, size * 1.1),
                                 "zbroj": ((0.25, -1, 0.2), Vector((0.0, -0.05, 0.75)), 0.34),
                                 "prilba": ((-0.5, -1, 0.35), Vector((0.0, 0.0, 0.91)), 0.22),
                                 "nohy": ((-0.3, -1, 0.2), Vector((0.05, -0.05, 0.16)), 0.36),
                                 "sikmo": ((-0.7, -0.7, 0.3), ctr, size * 1.1)}.items():
    dv = Vector(dvec).normalized(); cam.data.ortho_scale = scale
    cam.location = tgt + dv * size * 3
    cam.rotation_euler = (-dv).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = os.path.join(RDIR, f"{name}.png")
    bpy.ops.render.render(write_still=True)
print("DONE")
