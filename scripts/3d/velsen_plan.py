# The land of the Velsen 1 plan (book, phase 3 with wells) as polygons in plan pixels: fort ground, surrounding land, earthen wall. For velsen_pevnost.py.
#   python scripts/3d/velsen_plan.py LIB
import json
import sys
from pathlib import Path

import cv2
import numpy as np


def classes(bgr: np.ndarray, scale: int) -> np.ndarray:
    """0 water, 1 fort ground, 2 surrounding land, 3 earthen wall, 255 unknown (lines, text, dots), which then take the nearest class."""
    b, g, r = [bgr[..., i].astype(np.int16) for i in range(3)]
    out = np.full(b.shape, 255, np.uint8)
    out[b - r > 30] = 0
    out[(np.abs(r - g) < 9) & (np.abs(g - b) < 9) & (r > 80) & (r < 150)] = 0     # the dark strips of ditch remains; the thin aqueduct line closes up below
    out[(r >= 218) & (g >= 205) & (b >= 160) & (b <= 205)] = 1                       # white, outside the plan's frame, stays unknown
    out[(r - g > 25) & (b < 110)] = 1                           # the rampart stands on the fort ground
    out[(np.abs(r - g) <= 8) & (r - b >= 45)] = 2
    out[(r - g >= 12) & (r - g <= 24) & (r - b >= 55) & (r < 215)] = 3
    out[: 95 * scale, : 490 * scale] = 255      # the legend
    out[560 * scale:, : 200 * scale] = 2        # the label, the scale and the north arrow stand on the surrounding land
    known = (out != 255).astype(np.uint8)
    _, labels = cv2.distanceTransformWithLabels(1 - known, cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
    ys, xs = np.where(known)
    lookup = np.zeros(labels.max() + 1, np.uint8)
    lookup[labels[ys, xs]] = out[ys, xs]
    return lookup[labels]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    lib = Path(sys.argv[1])
    src = cv2.imread(str(lib / "podklady/plan.png"))
    k = 3
    big = cv2.resize(src, None, fx=k, fy=k, interpolation=cv2.INTER_NEAREST)
    cls = classes(big, k)
    shapes = {}
    for name, value in (("fort", 1), ("land", 2), ("wall", 3)):
        mask = (cls == value).astype(np.uint8) * 255
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((15, 15) if name == "fort" else (9, 9), np.uint8))     # heals the banks between the ditches, narrower than a ditch
        mask = cv2.threshold(cv2.GaussianBlur(mask, (0, 0), 3.0), 127, 255, cv2.THRESH_BINARY)[1]    # no pixel steps on the banks
        contours, tree = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
        polys = []
        for i, c in enumerate(contours):
            if tree[0][i][3] != -1 or cv2.contourArea(c) < (20000 if name == "wall" else 600):
                continue
            if name == "fort" and c[:, 0, 1].mean() / k > 545:     # the label box of the plan, not ground
                continue
            loops = [cv2.approxPolyDP(c, 1.5, True)[:, 0] / k]
            j = tree[0][i][2]
            while j != -1:
                if cv2.contourArea(contours[j]) > 300:
                    loops.append(cv2.approxPolyDP(contours[j], 1.5, True)[:, 0] / k)
                j = tree[0][j][0]
            polys.append([loop.round(2).tolist() for loop in loops])
        shapes[name] = polys
        print(name, len(polys), "polygonů", sum(len(p[0]) for p in polys), "bodů")
    out = lib / "pevnost"
    out.mkdir(parents=True, exist_ok=True)
    (out / "plan.json").write_text(json.dumps(shapes), encoding="utf-8")
    cv2.imwrite(str(out / "kontrola.png"), cv2.resize(cls * 80, None, fx=1 / k, fy=1 / k, interpolation=cv2.INTER_NEAREST))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
