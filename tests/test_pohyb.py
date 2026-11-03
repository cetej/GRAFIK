"""Předávka do POHYBu: vrstvy stránky, výběr série, balík a odeslání. POHYB tu nahrazuje malý HTTP server."""
from __future__ import annotations

import base64
import io
import json
import threading
import zipfile
from email.parser import BytesParser
from email.policy import default
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from PIL import Image

from engine.pohyb import split_layers
from tests.test_panels import api, doc, fields, settings, shot  # noqa: F401  (fixtures)


def png(size=(40, 60), color=(200, 120, 40, 255)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", size, color).save(buf, "PNG")
    return buf.getvalue()


def poster(title="Muž na dně studny") -> str:
    """Stejné vrstvy jako stránky série Studny (scripts/plakaty/sazba.py)."""
    data = base64.b64encode(png()).decode()
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="300" height="450" viewBox="0 0 300 450">'
            '<rect id="Pozadí" width="300" height="450" fill="#340d11"/>'
            f'<g id="Grafika"><g id="Studna"><image href="data:image/png;base64,{data}" x="20" y="100" width="40" height="60"/></g></g>'
            f'<g id="Texty"><g id="Titulek"><text x="10" y="40" font-size="30" fill="#dcb66e" font-weight="700">{title}</text></g>'
            '<g id="Tři sudy"><text x="150" y="120" font-size="16" fill="#dcb66e">Tři sudy</text><text x="150" y="140" font-size="14" fill="#f0e8da">nad sebou</text>'
            '<polyline points="40,110 40,110 140,110" fill="none" stroke="#dcb66e"/><circle cx="40" cy="110" r="5" fill="#dcb66e"/></g>'
            '<g id="Studny s kostmi"><circle cx="200" cy="300" r="5" fill="#e0322f"/><circle cx="220" cy="320" r="5" fill="#e0322f"/></g>'
            '<g id="Zdroj"><text x="10" y="440" font-size="10" fill="#b9a99a">Zdroj: Driessen 2026. Studna: Blender, bez AI.</text></g></g></svg>')


def test_layers_split_into_objects_labels_marks_and_a_picture_without_text():
    layers = split_layers(poster())
    assert layers["rozmer"] == [300, 450] and layers["pozadi"] == "#340d11"
    assert [o["id"] for o in layers["objekty"]] == ["Studna"]
    by_id = {t["id"]: t for t in layers["texty"]}
    assert by_id["Titulek"]["role"] == "titulek" and by_id["Zdroj"]["role"] == "zdroj"
    sudy = by_id["Tři sudy"]
    assert sudy["role"] == "popisek" and sudy["kotva"] == [40, 110] and sudy["voditko"][-1] == [140, 110]
    assert [r["text"] for r in sudy["radky"]] == ["Tři sudy", "nad sebou"] and sudy["radky"][0]["barva"] == "#dcb66e"
    assert by_id["Studny s kostmi"] == {"id": "Studny s kostmi", "role": "znacky", "barva": "#e0322f", "body": [[200, 300], [220, 320]]}
    assert "<text" not in layers["bez_textu"] and "Studna" in layers["bez_textu"]
    assert split_layers('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><text>x</text></svg>') is None


def test_panel_document_layers_take_the_anchor_from_its_leader_in_the_graphics():
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><g id="Grafika"><g id="Pozadí"><rect width="100" height="100" fill="#1d2532"/></g>'
           '<g id="Věž"><rect x="10" y="10" width="20" height="20"/></g>'
           '<g id="Vodítka Věž"><g id="Vodítko 57 metrů"><polyline points="20,20 50,20" fill="none"/><circle cx="20" cy="20" r="3"/></g></g></g>'
           '<g id="Texty"><g id="Popisky Věž"><g id="57 metrů"><text x="52" y="22">57 metrů</text></g></g></g></svg>')
    layers = split_layers(svg)
    assert layers["pozadi"] == "#1d2532" and [o["id"] for o in layers["objekty"]] == ["Věž"]
    assert layers["texty"] == [{"id": "57 metrů", "role": "popisek", "kotva": [20, 20], "voditko": [[20, 20], [50, 20]],
                                "radky": [{"text": "57 metrů", "x": 52, "y": 22, "velikost": 0, "barva": None, "rez": "400", "zarovnani": "start"}]}]
    assert "Vodítk" not in layers["bez_textu"] and "Pozadí" in layers["bez_textu"]


