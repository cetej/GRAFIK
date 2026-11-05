# Detailní rendery boků (meč vpravo = -X, dýka vlevo = +X) z několika stran.
# blender -b --factory-startup --python detail_render.py -- <model.glb> <out_dir> <hdri.exr>
import bpy, sys, os
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]
GLB, OUT, HDRI = (os.path.abspath(a) for a in args[:3])
os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)
sc = bpy.context.scene
sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = 32; sc.cycles.use_denoising = True
sc.render.resolution_x = sc.render.resolution_y = 900
wd = bpy.data.worlds.new("w"); sc.world = wd; wd.use_nodes = True
env = wd.node_tree.nodes.new("ShaderNodeTexEnvironment"); env.image = bpy.data.images.load(HDRI)
wd.node_tree.links.new(env.outputs["Color"], wd.node_tree.nodes["Background"].inputs["Color"])
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); cam.data.type = "ORTHO"; sc.collection.objects.link(cam); sc.camera = cam
mec = Vector((-0.114, -0.06, 0.52)); dyka = Vector((0.07, -0.03, 0.55))
for name, (d, t, s) in {"mec_zepredu": ((0, -1, 0.1), mec, 0.42), "mec_zboku": ((-1, 0, 0.1), mec, 0.42),
                        "mec_sikmo": ((-1, -0.6, 0.3), mec, 0.42), "mec_zezadu": ((-0.6, 1, 0.2), mec, 0.42),
                        "dyka_zepredu": ((0, -1, 0.1), dyka, 0.3), "dyka_zboku": ((1, 0, 0.1), dyka, 0.3),
                        "dyka_sikmo": ((1, -0.7, 0.3), dyka, 0.3)}.items():
    dv = Vector(d).normalized(); cam.data.ortho_scale = s
    cam.location = t + dv * 3
    cam.rotation_euler = (-dv).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = os.path.join(OUT, f"{name}.png")
    bpy.ops.render.render(write_still=True)
print("DONE")
