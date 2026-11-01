# The Hunyuan model of the axolotl in colour, free: skin, freckles, gills and lidless eyes painted by position on the body, feathery filaments added to the gills.
#   blender -b --factory-startup -P scripts/3d/axolotl_model.py -- model.glb OUT.png [--az -45] [--el 12] [--res W H] [--samples 128] [--lens 120] [--gpu] [--ortho]
# Hunyuan's model looks at -Y with the tail along +Y and z up; nx, ny, nz below are positions in its box (ny 0 = snout, 1 = tail tip).
# Eye centres were read from orthographic views of this very model.
import json
import math
import random
import sys
from pathlib import Path

import bmesh
import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "engine" / "blender"))
import parts_materials as pm  # noqa: E402

args = sys.argv[sys.argv.index("--") + 1:]
GLB, OUT = args[0], Path(args[1]).resolve()   # Blender writes a relative render path somewhere else than the working directory


def opt(name, default, n=1):
    if name in args:
        i = args.index(name)
        return args[i + 1] if n == 1 else args[i + 1:i + 1 + n]
    return default


AZ, EL = float(opt("--az", -45)), float(opt("--el", 12))
RES = [int(v) for v in opt("--res", (1800, 1300), 2)]
SAMPLES = int(opt("--samples", 128))
EYES = json.loads(opt("--eyes", "[]"))   # [[nx, ny, nz, r], ...] in box units of x
LENS = float(opt("--lens", 120))
ORTHO = "--ortho" in args
CLAY = "--clay" in args


