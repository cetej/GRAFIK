# Vkládá se do postava_s_vystroji.py (exec) po stavbě rukávů: vyříznuté díly zbroje nahradí samostatné díly z generátoru.
# Nový díl se srovná na obálku vyříznutého (percentily 1-99, ať cáry neroztáhnou rámeček), rovnoměrně s odchylkou os do 10 %.
DIL = VYSTROJ                            # <díl>/model.glb ze scripts/3d/postava/vystroj_dily.py
OTOC = globals().get("OTOC", {})          # díl -> úhel kolem Z ve stupních, když generátor díl otočil
def nacti(d):
    before = set(bpy.data.objects); bpy.ops.import_scene.gltf(filepath=os.path.join(DIL, d, "model.glb"))
    new = [o for o in bpy.data.objects if o not in before]; ms = [o for o in new if o.type == "MESH"]
    for o in ms:
        o.data.transform(o.matrix_world); o.parent = None; o.matrix_world = Matrix.Identity(4)
    sel(ms); bpy.ops.object.join() if len(ms) > 1 else None; o = bpy.context.view_layer.objects.active
    for x in new:
        if x != o and x.name in bpy.data.objects: bpy.data.objects.remove(x, do_unlink=True)
    o.name = f"{d}_novy"
    if d in OTOC: o.data.transform(Matrix.Rotation(math.radians(OTOC[d]), 4, "Z"))
    bm_ = bmesh.new(); bm_.from_mesh(o.data); bmesh.ops.remove_doubles(bm_, verts=bm_.verts, dist=1e-5); bm_.to_mesh(o.data); bm_.free()
    return o
def obalka(C):
    return np.percentile(C, 1, 0), np.percentile(C, 99, 0)
def usad(o, Cold):
    lo0, hi0 = obalka(Cold); C = co(o); lo1, hi1 = C.min(0), C.max(0)
    r = (hi0 - lo0) / (hi1 - lo1); s = float(np.median(r)); r = np.clip(r, 0.9 * s, 1.1 * s)
    o.data.transform(Matrix.Translation(Vector((lo0 + hi0) / 2)) @ Matrix.Diagonal((*r, 1)) @ Matrix.Translation(-Vector((lo1 + hi1) / 2))); o.data.update()
    print("INFO usazeno", o.name, "meritko os", r.round(3), "rozmer cm", ((hi0 - lo0) * 100).round(1), flush=True)
NOVE = {}
o = nacti("prilba"); usad(o, co(parts["helma"]))
# přilba podle hlavy, ne podle místa staré přilby: zvětšovat kolem středu lebky, dokud žádný bod hlavy nad lemem není venku
_GI = {g.index: g.name for g in body.vertex_groups}                   # bez skryté pomocné geometrie MPFB (HelperGeometry, JointCubes)
_C = co(o); _HV = np.array([body.matrix_world @ v.co for v in body.data.vertices if not any(_GI[g.group] in ("HelperGeometry", "JointCubes") for g in v.groups)])
_front = _C[(np.abs(_C[:, 0]) < 0.04) & (_C[:, 1] < np.median(_C[:, 1]))]; zrim = float(_front[:, 2].min())
_hd = _HV[(_HV[:, 2] > mp("head").z) & (np.abs(_HV[:, 0]) < 0.13)]; _zt = float(_hd[:, 2].max())
_H = _hd[_hd[:, 2] > _zt - 0.07]                  # jen temeno: obličej a uši jsou pod otvory přilby a paprsek by jimi prošel
_hc = Vector((float(np.median(_H[:, 0])), float(np.median(_H[:, 1])), _zt - 0.10))
_bvhP = BVHTree.FromPolygons([tuple(x) for x in _C.tolist()], [p_.vertices[:] for p_ in o.data.polygons])
def _venku(m):                                    # body hlavy převedené do souřadnic přilby (strom se staví jednou)
    mi = m.inverted(); c = mi @ _hc; n = 0
    for x in _H:                                  # paprsek od středu lebky přes bod hlavy ven: bez zásahu do přilby = hlava není zakrytá
        x = mi @ Vector(x); d_ = (x - c).normalized()
        if _bvhP.ray_cast(x + d_ * 0.003, d_, 0.25)[0] is None: n += 1
    return n
