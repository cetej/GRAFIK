"""GRAFIK v2 Engine (G1) — offline tests against a fake sd-server process.
Maps to spec sc-3…sc-9 (docs/plans/2026-10-22-grafik-v2-greenfield.md)."""
from __future__ import annotations

import ast
import json
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil
import pytest
import uvicorn
from fastapi.testclient import TestClient

from engine import sdserver
from engine.app import create_app
from engine.backends import FluxLocal, NanoBananaPro
from engine.config import Settings
from engine.gpu import GpuBusy, GpuLock
from engine.models import ImageRequest
from engine.prompt import build_prompt, image_ref_indices
from engine.sdserver import SdServer, SdServerError

ROOT = Path(__file__).resolve().parents[1]
FAKE = Path(__file__).with_name("fake_sd_server.py")
PNG_1PX = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class FakeSd(SdServer):
    def command(self):
        return [sys.executable, str(FAKE), "--listen-port", str(self.s.sd_port)]


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setattr(sdserver, "free_vram_mib", lambda: None)
    return Settings(data_dir=tmp_path, flux_dir=tmp_path, sd_port=free_port(),
                    gpu_lock_path=tmp_path / "gpu.lock", idle_timeout_s=600, start_timeout_s=20)


@pytest.fixture
def sd(settings):
    server = FakeSd(settings)
    yield server
    server.stop("test teardown")


# -- prompt translation (sc-8, sc-21) -------------------------------------

def test_layout_prompt_pinned():
    req = ImageRequest(prompt="In <ref_image_0>, move the bicycle <bike_1> to the right.",
                       refs=[{"b64": PNG_1PX, "role": "subject"}],
                       layout=[{"id": "bike_1", "from": "ref_image_0", "src_bbox": [430, 40, 920, 360],
                                "tgt_bbox": [430, 650, 920, 970], "desc": "red vintage bicycle"}])
    assert build_prompt(req) == (
        'In <ref_image_0>, move the bicycle <bike_1> to the right. No text, no letters, no labels. '
        '[{"id": "bike_1", "from": "ref_image_0", "src_bbox": [430, 40, 920, 360], '
        '"tgt_bbox": [430, 650, 920, 970], "desc": "red vintage bicycle"}]')


def test_style_ref_goes_as_words_never_pixels():
    req = ImageRequest(prompt="A lighthouse", refs=[
        {"b64": PNG_1PX, "role": "geometry"},
        {"b64": PNG_1PX, "role": "style", "text": "loose watercolour washes on cotton paper"},
        {"b64": PNG_1PX, "role": "subject"}])
    assert image_ref_indices(req) == [0, 2]
    assert "Style: loose watercolour washes on cotton paper." in build_prompt(req)


def test_no_text_not_duplicated():
    assert build_prompt(ImageRequest(prompt="Map. No text at all.")).count("No text") == 1


@pytest.mark.parametrize("bad", [
    {"size": "1000x1000"}, {"size": "abc"},
    {"layout": [{"id": "a", "desc": "x", "bbox": [500, 0, 400, 100]}]},
    {"layout": [{"id": "a", "desc": "x", "bbox": [0, 0, 1001, 100]}]},
    {"refs": [{"b64": PNG_1PX}] * 11},
    {"refs": [{"role": "subject"}]},
])
def test_request_validation(bad):
    with pytest.raises(ValueError):
        ImageRequest(prompt="x", **bad)


# -- sd-server lifecycle (sc-4) -------------------------------------------

def test_start_generate_and_idle_stop_only_own_pid(sd, settings):
    out = sd.generate({"prompt": "x", "width": 256, "height": 256, "seed": 1})
    assert out[0][:8] == b"\x89PNG\r\n\x1a\n"
    state = json.loads(sd.state_path.read_text())
    own = psutil.Process(state["pid"])
    assert abs(own.create_time() - state["create_time"]) < 1

    foreign = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        settings.idle_timeout_s = 0
        assert sd.stop_if_idle() is True
        assert not psutil.pid_exists(state["pid"]) or psutil.Process(state["pid"]).status() == psutil.STATUS_ZOMBIE
        assert foreign.poll() is None, "cizí proces nesmí být ukončen"
    finally:
        foreign.kill()


def test_reused_pid_is_never_killed(sd):
    foreign = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        p = psutil.Process(foreign.pid)
        sd.s.run_dir.mkdir(parents=True, exist_ok=True)
        sd.state_path.write_text(json.dumps({"pid": foreign.pid, "create_time": p.create_time() - 100,
                                             "exe": p.exe()}))
        assert sd.owned_process() is None
        assert sd.stop("test") is False
        assert foreign.poll() is None
    finally:
        foreign.kill()


def test_foreign_server_on_port_is_refused(settings):
    foreign = subprocess.Popen([sys.executable, str(FAKE), "--listen-port", str(settings.sd_port)])
    try:
        sd = FakeSd(settings)
        deadline = time.time() + 10
        while not sd._healthy() and time.time() < deadline:
            time.sleep(0.2)
        with pytest.raises(SdServerError, match="nespustil"):
            sd.ensure_running()
        assert foreign.poll() is None
    finally:
        foreign.kill()


def test_low_vram_fails_readably_without_start(settings, monkeypatch):
    monkeypatch.setattr(sdserver, "free_vram_mib", lambda: 900)
    sd = FakeSd(settings)
    with pytest.raises(SdServerError, match="volných jen 900 MiB"):
        sd.ensure_running()
    assert sd.owned_process() is None


# -- GPU lock ---------------------------------------------------------------

def test_gpu_lock_stale_replaced_live_blocks(tmp_path):
    path = tmp_path / "gpu.lock"
    path.write_text(json.dumps({"owner": "dead", "pid": 999999, "since": 0}))
    lock = GpuLock(path)
    assert lock.try_acquire()
    lock.release()
    assert not path.exists()
    path.write_text(json.dumps({"owner": "ng-robot-dabing", "pid": psutil.Process().ppid(), "since": 0}))
    with pytest.raises(GpuBusy, match="ng-robot-dabing"):
        GpuLock(path).acquire(wait_s=0.3, poll_s=0.1)


# -- API, queue, costs, provenance (sc-3, sc-5, sc-6, sc-7) ---------------

