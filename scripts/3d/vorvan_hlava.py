# Kontrola hlavy vorvaně z modelu ve scéně: zepředu proti tlamě, šikmo a z boku, bílý model na šedé (operátor 5. 11.:
# „Ta hlava vypadá zepředu takto“). Blender přes velsen_studna_run.py pod zámkem těžké práce:
#   python scripts/3d/velsen_studna_run.py vorvan_hlava.py OUT_DIR --vorvan vorvan-hunyuan-infografika/v1
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vorvan_scena as vs  # noqa: E402


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    out = Path(argv[0]).resolve()
    vorvan = argv[argv.index("--vorvan") + 1] if "--vorvan" in argv else "vorvan-hunyuan-infografika/v1"
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    r = scene.render
    r.engine, r.resolution_x, r.resolution_y = "CYCLES", 900, 900
    scene.cycles.samples, scene.cycles.device = 24, "CPU"
    world = bpy.data.worlds.new("Šedá")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.35, 0.35, 0.35, 1)
    scene.world = world
    sun = bpy.data.objects.new("Slunce", bpy.data.lights.new("Slunce", "SUN"))
    sun.data.energy = 3.0
    sun.rotation_euler = (math.radians(40), math.radians(-30), math.radians(20))
    bpy.context.collection.objects.link(sun)

    whale = vs.import_glb(vs.DATA / "library" / "3d" / vorvan / "model.glb")
    lo, hi = vs.normalize(whale, vs.LENGTH)
    if not vs.head_is_min_x(whale, lo, hi):
        whale.rotation_euler = (0, 0, math.radians(180))
        bpy.ops.object.transform_apply(rotation=True)
        lo, hi = vs.bbox(whale)
    cam = bpy.data.objects.new("Kamera", bpy.data.cameras.new("Kamera"))
    bpy.context.collection.objects.link(cam)
    scene.camera = cam
    cam.data.type = "ORTHO"
    head = Vector((lo.x + 2.5, 0, (lo.z + hi.z) / 2))
    views = {"zepredu": Vector((-1, 0, 0)), "sikmo": Vector((-1, -0.8, 0.35)), "zboku": Vector((0, -1, 0))}
    out.mkdir(parents=True, exist_ok=True)
    for name, d in views.items():
        cam.data.ortho_scale = 6.5
        vs.look(cam, head + d.normalized() * 40, head, Vector((0, 0, 1)))
        r.filepath = str(out / f"hlava-{name}.png")
        bpy.ops.render.render(write_still=True)
        print("render", r.filepath)


main()
