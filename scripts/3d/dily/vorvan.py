# Vorvaň jako popis z dílů pro Engine (POST /api/v2/models3d/parts), 0 USD:
#   python scripts/3d/dily/vorvan.py          -> scripts/3d/dily/vorvan.json
# Přepis ručního modelu scripts/3d/lod_vorvan.py (tvar z předloh, rozměry se zdroji) a vnitřností ze scripts/3d/vorvan_scena.py
# do obecných dílů: telo, prurezy (čelist), zuby, elipsoid (ploutve), deska (ocas), trubice (trávicí trubice), elipsoid (tmavá
# dutina), model (potápěč). Všechno vorvaňovské je tady v datech, Engine zná jen obecné díly (engine/parts_spec.py).
# Osy jako v Engine: x od hlavy (-8 m) k ocasu, y napříč, z nahoru od nejnižšího bodu břicha.
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROF = json.loads((HERE.parent / "vorvan_profily.json").read_text(encoding="utf-8"))
L = 16.0                  # samec, en.wikipedia Sperm whale; délka od špičky hlavy k zářezu ocasní ploutve
X0 = -L / 2
WIDTH, HEIGHT = 1.92, 2.7
JT, JH = 0.075, 0.25      # špička dolní čelisti a koutek tlamy (podíl délky), předloha 01 a 03
TEETH = 24
FLIPPER_X, FLIPPER_LEN = 0.31, 1.8
FLUKE_SPAN, FLUKE_PITCH = 3.8, 35
MOUTH = -15               # stupně, tlama pootevřená
SIRKA = [(0.0, 0.0), (0.01, 0.05), (0.03, 0.075), (0.06, 0.09), (0.1, 0.1), (0.2, 0.11), (0.3, 0.12), (0.4, 0.12),
         (0.5, 0.115), (0.6, 0.105), (0.7, 0.085), (0.8, 0.058), (0.88, 0.038), (0.94, 0.03), (0.985, 0.026), (1.0, 0.0)]
# vnitřnosti a body popisků v px 2D vrstvy vorvaně, ze které vznikla stránka (vorvan_scena.py)
LAYER_PX = (1308, 307)
CAVITY = (600, 200, 470, 108)
POINTS = {"tlama": (150, 258), "jicen": (349, 245), "predzaludek": (520, 190), "hlavni_zaludek": (640, 186), "strevo": (865, 186)}
# vzhled povrchu pro lokální FLUX (scripts/plakaty/vorvan_flux.py, operátor 5. 11.: ne guma, ne kovové torpédo, žádné rýhy plejtváka)
WHALE = ("Photorealistic adult male sperm whale with exactly the shape, pose, angle, size and outline of <ref_image_0>, "
         "the open narrow lower jaw with two rows of conical ivory teeth exactly where it is in the reference. Matte dark brownish grey skin, "
         "deeply wrinkled corrugated skin like a dried prune on the flanks behind the head, pale whitish scars and circular sucker scratches on "
         "the huge blunt head, white lips, small eye just above the mouth corner, small paddle pectoral fin, low dorsal hump with knuckles. "
         "Smooth throat and belly without any long grooves or pleats (not a rorqual), skin wrinkles short and irregular, not in regular bands; "
         "flukes visible as broad flat blades. Natural underwater daylight from above, wildlife photograph, sharp detail.")
ORGANS = ("Realistic anatomical 3D illustration of the digestive organs of a sperm whale with exactly the shapes, positions and sizes "
          "of <ref_image_0>: a fleshy muscular esophagus tube, a thick-walled muscular first stomach with deep ridges, a larger second stomach "
          "with folded glandular lining, two small round connecting chambers, a densely coiled long intestine. Wet tissue, fine blood vessels, "
          "pink, red and cream colours, soft studio light, medical illustration, no labels.")
TRACT = [(300, 274, 0.2), (328, 262, 0.16), (370, 228, 0.16), (412, 192, 0.17),     # jícen z hltanu za koutkem tlamy (operátor 5. 11.)
         (450, 184, 0.34), (490, 186, 0.6), (530, 192, 0.64), (570, 198, 0.44), (600, 196, 0.22),
         (625, 190, 0.48), (655, 186, 0.56), (688, 190, 0.38), (708, 195, 0.18),
         (726, 198, 0.29), (746, 200, 0.14), (766, 200, 0.27), (786, 198, 0.11), (806, 194, 0.09)]


def interp(table, x):
    for (x0, y0), (x1, y1) in zip(table, table[1:]):
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return table[-1][1]


def smooth(t):
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


XS = PROF["x"]
H = PROF["hrbet"]
H_S = [H[i] if XS[i] < 0.1 else sum(H[max(0, i - 6): i + 7]) / len(H[max(0, i - 6): i + 7]) for i in range(len(H))]   # hrb jen ve střední čáře


def raw(key, x):
    return interp(list(zip(XS, PROF[key] if key != "hrbet_s" else H_S)), x)


