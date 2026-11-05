# Spolkl by vorvaň člověka? Vrstvená stránka pro web (docs/infografiky-zasady.md: Web a mobil, Vrstvy pro jiný formát).
# Fakta: dossier library/research/vorvan-v2 (řetězec 20261105-071537-cf65): f4 f19 f21 f22 f50 f93 f138 a Wikipedia (en) Sperm whale,
# odstavec o trávení (komory žaludku, střevo 152 m). Zdroje do zdroje.txt, na stránce jen označení AI.
# Obrazy: scripts/plakaty/vorvan_obrazy.py (FLUX 3 Klein, AI), každý objekt vlastní vrstva:
#   vorvan-vrstva.png, potapec-vrstva.png, organy-42.png (3D orgány na zeleném). Jsou 2D; 3D model vorvaně je další krok.
# Operátor 5. 11.: hlavní je rozebrat možnost spolknutí. Dominuje vorvaň s průsvitným tělem a 3D vnitřnostmi a potápěč
# ve skutečném poměru; srovnání jícnu s člověkem patří na stránku, ale malé. Mírná perspektiva: hlava blíž, ocas dál.
# 9:16: vorvaň svisle hlavou nahoru vlevo (tak i spí, f21), popisky vpravo ve výšce svého orgánu.
# 16:9 (hlavní verze) ze stejných vrstev: vorvaň vodorovně, popisky nad a pod tělem.
#   python scripts/plakaty/vorvan_stranka.py DATA_DIR
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).parent))
from engine.panels import cut_green  # noqa: E402
from sazba import FONT, group, image_tag, text, write_poster  # noqa: E402

BG_TOP, BG_BOTTOM = "#0f3a52", "#06141e"
WHITE, DIM, TEAL = "#f1ede4", "#a9bcc6", "#7fd3dc"
FLESH = "#d07a6c"
NB = " "

WHALE_M = 16.0                       # dospělý samec měří v průměru 16 m (f22)
ORGAN_CROP = (200, 30, 1495, 500)    # organy-42.png bez zahnutého konce jícnu
ORGAN_AT, ORGAN_K = (385, 86), 0.44  # levý horní roh orgánů ve vrstvě vorvaně a jejich měřítko
THROAT_PTS = [((228, 242), (280, 240), (330, 232), (360, 214)), ((360, 214), (378, 198), (392, 192), (412, 190))]   # tlama → jícen orgánů
CAVITY = (600, 200, 470, 108)        # průsvitná část těla: střed a poloosy, souřadnice vorvaně
F = 2                                # vnitřek a kůže ve dvojnásobném rozlišení vrstvy vorvaně (orgány mají víc detailu)
PERSP_K, PERSP_C = 0.82, 0.94        # mírná perspektiva: ocas má 82 % výšky hlavy, délka zkrácená na 94 %

# popisky: bod ve vrstvě vorvaně, nadpis, text
LABELS = [
    ((150, 258), "Tlama", "Zuby má jen dole, 20 až 26 na každé straně."),
    ((345, 222), "Jícen", f"Jediná cesta dál. Měří 10{NB}až{NB}15, nebo 30{NB}až{NB}40{NB}cm? Zdroje se přou."),
    ((520, 190), "Předžaludek", "Svaly drtí potravu, trávicí šťávy tu nejsou."),
    ((640, 186), "Hlavní žaludek", "Teprve tady se tráví."),
    ((865, 186), "Střevo", f"Dlouhé kolem 152{NB}m."),
]
TITLE = "Spolkl by vorvaň člověka?"
LEAD = "Vorvaň (16 m) a potápěč jsou ve stejném měřítku. Do žaludku vede jen jícen."
PACKARD = "Michael Packard tvrdil, že ho v roce 2021 spolkl a vyplivl keporkak. Odborníci pochybují."
AI_NOTE = "Obrazy: AI (FLUX 3 Klein), ilustrace, ne fotografie."
CREDITS = """Spolkl by vorvaň člověka? Zdroje pod článek:
- Délka samce 16 m; spí svisle; komory žaludku a předžaludek bez trávicích šťáv; střevo kolem 152 m: Wikipedia (en), Sperm whale.
- Zuby 20–26 na každé straně dolní čelisti: Florida Fish and Wildlife Conservation Commission, Sperm whale.
- Jícen 10–15 cm: MarineBio, Swallowed by a sperm whale? Jícen 30–40 cm: Science Friday, Whalefall movie science.
- Předžaludek je bezžlázový vak: PubMed 3434544. Trávení až v hlavní komoře: Gut Health Times (sekundární zdroj).
- Michael Packard 2021: Smithsonian Magazine; pochybnosti odborníka: NPR, 12. 6. 2021.
- Obrazy: FLUX 3 Klein (AI). Tvar vorvaně podle kresby Physeter macrocephalus1.jpg (Wikimedia Commons, public domain), kůže podle fotografie B. Spragga (CC0). Vnitřnosti jsou ilustrace, poloha orgánů je přibližná.
"""


