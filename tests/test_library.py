"""Knihovna tab: every finished picture page by page, deleting moves to library/.trash (operator 3 Nov)."""
from base64 import b64encode
from io import BytesIO

from PIL import Image

from tests.test_engine_v2 import api, sd, settings  # noqa: F401  (fixtures)


def _upload(api, title: str) -> str:
    buf = BytesIO()
    Image.new("RGB", (64, 48), (20, 50, 110)).save(buf, "PNG")
    r = api.post("/api/v2/library/upload", json={"b64": b64encode(buf.getvalue()).decode(), "name": f"{title}.png", "title": title})
    assert r.status_code == 201, r.text
    return r.json()["ref"]


def test_library_pages_reach_past_the_newest_jobs(api):
    refs = [_upload(api, f"obraz {i}") for i in range(5)]
    first = api.get("/api/v2/library?offset=0&limit=2").json()
    last = api.get("/api/v2/library?offset=4&limit=2").json()
    assert first["total"] == 5 and [j["job_id"] for j in first["items"]] == [r.split("/")[0] for r in refs[:2:-1]]
    assert [j["job_id"] for j in last["items"]] == [refs[0].split("/")[0]]   # the oldest is on the last page


def test_deleting_moves_the_picture_to_the_trash_and_out_of_the_library(api, settings):
    keep, gone = _upload(api, "zůstane"), _upload(api, "pryč")
    url = "/api/v2/jobs/" + gone.replace("/", "/images/")
    assert api.get(url + "?w=128").status_code == 200   # a thumbnail exists and must go along
    r = api.delete(url)
    assert r.status_code == 200, r.text
    moved = sorted(p.name for p in (settings.library_dir / ".trash").iterdir() for p in p.iterdir())
    assert "image-0.png" in moved and "image-0.json" in moved and any(n.startswith("thumb-") for n in moved)
    assert api.get(url).status_code == 404 and api.delete(url).status_code == 404
    lib = api.get("/api/v2/library").json()
    assert lib["total"] == 1 and lib["items"][0]["job_id"] == keep.split("/")[0]
    assert api.get("/api/v2/jobs/" + gone.split("/")[0]).json()["status"] == "deleted"