def jaw_depth(x):
    return 0.2 + 0.25 * (x - JT) / (JH - JT)


def belly(x):
    """Břicho v podílech délky; pod hlavou je v obrysu kresby i zavřená čelist, ta se odečte (čelist je vlastní díl)."""
    bot = raw("bricho", x)
    if JT - 0.02 < x < JH + 0.06:
        bot += jaw_depth(min(max(x, JT), JH)) * smooth((x - (JT - 0.02)) / 0.03) * (1 - smooth((x - (JH - 0.05)) / 0.07)) / L
    return bot


def body():
    grid = [i / 400 for i in range(401)]
    prof = {"x": grid, "hrbet": [round(raw("hrbet_s", x), 5) for x in grid], "bricho": [round(belly(x), 5) for x in grid],
            "sirka": [round(interp(SIRKA, x), 5) for x in grid],
            "hreben": [round(max(raw("hrbet", x) - raw("hrbet_s", x), 0.0), 5) if x > 0.45 else 0.0 for x in grid]}
    return {"typ": "telo", "nazev": "telo", "material": "kuze_tmava", "delka": L, "x0": X0, "profil": prof, "celo": 0.05, "konec": 0.985,
            "hranatost": [[0.15, 3.0], [0.5, 2.0]], "zuzeni_dole": [[0.15, 0.55], [0.5, 0.15]], "zplosteni": [[0.9, 1.0], [0.985, 0.45]]}


def side(x):
    return raw("hrbet_s", x) * L, belly(x) * L


def hinge():
    return {"stred": [round(JH * L + X0, 4), 0.0, round(raw("bricho", JH) * L + jaw_depth(JH) * 0.7, 4)], "osa": "y", "uhel": MOUTH}


def jaw():
    rows = []
    for i in range(16):
        x = JT + (JH + 0.05 - JT) * i / 15             # za kloubem pokračuje do hlavy, ne jen dosedá zespodu
        xx = min(x, JH)
        d, w = jaw_depth(xx), 0.12 + 0.2 * (xx - JT) / (JH - JT)
        if i == 0:
            d, w = d * 0.6, w * 0.6
        z0 = raw("bricho", xx) * L + max(x - JH, 0) * L * 0.6
        rows.append([round(x * L + X0, 4), round(w, 4), round(z0 + d / 2, 4), round(d / 2, 4), 2.5])
    return {"typ": "prurezy", "nazev": "celist", "material": "kuze_tmava", "rezy": rows, "hladit": False, "otoceni": hinge()}


def teeth():
    pts = []
    for t in range(TEETH):
        x = JT + 0.01 + (JH - JT - 0.04) * t / (TEETH - 1)
        w = 0.12 + 0.2 * (x - JT) / (JH - JT)
        pts.append([round(x * L + X0, 4), round(w * 0.7, 4), round(raw("bricho", x) * L + jaw_depth(x) - 0.015, 4)])
    return {"typ": "zuby", "nazev": "zuby", "material": "zub", "body": pts, "vyska": 0.13, "polomer": 0.045, "spicka": 0.012, "zrcadlo": ["y"], "otoceni": hinge()}


def flippers():
    top, bot = side(FLIPPER_X)
    hw = interp(SIRKA, FLIPPER_X) * L / 2
    return {"typ": "elipsoid", "nazev": "ploutve", "material": "kuze_tmava", "poloosy": [FLIPPER_LEN / 2, 0.06, 0.32],
            "stred": [round(FLIPPER_X * L + FLIPPER_LEN * 0.35 + X0, 4), round(hw * 0.72, 4), round(bot + (top - bot) * 0.3 - 0.2, 4)],
            "natoceni": [-25, 25, -12], "zrcadlo": ["y"]}


def flukes():
    half, x0 = FLUKE_SPAN / 2, 0.935 * L
    outline = [(x0, 0.0), (x0 + 0.25, 0.45), (x0 + 0.55, 1.1), (x0 + 0.85, 1.7), (L + 0.25, half),
               (L + 0.35, half - 0.12), (L + 0.2, 1.4), (L + 0.08, 0.7), (L, 0.12), (L - 0.12, 0.0)]
    top, bot = side(0.975)
    return {"typ": "deska", "nazev": "ocas", "material": "kuze_tmava", "obrys": [[round(x + X0, 4), y] for x, y in outline], "zrcadlit_y": True,
            "z": round((top + bot) / 2, 4), "tloustka": 0.16, "osa_x": round(x0 + X0, 4), "sklon": FLUKE_PITCH}


