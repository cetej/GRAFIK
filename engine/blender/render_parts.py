# Coloured render of a parts model from a named view, free:
#   blender -b --factory-startup -P engine/blender/render_parts.py -- spec.json OUT_DIR '{"pohled": "rez", "res": [1920, 1080]}'
# Writes OUT_DIR/obraz.png (RGBA), OUT_DIR/body.json and, with "vrstvy", OUT_DIR/vrstva-<name>.png: one group of parts alone on
# transparent, the others cut it out and keep their shadows, so the picture can be edited object by object. With "samostatne"
# each layer is rendered without the others (translucent skin apart from the organs behind it, as the whale page needs).
# "perspektiva" uses a 50 mm camera instead of the orthographic one; "pruhledne" makes listed parts see-through in an ellipse;
# "hlina" paints everything matte light clay, the shape reference for the FLUX texture (engine/textura3d.py).
# body.json holds the canvas position of every part and of the description's `kotvy`, so labels sit exactly on the model.
# Generalised from the --render path of scripts/3d/lod_pantheon.py; that script stays as it is.
import json
import math
import os
import sys
from pathlib import Path

import bpy
import numpy as np
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, str(Path(__file__).resolve().parent))

import lod_parts  # noqa: E402
import parts_materials as pm  # noqa: E402

args = sys.argv[sys.argv.index("--") + 1:]
SPEC, OUT, REQ = json.loads(Path(args[0]).read_text(encoding="utf-8")), Path(args[1]), json.loads(args[2])
VIEWS = {
    "celek": {"az": -125, "el": 26},
    "rez": {"cut": True, "az": -122, "el": 12},
    "ctvrt": {"cut": "ctvrt", "az": -135, "el": 24},     # a quarter removed: both cuts meet in the middle, the outer wall stays on both sides
    "pudorys": {"az": -90, "el": 89.9},
    "pruceli": {"az": 180, "el": 0},
    "bok": {"az": -90, "el": 0},
    "rozklad": {"az": -125, "el": 24},
}
MARGIN = 1.06
VIEW = {**VIEWS[REQ["pohled"]], **(REQ.get("kamera") or {})}
RES = REQ.get("res", [1920, 1080])
SAMPLES = int(REQ.get("samples", 96))
ORGANIC = ("telo", "prurezy", "elipsoid", "deska", "zuby")
SOLID = ("prstenec", "hlediste", "kopule", "kvadr", "disk", "rada", "pricky") + ORGANIC
DECOR = lod_parts.DECOR
PARTS = {p["nazev"]: p for p in SPEC["dily"]}


def section_x():
    """A portico stays whole in a section: the near half of the building is removed only behind it. A quarter cut goes to the middle."""
    if VIEW.get("cut") == "ctvrt":
        return 0.0
    fronts = [p["x_zed"] + 1.4 for p in SPEC["dily"] if p["typ"] == "portik" and not p["azimut"]]
    return max(fronts) if fronts else -1e4


def near_boxes(x_cut):
    """What a section view takes away. A plinth (`sokl`) keeps the low part of the removed quarter, a strip of width `pas` also below ground:
    the plan of the piers stays on view and the rest of the quarter shows the underground in section."""
    if not VIEW.get("cut"):
        return []
    if VIEW["cut"] != "ctvrt":
        return [((x_cut, -5000, -5000), (5000, 0, 5000))]
    plinth = REQ.get("sokl")
    if not plinth:
        return [((-5000, -5000, -5000), (0, 0, 5000))]
    return [((-5000, -5000, plinth["z"]), (0, 0, 5000)), ((-5000, -5000, -5000), (-plinth["pas"], 0, 5000))]


def on_cut(p, boxes):
    """A face the section made: on a side of a removed box, inside its other two extents."""
    c, n = p.center, p.normal
    for lo, hi in boxes:
        for i in range(3):
            if abs(n[i]) > 0.99 and (abs(c[i] - lo[i]) < 0.02 or abs(c[i] - hi[i]) < 0.02) and all(lo[j] - 0.02 <= c[j] <= hi[j] + 0.02 for j in range(3) if j != i):
                return True
    return False


def part_radius(name):
    axes = PARTS[name].get("osy")
    if axes and max(axes) > 0:
        return float(max(axes))
    profile = PARTS[name].get("profil")
    if profile:
        return max(p[0] for p in profile)
    return float(PARTS[name].get("polomer", 0.0))


