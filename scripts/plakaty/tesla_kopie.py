# Czech copy of the operator's sample poster of Nikola Tesla: its layout, measured on the sample (736 x 1308 px), machines from 3D models,
# and the details the sample has wrong corrected (one tower, DC as a flat line, the Tesla coil without an iron core, a hydro plant in section instead of one with chimneys).
#   python scripts/plakaty/tesla_kopie.py RENDERS ASSETS OUT_DIR [--knihovna http://127.0.0.1:8300]
# RENDERS: <shot>/body.json from tesla_render.py, rytiny/<shot>.png: the same frame after local FLUX with the render as `geometry`, all in one engraving style. ASSETS: pergamen.png, postava.png (RGBA), rentgen.png.
# Facts and sources: docs/spikes/2026-11-01-plakaty-osoba-zvire.md.
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sazba import cover, crop_alpha, fit, group, image_tag, text, wrap, write_poster  # noqa: E402

S = 2
W, H = 736 * S, 1308 * S
SERIF = "'Palatino Linotype', 'Book Antiqua', Georgia, serif"
INK, BODY, LINE = "#15110b", "#2a2319", "#2a2218"
COPPER, STEEL, PALE = "#c2521c", "#1c6ea4", "#f4f0e4"
NB = " "
NIGHT = "#14171c"
PANELS = {"motor": (28, 117, 332, 324), "vez": (377, 117, 330, 376), "proudy": (28, 465, 220, 227), "civka": (492, 507, 215, 468),
          "radio": (28, 708, 220, 267), "trubice": (28, 992, 220, 285), "turbina": (260, 1055, 218, 222), "voda": (492, 992, 215, 285)}


def u(v: float) -> float:
    return v * S


def label(x, y, s, size=8.2, anchor="start", weight=400, italic=False, fill=BODY) -> str:
    return text(u(x), u(y), s, round(size * S, 1), fill, weight, anchor, italic=italic)


def body(x, y, s, n, size=7.8, leading=1.27, anchor="start", fill=BODY) -> str:
    return "".join(label(x, y + i * size * leading, line, size, anchor, italic=True, fill=fill) for i, line in enumerate(wrap(s, n)))


def head(x, y, s, size=12.6, anchor="start", fill=INK) -> str:
    return label(x, y, s, size, anchor, 700, fill=fill)


def ink(im: Image.Image) -> Image.Image:
    """A picture on its own plain paper as ink alone, so the poster's paper shows through and no picture edge is left."""
    rgb = np.asarray(im.convert("RGB"), dtype=np.float32)
    h, w = rgb.shape[:2]
    paper = np.median(np.concatenate([rgb[:12].reshape(-1, 3), rgb[-12:].reshape(-1, 3), rgb[:, :12].reshape(-1, 3), rgb[:, -12:].reshape(-1, 3)]), axis=0)
    a = np.clip((np.abs(rgb - paper).max(axis=2) / 255 - 0.035) * 4.0, 0, 1)
    yy, xx = np.mgrid[0:h, 0:w]
    a *= np.clip(np.minimum.reduce([xx, w - 1 - xx, yy, h - 1 - yy]) / 30.0, 0, 1)
    col = np.clip((rgb - (1 - a[..., None]) * paper) / np.maximum(a[..., None], 0.05), 0, 255)
    # on a light paper the plate needs real darks and colours
    grey = col.mean(axis=2, keepdims=True)
    col = 255 * (np.clip(grey + (col - grey) * 1.5, 0, 255) / 255) ** 1.22
    return Image.fromarray(np.dstack([col, a * 255]).astype("uint8"), "RGBA")


