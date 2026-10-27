# The 1.72 m control figure of the 3D scenes (engine/scenes3d.py), built once and committed as
# engine/assets/postava-172.glb (the Studio viewer and the scene render load the same file):
#   blender -b --factory-startup -P engine/blender/figure172.py -- engine/assets/postava-172.glb
# A plain standing person from capsules and a sphere, facing -Y (glTF +Z, as a figure in KLAPKA), feet at 0,
# 1.72 m to the top of the head. Low-poly on purpose: it is a yardstick, not a character.
import sys

import bpy
from mathutils import Vector

out = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)


def capsule(name, radius, a, b):
    """A cylinder from a to b with spheres on both ends."""
    a, b = Vector(a), Vector(b)
    d = b - a
    bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=radius, depth=d.length, location=(a + b) / 2)
    cyl = bpy.context.active_object
    cyl.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
    parts = [cyl]
    for p in (a, b):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8, radius=radius, location=p)
        parts.append(bpy.context.active_object)
    for o in parts:
        o.name = name
    return parts


parts = []
for side in (-1, 1):
    parts += capsule("noha", 0.075, (0.1 * side, 0, 0.075), (0.1 * side, 0, 0.86))          # leg
    parts += capsule("ruka", 0.05, (0.23 * side, 0, 1.40), (0.27 * side, 0, 0.82))          # arm
parts += capsule("trup", 0.16, (0, 0, 0.98), (0, 0, 1.36))                                  # torso
parts += capsule("krk", 0.05, (0, 0, 1.45), (0, 0, 1.52))
bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=0.11, location=(0, 0, 1.61))  # head
parts.append(bpy.context.active_object)

for o in parts:
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
bpy.ops.object.select_all(action="DESELECT")
for o in parts:
    o.select_set(True)
bpy.context.view_layer.objects.active = parts[0]
bpy.ops.object.join()
fig = bpy.context.active_object
fig.name = "postava-172"
top = max((fig.matrix_world @ v.co).z for v in fig.data.vertices)
print(f"HEIGHT {top:.4f}")
bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", use_selection=True, export_materials="NONE")
