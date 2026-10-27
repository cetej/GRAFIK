# Rotunda of St Martin, Vyšehrad (11th c.) built from published numbers (free):
#   blender -b -P scripts/3d/lod_rotunda_martin.py -- out.glb
# Every size is in DIM (metres) with its source; "odhad" = our estimate, no published figure found.
# Axes: x towards the apse (east), y across, z up, ground z = 0.
import math
import sys

import bpy

DIM = {
    "inner_d": 6.5,        # cs.wikipedia Rotunda sv. Martina (Vyšehrad)
    "wall": 0.95,          # cs.wikipedia: zdivo až 95 cm
    "apse_out": 2.2,       # cs.wikipedia: apsida vystupuje o 2,2 m
    "apse_w": 4.0,         # odhad
    "wall_h": 6.2,         # odhad: from the photo, door 2.6 m as a scale
    "roof_h": 1.4,         # odhad
    "apse_h": 4.2,         # odhad
    "lantern_r": 1.05,     # odhad
    "lantern_h": 2.4,      # odhad
    "lantern_roof": 1.1,   # odhad
    "portal": (1.9, 0.35, 3.3),  # odhad: width, projection, height
}
out = sys.argv[sys.argv.index("--") + 1]
R = DIM["inner_d"] / 2 + DIM["wall"]

bpy.ops.wm.read_factory_settings(use_empty=True)
add = bpy.ops.mesh
add.primitive_cylinder_add(vertices=64, radius=R, depth=DIM["wall_h"], location=(0, 0, DIM["wall_h"] / 2))
add.primitive_cylinder_add(vertices=64, radius=R + 0.25, depth=0.25, location=(0, 0, DIM["wall_h"]))  # cornice
add.primitive_cone_add(vertices=64, radius1=R + 0.35, radius2=DIM["lantern_r"] + 0.1, depth=DIM["roof_h"],
                       location=(0, 0, DIM["wall_h"] + DIM["roof_h"] / 2))
z = DIM["wall_h"] + DIM["roof_h"]
add.primitive_cylinder_add(vertices=48, radius=DIM["lantern_r"], depth=DIM["lantern_h"], location=(0, 0, z + DIM["lantern_h"] / 2))
z += DIM["lantern_h"]
add.primitive_cone_add(vertices=48, radius1=DIM["lantern_r"] + 0.15, depth=DIM["lantern_roof"], location=(0, 0, z + DIM["lantern_roof"] / 2))
add.primitive_cylinder_add(radius=0.04, depth=0.9, location=(0, 0, z + DIM["lantern_roof"] + 0.4))  # cross
add.primitive_cube_add(size=1, location=(0, 0, z + DIM["lantern_roof"] + 0.6))
bpy.context.object.scale = (0.04, 0.45, 0.04)

# apse: half cylinder with a half-cone roof, on the east side
aw = DIM["apse_w"] / 2
add.primitive_cylinder_add(vertices=48, radius=aw, depth=DIM["apse_h"], location=(R - aw + DIM["apse_out"], 0, DIM["apse_h"] / 2))
add.primitive_cone_add(vertices=48, radius1=aw + 0.25, depth=1.0, location=(R - aw + DIM["apse_out"], 0, DIM["apse_h"] + 0.5))

# portal on the west side
pw, pp, ph = DIM["portal"]
add.primitive_cube_add(size=1, location=(-R - pp / 2 + 0.1, 0, ph / 2))
bpy.context.object.scale = (pp + 0.2, pw, ph)

bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", export_apply=True)
print("outer diameter", 2 * R)