def placed(renders: Path, shot: str, x, y, w, h, glow=False):
    """The solid part of the machine fills the box; its shadow may spill out of it. glow: the render itself with a halo, for the dark panel."""
    full = Image.open(renders / shot / "obraz.png").convert("RGBA") if glow else Image.open(renders / "rytiny" / f"{shot}.png")
    im, shift = crop_alpha(full if glow else ink(full))
    if glow:
        rgba = np.asarray(im, dtype=np.float32).copy()
        grey = rgba[..., :3].mean(axis=2, keepdims=True)
        rgba[..., :3] = np.clip(grey + (rgba[..., :3] - grey) * 2.4, 0, 255)
        im = Image.fromarray(rgba.astype("uint8"), "RGBA")
        halo = im.filter(ImageFilter.GaussianBlur(34))
        halo.alpha_composite(im.filter(ImageFilter.GaussianBlur(12)))
        halo.alpha_composite(im)
        im = halo
    box = im.getchannel("A").point(lambda v: 255 if v > 200 else 0).getbbox()
    k = min(u(w) / (box[2] - box[0]), u(h) / (box[3] - box[1]))
    left = u(x) + (u(w) - (box[2] - box[0]) * k) / 2 - box[0] * k
    top = u(y) + (u(h) - (box[3] - box[1]) * k) / 2 - box[1] * k
    return im, shift, left, top, k, full.width


def picture(renders: Path, shot: str, x, y, w, h, glow=False) -> str:
    im, _, left, top, k, _ = placed(renders, shot, x, y, w, h, glow)
    return fit(im, left, top, im.width * k, im.height * k)


def anchors(renders: Path, shot: str, x, y, w, h) -> dict:
    """The machine's named points in the poster's units, so a leader ends exactly on the part."""
    _, shift, left, top, k, width = placed(renders, shot, x, y, w, h)
    body = json.loads((renders / shot / "body.json").read_text(encoding="utf-8"))
    scale = width / body["res"][0]
    return {n: ((left + (px * scale - shift[0]) * k) / S, (top + (py * scale - shift[1]) * k) / S) for n, (px, py) in body["points"].items()}


def line(x0, y0, x1, y1, color=INK, width=1.6) -> str:
    return f'<line x1="{u(x0):.1f}" y1="{u(y0):.1f}" x2="{u(x1):.1f}" y2="{u(y1):.1f}" stroke="{color}" stroke-width="{width}"/>'


def arrow(x0, y0, x1, y1) -> str:
    """Which way the water runs."""
    a = math.atan2(y1 - y0, x1 - x0)
    tips = "".join(line(x1, y1, x1 - 4.5 * math.cos(a + s_ * 0.55), y1 - 4.5 * math.sin(a + s_ * 0.55), PALE, 2.4) for s_ in (-1, 1))
    return line(x0, y0, x1, y1, PALE, 2.4) + tips


def axes(x, y, w, h) -> str:
    return line(x, y, x, y + h) + line(x, y + h / 2, x + w, y + h / 2)


def wave(x, y, w, h, periods=1.0, phase=0.0, color=INK, width=2.2) -> str:
    pts = " ".join(f"{u(x + w * i / 90):.1f},{u(y + h / 2 - h * 0.42 * math.sin(phase + 2 * math.pi * periods * i / 90)):.1f}" for i in range(91))
    return f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="{width}"/>'


def stator(cx, cy, r) -> str:
    """Tesla's patent: a ring with four coils, opposite ones on one current, and the rotor inside."""
    o = f'<circle cx="{u(cx)}" cy="{u(cy)}" r="{u(r)}" fill="#c7bfae" stroke="{INK}" stroke-width="2"/><circle cx="{u(cx)}" cy="{u(cy)}" r="{u(r * 0.66)}" fill="#e6dcc6" stroke="{INK}" stroke-width="1.6"/>'
    for k, color in enumerate((COPPER, STEEL, COPPER, STEEL)):
        o += (f'<rect x="{u(cx + r * 0.5):.1f}" y="{u(cy - r * 0.2):.1f}" width="{u(r * 0.62):.1f}" height="{u(r * 0.4):.1f}" rx="{u(2)}" fill="{color}" stroke="{INK}" stroke-width="1.2" '
              f'transform="rotate({45 + 90 * k} {u(cx)} {u(cy)})"/>')
    o += f'<circle cx="{u(cx)}" cy="{u(cy)}" r="{u(r * 0.36)}" fill="#a79c86" stroke="{INK}" stroke-width="1.6"/><circle cx="{u(cx)}" cy="{u(cy)}" r="{u(r * 0.08)}" fill="{INK}"/>'
    return o


