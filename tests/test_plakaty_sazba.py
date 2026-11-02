"""Text přes postavu: „Proč jde text přes Teslův obličej“ (1. 11.). Postava je obrázek, kolizi poznal jen operátor."""
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "plakaty"))
from sazba import text, text_over  # noqa: E402

W, H = 400, 300


def _page(x: int, y: int) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}"><g id="Grafika"><rect width="{W}" height="{H}" fill="#f4efe2"/>'
            f'<rect x="150" y="100" width="100" height="100" fill="#5a4632"/></g><g id="Texty">{text(x, y, "Šachta 37 m", 20, "#ffffff")}</g></svg>')


def _mask() -> Image.Image:
    mask = Image.new("L", (W, H), 0)
    mask.paste(255, (150, 100, 250, 200))
    return mask


def test_text_on_the_figure_is_found():
    hit = text_over(_page(160, 150), W, H, _mask())
    assert hit is not None
    assert 150 <= hit[0] < hit[2] <= 250 and 100 <= hit[1] < hit[3] <= 200


def test_text_beside_the_figure_passes():
    assert text_over(_page(20, 40), W, H, _mask()) is None
