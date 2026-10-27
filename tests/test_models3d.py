"""3D step offline: fake fal and fake Blender (spec docs/plans/2026-10-27-3d-v1.md, sc-2…sc-9; v2: viewer copy,
sheet on a button, render from the viewer's camera)."""
from __future__ import annotations

import base64
import json
import sys
import time
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from engine.app import create_app
from engine.backends import FluxLocal
from engine.jobs import load_costs
from engine.models3d import FalModel3d, Model3dError, Model3dLibrary
from tests.test_engine_v2 import FakeSd, free_port  # noqa: F401  (fixtures below reuse the fake sd-server)
from engine import sdserver
from engine.config import Settings

FAKE_BLENDER = Path(__file__).with_name("fake_blender.py")
GLB = b"glTF\x02\x00\x00\x00" + b"\x00" * 64


def png_b64(color=(120, 60, 30, 255)) -> str:
    buf = BytesIO()
    Image.new("RGBA", (32, 32), color).save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


class FakeFal(FalModel3d):
    """Records calls; `fail_after_submit` simulates fal or the network dying after the request was paid."""

    def __init__(self, method, endpoint):
        super().__init__(method, endpoint, method, 1, 5)
        self.calls, self.fetched = [], []
        self.fail_after_submit = False

    def run(self, refs, on_submitted):
        self.calls.append(sorted(refs))
        on_submitted("req-123")
        if self.fail_after_submit:
            raise Model3dError("fal: spojení spadlo")
        return GLB

    def fetch(self, request_id):
        self.fetched.append(request_id)
        return GLB


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setattr(sdserver, "free_vram_mib", lambda: None)
    monkeypatch.setenv("FAKE_BLENDER_TRACE", str(tmp_path / "blender-trace.jsonl"))
    monkeypatch.setenv("FAKE_BLENDER_LOCK", str(tmp_path / "gpu.lock"))
    return Settings(data_dir=tmp_path, flux_dir=tmp_path, sd_port=free_port(), gpu_lock_path=tmp_path / "gpu.lock",
                    idle_timeout_s=600, start_timeout_s=20, blender_cmd=[sys.executable, str(FAKE_BLENDER)],
                    blender_timeout_s=10, render_cpu=True)


@pytest.fixture
def api(settings):
    sd = FakeSd(settings)
    fal = {"fal-trellis2": FakeFal("fal-trellis2", "fal-ai/trellis-2"),
           "fal-hunyuan3d": FakeFal("fal-hunyuan3d", "fal-ai/hunyuan3d-v3/image-to-3d"),
           "fal-hunyuan31pro": FakeFal("fal-hunyuan31pro", "fal-ai/hunyuan-3d/v3.1/pro/image-to-3d")}
    app = create_app(settings, backends={"flux-local": FluxLocal(settings, sd)}, server=sd, backends3d=fal)
    with TestClient(app) as c:
        c.fal, c.sd = fal, sd
        yield c
    sd.stop("test teardown")


