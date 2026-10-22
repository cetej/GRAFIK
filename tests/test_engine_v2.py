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
