# Czech copy of the operator's sample poster of the axolotl: its layout (1500 x 2000 px), the animal from a 3D model given its look by local FLUX.
#   python scripts/plakaty/axolotl_kopie.py ASSETS OUT_DIR [--knihovna http://127.0.0.1:8300]
# ASSETS: plate.png (the sample's page without the animal, local FLUX), scene.png (1536 x 992, the page from y 370 to 1340 with the animal: its 3D model's render through FLUX
# as `geometry`, cut out and put on the plate, then one more FLUX pass over the whole scene, so that the animal sits in the wash and does not lie on top of it).
# Words of the plate are painted out and set again as vector text; wrong details of the sample are corrected, facts: docs/spikes/2026-11-01-plakaty-osoba-zvire.md.
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sazba import group, image_tag, leader, text, wrap, write_poster  # noqa: E402

W, H = 1500, 2000
SERIF = "'Palatino Linotype', 'Book Antiqua', Georgia, serif"
GREEN, INK, MUTED, PAPER_TEXT = "#3f7259", "#23261f", "#4d5a50", "#f2efe3"
NB = " "
# rectangles of generated words on the plate, in page pixels (x0, y0, x1, y1)
WIPE = [(70, 1656, 455, 1830), (200, 1582, 470, 1622), (505, 1582, 720, 1622), (1205, 1700, 1290, 1795), (1290, 1700, 1425, 1762), (30, 1852, 1180, 1990), (1180, 1885, 1490, 1990),
        (205, 655, 555, 675), (1208, 658, 1282, 678), (365, 1322, 415, 1348)]
# the rest of the plate's leaders ends on the paper under the wash: a feathered patch of paper, inpainting would drag the wash along
PAPER_PATCH = (1050, 1205, 1195, 1345)
# thin leader lines the plate kept from the sample: (x0, y0, x1, y1)
WIPE_LINES = [(1012, 410, 950, 412), (950, 412, 850, 500), (372, 1378, 505, 1232)]
LENS = {"zabry": (574, 1690, 60), "noha": (721, 1690, 60), "oko": (876, 1690, 60), "hlava": (1032, 1690, 60)}
SCENE = (0, 370, 1500, 1340)
# crops of the animal for the round details: centre on the page and half width
CROPS = {"zabry": (687, 751, 133), "noha": (687, 1131, 86), "oko": (938, 829, 47), "hlava": (956, 829, 180)}


def page(assets: Path) -> Image.Image:
    plate = cv2.imread(str(assets / "plate.png"))
    plate = cv2.resize(plate, (W, H), interpolation=cv2.INTER_LANCZOS4).astype(np.float32)
    x0, y0, x1, y1 = SCENE
    scene = cv2.resize(cv2.imread(str(assets / "scene.png")), (x1 - x0, y1 - y0), interpolation=cv2.INTER_LANCZOS4).astype(np.float32)
    # the same paper on both, the scene melts into the plate at its top and bottom
    scene *= np.median(plate[y0 + 4:y0 + 30, 400:500].reshape(-1, 3), axis=0) / np.median(scene[4:30, 400:500].reshape(-1, 3), axis=0)
    # FLUX warms the animal: the sample's skin is pale cream and its gills a pale rose
    hsv = cv2.cvtColor(np.clip(scene, 0, 255).astype(np.uint8), cv2.COLOR_BGR2HSV).astype(np.float32)
    skin = (hsv[..., 0] >= 6) & (hsv[..., 0] < 24) & (hsv[..., 1] > 45)   # the paper has the same hue, only paler
    gills = (hsv[..., 0] >= 165) | (hsv[..., 0] < 6)
    keep = np.where(skin, 0.6, np.where(gills, 0.72, 1.0)).astype(np.float32)
    hsv[..., 1] *= cv2.GaussianBlur(keep, (0, 0), 1.2)
    hsv[..., 2] = np.minimum(hsv[..., 2] * cv2.GaussianBlur(np.where(skin | gills, 1.04, 1.0).astype(np.float32), (0, 0), 1.2), 255)
    scene = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR).astype(np.float32)
    edge = np.minimum(np.arange(y1 - y0), np.arange(y1 - y0)[::-1])
    fade = np.clip(edge / 36.0, 0, 1)[:, None, None]
    plate[y0:y1, x0:x1] = plate[y0:y1, x0:x1] * (1 - fade) + scene * fade
    plate = np.clip(plate, 0, 255).astype(np.uint8)
    mask = np.zeros((H, W), np.uint8)
    for x0, y0, x1, y1 in WIPE:
        mask[y0:y1, x0:x1] = 255
    for x0, y0, x1, y1 in WIPE_LINES:
        cv2.line(mask, (x0, y0), (x1, y1), 255, 17)
    clean = cv2.inpaint(plate, mask, 9, cv2.INPAINT_TELEA)
    # the paper of the sample is cream, the generated plate leans to pink
    rgb = cv2.cvtColor(clean, cv2.COLOR_BGR2RGB).astype(np.float32)
    corner = np.median(rgb[1000:1060, 20:50].reshape(-1, 3), axis=0)
    rgb *= np.array((235.0, 228.0, 209.0)) / corner
    x0, y0, x1, y1 = PAPER_PATCH
    patch = np.zeros((H, W), dtype=np.float32)
    patch[y0:y1, x0:x1] = 1
    patch = cv2.GaussianBlur(patch, (0, 0), 16)[..., None]
    rgb = rgb * (1 - patch) + np.array((235.0, 228.0, 209.0)) * patch
    im = Image.fromarray(np.clip(rgb, 0, 255).astype("uint8"), "RGB")
    return im.filter(ImageFilter.UnsharpMask(2, 60, 2))


