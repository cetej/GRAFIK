# Kontrolní rendery GLB s vlastními materiály: 5 pravoúhlých pohledů (voják hledí k -Y).
# blender -b --factory-startup --python render_pohledy.py -- <model.glb> <out_dir>
import bpy, sys, os
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]
GLB, OUT = (os.path.abspath(a) for a in args[:2])
os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)
objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
mn = Vector([min(p[i] for p in pts) for i in range(3)]); mx = Vector([max(p[i] for p in pts) for i in range(3)])
ctr = (mn + mx) / 2; size = max(mx - mn)
print("bbox", tuple(round(v, 3) for v in mx - mn))
sc = bpy.context.scene
sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = 32; sc.cycles.use_denoising = True
sc.render.resolution_x = sc.render.resolution_y = 1024
sc.view_settings.view_transform = "Standard"
wd = bpy.data.worlds.new("w"); sc.world = wd; wd.use_nodes = True
wd.node_tree.nodes["Background"].inputs[0].default_value = (0.8, 0.8, 0.8, 1)
wd.node_tree.nodes["Background"].inputs[1].default_value = 0.6
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); sun.data.energy = 1.8
sun.rotation_euler = (0.8, 0, -0.5); sc.collection.objects.link(sun)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); cam.data.type = "ORTHO"
cam.data.ortho_scale = size * 1.1; sc.collection.objects.link(cam); sc.camera = cam
for name, d in {"zepredu": (0, -1, 0.15), "zezadu": (0, 1, 0.15), "zprava": (-1, 0, 0.15), "zleva": (1, 0, 0.15), "sikmo": (-0.7, -0.7, 0.3)}.items():
    dv = Vector(d).normalized()
    cam.location = ctr + dv * size * 3
    cam.rotation_euler = (-dv).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = os.path.join(OUT, f"{name}.png")
    bpy.ops.render.render(write_still=True)
print("DONE")