def wait(api, job_id, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        j = api.get(f"/api/v2/jobs/{job_id}").json()
        if j["status"] in ("done", "failed", "cancelled"):
            return j
        time.sleep(0.1)
    raise AssertionError(f"job {job_id} did not finish")


def upload(api, title="Tatra 87"):
    r = api.post("/api/v2/models3d", json={"title": title, "glb_b64": base64.b64encode(GLB).decode()})
    assert r.status_code == 202, r.text
    return r.json()


def trace(settings) -> list[dict]:
    p = settings.data_dir / "blender-trace.jsonl"
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


# -- sc-2: recommended method, price, 402 ------------------------------------------

def test_hunyuan31pro_price_and_views(api):
    one = api.post("/api/v2/models3d/estimate", json={"method": "fal-hunyuan31pro", "refs": [{"view": "front"}]}).json()
    assert one["method"] == "fal-hunyuan31pro" and one["total_usd"] == 0.375
    two = api.post("/api/v2/models3d/estimate",
                   json={"method": "fal-hunyuan31pro", "refs": [{"view": "front"}, {"view": "left"}]}).json()
    assert two["total_usd"] == 0.525
    no_front = api.post("/api/v2/models3d/estimate", json={"method": "fal-hunyuan31pro", "refs": [{"view": "back"}]})
    assert no_front.status_code == 400 and "zepředu" in no_front.json()["detail"]
    # the recommendation stays TRELLIS 2 for one reference (DECISIONS 2026-10-27)
    assert api.post("/api/v2/models3d/estimate", json={"refs": [{"view": "front"}]}).json()["method"] == "fal-trellis2"


def test_hunyuan_arguments_have_no_custom_face_count():
    """fal bills a custom face count 0.15 USD extra; its default is the same 500k faces."""
    for method in ("fal-hunyuan3d", "fal-hunyuan31pro"):
        args = FalModel3d(method, "x", method, 1, 5).arguments({"front": "u-f", "back": "u-b"})
        assert args == {"input_image_url": "u-f", "generate_type": "Geometry", "back_image_url": "u-b"}


def test_recommendation_and_price(api):
    one = api.post("/api/v2/models3d/estimate", json={"refs": [{"view": "front"}]}).json()
    assert one["method"] == "fal-trellis2" and one["total_usd"] == 0.30
    three = api.post("/api/v2/models3d/estimate", json={"refs": [{"view": v} for v in ("front", "back", "left")]}).json()
    assert three["method"] == "fal-hunyuan3d" and three["total_usd"] == 0.375
    single_h = api.post("/api/v2/models3d/estimate", json={"method": "fal-hunyuan3d", "refs": [{"view": "front"}]}).json()
    assert single_h["total_usd"] == 0.225
    up = api.post("/api/v2/models3d/estimate", json={"method": "upload"}).json()
    assert up["total_usd"] == 0
    bad = api.post("/api/v2/models3d/estimate", json={"method": "fal-trellis2", "refs": [{"view": "front"}, {"view": "back"}]})
    assert bad.status_code == 400 and "jednu předlohu" in bad.json()["detail"]


def test_paid_model_needs_confirmation(api, settings):
    body = {"title": "Slon", "refs": [{"view": "front", "b64": png_b64()}]}
    r = api.post("/api/v2/models3d", json=body)
    assert r.status_code == 402 and r.json()["estimate_usd"] == 0.30
    assert api.fal["fal-trellis2"].calls == []
    assert api.get("/api/v2/models3d").json() == [] and not settings.costs_path.exists()


# -- sc-6 + sc-3 + sc-5: paid model, write-ahead, request_id, views, review gate -------

def test_paid_model_full_flow(api, settings):
    body = {"title": "Tatra 87", "confirm_cost": True, "refs": [
        {"view": "front", "b64": png_b64(), "source": "Commons: front.jpg", "license": "CC BY-SA 4.0"},
        {"view": "back", "b64": png_b64(), "source": "Commons: back.jpg", "license": "CC BY-SA 3.0"}]}
    r = api.post("/api/v2/models3d", json=body)
    assert r.status_code == 202, r.text
    created = r.json()
    assert created["model_id"] == "tatra-87" and created["version"] == "v1" and created["estimate_usd"] == 0.375
    job = wait(api, created["job_id"])
    assert job["status"] == "done", job["error"]
    assert api.fal["fal-hunyuan3d"].calls == [["back", "front"]]
    viewer = wait(api, job["result"]["viewer_job"])
    assert viewer["status"] == "done", viewer["error"]

    rows = [json.loads(x) for x in settings.costs_path.read_text(encoding="utf-8").splitlines()]
    assert [x["status"] for x in rows] == ["pending", "ok"] and rows[1]["request_id"] == "req-123"
    assert load_costs(settings.costs_path)[-1]["usd"] == 0.375

    m = api.get("/api/v2/models3d/tatra-87").json()["versions"][0]
    assert m["schema_version"] == 1 and m["method"] == "fal-hunyuan3d" and m["request_id"] == "req-123"
    assert m["cost_usd"] == 0.375 and m["status"] == "ready" and m["blender"] == "fake 0.0"
    assert {r["license"] for r in m["refs"]} == {"CC BY-SA 4.0", "CC BY-SA 3.0"}
    # v2: the viewer copy comes by itself, the sheet only on the button
    assert m["viewer"]["file"] == "viewer.glb" and m["views"] == {}
    assert api.get("/api/v2/models3d/tatra-87/v1/viewer.glb").content == GLB
    sheet = api.post("/api/v2/models3d/tatra-87/v1/views", json={"elevation": 20}).json()
    assert wait(api, sheet["job_id"])["status"] == "done"
    m = api.get("/api/v2/models3d/tatra-87").json()["versions"][0]
    assert len(m["views"]["20"]["files"]) == 8 and m["status"] == "ready"
    assert api.get("/api/v2/models3d/tatra-87/v1/model.glb").content == GLB
    assert api.get("/api/v2/models3d/tatra-87/v1/files/views-e20/az045.png?w=32").content[:4] == b"\x89PNG"

    # → Studio is locked until the operator ticks the check
    assert api.get("/api/v2/models3d/tatra-87/v1/as-ref?azimuth=45").status_code == 409
    assert api.post("/api/v2/models3d/tatra-87/v1/review", json={"reviewed": True}).json()["review"]["by"]
    ref = api.get("/api/v2/models3d/tatra-87/v1/as-ref?azimuth=45").json()
    assert ref["role"] == "geometry" and Path(ref["path"]).name == "az045.png"
    assert "CC BY-SA" in ref["license"]


def test_crash_after_submit_keeps_request_id_and_recovers_without_paying(api, settings):
    fal = api.fal["fal-trellis2"]
    fal.fail_after_submit = True
    r = api.post("/api/v2/models3d", json={"title": "Mamut", "confirm_cost": True,
                                           "refs": [{"view": "front", "b64": png_b64()}]}).json()
    job = wait(api, r["job_id"])
    assert job["status"] == "failed" and "spojení spadlo" in job["error"]
    m = api.get("/api/v2/models3d/mamut").json()["versions"][0]
    assert m["status"] == "failed" and m["request_id"] == "req-123"
    # paid at fal -> the ledger keeps the pending row (estimated cost stays counted)
    assert load_costs(settings.costs_path)[-1]["status"] == "pending"

    rec = api.post("/api/v2/models3d/mamut/v1/recover")
    assert rec.status_code == 202
    assert wait(api, rec.json()["job_id"])["status"] == "done"
    assert fal.fetched == ["req-123"] and len(fal.calls) == 1, "vyzvednutí nesmí poslat druhou placenou úlohu"
    assert load_costs(settings.costs_path)[-1]["status"] == "ok"
    assert api.post("/api/v2/models3d/mamut/v1/recover").status_code == 409


# -- sc-5: versions, never overwrite; migration as a copy --------------------------------

def test_every_run_is_a_new_version(api, settings):
    first = upload(api)
    wait(api, first["job_id"])
    sheet = api.post("/api/v2/models3d/tatra-87/v1/views", json={"elevation": 20}).json()
    assert wait(api, sheet["job_id"])["status"] == "done"
    second = api.post("/api/v2/models3d", json={"model_id": "tatra-87", "glb_b64": base64.b64encode(GLB + b"x").decode()})
    assert second.json()["version"] == "v2"
    wait(api, second.json()["job_id"])
    # rendering again keeps the earlier set
    again = api.post("/api/v2/models3d/tatra-87/v1/views", json={"elevation": 20}).json()
    assert wait(api, again["job_id"])["status"] == "done"
    d = settings.library_dir / "3d" / "tatra-87"
    assert (d / "v1" / "views-e20-2" / "az000.png").is_file() and (d / "v1" / "views-e20" / "az000.png").is_file()
    assert (d / "v1" / "model.glb").read_bytes() == GLB and (d / "v2" / "model.glb").read_bytes() == GLB + b"x"
    assert [v["version"] for v in api.get("/api/v2/models3d/tatra-87").json()["versions"]] == ["v1", "v2"]
    low = api.post("/api/v2/models3d/tatra-87/v1/views", json={"elevation": 5}).json()
    assert wait(api, low["job_id"])["status"] == "done"
    assert set(api.get("/api/v2/models3d/tatra-87").json()["versions"][0]["views"]) == {"5", "20"}
    assert api.post("/api/v2/models3d/tatra-87/v1/views", json={"elevation": 33}).status_code == 400


def test_stretch_makes_a_new_version(api, settings):
    wait(api, upload(api)["job_id"])
    r = api.post("/api/v2/models3d/tatra-87/v1/stretch", json={"dims": [4.74, 1.67, 1.5], "part": "middle",
                                                                "source": "Wikipedia"}).json()
    assert r["version"] == "v2"
    job = wait(api, r["job_id"])
    assert job["status"] == "done", job["error"]
    assert wait(api, job["result"]["viewer_job"])["status"] == "done"
    v2 = api.get("/api/v2/models3d/tatra-87").json()["versions"][1]
    assert v2["method"] == "stretch" and v2["parent"] == "v1" and v2["stretch"]["bbox"] == [4.74, 1.67, 1.5]
    assert v2["status"] == "ready" and v2["review"] is None
    bad = api.post("/api/v2/models3d/tatra-87/v1/stretch", json={"dims": [4, 1], "part": "middle"})
    assert bad.status_code == 400


def test_upload_rejects_non_glb(api):
    r = api.post("/api/v2/models3d", json={"title": "x", "glb_b64": base64.b64encode(b"not a model").decode()})
    assert r.status_code == 400 and "GLB" in r.json()["detail"]


def test_migrate_legacy_copies(tmp_path):
    old = tmp_path / "3d" / "tatra87-hunyuan3d"
    old.mkdir(parents=True)
    (old / "model.glb").write_bytes(GLB)
    Image.new("RGB", (8, 8)).save(old / "predloha-front.png")
    Image.new("RGB", (8, 8)).save(old / "clay-az030.png")
    (old / "model.json").write_text(json.dumps({
        "title": "Tatra 87 (Hunyuan3D)", "made": "2026-10-27", "backend": "fal:fal-ai/hunyuan3d-v3/image-to-3d",
        "views": {"front": "Commons: Tatra front.jpg, CC BY-SA 4.0"}, "usd": 0.375}), encoding="utf-8")
    lib = Model3dLibrary(tmp_path / "3d")
    assert lib.migrate_legacy() == ["tatra87-hunyuan3d"]
    assert lib.migrate_legacy() == [], "převod jen jednou"
    m = lib.latest("tatra87-hunyuan3d")
    assert m["schema_version"] == 1 and m["method"] == "fal-hunyuan3d" and m["cost_usd"] == 0.375
    assert m["refs"][0]["license"] == "CC BY-SA 4.0" and m["status"] == "model"
    assert (old / "model.glb").is_file(), "originál zůstává (kopie, ne přesun)"
    assert (old / "v1" / "model.glb").read_bytes() == GLB and (old / "v1" / "legacy-thumb.png").is_file()


# -- sc-4: Blender under the GPU lock, FLUX and render both finish --------------------------

def test_flux_and_render_both_done_render_holds_gpu_lock(api, settings):
    img = api.post("/api/v2/images", json={"prompt": "a car", "size": "256x256", "seed": 1}).json()["job_id"]
    up = upload(api)
    wait(api, up["job_id"])
    sheet = api.post("/api/v2/models3d/tatra-87/v1/views", json={"elevation": 20}).json()["job_id"]
    img2 = api.post("/api/v2/images", json={"prompt": "a car", "size": "256x256", "seed": 2}).json()["job_id"]
    jobs = [wait(api, j) for j in (img, sheet, img2)]
    assert [j["status"] for j in jobs] == ["done"] * 3, [j["error"] for j in jobs]
    calls = [c for c in trace(settings) if c["script"] == "render_views.py"]
    assert calls and all(c["lock"] and json.loads(c["lock"])["owner"] == "grafik-engine" for c in calls)
    assert not settings.gpu_lock_path.exists(), "zámek se po renderu uvolní"
    # 3D jobs stay out of /api/v2/jobs (sc-7) but are in the 3D list
    assert {j["job_id"] for j in api.get("/api/v2/jobs").json()} == {img, img2}
    assert up["job_id"] in {j["job_id"] for j in api.get("/api/v2/models3d/jobs").json()}


def test_eevee_mode_stops_own_sd_server_first(api, settings):
    settings.render_cpu = False
    img = api.post("/api/v2/images", json={"prompt": "a car", "size": "256x256", "seed": 1}).json()["job_id"]
    assert wait(api, img)["status"] == "done"
    assert api.sd.owned_process() is not None
    assert wait(api, upload(api)["job_id"])["status"] == "done"
    assert api.sd.owned_process() is not None, "zmenšení pro prohlížeč nerenderuje, FLUX zůstává"
    sheet = api.post("/api/v2/models3d/tatra-87/v1/views", json={"elevation": 20}).json()["job_id"]
    assert wait(api, sheet)["status"] == "done"
    assert api.sd.owned_process() is None, "před renderem EEVEE musí vlastní sd-server skončit"
    assert "--cpu" not in trace(settings)[-1]["args"]


# -- sc-8: time limits and readable errors with the Blender log -----------------------------

@pytest.mark.parametrize("mode,needle", [("crash", "Blender skončil chybou 1"), ("empty", "je prázdný"),
                                         ("slow", "nedoběhl do 2 s")])
def test_blender_errors_are_readable(api, settings, monkeypatch, mode, needle):
    up = upload(api)
    assert wait(api, up["job_id"])["status"] == "done"
    monkeypatch.setenv("FAKE_BLENDER_MODE", mode)
    settings.blender_timeout_s = 2
    job = wait(api, api.post(f"/api/v2/models3d/{up['model_id']}/v1/views", json={"elevation": 20}).json()["job_id"])
    assert job["status"] == "failed" and needle in job["error"], job["error"]
    m = api.get(f"/api/v2/models3d/{up['model_id']}").json()["versions"][0]
    assert m["status"] == "ready" and needle in m["error"], "model zůstává v prohlížeči"
    log = settings.library_dir / "3d" / up["model_id"] / "v1" / "views-e20" / "blender.log"
    assert log.is_file()
    if mode == "crash":
        assert "GLB import failed" in log.read_text(encoding="utf-8")
    assert not settings.gpu_lock_path.exists()


def test_interrupted_step_is_marked(tmp_path):
    lib = Model3dLibrary(tmp_path / "3d")
    m = lib.new_version(None, "Rotunda", method="fal-trellis2", request_id="req-9")
    lib.update(m["id"], "v1", status="generating")
    assert lib.mark_interrupted() == 1
    v = lib.latest("rotunda")
    assert v["status"] == "failed" and "restartem" in v["error"] and v["request_id"] == "req-9"


# -- v2: viewer copy, check in the viewer, render from the viewer's camera -----------------------

CAM = {"target": [0.1, 0.2, -0.3], "azimuth": 315, "elevation": 20, "distance": 2.5, "lens": 50}


def test_viewer_copy_and_crash_keeps_model(api, settings, monkeypatch):
    up = upload(api)
    assert wait(api, up["job_id"])["status"] == "done"
    d = settings.library_dir / "3d" / "tatra-87" / "v1"
    assert (d / "viewer.glb").read_bytes() == GLB and (d / "model.glb").read_bytes() == GLB
    call = [c for c in trace(settings) if c["script"] == "decimate.py"][0]
    assert call["args"][2] == "100000" and call["lock"] is None, "zmenšení běží bez zámku GPU"
    # a model from before v2 (no viewer copy) gets one on first open; a second click joins the same job
    (d / "viewer.glb").unlink()
    monkeypatch.setenv("FAKE_BLENDER_MODE", "slow")
    settings.blender_timeout_s = 2
    a = api.post("/api/v2/models3d/tatra-87/v1/viewer").json()["job_id"]
    b = api.post("/api/v2/models3d/tatra-87/v1/viewer").json()["job_id"]
    assert a == b
    job = wait(api, a)
    assert job["status"] == "failed" and "nedoběhl" in job["error"]
    assert not (d / "viewer.tmp.glb").exists() and (d / "model.glb").read_bytes() == GLB
    assert api.get("/api/v2/models3d/tatra-87/v1/viewer.glb").status_code == 404
    assert api.post("/api/v2/models3d/nic/v1/viewer").status_code == 404


def test_review_in_viewer_then_render_from_camera(api, settings):
    wait(api, upload(api)["job_id"])
    base = "/api/v2/models3d/tatra-87/v1"
    # the gate (sc-3) holds for the camera render too
    assert api.post(f"{base}/camera", json=CAM).status_code == 409
    # v2: ticking the check needs the viewer, not the sheet
    assert api.post(f"{base}/review", json={"reviewed": True}).status_code == 200
    r = api.post(f"{base}/camera", json=CAM)
    assert r.status_code == 202, r.text
    job = wait(api, r.json()["job_id"])
    assert job["status"] == "done", job["error"]
    key = r.json()["key"]
    d = settings.library_dir / "3d" / "tatra-87" / "v1" / "camera"
    assert (d / f"{key}.png").is_file() and json.loads((d / f"{key}.json").read_text(encoding="utf-8"))["azimuth"] == 315
    call = [c for c in trace(settings) if "--camera" in c["args"]][-1]
    assert json.loads(call["args"][call["args"].index("--camera") + 1]) == CAM
    assert call["lock"] and "--cpu" in call["args"]
    # the same camera again: the existing render, no second job; another camera: a new file
    again = api.post(f"{base}/camera", json=CAM).json()
    assert again == {"key": key, "job_id": None, "file": f"camera/{key}.png"}
    other = api.post(f"{base}/camera", json={**CAM, "azimuth": 270}).json()
    assert other["key"] != key and wait(api, other["job_id"])["status"] == "done"
    ref = api.get(f"{base}/as-ref?cam={key}").json()
    assert ref["role"] == "geometry" and Path(ref["path"]).name == f"{key}.png" and ref["file"] == f"camera/{key}.png"
    assert "azimut 315°" in ref["source"] and "ohnisko 50 mm" in ref["source"]
    assert api.get(f"{base}/as-ref?cam=cam-0000000000").status_code == 404
    assert api.get(f"{base}/files/camera/{key}.png").content[:4] == b"\x89PNG"


@pytest.mark.parametrize("bad", [{"elevation": 90}, {"distance": 0}, {"lens": 5}, {"target": [0, 0]}])
def test_camera_rejects_impossible_values(api, bad):
    wait(api, upload(api)["job_id"])
    api.post("/api/v2/models3d/tatra-87/v1/review", json={"reviewed": True})
    assert api.post("/api/v2/models3d/tatra-87/v1/camera", json={**CAM, **bad}).status_code == 422


def test_empty_camera_view_is_an_error(api, settings, monkeypatch):
    wait(api, upload(api)["job_id"])
    api.post("/api/v2/models3d/tatra-87/v1/review", json={"reviewed": True})
    monkeypatch.setenv("FAKE_BLENDER_MODE", "empty")
    r = api.post("/api/v2/models3d/tatra-87/v1/camera", json=CAM).json()
    job = wait(api, r["job_id"])
    assert job["status"] == "failed" and "mimo záběr" in job["error"]
    assert not list((settings.library_dir / "3d" / "tatra-87" / "v1" / "camera").glob("*.png"))
