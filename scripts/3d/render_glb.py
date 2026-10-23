# Render a GLB from several azimuths (free): blender -b -P scripts/3d/render_glb.py -- model.glb out_prefix [azimuth ...]
import math, sys
import bpy
from mathutils import Vector

glb, prefix, *rest = sys.argv[sys.argv.index("--") + 1:]
AZ = [int(x) for x in rest] or [0, 45, 90, 135, 180, 225, 270, 315]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=glb)
objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
center, size = (lo + hi) / 2, max(hi - lo)
print("bbox", tuple(round(v, 3) for v in lo), tuple(round(v, 3) for v in hi))

scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items] else "BLENDER_EEVEE"
scene.render.resolution_x, scene.render.resolution_y = 1280, 720
scene.render.film_transparent = True
world = bpy.data.worlds.new("w"); scene.world = world; world.use_nodes = True
world.node_tree.nodes["Background"].inputs[1].default_value = 2.0
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); scene.collection.objects.link(sun)
sun.data.energy = 5.0; scene.view_settings.view_transform = "Standard"; sun.rotation_euler = (math.radians(50), 0, math.radians(30))
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); scene.collection.objects.link(cam); scene.camera = cam
cam.data.lens = 50

def shoot(name, azimuth, elevation, dist=1.9):
    a, e = math.radians(azimuth), math.radians(elevation)
    cam.location = center + Vector((math.cos(a) * math.cos(e), math.sin(a) * math.cos(e), math.sin(e))) * size * dist
    cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.render.filepath = f"{prefix}-{name}.png"
    bpy.ops.render.render(write_still=True)

for az in AZ:
    shoot(f"az{az:03d}", az, 22)