def para(x, y, s, size, fill, n, leading=1.28, weight=400, anchor="start", italic=False) -> str:
    return "".join(text(x, y + i * size * leading, line, size, fill, weight, anchor, italic=italic) for i, line in enumerate(wrap(s, n)))


def lens(src: Image.Image, name: str) -> str:
    cx, cy, r = LENS[name]
    sx, sy, half = CROPS[name]
    crop = src.crop((sx - half, sy - half, sx + half, sy + half)).convert("RGB").resize((r * 4, r * 4), Image.LANCZOS)
    mask = Image.new("L", crop.size, 0)
    ImageDraw.Draw(mask).ellipse((2, 2, crop.width - 3, crop.height - 3), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(1))
    crop.putalpha(mask)
    return image_tag(crop, cx - r, cy - r, 2 * r, 2 * r, "PNG") + f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{GREEN}" stroke-width="2.4"/>'


def poster(assets: Path) -> str:
    src = page(assets)
    gfx, txt = [group("Obraz podle vzoru", image_tag(src, 0, 0, W, H, "JPEG"))], []
    # leaders go to the real places on this animal
    leads = "".join(leader(a, b, INK, 1.5, 3.4) for a, b in (((743, 608), (600, 398)), ((988, 766), (1032, 398)), ((576, 734), (212, 667)), ((1194, 1067), (1276, 668))))
    gfx.append(group("Vodítka", leads))
    gfx.append(group("Detaily", "".join(lens(src, n) for n in LENS)))

    txt.append(group("Neotenie", text(232, 405, "Neotenie", 38, GREEN, 700) + para(232, 446, "Pohlavně dospívá bez přeměny. Zůstává ve vodě a drží si vnější žábry.", 22, INK, 30)))
    txt.append(group("Laboratorní model", text(1188, 405, "V laboratoři", 38, GREEN, 700) + para(1188, 446, f"Doroste končetina, ocas, mícha, srdce i sítnice. Čočka ne.", 22, INK, 25)))
    txt.append(group("Žábry", text(38, 758, "Vnější žábry", 38, GREEN, 700) + para(38, 796, "3 páry stvolů s vlákny", 22, INK, 22)))
    txt.append(group("Regenerace", text(1262, 758, "Regenerace", 38, GREEN, 700) + para(1262, 796, f"Končetina mláděte: 98{NB}% za 66 dní", 22, INK, 18)))
    txt.append(group("Xochimilco", text(150, 1386, "Xochimilco", 38, GREEN, 700)
                     + para(52, 1424, f"Dnes hlavně kanály Xochimilka a jezero Chalco. Růst Mexico City vzal většinu stanovišť. Růžová barva je známá jen z chovů.", 21, INK, 36)))
    txt.append(group("Stav druhu", text(1176, 1322, "Stav druhu", 38, GREEN, 700)
                     + para(1176, 1362, f"Volně žije 50 až 1{NB}000 dospělých. IUCN: kriticky ohrožený, CITES příloha{NB}II.", 22, INK, 25)))
    txt.append(group("Karta druhu", text(205, 1610, "KARTA DRUHU", 30, GREEN, 700) + text(515, 1610, "DETAILY", 30, GREEN, 700)
                     + text(78, 1690, "Ambystoma mexicanum", 27, INK, 400, italic=True) + f'<line x1="78" y1="1708" x2="448" y2="1708" stroke="{GREEN}" stroke-width="1.4"/>'
                     + text(78, 1746, f"volně 50–1{NB}000 dospělých", 25, INK) + f'<line x1="78" y1="1764" x2="448" y2="1764" stroke="{GREEN}" stroke-width="1.4"/>'
                     + text(78, 1802, "IUCN: kriticky ohrožený", 25, INK)))
    words = ""
    for (x, y, _r), (a, b) in zip(LENS.values(), (("vnější", "žábry"), ("4 prsty,", "vzadu 5"), ("oči", "bez víček"), ("zůstává", "larvou"))):
        words += text(x, y + 88, a, 21, INK, 400, "middle") + text(x, y + 113, b, 21, INK, 400, "middle")
    txt.append(group("Popisky detailů", words))
    txt.append(group("Razítko", text(1319, 1748, "Xochimilco", 34, PAPER_TEXT, 700, "middle")))
    txt.append(group("Patička", para(52, 1918, "Zdroje: IUCN Red List 2020-3; Voss a kol. 2015; Monaghan a kol. 2014; Joven a kol. 2019; Crowner a kol. 2019. Podle cizího vzoru, detaily opravené podle zdrojů. "
                                     "Axolotl: 3D model Hunyuan, vzhled lokální FLUX (AI). Podklad stránky: lokální FLUX (AI).", 19, MUTED, 152, 1.3, italic=True)))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{SERIF}">'
            f'<g id="Grafika">{"".join(gfx)}</g><g id="Texty">{"".join(txt)}</g></svg>')


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    assets, out = Path(sys.argv[1]), Path(sys.argv[2])
    knihovna = sys.argv[sys.argv.index("--knihovna") + 1] if "--knihovna" in sys.argv else None
    write_poster(poster(assets), out, "axolotl-kopie", W, H, "Axolotl: infografika podle vzoru, zvíře z 3D modelu", knihovna, ai=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
