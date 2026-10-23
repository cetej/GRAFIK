"""Stand-in for sd-server.exe in tests: same endpoints and JSON shapes as the
real server (docs/capabilities/sd-server-master-987.md), returns a solid PNG.

Usage: python fake_sd_server.py --listen-port N [ignored sd-server args...]
Env FAKE_SD_DELAY_S: seconds a job stays running. FAKE_SD_LOG: append payloads (JSON lines).
FAKE_SD_OOM_ONCE=<path>: the first job ever (marker file absent) fails like an out-of-VRAM run.
"""
import base64
import io
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PIL import Image

PORT = int(sys.argv[sys.argv.index("--listen-port") + 1])
DELAY = float(os.environ.get("FAKE_SD_DELAY_S", "0.2"))
LOG = os.environ.get("FAKE_SD_LOG")
jobs: dict = {}
counter = [0]
lock = threading.Lock()


def png(w, h, seed):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), ((seed * 37) % 256, 120, 200)).save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/v1/models":
            return self._json(200, {"data": [{"id": "sd-cpp-local", "object": "model"}]})
        if self.path.startswith("/sdcpp/v1/jobs/"):
            job = jobs.get(self.path.rsplit("/", 1)[1])
            if not job:
                return self._json(404, {"error": "not found"})
            if time.time() - job["t"] < DELAY:
                return self._json(200, {"id": job["id"], "status": "running"})
            marker = os.environ.get("FAKE_SD_OOM_ONCE")
            if marker and not os.path.exists(marker):
                open(marker, "w").close()
                print("[W] model manager cannot make enough memory available on CUDA0", flush=True)
                return self._json(200, {"id": job["id"], "status": "failed",
                                        "error": {"code": "generation_failed", "message": "no results"}})
            p = job["p"]
            return self._json(200, {"id": job["id"], "status": "completed", "error": None, "result": {
                "images": [{"b64_json": png(p["width"], p["height"], p["seed"]), "index": 0}],
                "output_format": "png"}})
        self._json(404, {"error": "no route"})

    def do_POST(self):
        if self.path != "/sdcpp/v1/img_gen":
            return self._json(404, {"error": "no route"})
        p = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if LOG:
            with lock, open(LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps({k: (len(v) if k == "ref_images" else v) for k, v in p.items()}) + "\n")
        with lock:
            counter[0] += 1
            jid = f"job_{counter[0]}"
            jobs[jid] = {"id": jid, "t": time.time(), "p": p}
        self._json(202, {"id": jid, "poll_url": f"/sdcpp/v1/jobs/{jid}", "status": "queued"})


ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
