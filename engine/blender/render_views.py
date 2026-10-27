# Clay views of a GLB for the 3D step (run by engine/models3d.py, free):
#   blender -b --factory-startup -P engine/blender/render_views.py -- model.glb OUT_DIR ELEVATION [--cpu] [--size 1024]
#   blender … -- model.glb OUT.png --camera '{"target":[x,y,z],"azimuth":a,"elevation":e,"distance":d,"lens":mm}' [--cpu]
#   blender … -- --scene SPEC.json OUT.png [--cpu]
# Sheet: writes OUT_DIR/az000.png … az315.png (8 views, 45° apart). --camera: one view from the Studio viewer's
# camera (target in glTF coordinates, Y up, as three.js sees the file; azimuth 0° looks from +X, 90° from -Z,
# i.e. the sheet's azimuths; distance in model units; lens on a 36 mm sensor). --scene: a 3D scene of
# engine/scenes3d.py (render_spec): several GLBs and simple shapes placed in metres, each GLB scaled uniformly to
# its longest side `rozmer`, centred on `misto` with its bottom on the ground (or on the top of the object `na`
# names), turned `otoceni` degrees about Z; the camera as with --camera, the frame `size` [w, h] (the 36 mm span
# the longer side, as studio/src/SceneViewer3d.tsx draws it). All print one line `STATS {json}` with
# vertex/face counts and the bounding box. Based on scripts/3d/render_glb.py --clay: one matte grey material
# (shape only, the image generator adds material), transparent film, no floor, so no shadow under the object
# (LEARNINGS 2026-10-23: shadows turn into objects). --cpu renders with Cycles on the processor instead of EEVEE
# on the GPU.
import json
import math
import sys

import bpy
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]
spec = None
if "--scene" in args:
    i = args.index("--scene")
    with open(args[i + 1], encoding="utf-8") as f:
        spec = json.load(f)
    out = args[i + 2]
    camera = spec["camera"]
else:
    glb, out = args[0], args[1]
    camera = json.loads(args[args.index("--camera") + 1]) if "--camera" in args else None
cpu = "--cpu" in args
size_px = int(args[args.index("--size") + 1]) if "--size" in args else 1024

bpy.ops.wm.read_factory_settings(use_empty=True)


def bbox(meshes):
    pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
    return (Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts))),
            Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts))))


def import_glb(path):
    """The GLB's meshes and its root objects (the importer may add empties above them)."""
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.context.scene.objects if o not in before]
    return [o for o in new if o.type == "MESH"], [o for o in new if o.parent is None]


def place_scene(spec):
    """Every object under two empties: `inner` scales it to its size and puts the bottom centre at the origin,
    `outer` turns and moves it. Returns {id: meshes}."""
    placed = {}
    for o in spec["objects"]:
        kind = o["kind"]
        if kind == "glb":
            meshes, roots = import_glb(o["glb"])
            if not meshes:
                raise SystemExit(f"objekt {o['id']}: GLB bez sítí")
            lo, hi = bbox(meshes)
            k = o["rozmer"] / max(hi - lo)
        else:
            if kind == "kvadr":
                bpy.ops.mesh.primitive_cube_add(size=1)
                dims = o["rozmery"]
            else:
                bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=0.5, depth=1)
                dims = [o["rozmery"][0], o["rozmery"][0], o["rozmery"][1]]
            m = bpy.context.active_object
            m.scale = dims
            bpy.ops.object.transform_apply(scale=True)
            meshes, roots = [m], [m]
            lo, hi, k = Vector((-dims[0] / 2, -dims[1] / 2, -dims[2] / 2)), Vector((dims[0] / 2, dims[1] / 2, dims[2] / 2)), 1.0
        inner = bpy.data.objects.new(f"{o['id']}-inner", None)
        outer = bpy.data.objects.new(o["id"], None)
        bpy.context.scene.collection.objects.link(inner)
        bpy.context.scene.collection.objects.link(outer)
        c = (lo + hi) / 2
        inner.scale = (k, k, k)
        inner.location = (-c.x * k, -c.y * k, -lo.z * k)
        inner.parent = outer
        for r in roots:
            r.parent = inner
        base = 0.0
        if o.get("na"):
            bpy.context.view_layer.update()
            base = bbox(placed[o["na"]])[1].z
        outer.location = (o["misto"][0], o["misto"][1], base)
        outer.rotation_euler = (0, 0, math.radians(o["otoceni"]))
        bpy.context.view_layer.update()
        placed[o["id"]] = meshes
    return placed


if spec:
    place_scene(spec)
else:
    bpy.ops.import_scene.gltf(filepath=glb)
objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
if not objs:
    print("STATS " + json.dumps({"verts": 0, "faces": 0}))
    sys.exit(3)
lo, hi = bbox(objs)
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
if spec:
    scene.render.resolution_x, scene.render.resolution_y = spec["size"]
else:
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
cam.data.sensor_fit = "AUTO"   # the 36 mm sensor width spans the longer side (both on a square frame)
cam.data.clip_end = max(1000.0, size * 20)


def shoot(target, az, el, distance, path):
    a, e = math.radians(az), math.radians(el)
    cam.location = target + Vector((math.cos(a) * math.cos(e), math.sin(a) * math.cos(e), math.sin(e))) * distance
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    # key light from behind the camera, a little left and above, so the visible side is lit
    sun.rotation_euler = (target - cam.location + Vector((0, 0, -0.6 * size))).to_track_quat("-Z", "Y").to_euler()
    sun.rotation_euler.z += math.radians(25)
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


if camera:
    x, y, z = camera["target"]
    cam.data.lens = float(camera.get("lens", 50))
    # glTF Y-up -> Blender Z-up (the importer's own conversion)
    shoot(Vector((x, -z, y)), float(camera["azimuth"]), float(camera["elevation"]), float(camera["distance"]), out)
    print("VIEW camera", flush=True)
else:
    el = float(args[2])
    cam.data.lens = 50
    # a square frame: tall objects need the distance a wide one does
    dist = 1.8 if el < 50 else 2.0
    for az in range(0, 360, 45):
        shoot(center, az, el, size * dist, f"{out}/az{az:03d}.png")
        print(f"VIEW az{az:03d}", flush=True)
