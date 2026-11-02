# Blender: the dagger from the Velsen well as a relief model, after the reconstruction drawing in the book (fig. 4.2, 21 px/cm) and the maps of scripts/plakaty/velsen_dyka_mapy.py.
#   blender -b --factory-startup -P scripts/3d/velsen_dyka.py -- MAPS_DIR
# Writes dyka-<yaw>.png into MAPS_DIR (RGBA, the hilt up), yaw 0 = the decorated face to the camera; 0.39 m tall in all, see PX_M.
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

MAPS = Path(sys.argv[sys.argv.index("--") + 1]).resolve()
CM = 21.0                   # pixels of the drawing per centimetre
THICK = 0.006               # half thickness of the sheath, metres
PX_M = 2400


def build():
    """A grid over the silhouette with a lens-shaped thickness, front and back, UVs straight from the drawing."""
    solid = np.array(_load("dyka-sit.png"))[..., 0] > 0.5
    round_ = np.load(MAPS / "dyka-tloustka.npy")
    h, w = solid.shape
    step = 2
    index, verts, uvs = {}, [], []
    for y in range(0, h, step):
        for x in range(0, w, step):
            if solid[y, x]:
                index[x, y] = len(verts)
                verts.append(((x - 292) / CM / 100, -THICK * float(round_[y, x]), (268 - y) / CM / 100))
                uvs.append((x / w, 1 - y / h))
    n = len(verts)
    verts += [(vx, -vy * 0.6, vz) for vx, vy, vz in verts]
    faces = []
    for (x, y), i in index.items():
        q = [index.get((x + step, y)), index.get((x + step, y + step)), index.get((x, y + step))]
        if None in q:
            continue
        faces.append((i, q[2], q[1], q[0]))
        faces.append((i + n, q[0] + n, q[1] + n, q[2] + n))
    me = bpy.data.meshes.new("dýka")
    me.from_pydata(verts, [], faces)
    me.update()
    me.shade_smooth()
    uv = me.uv_layers.new(name="UV").data
    loops = np.empty(len(me.loops), dtype=np.int32)
    me.loops.foreach_get("vertex_index", loops)
    for li, vi in enumerate(loops):
        uv[li].uv = uvs[vi % n]
    m = bpy.data.materials.new("výzdoba")
    m.use_nodes = True
    nt, p = m.node_tree, m.node_tree.nodes["Principled BSDF"]
    def tex(name, colorspace):
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = bpy.data.images.load(str(MAPS / name))
        t.image.colorspace_settings.name = colorspace
        return t
    nt.links.new(tex("dyka-barva.png", "sRGB").outputs["Color"], p.inputs["Base Color"])
    nt.links.new(tex("dyka-drsnost.png", "Non-Color").outputs["Color"], p.inputs["Roughness"])
    p.inputs["Metallic"].default_value = 0.85
    nt.links.new(tex("dyka-alfa.png", "Non-Color").outputs["Color"], p.inputs["Alpha"])
    b = nt.nodes.new("ShaderNodeBump")
    b.inputs["Strength"].default_value, b.inputs["Distance"].default_value = 0.8, 0.0012
    nt.links.new(tex("dyka-relief.png", "Non-Color").outputs["Color"], b.inputs["Height"])
    nt.links.new(b.outputs["Normal"], p.inputs["Normal"])
    me.materials.append(m)
    o = bpy.data.objects.new("dýka", me)
    bpy.context.collection.objects.link(o)
    return o


def _load(name):
    im = bpy.data.images.load(str(MAPS / name))
    a = np.empty(len(im.pixels), dtype=np.float32)
    im.pixels.foreach_get(a)
    return a.reshape(im.size[1], im.size[0], im.channels)[::-1]


def main():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.samples, sc.cycles.use_denoising, sc.cycles.device = 128, True, "CPU"
    sc.render.film_transparent = True
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    w = bpy.data.worlds.new("w")
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.8, 0.8, 0.78, 1)
    w.node_tree.nodes["Background"].inputs[1].default_value = 0.75
    sc.world = w
    d = bpy.data.lights.new("h", "AREA")
    d.energy, d.size = 28, 2
    l = bpy.data.objects.new("h", d)
    l.location = (-0.9, -1.5, 0.9)
    l.rotation_euler = (Vector((0, 0, 0)) - Vector(l.location)).to_track_quat("-Z", "Y").to_euler()
    sc.collection.objects.link(l)
    o = build()
    top, bottom, width = 0.135, -0.27, 0.2
    sc.render.resolution_x, sc.render.resolution_y = round(width * PX_M), round((top - bottom) * PX_M)
    cam = bpy.data.cameras.new("k")
    cam.type = "ORTHO"
    cam.ortho_scale = top - bottom
    co = bpy.data.objects.new("k", cam)
    sc.collection.objects.link(co)
    co.location = (0, -1.2, (top + bottom) / 2)
    co.rotation_euler = (math.pi / 2, 0, 0)
    sc.camera = co
    for yaw in (0, 35, 60):
        o.rotation_euler = (0, 0, math.radians(yaw))
        sc.render.filepath = str(MAPS / f"dyka-{yaw}.png")
        bpy.ops.render.render(write_still=True)
    print("HOTOVO", len(o.data.polygons))


main()
