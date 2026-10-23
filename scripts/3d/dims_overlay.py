import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# Dimension check: python scripts/3d/dims_overlay.py <folder with l3-plan/-profil/-tri.png>
S = Path(sys.argv[1])
PX, CX, CZ = 1280 / 56.0, 2.0, 4.0
F = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 22)
Y = (255, 214, 102)


def px(x, v):  # model (x, y|z) -> pixel, centre (640, 360)
    return 640 + (x - CX) * PX, 360 - v * PX


def dim(d, a, b, text, off=(0, -14)):
    d.line([a, b], fill=Y, width=3)
    for p in (a, b):
        d.ellipse([p[0] - 4, p[1] - 4, p[0] + 4, p[1] + 4], fill=Y)
    d.text(((a[0] + b[0]) / 2 + off[0], (a[1] + b[1]) / 2 + off[1]), text, fill=Y, font=F, anchor="mm")


plan = Image.open(S / "l3-plan.png").convert("RGB")
d = ImageDraw.Draw(plan)
dim(d, px(-22.5, -5.2), px(22.5, -5.2), "45 m", (0, 20))
dim(d, px(0, -3.5), px(0, 3.5), "7 m s nástavci", (110, 0))
dim(d, px(-8, -2.9), px(-8, 2.9), "5,8 m paluba", (-95, 0))

prof = Image.open(S / "l3-profil.png").convert("RGB")
d = ImageDraw.Draw(prof)
z0 = 360 - (0 - CZ) * PX
dim(d, px(-22.5, -2.2 + CZ - CZ), px(22.5, -2.2 + CZ - CZ), "45 m", (0, 20))
man_x = 22.5 + 4.0
dim(d, (px(man_x, 0)[0] + 30, z0 - 0.1 * PX), (px(man_x, 0)[0] + 30, z0 - (0.1 + 1.72) * PX), "1,72 m", (55, 0))
dim(d, (px(-8, 0)[0], z0), (px(-8, 0)[0], z0 - 3.0 * PX), "3 m", (-35, 0))

tri = Image.open(S / "l3-tri.png").convert("RGB")
sheet = Image.new("RGB", (1280, 1080), (20, 26, 34))
sheet.paste(tri.resize((960, 540)), (160, 0))
sheet.paste(plan.resize((640, 360)), (0, 560))
sheet.paste(prof.resize((640, 360)), (640, 560))
sheet.save(S / "l3-kontrola.png")
plan.save(S / "l3-plan-dims.png")
prof.save(S / "l3-profil-dims.png")
print("ok")
