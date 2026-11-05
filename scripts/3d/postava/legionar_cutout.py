# Výřez 4 pohledů z podkladu operátora: klíč šedého pozadí + rembg v pásu podlahy; tenké pilum zachovat.
import sys, io, json, base64, urllib.request
import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage
src = Image.open(sys.argv[1]).convert("RGB")
W, H = src.size; cx, cy, m = 367, 659, 4
boxes = {"front": (0, 0, cx-m, cy-m), "back": (cx+m, 0, W, cy-m), "left": (0, cy+m, cx-m, H), "right": (cx+m, cy+m, W, H)}
outs = []
for v, b in boxes.items():
    im = src.crop(b); a = np.asarray(im).astype(float); h, w = a.shape[:2]
    buf = io.BytesIO(); im.save(buf, "PNG")
    r = urllib.request.Request("http://127.0.0.1:8300/api/v2/models3d/cutout", data=json.dumps({"b64": base64.b64encode(buf.getvalue()).decode()}).encode(), headers={"Content-Type": "application/json"})
    rb = np.asarray(Image.open(io.BytesIO(base64.b64decode(json.load(urllib.request.urlopen(r))["b64"]))).convert("RGBA"))[..., 3] > 128
    mx = a.max(2); mn = a.min(2); sat = (mx - mn) / np.maximum(mx, 1)
    # pozadí po řádcích jen z nesytých pixelů okraje (okraj tvoří místy štít)
    border = np.concatenate([a[:, :6], a[:, -6:]], axis=1); bsat = np.concatenate([sat[:, :6], sat[:, -6:]], axis=1)
    bg = np.zeros((h, 3)); prev = np.median(border[0], axis=0)
    for y in range(h):
        ok = border[y][bsat[y] < 0.15]
        prev = np.median(ok, axis=0) if len(ok) else prev
        bg[y] = prev
    d = np.sqrt(((a - bg[:, None, :]) ** 2).sum(2))
    lab, n = ndimage.label(d < 22)
    sizes = ndimage.sum(np.ones_like(lab), lab, range(1, n + 1))
    edge = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
    bgl = [i + 1 for i, s in enumerate(sizes) if s > 1500] + list(edge)
    key = ~np.isin(lab, bgl)
    fl = int(h * 0.78)
    # tenké svislé struktury (pilum) nad podlahou protáhnout dolů
    row = key[fl - 5]; thin = np.zeros(w, bool)
    l2, n3 = ndimage.label(row)
    for i in range(1, n3 + 1):
        xs = np.where(l2 == i)[0]
        if len(xs) <= 12: thin[max(0, xs.min() - 2):xs.max() + 3] = True
    fg = key.copy()
    fg[fl:] = (key[fl:] & (sat[fl:] > 0.28)) | rb[fl:] | (key[fl:] & thin[None, :] & (d[fl:] > 30))
    fg = ndimage.binary_opening(fg, iterations=1)
    l3, n4 = ndimage.label(fg); s3 = ndimage.sum(fg, l3, range(1, n4 + 1))
    fg = np.isin(l3, [i + 1 for i, s in enumerate(s3) if s > 150])
    alpha = Image.fromarray((fg * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.7))
    rgba = im.convert("RGBA"); rgba.putalpha(alpha); rgba.save(f"ref-{v}.png"); outs.append(rgba)
sh = Image.new("RGBA", (sum(i.width for i in outs), max(i.height for i in outs)), (60, 140, 90, 255)); x = 0
for i in outs: sh.alpha_composite(i, (x, 0)); x += i.width
sh.convert("RGB").save("vyrezy.jpg", quality=90)
