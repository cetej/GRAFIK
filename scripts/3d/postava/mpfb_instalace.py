# BLENDER_USER_RESOURCES=GRAFIK/run/mpfb_profil blender -b --python mpfb_instalace.py
# Balíky MakeHuman (CC0) pak rozbalit do <profil>/extensions/.user/user_default/mpfb/data
# (C:/Users/stock/ai/models/free-2026-10-05/mpfb2_asset_packs/makehuman_system_assets_cc0.zip a _poses_cc0.zip).
# MPFB2 do oddělených uživatelských dat Blenderu (BLENDER_USER_RESOURCES), nastavení operátora se nemění.
import bpy, sys, os, addon_utils
ZIP = r"C:/Users/stock/ai/models/free-2026-10-05/mpfb2_blender_addon/add-on-mpfb-v2.0.17.zip"
print("INFO user resources", bpy.utils.resource_path("USER"))
try:
    bpy.ops.extensions.package_install_files(filepath=ZIP, repo="user_default", enable_on_install=True)
except Exception as e:
    print("INFO install error", e)
mods = [m.__name__ for m in addon_utils.modules() if "mpfb" in m.__name__]
print("INFO moduly", mods)
for m in mods:
    addon_utils.enable(m, default_set=True, persistent=True)
bpy.ops.wm.save_userpref()
print("INFO zapnuto", [a for a in bpy.context.preferences.addons.keys() if "mpfb" in a])
print("DONE")
