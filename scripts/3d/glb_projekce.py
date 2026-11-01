# Geometry-only model (Hunyuan) in colour, free: the picture it was made from is projected onto it from the front, then real light falls on it.
#   blender -b --factory-startup -P scripts/3d/glb_projekce.py -- model.glb ref.png OUT.png [--az 0] [--el 0] [--proj-az 0] [--proj-el 0] [--res W H] [--samples 96] [--clay] [--gpu] [--search]
# --search only prints the azimuth and elevation at which the model's outline best matches the ref (the model may be turned against the picture).
# The model's front is taken from the ref: its silhouette is fitted to the silhouette of the projected model. From the front the colours are exact,
# the further the camera turns away, the more they stretch.
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]
GLB, REF, OUT = args[0], args[1], Path(args[2])


def opt(name, default, n=1):
    if name in args:
        i = args.index(name)
        return args[i + 1] if n == 1 else args[i + 1:i + 1 + n]
    return default


AZ, EL = float(opt("--az", 0)), float(opt("--el", 0))
RES = [int(v) for v in opt("--res", (1000, 2000), 2)]
SAMPLES = int(opt("--samples", 96))
CLAY = "--clay" in args
PROJ_AZ, PROJ_EL = float(opt("--proj-az", AZ)), float(opt("--proj-el", EL))


def axes(az, el):
    a, e = math.radians(az - 90), math.radians(el)
    d = Vector((math.cos(a) * math.cos(e), math.sin(a) * math.cos(e), math.sin(e)))
    right = d.cross(Vector((0, 0, 1))).normalized() * -1
    return d, right, right.cross(d).normalized() * -1


def search(points, img):
    """Outline of the ref against the outline of the model from many directions, each scaled to the same box."""
    w, h = img.size
    px = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)[..., 3] > 0.5
    ys, xs = np.nonzero(px)
    aspect_ref = (xs.max() - xs.min()) / (ys.max() - ys.min())
    N = 192
    grid = np.zeros((N, N), dtype=bool)
    gx = ((xs - xs.min()) / (xs.max() - xs.min()) * (N - 1)).astype(int)
    gy = ((ys - ys.min()) / (ys.max() - ys.min()) * (N - 1)).astype(int)
    grid[gy, gx] = True
    best = []
    for az in range(-180, 181, 6):
        for el in range(-6, 37, 6):
            d, right, up = axes(az, el)
            u, v = points @ np.array(right), points @ np.array(up)
            aspect = (u.max() - u.min()) / (v.max() - v.min())
            mine = np.zeros((N, N), dtype=bool)
            mine[((v - v.min()) / (v.max() - v.min()) * (N - 1)).astype(int), ((u - u.min()) / (u.max() - u.min()) * (N - 1)).astype(int)] = True
            grown = mine.copy()
            for k in (1, -1):
                grown |= np.roll(mine, k, 0) | np.roll(mine, k, 1)
            iou = (grown & grid).sum() / max(1, (grown | grid).sum())
            best.append((round(float(iou) * (1 - min(0.5, abs(aspect - aspect_ref) / aspect_ref)), 4), az, el, round(float(aspect), 2)))
    print("STATS", sorted(best, reverse=True)[:6], "ref aspect", round(float(aspect_ref), 2))


