# Blender: the Roman sword and dagger of the time of Tiberius as real models, because the generator draws long medieval swords with a crossguard.
# Gladius of Mainz type: no crossguard, a rounded guard, ribbed grip and ball pommel, about 0.72 m in all, in a leather-covered scabbard with plain tinned bronze fittings and four rings. Worn high on the right hip, the hilt at the lowest ribs.
# Pugio: the bare dagger, about 0.36 m, for the man who raises it; the decorated one in its sheath is velsen_dyka.py.
#   blender -b --factory-startup -P scripts/3d/velsen_gladius.py -- OUT_DIR
# Writes gladius-<yaw>.png and pugio-<yaw>.png (RGBA, a hilt straight up), yaw 0 = the flat side to the camera. rozmer.json: metres per pixel and the pixel of the belt ring.
import json
import math
import random
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

OUT = Path(sys.argv[sys.argv.index("--") + 1]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
PX_M = 1800     # pixels per metre


def lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def rgb(h):
    return (lin(int(h[1:3], 16) / 255), lin(int(h[3:5], 16) / 255), lin(int(h[5:7], 16) / 255), 1)


def mat(name, dark, light, metal=0.0, rough=0.6, bump=0.25, scale=240.0):
    """Used, dull surfaces: a noise between two tones, no polish."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    n, l = m.node_tree.nodes, m.node_tree.links
    p = n["Principled BSDF"]
    tc, nz, r, b = n.new("ShaderNodeTexCoord"), n.new("ShaderNodeTexNoise"), n.new("ShaderNodeValToRGB"), n.new("ShaderNodeBump")
    nz.inputs["Scale"].default_value, nz.inputs["Detail"].default_value = scale, 8.0
    r.color_ramp.elements[0].position, r.color_ramp.elements[0].color = 0.35, rgb(dark)
    r.color_ramp.elements[1].position, r.color_ramp.elements[1].color = 0.68, rgb(light)
    l.new(tc.outputs["Object"], nz.inputs["Vector"])
    l.new(nz.outputs["Fac"], r.inputs["Fac"])
    l.new(r.outputs["Color"], p.inputs["Base Color"])
    p.inputs["Metallic"].default_value, p.inputs["Roughness"].default_value = metal, rough
    b.inputs["Strength"].default_value, b.inputs["Distance"].default_value = bump, 0.002
    l.new(nz.outputs["Fac"], b.inputs["Height"])
    l.new(b.outputs["Normal"], p.inputs["Normal"])
    return m


LEATHER = mat("kůže", "#2a1d12", "#4d3724", 0, 0.62)
BRONZE = mat("pocínovaný bronz", "#6f6a58", "#a59e86", 1.0, 0.5, 0.15)
BONE = mat("kost", "#8f8267", "#b3a68a", 0, 0.5, 0.1, 400)
WOOD = mat("dřevo", "#4a321c", "#6e4d2c", 0, 0.55, 0.15)
IRON = mat("železo", "#3b3a37", "#6a6862", 1.0, 0.6, 0.35, 300)
SILVER = mat("stříbrná výplň", "#7d7a70", "#b0ac9e", 1.0, 0.45, 0.1)


def loft(name, rings, m, seg=56, z0=0.0, x0=0.0):
    """Rings (z, half width, half thickness) closed at both ends, lens-shaped section."""
    bm = bmesh.new()
    last = None
    first = None
    for z, w, t in rings:
        loop = []
        for i in range(seg):
            a = 2 * math.pi * i / seg
            # a lens rather than an ellipse: flatter sides, sharper edge
            y = t * math.sin(a) * (1 - 0.25 * math.cos(a) ** 2)
            loop.append(bm.verts.new((x0 + w * math.cos(a), y, z0 + z)))
        if last:
            for i in range(seg):
                bm.faces.new((last[i], last[(i + 1) % seg], loop[(i + 1) % seg], loop[i]))
        else:
            first = loop
        last = loop
    bm.faces.new(first[::-1])
    bm.faces.new(last)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.shade_smooth()
    me.materials.append(m)
    o = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(o)
    return o


def ring_at(name, loc, radius, tube, m):
    bpy.ops.mesh.primitive_torus_add(major_radius=radius, minor_radius=tube, major_segments=32, minor_segments=10, location=loc, rotation=(math.pi / 2, 0, 0))
    o = bpy.context.object
    o.name = name
    o.data.materials.append(m)
    bpy.ops.object.shade_smooth()
    return o


def outline(z):
    """Half width of the scabbard: nearly parallel with a slight waist, then the long point of the Mainz type."""
    d = -z
    if d < 0.2:
        return 0.038 - 0.004 * d / 0.2
    if d < 0.38:
        return 0.034 + 0.002 * (d - 0.2) / 0.18
    return max(0.0035, 0.036 * (1 - ((d - 0.38) / 0.18) ** 1.25))


def gladius():
    parts = []
    zs = [-i * 0.56 / 80 for i in range(81)]
    parts.append(loft("pochva", [(z, outline(z), 0.0125 * min(1, (0.56 + z) / 0.1 + 0.3)) for z in zs], LEATHER))
    # plain fittings: a locket, two cross bands, the chape, a thin binding down both edges
    for name, a, b in (("ústí", 0.0, -0.085), ("pás 1", -0.15, -0.165), ("pás 2", -0.295, -0.31), ("koncovka", -0.445, -0.56)):
        rs = [a + (b - a) * i / 16 for i in range(17)]
        parts.append(loft(name, [(z, outline(z) + 0.0012, 0.0125 * min(1, (0.56 + z) / 0.1 + 0.3) + 0.001) for z in rs], BRONZE))
    parts.append(loft("hrot", [(-0.552, 0.0045, 0.0045), (-0.562, 0.007, 0.007), (-0.572, 0.0045, 0.0045), (-0.578, 0.001, 0.001)], BRONZE, 24))
    # four carrying rings on the edges of the locket and below it
    for sx in (-1, 1):
        for z in (-0.03, -0.09):
            parts.append(ring_at("kroužek", (sx * (outline(z) + 0.008), 0, z), 0.0085, 0.0018, BRONZE))
    # hilt
    parts.append(loft("záštita", [(0.0, 0.03, 0.019), (0.006, 0.037, 0.024), (0.016, 0.036, 0.024), (0.026, 0.024, 0.018), (0.03, 0.016, 0.015)], BONE, 40))
    grip = [(0.03 + i * 0.086 / 40, 0.0165 + 0.002 * math.cos(i / 40 * 2 * math.pi * 4), 0.0145 + 0.002 * math.cos(i / 40 * 2 * math.pi * 4)) for i in range(41)]
    parts.append(loft("rukojeť", grip, BONE, 32))
    pom = 0.028
    parts.append(loft("hlavice", [(0.116 + pom + pom * math.sin(a), max(pom * math.cos(a), 0.001), max(pom * math.cos(a) * 0.86, 0.001)) for a in [(-90 + i * 180 / 20) * math.pi / 180 for i in range(21)]], WOOD, 32))
    parts.append(loft("nýt", [(0.116 + 2 * pom - 0.001, 0.006, 0.006), (0.116 + 2 * pom + 0.004, 0.005, 0.005), (0.116 + 2 * pom + 0.006, 0.002, 0.002)], BRONZE, 16))
    return parts, (0.0, -0.03)


def pugio():
    """The bare dagger for the man who raises it: type A blade with a midrib, about 23 cm (book p. 68), waisted, the hilt after fig. 4.2. The decorated one in its sheath is velsen_dyka.py."""
    parts = []
    def out(d):
        return 0.0305 - 0.0115 * math.sin(min(d / 0.13, 1) * math.pi / 2) if d < 0.13 else 0.019 * max(0.0, 1 - ((d - 0.13) / 0.1) ** 1.2) + 0.0006
    parts.append(loft("čepel", [(-0.23 * i / 50, out(0.23 * i / 50), 0.002) for i in range(51)], IRON))
    parts.append(loft("žebro", [(-0.225 * i / 50, 0.0035 * (1 - i / 60), 0.0038) for i in range(51)], IRON, 16))
    parts.append(loft("záštita", [(0.0, 0.034, 0.008), (0.012, 0.032, 0.009), (0.022, 0.012, 0.008)], IRON, 32))
    parts.append(loft("rukojeť", [(0.022, 0.011, 0.008), (0.05, 0.012, 0.009), (0.058, 0.019, 0.011), (0.066, 0.012, 0.009), (0.092, 0.012, 0.008)], IRON, 32))
    parts.append(loft("hlavice", [(0.092, 0.012, 0.006), (0.1, 0.028, 0.006), (0.112, 0.03, 0.006), (0.122, 0.018, 0.006), (0.126, 0.006, 0.004)], IRON, 40))
    for x, z in ((-0.012, 0.11), (0.012, 0.11), (0.0, 0.118)):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8, radius=0.0036, location=(x, -0.006, z))
        o = bpy.context.object
        o.data.materials.append(SILVER)
        parts.append(o)
    return parts, (0.0, 0.05)


def crest():
    """The transverse crest of a centurion (Vegetius; stele of T. Calidius Severus, Carnuntum): stiff horsehair standing out from an arc across the helmet, from ear to ear. Origin = the top of the helmet."""
    r0 = 0.085                  # the arc follows a helmet of about 17 cm
    rnd = random.Random(28)
    verts, faces = [], []
    for _ in range(1500):
        a = math.radians(rnd.uniform(-88, 88))
        d = Vector((math.sin(a), 0, math.cos(a)))
        base = Vector((r0 * math.sin(a), rnd.uniform(-0.016, 0.016), r0 * (math.cos(a) - 1)))
        length = rnd.uniform(0.075, 0.098)
        tip = base + (d + Vector((rnd.uniform(-0.05, 0.05), rnd.uniform(-0.1, 0.1), rnd.uniform(-0.05, 0.05)))) * length
        side = Vector((math.cos(a), 0, -math.sin(a))) * 0.0015
        back = Vector((0, 0.0015, 0))
        i = len(verts)
        verts += [tuple(base + side), tuple(base - side), tuple(base + back), tuple(tip)]
        faces += [(i, i + 1, i + 3), (i + 1, i + 2, i + 3), (i + 2, i, i + 3)]
    me = bpy.data.meshes.new("žíně")
    me.from_pydata(verts, [], faces)
    me.update()
    me.materials.append(mat("žíně", "#3c0f0c", "#74201a", 0, 0.65, 0.1, 500))
    o = bpy.data.objects.new("žíně", me)
    bpy.context.collection.objects.link(o)
    # the holder: a thin iron strip along the arc
    rings = []
    verts2, faces2 = [], []
    seg = 40
    for i in range(seg + 1):
        a = math.radians(-88 + 176 * i / seg)
        for dy, dr in ((-0.009, 0.0), (0.009, 0.0), (0.009, 0.012), (-0.009, 0.012)):
            verts2.append(((r0 + dr) * math.sin(a), dy, (r0 + dr) * math.cos(a) - r0))
    for i in range(seg):
        for k in range(4):
            faces2.append((i * 4 + k, i * 4 + (k + 1) % 4, (i + 1) * 4 + (k + 1) % 4, (i + 1) * 4 + k))
    me2 = bpy.data.meshes.new("držák")
    me2.from_pydata(verts2, [], faces2)
    me2.update()
    me2.materials.append(IRON)
    o2 = bpy.data.objects.new("držák", me2)
    bpy.context.collection.objects.link(o2)
    return [o, o2], (0.0, 0.0)


def render(parts, anchor, name, top, bottom, width=0.2):
    sc = bpy.context.scene
    holder = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(holder)
    for o in parts:
        o.parent = holder
    h = top - bottom
    sc.render.resolution_x, sc.render.resolution_y = round(width * PX_M), round(h * PX_M)
    cam = bpy.data.cameras.new("k")
    cam.type = "ORTHO"
    cam.ortho_scale = max(width, h)
    co = bpy.data.objects.new("k", cam)
    bpy.context.collection.objects.link(co)
    co.location = (0, -2, (top + bottom) / 2)
    co.rotation_euler = (math.pi / 2, 0, 0)
    sc.camera = co
    info = {"m_px": 1 / PX_M, "top": top, "bottom": bottom, "width": width, "anchor_z": anchor[1]}
    for yaw in ((0, 20) if name == "chochol" else (0, 40, 70)):
        holder.rotation_euler = (0, 0, math.radians(yaw))
        sc.render.filepath = str(OUT / f"{name}-{yaw}.png")
        bpy.ops.render.render(write_still=True)
    for o in parts:
        o.hide_render = True
    co.hide_render = True
    return info


def main():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.samples, sc.cycles.use_denoising, sc.cycles.device = 96, True, "CPU"
    sc.render.film_transparent = True
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    w = bpy.data.worlds.new("w")
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.75, 0.75, 0.74, 1)
    w.node_tree.nodes["Background"].inputs[1].default_value = 0.55
    sc.world = w
    # the same soft studio light as the pictures of the men
    d = bpy.data.lights.new("h", "AREA")
    d.energy, d.size = 60, 3
    o = bpy.data.objects.new("h", d)
    o.location = (-1.2, -2.2, 1.2)
    o.rotation_euler = (Vector((0, 0, -0.2)) - Vector(o.location)).to_track_quat("-Z", "Y").to_euler()
    sc.collection.objects.link(o)
    info = {}
    p, a = gladius()
    info["gladius"] = render(p, a, "gladius", 0.19, -0.6)
    p, a = pugio()
    info["pugio"] = render(p, a, "pugio", 0.14, -0.24, 0.14)
    p, a = crest()
    info["chochol"] = render(p, a, "chochol", 0.11, -0.1, 0.42)
    (OUT / "rozmer.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
    print("HOTOVO", info)


main()
