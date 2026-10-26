"""grafik_client — the one way projects ask GRAFIK Engine for an image.

Copy this single file into a project; it needs only the Python standard library.

    from grafik_client import generate
    paths = generate("red apple on a table", size="1024x1024", out_dir="out")
    paths = generate("The ship in <ref_image_0> from above", refs=[{"path": "ship.png", "role": "geometry"}])

The default backend is the local FLUX (0 USD). A paid backend runs only when you
name it AND pass confirm_cost=True; without it you get CostConfirmationRequired
with the estimate and nothing runs. The client never switches backends on its
own: when the local generator is unavailable you get EngineUnavailable.

ensure_engine() starts the Engine in the background when it is not running (the
same command as start-grafik.bat, without Studio and the browser). Call it before
a job; GRAFIK_AUTOSTART=0 turns it off.

variants() makes N images to pick from instead of iterating one by one: the jobs,
a manifest.json and varianty.html (zoom, favourites, combine params, copy the pick
back to the agent). The page comes from variants_page.py (a copy of STOPA
scripts/manual/variants_page.py) next to this file or in GRAFIK/clients.

CLI: python grafik_client.py generate "prompt" [--size 1024x1024] [--ref path[:role]] [--out DIR]
     python grafik_client.py variants "prompt" [--count 8] [--style SLUG ...] [--out DIR] [--no-open]
     python grafik_client.py ref-add <image or pin URL> [--page URL] [--title T]
     python grafik_client.py health
     python grafik_client.py ensure
"""
from __future__ import annotations

import base64
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

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


_start_lock = threading.Lock()


def _engine_up() -> bool:
    try:
        return _request("GET", "/api/v2/health", timeout=3)[0] == 200
    except EngineUnavailable:
        return False


def _grafik_dir() -> Path | None:
    """GRAFIK_DIR, else a folder GRAFIK next to any parent of this file (works from worktrees too)."""
    if os.environ.get("GRAFIK_DIR"):
        return Path(os.environ["GRAFIK_DIR"])
    for parent in Path(__file__).resolve().parents:
        if (parent / "GRAFIK" / "engine" / "app.py").is_file():
            return parent / "GRAFIK"
    return None


def _engine_python() -> str | None:
    """GRAFIK_PYTHON, else python on PATH outside the caller's venv (GRAFIK's packages are not there)."""
    if os.environ.get("GRAFIK_PYTHON"):
        return os.environ["GRAFIK_PYTHON"]
    venv = Path(sys.prefix).resolve()
    for name in ("python", "py"):
        found = shutil.which(name)
        if found and not Path(found).resolve().is_relative_to(venv):
            return found
    return None


def ensure_engine(timeout: float = 90) -> None:
    """Start the Engine in the background when it does not answer; EngineUnavailable when that fails.
    The Engine runs the GPU itself, so callers only switch the service on."""
    if _engine_up():
        return
    down = f"GRAFIK Engine na {ENGINE_URL} neodpovídá"
    if os.environ.get("GRAFIK_AUTOSTART", "1") == "0":
        raise EngineUnavailable(f"{down} (autostart vypnut GRAFIK_AUTOSTART=0). Spusťte start-grafik.bat.")
    with _start_lock:
        if _engine_up():            # another thread started it meanwhile
            return
        root, python = _grafik_dir(), _engine_python()
        if root is None or not (root / "engine" / "app.py").is_file() or not python:
            raise EngineUnavailable(f"{down} a spustit ho nejde (GRAFIK {root or 'nenalezen, nastavte GRAFIK_DIR'}, "
                                    f"Python {python or 'nenalezen, nastavte GRAFIK_PYTHON'}).")
        log_path = root / "logs" / "engine.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        flags = 0
        if sys.platform == "win32":
            flags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        with open(log_path, "ab") as out:
            proc = subprocess.Popen([python, "-m", "uvicorn", "engine.app:app", "--host", "127.0.0.1",
                                     "--port", str(urlparse(ENGINE_URL).port or 8300), "--access-log"],
                                    cwd=str(root), stdout=out, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, creationflags=flags, close_fds=True)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if _engine_up():
                return
            if proc.poll() is not None:
                raise EngineUnavailable(f"{down}: spuštění skončilo kódem {proc.returncode}, detail v {log_path}")
            time.sleep(1)
        raise EngineUnavailable(f"{down}: nenaběhl do {int(timeout)} s, detail v {log_path}")


def styles() -> list[dict]:
    """Style cards from GRAFIK's library. Pass a card's `slug` as generate(..., style=slug):
    the Engine adds the card's words to the prompt (never the sample images)."""
    status, data = _request("GET", "/api/v2/styles")
    if status != 200:
        raise GrafikError(f"knihovnu stylů se nepodařilo načíst ({status})")
    return data


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


def _variants_page_module():
    """variants_page.py next to this file, else in GRAFIK/clients; None when neither is there."""
    root = _grafik_dir()
    for folder in (Path(__file__).resolve().parent, root / "clients" if root else None):
        if folder and (folder / "variants_page.py").is_file():
            spec = importlib.util.spec_from_file_location("variants_page", folder / "variants_page.py")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    return None


