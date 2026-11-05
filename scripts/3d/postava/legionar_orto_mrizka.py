# Pravoúhlé pohledy zepředu a z boku s pevným měřítkem (pro odečet kloubů): -- <in.glb> <out_dir>
# Rámec: x (resp. y) -0.6..0.6, z -0.03..1.17, 1200x1200 px => 1000 px na jednotku.
import bpy, sys, os
from mathutils import Vector
args = sys.argv[sys.argv.index("--") + 1:]
OUT = os.path.abspath(args[1]); os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=os.path.abspath(args[0]))
sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items] else "CYCLES"
if sc.render.engine == "CYCLES":
    sc.cycles.device = "CPU"; sc.cycles.samples = 16
sc.render.resolution_x = sc.render.resolution_y = 1200
sc.view_settings.view_transform = "Standard"
wd = bpy.data.worlds.new("w"); sc.world = wd; wd.use_nodes = True
wd.node_tree.nodes["Background"].inputs[0].default_value = (1, 1, 1, 1)
wd.node_tree.nodes["Background"].inputs[1].default_value = 1.0
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); cam.data.type = "ORTHO"; cam.data.ortho_scale = 1.2
sc.collection.objects.link(cam); sc.camera = cam
ctr = Vector((0, 0, 0.57))
for name, d in {"orto_zepredu": (0, -1, 0), "orto_zboku": (1, 0, 0)}.items():
    dv = Vector(d)
    cam.location = ctr + dv * 5
    cam.rotation_euler = (-dv).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = os.path.join(OUT, f"{name}.png")
    bpy.ops.render.render(write_still=True)
print("DONE")