def poles(cx, cy, r) -> str:
    """Two poles on a ring and the direction they travel."""
    a0 = 0.7
    arc = lambda start, end, color: (f'<path d="M{u(cx + r * math.cos(start)):.1f} {u(cy + r * math.sin(start)):.1f} A{u(r)} {u(r)} 0 0 1 {u(cx + r * math.cos(end)):.1f} {u(cy + r * math.sin(end)):.1f} '
                                     f'L{u(cx + a0 * r * math.cos(end)):.1f} {u(cy + a0 * r * math.sin(end)):.1f} A{u(a0 * r)} {u(a0 * r)} 0 0 0 {u(cx + a0 * r * math.cos(start)):.1f} {u(cy + a0 * r * math.sin(start)):.1f} Z" fill="{color}" fill-opacity=".8"/>')
    o = arc(math.pi, 2 * math.pi, COPPER) + arc(0, math.pi, STEEL)
    o += f'<circle cx="{u(cx)}" cy="{u(cy)}" r="{u(r)}" fill="none" stroke="{INK}" stroke-width="1.8"/><circle cx="{u(cx)}" cy="{u(cy)}" r="{u(a0 * r)}" fill="none" stroke="{INK}" stroke-width="1.4"/>'
    rr = r * 0.42
    start, end = math.radians(200), math.radians(500)
    pts = " ".join(f"{u(cx + rr * math.cos(start + (end - start) * i / 40)):.1f},{u(cy + rr * math.sin(start + (end - start) * i / 40)):.1f}" for i in range(41))
    tipx, tipy = cx + rr * math.cos(end), cy + rr * math.sin(end)
    ang = end + math.pi / 2
    head_ = "".join(line(tipx, tipy, tipx - 7 * math.cos(ang + s * 0.5), tipy - 7 * math.sin(ang + s * 0.5), INK, 2.2) for s in (-1, 1))
    return o + f'<polyline points="{pts}" fill="none" stroke="{INK}" stroke-width="2.2"/>' + head_


def coil_circuit(x, y) -> str:
    """The Tesla coil's own circuit: capacitor and spark gap charge the primary, the secondary has many turns and no iron."""
    o = line(x + 8, y + 18, x + 8, y + 42) + line(x + 8, y + 58, x + 8, y + 104)                                 # source side
    o += line(x + 8, y + 18, x + 66, y + 18) + line(x + 8, y + 104, x + 66, y + 104)
    o += line(x - 2, y + 42, x + 18, y + 42, INK, 2.6) + line(x - 2, y + 58, x + 18, y + 58, INK, 2.6)             # capacitor
    o += line(x + 34, y + 18, x + 34, y + 44) + line(x + 34, y + 76, x + 34, y + 104)                              # spark gap branch
    o += f'<circle cx="{u(x + 34)}" cy="{u(y + 49)}" r="{u(5)}" fill="#a88e4e" stroke="{INK}" stroke-width="1.4"/><circle cx="{u(x + 34)}" cy="{u(y + 71)}" r="{u(5)}" fill="#a88e4e" stroke="{INK}" stroke-width="1.4"/>'
    for i, (a, b) in enumerate(((54, 56), (56, 67), (67, 64))):
        o += line(x + 34 - 2 + i * 1.6, y + a, x + 34 + 2 - i * 1.6, y + b, "#3f55b8", 1.8)
    # primary: few thick turns; secondary: many thin ones
    for i in range(5):
        yy = y + 22 + i * 18
        o += f'<path d="M{u(x + 66)} {u(yy)} a{u(9)} {u(9)} 0 0 1 0 {u(18)}" fill="none" stroke="{COPPER}" stroke-width="4.4"/>'
    for i in range(24):
        yy = y + 2 + i * 5
        o += f'<path d="M{u(x + 118)} {u(yy)} a{u(2.5)} {u(2.5)} 0 0 0 0 {u(5)}" fill="none" stroke="{COPPER}" stroke-width="1.6"/>'
    o += line(x + 118, y + 2, x + 118, y - 10) + line(x + 118, y + 122, x + 118, y + 134)
    o += f'<ellipse cx="{u(x + 118)}" cy="{u(y - 15)}" rx="{u(19)}" ry="{u(6)}" fill="#bdbdb8" stroke="{INK}" stroke-width="1.4"/>'
    o += line(x + 106, y + 134, x + 130, y + 134, INK, 2.4) + line(x + 110, y + 138, x + 126, y + 138, INK, 2) + line(x + 114, y + 142, x + 122, y + 142, INK, 1.6)
    return o


