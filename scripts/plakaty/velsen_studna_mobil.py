# The well of Velsen as a series for the phone (docs/infografiky-zasady.md, Web a mobil): one question on a page, the same text sizes on all pages, every page with its own title and source.
# Facts: docs/spikes/2026-11-01-velsen.md. The big page stays as it is: velsen_studna_stranka.py. Renders, under the heavy lock (scripts/3d/velsen_studna_run.py):
#   velsen_kostra.py kostra/bp3d mobil/kostra --w 1500 --h 1300 --vyska 0.44 --stred -0.03 --gpu       velsen_studna.py render/celek-2x --w 2028 --h 4400 --gpu --zblizka
#   python scripts/plakaty/velsen_studna_mobil.py LIB OUT [--jen 1,3]
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from sazba import FONT, crop_alpha, group, image_tag, text, text_over, wrap, write_poster  # noqa: E402
from velsen_studna_stranka import BG, DIM, GOLD, WHITE, compose, torn  # noqa: E402

W, H = 1080, 1620
TITLE, LEAD, HEAD, LINE, NOTE = 120, 42, 40, 36, 27
M = 30
SOURCE = "Zdroj: Driessen, van Driel-Murray (eds.), Victims of Violence from the early Roman fort Velsen 1, Sidestone 2026, CC BY-NC-ND 4.0"


def lines(x, y, rows, size, fill, leading=1.24, weight=400, anchor="start") -> str:
    return "".join(text(x, y + i * size * leading, row, size, fill, weight, anchor) for i, row in enumerate(rows))


def note(x, s, chars, bottom=H - M) -> str:
    rows = wrap(s, chars)
    return group("Zdroj", lines(x, bottom - (len(rows) - 1) * NOTE * 1.24, rows, NOTE, DIM))


def label(lx, x, y, head, line, via=None, dot=None) -> str:
    """A heading and a line at the height of the thing. `via`: the height of the leader when it has to go round something, `dot`: of the point."""
    at = y if via is None else via
    heads = head if isinstance(head, tuple) else (head,)
    rows = line if isinstance(line, tuple) else (line,)
    dot = y if dot is None else dot
    s = lines(lx, at + 14, heads, HEAD, GOLD, weight=600) + lines(lx, at + 14 + len(heads) * HEAD * 1.16 + 2, rows, LINE, WHITE)
    s += f'<polyline points="{x:.1f},{dot:.1f} {x:.1f},{at:.1f} {lx - 12:.1f},{at:.1f}" fill="none" stroke="{GOLD}" stroke-width="2"/><circle cx="{x:.1f}" cy="{dot:.1f}" r="5" fill="{GOLD}"/>'
    return group(heads[0], s)


def page(grafika: str, texty: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{FONT}" font-stretch="semi-condensed">'
            f'<rect id="Pozadí" width="{W}" height="{H}" fill="{BG}"/>' + group("Grafika", grafika) + group("Texty", texty) + "</svg>")


def well(lib: Path) -> str:
    """Where he lay: the whole well, as tall as the page lets it."""
    raw, body, _ = compose(lib, "celek-2x")
    s = raw.width / 1014        # torn() counts in pixels of the size celek
    body = {name: [v / s for v in point] for name, point in body.items()}
    block, (ox, oy) = crop_alpha(torn(raw.resize((1014, round(raw.height / s)), Image.LANCZOS), 0.42))
    by = 150
    k = (H - by - M) / block.height
    bw = block.width * k

    def at(name):
        return M + (body[name][0] - ox) * k, by + (body[name][1] - oy) * k

    lx = M + bw + 48
    t = group("Titulek", text(M, 118, "MUŽ NA DNĚ STUDNY", TITLE, GOLD, 700)
              + lines(lx, 208, ("Římská pevnost Velsen, dnes", "Nizozemsko, léta 28–38 n. l.", "Někdo ho spustil pod vodu", "a zatížil, aby nevyplaval.", "Kdo a proč, se neví."), LEAD, WHITE))
    t += label(lx, at("hladina")[0], at("hladina")[1], "Nejméně metr vody nad hlavou", "Hladina asi −0,5 až −0,75 m")
    t += label(lx, at("sud1")[0], at("sud1")[1], "Tři sudy nad sebou", "Horní je odhad ze zlomků obruče")
    t += label(lx, at("muz")[0], at("muz")[1], "Muž v prostředním sudu", "Seděl skrčený, zatížený kameny")
    t += label(lx, at("sud3")[0] - 40, 1305, "Spodní sud plný písku", "Tělo proto nekleslo níž")     # under the pot
    scale = ""
    for name, value in (("povrch", "0 m"), ("ret", "−2,41 m"), ("floor", "−4,0 m"), ("dno", "−5,8 m")):
        ay = at(name)[1]
        scale += f'<line x1="{M + 4}" y1="{ay:.1f}" x2="{M + 58}" y2="{ay:.1f}" stroke="{WHITE}" stroke-width="2"/>' + text(M + 4, ay - 8, value, LINE, WHITE, 500)
    t += group("Hloubka", scale)
    t += note(lx, f"{SOURCE}, obr. 2.1. Studna: 3D model, Blender, bez AI. Muž a plášť: FLUX 3 Klein (AI). Nadzemní část a horní sud: rekonstrukce. Výšky vůči hladině moře.", 48, H - 22)
    return page(group("Studna", image_tag(block, M, by, bw, block.height * k, "PNG")), t)


