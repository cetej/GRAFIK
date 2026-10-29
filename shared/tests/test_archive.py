"""Archiv s hledáním (`ngm_shared.archive`) nad databází se stejným schématem, jaké má GRAFIK Engine."""

import json
import sqlite3
from datetime import datetime

import pytest
from PIL import Image

from ngm_shared import archive

SCHEMA = """CREATE TABLE jobs (id TEXT PRIMARY KEY, seq INTEGER, status TEXT, caller TEXT, backend TEXT,
  request TEXT, result TEXT, error TEXT, created REAL, started REAL, finished REAL, parent TEXT,
  kind TEXT DEFAULT 'image')"""


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "jobs.sqlite"
    con = sqlite3.connect(path)
    con.execute(SCHEMA)
    lib = tmp_path / "library"

    def add(seq, job_id, day, caller, request, kind="image", status="done", n_images=1, result=None):
        files = []
        for n in range(n_images):
            (lib / job_id).mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (600, 400), (40 * seq % 255, 90, 120)).save(lib / job_id / f"image-{n}.png")
            files.append(str(lib / job_id / f"image-{n}.png"))
        res = {"files": files, "dir": str(lib / job_id), **(result or {})} if status == "done" else None
        con.execute("INSERT INTO jobs (id, seq, status, caller, backend, request, result, created, kind) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (job_id, seq, status, caller, "flux-local", json.dumps(request, ensure_ascii=False),
                     json.dumps(res, ensure_ascii=False) if res else None,
                     datetime.strptime(day, "%Y-%m-%d %H:%M").timestamp(), kind))

    add(1, "20261022-100000-aaaaaa", "2026-10-22 10:00", "studio",
        {"prompt": "Liška obecná v zasněženém lese", "refs": [{"b64": "liska" * 50}]},
        result={"prompt_sent": "A red fox in a snowy birch forest"})
    add(2, "20261023-110000-bbbbbb", "2026-10-23 11:00", "ng-robot",
        {"prompt": "Reliéf Krkonoše, přemalovat", "refs": []})
    add(3, "20261028-120000-cccccc", "2026-10-28 12:00", "ng-robot-test", {"prompt": "Maják v noci"},
        status="failed", n_images=0)
    add(4, "20261029-130000-dddddd", "2026-10-29 13:00", "test-t2", {"image": "x.png", "source": "nahraný obrázek"},
        kind="localize", result={"text": "Koloběh vody · Srážky", "text_src": "The Water Cycle · Precipitation"})
    add(5, "20261029-140000-eeeeee", "2026-10-29 14:00", "klapka", {"model_id": "tatra-87", "version": "v2"},
        kind="views3d", n_images=0, result={"files": ["az000.png"], "dir": str(lib / "3d" / "views-e20")})
    (lib / "3d" / "views-e20").mkdir(parents=True)
    Image.new("RGB", (300, 300), "white").save(lib / "3d" / "views-e20" / "az000.png")
    con.commit()
    con.close()
    return path


def test_words_without_case_or_diacritics_and_newest_first(db):
    hits = archive.search("krkonose", db=db)
    assert [h["job_id"] for h in hits] == ["20261023-110000-bbbbbb"] and hits[0]["prompt"].startswith("Reliéf")
    assert [h["job_id"] for h in archive.search("LIŠKA les", db=db)] == ["20261022-100000-aaaaaa"]
    assert archive.search("fox birch", db=db)[0]["prompt_sent"].startswith("A red fox")     # anglický prompt
    assert archive.search("liska more", db=db) == []                                         # všechna slova
    assert [h["job_id"] for h in archive.search("", db=db)][:2] == ["20261029-140000-eeeeee",
                                                                    "20261029-130000-dddddd"]


def test_b64_of_references_is_not_searched(db):
    assert archive.search("liskaliska", db=db) == []


def test_filters_caller_kind_date_status(db):
    assert {h["caller"] for h in archive.search(caller="NG-ROBOT", db=db, status=None)} == {"ng-robot", "ng-robot-test"}
    assert [h["kind"] for h in archive.search(kind="localize", db=db)] == ["localize"]
    assert archive.search("kolobeh", db=db)[0]["text"].startswith("Koloběh")                  # počeštění
    assert [h["job_id"] for h in archive.search(since="2026-10-23", until="2026-10-28", db=db, status=None)] == [
        "20261028-120000-cccccc", "20261023-110000-bbbbbb"]
    views = archive.search("tatra", db=db, thumbs=True)[0]
    assert views["kind"] == "views3d" and views["images"][0]["exists"] and views["images"][0]["url"] is None
    assert views["images"][0]["path"].endswith("az000.png") and views["images"][0]["thumb_path"]
    with pytest.raises(archive.ArchiveError, match="RRRR-MM-DD"):
        archive.search(since="29. 10.", db=db)


def test_images_with_paths_urls_and_thumbnails(db):
    hit = archive.search("liska", db=db, engine="")[0]
    img = hit["images"][0]
    assert img["exists"] and img["path"].endswith("image-0.png") and img["thumb_path"] is None
    assert img["url"] == "/api/v2/jobs/20261022-100000-aaaaaa/images/0" and img["thumb_url"].endswith("?w=256")
    img = archive.search("liska", db=db, thumbs=True)[0]["images"][0]
    assert img["thumb_path"].endswith("thumb-image-0-256.jpg") and img["url"].startswith("http://127.0.0.1:8300/")
    with Image.open(img["thumb_path"]) as t:
        assert t.width == 256


def test_facets_and_missing_db(db, tmp_path):
    f = archive.facets(db)
    assert f["total"] == 5 and f["callers"]["ng-robot"] == 1 and f["kinds"]["image"] == 3
    assert (f["first"], f["last"]) == ("2026-10-22", "2026-10-29")
    with pytest.raises(archive.ArchiveError, match="neexistuje"):
        archive.search(db=tmp_path / "nic.sqlite")


def test_archive_never_writes_to_the_database(db):
    before = db.read_bytes()
    archive.search("liska", db=db)
    archive.facets(db)
    assert db.read_bytes() == before
