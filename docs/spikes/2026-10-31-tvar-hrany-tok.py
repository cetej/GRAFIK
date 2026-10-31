# Can edge maps + optical flow tell a clay/FLUX pair with a known bad shape from the good ones? (GRAFIK#86, free, CPU)
#   python docs/spikes/2026-10-31-tvar-hrany-tok.py library/3d [out_dir]
# Pairs and their labels come from docs/spikes/2026-10-27-3d-trellis-vs-blender.md, fixed before this measurement.
import json
import sys
from pathlib import Path

import cv2
import numpy as np

SIZE = 512       # longer side the images are measured at; numbers are in pixels of this size
PAIRS = {  # name: (model, azimuth, FLUX job, label)
    "tatra-trellis-030": ("tatra87-trellis2", "030", "073602-623d52", "spatny"),      # obecný sedan
    "tatra-blender-120": ("tatra87-blender", "120", "073709-eece4f", "dobry"),
    "rotunda-trellis-300": ("rotunda-martin-trellis2", "300", "073815-cdb2b5", "dobry"),
    "rotunda-blender-300": ("rotunda-martin-blender", "300", "073922-908d8c", "dobry"),
    "mamut-trellis-300": ("mamut-trellis2", "300", "074032-2333ed", "dobry"),
    "mamut-blender-300": ("mamut-blender", "300", "074139-25dd9b", "dobry"),
    "tatra-hunyuan-030": ("tatra87-hunyuan3d", "030", "080633-ab14d0", "dobry"),
    "tatra-hunyuan-300": ("tatra87-hunyuan3d", "300", "080747-cbfe58", "dobry"),
    "tatra-natazena-030": ("tatra87-hunyuan3d-natazeny", "030", "081148-530b77", "spatny"),  # záď: limuzína
    "tatra-natazena-300": ("tatra87-hunyuan3d-natazeny", "300", "081256-68d988", "dobry"),
    "doryforos-210": ("doryforos-hunyuan3d", "210", "081929-7ca0e4", "dobry"),
    "slon-210": ("slon-hunyuan3d", "210", "082033-cc75b1", "spatny"),                 # zadní noha
    "vez-300": ("mostecka-vez-hunyuan3d", "300", "082138-903562", "dobry"),
}
OTHER_VIEW = {"030": "210", "120": "300", "210": "030", "300": "120"}
OTHER_MODEL = {"rotunda-trellis-300": "rotunda-blender-300", "mamut-trellis-300": "mamut-blender-300",
               "tatra-hunyuan-030": "tatra-natazena-030", "tatra-hunyuan-300": "tatra-natazena-300"}
OTHER_MODEL |= {v: k for k, v in OTHER_MODEL.items()}
FLOW = {"M": cv2.DISOPTICAL_FLOW_PRESET_MEDIUM, "F": cv2.DISOPTICAL_FLOW_PRESET_FAST}


def load(path):
    img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    k = SIZE / max(img.shape[:2])
    img = cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
    if img.shape[2] == 4:
        alpha = img[:, :, 3:].astype(np.float32) / 255
        flat = (img[:, :, :3] * alpha + 128 * (1 - alpha)).astype(np.uint8)
        return cv2.cvtColor(flat, cv2.COLOR_BGR2GRAY), (alpha[:, :, 0] > 0.5).astype(np.uint8)
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), None


def edges(grey):
    g = cv2.GaussianBlur(grey.astype(np.float32), (0, 0), 2.0)
    mag = np.log1p(np.hypot(cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1)))
    return (255 * mag / max(float(mag.max()), 1e-6)).astype(np.uint8)


def strong(edge):
    return cv2.threshold(edge, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1] > 0


def align(e_clay, sil, e_res, scales):
    """Scale and shift of the clay's edges that best match the result: masked template matching over `scales`."""
    ys, xs = np.where(sil > 0)
    y0, y1, x0, x1 = max(ys.min() - 6, 0), ys.max() + 7, max(xs.min() - 6, 0), xs.max() + 7
    tmpl, mask = e_clay[y0:y1, x0:x1], cv2.dilate(sil[y0:y1, x0:x1], np.ones((9, 9), np.uint8))
    best = (-2.0, 1.0, 0.0, 0.0)
    for s in scales:
        t = cv2.resize(tmpl, None, fx=s, fy=s, interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR)
        if t.shape[0] > e_res.shape[0] or t.shape[1] > e_res.shape[1]:
            continue
        m = cv2.resize(mask, (t.shape[1], t.shape[0]), interpolation=cv2.INTER_NEAREST)
        res = cv2.matchTemplate(e_res, t, cv2.TM_CCOEFF_NORMED, mask=m)
        res[~np.isfinite(res)] = -2
        _, v, _, loc = cv2.minMaxLoc(res)
        if v > best[0]:
            best = (float(v), float(s), loc[0] - x0 * float(s), loc[1] - y0 * float(s))
    return best