def scene_frame(parts):
    """Převod z px 2D vrstvy do metrů jako ve vorvan_scena.py: délka celého modelu (i s ocasem) = šířka vrstvy, výška vnitřností
    podle břicha modelu (KZ), aby dutina sahala do 92 % hloubky těla v jejím středu."""
    sections = [s for p in parts if p["typ"] == "telo" for s in p["rezy"]]
    hi_z = max(s[2] + s[3] + s[6] for s in sections)
    lo_x, hi_x = X0, L + 0.35 + X0
    m = (hi_x - lo_x) / LAYER_PX[0]
    cx = lo_x + CAVITY[0] * m
    near = min(sections, key=lambda s: abs(s[0] - cx))
    kz = 0.92 * (hi_z - (near[2] - near[3])) / ((CAVITY[1] + CAVITY[3]) * m)
    return lo_x, hi_z, m, kz


def to3d(px, py, frame, kz=None):
    lo_x, hi_z, m, k = frame
    return [round(lo_x + px * m, 4), 0.0, round(hi_z - py * m * (k if kz is None else kz), 4)]


def inside(frame):
    lo_x, hi_z, m, kz = frame
    keys = [to3d(px, py, frame)[:3] + [r] for px, py, r in TRACT]
    tract = {"typ": "trubice", "nazev": "traveni", "material": "strevo", "body": keys, "useky": [[4, "tkan"], [9, "sval"], [18, "sliznice"]],
             "stlaceni_y": 0.8, "stlaceni_od": 0.25,
             "klubko": {"stred": to3d(*POINTS["strevo"], frame), "rozmer": [0.95, 0.304, 0.4275], "smycek": 12, "polomer": 0.1, "bodu": 900}}
    cavity = {"typ": "elipsoid", "nazev": "dutina", "material": "dutina", "stred": [round(lo_x + CAVITY[0] * m, 4), 0.6, round(hi_z - CAVITY[1] * m * kz, 4)],
              "poloosy": [round(CAVITY[2] * m * 0.86, 4), 0.05, round(CAVITY[3] * m * 0.86 * kz, 4)]}
    window = {"stred": [round(lo_x + CAVITY[0] * m, 4), round(hi_z - CAVITY[1] * m * kz, 4)], "poloosy": [round(CAVITY[2] * m, 4), round(CAVITY[3] * m * kz, 4)]}
    return [tract, cavity], window


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    from engine.parts_spec import validate      # tělo se rozloží na průřezy, ze kterých scene_frame bere výšku

    shape = [body(), jaw(), teeth(), flippers(), flukes()]
    frame = scene_frame(validate({"dim": {"length": L, "width": WIDTH, "height": HEIGHT}, "dily": shape})["dily"])
    organs, window = inside(frame)
    jaw_tip = to3d(40, 262, frame, kz=1.0)
    diver = {"typ": "model", "nazev": "potapec", "material": "kuze", "model": "potapec-infografika-vorvan/v1", "delka": 2.3,
             "stred": [round(X0 - 2.3 / 2 - 0.15, 4), -0.2, jaw_tip[2]], "natoceni": [0, 0, 0]}     # hlavou k vorvani
    anchors = [{"nazev": k, "xyz": to3d(*v, frame, kz=1.0 if k == "tlama" else None)} for k, v in POINTS.items()]
    spec = {"nazev": "Vorvaň s vnitřnostmi a potápěčem", "dim": {"length": L + 0.35, "width": WIDTH, "height": HEIGHT},
            "dily": shape + organs + [diver], "kotvy": anchors,
            "zdroje": {"length": "samec 16 m, en.wikipedia Sperm whale", "width": "tabule od operátora, pohled shora", "height": "předloha 01 (NOAA)",
                       "vnitrnosti": "odhad podle délky 16 m, komory zjednodušené"},
            "render": {"pohled": "celek", "kamera": {"az": -121.8, "el": 5.8}, "perspektiva": True, "res": [2400, 1000], "samples": 48,
                       "pruhledne": {"dily": ["telo", "celist", "ploutve", "ocas"], "okno": window, "zbyva": 0.14},
                       "skupiny": {"kuze": ["telo", "celist", "zuby", "ploutve", "ocas"], "vnitrek": ["traveni", "dutina"], "potapec": ["potapec"]},
                       "samostatne": True},
            # textura FLUXem (engine/textura3d.py): render v hlíně se stejnou kamerou, bez tmavé dutiny, je předloha tvaru
            "predloha": {"pohled": "celek", "kamera": {"az": -121.8, "el": 5.8}, "perspektiva": True, "res": [2400, 1000], "samples": 32, "hlina": True,
                         "bez": ["dutina"], "skupiny": {"kuze": ["telo", "celist", "zuby", "ploutve", "ocas"], "vnitrek": ["traveni", "dutina"],
                                                        "potapec": ["potapec"]}, "samostatne": True},
            "textura": {"kuze": {"prompt": WHALE, "slozeni": "okno"}, "vnitrek": {"prompt": ORGANS, "slozeni": "pod"}}}
    out = HERE / "vorvan.json"
    out.write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
    print(out, "KZ", round(frame[3], 3), "okno", window)


if __name__ == "__main__":
    sys.path.insert(0, str(HERE.parents[2]))
    main()
