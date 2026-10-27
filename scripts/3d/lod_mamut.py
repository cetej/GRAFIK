# Woolly mammoth (adult male) built from published numbers with metaballs (free):
#   blender -b -P scripts/3d/lod_mamut.py -- out.glb
# Every size is in DIM (metres) with its source; "odhad" = our estimate, no published figure found.
# Axes: x towards the head, y across, z up, ground z = 0.
import math
import sys

import bpy

DIM = {
    "shoulder": 3.0,      # en.wikipedia Woolly mammoth: males 2.8-3.15 m
    "body_l": 3.6,        # odhad: rump to chest
    "leg_r": 0.28,        # odhad
    "tusk_l": 2.6,        # odhad (record 4.2 m, en.wikipedia)
    "tusk_r": 0.09,       # odhad
    "trunk_l": 2.0,       # odhad
    "ear": 0.38,          # en.wikipedia: ears about 38 cm long
}
out = sys.argv[sys.argv.index("--") + 1]
S, BL = DIM["shoulder"], DIM["body_l"]

bpy.ops.wm.read_factory_settings(use_empty=True)
mb = bpy.data.metaballs.new("body")
mb.resolution = 0.05
mb.threshold = 0.25  # low threshold: neighbouring elements melt into one body instead of separate balls
obj = bpy.data.objects.new("body", mb)
bpy.context.scene.collection.objects.link(obj)


def ball(x, y, z, r, kind="BALL", size=None):
    e = mb.elements.new(type=kind)
    e.co, e.radius = (x, y, z), r
    if size:
        e.size_x, e.size_y, e.size_z = size


# torso: high shoulder, back sloping down to the rump (mammoth profile)
ball(0.4, 0, S - 0.9, 1.0, "ELLIPSOID", (1.1, 0.75, 0.9))
ball(-0.9, 0, S - 1.15, 0.95, "ELLIPSOID", (1.0, 0.75, 0.8))
ball(0.7, 0, S - 0.35, 0.55)                     # shoulder hump
ball(1.55, 0, S - 0.2, 0.62)                     # domed head
ball(1.9, 0, S - 0.75, 0.42)                     # face
for x in (0.55, -1.15):                          # legs, front and back: a dense column of balls
    for y in (-0.45, 0.45):
        for i in range(8):
            z = 0.15 + i * 0.2
            ball(x, y, z, DIM["leg_r"] + 0.04 * i / 7)
# trunk hangs down and curls forward at the tip
for i in range(16):
    t = i / 15
    ball(2.15 + 0.25 * math.sin(t * 2.4), 0, S - 1.0 - t * (DIM["trunk_l"] - 0.3), 0.18 - 0.08 * t)
for y in (-0.55, 0.55):                          # small ears
    ball(1.35, y, S - 0.35, DIM["ear"] / 2)
ball(-1.95, 0, S - 1.25, 0.1)                    # tail
bpy.context.view_layer.objects.active = obj
obj.select_set(True)
bpy.ops.object.convert(target="MESH")

# tusks: curve out, then up and inwards
for side in (-1, 1):
    pts = []
    for i in range(24):
        t = i / 23
        a = t * math.radians(200)
        pts.append((2.05 + 0.8 * math.sin(a), side * (0.25 + 0.55 * math.sin(a / 2) - 0.25 * t), S - 1.15 - 0.6 * math.sin(a) + 1.1 * t))
    cu = bpy.data.curves.new("tusk", "CURVE")
    cu.dimensions = "3D"
    sp = cu.splines.new("POLY")
    sp.points.add(len(pts) - 1)
    for p, c in zip(sp.points, pts):
        p.co = (*c, 1)
    cu.bevel_depth = DIM["tusk_r"]
    tusk = bpy.data.objects.new("tusk", cu)
    bpy.context.scene.collection.objects.link(tusk)
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = tusk
    tusk.select_set(True)
    bpy.ops.object.convert(target="MESH")

bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", export_apply=True)
print("shoulder", S)