# --- usazení podle hlavy: výřez pro ucho nad uchem, čelní lem kousek nad obočím, temeno zakryté ---
_yc = float((_C[:, 1].min() + _C[:, 1].max()) / 2); _zs = np.arange(_C[:, 2].max(), _C[:, 2].min() - 1e-6, -0.003)
def _spodek(org_xy, d):                            # nejnižší výška, kde paprsek z vnitřku přilby ve směru d ještě narazí na plech
    lo = None
    for z in _zs:
        if _bvhP.ray_cast(Vector((org_xy[0], org_xy[1], float(z))), d, 0.3)[0] is not None: lo = float(z)
    return lo
_brz = _spodek((0.0, _yc), Vector((0, -1, 0))); _bry = _bvhP.ray_cast(Vector((0, _yc, _brz)), Vector((0, -1, 0)), 0.3)[0].y
_ys = np.arange(_C[:, 1].min() + 0.01, _C[:, 1].max() - 0.01, 0.003); _ucho = {}
for sg in (1, -1):
    prof = np.array([_spodek((0.0, float(y)), Vector((sg, 0, 0))) or 9.0 for y in _ys])
    mid = (_ys > np.percentile(_ys, 25)) & (_ys < np.percentile(_ys, 80)) & (prof < 9)
    j = np.argmax(np.where(mid, prof, -9)); _ucho[sg] = np.array([sg * 0.07, _ys[j], prof[j]])
# hlava: uši podle materiálu MPFB, obočí podle objektu obočí
_mi = next(i for i, m in enumerate(body.data.materials) if m and "ears" in m.name)
_ev = np.unique(np.concatenate([np.array(f.vertices[:]) for f in body.data.polygons if f.material_index == _mi]))
_EV = np.array([body.matrix_world @ body.data.vertices[i].co for i in _ev]); _ear = {sg: _EV[_EV[:, 0] * sg > 0] for sg in (1, -1)}
_bo = [x for x in bpy.data.objects if x.type == "MESH" and "eyebrow" in x.name.lower()]
_BV = np.array([x.matrix_world @ v.co for x in _bo for v in x.data.vertices]) if _bo else _HV[(_HV[:, 1] < _hc.y - 0.06)]
_browz = float(np.median(_BV[:, 2])); _fy = float(_HV[(np.abs(_HV[:, 2] - _browz - 0.015) < 0.006) & (np.abs(_HV[:, 0]) < 0.03)][:, 1].min())
_LM = np.array([[0.0, _bry, _brz], _ucho[1], _ucho[-1], [1, 1, 1]], dtype=float)[:3]
_tgt = {"lem_z": _browz + 0.012, "lem_y": _fy - 0.008, "ucho": {sg: (float(_ear[sg][:, 1].mean()), float(_ear[sg][:, 2].max()) + 0.004) for sg in (1, -1)}}
print("INFO prilba orientacni body: lem", round(_brz, 3), "usi", {sg: _ucho[sg].round(3).tolist() for sg in (1, -1)}, "| hlava: obočí z", round(_browz, 3),
      "celo y", round(_fy, 3), "uši (y, vrch z)", {sg: np.round(_tgt["ucho"][sg], 3).tolist() for sg in (1, -1)}, "objekt obočí", [x.name for x in _bo], flush=True)
def _M(k, a, dy, dz):
    return Matrix.Translation(Vector((0, dy, dz))) @ Matrix.Translation(_hc) @ Matrix.Rotation(math.radians(a), 4, "X") @ Matrix.Scale(k, 4) @ Matrix.Translation(-_hc)
cand = []
for k_ in np.arange(1.0, 1.101, 0.02):
    for a_ in range(-12, 13, 2):
        R_ = np.array(_M(float(k_), a_, 0, 0))[:3]; P_ = _LM @ R_[:, :3].T + R_[:, 3]
        for dy in np.arange(-0.06, 0.041, 0.005):
            for dz in np.arange(-0.04, 0.031, 0.005):
                Q = P_ + np.array([0, dy, dz])
                c_ = ((Q[0, 2] - _tgt["lem_z"]) ** 2 + 0.5 * (Q[0, 1] - _tgt["lem_y"]) ** 2
                      + sum((Q[i, 1] - _tgt["ucho"][sg][0]) ** 2 + (Q[i, 2] - _tgt["ucho"][sg][1]) ** 2 for i, sg in ((1, 1), (2, -1))) / 2)
                cand.append((c_, float(k_), a_, float(dy), float(dz)))
cand.sort()
for c_, k_, a_, dy, dz in cand[:60]:               # nejlépe sedící, které zároveň zakryje temeno
    M_ = _M(k_, a_, dy, dz); nv = _venku(M_)
    if nv <= 1: break