def lines(x, y, rows, size, fill, leading=1.22, weight=400, anchor="start") -> str:
    return "".join(text(x, y + i * size * leading, r, size, fill, weight, anchor) for i, r in enumerate(rows))


def wrap_px(s: str, width: float, size: float) -> list[str]:
    """Zalomení podle šířky v px; Bahnschrift zúžený má průměrně ~0,47 em na znak."""
    n = max(8, int(width / (size * 0.47)))
    rows, cur = [], ""
    for w in s.split(" "):     # pevná mezera drží číslo s jednotkou
        if cur and len(cur) + 1 + len(w) > n:
            rows.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    rows.append(cur)
    for i in range(len(rows) - 1):       # jednopísmenná předložka nezůstane na konci řádku
        head, _, last = rows[i].rpartition(" ")
        if head and len(last) == 1:
            rows[i], rows[i + 1] = head, f"{last} {rows[i + 1]}"
    return rows


def organs_layer(data: Path) -> Image.Image:
    cut = data / "organy-vrstva.png"
    if not cut.exists():
        cut_green(Image.open(data / "organy-42.png").convert("RGBA")).crop(ORGAN_CROP).save(cut)
    return Image.open(cut)


def see_through(whale: Image.Image, keep: float = 0.22) -> Image.Image:
    """Kůže vorvaně zprůhledněná nad tělní dutinou: z kůže zůstane `keep`, k okraji plynule celá."""
    cx, cy, rx, ry = CAVITY
    yy, xx = np.mgrid[0:whale.height, 0:whale.width]
    d = np.sqrt(((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2)
    fade = np.clip((d - 0.72) / 0.28, 0, 1)
    a = np.asarray(whale.getchannel("A"), dtype=np.float32) * (keep + (1 - keep) * fade)
    out = whale.copy()
    out.putalpha(Image.fromarray(a.astype("uint8")))
    return out


def bezier(p0, p1, p2, p3, n: int = 40) -> list[tuple[float, float]]:
    t = np.linspace(0, 1, n)[:, None]
    pts = (1 - t) ** 3 * np.array(p0) + 3 * (1 - t) ** 2 * t * np.array(p1) + 3 * (1 - t) * t ** 2 * np.array(p2) + t ** 3 * np.array(p3)
    return [(float(x), float(y)) for x, y in pts]


def homography(src, dst) -> np.ndarray:
    rows, rhs = [], []
    for (x, y), (u, v) in zip(src, dst):
        rows += [[x, y, 1, 0, 0, 0, -u * x, -u * y], [0, 0, 0, x, y, 1, -v * x, -v * y]]
        rhs += [u, v]
    return np.append(np.linalg.solve(np.array(rows, float), np.array(rhs, float)), 1).reshape(3, 3)


def layers(data: Path):
    """Průsvitná kůže a vnitřek (dutina, jícen, 3D orgány) ve stejné mírné perspektivě: hlava blíž, ocas dál.
    Vrací (kůže, vnitřek, bod vrstvy vorvaně → bod v perspektivě, (šířka, výška) vrstvy)."""
    whale = Image.open(data / "vorvan-vrstva.png")
    W, H = whale.size
    big = (W * F, H * F)
    cx, cy, rx, ry = CAVITY
    yy, xx = np.mgrid[0:big[1], 0:big[0]] / F
    d = np.sqrt(((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2)
    mix = np.clip(d, 0, 1)[..., None]
    rgb = (1 - mix) * np.array([74, 28, 30]) + mix * np.array([58, 22, 24])
    inner = Image.fromarray(np.dstack([rgb, 255 * np.clip((1 - d) / 0.2, 0, 1)]).astype("uint8"), "RGBA")
    draw = ImageDraw.Draw(inner)
    pts = [(x * F, y * F) for seg in THROAT_PTS for x, y in bezier(*seg, n=240)]
    for r, fill in ((15 * F, (142, 68, 61, 255)), (12 * F, (208, 122, 108, 255)), (4 * F, (232, 156, 142, 255))):
        for x, y in pts:          # řada kruhů: spoje tlusté čáry v PIL dělají příčné čárky
            dy = -5 * F if r == 4 * F else 0
            draw.ellipse((x - r, y + dy - r, x + r, y + dy + r), fill=fill)
    organs = organs_layer(data)
    inner.alpha_composite(organs.resize((round(organs.width * ORGAN_K * F), round(organs.height * ORGAN_K * F)), Image.LANCZOS),
                          (ORGAN_AT[0] * F, ORGAN_AT[1] * F))
    body = whale.getchannel("A").filter(ImageFilter.MinFilter(5)).resize(big, Image.LANCZOS)
    inner.putalpha(Image.fromarray((np.asarray(inner.getchannel("A"), np.float32) * np.asarray(body, np.float32) / 255).astype("uint8")))
    skin = see_through(whale).resize(big, Image.LANCZOS)

    Wd, Hd = big
    src = [(0, 0), (Wd, 0), (Wd, Hd), (0, Hd)]
    dst = [(0, 0), (Wd * PERSP_C, Hd * (1 - PERSP_K) / 2), (Wd * PERSP_C, Hd * (1 + PERSP_K) / 2), (0, Hd)]
    fwd, inv = homography(src, dst), homography(dst, src)

    def warp(im: Image.Image) -> Image.Image:
        return im.transform(big, Image.PERSPECTIVE, tuple(inv.flatten()[:8]), Image.BICUBIC)

    def point(px, py):
        u, v, w = fwd @ np.array([px * F, py * F, 1.0])
        return u / w / F, v / w / F
    return warp(skin), warp(inner), point, (W, H)


def whale_svg(data: Path, x0: float, y0: float, s: float, upright: bool):
    """Vorvaň na stránce: vodorovně hlavou vlevo, nebo `upright` svisle hlavou nahoru s břichem vpravo (zrcadlově, k popiskům).
    Vrací (svg, bod vrstvy → stránka, šířka, výška)."""
    skin, inner, point, (W, H) = layers(data)
    body = group("Vnitřnosti 3D", image_tag(inner, 0, 0, W * F, H * F, "PNG")) + group("Průsvitná kůže", image_tag(skin, 0, 0, W * F, H * F, "PNG"))
    flip = "matrix(0 1 1 0 0 0) " if upright else ""
    svg = f'<g transform="translate({x0:.2f} {y0:.2f}) {flip}scale({s / F:.5f})">{body}</g>'

    def at(px, py):
        u, v = point(px, py)
        return (x0 + v * s, y0 + u * s) if upright else (x0 + u * s, y0 + v * s)
    size = (H * s, W * PERSP_C * s) if upright else (W * PERSP_C * s, H * s)
    return svg, at, size[0], size[1]


def diver_layer(data: Path, mouth: tuple[float, float], px_per_m: float, facing_left: bool) -> str:
    """Potápěč ve stejném měřítku jako hlava vorvaně: tělo s ploutvemi kolem 2,3 m, hlavou k tlamě."""
    diver = Image.open(data / "potapec-vrstva.png")          # ve vrstvě plave doleva
    if not facing_left:
        diver = ImageOps.mirror(diver)
    w = 2.3 * px_per_m
    h = diver.height * w / diver.width
    x = mouth[0] if facing_left else mouth[0] - w
    y = mouth[1] - h * 0.45
    # jemná záře kolem těla potápěče (operátor: „je špatně viditelný“, „víc kolem těla“): rozostřená silueta, ne elipsa
    pad = round(diver.width * 0.08)
    sil = Image.new("L", (diver.width + 2 * pad, diver.height + 2 * pad), 0)
    sil.paste(diver.getchannel("A"), (pad, pad))
    halo = sil.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.GaussianBlur(pad * 0.45))
    glow = Image.new("RGBA", sil.size, (150, 225, 232, 0))
    glow.putalpha(halo.point(lambda v: round(v * 0.6)))
    k = w / diver.width
    return (group("Záře kolem potápěče", image_tag(glow, x - pad * k, y - pad * k, glow.width * k, glow.height * k, "PNG"))
            + group("Potápěč", image_tag(diver, x, y, w, h, "PNG")))


def rings_inset(x: float, y: float, cm: float = 2.6, step: float = 190, head: int = 40) -> tuple[str, str, float]:
    """Projde člověk jícnem? Člověk zepředu (ramena kolem 45 cm, jen obrys) a jícen podle dvou zdrojů ve stejném měřítku."""
    base = y + 78 + 46 * cm
    sx = x + 70
    shape = (f'<ellipse cx="{sx:.1f}" cy="{base - 33 * cm:.1f}" rx="{8 * cm:.1f}" ry="{10.5 * cm:.1f}" fill="{DIM}" fill-opacity="0.75"/>'
             f'<path d="M {sx - 22.5 * cm:.1f} {base:.1f} C {sx - 23 * cm:.1f} {base - 14 * cm:.1f} {sx - 16 * cm:.1f} {base - 20 * cm:.1f} {sx - 6 * cm:.1f} {base - 21 * cm:.1f} '
             f'L {sx + 6 * cm:.1f} {base - 21 * cm:.1f} C {sx + 16 * cm:.1f} {base - 20 * cm:.1f} {sx + 23 * cm:.1f} {base - 14 * cm:.1f} {sx + 22.5 * cm:.1f} {base:.1f} Z" fill="{DIM}" fill-opacity="0.75"/>')
    labels = text(x, y + 40, "Projde člověk jícnem?", head, TEAL, 700) + text(sx, base + 44, "člověk", 36, WHITE, 700, "middle")
    for i, (lo, hi, label, who) in enumerate(((10, 15, "10–15 cm", "MarineBio"), (30, 40, "30–40 cm", "Science Friday"))):
        cx, cy = sx + step * (i + 1), base - 20 * cm
        shape += (f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{hi / 2 * cm:.1f}" fill="{FLESH}" fill-opacity="0.45" stroke="{FLESH}" stroke-width="2.5"/>'
                  f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{lo / 2 * cm:.1f}" fill="none" stroke="{WHITE}" stroke-width="1.5" stroke-dasharray="5 5"/>')
        labels += text(cx, base + 44, label, 36, WHITE, 700, "middle")
        labels += group(f"Zdroj {who}", text(cx, base + 80, who, 28, DIM, anchor="middle"))
    return group("Jícen proti člověku", shape), group("Jícen proti člověku, popisky", labels), base + 80


def svg_page(W: int, H: int, graphics: list[str], texts: list[str]) -> str:
    defs_bg = (f'<linearGradient id="more" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{BG_TOP}"/>'
               f'<stop offset="1" stop-color="{BG_BOTTOM}"/></linearGradient>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{FONT}" font-stretch="semi-condensed">'
            f'<defs>{defs_bg}</defs><rect id="Pozadí" width="{W}" height="{H}" fill="url(#more)"/>'
            + group("Grafika", "".join(graphics)) + group("Texty", "".join(texts)) + "</svg>")


def page_916(data: Path) -> tuple[str, int, int]:
    """Vorvaň svisle vlevo, popisky vpravo ve výšce svého orgánu (operátor: obraz a popisky zrcadlově)."""
    W, H = 1080, 1920
    TT, LEAD_S, HEAD, LINE, NOTE = 84, 40, 40, 36, 27
    M = 40
    whale_w = Image.open(data / "vorvan-vrstva.png").width
    y0 = 150
    s = (H - y0 - 40) / (whale_w * PERSP_C)
    whale_s, at, ww, wh = whale_svg(data, 20, y0, s, upright=True)
    col_x = 20 + ww + 50
    col = W - M - col_x
    texts = [group("Titulek", text(M, 104, TITLE, TT, WHITE, 700))]
    lead_rows = wrap_px(LEAD, col, LEAD_S)
    texts.append(group("Úvod", lines(col_x, 210, lead_rows, LEAD_S, DIM)))
    prev_bottom = 210 + (len(lead_rows) - 1) * LEAD_S * 1.22 + 20
    mouth = at(290, 252)
    graphics = [whale_s, diver_layer(data, (mouth[0] + 10, mouth[1]), whale_w * s / WHALE_M, facing_left=True)]
    for (px, py), head, body in LABELS:
        bx, by = at(px, py)
        rows = wrap_px(body, col, LINE)
        top = max(by - 14, prev_bottom + 30)
        line_y = top + HEAD * 0.5
        s_txt = text(col_x, top + HEAD * 0.8, head, HEAD, TEAL, 700) + lines(col_x, top + HEAD * 0.8 + HEAD * 1.1, rows, LINE, WHITE)
        lead = f'<polyline points="{bx:.1f},{by:.1f} {col_x - 34:.1f},{by:.1f} {col_x - 14:.1f},{line_y:.1f}" fill="none" stroke="{WHITE}" stroke-width="2"/>'
        texts.append(group(head, s_txt + lead + f'<circle cx="{bx:.1f}" cy="{by:.1f}" r="6" fill="{WHITE}"/>'))
        prev_bottom = top + HEAD * 0.8 + HEAD * 1.1 + (len(rows) - 1) * LINE * 1.22 + 10
    shape, labels, bottom = rings_inset(col_x, prev_bottom + 26, cm=2.2, step=175)
    graphics.append(shape)
    texts.append(labels)
    texts.append(group("Packard", lines(col_x, bottom + 52, wrap_px(PACKARD, col, LINE), LINE, WHITE)))
    texts.append(group("Patička", text(W - M, H - 24, AI_NOTE, NOTE, DIM, anchor="end")))
    return svg_page(W, H, graphics, texts), W, H


def page_169(data: Path) -> tuple[str, int, int]:
    """Hlavní verze 16:9: vorvaň vodorovně hlavou vlevo, potápěč před tlamou, popisky nad a pod tělem u svého orgánu."""
    W, H = 1920, 1080
    TT, HEAD, LINE, NOTE = 112, 48, 40, 30
    M = 60
    whale_w = Image.open(data / "vorvan-vrstva.png").width
    x0, y0 = 380, 330
    s = (W - 30 - x0) / (whale_w * PERSP_C)
    whale_s, at, ww, wh = whale_svg(data, x0, y0, s, upright=False)
    jaw = at(40, 262)
    graphics = [whale_s, diver_layer(data, (jaw[0] - 14, jaw[1]), whale_w * s / WHALE_M, facing_left=False)]
    texts = [group("Titulek", text(M, 140, TITLE, TT, WHITE, 700)),
             group("Úvod", text(M, 210, "Vorvaň (16 m) a potápěč ve stejném měřítku.", 40, DIM))]
    # popisek: (nad tělem?, levý okraj textu, šířka)
    place = {"Tlama": (False, 470, 300), "Jícen": (False, 800, 330), "Předžaludek": (True, 910, 470),
             "Hlavní žaludek": (False, 1160, 220), "Střevo": (True, 1420, 440)}
    for (px, py), head, body in LABELS:
        above, x, w = place[head]
        bx, by = at(px, py)
        rows = wrap_px(body, w, LINE)
        block = HEAD * 0.8 + HEAD * 1.1 + (len(rows) - 1) * LINE * 1.22 + LINE * 0.3
        top = 345 - block if above else 720
        s_txt = text(x, top + HEAD * 0.8, head, HEAD, TEAL, 700) + lines(x, top + HEAD * 0.8 + HEAD * 1.1, rows, LINE, WHITE)
        end = (top + block + 8) if above else (top - 12)
        lead = f'<line x1="{bx:.1f}" y1="{by:.1f}" x2="{bx:.1f}" y2="{end:.1f}" stroke="{WHITE}" stroke-width="2.5"/>'
        texts.append(group(head, s_txt + lead + f'<circle cx="{bx:.1f}" cy="{by:.1f}" r="7" fill="{WHITE}"/>'))
    shape, labels, _ = rings_inset(1390, 770, cm=2.0, step=175)
    graphics.append(shape)
    texts.append(labels)
    texts.append(group("Patička", text(W - M, H - 26, AI_NOTE, NOTE, DIM, anchor="end")))
    return svg_page(W, H, graphics, texts), W, H


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    data = Path(sys.argv[1])
    out = data.parent / "stranky"
    for stem, page in (("vorvan-9x16", page_916), ("vorvan-16x9", page_169)):
        svg, w, h = page(data)
        print(stem)
        write_poster(svg, out, stem, w, h, TITLE, None, ai=True)
    (out / "zdroje.txt").write_text(CREDITS, encoding="utf-8")
