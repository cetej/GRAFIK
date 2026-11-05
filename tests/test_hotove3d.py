"""Hotové 3D modely: licence a odpovědi Smithsonianu a Sketchfabu bez sítě (podvržené `_get`)."""
import json

import pytest

from engine import hotove3d as h

PKG = "341c96cd-f967-4540-8ed1-d3fc56d31f12"
GLB = b"glTF" + b"\x02\x00\x00\x00" + b"\x00" * 16


def resp(url, data=None, content=b""):
    return json.dumps(data).encode() if data is not None else content


def si_rows(*qualities):
    return {"rows": [{"title": "Mammuthus primigenius (Blumbach)", "content": {
        "model_url": f"3d_package:{PKG}", "file_type": "glb", "quality": q,
        "uri": f"https://3d-api.si.edu/content/document/3d_package:{PKG}/mammoth-{q.lower()}.glb"}} for q in qualities]}


def si_oa(access):
    return {"response": {"rows": [{"title": "Mammuthus primigenius (Blumbach)", "unitCode": "NMNHPALEO", "content": {
        "descriptiveNonRepeating": {"data_source": "NMNH - Paleobiology Dept.", "record_link": "http://n2t.net/ark:/65665/x",
                                    "online_media": {"media": [{"id": "3d_package:other", "usage": {"access": "CC0"}},
                                                               {"id": f"3d_package:{PKG}", "usage": {"access": access}}]}}}}]}}


def sf_row(label, uid="abc"):
    return {"uid": uid, "name": "Colosseum, Rome, Italy", "user": {"displayName": "CMBC"}, "license": {"label": label},
            "viewerUrl": f"https://sketchfab.com/3d-models/{uid}", "faceCount": 400000,
            "thumbnails": {"images": [{"url": "s.jpg", "width": 100}, {"url": "m.jpg", "width": 256}, {"url": "l.jpg", "width": 1024}]}}


@pytest.mark.parametrize("label, ok", [
    ("CC0 Public Domain", True), ("CC Attribution", True), ("CC Attribution-ShareAlike", False),
    ("CC Attribution-NonCommercial", False), ("CC Attribution-NoDerivs", False), ("Standard", False), ("", False)])
def test_licence_ok_only_cc0_and_by(label, ok):
    assert h.licence_ok(label)[0] is ok


def test_si_search_groups_qualities_into_one_candidate(monkeypatch):
    monkeypatch.setattr(h, "_get", lambda url, params=None, headers=None: resp(url, si_rows("Thumb", "Low", "Medium", "High")))
    [c] = h.search_si("mammoth")
    assert c["id"] == PKG and c["zdroj"] == "smithsonian" and c["stranka"].endswith(PKG) and c["lze_stahnout"]


def test_si_fetch_checks_cc0_then_takes_medium(monkeypatch):
    calls = []

    def fake(url, params=None, headers=None):
        calls.append(url)
        if url == h.SI_OA:
            return resp(url, si_oa("CC0"))
        if url == h.SI_SEARCH:
            return resp(url, si_rows("Thumb", "High", "Medium"))
        return resp(url, content=GLB)

    monkeypatch.setattr(h, "_get", fake)
    glb, info = h.fetch("smithsonian", PKG)
    assert glb == GLB and calls[0] == h.SI_OA and calls[-1].endswith("mammoth-medium.glb")
    assert info["licence"] == "CC0" and "Paleobiology" in info["autor"] and info["origin"].startswith("Smithsonian 3D: Mammuthus")


def test_si_fetch_refuses_without_cc0(monkeypatch):
    monkeypatch.setattr(h, "_get", lambda url, params=None, headers=None: resp(url, si_oa("Usage conditions apply")))
    with pytest.raises(h.Hotove3dError, match="ne CC0"):
        h.fetch_si(PKG)