def barrel(lib: Path) -> tuple[str, Image.Image]:
    """What held him down: the middle barrel close up, from the render at twice the size."""
    raw, body, _ = compose(lib, "celek-2x")
    s = raw.width / 1014
    x0, y0, x1, y1 = 300, 992, 720, 1720        # at the size of the render celek
    crop = raw.crop((round(x0 * s), round(y0 * s), round(x1 * s), round(y1 * s)))
    by, bw = 300, 640
    k = bw / (x1 - x0)
    bh = (y1 - y0) * k

    def at(name):
        return M + (body[name][0] / s - x0) * k, by + (body[name][1] / s - y0) * k

    lx = M + bw + 42
    t = group("Titulek", text(M, 118, "ABY NEVYPLAVAL", TITLE, GOLD, 700)
              + lines(M, 208, ("Voják, 184–191 cm, asi 25 let,", "v prostředním sudu studny ve Velsenu."), LEAD, WHITE))
    t += label(lx, at("kul")[0], at("kul")[1], "Kůl asi 1,5 m", "Šikmo k hrudi")
    t += label(lx, at("kameny")[0], at("kameny")[1], ("60 kg žernovů,", "19 kg kamenů"), "Aby tělo nevyplavalo", via=at("kameny_nad")[1])     # over his head
    t += label(lx, at("muz")[0], at("muz")[1] - 40, "Bez zbroje", ("Do sudu se vešel", "jen skrčený"))
    t += label(lx, at("bota")[0], at("bota")[1], "Jediná bota", "Levá caliga", via=at("bota_pod")[1])
    t += note(M, f"{SOURCE}: muž podle kresby F. Marschalla (obr. 11.1). Studna: 3D model, render v Blenderu, bez AI. Postava muže a plášť: FLUX 3 Klein (AI).", 94)
    mask = Image.new("L", (W, H), 0)
    mask.paste(255, (M, by, round(M + bw), round(by + bh)))
    return page(group("Prostřední sud", image_tag(crop, M, by, bw, bh)), t), mask


def bones(lib: Path) -> tuple[str, Image.Image]:
    """Where they stabbed him: one pelvis, large enough for the wounds to be seen on a phone."""
    d = lib / "mobil/kostra"
    pelvis = Image.open(d / "panev.png").convert("RGBA")
    ghost = Image.open(d / "panev-duch.png").convert("RGBA")
    ghost.putalpha(ghost.getchannel("A").point(lambda v: round(v * 0.62)))
    pelvis.alpha_composite(ghost)
    marks = json.loads((d / "body.json").read_text(encoding="utf-8"))["panev"]
    pelvis, (kx, ky) = crop_alpha(pelvis)
    vw = W - 2 * M
    k = vw / pelvis.width
    vy, vh = 550, 890
    # the thigh bones go on below the picture: they fade out instead of ending in a straight cut
    pelvis = pelvis.crop((0, 0, pelvis.width, round(vh / k)))
    a = np.asarray(pelvis.getchannel("A"), dtype=np.float32) * np.clip((pelvis.height - np.arange(pelvis.height, dtype=np.float32)) / 170, 0, 1)[:, None]
    pelvis.putalpha(Image.fromarray(np.uint8(a)))

    def at(name):
        return M + (marks[name][0] - kx) * k, vy + (marks[name][1] - ky) * k

    t = group("Titulek", text(M, 118, "KAM HO BODALI", TITLE, GOLD, 700)
              + lines(M, 208, ("Úhly ran jsou podobné, muž se nejspíš nehýbal:", "spoutaný, držený, v bezvědomí, nebo už mrtvý.", "Forenzní specialisté v tom vidí spíš ponížení než boj."), LEAD, WHITE))

    def callout(x, name, head, rows):
        ax, ay = at(name)
        y = 440
        s = lines(x, y, (head,), HEAD, GOLD, weight=600) + lines(x, y + HEAD * 1.16 + 2, rows, LINE, WHITE)
        top = y + HEAD * 1.16 + (len(rows) - 1) * LINE * 1.24 + 18
        s += f'<line x1="{ax:.1f}" y1="{top:.1f}" x2="{ax:.1f}" y2="{ay:.1f}" stroke="{GOLD}" stroke-width="2"/><circle cx="{ax:.1f}" cy="{ay:.1f}" r="5" fill="{GOLD}"/>'
        return group(head, s)

    t += callout(M, "pravy", "Pravá strana", ("3 větší a 4 menší zepředu",))
    t += callout(at("levy")[0] - 30, "levy", "Levá strana", ("Nejméně 14 zezadu", "Čepel v největším z nich"))
    t += note(M, f"{SOURCE}: vpichy podle skenu pánve, zezadu zakreslené přes kost. Kosti: BodyParts3D, © 2008 Life Science Integrated Database Center, CC BY-SA 2.1 JP, obecný model, ne kosti oběti. 3D model, render v Blenderu, bez AI.", 94)
    mask = Image.new("L", (W, H), 0)
    mask.paste(pelvis.getchannel("A").resize((round(vw), round(vh))), (M, round(vy)))
    return page(group("Pánev", image_tag(pelvis, M, vy, vw, vh, "PNG")), t), mask


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    lib, out = Path(sys.argv[1]), Path(sys.argv[2])
    only = sys.argv[sys.argv.index("--jen") + 1].split(",") if "--jen" in sys.argv else ["1", "2", "3"]
    if "1" in only:
        write_poster(well(lib), out, "studna-1-kde", W, H, "Muž na dně studny", None, True)
    for n, build, stem, title in (("2", barrel, "studna-2-zatizeny", "Aby nevyplaval"), ("3", bones, "studna-3-vpichy", "Kam ho bodali")):
        if n in only:
            svg, mask = build(lib)
            hit = text_over(svg, W, H, mask, margin=20 if n == "3" else 0)
            if hit:
                print(f"{stem}: text u obrazu, oblast stránky {hit}")
            write_poster(svg, out, stem, W, H, title, None, n == "2")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