class FakePohyb:
    def __init__(self):
        self.received: list[bytes] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _json(self, code, body):
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                self._json(200, {"ok": True}) if self.path == "/api/health" else self._json(404, {"detail": "nic"})

            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                msg = BytesParser(policy=default).parsebytes(f"Content-Type: {self.headers['Content-Type']}\r\n\r\n".encode() + body)
                part = next(p for p in msg.iter_parts() if p.get_param("name", header="content-disposition") == "balik")
                outer.received.append(part.get_payload(decode=True))
                self._json(201, {"id": f"1103-120000-{len(outer.received):04d}", "url": "http://127.0.0.1:8340/#1103"})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()


@pytest.fixture
def pohyb(settings):
    fake = FakePohyb()
    settings.pohyb_url = fake.url
    yield fake
    fake.server.shutdown()


def upload_page(api, title, svg=None) -> str:
    body = {"b64": base64.b64encode(png((300, 450))).decode(), "name": f"{title}.png", "title": title, "blender_render": True}
    r = api.post("/api/v2/library/upload", json={**body, **({"svg": svg} if svg else {})})
    assert r.status_code == 201, r.text
    return r.json()["ref"]


def test_series_uploaded_together_is_preselected_in_its_own_order(api, pohyb):
    second = upload_page(api, "Aby nevyplaval (série, 2 ze 2)", poster("Aby nevyplaval"))
    first = upload_page(api, "Muž na dně studny (série, 1 ze 2)", poster())
    r = api.get(f"/api/v2/pohyb/stranky?obrazek={second}").json()
    assert r["vybrane"] == [{"obrazek": first}, {"obrazek": second}]
    assert {o["polozka"]["obrazek"] for o in r["nabidka"]} == {first, second} and r["pohyb_bezi"] is True
    assert api.get("/api/v2/pohyb/stranky?obrazek=neni/0").status_code == 404


def test_preview_counts_what_goes_and_writes_nothing(api, settings, pohyb):
    ref = upload_page(api, "Muž na dně studny", poster())
    plain = upload_page(api, "Bez vrstev")
    r = api.post("/api/v2/pohyb/nahled", json={"polozky": [{"obrazek": ref}, {"obrazek": plain}]})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["stranky"][0] == {"nazev": "Muž na dně studny", "vrstvy": True, "objekty": 1, "popisky": 1, "panely": 0, "modely": 0}
    assert p["stranky"][1]["vrstvy"] is False and p["format"] == "9:16"
    assert any("Bez vrstev" in n for n in p["upozorneni"]) and any("předlohy ani rešerši" in n for n in p["upozorneni"])
    assert not (settings.library_dir / "pohyb").exists()
    assert api.post("/api/v2/pohyb/nahled", json={"polozky": []}).status_code == 400