def smooth(a, b, x):
    t = max(0.0, min(1.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


def skin_material():
    m, t, bsdf = pm.new_mat("skin", 0.48)
    bsdf.inputs["Coat Weight"].default_value = 0.1
    bsdf.inputs["Coat Roughness"].default_value = 0.18
    co = t.nodes.new("ShaderNodeTexCoord").outputs["Object"]
    attr = t.nodes.new("ShaderNodeVertexColor")
    attr.layer_name = "paint"
    sep = t.nodes.new("ShaderNodeSeparateColor")
    t.links.new(attr.outputs["Color"], sep.inputs[0])
    base = pm.ramp_of(t, pm.noise_of(t, co, 26.0, 5.0), "#f1d8c8", "#f6e5d8", 0.3, 0.7)
    gill_col = pm.ramp_of(t, sep.outputs["Blue"], "#eaa2a4", "#e8868e", 0.15, 0.8)
    # big peach freckles on the head and back, fine dark specks everywhere
    freck = pm.noise_of(t, co, 70.0, 2.0)
    fr = t.nodes.new("ShaderNodeValToRGB")
    fr.color_ramp.elements[0].position, fr.color_ramp.elements[1].position = 0.58, 0.63
    t.links.new(freck, fr.inputs[0])
    gain = t.nodes.new("ShaderNodeMath")
    gain.operation = "MULTIPLY"
    t.links.new(fr.outputs[0], gain.inputs[0])
    t.links.new(sep.outputs["Green"], gain.inputs[1])
    mix_f = t.nodes.new("ShaderNodeMix")
    mix_f.data_type = "RGBA"
    t.links.new(gain.outputs[0], mix_f.inputs["Factor"])
    t.links.new(base, mix_f.inputs["A"])
    mix_f.inputs["B"].default_value = pm.srgb("#d98a66")
    specks = pm.noise_of(t, co, 240.0, 1.0)
    sp = t.nodes.new("ShaderNodeValToRGB")
    sp.color_ramp.elements[0].position, sp.color_ramp.elements[1].position = 0.66, 0.70
    t.links.new(specks, sp.inputs[0])
    mix_s = t.nodes.new("ShaderNodeMix")
    mix_s.data_type = "RGBA"
    mul = t.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    mul.inputs[1].default_value = 0.22
    t.links.new(sp.outputs[0], mul.inputs[0])
    t.links.new(mul.outputs[0], mix_s.inputs["Factor"])
    t.links.new(mix_f.outputs["Result"], mix_s.inputs["A"])
    mix_s.inputs["B"].default_value = pm.srgb("#8a6a68")
    mix_g = t.nodes.new("ShaderNodeMix")
    mix_g.data_type = "RGBA"
    t.links.new(sep.outputs["Red"], mix_g.inputs["Factor"])
    t.links.new(mix_s.outputs["Result"], mix_g.inputs["A"])
    t.links.new(gill_col, mix_g.inputs["B"])
    occ = t.nodes.new("ShaderNodeAmbientOcclusion")
    occ.samples = 8
    occ.inputs["Distance"].default_value = 0.03
    dark = t.nodes.new("ShaderNodeMix")
    dark.data_type, dark.blend_type = "RGBA", "MULTIPLY"
    dark.inputs["Factor"].default_value = 0.7
    t.links.new(mix_g.outputs["Result"], dark.inputs["A"])
    t.links.new(occ.outputs["AO"], dark.inputs["B"])
    t.links.new(dark.outputs["Result"], bsdf.inputs["Base Color"])
    bsdf.inputs["Subsurface Weight"].default_value = 0.65
    bsdf.inputs["Subsurface Radius"].default_value = (0.012, 0.004, 0.003)
    bsdf.inputs["Subsurface Scale"].default_value = 1.0
    bp = t.nodes.new("ShaderNodeBump")
    bp.inputs["Strength"].default_value = 0.3
    bp.inputs["Distance"].default_value = 0.0025
    # fine skin grain over the grooves between the ribs
    wave = t.nodes.new("ShaderNodeTexWave")
    wave.wave_type, wave.bands_direction = "BANDS", "Y"
    wave.inputs["Scale"].default_value = 9.0
    wave.inputs["Distortion"].default_value = 0.6
    t.links.new(co, wave.inputs["Vector"])
    add = t.nodes.new("ShaderNodeMath")
    add.operation = "ADD"
    t.links.new(pm.noise_of(t, co, 180.0, 4.0), add.inputs[0])
    t.links.new(wave.outputs["Fac"], add.inputs[1])
    t.links.new(add.outputs[0], bp.inputs["Height"])
    t.links.new(bp.outputs[0], bsdf.inputs["Normal"])
    return m


def main():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    bpy.ops.import_scene.gltf(filepath=GLB)
    ob = next(o for o in bpy.data.objects if o.type == "MESH")
    bpy.context.view_layer.update()
    me = ob.data
    world = ob.matrix_world
    pts = [world @ v.co for v in me.vertices]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    centre = (lo + hi) / 2
    half = (hi.x - lo.x) / 2
    span_y, span_z = hi.y - lo.y, hi.z - lo.z
    nx = lambda p: (p.x - centre.x) / half
    ny = lambda p: (p.y - lo.y) / span_y
    nz = lambda p: (p.z - lo.z) / span_z

    # paint: R = gill, G = where the freckles sit, B = along a gill from base to tip
    gill, freckle, tip = [], [], []
    for p in pts:
        g = smooth(0.32, 0.37, abs(nx(p))) * smooth(0.27, 0.32, nz(p)) * (1 - smooth(0.6, 0.7, ny(p)))
        gill.append(g)
        freckle.append((1 - smooth(0.28, 0.5, ny(p))) * smooth(0.5, 0.7, nz(p)) * 0.9 + 0.1)
        tip.append(smooth(0.34, 0.95, abs(nx(p))))
    col = me.color_attributes.new("paint", "FLOAT_COLOR", "POINT")
    for i in range(len(pts)):
        col.data[i].color = (gill[i], freckle[i], tip[i], 1)
    me.materials.clear()
    if CLAY:
        me.materials.append(pm.new_mat("clay", 0.6)[0])
    else:
        me.materials.append(skin_material())
    for poly in me.polygons:
        poly.use_smooth = True

    if not CLAY:
        # lidless eyes: black glass spheres set into the bumps of the model; the front of each bump is found by a ray
        bm = bmesh.new()
        bm.from_mesh(me)
        bm.transform(world)
        tree = BVHTree.FromBMesh(bm)
        bm.free()
        found = []
        for sx in (-1, 1):
            start = Vector((centre.x + sx * 0.181 * half, lo.y - 1.0, lo.z + 0.518 * span_z))
            hit = tree.ray_cast(start, Vector((0, 1, 0)))[0]
            found.append((sx * 0.181, (hit.y + 0.0095 - lo.y) / span_y, 0.518, 0.0118 / half))
        eye = pm.new_mat("eye", 0.08)
        eye[2].inputs["Base Color"].default_value = (0.008, 0.007, 0.007, 1)
        eye[2].inputs["Specular IOR Level"].default_value = 0.8
        for k, (ex, ey, ez, er) in enumerate(EYES or found):
            bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=32, radius=er * half, location=(centre.x + ex * half, lo.y + ey * span_y, lo.z + ez * span_z))
            s = bpy.context.active_object
            s.name = f"eye{k}"
            s.data.materials.append(eye[0])
            for poly in s.data.polygons:
                poly.use_smooth = True

        # filaments: thin curved threads on the gill stalks, what a mesh of this size cannot hold
        rng = random.Random(7)
        hairs = bpy.data.curves.new("hairs", "CURVE")
        hairs.dimensions, hairs.bevel_depth, hairs.bevel_resolution = "3D", 0.00016, 1
        rows = [i for i, g in enumerate(gill) if g > 0.75 and abs(nx(pts[i])) > 0.37]
        rng.shuffle(rows)
        count = 0
        normal_of = me.vertices
        nm = world.to_3x3()
        for i in rows[:7000]:
            p = pts[i]
            n = (nm @ normal_of[i].normal).normalized()
            out = Vector((p.x - centre.x, 0, 0)).normalized()
            length = half * rng.uniform(0.035, 0.085) * (1.1 - 0.6 * tip[i])
            d = (n + out * 0.15 + Vector((rng.gauss(0, 0.3), rng.gauss(0, 0.3), rng.gauss(0.05, 0.3)))).normalized()
            sp = hairs.splines.new("POLY")
            sp.points.add(4)
            q = p.copy()
            for j in range(5):
                sp.points[j].co = (*q, 1)
                sp.points[j].radius = 1.0 - j * 0.18
                d = (d + Vector((rng.gauss(0, 0.12), rng.gauss(0, 0.12), rng.gauss(0.07, 0.12)))).normalized()
                q = q + d * length / 4
            count += 1
        fil = pm.new_mat("filament", 0.38)
        fil[2].inputs["Base Color"].default_value = pm.srgb("#e88e92")
        fil[2].inputs["Subsurface Weight"].default_value = 0.5
        fil[2].inputs["Subsurface Radius"].default_value = (0.01, 0.002, 0.002)
        hairs.materials.append(fil[0])
        bpy.context.scene.collection.objects.link(bpy.data.objects.new("hairs", hairs))
        print("hairs", count)

    scene = bpy.context.scene
    a, e = math.radians(AZ - 90), math.radians(EL)
    d = Vector((math.cos(a) * math.cos(e), math.sin(a) * math.cos(e), math.sin(e)))
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.data.lens, cam.data.clip_end = LENS, 100 * span_y
    if ORTHO:
        cam.data.type = "ORTHO"
    cam.rotation_mode = "QUATERNION"
    cam.rotation_quaternion = (-d).to_track_quat("-Z", "Y")
    r = scene.render
    r.engine, r.film_transparent = "CYCLES", True
    r.resolution_x, r.resolution_y = RES
    r.image_settings.file_format, r.image_settings.color_mode = "PNG", "RGBA"
    r.filepath = str(OUT)
    c = scene.cycles
    c.samples, c.use_denoising, c.denoiser = SAMPLES, True, "OPENIMAGEDENOISE"
    c.max_bounces = 10
    if "--gpu" in args:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "OPTIX"
        prefs.get_devices()
        gpus = [x for x in prefs.devices if x.type == "OPTIX"]
        for x in prefs.devices:
            x.use = x in gpus
        c.device = "GPU" if gpus else "CPU"
    scene.view_settings.view_transform = "Standard"
    bpy.context.view_layer.update()
    coords = [v for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z) for v in (x, y, z)]
    loc, scale = cam.camera_fit_coords(bpy.context.evaluated_depsgraph_get(), coords)
    cam.location = centre + (Vector(loc) - centre) * 1.04
    if ORTHO:
        cam.data.ortho_scale = scale * 1.04
    w = bpy.data.worlds.new("w")
    scene.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (1, 1, 1, 1)
    w.node_tree.nodes["Background"].inputs[1].default_value = 0.42
    for name, offset, el, energy, angle in (("key", -40, 55, 1.9, 28), ("fill", 55, 15, 0.35, 70), ("rim", 165, 30, 0.9, 20)):
        sun = bpy.data.objects.new(name, bpy.data.lights.new(name, "SUN"))
        scene.collection.objects.link(sun)
        sun.data.energy, sun.data.angle = energy, math.radians(angle)
        b, f = a + math.radians(offset), math.radians(el)
        sun.rotation_mode = "QUATERNION"
        sun.rotation_quaternion = Vector((math.cos(b) * math.cos(f), math.sin(b) * math.cos(f), math.sin(f))).to_track_quat("Z", "Y")
    bpy.context.view_layer.update()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.render.render(write_still=True)

    def uv(x, y, z):
        q = world_to_camera_view(scene, cam, Vector((x, y, z)))
        return [round(q.x * RES[0], 1), round((1 - q.y) * RES[1], 1)]
    print("STATS", json.dumps({"lo": [round(v, 4) for v in lo], "hi": [round(v, 4) for v in hi], "grid": {f"{i}/{j}": uv(centre.x + i * half / 2, lo.y, lo.z + j * span_z / 4) for i in (-1, 0, 1) for j in (2, 3)}}))


main()