def wait_done(client, job_id, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        j = client.get(f"/api/v2/jobs/{job_id}").json()
        if j["status"] in ("done", "failed", "cancelled"):
            return j
        time.sleep(0.1)
    raise AssertionError(f"job {job_id} did not finish")


@pytest.fixture
def api(settings, sd, monkeypatch):
    calls = []
    monkeypatch.setattr(NanoBananaPro, "_call", lambda self, *a: calls.append(a) or b"\x89PNG\r\n\x1a\nfake")
    backends = {"flux-local": FluxLocal(settings, sd), "nb-pro": NanoBananaPro()}
    app = create_app(settings, backends=backends, server=sd)
    with TestClient(app) as c:
        c.nb_calls = calls
        yield c


def test_paid_backend_needs_confirmation(api, settings):
    r = api.post("/api/v2/images", json={"prompt": "x", "backend": "nb-pro"})
    assert r.status_code == 402 and r.json()["estimate_usd"] == 0.134
    assert api.get("/api/v2/jobs").json() == [] and api.nb_calls == []
    r = api.post("/api/v2/images", json={"prompt": "x", "backend": "nb-pro", "confirm_cost": True})
    assert r.status_code == 202
    assert wait_done(api, r.json()["job_id"])["status"] == "done"
    assert len(api.nb_calls) == 1
    assert api.get("/api/v2/costs").json()["total_usd"] == 0.134


def test_local_failure_never_falls_back_to_paid(api, settings, monkeypatch):
    monkeypatch.setattr(sdserver, "free_vram_mib", lambda: 100)
    r = api.post("/api/v2/images", json={"prompt": "x", "size": "512x512"})
    job = wait_done(api, r.json()["job_id"])
    assert job["status"] == "failed" and "volných jen 100 MiB" in job["error"]
    assert api.nb_calls == []


def test_two_concurrent_requests_queue_fifo(api, sd, monkeypatch):
    monkeypatch.setenv("FAKE_SD_DELAY_S", "1.0")
    ids, errors = [], []

    def go(i):
        r = api.post("/api/v2/images", json={"prompt": f"p{i}", "size": "256x256", "seed": i})
        (ids.append(r.json()["job_id"]) if r.status_code == 202 else errors.append(r.text))

    threads = [threading.Thread(target=go, args=(i,)) for i in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors
    jobs = [wait_done(api, i) for i in ids]
    assert [j["status"] for j in jobs] == ["done", "done"]
    first, second = sorted(jobs, key=lambda j: j["created"])
    assert second["started"] >= first["finished"], "dva joby nesmí běžet současně"
    assert len({json.loads(sd.state_path.read_text())["pid"]}) == 1


def test_provenance_and_zero_cost(api, settings):
    r = api.post("/api/v2/images", json={
        "prompt": "a ship", "size": "256x256", "seed": 5, "caller": "pytest",
        "refs": [{"b64": PNG_1PX, "role": "geometry", "license": "CC BY-SA 4.0", "source": "commons"}]})
    job = wait_done(api, r.json()["job_id"])
    assert job["status"] == "done", job["error"]
    prov = api.get(job["images"][0] + "/provenance").json()
    for key in ("backend", "model", "seed", "params", "prompt_original", "prompt_sent", "refs", "layout",
                "ai_generated", "reviewed_by", "cost_usd", "timing_s"):
        assert key in prov
    assert prov["backend"] == "flux-local" and prov["cost_usd"] == 0 and prov["seed"] == 5
    assert prov["ai_generated"] is True and prov["reviewed_by"] is None
    assert prov["refs"][0]["role"] == "geometry" and len(prov["refs"][0]["sha256"]) == 64
    assert prov["refs"][0]["license"] == "CC BY-SA 4.0"
    assert api.get(job["images"][0]).content[:4] == b"\x89PNG"
    assert api.get("/api/v2/costs").json()["entries"][-1]["usd"] == 0


def test_image_only_style_ref_requires_cost_confirmation(api):
    r = api.post("/api/v2/images", json={"prompt": "x", "refs": [{"b64": PNG_1PX, "role": "style"}]})
    assert r.status_code == 402 and "Haiku" in r.json()["items"][0]["what"]


def test_size_over_8gb_ceiling_rejected(api):
    r = api.post("/api/v2/images", json={"prompt": "x", "size": "2048x2048"})
    assert r.status_code == 400 and "strop" in r.json()["detail"]


def test_interrupted_running_job_marked_failed(settings):
    from engine.jobs import JobStore
    store = JobStore(settings.db_path)
    job_id = store.add(ImageRequest(prompt="x"))
    store.next_queued()
    assert store.recover_interrupted() == 1
    assert store.get(job_id)["status"] == "failed"


# -- client (sc-9) ----------------------------------------------------------

def test_client_is_stdlib_only():
    tree = ast.parse((ROOT / "clients" / "grafik_client.py").read_text(encoding="utf-8"))
    mods = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    mods |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.level == 0}
    assert mods <= set(sys.stdlib_module_names) | {"__future__"}, mods - set(sys.stdlib_module_names)


def test_client_end_to_end(settings, sd, tmp_path, monkeypatch):
    port = free_port()
    app = create_app(settings, backends={"flux-local": FluxLocal(settings, sd), "nb-pro": NanoBananaPro()},
                     server=sd)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    while not server.started:
        time.sleep(0.05)
    try:
        sys.path.insert(0, str(ROOT / "clients"))
        import grafik_client
        monkeypatch.setattr(grafik_client, "ENGINE_URL", f"http://127.0.0.1:{port}")
        ref = tmp_path / "ref.png"
        ref.write_bytes(__import__("base64").b64decode(PNG_1PX))
        paths = grafik_client.generate("red apple", size="256x256", refs=[{"path": str(ref), "role": "subject"}],
                                       out_dir=tmp_path / "out", timeout=30)
        assert len(paths) == 1 and paths[0].read_bytes()[:4] == b"\x89PNG"
        with pytest.raises(grafik_client.CostConfirmationRequired):
            grafik_client.generate("x", backend="nb-pro")
    finally:
        server.should_exit = True
        t.join(timeout=5)


def test_client_engine_down_raises_unavailable(monkeypatch):
    sys.path.insert(0, str(ROOT / "clients"))
    import grafik_client
    monkeypatch.setattr(grafik_client, "ENGINE_URL", f"http://127.0.0.1:{free_port()}")
    with pytest.raises(grafik_client.EngineUnavailable):
        grafik_client.generate("x")


class _FakeProc:
    def __init__(self, code=None):
        self.returncode = code

    def poll(self):
        return self.returncode


def _ensure_setup(monkeypatch, tmp_path, *, up_after, code=None):
    """Engine does not answer the first `up_after` probes; returns the spawned commands."""
    sys.path.insert(0, str(ROOT / "clients"))
    import grafik_client
    (tmp_path / "engine").mkdir()
    (tmp_path / "engine" / "app.py").write_text("")
    monkeypatch.setenv("GRAFIK_DIR", str(tmp_path))
    monkeypatch.setenv("GRAFIK_PYTHON", "python")
    monkeypatch.delenv("GRAFIK_AUTOSTART", raising=False)
    monkeypatch.setattr(grafik_client.time, "sleep", lambda s: None)
    probes, started = [0], []

    def up():
        probes[0] += 1
        return probes[0] > up_after
    monkeypatch.setattr(grafik_client, "_engine_up", up)

    def popen(cmd, **kw):
        started.append((cmd, kw["cwd"]))
        return _FakeProc(code)
    monkeypatch.setattr(grafik_client.subprocess, "Popen", popen)
    return grafik_client, started


def test_client_ensure_engine_starts_it_in_background(monkeypatch, tmp_path):
    gc, started = _ensure_setup(monkeypatch, tmp_path, up_after=3)
    gc.ensure_engine()
    (cmd, cwd), = started
    assert cmd[:4] == ["python", "-m", "uvicorn", "engine.app:app"] and "8300" in cmd
    assert cwd == str(tmp_path) and (tmp_path / "logs" / "engine.log").exists()


def test_client_ensure_engine_leaves_running_engine_alone(monkeypatch, tmp_path):
    gc, started = _ensure_setup(monkeypatch, tmp_path, up_after=0)
    gc.ensure_engine()
    assert started == []


def test_client_ensure_engine_reports_crashed_start(monkeypatch, tmp_path):
    gc, _ = _ensure_setup(monkeypatch, tmp_path, up_after=99, code=1)
    with pytest.raises(gc.EngineUnavailable, match="neodpovídá: spuštění skončilo kódem 1"):
        gc.ensure_engine()


def test_client_ensure_engine_respects_autostart_off(monkeypatch, tmp_path):
    gc, started = _ensure_setup(monkeypatch, tmp_path, up_after=99)
    monkeypatch.setenv("GRAFIK_AUTOSTART", "0")
    with pytest.raises(gc.EngineUnavailable, match="neodpovídá"):
        gc.ensure_engine()
    assert started == []


# -- supersample ------------------------------------------------------------

@pytest.mark.parametrize("size,factor,expected", [
    ("512x512", 2.0, (1024, 1024)),
    ("1024x1024", 2.0, (1440, 1440)),      # capped by 1920*1088 px, aspect kept
    ("1024x576", 1.5, (1536, 864)),
    ("1024x1024", None, (1024, 1024)),
])
def test_supersample_render_size(settings, size, factor, expected):
    fl = FluxLocal(settings, None)
    req = ImageRequest(prompt="x", size=size, supersample=factor)
    w, h = fl.render_size(req)
    assert (w, h) == expected and w % 16 == 0 and h % 16 == 0 and w * h <= settings.max_pixels


def test_supersample_renders_big_returns_requested(api, settings, tmp_path, monkeypatch):
    log = tmp_path / "sd.log"
    monkeypatch.setenv("FAKE_SD_LOG", str(log))
    r = api.post("/api/v2/images", json={"prompt": "tiny figures", "size": "512x512", "supersample": 2})
    job = wait_done(api, r.json()["job_id"])
    assert job["status"] == "done", job["error"]
    sent = json.loads(log.read_text().splitlines()[-1])
    assert (sent["width"], sent["height"]) == (1024, 1024)
    from PIL import Image
    assert Image.open(job["result"]["files"][0]).size == (512, 512)
    prov = api.get(job["images"][0] + "/provenance").json()
    assert prov["params"]["render_size"] == "1024x1024" and prov["params"]["size"] == "512x512"


def test_supersample_rejected_for_paid(api):
    r = api.post("/api/v2/images", json={"prompt": "x", "backend": "nb-pro", "supersample": 2})
    assert r.status_code == 400 and "flux-local" in r.json()["detail"]


# -- fal backend (opt-in, price first) -------------------------------------

from engine.backends import FAL_CATALOG, FalBackend  # noqa: E402


@pytest.mark.parametrize("endpoint,body,usd", [
    ("fal-ai/nano-banana-pro", {"n": 2}, 0.30),
    ("fal-ai/flux/krea", {"size": "1024x1024"}, 0.05),           # 1.05 MP -> 2 MP rounded up
    ("fal-ai/flux-pro/v1.1", {"size": "1024x576"}, 0.04),
    ("fal-ai/flux-2-pro", {"size": "1024x576", "refs": [{"b64": PNG_1PX}]}, 0.18),  # 1 + 5 MP upper bound
])
def test_fal_estimates(endpoint, body, usd):
    assert FalBackend(endpoint).usd_for(ImageRequest(prompt="x", **body)) == pytest.approx(usd)


def test_fal_refs_need_edit_variant_and_unknown_endpoint():
    with pytest.raises(Exception, match="neumí předlohy"):
        FalBackend("fal-ai/flux/krea").validate(ImageRequest(prompt="x", refs=[{"b64": PNG_1PX}]))
    with pytest.raises(Exception, match="katalogu"):
        FalBackend("fal-ai/whatever")


def test_fal_arguments_only_schema_fields():
    req = ImageRequest(prompt="x", size="1024x576")
    a = FalBackend("fal-ai/flux-2-pro").arguments(req, "p", [], 7)
    assert a == {"prompt": "p", "output_format": "png", "seed": 7, "image_size": {"width": 1024, "height": 576}}
    b = FalBackend("fal-ai/nano-banana-pro").arguments(ImageRequest(prompt="x", size="1536x1024"), "p", ["u"], None)
    assert b == {"prompt": "p", "output_format": "png", "aspect_ratio": "3:2", "resolution": "2K", "image_urls": ["u"]}


class FakeFalClient:
    calls: list = []

    def __init__(self, key=None, default_timeout=120):
        assert key

    def upload(self, data, content_type, file_name=None):
        return "https://fal.media/ref.png"

    def subscribe(self, application, arguments):
        FakeFalClient.calls.append((application, arguments))
        return {"images": [{"url": "https://fal.media/out.png"}], "seed": arguments.get("seed")}


def test_fal_job_runs_only_after_confirmation(api, settings, monkeypatch):
    import fal_client
    import httpx as _httpx
    monkeypatch.setattr(fal_client, "SyncClient", FakeFalClient)
    monkeypatch.setenv("FAL_KEY", "test-key")
    real_get = _httpx.get

    def fake_get(url, *a, **kw):
        if url.startswith("https://fal.media/"):
            return _httpx.Response(200, content=b"\x89PNG\r\n\x1a\nfal", request=_httpx.Request("GET", url))
        return real_get(url, *a, **kw)
    monkeypatch.setattr(_httpx, "get", fake_get)
    api.app.state.worker.backends.update({f"fal:{e}": FalBackend(e) for e in FAL_CATALOG})
    FakeFalClient.calls = []

    body = {"prompt": "x", "backend": "fal:fal-ai/flux-2-pro", "size": "1024x576",
            "refs": [{"b64": PNG_1PX, "role": "subject"}]}
    r = api.post("/api/v2/images", json=body)
    assert r.status_code == 402 and r.json()["estimate_usd"] == pytest.approx(0.18)
    assert FakeFalClient.calls == []
    r = api.post("/api/v2/images", json={**body, "confirm_cost": True})
    job = wait_done(api, r.json()["job_id"])
    assert job["status"] == "done", job["error"]
    assert FakeFalClient.calls[0][0] == "fal-ai/flux-2-pro/edit"
    assert FakeFalClient.calls[0][1]["image_urls"] == ["https://fal.media/ref.png"]
    prov = api.get(job["images"][0] + "/provenance").json()
    assert prov["backend"] == "fal:fal-ai/flux-2-pro" and prov["cost_usd"] == pytest.approx(0.18)


# -- G2 studio API ------------------------------------------------------------

def _first_image(api, **body):
    r = api.post("/api/v2/images", json={"prompt": "base", "size": "512x256", "seed": 1, **body})
    job = wait_done(api, r.json()["job_id"])
    assert job["status"] == "done", job["error"]
    return job


def test_edit_in_box_pastes_back_outside(api, settings):
    from io import BytesIO

    from PIL import Image, ImageChops
    base = _first_image(api)
    parent = f"{base['job_id']}/0"
    edit = {"action": "remove", "bbox": [250, 250, 750, 500], "instruction": "two soldiers"}
    r = api.post("/api/v2/images", json={"prompt": "-", "parent": parent, "edit": edit, "seed": 50})
    job = wait_done(api, r.json()["job_id"])
    assert job["status"] == "done", job["error"]
    before = Image.open(job["result"]["files"][0].replace(job["job_id"], base["job_id"])).convert("RGB")
    after = Image.open(BytesIO(api.get(job["images"][0]).content)).convert("RGB")
    assert after.size == before.size == (512, 256)
    diff = ImageChops.difference(before, after)
    assert diff.crop((0, 0, 100, 256)).getbbox() is None, "mimo rámeček musí zůstat beze změny"
    assert diff.crop((140, 70, 250, 185)).getbbox() is not None, "v rámečku se má obraz změnit"
    prov = api.get(job["images"][0] + "/provenance").json()
    assert prov["parent"] == parent and prov["edit"]["action"] == "remove"
    assert prov["refs"][0]["source"] == f"verze {parent}"
    assert '"src_bbox": [250, 250, 750, 500], "tgt_bbox": null' in prov["prompt_sent"]


def test_edit_validation(api):
    r = api.post("/api/v2/images", json={"prompt": "-", "edit": {"action": "remove", "bbox": [1, 1, 2, 2],
                                                                  "instruction": "x"}})
    assert r.status_code == 422
    r = api.post("/api/v2/images", json={"prompt": "-", "parent": "nope-1/0",
                                         "edit": {"action": "add", "bbox": [1, 1, 2, 2], "instruction": "x"}})
    assert r.status_code == 404


def test_lineage_tree_and_request_summary(api):
    base = _first_image(api, refs=[{"b64": PNG_1PX, "role": "subject"}])
    root = f"{base['job_id']}/0"
    v2 = _first_image(api, parent=root)
    v3 = _first_image(api, parent=f"{v2['job_id']}/0",
                      edit={"action": "recolor", "bbox": [0, 0, 500, 500], "instruction": "blue"})
    tree = api.get(f"/api/v2/lineage/{v3['job_id']}/0").json()
    assert [n["ref"] for n in tree] == [root, f"{v2['job_id']}/0", f"{v3['job_id']}/0"]
    assert [n["parent"] for n in tree] == [None, root, f"{v2['job_id']}/0"]
    assert all(n["image"] for n in tree)
    assert "b64" not in json.dumps(api.get(f"/api/v2/jobs/{base['job_id']}").json()["request"])
    assert api.get(f"/api/v2/jobs/{base['job_id']}/refs/0").content[1:4] == b"PNG"
    assert api.get(f"/api/v2/jobs/{base['job_id']}/refs/5").status_code == 404


def test_thumbnail_review_estimate_backends(api):
    from io import BytesIO

    from PIL import Image
    job = _first_image(api)
    t = api.get(job["images"][0] + "?w=128")
    assert t.headers["content-type"] == "image/jpeg" and Image.open(BytesIO(t.content)).width == 128
    prov = api.post(job["images"][0] + "/review", json={"reviewed_by": "operátor"}).json()
    assert prov["reviewed_by"] == "operátor" and prov["reviewed_at"]
    est = api.post("/api/v2/estimate", json={"prompt": "x", "size": "512x512", "supersample": 2}).json()
    assert est["total_usd"] == 0 and est["render_size"] == "1024x1024" and est["eta_s"] > 0
    est = api.post("/api/v2/estimate", json={"prompt": "x", "backend": "nb-pro", "n": 2}).json()
    assert est["total_usd"] == pytest.approx(0.268)
    ids = [b["id"] for b in api.get("/api/v2/backends").json()]
    assert ids[0] == "flux-local"


def test_prompt_expand_needs_confirmation(api, monkeypatch):
    from engine import app as app_mod
    calls = []
    monkeypatch.setattr(app_mod, "expand_prompt", lambda t: calls.append(t) or "A Roman harbour at noon.")
    r = api.post("/api/v2/prompt/expand", json={"text": "římský přístav"})
    assert r.status_code == 402 and r.json()["estimate_usd"] == 0.01 and calls == []
    r = api.post("/api/v2/prompt/expand", json={"text": "římský přístav", "confirm_cost": True})
    assert r.json()["prompt"] == "A Roman harbour at noon." and calls == ["římský přístav"]
    assert api.get("/api/v2/costs").json()["entries"][-1]["backend"] == "claude:prompt-expand"


def test_repeat_keeps_refs_new_seed_and_lineage(api):
    base = _first_image(api, refs=[{"b64": PNG_1PX, "role": "geometry", "source": "lod.png"}])
    r = api.post(f"/api/v2/jobs/{base['job_id']}/repeat", json={})
    job = wait_done(api, r.json()["job_id"])
    assert job["status"] == "done", job["error"]
    assert job["request"]["parent"] == f"{base['job_id']}/0" and job["request"]["seed"] is None
    prov = api.get(job["images"][0] + "/provenance").json()
    assert prov["refs"][0]["source"] == "lod.png" and prov["refs"][0]["sha256"]
    r = api.post(f"/api/v2/jobs/{base['job_id']}/repeat", json={"n": 0})
    assert r.status_code == 202


def test_repeat_of_edit_is_sibling_with_single_parent_ref(api):
    base = _first_image(api)
    parent = f"{base['job_id']}/0"
    e = _first_image(api, parent=parent, edit={"action": "add", "bbox": [0, 0, 500, 500], "instruction": "strom"})
    r = api.post(f"/api/v2/jobs/{e['job_id']}/repeat", json={})
    job = wait_done(api, r.json()["job_id"])
    assert job["request"]["parent"] == parent
    prov = api.get(job["images"][0] + "/provenance").json()
    assert [x["source"] for x in prov["refs"]] == [f"verze {parent}"]


# -- Czech -> English translation layer ---------------------------------------

@pytest.fixture
def fake_claude(monkeypatch):
    from engine import translate
    calls = []

    def fake(content, max_tokens, what):
        calls.append(content)
        text = content if isinstance(content, str) else content[-1]["text"]
        return "the fox has silver-grey fur" if "image-edit" in text else "A red lighthouse on a rocky coast in a storm."
    monkeypatch.setattr(translate, "claude_text", fake)
    return calls


def test_czech_prompt_translated_with_price_first_then_cached(api, fake_claude):
    body = {"prompt": "Červený maják na skalnatém pobřeží za bouře", "size": "256x256"}
    r = api.post("/api/v2/images", json=body)
    assert r.status_code == 402 and r.json()["estimate_usd"] == 0.01 and fake_claude == []
    assert r.json()["items"][0]["kind"] == "translation"
    r = api.post("/api/v2/images", json={**body, "confirm_cost": True})
    job = wait_done(api, r.json()["job_id"])
    assert job["status"] == "done", job["error"]
    prov = api.get(job["images"][0] + "/provenance").json()
    assert prov["prompt_sent"].startswith("A red lighthouse on a rocky coast in a storm.")
    assert prov["prompt_original"] == body["prompt"] and prov["translations"][0]["paid"] is True
    assert "FLUX" in fake_claude[0]
    # same text again: cached -> free, no confirmation needed
    est = api.post("/api/v2/estimate", json=body).json()
    assert est["total_usd"] == 0
    assert api.post("/api/v2/images", json=body).status_code == 202


def test_czech_edit_instruction_translated_into_edit_template(api, fake_claude):
    base = _first_image(api)
    edit = {"action": "recolor", "bbox": [100, 100, 900, 900], "instruction": "liška má stříbrně šedou srst"}
    r = api.post("/api/v2/images", json={"prompt": "-", "parent": f"{base['job_id']}/0", "edit": edit,
                                         "confirm_cost": True})
    job = wait_done(api, r.json()["job_id"])
    prov = api.get(job["images"][0] + "/provenance").json()
    assert prov["prompt_sent"].startswith("In <ref_image_0>, change <edit_1>: the fox has silver-grey fur.")
    assert prov["prompt_original"] == edit["instruction"]


def test_translation_off_and_english_untouched(api, fake_claude):
    assert api.post("/api/v2/estimate", json={"prompt": "Maják", "translate": "off"}).json()["total_usd"] == 0
    assert api.post("/api/v2/estimate", json={"prompt": "A lighthouse"}).json()["total_usd"] == 0
    assert api.post("/api/v2/estimate", json={"prompt": "Červený maják"}).json()["total_usd"] == 0.01
    assert fake_claude == []


def test_translation_guide_per_generator(fake_claude, tmp_path):
    from engine.translate import Translator
    t = Translator(tmp_path / "t.jsonl")
    t.translate("nb-pro", "prompt", "Červený maják")
    t.translate("fal:fal-ai/flux-2-pro", "prompt", "Červený maják")
    assert "Gemini" in fake_claude[0] and "FLUX" in fake_claude[1]
    assert Translator(tmp_path / "t.jsonl").pending(ImageRequest(prompt="Červený maják", backend="nb-pro")) == (0, 0)


def test_failed_translation_is_not_cached_and_fails_readably(monkeypatch, tmp_path):
    from engine import translate
    from engine.backends import BackendError
    answers, calls = ["", "maják"], []
    monkeypatch.setattr(translate, "claude_text", lambda c, m, w: calls.append(c) or answers[len(calls) - 1])
    t = translate.Translator(tmp_path / "t.jsonl")
    for expected in ("prázdná", "pořád česky"):
        with pytest.raises(BackendError, match=expected):
            t.translate("flux-local", "prompt", "Červený maják")
        assert not (tmp_path / "t.jsonl").exists() and t._cache == {}
    assert len(calls) == 2  # the second call went to the API again
    assert t.pending(ImageRequest(prompt="Červený maják")) == (1, 0)


def test_failed_translation_fails_the_job(api, monkeypatch):
    from engine import translate
    monkeypatch.setattr(translate, "claude_text", lambda c, m, w: "Červený maják na pobřeží")
    r = api.post("/api/v2/images", json={"prompt": "Červený maják", "size": "256x256", "confirm_cost": True})
    job = wait_done(api, r.json()["job_id"])
    assert job["status"] == "failed" and "pořád česky" in job["error"]


def test_still_czech_allows_place_names_and_quoted_lettering():
    from engine.translate import still_czech
    assert not still_czech("A Gothic cathedral in Kutná Hora at dusk, seen from the river bank")
    assert not still_czech('A shop sign reading "Pekařství U Zlatého klasu" above the door')
    assert still_czech("Červený maják") and still_czech("  ")


def test_rules_keep_quoted_lettering_verbatim(fake_claude, tmp_path):
    from engine.backends import EXPAND_INSTRUCTION
    from engine.translate import Translator
    Translator(tmp_path / "t.jsonl").translate("flux-local", "prompt", 'Cedule s nápisem „Pekárna“')
    for text in (fake_claude[0], EXPAND_INSTRUCTION):
        assert "original language and spelling" in text


def test_expand_instruction_whole_parts_whole_and_style_last():
    from engine.backends import EXPAND_INSTRUCTION
    i = EXPAND_INSTRUCTION
    assert i.index("whole picture") < i.index("background to foreground") < i.index("whole again")
    assert "last sentence names the overall style and type of image" in i
    for rule in ("physically consistent", "no judgements", "exact counts", "concrete visible changes"):
        assert rule in i


def test_claude_text_disables_haiku_thinking_and_rejects_empty_answer(monkeypatch):
    from engine import backends
    from engine.backends import BackendError
    sent, replies = [], [{"content": [{"type": "thinking", "thinking": ""}], "stop_reason": "max_tokens"},
                         {"content": [{"type": "text", "text": " A harbour. "}], "stop_reason": "end_turn"}]

    class R:
        def __init__(self, data):
            self.data = data

        def raise_for_status(self):
            pass

        def json(self):
            return self.data

    monkeypatch.setattr(backends, "get_key", lambda name: "test")
    monkeypatch.setattr(backends.httpx, "post", lambda url, headers, json, timeout: sent.append(json) or R(replies.pop(0)))
    with pytest.raises(BackendError, match="žádný text.*max_tokens"):
        backends.claude_text("x", 500, "rozepsání zadání")
    assert backends.claude_text("x", 500, "soudce", model="claude-sonnet-5-5") == "A harbour."
    assert sent[0]["thinking"] == {"type": "disabled"} and "thinking" not in sent[1]


def test_eval_keypoints_verdict_is_last_occurrence():
    import importlib.util
    spec = importlib.util.spec_from_file_location("eval_keypoints", Path(__file__).parents[1] / "scripts" / "eval_keypoints.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.verdict("I could accept the sky, but the logo is missing.\nreject") == "reject"
    assert mod.verdict("No reason to reject: the hat is red.\nAccept") == "accept"
    assert mod.verdict("unclear") is None
    sample = [{"points": [("a", "x")] * 4}] * 24
    assert mod.estimate(sample, "claude-haiku-5-5", False) < mod.estimate(sample, "claude-sonnet-5-5", False) < 2


def test_edit_translation_sends_crop_of_box_and_keys_cache_by_it(api, fake_claude):
    base = _first_image(api)
    parent = f"{base['job_id']}/0"
    edit = {"action": "recolor", "bbox": [100, 100, 600, 900], "instruction": "přebarvi lišku na stříbrnou"}
    body = {"prompt": "-", "parent": parent, "edit": edit}
    est = api.post("/api/v2/estimate", json=body).json()
    assert [i["kind"] for i in est["items"]] == ["translation", "translation"] and 0.01 < est["total_usd"] < 0.02
    job = wait_done(api, api.post("/api/v2/images", json={**body, "confirm_cost": True}).json()["job_id"])
    assert job["status"] == "done", job["error"]
    content = fake_claude[-1]
    assert content[0]["type"] == "image" and "actually visible" in content[1]["text"]
    import base64
    from io import BytesIO
    from PIL import Image
    crop = Image.open(BytesIO(base64.b64decode(content[0]["source"]["data"])))
    assert max(crop.size) <= 512
    prov = api.get(job["images"][0] + "/provenance").json()
    assert prov["translations"][0]["crop"] is True
    # same words: cached for the same box, paid again for another box
    assert api.post("/api/v2/estimate", json=body).json()["total_usd"] == 0
    other = {**body, "edit": {**edit, "bbox": [0, 0, 300, 300]}}
    assert api.post("/api/v2/estimate", json=other).json()["total_usd"] > 0


# -- G3: reference library, Commons, Pinterest, historical-object workflow -----

def _png_bytes(color=(200, 30, 30), size=(64, 32)):
    from io import BytesIO

    from PIL import Image
    buf = BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


def test_reflib_add_dedupe_and_pinterest_license(tmp_path):
    from engine.reflib import PINTEREST_LICENSE, RefLibrary, origin_of
    lib = RefLibrary(tmp_path / "lib")
    a = lib.add(_png_bytes(), origin="pinterest", page_url="https://www.pinterest.com/pin/1/")
    b = lib.add(_png_bytes(), origin="upload")
    assert a["id"] == b["id"] and len(lib.list()) == 1
    assert a["license"] == PINTEREST_LICENSE and a["seen"] is False
    assert lib.mark_seen(a["id"])["seen"] is True
    assert origin_of("https://i.pinimg.com/originals/x.jpg") == "pinterest"
    assert origin_of("https://upload.wikimedia.org/x.jpg") == "commons"


def test_pin_page_resolves_og_image(tmp_path, monkeypatch):
    import httpx as _httpx

    from engine import reflib
    page = '<html><meta property="og:image" content="https://i.pinimg.com/originals/ab/cd.jpg"></html>'

    def fake_get(url, **kw):
        req = _httpx.Request("GET", url)
        if "pinterest.com/pin" in url:
            return _httpx.Response(200, text=page, headers={"content-type": "text/html"}, request=req)
        return _httpx.Response(200, content=_png_bytes(), headers={"content-type": "image/png"}, request=req)
    monkeypatch.setattr(reflib.httpx, "get", fake_get)
    meta = reflib.RefLibrary(tmp_path / "lib").add_url("https://www.pinterest.com/pin/123/")
    assert meta["origin"] == "pinterest" and meta["source_url"] == "https://www.pinterest.com/pin/123/"


def test_commons_search_parses_license_and_author(monkeypatch):
    from engine import commons
    fake = {"query": {"pages": {"1": {"index": 1, "title": "File:Ship model.jpg", "imageinfo": [{
        "thumburl": "https://upload.wikimedia.org/thumb/ship.jpg", "thumbwidth": 320, "url": "https://u/ship.jpg",
        "descriptionurl": "https://commons.wikimedia.org/wiki/File:Ship_model.jpg", "width": 3000, "height": 2000,
        "extmetadata": {"LicenseShortName": {"value": "CC BY-SA 4.0"},
                        "Artist": {"value": '<a href="//x">Zbyna&nbsp;Zl</a>'}}}]}}}}
    seen = {}
    monkeypatch.setattr(commons, "_call", lambda params: seen.update(params) or fake)
    r = commons.search("roman warship")
    assert seen["gsrsearch"] == "roman warship filetype:bitmap"
    assert r[0]["license"] == "CC BY-SA 4.0" and r[0]["author"] == "Zbyna Zl" and r[0]["title"] == "Ship model.jpg"


def test_api_refs_and_ref_id_provenance(api):
    import base64
    r = api.post("/api/v2/refs", json={"b64": base64.b64encode(_png_bytes()).decode(), "title": "loď",
                                       "author": "Zbyna Zl", "license": "CC BY-SA 4.0"})
    assert r.status_code == 201
    ref = r.json()
    assert api.get(ref["image"]).content[1:4] == b"PNG"
    assert api.get(ref["image"] + "?w=64").headers["content-type"] == "image/jpeg"
    assert [x["id"] for x in api.get("/api/v2/refs").json()] == [ref["id"]]
    job = _first_image(api, refs=[{"ref_id": ref["id"], "role": "geometry"}])
    prov = api.get(job["images"][0] + "/provenance").json()
    assert prov["refs"][0]["ref_id"] == ref["id"]
    assert prov["refs"][0]["license"] == "CC BY-SA 4.0" and prov["refs"][0]["author"] == "Zbyna Zl"
    assert api.post("/api/v2/images", json={"prompt": "x", "refs": [{"ref_id": "nope-1"}]}).status_code == 404
    # repeat re-validates the stored request (path + ref_id together)
    assert api.post(f"/api/v2/jobs/{job['job_id']}/repeat", json={}).status_code == 202


def test_historical_workflow_steps(api, tmp_path, monkeypatch):
    import base64
    log = tmp_path / "sd.log"
    monkeypatch.setenv("FAKE_SD_LOG", str(log))
    ref = api.post("/api/v2/refs", json={"b64": base64.b64encode(_png_bytes(size=(96, 32))).decode()}).json()
    wf = api.post("/api/v2/workflows/historical", json={"object": "Roman quinquereme of the First Punic War",
                                                        "refs": [{"ref_id": ref["id"], "role": "geometry"}]}).json()
    assert api.post(f"/api/v2/workflows/{wf['id']}/rotate", json={}).status_code == 400  # no elevation yet
    est = api.post(f"/api/v2/workflows/{wf['id']}/side", json={"n": 2, "estimate_only": True}).json()
    assert est["total_usd"] == 0 and est["size"] == "1920x640"
    r = api.post(f"/api/v2/workflows/{wf['id']}/side", json={"n": 2})
    side = wait_done(api, r.json()["job_id"])
    assert side["status"] == "done", side["error"]
    assert "pure side elevation" in side["result"]["prompt_sent"]
    wf = api.get(f"/api/v2/workflows/{wf['id']}").json()
    assert wf["side_job"] == side["job_id"]
    wf = api.patch(f"/api/v2/workflows/{wf['id']}", json={"side_pick": f"{side['job_id']}/1"}).json()
    r = api.post(f"/api/v2/workflows/{wf['id']}/rotate", json={"view": "34_right", "background": "sea", "n": 1})
    rot = wait_done(api, r.json()["job_id"])
    assert rot["status"] == "done", rot["error"]
    assert rot["request"]["parent"] == f"{side['job_id']}/1"
    assert "front right" in rot["result"]["prompt_sent"] and "calm smooth sea" in rot["result"]["prompt_sent"]
    sent = json.loads(log.read_text().splitlines()[-1])
    assert (sent["width"], sent["height"]) == (1920, 1072) and sent["ref_images"] == 1
    wf = api.get(f"/api/v2/workflows/{wf['id']}").json()
    assert wf["rotate_job"] == rot["job_id"] and wf["view"] == "34_right"
    assert api.patch(f"/api/v2/workflows/{wf['id']}", json={"pick": "nope-1/0"}).status_code == 404


def test_workflow_czech_object_is_translated(api, fake_claude):
    import base64
    ref = api.post("/api/v2/refs", json={"b64": base64.b64encode(_png_bytes(size=(80, 40))).decode()}).json()
    wf = api.post("/api/v2/workflows/historical", json={"object": "římská kvinquerema",
                                                        "refs": [{"ref_id": ref["id"]}]}).json()
    r = api.post(f"/api/v2/workflows/{wf['id']}/side", json={})
    assert r.status_code == 402 and r.json()["items"][0]["kind"] == "translation"


def test_flux_refs_share_one_megapixel_budget(settings):
    import base64
    from io import BytesIO

    from PIL import Image
    fl = FluxLocal(settings, None)
    big, small = _png_bytes(size=(2048, 1028)), _png_bytes(size=(736, 387))
    p = fl.payload(ImageRequest(prompt="x", size="1920x640"), "x", [small, big], 1)
    sizes = [Image.open(BytesIO(base64.b64decode(b))).size for b in p["ref_images"]]
    assert sum(w * h for w, h in sizes) <= FluxLocal.REF_MAX_PIXELS
    assert abs(sizes[1][0] / sizes[1][1] - 2048 / 1028) < 0.01
    parent = _png_bytes(size=(1344, 768))
    p = fl.payload(ImageRequest(prompt="x", size="1344x768"), "x", [parent], 1)
    assert Image.open(BytesIO(base64.b64decode(p["ref_images"][0]))).size == (1344, 768)


def test_out_of_vram_restarts_own_server_and_retries(sd, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_SD_OOM_ONCE", str(tmp_path / "oom.marker"))
    sd.ensure_running()
    first_pid = json.loads(sd.state_path.read_text())["pid"]
    out = sd.generate({"prompt": "x", "width": 256, "height": 256, "seed": 1})
    assert out[0][1:4] == b"PNG"
    assert json.loads(sd.state_path.read_text())["pid"] != first_pid
    assert "restart" in (sd.s.log_dir / "engine-events.log").read_text(encoding="utf-8")


def test_settings_status_never_exposes_key_values(api, monkeypatch):
    monkeypatch.setenv("FAL_KEY", "secret-fal-value")
    st = api.get("/api/v2/settings").json()
    assert "secret-fal-value" not in json.dumps(st)
    fal = next(x for x in st["services"] if x["id"] == "fal")
    assert fal["connected"] is True
    assert next(x for x in st["services"] if x["id"] == "pinterest")["note"].startswith("bez účtu")
    assert st["flux_local"]["min_free_vram_mib"] == 4600 and "today_usd" in st["costs"]


# -- G4: style library (sc-20 … sc-23) ---------------------------------------

STYLE_CARD = {"label": "Akvarel přírodovědný", "medium": "watercolour on rough cotton paper, loose washes",
              "light": "soft diffuse daylight", "line": "fine sepia ink contours",
              "composition": "single specimen on a white page", "avoid": "photographic detail",
              "signature": "zrnitý papír · sépiová linka", "palette": [{"hex": "#c46a2c"}, {"hex": "#6F7D5A"}]}


def test_palette_kmeans_finds_the_colours():
    from io import BytesIO

    from PIL import Image

    from engine.styles import palette
    img = Image.new("RGB", (100, 100), (200, 30, 30))
    img.paste((30, 60, 200), (0, 0, 100, 25))
    buf = BytesIO()
    img.save(buf, "PNG")
    p = palette([buf.getvalue()], k=2)
    assert [c["hex"] for c in p] == ["#c81e1e", "#1e3cc8"]
    assert p[0]["share"] == 0.75 and p[0]["name"] == "red" and p[1]["name"] == "blue"


def test_style_card_files_and_prompt_words(api, settings):
    r = api.post("/api/v2/styles", json=STYLE_CARD)
    assert r.status_code == 201, r.text
    card = r.json()
    assert card["slug"] == "akvarel-prirodovedny" and card["origin"] == "manual"
    d = settings.styles_dir / "akvarel-prirodovedny"
    assert json.loads((d / "style.json").read_text(encoding="utf-8"))["palette"][1]["hex"] == "#6f7d5a"
    md = (d / "STYLE.md").read_text(encoding="utf-8")
    assert md.startswith("# Akvarel přírodovědný") and "## Podpisové znaky" in md and "Style: Watercolour" in md
    assert card["prompt"].startswith("Watercolour on rough cotton paper") and "terracotta #c46a2c" in card["prompt"]
    assert api.post("/api/v2/styles", json=STYLE_CARD).status_code == 409
    assert api.post("/api/v2/styles", json={"label": "Prázdný"}).status_code == 400
    assert [c["slug"] for c in api.get("/api/v2/styles").json()] == ["akvarel-prirodovedny"]


def test_style_slug_goes_to_prompt_as_words_never_as_image(api, tmp_path, monkeypatch):
    import base64
    log = tmp_path / "sd.log"
    monkeypatch.setenv("FAKE_SD_LOG", str(log))
    api.post("/api/v2/styles", json=STYLE_CARD)
    api.post("/api/v2/styles/akvarel-prirodovedny/samples", json={"b64": base64.b64encode(_png_bytes()).decode()})
    r = api.post("/api/v2/images", json={"prompt": "A heron", "size": "256x256", "style": "akvarel-prirodovedny"})
    job = wait_done(api, r.json()["job_id"])
    assert job["status"] == "done", job["error"]
    assert "Style: Watercolour on rough cotton paper" in job["result"]["prompt_sent"]
    assert not json.loads(log.read_text().splitlines()[-1]).get("ref_images")  # sc-21: the sample never goes as pixels
    prov = api.get(job["images"][0] + "/provenance").json()
    assert prov["style_id"] == "akvarel-prirodovedny"
    # free text stays text, an unknown style_id is an error
    r = api.post("/api/v2/estimate", json={"prompt": "x", "style": "pencil sketch"})
    assert r.status_code == 200
    assert api.post("/api/v2/images", json={"prompt": "x", "style_id": "nope"}).status_code == 404


def test_style_samples_from_job_and_trash(api, settings):
    api.post("/api/v2/styles", json=STYLE_CARD)
    base = _first_image(api)
    card = api.post("/api/v2/styles/akvarel-prirodovedny/samples", json={"job": f"{base['job_id']}/0"}).json()
    assert card["samples"] == ["1.jpg"] and card["sample_urls"][0].endswith("/samples/1.jpg")
    assert api.get(card["sample_urls"][0]).headers["content-type"] == "image/jpeg"
    assert api.delete("/api/v2/styles/akvarel-prirodovedny/samples/1.jpg").json()["samples"] == []
    moved = api.delete("/api/v2/styles/akvarel-prirodovedny").json()["moved_to"]
    assert ".trash" in moved and (Path(moved) / "style.json").exists()
    assert api.get("/api/v2/styles/akvarel-prirodovedny").status_code == 404
    assert api.get("/api/v2/styles/../etc").status_code in (400, 404)


def test_style_palette_free_describe_paid(api, settings, monkeypatch):
    import base64

    from engine import app as app_mod
    imgs = [base64.b64encode(_png_bytes((200, 30, 30))).decode(), base64.b64encode(_png_bytes((30, 60, 200))).decode()]
    pal = api.post("/api/v2/styles/palette", json={"b64": imgs}).json()["palette"]
    assert {c["hex"] for c in pal} == {"#c81e1e", "#1e3cc8"}
    calls = []
    monkeypatch.setattr(app_mod, "describe_style_card", lambda images: calls.append(len(images)) or {
        "label": "Test", "note": "", "medium": "flat vector", "light": "", "line": "", "composition": "",
        "avoid": "", "signature": ""})
    r = api.post("/api/v2/styles/describe", json={"b64": imgs})
    assert r.status_code == 402 and r.json()["estimate_usd"] == 0.01 and calls == []
    d = api.post("/api/v2/styles/describe", json={"b64": imgs, "confirm_cost": True}).json()
    assert calls == [2] and d["medium"] == "flat vector" and d["origin"] == "detected" and len(d["palette"]) == 2
    assert api.get("/api/v2/costs").json()["entries"][-1]["backend"] == "claude:style-card"
    assert api.post("/api/v2/styles/palette", json={}).status_code == 400
    assert api.post("/api/v2/styles/palette", json={"b64": imgs * 3}).status_code == 400


def test_describe_style_card_parses_json(monkeypatch):
    import base64

    from engine import backends
    sent = []
    monkeypatch.setattr(backends, "claude_text", lambda content, mt, what: sent.append(content) or
                        'Here: {"label": "Akvarel", "medium": "watercolour", "light": "soft"}')
    card = backends.describe_style_card([_png_bytes(size=(2000, 1000))])
    assert card["medium"] == "watercolour" and card["avoid"] == ""
    from io import BytesIO

    from PIL import Image
    assert max(Image.open(BytesIO(base64.b64decode(sent[0][0]["source"]["data"]))).size) == 768
    monkeypatch.setattr(backends, "claude_text", lambda *a: "no json")
    with pytest.raises(backends.BackendError, match="není JSON"):
        backends.describe_style_card([_png_bytes()])


def test_czech_style_card_is_translated_before_the_prompt(api, fake_claude):
    api.post("/api/v2/styles", json={"label": "Tužka", "medium": "tužková kresba na drsném papíře"})
    body = {"prompt": "A heron", "size": "256x256", "style": "tuzka"}
    est = api.post("/api/v2/estimate", json=body).json()
    assert [i["kind"] for i in est["items"]] == ["translation"]
    job = wait_done(api, api.post("/api/v2/images", json={**body, "confirm_cost": True}).json()["job_id"])
    assert job["status"] == "done", job["error"]
    assert "style descriptors" in fake_claude[0] and "Tužková kresba" in fake_claude[0]
    prov = api.get(job["images"][0] + "/provenance").json()
    assert prov["style_id"] == "tuzka" and prov["translations"][0]["field"] == "style"
    assert "užková" not in prov["prompt_sent"]


# -- write-ahead cost ledger (GRAFIK#14) --------------------------------------

def _fal_env(api, monkeypatch, subscribe):
    import fal_client
    import httpx as _httpx

    class Client(FakeFalClient):
        def subscribe(self, application, arguments):
            return subscribe(application, arguments)

    monkeypatch.setattr(fal_client, "SyncClient", Client)
    monkeypatch.setenv("FAL_KEY", "test-key")
    real_get = _httpx.get
    monkeypatch.setattr(_httpx, "get", lambda url, *a, **kw: _httpx.Response(
        200, content=b"\x89PNG\r\n\x1a\nfal", request=_httpx.Request("GET", url))
        if url.startswith("https://fal.media/") else real_get(url, *a, **kw))
    api.app.state.worker.backends.update({f"fal:{e}": FalBackend(e) for e in FAL_CATALOG})


def _cost_rows(settings):
    return [json.loads(line) for line in settings.costs_path.read_text(encoding="utf-8").splitlines() if line]


FAL_BODY = {"prompt": "x", "backend": "fal:fal-ai/flux-2-pro", "size": "1024x576", "confirm_cost": True}


def test_fal_cost_is_pending_before_the_call_and_ok_after(api, settings, monkeypatch):
    seen = {}

    def subscribe(application, arguments):
        seen["during"] = _cost_rows(settings)
        return {"images": [{"url": "https://fal.media/out.png"}], "seed": 1}
    _fal_env(api, monkeypatch, subscribe)
    job = wait_done(api, api.post("/api/v2/images", json=FAL_BODY).json()["job_id"])
    assert job["status"] == "done", job["error"]
    assert [r["status"] for r in seen["during"]] == ["pending"]
    assert seen["during"][0]["backend"] == "fal:fal-ai/flux-2-pro" and seen["during"][0]["usd"] > 0
    assert [r["status"] for r in _cost_rows(settings)] == ["pending", "ok"]
    costs = api.get("/api/v2/costs").json()
    assert costs["total_usd"] == pytest.approx(seen["during"][0]["usd"])  # not counted twice
    assert costs["pending"] == []


def test_fal_exception_leaves_failed_row_with_estimate(api, settings, monkeypatch):
    def subscribe(application, arguments):
        raise TimeoutError("spojení spadlo")
    _fal_env(api, monkeypatch, subscribe)
    job = wait_done(api, api.post("/api/v2/images", json=FAL_BODY).json()["job_id"])
    assert job["status"] == "failed"
    rows = _cost_rows(settings)
    assert [r["status"] for r in rows] == ["pending", "failed"]
    assert rows[0]["backend"] == "fal:fal-ai/flux-2-pro" and rows[1]["est_usd"] == rows[0]["usd"] > 0
    assert api.get("/api/v2/costs").json()["total_usd"] == 0


def test_unfinished_pending_row_counts_as_spent(api, settings):
    settings.library_dir.mkdir(parents=True, exist_ok=True)
    settings.costs_path.write_text(json.dumps(
        {"ts": "2026-10-26T10:00:00", "job_id": "j1", "backend": "fal:x", "n": 1, "usd": 0.18, "items": [],
         "status": "pending"}) + "\n", encoding="utf-8")
    costs = api.get("/api/v2/costs").json()
    assert costs["total_usd"] == 0.18 and [p["job_id"] for p in costs["pending"]] == ["j1"]
