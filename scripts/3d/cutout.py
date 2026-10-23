# Light unsaturated studio background -> alpha, by flood fill from the image border (free).
# python scripts/3d/cutout.py ref.png cutout.png
import sys
from collections import deque
import numpy as np
from PIL import Image
src, dst = sys.argv[1], sys.argv[2]
a = np.asarray(Image.open(src).convert("RGB")).astype(int)
h, w, _ = a.shape
mx, mn = a.max(2), a.min(2)
bgish = (mn > 150) & (mx - mn < 14)  # light, unsaturated gray studio background and its soft shadow
mask = np.zeros((h, w), bool)
q = deque((y, x) for y in range(h) for x in (0, w - 1)) + deque((y, x) for x in range(w) for y in (0, h - 1))
while q:
    y, x = q.popleft()
    if 0 <= y < h and 0 <= x < w and not mask[y, x] and bgish[y, x]:
        mask[y, x] = True
        q.extend(((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)))
rgba = np.dstack([a.astype(np.uint8), np.where(mask, 0, 255).astype(np.uint8)])
Image.fromarray(rgba, "RGBA").save(dst)
print("background share", round(mask.mean(), 3))
