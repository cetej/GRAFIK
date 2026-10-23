"""grafik_client — the one way projects ask GRAFIK Engine for an image.

Copy this single file into a project; it needs only the Python standard library.

    from grafik_client import generate
    paths = generate("red apple on a table", size="1024x1024", out_dir="out")
    paths = generate("The ship in <ref_image_0> from above", refs=[{"path": "ship.png", "role": "geometry"}])

The default backend is the local FLUX (0 USD). A paid backend runs only when you
name it AND pass confirm_cost=True; without it you get CostConfirmationRequired
with the estimate and nothing runs. The client never switches backends on its
own: when the local generator is unavailable you get EngineUnavailable.

CLI: python grafik_client.py generate "prompt" [--size 1024x1024] [--ref path[:role]] [--out DIR]
     python grafik_client.py ref-add <image or pin URL> [--page URL] [--title T]
     python grafik_client.py health
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ENGINE_URL = os.environ.get("GRAFIK_ENGINE_URL", "http://127.0.0.1:8300")


class GrafikError(RuntimeError):
    pass


class EngineUnavailable(GrafikError):
    """Engine is not running or the local generator failed. Never auto-fallback to paid."""


class CostConfirmationRequired(GrafikError):
    def __init__(self, estimate_usd: float, items: list):
        self.estimate_usd = estimate_usd
        self.items = items
        super().__init__(f"Placená operace ~{estimate_usd} USD — zopakujte s confirm_cost=True. {items}")


def _request(method: str, path: str, body: dict | None = None, timeout: float = 30):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(ENGINE_URL + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if r.headers.get_content_type() == "application/json" else raw)
    except urllib.error.HTTPError as e:
        payload = e.read()
        try:
            return e.code, json.loads(payload)
        except ValueError:
            return e.code, {"detail": payload.decode("utf-8", "replace")}
    except (urllib.error.URLError, OSError) as e:
        raise EngineUnavailable(f"GRAFIK Engine na {ENGINE_URL} neodpovídá ({e}). Spusťte start-grafik.bat.") from e


def health() -> dict:
    return _request("GET", "/api/v2/health")[1]


def add_ref(url: str, page_url: str | None = None, title: str | None = None, author: str | None = None,
            license: str | None = None) -> dict:
    """Put an image into GRAFIK's reference library ("Schránka předloh"). `url` may be the image
    itself or a Pinterest pin page; use the returned `id` as refs=[{"ref_id": id, "role": ...}]."""
    status, data = _request("POST", "/api/v2/refs", {"url": url, "page_url": page_url, "title": title,
                                                     "author": author, "license": license}, timeout=90)
    if status != 201:
        raise GrafikError(f"předlohu se nepodařilo přidat ({status}): {data.get('detail')}")
    return data


def _ref_payload(ref) -> dict:
    ref = {"path": ref} if isinstance(ref, (str, Path)) else dict(ref)
    if "path" in ref and "b64" not in ref:
        # Send pixels, not a path: the Engine may not see the caller's working dir.
        p = Path(ref.pop("path"))
        ref["b64"] = base64.b64encode(p.read_bytes()).decode("ascii")
        ref.setdefault("source", str(p))
    return ref


def submit(prompt: str, *, backend: str = "flux-local", size: str = "1024x1024", n: int = 1,
           seed: int | None = None, steps: int | None = None, refs: list | None = None,
           layout: list | None = None, style: str | None = None, no_text: bool = True,
           supersample: float | None = None, caller: str | None = None, confirm_cost: bool = False) -> str:
    body = {"prompt": prompt, "backend": backend, "size": size, "n": n, "seed": seed, "steps": steps,
            "refs": [_ref_payload(r) for r in refs or []], "layout": layout or [], "style": style,
            "no_text": no_text, "supersample": supersample, "caller": caller or Path(sys.argv[0]).stem or "client",
            "confirm_cost": confirm_cost}
    status, data = _request("POST", "/api/v2/images", body)
    if status == 402:
        raise CostConfirmationRequired(data["estimate_usd"], data.get("items", []))
    if status != 202:
        raise GrafikError(f"Engine odmítl požadavek ({status}): {data.get('detail')}")
    return data["job_id"]


def wait(job_id: str, timeout: float = 900, poll_s: float = 2.0, on_status=None) -> dict:
    deadline = time.monotonic() + timeout
    while True:
        status, job = _request("GET", f"/api/v2/jobs/{job_id}")
        if status != 200:
            raise GrafikError(f"úloha {job_id}: {job.get('detail')}")
        if on_status:
            on_status(job)
        if job["status"] == "done":
            return job
        if job["status"] in ("failed", "cancelled"):
            raise EngineUnavailable(f"úloha {job_id} {job['status']}: {job.get('error')}")
        if time.monotonic() > deadline:
            raise GrafikError(f"úloha {job_id} nedoběhla do {int(timeout)} s (stav {job['status']})")
        time.sleep(poll_s)


def download(job: dict, out_dir: str | Path) -> list[Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for n, url in enumerate(job["images"]):
        status, data = _request("GET", url, timeout=120)
        if status != 200:
            raise GrafikError(f"stažení {url} selhalo ({status})")
        p = out / f"{job['job_id']}-{n}.png"
        p.write_bytes(data)
        paths.append(p)
    return paths


def generate(prompt: str, *, out_dir: str | Path = ".", timeout: float = 900, **kw) -> list[Path]:
    """Submit, wait, download. Returns local PNG paths (a copy; the Engine keeps the original)."""
    return download(wait(submit(prompt, **kw), timeout=timeout), out_dir)


def _cli(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="grafik_client")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("health")
    ra = sub.add_parser("ref-add", help="uložit obrázek (nebo pin z Pinterestu) do schránky předloh")
    ra.add_argument("url")
    ra.add_argument("--page", help="adresa stránky, odkud obrázek je (pin)")
    ra.add_argument("--title")
    g = sub.add_parser("generate")
    g.add_argument("prompt")
    g.add_argument("--size", default="1024x1024")
    g.add_argument("--n", type=int, default=1)
    g.add_argument("--seed", type=int)
    g.add_argument("--steps", type=int)
    g.add_argument("--ref", action="append", default=[], help="cesta[:role], role subject|geometry|scene|style")
    g.add_argument("--style")
    g.add_argument("--supersample", type=float, help="vykreslit N× větší a zmenšit (drobné postavy), jen flux-local")
    g.add_argument("--backend", default="flux-local")
    g.add_argument("--confirm-cost", action="store_true")
    g.add_argument("--out", default=".")
    a = ap.parse_args(argv)
    if a.cmd == "health":
        print(json.dumps(health(), ensure_ascii=False, indent=2))
        return 0
    if a.cmd == "ref-add":
        try:
            meta = add_ref(a.url, page_url=a.page, title=a.title)
        except GrafikError as e:
            print(f"CHYBA: {e}", file=sys.stderr)
            return 1
        print(f"předloha {meta['id']} ({meta['origin']}, {meta['width']}x{meta['height']}) je ve schránce")
        return 0
    refs = []
    for r in a.ref:
        path, _, role = r.rpartition(":") if r.rsplit(":", 1)[-1] in ("subject", "geometry", "scene", "style") else (r, "", "")
        refs.append({"path": path, "role": role or "subject"})
    t0 = time.monotonic()
    last = [None]

    def show(job):
        state = (job["status"], job.get("position"))
        if state != last[0]:
            print(f"[{time.monotonic() - t0:6.1f} s] {job['status']}"
                  + (f" (ve frontě před vámi: {job['position']})" if job.get("position") else ""), flush=True)
            last[0] = state
    try:
        job_id = submit(a.prompt, backend=a.backend, size=a.size, n=a.n, seed=a.seed, steps=a.steps,
                        refs=refs, style=a.style, supersample=a.supersample, confirm_cost=a.confirm_cost, caller="grafik_client-cli")
        print(f"úloha {job_id}", flush=True)
        paths = download(wait(job_id, on_status=show), a.out)
    except GrafikError as e:
        print(f"CHYBA: {e}", file=sys.stderr)
        return 1
    for p in paths:
        print(p)
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(_cli(sys.argv[1:]))
