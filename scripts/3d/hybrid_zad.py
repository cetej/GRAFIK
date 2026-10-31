# Front of a generated model + rear of a dimension model, cut at one place along the length (GRAFIK#72, free):
#   blender -b --factory-startup -P scripts/3d/hybrid_zad.py -- ai.glb lod.glb out.glb CUT_M
# ai.glb: stretched to real size by engine/blender/stretch.py, long axis Y, nose at -Y. lod.glb: x towards the rear,
# nose at x = 0, ground z = 0. The two surfaces are only cut and joined, not bridged: for a clay view, not for printing.
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

a = sys.argv[sys.argv.index("--") + 1:]
ai_path, lod_path, out, cut = a[0], a[1], a[2], float(a[3])
bpy.ops.wm.read_factory_settings(use_empty=True)


def load(path):
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    return [o for o in bpy.context.scene.objects if o not in before and o.type == "MESH"]


def keep(objs, matrix, keep_low):
    """Everything in lod coordinates (via matrix), cut at x = cut, one side thrown away."""
    bm = bmesh.new()
    for o in objs:
        tmp = o.data.copy()
        tmp.transform(matrix @ o.matrix_world)
        bm.from_mesh(tmp)
        bpy.data.meshes.remove(tmp)
    geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
    bmesh.ops.bisect_plane(bm, geom=geom, plane_co=Vector((cut, 0, 0)), plane_no=Vector((1, 0, 0)),
                           clear_outer=keep_low, clear_inner=not keep_low)
    return bm


ai = load(ai_path)
pts = [o.matrix_world @ v.co for o in ai for v in o.data.vertices]
ymin = min(p.y for p in pts)
xmid = (min(p.x for p in pts) + max(p.x for p in pts)) / 2
zmin = min(p.z for p in pts)
# ai (x, y, z) -> lod (y - ymin, xmid - x, z - zmin): a rotation about Z, so normals stay outward
to_lod = Matrix(((0, 1, 0, -ymin), (-1, 0, 0, xmid), (0, 0, 1, -zmin), (0, 0, 0, 1)))
front = keep(ai, to_lod, True)
rear = keep(load(lod_path), Matrix.Identity(4), False)
for o in list(bpy.context.scene.objects):
    bpy.data.objects.remove(o)
for name, bm in (("front", front), ("rear", rear)):
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    bpy.context.scene.collection.objects.link(bpy.data.objects.new(name, mesh))
bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", export_normals=False)