def flow_on_edges(e_clay, e_res, where, preset):
    f = cv2.DISOpticalFlow_create(preset).calc(e_clay, e_res, None)
    shift = np.hypot(f[:, :, 0], f[:, :, 1])
    return shift, float(np.median(shift[where])), float(np.percentile(shift[where], 90))


def score(clay_path, res_path):
    clay, sil = load(clay_path)
    res, _ = load(res_path)
    e_c, e_r = edges(clay), edges(res)
    out = {}
    shift, out["tok_med"], out["tok_p90"] = flow_on_edges(e_c, e_r, strong(e_c), FLOW["M"])
    v, s, dx, dy = align(e_c, sil, e_r, np.arange(0.9, 1.1001, 0.02))
    out.update(ncc=round(v, 3), meritko=round(s, 2), dx=round(dx, 1), dy=round(dy, 1))
    m = np.float32([[s, 0, dx], [0, s, dy]])
    e_a = cv2.warpAffine(e_c, m, e_c.shape[::-1])
    band = cv2.dilate(cv2.warpAffine(sil, m, e_c.shape[::-1], flags=cv2.INTER_NEAREST), np.ones((9, 9), np.uint8)) > 0
    _, out["srov_med"], out["srov_p90"] = flow_on_edges(e_a, e_r, strong(e_a) & band, FLOW["M"])
    _, out["srov_fast_med"], _ = flow_on_edges(e_a, e_r, strong(e_a) & band, FLOW["F"])
    return {k: round(float(v), 3) for k, v in out.items()}, shift, e_c, e_r


def auc(bad, good, lower_is_better=True):
    """Chance a bad pair scores worse than a good one (1 = perfect, 0.5 = coin)."""
    sign = 1 if lower_is_better else -1
    return float(np.mean([(sign * b > sign * g) + 0.5 * (b == g) for b in bad for g in good]))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    lib = Path(sys.argv[1])
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    rows = {}
    for name, (model, az, job, label) in PAIRS.items():
        res = lib / model / f"20261027-{job}-0.png"
        ok, shift, e_c, e_r = score(lib / model / f"clay-az{az}.png", res)
        view = score(lib / model / f"clay-az{OTHER_VIEW[az]}.png", res)[0]
        other = None
        if name in OTHER_MODEL:
            o = PAIRS[OTHER_MODEL[name]]
            other = score(lib / o[0] / f"clay-az{o[1]}.png", res)[0]
        rows[name] = {"label": label, "ok": ok, "pohled": view, "model": other}
        if out_dir:
            heat = cv2.applyColorMap(np.clip(shift * 6, 0, 255).astype(np.uint8), cv2.COLORMAP_INFERNO)
            cv2.imwrite(str(out_dir / f"{name}.jpg"), np.hstack([cv2.cvtColor(e_c, cv2.COLOR_GRAY2BGR),
                                                                 cv2.cvtColor(e_r, cv2.COLOR_GRAY2BGR), heat]))
        print(f"{name:22} {label:6} {ok}")
    print()
    print("metrika        špatné       dobré        AUC   lepší než jiný pohled / jiný model")
    for key, lower in (("tok_med", True), ("tok_p90", True), ("ncc", False), ("srov_med", True),
                       ("srov_p90", True), ("srov_fast_med", True)):
        bad = [r["ok"][key] for r in rows.values() if r["label"] == "spatny"]
        good = [r["ok"][key] for r in rows.values() if r["label"] == "dobry"]
        sign = 1 if lower else -1
        view = sum(sign * r["ok"][key] < sign * r["pohled"][key] for r in rows.values())
        with_model = [r for r in rows.values() if r["model"]]
        other = sum(sign * r["ok"][key] < sign * r["model"][key] for r in with_model)
        print(f"{key:14} {min(bad):5.1f}-{max(bad):5.1f}  {min(good):5.1f}-{max(good):5.1f}  {auc(bad, good, lower):.2f}"
              f"  {view}/{len(rows)} / {other}/{len(with_model)}")
    if out_dir:
        (out_dir / "mereni.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