o.data.transform(M_); rigid(o, "head"); NOVE["helma"] = o
print("INFO prilba usazena: odchylka cm", round(math.sqrt(c_) * 100, 2), "zvetseni", round(k_, 2), "naklon", a_, "posun y/z cm", round(dy * 100, 1), round(dz * 100, 1), "temene venku", nv, flush=True)
if os.environ.get("JEN_PRILBA"):                   # rychlá kontrola usazení: hlava zepředu a z obou boků, bez simulace a póz
    setup_render(sc); sc.cycles.samples = 16
    for x in [x for x in bpy.data.objects if x.type == "MESH" and x.name in ("helma", "zbroj", "ramena")]: x.hide_render = True
    for vn, d in (("predek", (0.15, -1, 0.05)), ("bok", (1, 0, 0.05)), ("bok2", (-1, 0, 0.05))): shot(sc, os.path.join(OUT, f"prilba-{vn}.png"), d, 0.42, (0, mp("head").y, 1.52))
    sys.exit(0)
print("INFO prilba temene venku", nv, "z", len(_H), flush=True)
o = nacti("opasek"); usad(o, co(parts["opasek"]))
# opasek do výšky z předlohy (BELT_C) a na obvod těla v té výšce: pás 1,2 cm od těla + tloušťka
_C = co(o); _bt = float(_C[:, 2].max()); _band = _C[_C[:, 2] > _bt - 0.05]; _bc = (_bt + float(_band[:, 2].min())) / 2
o.data.transform(Matrix.Translation(Vector((0, 0, BELT_C - _bc)))); _C = co(o); _band = _C[_C[:, 2] > _C[:, 2].max() - 0.05]
_T = co(bpy.data.objects["tunika_latka"]); _T = _T[np.abs(_T[:, 2] - BELT_C) < 0.015]     # opasek leží na tunice, ne pod ní
_S = np.concatenate([BV[(np.abs(BV[:, 2] - BELT_C) < 0.012) & (np.abs(BV[:, 0]) < 0.22)], _T])
_bx, _by = (_band[:, 0].max() - _band[:, 0].min()), (_band[:, 1].max() - _band[:, 1].min())
_sx = (_S[:, 0].max() - _S[:, 0].min() + 0.05) / _bx; _sy = (_S[:, 1].max() - _S[:, 1].min() + 0.05) / _by     # přes tunici (tloušťka látky a vyhlazení)
_c = Vector(((_S[:, 0].max() + _S[:, 0].min()) / 2, (_S[:, 1].max() + _S[:, 1].min()) / 2, BELT_C)); _c0 = Vector(((_band[:, 0].max() + _band[:, 0].min()) / 2, (_band[:, 1].max() + _band[:, 1].min()) / 2, BELT_C))
o.data.transform(Matrix.Translation(_c) @ Matrix.Diagonal((_sx, _sy, 1, 1)) @ Matrix.Translation(-_c0)); rigid(o, "root"); NOVE["opasek"] = o
_C = co(o); _bt = float(_C[:, 2].max()); _bb = _bt - 0.05; _bc2 = (_bt + _bb) / 2
for v in o.data.vertices:                                   # pás o 35 % vyšší (předloha), zástěra pod ním jen posunutá
    if v.co.z > _bb - 0.005: v.co.z = _bc2 + (v.co.z - _bc2) * 1.35
    else: v.co.z -= 0.05 * 0.35 / 2
