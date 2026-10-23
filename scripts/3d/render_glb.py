# Render a GLB from several azimuths (free):
#   blender -b -P scripts/3d/render_glb.py -- model.glb out_prefix [--clay] [--el 22] [--edit edits.py] [azimuth ...]
# --clay replaces every material with one matte grey: the render then carries only shape and
# proportions, so the image generator does not copy TRELLIS's glossy toy-plastic texture.
# --edit runs a Python file with `objs`, `lo`, `hi`, `center`, `size` in scope (fix or add geometry).
import math, sys
import bpy
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]
glb, prefix, rest = args[0], args[1], args[2:]
clay = "--clay" in rest
el = float(rest[rest.index("--el") + 1]) if "--el" in rest else 22.0
edit = rest[rest.index("--edit") + 1] if "--edit" in rest else None
taken = {i + 1 for i, x in enumerate(rest) if x in ("--el", "--edit")}
AZ = [int(x) for i, x in enumerate(rest) if i not in taken and x.lstrip("-").isdigit()] or [0, 45, 90, 135, 180, 225, 270, 315]

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=glb)
objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
center, size = (lo + hi) / 2, max(hi - lo)
print("bbox", tuple(round(v, 3) for v in lo), tuple(round(v, 3) for v in hi))
if edit:
    exec(open(edit, encoding="utf-8").read(), {"__name__": "edit", "bpy": bpy, "Vector": Vector, "objs": objs, "lo": lo, "hi": hi,
                                                "center": center, "size": size})
    objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]

if clay:
    mat = bpy.data.materials.new("clay")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.62, 0.6, 0.56, 1)
    bsdf.inputs["Roughness"].default_value = 0.9
    for o in objs:
        o.data.materials.clear()
        o.data.materials.append(mat)

scene = bpy.context.scene
engines = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engines else "BLENDER_EEVEE"
scene.render.resolution_x, scene.render.resolution_y = 1280, 720
scene.render.film_transparent = True
scene.view_settings.view_transform = "Standard"
world = bpy.data.worlds.new("w"); scene.world = world; world.use_nodes = True
world.node_tree.nodes["Background"].inputs[1].default_value = 2.0
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); scene.collection.objects.link(sun)
sun.data.energy = 5.0; sun.rotation_euler = (math.radians(50), 0, math.radians(30))
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); scene.collection.objects.link(cam); scene.camera = cam
cam.data.lens = 50


def shoot(name, azimuth, elevation, dist=1.9):
    a, e = math.radians(azimuth), math.radians(elevation)
    cam.location = center + Vector((math.cos(a) * math.cos(e), math.sin(a) * math.cos(e), math.sin(e))) * size * dist
    cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
    # key light from behind the camera, a little left and above, so the visible side is lit
    sun.rotation_euler = (center - cam.location + Vector((0, 0, -0.6 * size))).to_track_quat("-Z", "Y").to_euler()
    sun.rotation_euler.z += math.radians(25)
    scene.render.filepath = f"{prefix}-{name}.png"
    bpy.ops.render.render(write_still=True)


for az in AZ:
    shoot(f"az{az:03d}", az, el)
