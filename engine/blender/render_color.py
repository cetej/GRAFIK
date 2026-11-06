# Barevný náhled modelu i s texturami (prohlížeč Studia a sheet ukazují jen hlínu): dva pohledy, Cycles na CPU.
# blender -b --factory-startup -P render_color.py -- <model.glb> <out_dir> <prefix>
# Píše <out_dir>/<prefix>-0.png a -1.png; cesty přes resolve(), relativní render.filepath zapisuje jinam.
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

glb, out_dir, prefix = sys.argv[sys.argv.index("--") + 1:][:3]
out = Path(out_dir).resolve()
ANGLES = [(35, 25), (215, 20)]

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = 48
scene.cycles.use_denoising = True
scene.render.resolution_x = scene.render.resolution_y = 900
world = bpy.data.worlds.new("w")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.6, 0.62, 0.65, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = 0.6
scene.world = world
bpy.ops.import_scene.gltf(filepath=str(Path(glb).resolve()))
meshes = [o for o in scene.objects if o.type == "MESH"]
pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
center, size = (lo + hi) / 2, (hi - lo).length
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
sun.data.energy = 3.5
sun.rotation_euler = (math.radians(50), 0, math.radians(30))
scene.collection.objects.link(sun)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.lens = 50
scene.collection.objects.link(cam)
scene.camera = cam
for i, (az, el) in enumerate(ANGLES):
    d, a, e = size * 1.35, math.radians(az), math.radians(el)
    cam.location = center + Vector((d * math.cos(e) * math.cos(a), d * math.cos(e) * math.sin(a), d * math.sin(e)))
    cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = str(out / f"{prefix}-{i}.png")
    bpy.ops.render.render(write_still=True)
print("COLOR " + str(len(ANGLES)))
