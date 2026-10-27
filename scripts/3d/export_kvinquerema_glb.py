# The quinquereme of scripts/3d/lod_kvinquerema.py (built from reconstruction numbers, tuned for the infographic)
# as a GLB for the 3D library, so it can stand in 3D scenes (free):
#   blender -b --factory-startup -P scripts/3d/export_kvinquerema_glb.py -- out.glb
# Runs the build script unchanged with --nosea (it renders its own clay PNGs next to out.glb), then exports every
# mesh that is rendered, without the script's scale figure beside the bow (a 3D scene has its own 1.72 m figure).
# Metres, x towards the bow, waterline at z = 0.
import sys
from pathlib import Path

import bpy

out = Path(sys.argv[sys.argv.index("--") + 1])
script = Path(__file__).with_name("lod_kvinquerema.py")
sys.argv = [sys.argv[0], "--", str(out.with_suffix("")), "--nosea"]
ns = {"__name__": "__main__", "__file__": str(script)}
exec(compile(script.read_text(encoding="utf-8"), str(script), "exec"), ns)
skip = set(ns["scale_figure"])

bpy.ops.object.select_all(action="DESELECT")
meshes = [o for o in bpy.context.scene.objects if o.type == "MESH" and not o.hide_render and o not in skip]
for o in meshes:
    o.select_set(True)
print(f"EXPORT {len(meshes)} meshes")
bpy.ops.export_scene.gltf(filepath=str(out), export_format="GLB", use_selection=True, export_materials="NONE",
                          export_apply=True)
