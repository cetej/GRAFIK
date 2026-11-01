# Materials for the coloured render of a parts model (engine/blender/render_parts.py), taken over from
# scripts/3d/lod_pantheon.py: what makes a procedural surface read as a real thing is dirt in the corners, slightly rounded
# edges and joints. Names are those of engine/parts_spec.MATERIALS; a wall course follows the curve when `radius` is given.
import bpy


def srgb(hexs):
    c = [int(hexs[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return tuple((x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4) for x in c) + (1.0,)


def new_mat(name, rough=0.7, metal=0.0):
    m = bpy.data.materials.new(name)
    if not m.node_tree:
        m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    return m, m.node_tree, bsdf


def coords(tree):
    return tree.nodes.new("ShaderNodeTexCoord").outputs["Object"]


def aged(t, bsdf, color, ao=0.8, dist=1.4, bevel=0.0):
    occ = t.nodes.new("ShaderNodeAmbientOcclusion")
    occ.samples = 6
    occ.inputs["Distance"].default_value = dist
    mix = t.nodes.new("ShaderNodeMix")
    mix.data_type, mix.blend_type = "RGBA", "MULTIPLY"
    mix.inputs["Factor"].default_value = ao
    t.links.new(color, mix.inputs["A"])
    t.links.new(occ.outputs["AO"], mix.inputs["B"])
    t.links.new(mix.outputs["Result"], bsdf.inputs["Base Color"])
    if bevel:
        bev = t.nodes.new("ShaderNodeBevel")
        bev.samples = 4
        bev.inputs["Radius"].default_value = bevel
        t.links.new(bev.outputs[0], bsdf.inputs["Normal"])


def ramp_of(t, fac, a, b, lo=0.35, hi=0.65):
    r = t.nodes.new("ShaderNodeValToRGB")
    r.color_ramp.elements[0].position, r.color_ramp.elements[1].position = lo, hi
    r.color_ramp.elements[0].color, r.color_ramp.elements[1].color = srgb(a), srgb(b)
    t.links.new(fac, r.inputs[0])
    return r.outputs[0]


def noise_of(t, co, scale, detail=6.0):
    n = t.nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value, n.inputs["Detail"].default_value = scale, detail
    t.links.new(co, n.inputs["Vector"])
    return n.outputs[0]


def noisy(name, a, b, scale=1.2, rough=0.7, metal=0.0, detail=6.0, lo=0.35, hi=0.65, ao=0.8, bevel=0.0):
    m, t, bsdf = new_mat(name, rough, metal)
    aged(t, bsdf, ramp_of(t, noise_of(t, coords(t), scale, detail), a, b, lo, hi), ao, bevel=bevel)
    return m


def veined(name, base_a, base_b, vein, scale=0.5, rough=0.35, amount=0.55, bevel=0.03):
    m, t, bsdf = new_mat(name, rough)
    co = coords(t)
    cloud = ramp_of(t, noise_of(t, co, 0.9, 5.0), base_a, base_b)
    wave = t.nodes.new("ShaderNodeTexWave")
    wave.wave_type, wave.bands_direction = "BANDS", "DIAGONAL"
    wave.inputs["Scale"].default_value, wave.inputs["Distortion"].default_value = scale, 11.0
    wave.inputs["Detail"].default_value, wave.inputs["Detail Scale"].default_value = 5.0, 1.4
    t.links.new(co, wave.inputs["Vector"])
    line = t.nodes.new("ShaderNodeValToRGB")
    line.color_ramp.elements[0].position, line.color_ramp.elements[1].position = 0.0, 0.16
    line.color_ramp.elements[0].color, line.color_ramp.elements[1].color = (1, 1, 1, 1), (0, 0, 0, 1)
    t.links.new(wave.outputs["Fac"], line.inputs[0])
    gain = t.nodes.new("ShaderNodeMath")
    gain.operation = "MULTIPLY"
    gain.inputs[1].default_value = amount
    t.links.new(line.outputs[0], gain.inputs[0])
    mix = t.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    t.links.new(gain.outputs[0], mix.inputs["Factor"])
    t.links.new(cloud, mix.inputs["A"])
    mix.inputs["B"].default_value = srgb(vein)
    aged(t, bsdf, mix.outputs["Result"], 0.75, bevel=bevel)
    return m


def wall_uv(t, radius):
    """(along the wall, height): around the drum for a curved wall, x + y for the flat ones."""
    geo = t.nodes.new("ShaderNodeTexCoord").outputs["Object"]
    sep = t.nodes.new("ShaderNodeSeparateXYZ")
    t.links.new(geo, sep.inputs[0])
    along = t.nodes.new("ShaderNodeMath")
    if radius:
        along.operation = "ARCTAN2"
        t.links.new(sep.outputs["Y"], along.inputs[0])
        t.links.new(sep.outputs["X"], along.inputs[1])
        out = t.nodes.new("ShaderNodeMath")
        out.operation = "MULTIPLY"
        out.inputs[1].default_value = radius
        t.links.new(along.outputs[0], out.inputs[0])
        along = out
    else:
        along.operation = "ADD"
        t.links.new(sep.outputs["X"], along.inputs[0])
        t.links.new(sep.outputs["Y"], along.inputs[1])
    comb = t.nodes.new("ShaderNodeCombineXYZ")
    t.links.new(along.outputs[0], comb.inputs["X"])
    t.links.new(sep.outputs["Z"], comb.inputs["Y"])
    return comb.outputs[0]


def masonry(name, a, b, joint, width, height, radius=0.0, rough=0.8, seam=0.02):
    m, t, bsdf = new_mat(name, rough)
    br = t.nodes.new("ShaderNodeTexBrick")
    br.inputs["Color1"].default_value, br.inputs["Color2"].default_value = srgb(a), srgb(b)
    br.inputs["Mortar"].default_value = srgb(joint)
    br.inputs["Scale"].default_value = 1.0
    br.inputs["Mortar Size"].default_value = seam
    br.inputs["Mortar Smooth"].default_value = 0.2
    br.inputs["Brick Width"].default_value, br.inputs["Row Height"].default_value = width, height
    t.links.new(wall_uv(t, radius), br.inputs["Vector"])
    co = coords(t)
    stain = t.nodes.new("ShaderNodeMix")
    stain.data_type, stain.blend_type = "RGBA", "MULTIPLY"
    stain.inputs["Factor"].default_value = 1.0
    t.links.new(br.outputs["Color"], stain.inputs["A"])
    t.links.new(ramp_of(t, noise_of(t, co, 0.7, 7.0), "#a79c8c", "#ffffff", 0.3, 0.7), stain.inputs["B"])
    bump = t.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value, bump.inputs["Distance"].default_value = 0.6, 0.03
    t.links.new(br.outputs["Fac"], bump.inputs["Height"])
    bump.invert = True
    aged(t, bsdf, stain.outputs["Result"], 0.85)
    t.links.new(bump.outputs[0], bsdf.inputs["Normal"])
    return m


def roof(name, a, b, every=0.62):
    m, t, bsdf = new_mat(name, 0.55, 0.25)
    co = coords(t)
    sep = t.nodes.new("ShaderNodeSeparateXYZ")
    t.links.new(co, sep.inputs[0])
    comb = t.nodes.new("ShaderNodeCombineXYZ")
    t.links.new(sep.outputs["Y"], comb.inputs["X"])
    wave = t.nodes.new("ShaderNodeTexWave")
    wave.wave_type, wave.bands_direction = "BANDS", "X"
    wave.inputs["Scale"].default_value, wave.inputs["Distortion"].default_value = 1 / every, 0.0
    t.links.new(comb.outputs[0], wave.inputs["Vector"])
    bump = t.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value, bump.inputs["Distance"].default_value = 1.0, 0.16
    t.links.new(wave.outputs["Fac"], bump.inputs["Height"])
    aged(t, bsdf, ramp_of(t, noise_of(t, co, 0.5, 6.0), a, b), 0.8)
    t.links.new(bump.outputs[0], bsdf.inputs["Normal"])
    return m


def aggregate(name, mortar_a, mortar_b, rocks, scale, rough=0.95):
    """Section through masonry core: broken angular stones in cement, some cells empty, grit between them."""
    m, t, bsdf = new_mat(name, rough)
    co = coords(t)
    warp = t.nodes.new("ShaderNodeTexNoise")
    warp.inputs["Scale"].default_value, warp.inputs["Detail"].default_value = 3.0, 4.0
    t.links.new(co, warp.inputs["Vector"])
    sc = t.nodes.new("ShaderNodeVectorMath")
    sc.operation = "SCALE"
    sc.inputs[3].default_value = 0.1
    t.links.new(warp.outputs["Color"], sc.inputs[0])
    add = t.nodes.new("ShaderNodeVectorMath")
    add.operation = "ADD"
    t.links.new(co, add.inputs[0])
    t.links.new(sc.outputs[0], add.inputs[1])
    col = ramp_of(t, noise_of(t, co, 26.0, 8.0), mortar_a, mortar_b, 0.3, 0.7)
    height = None
    for sc_k, gap, empty in ((scale * 3.1, 0.2, 0.45), (scale, 0.085, 0.16)):   # grit first, big stones over it
        cell = t.nodes.new("ShaderNodeTexVoronoi")
        cell.inputs["Scale"].default_value = sc_k
        t.links.new(add.outputs[0], cell.inputs["Vector"])
        edge = t.nodes.new("ShaderNodeTexVoronoi")
        edge.feature = "DISTANCE_TO_EDGE"
        edge.inputs["Scale"].default_value = sc_k
        t.links.new(add.outputs[0], edge.inputs["Vector"])
        sep = t.nodes.new("ShaderNodeSeparateColor")
        t.links.new(cell.outputs["Color"], sep.inputs[0])
        solid = t.nodes.new("ShaderNodeMapRange")
        solid.inputs["From Min"].default_value, solid.inputs["From Max"].default_value = gap, gap + 0.02
        t.links.new(edge.outputs["Distance"], solid.inputs["Value"])
        keep = t.nodes.new("ShaderNodeMath")
        keep.operation = "GREATER_THAN"
        keep.inputs[1].default_value = empty
        t.links.new(sep.outputs[1], keep.inputs[0])
        mask = t.nodes.new("ShaderNodeMath")
        mask.operation = "MULTIPLY"
        t.links.new(solid.outputs[0], mask.inputs[0])
        t.links.new(keep.outputs[0], mask.inputs[1])
        tint = t.nodes.new("ShaderNodeValToRGB")
        cr = tint.color_ramp
        cr.interpolation = "CONSTANT"
        while len(cr.elements) < len(rocks):
            cr.elements.new(0.5)
        for k, c in enumerate(rocks):
            cr.elements[k].position, cr.elements[k].color = k / len(rocks), srgb(c)
        t.links.new(sep.outputs[0], tint.inputs[0])
        speck = t.nodes.new("ShaderNodeMix")
        speck.data_type, speck.blend_type = "RGBA", "MULTIPLY"
        speck.inputs["Factor"].default_value = 1.0
        t.links.new(tint.outputs[0], speck.inputs["A"])
        t.links.new(ramp_of(t, noise_of(t, co, 16.0, 7.0), "#a39a8e", "#ffffff", 0.3, 0.72), speck.inputs["B"])
        mix = t.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        t.links.new(mask.outputs[0], mix.inputs["Factor"])
        t.links.new(col, mix.inputs["A"])
        t.links.new(speck.outputs["Result"], mix.inputs["B"])
        col = mix.outputs["Result"]
        height = mask.outputs[0]
    bump = t.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value, bump.inputs["Distance"].default_value = 0.8, 0.03
    t.links.new(height, bump.inputs["Height"])
    t.links.new(bump.outputs[0], bsdf.inputs["Normal"])
    t.links.new(col, bsdf.inputs["Base Color"])
    # the section is what the picture explains: it stays readable while the room around it goes dim
    t.links.new(col, bsdf.inputs["Emission Color"])
    bsdf.inputs["Emission Strength"].default_value = 0.2
    return m


_cache = {}
FLAT = {"provaz": "#5c4c35", "kuze": "#b98a66", "lide_1": "#8c2f26", "lide_2": "#e6dfcf", "lide_3": "#34507a", "lide_4": "#b9893a", "lide_5": "#5b6b45", "lide_6": "#d9c7a0"}


def surface(name, radius=0.0):
    """Material of a part; masonry is made per radius, so the courses run along the wall at the right scale."""
    key = (name, round(radius) if name in ("travertin", "tuf", "cihla") else 0)
    if key in _cache:
        return _cache[key]
    label = f"{name}_{key[1]}"
    if name in FLAT:
        m, _t, bsdf = new_mat(label, 0.85)
        bsdf.inputs["Base Color"].default_value = srgb(FLAT[name])
    elif name == "travertin":
        m = masonry(label, "#b9ae98", "#c7bda8", "#857b6b", 2.4, 0.62, radius)
    elif name == "tuf":
        m = masonry(label, "#9d927b", "#ada28b", "#6f6755", 1.8, 0.55, radius)
    elif name == "cihla":
        m = masonry(label, "#84492f", "#9c5f42", "#b7aa95", 0.52, 0.17, radius, seam=0.012)
    elif name == "beton":
        m = noisy(label, "#a69d8c", "#bcb3a2", 0.4, 0.85, ao=1.0)
    elif name == "mramor":
        m = veined(label, "#cfc9bc", "#dfdbd1", "#9a958b", 1.3, 0.5, 0.16)
    elif name == "zula":
        m = noisy(label, "#5a5d60", "#8d8f8e", 22.0, 0.32, lo=0.42, hi=0.58, bevel=0.02)
    elif name == "bronz":
        m = noisy(label, "#5f4a2b", "#8f7040", 6.0, 0.35, 0.9)
    elif name == "strecha":
        m = roof(label, "#73787b", "#7d8285")
    elif name == "drevo":
        m = noisy(label, "#7f5f36", "#a68455", 3.0, 0.75)
    elif name == "omitka":
        m = noisy(label, "#8c3325", "#a2412f", 1.4, 0.9, ao=0.6)
    elif name == "pisek":
        m = noisy(label, "#bfa77a", "#d2bd93", 2.0, 0.95)
    elif name == "platno":
        m = noisy(label, "#d8cdb4", "#e0d6bf", 0.5, 0.95, ao=0.3)
    elif name == "platno_2":
        m = noisy(label, "#c6b896", "#cfc2a2", 0.5, 0.95, ao=0.3)
    elif name == "zemina":
        m = noisy(label, "#5a4834", "#6e5a43", 2.5, 0.95)
    elif name == "freska":
        m = noisy(label, "#c0903a", "#d3a851", 1.5, 0.8, ao=0.5)
    else:
        m = noisy(label, "#b3aa98", "#c4bcab", 0.9, 0.75)
    _cache[key] = m
    return m


def section(name, style="kamen"):
    """Cut face of a part: what the wall is made of inside, or black like an architect's section, where the structure reads at a glance."""
    key = ("rez", style if style in ("cerna", "tmava") else name)
    if key not in _cache and style == "cerna":
        m, t, bsdf = new_mat("rez_cerna", 0.95)
        bsdf.inputs["Base Color"].default_value = srgb("#16130f")
        _cache[key] = m
    if key not in _cache and style == "tmava":
        _cache[key] = aggregate("rez_tmava", "#26221c", "#2e2922", ("#3b342a", "#231f19", "#443c30", "#2c2720"), 1.6)
    if key not in _cache:
        if name == "zemina":
            _cache[key] = aggregate("rez_zemina", "#54432f", "#63513b", ("#46382a", "#6f5c46", "#3b2f23", "#7d6a52"), 1.6)
        elif name == "cihla":
            _cache[key] = aggregate("rez_cihla", "#a89c8c", "#b8ac9c", ("#9c4f37", "#ae6045", "#88442e", "#b86f52"), 2.3)
        elif name == "beton":
            _cache[key] = aggregate("rez_beton", "#a2988a", "#b1a798", ("#cfc5ae", "#85735f", "#9d5238", "#b5a88f", "#786656"), 2.3)
        else:
            _cache[key] = aggregate(f"rez_{name}", "#b4ac9d", "#c2baab", ("#d6d0c3", "#857d6f", "#c6bfb0", "#9d9485", "#e4dfd2"), 2.6)
    return _cache[key]
