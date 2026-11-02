# The check that was missing: the render with the man next to and over the book's section fig. 2.1, at the same scale (both 250 px/m after scaling).
#   python scripts/plakaty/velsen_srovnani.py LIB RENDER_DIR OUT.png
import json
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from velsen_studna_stranka import compose  # noqa: E402


def main() -> int:
    lib, name, out = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
    book = Image.open(lib / "podklady/studna.png").convert("RGB")
    raw, _, _ = compose(lib, name)
    # the frame of the render is fig. 2.1's height; its width is centred on the shaft
    k = book.height / raw.height
    model = raw.resize((round(raw.width * k), book.height), Image.LANCZOS)
    x = round(312 - model.width / 2)
    canvas = Image.new("RGBA", book.size, (52, 13, 17, 255))
    canvas.alpha_composite(model, (max(x, 0), 0), (max(-x, 0), 0))
    over = Image.blend(book.convert("RGBA"), canvas, 0.5).convert("RGB")
    w = book.width
    sheet = Image.new("RGB", (w * 3 + 40, book.height), (20, 20, 20))
    sheet.paste(book, (0, 0))
    sheet.paste(canvas.convert("RGB"), (w + 20, 0))
    sheet.paste(over, (2 * w + 40, 0))
    sheet.save(out)
    print(sheet.size, json.dumps({"kresba": book.size, "model": model.size}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
