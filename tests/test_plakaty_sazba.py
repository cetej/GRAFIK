"""Text přes postavu: „Proč jde text přes Teslův obličej“ (1. 11.). Postava je obrázek, kolizi poznal jen operátor.
Sazba a přijatý soubor: „To natěsnání popisků je ohavné“ (2. 11.), `--knihovna` skládal přijatou stránku znovu."""
import base64
import json
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "plakaty"))
import sazba  # noqa: E402
from sazba import check_layout, group, text, text_over, upload_poster, vectorcraft_copy  # noqa: E402

W, H = 400, 300


def _page(x: int, y: int, fill: str = "#ffffff") -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}"><g id="Grafika"><rect width="{W}" height="{H}" fill="#f4efe2"/>'
            f'<rect x="150" y="100" width="100" height="100" fill="#5a4632"/></g><g id="Texty">{text(x, y, "Šachta 37 m", 20, fill)}</g></svg>')


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


def test_text_close_to_the_figure_needs_a_margin():
    page = _page(36, 150, "#000000")     # the text ends just before the figure; white would not show on the paper
    assert text_over(page, W, H, _mask()) is None
    assert text_over(page, W, H, _mask(), margin=30) is not None


def test_a_leader_may_touch_the_figure():
    page = _page(20, 40).replace('</g></svg>', '<line x1="100" y1="40" x2="200" y2="150" stroke="#ffffff" stroke-width="4"/></g></svg>')
    assert text_over(page, W, H, _mask(), margin=30) is None


def _labels(*items) -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}">' + "".join(items) + "</svg>"


def test_check_layout_finds_text_over_text():
    found = check_layout(_labels(group("A", text(20, 100, "První popisek", 20, "#000")), group("B", text(40, 104, "Druhý popisek", 20, "#000"))))
    assert len(found) == 1 and found[0].startswith("přes sebe")


def test_check_layout_finds_text_off_the_page():
    assert check_layout(_labels(text(390, 100, "Moc daleko vpravo", 20, "#000")))[0].startswith("mimo stránku")


def test_check_layout_finds_two_labels_reading_as_one_line():
    near = _labels(group("A", text(20, 100, "Levý", 20, "#000")), group("B", text(85, 104, "Pravý", 20, "#000")))
    assert check_layout(near)[0].startswith("čte se jako jeden řádek")
    assert check_layout(near, gap=10) == []


def test_check_layout_leaves_a_heading_and_its_line_in_one_group_alone():
    assert check_layout(_labels(group("A", text(20, 100, "Nadpis", 20, "#000") + text(100, 100, "a řádek", 20, "#000")))) == []


def test_check_layout_finds_text_too_small_on_a_phone():
    # „velké plachty, kde hrozí titěrné písmo“ (2. 11.): stránka 1800 px, písmo 26 px = 5,2 px na telefonu
    page = lambda size, name="A": ('<svg xmlns="http://www.w3.org/2000/svg" width="1800" height="2400" viewBox="0 0 1800 2400"><g id="Texty">'
                                   + group(name, text(40, 200, "Kosti nejméně 20 lidí", size, "#000")) + "</g></svg>")
    assert check_layout(page(26)) == ["na mobilu (šířka 360 px): 1 z 1 textů je pod 12 px, nejmenší 5.2 px „Kosti nejméně 20 lidí“. Větší písmo, méně textu, nebo víc menších stránek."]
    assert check_layout(page(60)) == []
    assert check_layout(page(45, "Zdroj")) == []     # zdroj a patička smějí být menší
    assert check_layout(page(44, "Zdroj")) != []


def test_vectorcraft_copy_is_new_only_when_the_page_changed(tmp_path):
    first = vectorcraft_copy(tmp_path, "x", _page(20, 40))
    older = first.with_name("x-vectorcraft-20000101-000000.svg")
    first.rename(older)
    assert vectorcraft_copy(tmp_path, "x", _page(20, 40)) is None
    assert vectorcraft_copy(tmp_path, "x", _page(30, 40)) is not None
    assert older.exists()


def test_upload_sends_the_files_as_they_are(tmp_path, monkeypatch):
    png = tmp_path / "x.png"
    png.write_bytes(b"prijaty soubor")
    png.with_suffix(".svg").write_text("<svg/>", encoding="utf-8")
    sent = {}

    class Reply:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b'{"job_id":"j"}'

    def urlopen(req, timeout):
        sent.update(url=req.full_url, body=json.loads(req.data))
        return Reply()

    monkeypatch.setattr(sazba.urllib.request, "urlopen", urlopen)
    assert upload_poster(png, "Název", "http://engine", ai=True) == '{"job_id":"j"}'
    assert sent["url"] == "http://engine/api/v2/library/upload"
    assert base64.b64decode(sent["body"]["b64"]) == b"prijaty soubor"
    assert sent["body"]["svg"] == "<svg/>" and sent["body"]["title"] == "Název" and sent["body"]["blender_render"] is False
    assert png.read_bytes() == b"prijaty soubor"