o.data.update()
print("INFO opasek: stred pasu z", round(BELT_C, 3), "posun dolu cm", round((_bc - BELT_C) * 100, 1), "sirka x/y", round(_sx, 3), round(_sy, 3), flush=True)
o = nacti("lorica"); usad(o, np.concatenate([co(parts["zbroj"]), co(parts["ramena"])])); NOVE["zbroj"] = o
_C = co(o); _lt = float(_C[:, 2].max()); _lb = float(np.percentile(_C[np.abs(_C[:, 0]) < 0.12][:, 2], 2))   # spodní obruč (bez visících řemínků)
_ld = BELT_C + 0.02                                                              # spodní plát dosedne na horní okraj opasku (předloha)
o.data.transform(Matrix.Translation(Vector((0, 0, _lt))) @ Matrix.Diagonal((1, 1, (_lt - _ld) / (_lt - _lb), 1)) @ Matrix.Translation(Vector((0, 0, -_lt))))
_C = co(o); _zb = (_ld + 0.04, _ld + 0.16); _h = _C[(_C[:, 2] > _zb[0]) & (_C[:, 2] < _zb[1])]           # obruče na trupu
_tb = BV[(BV[:, 2] > _zb[0]) & (BV[:, 2] < _zb[1]) & (np.abs(BV[:, 0]) < 0.2)]
_kx = float(np.clip((_tb[:, 0].max() - _tb[:, 0].min() + 0.06) / (_h[:, 0].max() - _h[:, 0].min()), 0.9, 1.5))   # obruče obepnou trup: 3 cm na plech a látku
_ky = float(np.clip((_tb[:, 1].max() - _tb[:, 1].min() + 0.06) / (_h[:, 1].max() - _h[:, 1].min()), 0.9, 1.5))
_cc = Vector(((_tb[:, 0].max() + _tb[:, 0].min()) / 2, (_tb[:, 1].max() + _tb[:, 1].min()) / 2, 0)); _c0 = Vector(((_h[:, 0].max() + _h[:, 0].min()) / 2, (_h[:, 1].max() + _h[:, 1].min()) / 2, 0))
o.data.transform(Matrix.Translation(_cc) @ Matrix.Diagonal((_kx, _ky, 1, 1)) @ Matrix.Translation(-_c0))
print("INFO lorica: spodek z", round(_lb, 3), "na", round(_ld, 3), "sirka x/y", round(_kx, 3), round(_ky, 3), flush=True)
# lorica: trup na páteři, ramenní pláty na ramenou (stejné dělení jako dřív u vyříznutých plátů)
C = co(o); zsh = mp("upperarm01.L").z; o.vertex_groups.clear(); spine(o)
# Ramenní pláty jsou kloubové: u krku drží na klíční kosti, k vnějšímu okraji jdou čím dál víc s paží (nejvýš 90 %).
# Napevno na klíční kosti je zvednutá paže (nápřah B) vytlačila ven a odkryla podpaží; ostrá hranice trup/rameno
# pak plát roztrhla do cípu. Proto plynulý přechod v šířce i výšce (ws) a podíl paže (wa).
_ax = np.abs(C[:, 0]); ws = np.clip((_ax - 0.11) / 0.04, 0, 1) * np.clip((C[:, 2] - (zsh - 0.13)) / 0.07, 0, 1)
wa = np.clip((_ax - 0.12) / 0.08, 0, 1) * 0.9   # pásy loriky se zvedají s paží (operátor), dřív 60 % nestačilo
for i in np.nonzero(ws > 0)[0]:
    for ge in o.data.vertices[int(i)].groups: ge.weight *= float(1 - ws[i])
for q, m in (("L", C[:, 0] > 0), ("R", C[:, 0] < 0)):
    gs, ga = o.vertex_groups.new(name=f"shoulder01.{q}"), o.vertex_groups.new(name=f"upperarm01.{q}")
    for i in np.nonzero(m & (ws > 0))[0]:
        gs.add([int(i)], float(ws[i] * (1 - wa[i])), "REPLACE")
        if wa[i] > 0: ga.add([int(i)], float(ws[i] * wa[i]), "REPLACE")
# šátek (focale): vyříznutý kus měl roztřepené okraje a díry, místo něj čistý prstenec látky kolem krku
bpy.data.objects.remove(parts.pop("satek"), do_unlink=True)
n0, n1 = mp("neck01"), mp("head"); ax = (n1 - n0).normalized(); u = ax.cross(Vector((0, 1, 0))).normalized(); v_ = ax.cross(u).normalized()
ts_ = np.arange(-0.045, 0.045, 0.006); vs_ = []        # dolů až pod límec loriky, ať zátylek není vidět
for t in ts_:
    c = n0 + ax * float(t); bulge = 0.012 * np.clip((0.01 - t) / 0.025, 0, 1)      # dole se šátek vrství na límec zbroje
    for j in range(48):
        ang = 2 * math.pi * j / 48; d = (u * math.cos(ang) + v_ * math.sin(ang)).normalized()
        hb = abvh.ray_cast(c, d, 0.25); rb = min((hb[0] - c).length if hb[0] is not None else 0.06, 0.07)   # nejvýš tloušťka krku: paprsek dole jinak doletí na ramena
        vs_.append(tuple(c + d * (rb + 0.008 + bulge)))
