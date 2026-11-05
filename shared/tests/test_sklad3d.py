import hashlib
import json
import struct

import pytest

from ngm_shared import sklad, sklad3d
from ngm_shared.sklad import SkladError

BIN = bytes(range(40))
JPG = b"\xff\xd8jpegdata"
GLTF = {"asset": {"version": "2.0"}, "buffers": [{"uri": "a.bin", "byteLength": 40}],
        "bufferViews": [{"buffer": 0, "byteOffset": 8, "byteLength": 12}],
        "images": [{"uri": "textures/a_diff_1k.jpg"}], "meshes": []}


def rozbal_glb(glb: bytes) -> tuple[dict, bytes]:
    magic, ver, delka = struct.unpack_from("<4sII", glb)
    assert (magic, ver, delka) == (b"glTF", 2, len(glb))
    jl, jt = struct.unpack_from("<II", glb, 12)
    assert jt == 0x4E4F534A
    doc = json.loads(glb[20:20 + jl])
    bl, bt = struct.unpack_from("<II", glb, 20 + jl)
    assert bt == 0x004E4942
    return doc, glb[28 + jl:28 + jl + bl]


def test_gltf_na_glb_slozi_buffer_a_obrazek():
    glb = sklad3d.gltf_na_glb(json.dumps(GLTF).encode(), {"a.bin": BIN, "textures/a_diff_1k.jpg": JPG})
    doc, blob = rozbal_glb(glb)
    assert doc["buffers"] == [{"byteLength": len(blob)}]
    bv = doc["bufferViews"][0]
    assert blob[bv["byteOffset"]:bv["byteOffset"] + bv["byteLength"]] == BIN[8:20]
    img = doc["images"][0]
    assert "uri" not in img and img["mimeType"] == "image/jpeg"
    ib = doc["bufferViews"][img["bufferView"]]
    assert blob[ib["byteOffset"]:ib["byteOffset"] + ib["byteLength"]] == JPG
    assert ib["byteOffset"] % 4 == 0 and len(glb) % 4 == 0


def test_gltf_na_glb_chybejici_soubor():
    with pytest.raises(SkladError, match="chybí"):
        sklad3d.gltf_na_glb(json.dumps(GLTF).encode(), {"a.bin": BIN})


@pytest.mark.parametrize("label,ok", [("CC0", True), ("CC Attribution", True), ("CC BY 4.0", True),
                                      ("CC Attribution-NonCommercial", False), ("CC BY-SA", False),
                                      ("CC BY-ND", False), ("", False)])
def test_licence(label, ok):
    assert sklad3d.licence_ok(label)[0] is ok


def test_uloz_model_odmitne_nc_a_neplatne_id():
    with pytest.raises(SkladError, match="NC"):
        sklad3d.uloz_model("smithsonian", "x", b"glTF", {"licence": "CC BY-NC"})
    with pytest.raises(SkladError, match="neplatný"):
        sklad3d.uloz_model("smithsonian", "../ven", b"glTF", {"licence": "CC0"})
    with pytest.raises(SkladError, match="neplatný"):
        sklad3d.uloz_model("polyhaven", "x", b"glTF", {"licence": "CC0"})


def test_index_a_hledani():
    sklad3d.uloz_model("smithsonian", "mamut", b"glTF1", {"nazev": "Woolly Mammoth", "licence": "CC0",
                                                          "autor": "Smithsonian", "tagy": ["fossil"]})
    sklad3d.uloz_model("smithsonian", "lebka", b"glTF2", {"nazev": "Skull", "licence": "CC0",
                                                          "popis": "mammoth skull fragment"})
    index = sklad3d.sestav_index()
    assert {z["id"] for z in index} == {"smithsonian/mamut", "smithsonian/lebka"}
    vysl = sklad3d.hledej("mammoth")
    assert [z["id"] for z in vysl] == ["smithsonian/mamut", "smithsonian/lebka"]  # název váží víc než popis
    assert sklad3d.hledej("mamm", druh="hdri") == []
    assert sklad3d.hledej("mammoth", bez_zdroje=("smithsonian",)) == []
    z = sklad3d.zaznam("smithsonian/mamut")
    assert sklad3d.cesta(z).read_bytes() == b"glTF1"
    with pytest.raises(SkladError):
        sklad3d.zaznam("smithsonian/nic")


