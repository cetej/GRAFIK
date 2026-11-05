# Železná část pila nahrazená vymodelovanou: tenký krk (stopka) a jehlanový hrot s osazením. 0 USD.
# Dřevěná násada s klínem a ruka zůstávají z generátoru.
# blender -b --factory-startup --python hrot_pila.py -- <in.glb> <out.glb> <render_dir> <hdri.exr>
import bpy, bmesh, sys, os
import numpy as np
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]
IN, OUT, RDIR, HDRI = (os.path.abspath(a) for a in args[:4])
os.makedirs(RDIR, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=IN)
obj = [o for o in bpy.context.scene.objects if o.type == "MESH"][0]
bpy.context.view_layer.objects.active = obj
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
me = obj.data
co = np.array([v.co for v in me.vertices])
H = co[:, 2].max() - co[:, 2].min()

# osa pila: nejvyšší body modelu jsou hrot
top = co[co[:, 2] > co[:, 2].max() - 0.01 * H]
ax, ay = top[:, 0].mean(), top[:, 1].mean()
d = np.hypot(co[:, 0] - ax, co[:, 1] - ay)
col = d < 0.03 * H
zs = np.linspace(co[:, 2].max(), co[:, 2].max() - 0.45 * H, 120)
prof = []
for z in zs:
    s = col & (np.abs(co[:, 2] - z) < 0.004 * H)
    prof.append(d[s].max() if s.any() else 0)
prof = np.array(prof)
shank_r = np.median(prof[10:40])
# horní okraj dřevěného klínu: první řez shora, kde poloměr vyskočí nad 2,2× krk
i_block = next(i for i in range(15, len(zs)) if prof[i] > 2.2 * shank_r)
z_block = zs[i_block] + 0.004 * H
print("axis", round(ax, 4), round(ay, 4), "shank r", round(shank_r, 4), "block top z", round(z_block, 4), "top z", round(co[:, 2].max(), 4))

# vyříznout staré železo (vše v ose nad klínem)
bm = bmesh.new(); bm.from_mesh(me)
cut = [v for v in bm.verts if v.co.z > z_block and np.hypot(v.co.x - ax, v.co.y - ay) < 3 * shank_r + 0.004 * H]
bmesh.ops.delete(bm, geom=cut, context="VERTS")
bm.to_mesh(me); bm.free()
print("removed verts", len(cut))

# nové železo (měřítko: postava ~1,75 m = H)
m = H / 1.75
z0, z1 = z_block, co[:, 2].max()
head_len = 0.055 * m
steel = bpy.data.materials.new("zelezo_pila"); steel.use_nodes = True
b = steel.node_tree.nodes["Principled BSDF"]
b.inputs["Base Color"].default_value = (0.45, 0.45, 0.47, 1); b.inputs["Metallic"].default_value = 1.0
b.inputs["Roughness"].default_value = 0.32
parts = []
# objímka na klínu
bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.009 * m, depth=0.03 * m, location=(ax, ay, z0 + 0.015 * m)); parts.append(bpy.context.object)
# stopka (krk) – kulatý průřez ~7 mm
shank_len = (z1 - head_len) - (z0 + 0.03 * m)
bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=0.0042 * m, depth=shank_len, location=(ax, ay, z0 + 0.03 * m + shank_len / 2)); parts.append(bpy.context.object)
# hrot: čtyřboký jehlan s mírným osazením
bpy.ops.mesh.primitive_cone_add(vertices=4, radius1=0.0095 * m, radius2=0, depth=head_len * 0.8, location=(ax, ay, z1 - head_len * 0.4)); parts.append(bpy.context.object)
bpy.ops.mesh.primitive_cone_add(vertices=4, radius1=0.0045 * m, radius2=0.0095 * m, depth=head_len * 0.2, location=(ax, ay, z1 - head_len * 0.9)); parts.append(bpy.context.object)
for p in parts:
    p.data.materials.append(steel)
    for f in p.data.polygons: f.use_smooth = p.data.polygons[0].normal.z == 0 and len(p.data.vertices) > 30
    p.name = "pilum_zelezo"

bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB")
print("exported", OUT)

sc = bpy.context.scene
sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = 48; sc.cycles.use_denoising = True
sc.render.resolution_x = sc.render.resolution_y = 1024
wd = bpy.data.worlds.new("w"); sc.world = wd; wd.use_nodes = True
env = wd.node_tree.nodes.new("ShaderNodeTexEnvironment"); env.image = bpy.data.images.load(HDRI)
wd.node_tree.links.new(env.outputs["Color"], wd.node_tree.nodes["Background"].inputs["Color"])
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); cam.data.type = "ORTHO"; sc.collection.objects.link(cam); sc.camera = cam
allp = [o.matrix_world @ Vector(c) for o in sc.objects if o.type == "MESH" for c in o.bound_box]
lo = Vector([min(p[i] for p in allp) for i in range(3)]); hi = Vector([max(p[i] for p in allp) for i in range(3)])
ctr = (lo + hi) / 2; size = max(hi - lo)
shots = {"zepredu": ((0, -1, 0.15), ctr, size * 1.1),
         "hrot_detail": ((-0.5, -1, 0.1), Vector((ax, ay, z1 - 0.12 * H)), 0.3 * H)}
for name, (dvec, tgt, scale) in shots.items():
    dv = Vector(dvec).normalized(); cam.data.ortho_scale = scale
    cam.location = tgt + dv * size * 3
    cam.rotation_euler = (-dv).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = os.path.join(RDIR, f"{name}.png")
    bpy.ops.render.render(write_still=True)
print("DONE")