def page(assets: Path) -> str:
    """Pale cream like the sample: only the stains and the grain of the generated sheet stay, not its colour or torn edge."""
    src = Image.open(assets / "pergamen.png").convert("L")
    mx, my = src.width // 14, src.height // 14
    tex = np.asarray(src.crop((mx, my, src.width - mx, src.height - my)).resize((W, H), Image.LANCZOS), dtype=np.float32)
    tex = tex / np.median(tex)
    yy, xx = np.mgrid[0:H, 0:W]
    edge = np.minimum.reduce([xx, W - xx, yy, H - yy]) / 180.0
    vignette = 0.965 + 0.035 * np.clip(edge, 0, 1)
    shade = (1 + (np.clip(tex, 0.75, 1.15) - 1) * 0.3) * vignette
    cream = np.array((248, 243, 231), dtype=np.float32)
    paper = Image.fromarray(np.clip(shade[..., None] * cream, 0, 255).astype("uint8"), "RGB")
    return group("Pergamen", image_tag(paper, 0, 0, W, H, "JPEG"))


def figure(assets: Path) -> str:
    """The figure with the soft shadow it casts on the paper on the sample."""
    fig, _ = crop_alpha(Image.open(assets / "postava.png").convert("RGBA"), 0)
    tone = np.asarray(fig, dtype=np.float32).copy()
    tone[..., :3] = np.clip((tone[..., :3] / 255 - 0.5) * 1.14 + 0.44, 0, 1) * 255
    fig = Image.fromarray(tone.astype("uint8"), "RGBA")
    x, y, w, h = 253, 342, 230, 705
    k = min(u(w) / fig.width, u(h) / fig.height)
    pw, ph = fig.width * k, fig.height * k
    fx, fy = u(x) + (u(w) - pw) / 2, u(y) + (u(h) - ph) / 2
    pad = 90
    canvas = Image.new("L", (round(pw) + 2 * pad, round(ph) + 2 * pad), 0)
    mask = fig.getchannel("A").resize((round(pw), round(ph)), Image.LANCZOS)
    canvas.paste(mask, (pad, pad))
    blur = np.asarray(canvas.filter(ImageFilter.GaussianBlur(26)), dtype=np.float32) * 0.5
    zeros = np.zeros_like(blur)
    shadow = Image.fromarray(np.dstack([zeros + 58, zeros + 44, zeros + 28, blur]).astype("uint8"), "RGBA")
    return (group("Stín postavy", image_tag(shadow, fx - pad - 26, fy - pad + 8, shadow.width, shadow.height, "PNG"))
            + group("Nikola Tesla", fit(fig, fx, fy, pw, ph)))


