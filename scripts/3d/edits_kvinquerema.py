# Edit for library/3d/kvinquerema-trellis2/model.glb (run via render_glb.py --edit).
# The construction-kit reference has no tower, only a raised corvus that TRELLIS made into one tall
# slab near the bow (operator 2026-10-23: "záměna či fúze věže a padacího mostu"), and its oars are
# kinked kit pieces in one row. Remove both, then build: corvus after Polybius 1.22 (pole at the prow,
# bridge hauled up by a rope from the pole top, swung round to one side on its pivot), a crenellated
# tower ahead of the mast, and three banks of straight oars, all with the same angle and spacing.
# Model axes: +x = bow, z = up, hull length 1.0 (x -0.5..0.5).
import math

import bmesh
import numpy as np

MAST_X = 0.054
HULL_Y = 0.118     # outer face of the outrigger (top view); anything further out is an oar
SIDE = -1          # the side the corvus is swung to (-y faces the camera at azimuth 300)

# deck height: rays straight down along the centre line, away from the mast
deps = bpy.context.evaluated_depsgraph_get()
hits = []
for i in range(25):
    x = -0.3 + i * 0.025
    if abs(x - MAST_X) < 0.04:
        continue
    ok, loc, *_ = bpy.context.scene.ray_cast(deps, Vector((x, 0.0, 2.0)), Vector((0, 0, -1)))
    if ok:
        hits.append(loc.z)
deck_z = float(np.median(hits))
print("deck_z", round(deck_z, 3))

for o in objs:
    bm = bmesh.new()
    bm.from_mesh(o.data)
    m = o.matrix_world
    gone = [v for v in bm.verts
            if (0.29 < (m @ v.co).x < 0.415 and (m @ v.co).z > deck_z + 0.012)      # fused corvus slab
            or (abs((m @ v.co).y) > HULL_Y and abs((m @ v.co).x) < 0.42)]          # kit oars
    bmesh.ops.delete(bm, geom=gone, context="VERTS")
    bm.to_mesh(o.data)
    bm.free()
    print("removed", len(gone), "vertices from", o.name)


def box(x, y, z, sx, sy, sz, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x, y, z), rotation=rot)
    bpy.context.active_object.scale = (sx, sy, sz)
    return bpy.context.active_object


def rod(a, b, r, verts=8):
    a, b = Vector(a), Vector(b)
    d = b - a
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=d.length, location=(a + b) / 2)
    bpy.context.active_object.rotation_euler = d.to_track_quat("Z", "Y").to_euler()


# corvus
px, pole_h = 0.40, 0.24
rod((px, 0, deck_z), (px, 0, deck_z + pole_h), 0.006)
pitch, yaw, L = math.radians(70), math.radians(35) * SIDE, 0.15
pivot = Vector((px, 0, deck_z + 0.025))
d = Vector((math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch)))
mid = pivot + d * (L / 2)
box(mid.x, mid.y, mid.z, L, 0.03, 0.005, (0, -pitch, yaw))
side = Vector((-math.sin(yaw), math.cos(yaw), 0))
for s in (-1, 1):
    rail = mid + side * (s * 0.015) + Vector((0, 0, 0.006))
    box(rail.x, rail.y, rail.z, L, 0.003, 0.012, (0, -pitch, yaw))
tip = pivot + d * L
rod(tip, tip - Vector((0, 0, 0.022)), 0.003, 6)                       # the iron spike
rod((px, 0, deck_z + pole_h), tip + Vector((0, 0, 0.004)), 0.0012, 6)  # hauling rope

# tower
tx, tw, th = 0.18, 0.07, 0.075
box(tx, 0, deck_z + th / 2, tw, tw, th)
for i in range(4):
    off = -tw / 2 + tw * (i + 0.5) / 4
    for x, y in ((tx + off, tw / 2 - 0.004), (tx + off, -tw / 2 + 0.004), (tx + tw / 2 - 0.004, off), (tx - tw / 2 + 0.004, off)):
        box(x, y, deck_z + th + 0.008, 0.009, 0.009, 0.016)

# oars: three banks, ports staggered, all blades in the water on one line
WATER_Z, TIP_Y, N = deck_z - 0.10, 0.27, 22
for s in (-1, 1):
    for dz, stagger in ((-0.012, 0.0), (-0.032, 0.33), (-0.052, 0.66)):
        for k in range(N):
            x = -0.32 + (k + stagger) * 0.62 / N
            port = Vector((x, s * (HULL_Y - 0.004), deck_z + dz))
            tip = Vector((x - 0.03, s * TIP_Y, WATER_Z))
            rod(port, tip, 0.0022, 6)
            u = (tip - port).normalized()
            blade = tip - u * 0.018
            b = box(blade.x, blade.y, blade.z, 0.002, 0.036, 0.009)
            b.rotation_euler = u.to_track_quat("Y", "Z").to_euler()
