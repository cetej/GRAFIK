# Naše postava přesně zepředu a zprava (presne-*.png z postava_s_vystroji.py: ortho 2,0 m na 900 px, střed z 0,86) vedle předlohy
# ve stejném měřítku a obrys naší postavy (červeně) přes předlohu. Čáry po 10 cm.
#   python srovnej_predloha.py <výstup běhu> <srovnani.jpg> [<složka předlohy s ref-front.png a ref-right.png> [<výška s přilbou v m>]]
# Vršek přilby a chodidlo na předloze v px je v REF (pro jinou předlohu změřit).
import os
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
D, OUT = sys.argv[1], sys.argv[2]
P = (sys.argv[3] if len(sys.argv) > 3 else "C:/Users/stock/Documents/000_NGM/GRAFIK/library/3d/rimsky-legionar-v-a-poze-zaklad-pro-kostru/v1/podklad").rstrip("/") + "/"
REF = {"zepredu": ("ref-front.png", 22, 1120), "zprava": ("ref-right.png", 22, 1120)}     # vršek přilby a chodidlo v px
f = ImageFont.truetype("arial.ttf", 16); rows = []
def mask(im, tol=18):
    a = np.asarray(im).astype(int); bg = np.median(np.concatenate([a[:8, :8].reshape(-1, 3), a[:8, -8:].reshape(-1, 3)]), 0)
    return Image.fromarray(((np.abs(a - bg).sum(2) > tol) * 255).astype(np.uint8))
for vn, (rf, top, sole) in REF.items():
    if vn == "zprava" and not os.path.exists(f"{D}/presne-zprava.png"):     # starší běh: snímek z levého boku, zrcadlit
        ours = Image.open(f"{D}/presne-zboku.png").convert("RGB").transpose(Image.FLIP_LEFT_RIGHT)
    else:
        ours = Image.open(f"{D}/presne-{vn}.png").convert("RGB")
    W, H = ours.size; mpp = 2.0 / max(W, H); zpx = lambda z: int(H / 2 - (z - 0.86) / mpp)
    htop = float(sys.argv[4]) if len(sys.argv) > 4 else 1.696
    ref = Image.open(P + rf).convert("RGB"); k = (zpx(0) - zpx(htop)) / (sole - top); ref = ref.resize((int(ref.width * k), int(ref.height * k)))
    oy = zpx(htop) - int(top * k); ox = (W - ref.width) // 2
    R = Image.new("RGB", (W, H), (235, 235, 235)); R.paste(ref, (ox, oy))
    m = mask(ours); edge = Image.fromarray((np.asarray(m) > 0) & ~(np.asarray(m.filter(ImageFilter.MinFilter(5))) > 0))
    ov = R.copy(); ov.paste((230, 0, 0), (0, 0), edge.convert("L"))
    S = Image.new("RGB", (W * 3, H), (235, 235, 235)); S.paste(ours, (0, 0)); S.paste(R, (W, 0)); S.paste(ov, (2 * W, 0)); d = ImageDraw.Draw(S)
    for i in range(18):
        y = zpx(i / 10); d.line([(0, y), (S.width, y)], fill=(0, 140, 255) if i % 5 else (255, 0, 0), width=1); d.text((4, y - 18), f"{i / 10:.1f} m", fill=(0, 0, 0), font=f)
    for x, t in ((10, f"naše postava ({vn})"), (W + 10, "předloha, stejná výška"), (2 * W + 10, "obrys naší postavy přes předlohu")): d.text((x, 8), t, fill=(0, 0, 0), font=f)
    rows.append(S)
out = Image.new("RGB", (rows[0].width, sum(r.height for r in rows)), "white"); y = 0
for r in rows: out.paste(r, (0, y)); y += r.height
out.save(OUT, quality=90)