def main():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    bpy.ops.import_scene.gltf(filepath=GLB)
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    bpy.context.view_layer.update()
    pts = [o.matrix_world @ v.co for o in meshes for v in o.data.vertices]
    xs, ys, zs = [p.x for p in pts], [p.y for p in pts], [p.z for p in pts]
    lo, hi = Vector((min(xs), min(ys), min(zs))), Vector((max(xs), max(ys), max(zs)))
    centre = (lo + hi) / 2
    span = max(hi - lo)

    # the projection: x and z of each corner, read in the picture's silhouette box
    img = bpy.data.images.load(REF)
    if "--search" in args:
        search(np.array([tuple(p) for p in pts[::4]], dtype=np.float32), img)
        return
    _, right, up = axes(PROJ_AZ, PROJ_EL)
    us, vs = [p.dot(right) for p in pts], [p.dot(up) for p in pts]
    u0, u1, v0, v1 = min(us), max(us), min(vs), max(vs)
    w, h = img.size
    px = img.pixels[:]
    has_alpha = img.channels == 4
    x0, x1, y0, y1 = w, 0, h, 0
    for j in range(0, h, 2):
        for i in range(0, w, 2):
            k = (j * w + i) * 4
            if has_alpha and px[k + 3] > 0.5:
                x0, x1, y0, y1 = min(x0, i), max(x1, i), min(y0, j), max(y1, j)
    img.alpha_mode = "NONE"     # the colour bled past the outline must stay, not turn black with its zero alpha
    for o in meshes:
        me = o.data
        uv = me.uv_layers.new(name="ref")
        for poly in me.polygons:
            for li in poly.loop_indices:
                co = o.matrix_world @ me.vertices[me.loops[li].vertex_index].co
                a = (co.dot(right) - u0) / (u1 - u0)
                b = (co.dot(up) - v0) / (v1 - v0)
                uv.data[li].uv = ((x0 + a * (x1 - x0)) / w, (y0 + b * (y1 - y0)) / h)
        m = bpy.data.materials.new("ref")
        m.use_nodes = True
        t = m.node_tree
        bsdf = t.nodes["Principled BSDF"]
        bsdf.inputs["Roughness"].default_value = 0.62
        if not CLAY:
            tex = t.nodes.new("ShaderNodeTexImage")
            tex.image = img
            tex.extension = "EXTEND"
            coord = t.nodes.new("ShaderNodeUVMap")
            coord.uv_map = "ref"
            t.links.new(coord.outputs[0], tex.inputs[0])
            t.links.new(tex.outputs[0], bsdf.inputs["Base Color"])
        me.materials.clear()
        me.materials.append(m)
        for poly in me.polygons:
            poly.use_smooth = True

    scene = bpy.context.scene
    a, e = math.radians(AZ - 90), math.radians(EL)
    d = Vector((math.cos(a) * math.cos(e), math.sin(a) * math.cos(e), math.sin(e)))
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.data.lens, cam.data.clip_end = 200, span * 100
    cam.rotation_mode = "QUATERNION"
    cam.rotation_quaternion = (-d).to_track_quat("-Z", "Y")
    r = scene.render
    r.engine, r.film_transparent = "CYCLES", True
    r.resolution_x, r.resolution_y = RES
    r.image_settings.file_format, r.image_settings.color_mode = "PNG", "RGBA"
    r.filepath = str(OUT)
    c = scene.cycles
    c.samples, c.use_denoising, c.denoiser = SAMPLES, True, "OPENIMAGEDENOISE"
    if "--gpu" in args:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "OPTIX"
        prefs.get_devices()
        gpus = [x for x in prefs.devices if x.type == "OPTIX"]
        for x in prefs.devices:
            x.use = x in gpus
        c.device = "GPU" if gpus else "CPU"
    # the picture already holds its colours, so the view must not grade them
    scene.view_settings.view_transform = "Standard"
    bpy.context.view_layer.update()
    coords = [v for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z) for v in (x, y, z)]
    loc, _ = cam.camera_fit_coords(bpy.context.evaluated_depsgraph_get(), coords)
    cam.location = centre + (Vector(loc) - centre) * 1.04
    world = bpy.data.worlds.new("w")
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[1].default_value = 0.55
    world.node_tree.nodes["Background"].inputs[0].default_value = (1, 1, 1, 1)
    for name, offset, el, energy, angle in (("key", -38, 42, 1.7, 30), ("fill", 50, 12, 0.35, 70)):
        sun = bpy.data.objects.new(name, bpy.data.lights.new(name, "SUN"))
        scene.collection.objects.link(sun)
        sun.data.energy, sun.data.angle = energy, math.radians(angle)
        b, f = a + math.radians(offset), math.radians(el)
        sun.rotation_mode = "QUATERNION"
        sun.rotation_quaternion = Vector((math.cos(b) * math.cos(f), math.sin(b) * math.cos(f), math.sin(f))).to_track_quat("Z", "Y")
    bpy.context.view_layer.update()
    q = world_to_camera_view(scene, cam, centre)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.render.render(write_still=True)
    print("STATS", {"verts": len(pts), "size": [round(v, 3) for v in hi - lo], "centre_px": [round(q.x * RES[0]), round((1 - q.y) * RES[1])], "ref_box": [x0, y0, x1, y1]})


main()
