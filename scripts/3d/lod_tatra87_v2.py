# Tatra 87 (1936-1950), third and last round of the check loop (docs/3d-lod-postup.md, GRAFIK#71; free):
#   blender -b -P scripts/3d/lod_tatra87_v2.py -- out.glb
# Round 1 is scripts/3d/lod_tatra87.py, the model in library/3d/tatra87-blender. Changed after its check: top of the
# sections from the straightened side photo; round 3: the fin no longer stands out of the outline, headlights back
# out of the raised nose.
# Every size is in DIM (metres) with its source; "odhad" = our estimate, no published figure found.
# Axes: x towards the rear (front bumper at x = 0), y across, z up, ground z = 0.
import math
import sys

import bmesh
import bpy

DIM = {
    "length": 4.74,       # en.wikipedia Tatra 87 (aerotatra.czweb.org)
    "width": 1.67,        # en.wikipedia Tatra 87 (aerotatra.czweb.org)
    "height": 1.50,       # en.wikipedia Tatra 87 (aerotatra.czweb.org)
    "wheelbase": 2.85,    # en.wikipedia Tatra 87 (tatraportal.sk)
    "front_axle": 0.80,   # odhad: front overhang
    "track": 1.30,        # odhad
    "wheel_r": 0.36,      # odhad: 6.00-16 tyre
    "clearance": 0.20,    # odhad
    "fin_h": 0.08,        # odhad: blade along the rear deck
}
out = sys.argv[sys.argv.index("--") + 1]
L, W, H = DIM["length"], DIM["width"], DIM["height"]

# side profile: (x, bottom z, top z, half width, roof half width) — top from the straightened side photo
# (docs/spikes/2026-10-31-lod-smycka.md), minus the fin's height over the rear deck
PROFILE = [
    (0.00, 0.30, 0.72, 0.62, 0.55),
    (0.25, 0.30, 1.00, 0.76, 0.60),
    (0.80, 0.20, 1.15, 0.82, 0.62),
    (1.35, 0.20, 1.35, 0.835, 0.60),
    (1.75, 0.20, 1.47, 0.835, 0.58),
    (2.20, 0.20, H, 0.835, 0.56),
    (2.90, 0.20, 1.34, 0.835, 0.56),
    (3.50, 0.22, 1.18, 0.82, 0.56),
    (4.20, 0.26, 0.78, 0.76, 0.52),
    (L, 0.36, 0.50, 0.60, 0.45),
]
SEG = 32


def section(x, zb, zt, hw, rw):
    pts = []
    for i in range(SEG):
        a = 2 * math.pi * i / SEG
        c, s = math.cos(a), math.sin(a)
        # rounded box below the belt line, narrower greenhouse above it
        half = rw if s > 0.35 else hw
        y = half * math.copysign(abs(c) ** 0.6, c)
        z = (zb + zt) / 2 + (zt - zb) / 2 * math.copysign(abs(s) ** 0.8, s)
        pts.append((x, y, z))
    return pts


bpy.ops.wm.read_factory_settings(use_empty=True)
bm = bmesh.new()
rings = [[bm.verts.new(p) for p in section(*row)] for row in PROFILE]
for a, b in zip(rings, rings[1:]):
    for i in range(SEG):
        bm.faces.new((a[i], a[(i + 1) % SEG], b[(i + 1) % SEG], b[i]))
bm.faces.new(list(reversed(rings[0])))
bm.faces.new(rings[-1])
mesh = bpy.data.meshes.new("body")
bm.to_mesh(mesh)
body = bpy.data.objects.new("body", mesh)
bpy.context.scene.collection.objects.link(body)
body.modifiers.new("smooth", "SUBSURF").levels = 2

# dorsal fin along the centre line over the rear deck, its top on the outline of the side photo
bpy.ops.mesh.primitive_cube_add(size=1)
fin = bpy.context.object
fin.scale = (1.5, 0.04, DIM["fin_h"])
fin.location = (3.3, 0, 1.22 - DIM["fin_h"] / 2)
fin.rotation_euler = (0, math.radians(17), 0)

for ax in (DIM["front_axle"], DIM["front_axle"] + DIM["wheelbase"]):
    for side in (-1, 1):
        bpy.ops.mesh.primitive_cylinder_add(radius=DIM["wheel_r"], depth=0.17,
                                            location=(ax, side * DIM["track"] / 2, DIM["wheel_r"]),
                                            rotation=(math.radians(90), 0, 0))
for y in (-0.42, 0, 0.42):  # three headlights, the middle one in the nose
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.1, location=(0.12 if y else 0.08, y * 1.2, 0.74 if y else 0.62))

bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", export_apply=True)
print("bbox L W H", L, W, H)
