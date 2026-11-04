"""Předělat ilustraci na formát (GRAFIK#150): ořez podle objektu zdarma, rozšíření placené; nejistý objekt = None (GRAFIK#68)."""
import json
from base64 import b64encode
from io import BytesIO

from PIL import Image, ImageDraw

from engine import image_format
from tests.test_engine_v2 import api, sd, settings  # noqa: F401  (fixtures)


def _scene(w=1200, h=800, at=(560, 340), size=160) -> Image.Image:
    im = Image.new("RGB", (w, h), (90, 110, 130))
    ImageDraw.Draw(im).ellipse([at[0], at[1], at[0] + size, at[1] + size], fill=(250, 200, 40))
    return im


def _upload(api, im: Image.Image, title="ilustrace") -> str:
    buf = BytesIO()
    im.save(buf, "PNG")
    r = api.post("/api/v2/library/upload", json={"b64": b64encode(buf.getvalue()).decode(), "name": f"{title}.png", "title": title})
    assert r.status_code == 201, r.text
    return r.json()["ref"]


def test_subject_in_the_middle_is_found_in_0_1000():
    box = image_format.find_subject(_scene())          # kruh leží na 425–625 (výška) a 467–600 (šířka)
    assert box is not None
    t, l, b, r = box
    assert 370 <= t <= 425 and 420 <= l <= 467 and 625 <= b <= 680 and 600 <= r <= 650


def test_plain_or_off_centre_picture_gives_none_not_a_made_up_box():
    assert image_format.find_subject(Image.new("RGB", (800, 600), (90, 110, 130))) is None
    assert image_format.find_subject(_scene(at=(40, 40))) is None


def test_crop_follows_the_subject_and_says_when_it_would_cut_it():
    small = image_format.plan(1200, 800, 4 / 5, [400, 700, 600, 800])         # objekt vpravo, vejde se
    t, l, b, r = small["crop"]
    assert (t, b) == (0, 1000) and l < 700 and r > 800 and not small["cuts_subject"]
    wide = image_format.plan(1200, 800, 4 / 5, [100, 50, 900, 950])           # přes celou šířku
    assert wide["cuts_subject"]
    assert wide["expand"]["canvas"][0] / wide["expand"]["canvas"][1] == 1200 / 1500
    assert image_format.plan(1200, 800, 3 / 2, None)["expand"] is None        # poměr už sedí


def test_crop_is_a_new_picture_and_the_original_stays(api, settings):
    ref = _upload(api, _scene())
    src = settings.library_dir.glob("*/" + ref.split("/")[0] + "/image-0.png").__next__().read_bytes()
    url = "/api/v2/jobs/" + ref.replace("/", "/images/") + "/format"
    preview = api.post(url + "/nahled", json={"size": "1:1"}).json()
    assert preview["subject_from"] == "saliency" and not preview["cuts_subject"] and preview["expand_usd"] == 0.04
    r = api.post(url, json={"size": "1:1"})
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["method"] == "orez" and out["usd"] == 0 and out["size"] == [800, 800]
    prov = api.get("/api/v2/jobs/" + out["ref"].replace("/", "/images/") + "/provenance").json()
    assert prov["format_of"] == ref and prov["format"]["method"] == "orez"
    assert settings.library_dir.glob("*/" + ref.split("/")[0] + "/image-0.png").__next__().read_bytes() == src


def test_operator_box_wins_over_saliency(api):
    ref = _upload(api, _scene())
    url = "/api/v2/jobs/" + ref.replace("/", "/images/") + "/format/nahled"
    p = api.post(url, json={"size": "1:2", "objekt": [400, 0, 600, 100]}).json()
    assert p["subject_from"] == "operator" and p["crop"][1] == 0
    assert api.post(url, json={"size": "1:2", "objekt": [600, 0, 400, 100]}).status_code == 422
    assert api.post(url, json={"size": "široký"}).status_code == 400


def test_expand_is_paid_asks_first_and_keeps_the_original_pixels(api, settings, monkeypatch):
    ref = _upload(api, _scene())
    url = "/api/v2/jobs/" + ref.replace("/", "/images/") + "/format"
    r = api.post(url, json={"size": "4:5", "zpusob": "rozsirit"})
    assert r.status_code == 402 and r.json()["estimate_usd"] == 0.04
    calls = []

    def fake_fal(png, arguments):
        calls.append(arguments)
        buf = BytesIO()
        Image.new("RGB", tuple(arguments["canvas_size"]), (0, 0, 0)).save(buf, "PNG")
        return buf.getvalue()

    monkeypatch.setattr(image_format, "fal_expand", fake_fal)
    r = api.post(url, json={"size": "4:5", "zpusob": "rozsirit", "confirm_cost": True})
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["method"] == "rozsirit" and out["usd"] == 0.04 and out["size"] == [1200, 1500] and len(calls) == 1
    path = next(settings.library_dir.glob("*/" + out["ref"].split("/")[0] + "/image-0.png"))
    with Image.open(path) as im:
        assert im.getpixel((10, 350 + 10)) == (90, 110, 130)       # originál vrácený na místo
        assert im.getpixel((10, 10)) == (0, 0, 0)                  # dogenerovaný okraj
    prov = api.get("/api/v2/jobs/" + out["ref"].replace("/", "/images/") + "/provenance").json()
    assert prov["ai_generated"] is True and prov["format"]["expand_backend"] == "fal:fal-ai/bria/expand"
    costs = [json.loads(x) for x in settings.costs_path.read_text(encoding="utf-8").splitlines()]
    assert costs[-1]["usd"] == 0.04 and costs[-1]["job_id"] == out["ref"].split("/")[0]