def _plan(count: int, styles: list) -> list[tuple]:
    """count images spread over styles (round-robin share), each style cut into jobs of at most 4."""
    jobs = []
    for i, style in enumerate(styles):
        left = count // len(styles) + (i < count % len(styles))
        while left > 0:
            jobs.append((style, min(4, left)))
            left -= 4
    return jobs


def variants(prompt: str, *, count: int = 8, styles: list | None = None, out_dir: str | Path = "varianty",
             title: str | None = None, open_page: bool = True, timeout: float = 900, on_status=None,
             confirm_cost: bool = False, **kw) -> Path:
    """count images (spread over styles) for picking instead of iterating; writes the PNGs,
    manifest.json and varianty.html into out_dir and returns the page (or the manifest when
    variants_page.py is missing). A paid batch needs confirm_cost=True; without it the estimate
    for the WHOLE batch comes back as CostConfirmationRequired and nothing runs."""
    if not 1 <= count <= 40:
        raise GrafikError("počet variant 1–40")
    plan = _plan(count, list(styles or [kw.pop("style", None)]))
    total, items = 0.0, []
    for style, n in plan:
        body = {**kw, "prompt": prompt, "n": n, "style": style, "refs": [_ref_payload(r) for r in kw.get("refs") or []]}
        status, est = _request("POST", "/api/v2/estimate", body)
        if status != 200:
            raise GrafikError(f"Engine odmítl požadavek ({status}): {est.get('detail')}")
        total += est["total_usd"]
        items += est.get("items", [])
    if total > 0 and not confirm_cost:
        raise CostConfirmationRequired(round(total, 4), items)

    job_ids = [submit(prompt, n=n, style=style, confirm_cost=confirm_cost, **kw) for style, n in plan]
    out = Path(out_dir)
    entries = []
    for job_id in job_ids:
        job = wait(job_id, timeout=timeout, on_status=on_status)
        req, res = job["request"], job["result"] or {}
        for n, path in enumerate(download(job, out)):
            params = {"styl": req.get("style_id") or req.get("style") or "bez stylu",
                      "seed": (res.get("seeds") or [None] * (n + 1))[n], "velikost": req.get("size"),
                      "backend": job.get("backend"), "kroky": req.get("steps")}
            entries.append({"id": f"v{len(entries) + 1:02d}", "src": path.name, "label": f"úloha {job_id}/{n}",
                            "prompt": res.get("prompt_sent") or prompt,
                            "params": {k: v for k, v in params.items() if v is not None}})
    manifest = {"title": title or prompt[:80], "note": f"{len(entries)} variant z GRAFIK Engine · zadání: {prompt}",
                "variants": entries}
    manifest_path = out / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    page_mod = _variants_page_module()
    if page_mod is None:
        return manifest_path
    page = page_mod.write_page(page_mod.load_manifest(manifest_path), out / "varianty.html")
    if open_page:
        webbrowser.open(page.resolve().as_uri())
    return page


def _cli(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="grafik_client")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("health")
    sub.add_parser("ensure", help="spustit Engine na pozadí, když neběží")
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
    v = sub.add_parser("variants", help="N variant a stránka pro výběr místo iterace")
    v.add_argument("prompt")
    v.add_argument("--count", type=int, default=8)
    v.add_argument("--style", action="append", default=[], help="slug stylu; víc --style = varianty se rozdělí mezi styly")
    v.add_argument("--size", default="1024x1024")
    v.add_argument("--steps", type=int)
    v.add_argument("--supersample", type=float)
    v.add_argument("--backend", default="flux-local")
    v.add_argument("--confirm-cost", action="store_true")
    v.add_argument("--title")
    v.add_argument("--out", default="varianty")
    v.add_argument("--no-open", action="store_true", help="stránku neotevírat v prohlížeči")
    a = ap.parse_args(argv)
    if a.cmd == "health":
        print(json.dumps(health(), ensure_ascii=False, indent=2))
        return 0
    if a.cmd == "ensure":
        try:
            ensure_engine()
        except GrafikError as e:
            print(f"CHYBA: {e}", file=sys.stderr)
            return 1
        print(f"GRAFIK Engine běží na {ENGINE_URL}")
        return 0
    if a.cmd == "ref-add":
        try:
            meta = add_ref(a.url, page_url=a.page, title=a.title)
        except GrafikError as e:
            print(f"CHYBA: {e}", file=sys.stderr)
            return 1
        print(f"předloha {meta['id']} ({meta['origin']}, {meta['width']}x{meta['height']}) je ve schránce")
        return 0
    if a.cmd == "variants":
        try:
            page = variants(a.prompt, count=a.count, styles=a.style or None, out_dir=a.out, title=a.title,
                            open_page=not a.no_open, size=a.size, steps=a.steps, supersample=a.supersample,
                            backend=a.backend, confirm_cost=a.confirm_cost, caller="grafik_client-variants")
        except CostConfirmationRequired as e:
            print(f"CHYBA: placená dávka ~{e.estimate_usd} USD, nic nespuštěno. Zopakujte s --confirm-cost.",
                  file=sys.stderr)
            return 1
        except GrafikError as e:
            print(f"CHYBA: {e}", file=sys.stderr)
            return 1
        print(page.resolve())
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