def linings():
    """(material, surface of the cut, targets) of the cuts with their own `povrch`: rebuilt here, a boolean does not carry it over."""
    out = []
    for part in SPEC["dily"]:
        if part.get("povrch") and part["typ"] != "vyrez":
            cutter = lod_parts.cutter_of(part["nazev"], part)
            verts = [v.co.copy() for v in cutter.data.vertices]
            tree = BVHTree.FromPolygons(verts, [tuple(p.vertices) for p in cutter.data.polygons], epsilon=0.0)
            out.append((part["povrch"], tree, [part["cil"]] if part["typ"] == "arkady" else part["cile"]))
            bpy.data.objects.remove(cutter)
    return out


def paint(name, o, boxes, lined):
    """Real materials by part; faces on the section plane show what the wall is made of inside."""
    part = PARTS[name]
    if part["typ"] == "model":      # postava v měřítku má vlastní materiály z GLB
        return
    radius = part_radius(name) if part["typ"] in SOLID and part["typ"] not in ORGANIC + ("kvadr",) else 0.0
    if part["typ"] not in SOLID:
        for i, slot in enumerate(o.data.materials):
            o.data.materials[i] = pm.surface(slot.name.split(".")[0], radius)
        return
    o.data.materials.clear()
    o.data.materials.append(pm.surface(part["material"], radius))
    # sawn timber looks the same inside, only masonry has a section of its own
    o.data.materials.append(pm.surface(part["material"], radius) if part["material"] == "drevo" else pm.section(part["material"], part.get("rez") or REQ.get("rez", "kamen")))
    mine = [(mat, tree) for mat, tree, targets in lined if name in targets]
    slots = {}
    for mat, _tree in mine:
        if mat not in slots:
            slots[mat] = len(o.data.materials)
            o.data.materials.append(pm.surface(mat, 0.0))
    for p in o.data.polygons:
        if on_cut(p, boxes):
            p.material_index = 1
            continue
        p.material_index = 0
        for mat, tree in mine:
            if tree.find_nearest(p.center)[3] < 0.02:
                p.material_index = slots[mat]
                break


def see_through(o, window, keep):
    """Kůže průhledná v elipse `okno` (střed [x, z] a poloosy v metrech, pohled z boku), k okraji naplno: ostrý okraj řezu,
    ne šmouha (operátor 5. 11.). Mimo okno zůstává `zbyva` krytí, aby se tělo neztratilo. Každý díl dostane vlastní kopii materiálu."""
    (cx, cz), (rx, rz) = window["stred"], window["poloosy"]
    for i, slot in enumerate(o.data.materials):
        mat = slot.copy()
        o.data.materials[i] = mat
        nt = mat.node_tree
        bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(nt.nodes.new("ShaderNodeTexCoord").outputs["Object"], sep.inputs[0])

        def op(kind, a, b):
            n = nt.nodes.new("ShaderNodeMath")
            n.operation = kind
            for k, v in enumerate((a, b)):
                if isinstance(v, (int, float)):
                    n.inputs[k].default_value = v
                else:
                    nt.links.new(v, n.inputs[k])
            return n.outputs[0]
        dx = op("DIVIDE", op("SUBTRACT", sep.outputs["X"], cx), rx)
        dz = op("DIVIDE", op("SUBTRACT", sep.outputs["Z"], cz), rz)
        d = op("SQRT", op("ADD", op("MULTIPLY", dx, dx), op("MULTIPLY", dz, dz)), 0)
        fade = op("MINIMUM", op("MAXIMUM", op("DIVIDE", op("SUBTRACT", d, 0.92), 0.08), 0.0), 1.0)
        nt.links.new(op("ADD", keep, op("MULTIPLY", fade, 1 - keep)), bsdf.inputs["Alpha"])


def clay_material():
    m = bpy.data.materials.new("hlina")
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.42, 0.42, 0.42, 1)
    bsdf.inputs["Roughness"].default_value = 0.8
    return m


def look_at(cam, pos, target, up):
    f = (target - pos).normalized()
    r = f.cross(up).normalized()
    u = r.cross(f)
    cam.matrix_world = Matrix((r, u, -f)).transposed().to_4x4()
    cam.matrix_world.translation = pos