def test_sf_search_marks_sharealike_as_reference_only(monkeypatch):
    rows = {"results": [sf_row("CC Attribution", "a"), sf_row("CC Attribution-ShareAlike", "b")]}
    monkeypatch.setattr(h, "_get", lambda url, params=None, headers=None: resp(url, rows))
    a, b = h.search_sf("colosseum")
    assert a["lze_stahnout"] and a["nahled"] == "m.jpg" and a["autor"] == "CMBC"
    assert not b["lze_stahnout"] and "ShareAlike" in b["proc_ne"]


def test_sf_fetch_needs_token(monkeypatch):
    monkeypatch.setattr(h, "get_key", lambda *names: None)
    with pytest.raises(h.Hotove3dError, match="SKETCHFAB_API_TOKEN"):
        h.fetch_sf("abc")


def test_sf_fetch_rechecks_licence_and_downloads_glb(monkeypatch):
    monkeypatch.setattr(h, "get_key", lambda *names: "tok")
    seen = {}

    def fake(url, params=None, headers=None):
        if url.endswith("/download"):
            seen["auth"] = (headers or {}).get("Authorization")
            return resp(url, {"glb": {"url": "https://cdn/x.glb", "size": len(GLB)}})
        if url.endswith("/models/abc"):
            return resp(url, sf_row("CC Attribution"))
        return resp(url, content=GLB)

    monkeypatch.setattr(h, "_get", fake)
    glb, info = h.fetch("sketchfab", "abc")
    assert glb == GLB and seen["auth"] == "Token tok" and info["licence"] == "CC Attribution" and "CMBC" in info["origin"]


def test_search_survives_one_source_down(monkeypatch):
    def down(q):
        raise h.Hotove3dError("api.sketchfab.com vrátil 503")

    monkeypatch.setattr(h, "search_sf", down)
    monkeypatch.setattr(h, "search_si", lambda q: [{"zdroj": "smithsonian"}])
    monkeypatch.setattr(h, "search_sklad", lambda q: [])
    out = h.search("mammoth")
    assert out["kandidati"] == [{"zdroj": "smithsonian"}] and "503" in out["chyby"][0]


# -- sklad na D: (ngm_shared.sklad3d; NGM_SKLAD je v testech dočasná složka) ------------

def test_sklad_search_first_without_our_models(monkeypatch):
    from ngm_shared import sklad3d
    sklad3d.uloz_model("smithsonian", "mamut", GLB, {"nazev": "Woolly Mammoth", "licence": "CC0", "autor": "SI"})
    sklad3d.sestav_index()
    monkeypatch.setattr(h, "search_si", lambda q: [{"zdroj": "smithsonian"}])
    monkeypatch.setattr(h, "search_sf", lambda q: [])
    out = h.search("mammoth")
    assert [k["zdroj"] for k in out["kandidati"]] == ["sklad", "smithsonian"]
    k = out["kandidati"][0]
    assert (k["id"], k["licence"], k["lze_stahnout"], k["nahled"]) == ("smithsonian/mamut", "CC0", True, None)
    glb, info = h.fetch("sklad", "smithsonian/mamut")
    assert glb == GLB and info["sklad_id"] == "smithsonian/mamut"
    assert info["origin"].startswith("Sklad (smithsonian): Woolly Mammoth, SI, CC0")


def test_sklad_offers_no_own_models_and_survives_missing_store(tmp_path, monkeypatch):
    from ngm_shared import sklad3d
    (tmp_path / "v1").mkdir()
    (tmp_path / "v1" / "model.glb").write_bytes(GLB)
    sklad3d.uloz_nas(tmp_path / "v1", {"id": "amfora", "version": "v1", "title": "Amphora"})
    assert h.search_sklad("amphora") == []
    with pytest.raises(h.Hotove3dError, match="není cizí model"):
        h.fetch("sklad", "nase/amfora/v1")
    monkeypatch.setenv("NGM_SKLAD", str(tmp_path / "chybi"))
    monkeypatch.setattr(h, "search_si", lambda q: [])
    monkeypatch.setattr(h, "search_sf", lambda q: [])
    out = h.search("amphora")
    assert out["kandidati"] == [] and out["chyby"][0].startswith("sklad: sklad")
