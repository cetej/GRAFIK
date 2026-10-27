# Clay views of a GLB for the 3D step (run by engine/models3d.py, free):
#   blender -b --factory-startup -P engine/blender/render_views.py -- model.glb OUT_DIR ELEVATION [--cpu] [--size 1024]
# Writes OUT_DIR/az000.png … az315.png (8 views, 45° apart) and prints one line
# `STATS {json}` with vertex/face counts and the bounding box. Based on scripts/3d/render_glb.py --clay:
# one matte grey material (shape only, the image generator adds material), transparent film,
# no floor, so no shadow under the object (LEARNINGS 2026-10-23: shadows turn into objects).
# --cpu renders with Cycles on the processor instead of EEVEE on the GPU.
import json
import math
import sys

import bpy
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]
glb, out_dir, el = args[0], args[1], float(args[2])
cpu = "--cpu" in args
size_px = int(args[args.index("--size") + 1]) if "--size" in args else 1024

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=glb)
objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
if not objs:
    print("STATS " + json.dumps({"verts": 0, "faces": 0}))
    sys.exit(3)
pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
center, size = (lo + hi) / 2, max(hi - lo)
print("STATS " + json.dumps({
    "verts": sum(len(o.data.vertices) for o in objs), "faces": sum(len(o.data.polygons) for o in objs),
    "objects": len(objs), "bbox": [round(v, 4) for v in (hi - lo)], "blender": bpy.app.version_string}))

mat = bpy.data.materials.new("clay")
mat.use_nodes = True
bsdf = mat.node_tree.nodes["Principled BSDF"]
bsdf.inputs["Base Color"].default_value = (0.62, 0.6, 0.56, 1)
bsdf.inputs["Roughness"].default_value = 0.9
for o in objs:
    o.data.materials.clear()
    o.data.materials.append(mat)

scene = bpy.context.scene
if cpu:
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 32
    scene.cycles.use_denoising = True
else:
    engines = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
    scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engines else "BLENDER_EEVEE"
scene.render.resolution_x = scene.render.resolution_y = size_px
scene.render.film_transparent = True
scene.view_settings.view_transform = "Standard"
world = bpy.data.worlds.new("w")
scene.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[1].default_value = 2.0
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
scene.collection.objects.link(sun)
sun.data.energy = 5.0
sun.data.angle = math.radians(20)  # soft edges: hard cast shadows read as extra parts
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
scene.collection.objects.link(cam)
scene.camera = cam
cam.data.lens = 50
# a square frame: tall objects need the distance a wide one does
dist = 1.8 if el < 50 else 2.0

for az in range(0, 360, 45):
    a, e = math.radians(az), math.radians(el)
    cam.location = center + Vector((math.cos(a) * math.cos(e), math.sin(a) * math.cos(e), math.sin(e))) * size * dist
    cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
    # key light from behind the camera, a little left and above, so the visible side is lit
    sun.rotation_euler = (center - cam.location + Vector((0, 0, -0.6 * size))).to_track_quat("-Z", "Y").to_euler()
    sun.rotation_euler.z += math.radians(25)
    scene.render.filepath = f"{out_dir}/az{az:03d}.png"
    bpy.ops.render.render(write_still=True)
    print(f"VIEW az{az:03d}", flush=True)