def test_send_builds_a_new_bundle_every_time_and_pohyb_gets_it_whole(api, settings, pohyb):
    ref = upload_page(api, "Muž na dně studny", poster())
    r = api.post("/api/v2/pohyb", json={"polozky": [{"obrazek": ref}], "sdeleni": "Kdo ho zabil", "format": "16:9"})
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["pohyb"]["id"] == "1103-120000-0001" and out["stranky"] == 1
    folder = settings.library_dir / "pohyb" / out["id"]
    assert json.loads((folder / "odeslano.json").read_text(encoding="utf-8"))["id"] == "1103-120000-0001"
    with zipfile.ZipFile(io.BytesIO(pohyb.received[0])) as z:
        names = set(z.namelist())
        manifest = json.loads(z.read("manifest.json"))
        assert manifest["format"] == "grafik-predavka" and manifest["verze"] == 1 and manifest["sdeleni"] == "Kdo ho zabil"
        assert manifest["format_videa"] == "16:9" and manifest["nazev"] == "Muž na dně studny"
        page = manifest["stranky"][0]
        for key in ("hotovo", "vrstvy", "bez_textu", "puvod"):
            assert page[key] in names, key
        obj = page["objekty"][0]
        assert obj["id"] == "Studna" and obj["soubor"] in names and obj["rect"] == [20, 100, 40, 60]
        assert page["hlavni"] == [20, 100, 40, 60] and page["pozadi"] == "#340d11"
        assert page["zdroje"].startswith("Zdroj: Driessen") and page["ai"].startswith("Model a render")
        assert Image.open(io.BytesIO(z.read(obj["soubor"]))).size == (40, 60)
        no_text = Image.open(io.BytesIO(z.read(page["bez_textu"]))).convert("RGB")
        assert no_text.getpixel((30, 130)) == (200, 120, 40) and no_text.getpixel((160, 115)) == (0x34, 0x0d, 0x11)   # obraz ano, popisek ne
        assert "odeslano.json" not in names
    again = api.post("/api/v2/pohyb", json={"polozky": [{"obrazek": ref}]}).json()
    assert again["id"] != out["id"] and (folder / "manifest.json").is_file() and len(pohyb.received) == 2
    assert api.post("/api/v2/pohyb", json={"polozky": [{"obrazek": ref}], "format": "21:9"}).status_code == 400


def test_pohyb_down_says_so_and_writes_nothing(api, settings):
    ref = upload_page(api, "Muž na dně studny", poster())
    settings.pohyb_url = "http://127.0.0.1:9"
    r = api.post("/api/v2/pohyb", json={"polozky": [{"obrazek": ref}]})
    assert r.status_code == 503 and "POHYB neběží" in r.json()["detail"]
    assert not (settings.library_dir / "pohyb").exists()


def test_panel_document_sends_its_panels_with_anchors(api, settings, doc, pohyb):
    pages = api.get(f"/api/v2/pohyb/stranky?infografika={doc['id']}").json()
    assert pages["vybrane"] == [{"infografika": doc["id"]}]
    r = api.post("/api/v2/pohyb", json={"polozky": pages["vybrane"]})
    assert r.status_code == 201, r.text
    with zipfile.ZipFile(io.BytesIO(pohyb.received[0])) as z:
        names = set(z.namelist())
        page = json.loads(z.read("manifest.json"))["stranky"][0]
        assert page["rozmer"] == [1600, 2400] and page["dokument"] in names and page["zdroje"] == "Wikipedie"
        hero = next(p for p in page["panely"] if p["id"] == "hlavni")
        assert hero["obraz"] in names and hero["body"] in names and hero["vrstvy"] == ["stranky/1/panely/hlavni/vrstva-zed.png"]
        assert page["hlavni"] == [0, 100, 800, 400]
        assert any(t["role"] == "popisek" and t["kotva"] for t in page["texty"])


def glb(nodes: list[dict]) -> bytes:
    """Nejmenší GLB: jen kus JSON s uzly, jako ho píše scripts/3d/tesla_stroje.py --glb."""
    text = json.dumps({"asset": {"version": "2.0"}, "nodes": nodes}).encode()
    text += b" " * (-len(text) % 4)
    return b"glTF" + (2).to_bytes(4, "little") + (20 + len(text)).to_bytes(4, "little") + len(text).to_bytes(4, "little") + b"JSON" + text


def model(settings, model_id: str, nodes: list[dict]) -> None:
    folder = settings.library_dir / "3d" / model_id / "v1"
    folder.mkdir(parents=True)
    (folder / "model.glb").write_bytes(glb(nodes))
    (folder / "model.json").write_text(json.dumps({"id": model_id, "version": "v1", "title": model_id, "method": "upload"}), encoding="utf-8")