def test_uloz_nas_kopie_bez_prepisu(tmp_path):
    vdir = tmp_path / "library" / "amfora" / "v2"
    (vdir / "views").mkdir(parents=True)
    (vdir / "model.glb").write_bytes(b"glTFpuvodni")
    (vdir / "views" / "front.png").write_bytes(b"png")
    meta = {"id": "amfora", "version": "v2", "title": "Amfora", "review": {"by": "operátor"}}
    z = sklad3d.uloz_nas(vdir, meta)
    cil = sklad.root() / "3d" / "nase" / "amfora" / "v2"
    assert (cil / "model.glb").read_bytes() == b"glTFpuvodni"
    assert z["nahled"] == "3d/nase/amfora/v2/views/front.png"
    assert z["grafik"] == {"model_id": "amfora", "verze": "v2", "zkontroloval": "operátor"}
    (vdir / "model.glb").write_bytes(b"glTFzmeneny")
    sklad3d.uloz_nas(vdir, meta)
    assert (cil / "model.glb").read_bytes() == b"glTFpuvodni"
    assert [x["id"] for x in sklad3d.nacti_index()] == ["nase/amfora/v2"]


def test_uloz_nas_bez_glb(tmp_path):
    (tmp_path / "v1").mkdir()
    with pytest.raises(SkladError, match="model.glb"):
        sklad3d.uloz_nas(tmp_path / "v1", {"id": "x", "version": "v1"})


def test_stahni_polyhaven_opakovatelne(monkeypatch):
    gltf = json.dumps(GLTF).encode()
    assets = {"Chair_01": {"name": "Chair 01", "categories": ["furniture"], "tags": ["chair"], "authors": {"A B": "All"},
                           "dimensions": [500, 400, 900], "polycount": 10, "files_hash": "h1",
                           "thumbnail_url": "https://t/chair.webp"}}
    files = {"gltf": {"1k": {"gltf": {"url": "https://x/c.gltf", "include": {
        "a.bin": {"url": "https://x/a.bin", "md5": hashlib.md5(BIN).hexdigest()},
        "textures/a_diff_1k.jpg": {"url": "https://x/a.jpg", "md5": hashlib.md5(JPG).hexdigest()}}}}}}
    odpovedi = {"https://api.polyhaven.com/assets?t=models": json.dumps(assets).encode(),
                "https://api.polyhaven.com/files/Chair_01": json.dumps(files).encode(),
                "https://x/c.gltf": gltf, "https://x/a.bin": BIN, "https://x/a.jpg": JPG, "https://t/chair.webp": b"webp"}
    volani = []

    def get(url):
        volani.append(url)
        return odpovedi[url]

    monkeypatch.setattr(sklad3d, "_get", get)
    stav = sklad3d.stahni_polyhaven("model", log=lambda s: None)
    assert stav["novych"] == 1 and stav["chyb"] == 0
    z = sklad3d.zaznam("polyhaven/Chair_01")
    assert z["licence"] == "CC0" and z["autor"] == "A B" and z["rozmery_m"] == [0.5, 0.4, 0.9]
    rozbal_glb(sklad3d.cesta(z).read_bytes())
    assert sklad3d.cesta(z, "nahled").read_bytes() == b"webp"

    volani.clear()
    stav = sklad3d.stahni_polyhaven("model", log=lambda s: None)
    assert stav["beze_zmeny"] == 1 and volani == ["https://api.polyhaven.com/assets?t=models"]


def test_stahni_polyhaven_spatne_md5(monkeypatch):
    assets = {"X": {"name": "X", "files_hash": "h"}}
    files = {"gltf": {"1k": {"gltf": {"url": "https://x/c.gltf", "include": {"a.bin": {"url": "https://x/a.bin", "md5": "0"}}}}}}
    odpovedi = {"https://api.polyhaven.com/assets?t=models": json.dumps(assets).encode(),
                "https://api.polyhaven.com/files/X": json.dumps(files).encode(), "https://x/a.bin": BIN}
    monkeypatch.setattr(sklad3d, "_get", lambda u: odpovedi[u])
    stav = sklad3d.stahni_polyhaven("model", log=lambda s: None)
    assert stav["chyb"] == 1 and stav["v_indexu"] == 0
