# Lesk kovu: z barevné textury odvodí metallic-roughness mapu (ocel a zlacené kování kov, zbytek matný). 0 USD.
# blender -b --factory-startup --python lesk_zbroje.py -- <in.glb> <out.glb> <render_dir> <hdri.exr>
import bpy, sys, os
import numpy as np
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]
IN, OUT, RDIR, HDRI = (os.path.abspath(a) for a in args[:4])
os.makedirs(RDIR, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=IN)
objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
mat = objs[0].data.materials[0]
nt = mat.node_tree
bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
tex = next(n for n in nt.nodes if n.type == "TEX_IMAGE" and any(l.to_socket == bsdf.inputs["Base Color"] for l in n.outputs["Color"].links))
img = tex.image
w, h = img.size
px = np.array(img.pixels[:], np.float32).reshape(h, w, 4)[..., :3]  # hodnoty jak v souboru (sRGB)
mx = px.max(2); mn = px.min(2); sat = (mx - mn) / np.maximum(mx, 1e-4)
r, g, b = px[..., 0], px[..., 1], px[..., 2]
steel = (sat < 0.14) & (mx > 0.38)
hue = np.degrees(np.arctan2(np.sqrt(3) * (g - b), 2 * r - g - b)) % 360
gold = (hue > 38) & (hue < 60) & (sat > 0.3) & (mx > 0.45)  # kůže je oranžovější (pod ~32°), jinak by se leskla jako kov
metal = np.where(steel, 1.0, np.where(gold, 0.9, 0.0))
rough = np.where(steel, 0.28, np.where(gold, 0.35, 0.65))
print("steel %", round(steel.mean() * 100, 1), "gold %", round(gold.mean() * 100, 1))

# ocel trochu prosvětlit a ochladit, ať se odrazem nečerná
base = px.copy()
base[steel] = np.clip(base[steel] * 1.12 + np.array([0.0, 0.01, 0.03]), 0, 1)
img.pixels[:] = np.concatenate([base, np.ones((h, w, 1), np.float32)], 2).ravel()
img.pack()

mr = bpy.data.images.new("metal_rough", w, h)
mr.colorspace_settings.name = "Non-Color"
mrpx = np.stack([np.zeros_like(rough), rough, metal, np.ones_like(rough)], 2).astype(np.float32)  # glTF: G drsnost, B kov
mr.pixels[:] = mrpx.ravel(); mr.pack()
mt = nt.nodes.new("ShaderNodeTexImage"); mt.image = mr
uvsrc = tex.inputs["Vector"].links[0].from_socket if tex.inputs["Vector"].links else None
if uvsrc: nt.links.new(uvsrc, mt.inputs["Vector"])
sep = nt.nodes.new("ShaderNodeSeparateColor")
nt.links.new(mt.outputs["Color"], sep.inputs["Color"])
nt.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
nt.links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])

bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB")
print("exported", OUT)

sc = bpy.context.scene
sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = 48; sc.cycles.use_denoising = True
sc.render.resolution_x = sc.render.resolution_y = 1024
sc.render.film_transparent = False
wd = bpy.data.worlds.new("w"); sc.world = wd; wd.use_nodes = True
env = wd.node_tree.nodes.new("ShaderNodeTexEnvironment"); env.image = bpy.data.images.load(HDRI)
wd.node_tree.links.new(env.outputs["Color"], wd.node_tree.nodes["Background"].inputs["Color"])
wd.node_tree.nodes["Background"].inputs[1].default_value = 1.0
pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
lo = Vector([min(p[i] for p in pts) for i in range(3)]); hi = Vector([max(p[i] for p in pts) for i in range(3)])
ctr = (lo + hi) / 2; size = max(hi - lo)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); cam.data.type = "ORTHO"
cam.data.ortho_scale = size * 1.1; sc.collection.objects.link(cam); sc.camera = cam
for name, d in {"zepredu": (0, -1, 0.15), "sikmo": (-0.7, -0.7, 0.3), "zezadu": (0, 1, 0.15)}.items():
    dv = Vector(d).normalized()
    cam.location = ctr + dv * size * 3
    cam.rotation_euler = (-dv).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = os.path.join(RDIR, f"{name}.png")
    bpy.ops.render.render(write_still=True)
print("DONE")