fs_ = [(i * 48 + j, i * 48 + (j + 1) % 48, (i + 1) * 48 + (j + 1) % 48, (i + 1) * 48 + j) for i in range(len(ts_) - 1) for j in range(48)]
me_ = bpy.data.meshes.new("satek"); me_.from_pydata(vs_, [], fs_); me_.update(); sa = bpy.data.objects.new("satek", me_); sc.collection.objects.link(sa); me_.materials.append(mt)
for f in me_.polygons: f.use_smooth = True
transfer(sa); sa.parent = rig; am = sa.modifiers.new("kostra", "ARMATURE"); am.object = rig
so3 = sa.modifiers.new("tloustka", "SOLIDIFY"); so3.thickness = 0.004; so3.offset = 1; sb3 = sa.modifiers.new("hladka", "SUBSURF"); sb3.levels = 1; sb3.render_levels = 2
parts["satek"] = sa; print("INFO satek prstenec", len(ts_), "kruhu", flush=True)
for g in ("helma", "opasek", "zbroj", "ramena"):
    bpy.data.objects.remove(parts.pop(g), do_unlink=True)
for g, o in NOVE.items():
    parts[g] = o; o.parent = rig; am = o.modifiers.new("kostra", "ARMATURE"); am.object = rig
    for f in o.data.polygons: f.use_smooth = True
    for m in o.data.materials:                      # lesk z barvy textury: světlá místa kov (ocel i mosaz), tmavá kůže matná; sytost zdrsní
        nt = m.node_tree if m and m.node_tree else None
        b = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None) if nt else None
        tx = next((n for n in nt.nodes if n.type == "TEX_IMAGE"), None) if nt else None
        if not (b and tx) or b.inputs["Metallic"].is_linked: continue
        hs = nt.nodes.new("ShaderNodeSeparateColor"); hs.mode = "HSV"; nt.links.new(tx.outputs["Color"], hs.inputs[0])
        mm = nt.nodes.new("ShaderNodeMapRange"); mm.inputs["From Min"].default_value = 0.25; mm.inputs["From Max"].default_value = 0.42; mm.inputs["To Min"].default_value = 0.0; mm.inputs["To Max"].default_value = 0.85
        nt.links.new(hs.outputs[2], mm.inputs["Value"]); nt.links.new(mm.outputs["Result"], b.inputs["Metallic"])
        rr = nt.nodes.new("ShaderNodeMapRange"); rr.inputs["From Min"].default_value = 0.0; rr.inputs["From Max"].default_value = 0.6; rr.inputs["To Min"].default_value = 0.32; rr.inputs["To Max"].default_value = 0.62
        nt.links.new(hs.outputs[1], rr.inputs["Value"]); nt.links.new(rr.outputs["Result"], b.inputs["Roughness"])
o = nacti("sandal"); oL = o.copy(); oL.data = o.data.copy(); sc.collection.objects.link(oL); oL.name = "sandal_L_novy"   # kopie dřív, než se pravý zmenší
for g in ("sandal_L", "sandal_R"):
    if g in parts: bpy.data.objects.remove(parts.pop(g), do_unlink=True)
for sd, sg in (("R", -1), ("L", 1)):
    if sd == "R": x = o
    else:
        x = oL
        x.data.transform(Matrix.Diagonal((-1, 1, 1, 1))); x.data.flip_normals()          # levý = zrcadlo pravého
    F = BV[(BV[:, 2] < 0.10) & (BV[:, 0] * sg > 0.02) & (BV[:, 0] * sg < 0.3)]; C = co(x); sole = C[C[:, 2] < C[:, 2].min() + 0.025]
    k_ = max((F[:, 1].max() - F[:, 1].min() + 0.03) / (sole[:, 1].max() - sole[:, 1].min()), (F[:, 0].max() - F[:, 0].min() + 0.02) / (sole[:, 0].max() - sole[:, 0].min()))
    p0 = Vector(((sole[:, 0].max() + sole[:, 0].min()) / 2, sole[:, 1].max(), C[:, 2].min()))                 # pata dole uprostřed
    p1 = Vector(((F[:, 0].max() + F[:, 0].min()) / 2, F[:, 1].max() + 0.012, F[:, 2].min() - 0.012))
    x.data.transform(Matrix.Translation(p1) @ Matrix.Scale(k_, 4) @ Matrix.Translation(-p0)); x.data.update()
    transfer(x, keep=("foot", "lowerleg", "toe")); x.parent = rig; am = x.modifiers.new("kostra", "ARMATURE"); am.object = rig
    for f in x.data.polygons: f.use_smooth = True
    parts[f"sandal_{sd}"] = x
    print("INFO sandal", sd, "meritko", round(k_, 3), "vyska cm", round((co(x)[:, 2].max() - co(x)[:, 2].min()) * 100, 1), flush=True)
print("INFO nove dily", {g: len(o.data.vertices) for g, o in NOVE.items()}, flush=True)