def poster(renders: Path, assets: Path) -> str:
    gfx, txt = [page(assets)], []
    gfx.append(group("Rámy", "".join(f'<rect x="{u(x)}" y="{u(y)}" width="{u(w)}" height="{u(h)}" fill="none" stroke="{LINE}" stroke-width="2.2"/>' for x, y, w, h in PANELS.values())))
    txt.append(group("Nadpis", text(u(368), u(78), "NIKOLA TESLA", 53 * S, INK, 700, "middle", spacing=2)))
    gfx.append(group("Linka pod nadpisem", line(145, 95, 592, 95, LINE, 2)))

    # 1 motor
    gfx.append(group("Motor", picture(renders, "motor", 36, 142, 214, 198)))
    gfx.append(group("Dvě fáze", axes(256, 148, 92, 62) + wave(256, 148, 92, 62, 1, 0, COPPER) + wave(256, 148, 92, 62, 1, math.pi / 2, STEEL)))
    gfx.append(group("Stator", stator(84, 380, 40)))
    gfx.append(group("Póly", poles(202, 378, 41)))
    txt.append(group("Motor text", head(36, 133, "STŘÍDAVÝ INDUKČNÍ MOTOR", 12.6)
                     + label(302, 222, "dvě fáze, posun 90°", 7.6, "middle", italic=True)
                     + body(254, 240, f"Dva střídavé proudy posunuté o čtvrtinu periody vytvoří magnetické pole, které obíhá. Rotor ho následuje, bez komutátoru a kartáčů. Patent US{NB}381,968 z{NB}1.{NB}5.{NB}1888.", 25)
                     + body(38, 429, "Čtyři cívky, dvě fáze.", 30) + body(150, 429, f"Póly obíhají, síla pole je stálá.", 34)
                     + label(202, 351, "S", 9.5, "middle", 700, fill="#fff") + label(202, 412, "J", 9.5, "middle", 700, fill="#fff")))

    # 2 Wardenclyffe: one tower, in section. The head covers the panel's left edge, so no words there
    gfx.append(group("Wardenclyffe v řezu", picture(renders, "vez", 410, 140, 262, 326)))
    txt.append(group("Věž text", head(385, 133, f"VĚŽ WARDENCLYFFE: BEZDRÁTOVÝ PŘENOS ENERGIE", 10.6)
                     + body(562, 158, f"Věž 57{NB}m, kupole asi 20{NB}m. Cihlová dílna stojí dodnes.", 31)
                     + body(562, 190, f"J.{NB}P.{NB}Morgan dal 150{NB}000{NB}USD, další peníze 1903 odmítl. Přenos na dálku se nikdy nepovedl. Odstřel 1917.", 31)
                     + body(450, 480, f"Šachta 37{NB}m, na dně podle Tesly 16 železných trubek.", 70)))

    # 3 war of the currents: AC swings, DC does not
    g = axes(48, 500, 80, 76) + wave(48, 500, 80, 76, 1, 0, COPPER, 3.0) + axes(150, 500, 80, 76) + line(150, 516, 230, 516, STEEL, 3.2) + axes(150, 628, 80, 44) + wave(150, 628, 80, 44, 1, 0, COPPER, 2) + wave(150, 642, 80, 16, 1, 0, STEEL, 2)
    gfx.append(group("Grafy proudů", g))
    txt.append(group("Proudy text", head(138, 481, "VÁLKA PROUDŮ", 13, "middle") + label(88, 498, "STŘÍDAVÝ", 8.4, "middle", 700) + label(190, 498, "STEJNOSMĚRNÝ", 8.4, "middle", 700)
                     + body(38, 592, f"16.{NB}11.{NB}1896 dorazil střídavý proud z{NB}Niagary do Buffala, 42{NB}km.", 25)
                     + body(142, 592, f"Edisonova stanice z{NB}roku 1882 pokryla asi 0,8{NB}km.", 25)
                     + body(38, 636, "Transformátor zvýší napětí střídavého proudu, vedení má malé ztráty, u spotřebiče se zase sníží.", 23)
                     + label(190, 684, "vyšší napětí, menší proud", 6.8, "middle", italic=True)))

    # 4 coil and its circuit
    gfx.append(group("Teslova cívka", picture(renders, "civka-bez", 496, 546, 194, 184)))
    gfx.append(group("Obvod cívky", coil_circuit(528, 760)))
    words = text(u(600), u(524), "TESLOVA CÍVKA:", 11.8 * S, INK, 700, "middle") + text(u(600), u(540), "VYSOKOFREKVENČNÍ TRANSFORMÁTOR", 9.6 * S, INK, 700, "middle")
    words += body(649, 590, f"Rezonance zvedne nízké napětí na velmi vysoké. Patent US{NB}454,622, 1891.", 14, 7.6)
    words += label(600, 734, "Obvod rezonančního transformátoru", 8.2, "middle")
    words += label(506, 812, "Kondenzátor", 7, italic=True) + label(574, 800, "Jiskřiště", 7, "middle", italic=True) + label(612, 892, "Primár:", 7.4, "middle", 700) + label(612, 902, "pár závitů", 7, "middle", italic=True)
    words += label(652, 846, "Sekundár:", 7.4, weight=700) + label(652, 856, "stovky závitů,", 7, italic=True) + label(652, 866, "bez železa", 7, italic=True)
    words += body(502, 922, f"Jiskřiště vybíjí kondenzátor přes primár, znovu a znovu. Stejný obvod nezávisle našel Elihu Thomson.", 54)
    txt.append(group("Cívka text", words))

    # 5 radio
    gfx.append(group("Přijímač a klíč", picture(renders, "prijimac", 36, 732, 204, 104)))
    gfx.append(group("Loď", picture(renders, "lod", 38, 866, 204, 74)))
    txt.append(group("Rádio text", head(138, 724, "RÁDIO A DÁLKOVÉ OVLÁDÁNÍ", 11.6, "middle")
                     + body(38, 846, "Skříňka s měřidly, anténa a telegrafní klíč: signál prochází bez drátu. Ilustrační model.", 50)
                     + body(38, 950, f"Teslova loď bez posádky, řízená elektrickými kmity. Madison Square Garden, září 1898. Patent US{NB}613,809.", 50)))

    # 6 tubes
    px, py, pw, ph = PANELS["trubice"]
    gfx.append(group("Tmavý panel", f'<rect x="{u(px)}" y="{u(py)}" width="{u(pw)}" height="{u(ph)}" fill="{NIGHT}"/>'))
    gfx.append(group("Výbojka", picture(renders, "trubice", 38, 1046, 204, 66, glow=True)))
    gfx.append(group("Dvě trubice", picture(renders, "trubice2", 62, 1140, 62, 104, glow=True)))
    shadow = np.asarray(Image.open(assets / "rentgen.png").convert("L").filter(ImageFilter.GaussianBlur(16)), dtype=np.float32) / 255
    shadow = shadow ** 1.3
    shadow = Image.fromarray(np.dstack([shadow * 232 + 16, shadow * 236 + 16, shadow * 240 + 20]).astype("uint8"), "RGB")
    gfx.append(group("Stínový snímek", cover(shadow, u(146), u(1148), u(88), u(92))))
    txt.append(group("Trubice text", head(138, 1008, "VÝBOJKY A RENTGEN", 12.6, "middle", PALE)
                     + body(38, 1024, "V 90. letech rozsvěcel Tesla výbojky bez drátů pomocí svých cívek, i při veřejných ukázkách.", 50, fill=PALE)
                     + body(38, 1122, "Trubice dávaly jasné nazelenalé světlo, komerčně neuspěly.", 50, fill=PALE)
                     + body(38, 1254, "Výbojky svítí bez přívodního drátu.", 21, fill=PALE) + body(146, 1254, "Stínový snímek, rentgen 1896 (ilustrace).", 25, 7.2, fill=PALE)))

    # 7 turbine
    gfx.append(group("Turbína", picture(renders, "turbina", 276, 1110, 188, 138)))
    txt.append(group("Turbína text", head(369, 1071, "TESLOVA TURBÍNA", 12.6, "middle")
                     + body(269, 1085, "Hladké disky bez lopatek: pára vstupuje na obvodu a spirálou míří ke středu. Rotor unáší přilnavost a vazkost.", 50)
                     + body(269, 1252, f"Patent US{NB}1,061,206 ze 6.{NB}5.{NB}1913. Disky se v žáru deformovaly, proto se neprosadila.", 50)))

    # 8 water: how it works, in section; a water plant has no chimneys
    box = (500, 1016, 200, 220)
    gfx.append(group("Elektrárna Adams v řezu", picture(renders, "elektrarna", *box)))
    at = anchors(renders, "elektrarna", *box)
    ties = "".join(line(tx, ty, *at[name], INK, 1.4) + f'<circle cx="{u(at[name][0]):.1f}" cy="{u(at[name][1]):.1f}" r="2.6" fill="{INK}"/>'
                   for name, tx, ty in (("generator", 643, 1043), ("privadec", 558, 1106), ("hridel", 625, 1112), ("turbina", 625, 1176)))
    gfx.append(group("Vodítka elektrárny", ties))
    gfx.append(group("Tok vody", "".join(arrow(*at[a_], *at[b_]) for a_, b_ in (("kanal_a", "kanal_b"), ("trubka_a", "trubka_b"), ("tunel_a", "tunel_b")))))
    words = label(645, 1046, "generátor", 7.6, weight=700) + label(528, 1108, "přivaděč", 7.6, weight=700) + label(627, 1110, "hřídel", 7.6, weight=700)
    words += label(627, 1174, "turbína", 7.6, weight=700) + label(573, 1232, f"odpadní tunel, asi 2{NB}km", 7.6, weight=700)
    words += label(670, 1120, "vodopády", 7.6, "middle", 700) + label(at["reka"][0], at["reka"][1] + 2, "řeka", 7.2, "middle", 700) + label(517, 1079, "řeka", 7.2, weight=700)
    # labels lie on the hatched ground: a thin outline in the colour of the paper keeps them readable
    words = f'<g style="paint-order:stroke;stroke:#f8f3e7;stroke-width:3px;stroke-linejoin:round">{words}</g>'
    txt.append(group("Voda text", head(600, 1009, "VODNÍ ELEKTRÁRNA", 12.6, "middle") + words
                     + body(502, 1246, f"Elektrárna Adams, Niagara, 1895. Voda padá šachtou asi 50{NB}m na turbínu, hřídel točí generátorem v{NB}hale, tunel ji odvádí pod vodopády. Deset generátorů po 5{NB}000 koňských silách (3,7{NB}MW). Řez není v{NB}měřítku.", 56, 7.2)))

    gfx.append(figure(assets))
    txt.append(group("Poznámka", label(368, 1298, "Stroje: modely v Blenderu. Postava: 3D model Hunyuan a lokální FLUX (AI). Stínový snímek: lokální FLUX (AI). Podle cizího vzoru, detaily opravené podle zdrojů.", 6.2, "middle", italic=True)))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{SERIF}">'
            f'<g id="Grafika">{"".join(gfx)}</g><g id="Texty">{"".join(txt)}</g></svg>')


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    renders, assets, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    knihovna = sys.argv[sys.argv.index("--knihovna") + 1] if "--knihovna" in sys.argv else None
    write_poster(poster(renders, assets), out, "tesla-kopie", W, H, "Nikola Tesla: infografika podle vzoru, stroje z 3D modelů", knihovna, ai=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