def test_models_behind_panels_go_along_with_their_moving_parts(api, settings, pohyb):
    """Tesla 3. 11.: obraz tématu (`slozka`) ukazoval na model jen přes obrazy.json a předávka GLB vynechala."""
    rotor = {"name": "rotor", "translation": [0, 0, -0.06], "extras": {"cast": "rotor", "pohyb": "otaceni", "osa": [0, 0, -1], "popis": "Rotor"}}
    model(settings, "motor-test", [rotor, {"name": "kotva-rotor", "extras": {"kotva": "rotor"}}])
    model(settings, "civka-test", [{"name": "vyboje", "extras": {"cast": "vyboje", "pohyb": "vyboj"}}])
    (settings.library_dir / "3d" / "motor-test" / "v1" / "ref-front.png").write_bytes(b"front")     # čelní předloha: POHYB podle ní obarví síť
    shot(settings.library_dir / "tema" / "Q1" / "obrazy" / "motor", ["zed"])
    shot(settings.library_dir / "strely" / "detail")
    (settings.library_dir / "tema" / "Q1" / "obrazy.json").write_text(json.dumps({"obrazy": [
        {"id": "motor", "nazev": "Motor", "slozka": "tema/Q1/obrazy/motor", "model": {"model_id": "motor-test", "version": "v1"}}]}), encoding="utf-8")
    body = fields()
    body["panels"][0]["zdroj"] = {"slozka": "tema/Q1/obrazy/motor"}                                  # starý dokument: model jen v obrazy.json
    body["panels"][1]["zdroj"] = {"slozka": "strely/detail", "model_id": "civka-test", "version": "v1"}     # nový dokument: model ve zdroji
    doc = api.post("/api/v2/infographics/panels", json=body).json()
    item = {"polozky": [{"infografika": doc["id"]}]}
    assert api.post("/api/v2/pohyb/nahled", json=item).json()["stranky"][0]["modely"] == 2
    r = api.post("/api/v2/pohyb", json=item)
    assert r.status_code == 201, r.text
    with zipfile.ZipFile(io.BytesIO(pohyb.received[0])) as z:
        names = set(z.namelist())
        found = {p["id"]: p for p in json.loads(z.read("manifest.json"))["stranky"][0]["panely"]}
        hero, detail = found["hlavni"], found["detail"]
        assert hero["model"] == "stranky/1/modely/hlavni.glb" and hero["model"] in names and hero["model_id"] == "motor-test"
        assert hero["casti"] == [{"uzel": "rotor", "stred": [0, 0, -0.06], "cast": "rotor", "pohyb": "otaceni", "osa": [0, 0, -1], "popis": "Rotor"}]
        assert z.read(hero["model"]) == (settings.library_dir / "3d" / "motor-test" / "v1" / "model.glb").read_bytes()
        assert detail["model_id"] == "civka-test" and detail["casti"][0]["pohyb"] == "vyboj" and detail["model"] in names
        assert "stranky/1/modely/hlavni.json" in names
        assert hero["predloha"] == "stranky/1/modely/hlavni.ref-front.png" and z.read(hero["predloha"]) == b"front"
        assert "predloha" not in detail


def test_picture_without_a_model_or_with_a_missing_one_goes_without_glb(api, settings, doc, pohyb):
    (settings.library_dir / "strely" / "obrazy.json").write_text(json.dumps({"obrazy": [
        {"id": "hlavni", "nazev": "Věž", "slozka": "strely/hlavni", "model": {"model_id": "smazany", "version": "v1"}}]}), encoding="utf-8")
    r = api.post("/api/v2/pohyb", json={"polozky": [{"infografika": doc["id"]}]})
    assert r.status_code == 201, r.text
    with zipfile.ZipFile(io.BytesIO(pohyb.received[0])) as z:
        assert not any(n.endswith(".glb") for n in z.namelist())
        assert all("model" not in p for p in json.loads(z.read("manifest.json"))["stranky"][0]["panely"])