def frame_perspective(scene, cam, pts, direction, fill=0.9):
    """Perspektivní kamera ve směru `direction` od středu modelu: vzdálenost a posun tak, aby model vyplnil `fill` snímku
    (scripts/3d/vorvan_scena.py). Mírná perspektiva: bližší konec je větší, jako hlava vorvaně k divákovi."""
    lo, hi = pts.min(0), pts.max(0)
    target = Vector(((lo + hi) / 2).tolist())
    up = Vector((0, 0, 1)) if abs(direction.z) < 0.99 else Vector((0, 1, 0))
    sample = [Vector(p) for p in pts[:: max(1, len(pts) // 4000)]]
    dist = 2.5 * float(np.linalg.norm(hi - lo))
    for _ in range(6):
        look_at(cam, target + direction * dist, target, up)
        cam.data.shift_x = cam.data.shift_y = 0
        bpy.context.view_layer.update()
        q = [world_to_camera_view(scene, cam, p) for p in sample]
        span = max(max(p.x for p in q) - min(p.x for p in q), max(p.y for p in q) - min(p.y for p in q))
        dist *= span / fill
    look_at(cam, target + direction * dist, target, up)
    bpy.context.view_layer.update()
    q = [world_to_camera_view(scene, cam, p) for p in sample]
    aspect = RES[0] / RES[1]
    big = max(aspect, 1.0)
    cam.data.shift_x = ((min(p.x for p in q) + max(p.x for p in q)) / 2 - 0.5) * (aspect / big)
    cam.data.shift_y = ((min(p.y for p in q) + max(p.y for p in q)) / 2 - 0.5) / big
    bpy.context.view_layer.update()
    return target, dist


def smooth(o, deg=28):
    bpy.ops.object.select_all(action="DESELECT")
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.shade_smooth_by_angle(angle=math.radians(deg))
    o.select_set(False)


def corners(objs):
    for o in objs:
        for b in o.bound_box:
            yield o.matrix_world @ Vector(b)


def world_points(objs):
    out = []
    for o in objs:
        co = np.empty(len(o.data.vertices) * 3)
        o.data.vertices.foreach_get("co", co)
        m = np.array(o.matrix_world)
        out.append(co.reshape(-1, 3) @ m[:3, :3].T + m[:3, 3])
    return np.vstack(out)


def frame(pts, camera_dir, res):
    """Orthographic camera that fits everything with a small margin: scale and centre. It measures the vertices, not the boxes:
    the corners of a box around an ellipse stick far out of the ellipse in a view from an angle."""
    up = Vector((0, 0, 1))
    if abs(camera_dir.dot(up)) > 0.99:
        up = Vector((0, 1, 0))
    right = camera_dir.cross(up).normalized()
    top = right.cross(camera_dir).normalized()
    us, vs = pts @ np.array(right), pts @ np.array(top)
    span_u, span_v = float(us.max() - us.min()) * MARGIN, float(vs.max() - vs.min()) * MARGIN
    w, h = res
    scale = max(span_u, span_v * w / h) if w >= h else max(span_v, span_u * h / w)
    centre = right * float((us.max() + us.min()) / 2) + top * float((vs.max() + vs.min()) / 2)
    return scale, centre


def lights(camera_az):
    a = math.radians(camera_az + 40)
    sun_dir = Vector((math.cos(a) * 0.55, math.sin(a) * 0.55, 0.85)).normalized()
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    bpy.context.scene.collection.objects.link(sun)
    sun.data.energy, sun.data.angle = 5.5, math.radians(1.2)
    sun.data.color = (1.0, 0.93, 0.82)
    sun.rotation_mode = "QUATERNION"
    sun.rotation_quaternion = sun_dir.to_track_quat("Z", "Y")
    fill = bpy.data.objects.new("fill", bpy.data.lights.new("fill", "SUN"))
    bpy.context.scene.collection.objects.link(fill)
    fill.data.energy, fill.data.angle = 0.55, math.radians(35)
    fill.data.color = (0.92, 0.96, 1.0)
    b, e = math.radians(camera_az - 25), math.radians(30)
    fill.rotation_mode = "QUATERNION"
    fill.rotation_quaternion = Vector((math.cos(b) * math.cos(e), math.sin(b) * math.cos(e), math.sin(e))).to_track_quat("Z", "Y")
    world = bpy.data.worlds.new("w")
    bpy.context.scene.world = world
    if not world.node_tree:
        world.use_nodes = True
    wt = world.node_tree
    bg = wt.nodes["Background"]
    co = wt.nodes.new("ShaderNodeTexCoord")
    sep = wt.nodes.new("ShaderNodeSeparateXYZ")
    wt.links.new(co.outputs["Generated"], sep.inputs[0])
    sky = wt.nodes.new("ShaderNodeValToRGB")
    sky.color_ramp.elements[0].position, sky.color_ramp.elements[0].color = 0.0, (0.95, 0.78, 0.6, 1)
    sky.color_ramp.elements[1].position, sky.color_ramp.elements[1].color = 0.55, (0.34, 0.5, 0.86, 1)
    wt.links.new(sep.outputs["Z"], sky.inputs[0])
    wt.links.new(sky.outputs[0], bg.inputs[0])
    bg.inputs[1].default_value = 0.8


def setup_cycles():
    scene = bpy.context.scene
    r = scene.render
    r.engine = "CYCLES"
    r.resolution_x, r.resolution_y = RES
    r.film_transparent = True
    r.image_settings.file_format = "PNG"
    r.image_settings.color_mode = "RGBA"
    c = scene.cycles
    c.samples, c.use_denoising = SAMPLES, True
    c.denoiser = "OPENIMAGEDENOISE"
    c.max_bounces = 8
    c.diffuse_bounces = 5
    if not REQ.get("cpu") and os.environ.get("GRAFIK_RENDER_CPU") != "1":
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "OPTIX"
        prefs.get_devices()
        gpus = [d for d in prefs.devices if d.type == "OPTIX"]
        for d in prefs.devices:
            d.use = d in gpus
        c.device = "GPU" if gpus else "CPU"
    scene.view_settings.view_transform = "AgX"
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    return c.device


def groups(objects):
    """Layers: what the request asks for; each part while there are few of them, otherwise by material."""
    wanted = REQ.get("skupiny")
    if wanted:
        out = {k: [objects[n] for n in v if n in objects] for k, v in wanted.items()}   # a section may remove a whole part
        return {k: v for k, v in out.items() if v}
    if len(objects) <= 12:
        return {n: [o] for n, o in objects.items()}
    out = {}
    for name, o in objects.items():
        out.setdefault("ozdoby" if PARTS[name]["typ"] in DECOR else PARTS[name].get("material", "kamen"), []).append(o)
    return out


def main():
    boxes = near_boxes(section_x())

    def kept(x, y, z=None):
        """Loose pieces in the removed space go with it; without a height, a whole column counts as standing above the plinth."""
        return not any(lo[0] <= x <= hi[0] and lo[1] <= y <= hi[1] and (z is None or lo[2] <= z <= hi[2]) for lo, hi in boxes)

    objects = lod_parts.build(SPEC, kept=kept)

    def remove(cutter, names):
        for name in [n for n in names if n in objects]:
            lod_parts.boolean(objects[name], cutter)
            if not objects[name].data.polygons:
                bpy.data.objects.remove(objects.pop(name))
        bpy.data.objects.remove(cutter)

    for lo, hi in boxes:
        g = lod_parts.Geo()
        g.box(lo, hi)
        remove(lod_parts.mesh_object("near_cut", g.v, g.f), [n for n in objects if PARTS[n]["typ"] in SOLID])
    for item in REQ.get("odkryv") or []:    # a sector of a part taken away in this picture only: the arena floor over the underground
        remove(lod_parts.wedge_cutter("odkryv", item["azimut"], (-5000, 5000)), item["dily"])
    for name in REQ.get("bez") or []:   # e.g. the arena floor, so the rooms under it can be seen
        if name in objects:
            bpy.data.objects.remove(objects.pop(name))
    for name, dz in (REQ.get("posuny") or {}).items():
        if name in objects:
            objects[name].location.z += dz
    bpy.context.view_layer.update()
    lined = linings()
    for name, o in objects.items():
        paint(name, o, boxes, lined)
        if PARTS[name]["typ"] != "model":
            smooth(o, 28 if PARTS[name]["typ"] in SOLID else 40)
    if REQ.get("hlina"):    # předloha tvaru pro FLUX: matná světlá hlína, ze které čte tvar a světlo, kůži dodá sám (vorvaň 5. 11.)
        clay = clay_material()
        for o in objects.values():
            o.data.materials.clear()
            o.data.materials.append(clay)
    clear = None if REQ.get("hlina") else REQ.get("pruhledne")
    if clear:
        for name in clear["dily"]:
            if name in objects:
                see_through(objects[name], clear["okno"], clear.get("zbyva", 0.14))

    scene = bpy.context.scene
    scene.render.resolution_x, scene.render.resolution_y = RES
    az, el = math.radians(VIEW["az"]), math.radians(VIEW["el"])
    d = Vector((math.cos(az) * math.cos(el), math.sin(az) * math.cos(el), math.sin(el)))
    objs = list(objects.values())
    box = REQ.get("zaber")      # a part of the model fills the picture, the rest runs off its edges
    pts = np.array([(x, y, z) for x in (box[0][0], box[1][0]) for y in (box[0][1], box[1][1]) for z in (box[0][2], box[1][2])], dtype=float) if box else world_points(objs)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    perspective = bool(REQ.get("perspektiva"))
    if perspective:
        cam.data.lens = 50
        _target, dist = frame_perspective(scene, cam, pts, d)
        reach = dist
        scale = 2 * dist * math.tan(cam.data.angle / 2)      # šířka záběru ve vzdálenosti středu modelu, pro m_px
        cam.data.clip_end = 10 * dist
    else:
        scale, centre = frame(pts, -d, RES)
        cam.data.type = "ORTHO"
        reach = 10 * max(scale, *SPEC["dim"].values())
        cam.data.ortho_scale = scale
        cam.data.clip_end = 4 * reach
        cam.rotation_mode = "QUATERNION"
        cam.location = centre + d * reach
        cam.rotation_quaternion = (-d).to_track_quat("-Z", "Y")
    lights(VIEW["az"])
    device = setup_cycles()
    scene.cycles.transparent_max_bounces = 24      # průsvitná kůže a vnitřnosti za ní
    bpy.context.view_layer.update()
    OUT.mkdir(parents=True, exist_ok=True)

    def uv(p):
        q = world_to_camera_view(scene, cam, Vector(p))
        return [round(q.x * RES[0], 1), round((1 - q.y) * RES[1], 1)]

    dg = bpy.context.evaluated_depsgraph_get()
    near = 0.05 * max(SPEC["dim"].values())

    def in_sight(world, part=None):
        """Nothing stands in front of this point on the camera's ray; with a part named, the ray lands on that part here."""
        start = cam.matrix_world.translation.copy() if perspective else world + d * reach
        ray = (world - start).normalized()
        hit, loc, _n, _i, what, _m = scene.ray_cast(dg, start, ray)
        if part is not None:
            return hit and what.name == part and (loc - world).length < near
        return not hit or (loc - start).length > (world - start).length - near

    def visible_point(o):
        """A surface point of the part that the camera sees, closest to the middle of its visible points."""
        verts = o.data.vertices
        seen = [w for k in range(0, len(verts), max(1, len(verts) // 240)) if in_sight(w := o.matrix_world @ verts[k].co, o.name)]
        if not seen:
            return None
        mid = sum(seen, Vector()) / len(seen)
        return min(seen, key=lambda p: (p - mid).length)

    points, visible, boxes = {}, [], {}
    for name, o in objects.items():
        spot = visible_point(o)
        if spot is not None:
            visible.append(name)
        lo, hi = lod_parts.bbox_of(o)
        points[name] = uv(spot if spot is not None else [(a + b) / 2 for a, b in zip(lo, hi)])
        rect = [uv(c) for c in corners([o])]
        boxes[name] = [round(min(p[0] for p in rect), 1), round(min(p[1] for p in rect), 1), round(max(p[0] for p in rect), 1), round(max(p[1] for p in rect), 1)]
    for anchor in SPEC.get("kotvy") or []:
        world = Vector(anchor["xyz"])
        world.z += (REQ.get("posuny") or {}).get(anchor.get("dil"), 0.0)
        points[anchor["nazev"]] = uv(world)
        if in_sight(world):
            visible.append(anchor["nazev"])
    origin = uv((0, 0, 0))
    basis = {axis: [round(b - a, 4) for a, b in zip(origin, uv(q))] for axis, q in (("x", (1, 0, 0)), ("y", (0, 1, 0)), ("z", (0, 0, 1)))}
    info = {"pohled": REQ["pohled"], "res": RES, "points": points, "viditelne": visible, "ramecky": boxes, "origin": origin, "basis": basis,
            "m_px": round(max(RES) / scale, 4), "dim": SPEC["dim"], "posuny": REQ.get("posuny") or {}, "zarizeni": device}
    r = scene.render
    r.filepath = str(OUT / "obraz.png")
    bpy.ops.render.render(write_still=True)
    if REQ.get("vrstvy"):
        layers = groups(objects)
        alone = bool(REQ.get("samostatne"))     # vrstva sama bez ostatních (kůže zvlášť od vnitřností), jinak ostatní vyříznou svůj obrys
        for name, group in layers.items():
            for o in objs:
                if alone:
                    o.hide_render = o not in group
                else:
                    o.is_holdout = o not in group
            r.filepath = str(OUT / f"vrstva-{name}.png")
            bpy.ops.render.render(write_still=True)
        info["vrstvy"] = {name: [o.name for o in group] for name, group in layers.items()}
    (OUT / "body.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    print("STATS", json.dumps({"parts": len(objects), "device": device}))


main()
