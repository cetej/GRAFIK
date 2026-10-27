"""3D step (spec docs/plans/2026-10-27-3d-v1.md, v2 in docs/plans/2026-10-27-3d-dalsi-zadani.md § A): models
from fal TRELLIS 2 / Hunyuan3D v3 or an uploaded GLB, a light copy for the Studio orbit viewer, 8 clay views
on demand (the sheet), operator check, a clay render from the viewer's camera (or a sheet view) goes to the
image generator as a `geometry` ref.

Library: library/3d/<id>/v<n>/ — every run is a new version, nothing is overwritten; model.json carries
`schema_version`. Each step is its own queue job (kind `model3d`, `viewer3d`, `views3d`, `camera3d`,
`stretch3d`), so a paid model
is saved the moment it is downloaded and a crash between steps never costs a second payment
(the fal `request_id` is stored right after submit, `recover` fetches the result again).
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import shutil
import subprocess
import threading
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image
from pydantic import BaseModel, field_validator

from engine.config import REPO_ROOT, Settings
from engine.keys import get_key
from engine.styles import slugify

SCHEMA_VERSION = 1
VIEWS = ("front", "back", "left", "right")
VIEW_LABEL = {"front": "zepředu", "back": "zezadu", "left": "zleva", "right": "zprava"}
ELEVATIONS = {5: "nízko", 20: "20° nad", 60: "shora"}
AZIMUTHS = list(range(0, 360, 45))
PARTS = ("middle", "end-max", "end-min", "all")
RENDER_SCRIPT = REPO_ROOT / "engine" / "blender" / "render_views.py"
STRETCH_SCRIPT = REPO_ROOT / "engine" / "blender" / "stretch.py"
DECIMATE_SCRIPT = REPO_ROOT / "engine" / "blender" / "decimate.py"
# viewer.glb: enough for the silhouette and the wheels, ~1.2 MB instead of 42 MB (Tatra 87 v2, 500k faces)
VIEWER_TRIANGLES = 100_000
# viewer.opt.glb: viewer.glb quantized + meshopt (Tatra 87 v2 1.2 MB -> 0.33 MB). Already decimated, so no
# simplify. No join and no GPU instancing: joined into one mesh, the Blender ship (993 parts, 50 m) is quantized
# over its whole length and the thin oars shade differently (3.4 % of pixels, docs/spikes/2026-10-27-gltf-optimize.md).
# Textures (none in the clay copy today) go to WebP of at most 2048 px.
OPTIMIZE_ARGS = ["optimize", "--compress", "meshopt", "--simplify", "false", "--join", "false", "--instance", "false",
                 "--texture-compress", "webp", "--texture-size", "2048"]
KINDS = ("model3d", "viewer3d", "views3d", "camera3d", "stretch3d")
VERSION_RE = re.compile(r"^v(\d+)$")
# A version whose step was running when the Engine stopped.
RUNNING = ("generating", "rendering", "stretching", "viewer")


class Model3dError(RuntimeError):
    pass


# -- request bodies -----------------------------------------------------------

class Ref3d(BaseModel):
    view: str = "front"
    b64: str | None = None          # the cutout the operator checked (RGBA PNG)
    ref_id: str | None = None       # reference library; the API resolves it to `path`
    path: str | None = None
    source: str | None = None
    license: str | None = None
    author: str | None = None

    @field_validator("view")
    @classmethod
    def _view(cls, v: str) -> str:
        if v not in VIEWS:
            raise ValueError(f"pohled musí být jeden z {VIEWS}")
        return v


class Model3dIn(BaseModel):
    title: str = ""
    model_id: str | None = None     # a new version of an existing model
    method: str | None = None       # fal-trellis2 | fal-hunyuan3d | fal-hunyuan31pro | upload; empty = recommended
    refs: list[Ref3d] = []
    glb_b64: str | None = None      # upload: a finished GLB (Blender script, earlier run), 0 USD
    origin: str = ""                # upload: where the GLB comes from ("scripts/3d/lod_tatra87.py")
    caller: str = "studio"
    confirm_cost: bool = False


class ViewsIn(BaseModel):
    elevation: int = 20


class CameraIn(BaseModel):
    """The Studio viewer's camera: target in glTF coordinates (Y up), azimuth as on the sheet (0° from +X,
    90° from -Z), elevation above the target, distance in model units, lens on a 36 mm sensor (square frame)."""
    target: list[float]
    azimuth: float
    elevation: float
    distance: float
    lens: float = 50

    @field_validator("target")
    @classmethod
    def _target(cls, v: list[float]) -> list[float]:
        if len(v) != 3:
            raise ValueError("cíl kamery: tři souřadnice x, y, z")
        return v

    @field_validator("elevation")
    @classmethod
    def _el(cls, v: float) -> float:
        if not -89 <= v <= 89:
            raise ValueError("výška kamery musí být mezi -89° a 89°")
        return v

    @field_validator("distance")
    @classmethod
    def _dist(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("vzdálenost kamery musí být kladná")
        return v

    @field_validator("lens")
    @classmethod
    def _lens(cls, v: float) -> float:
        if not 10 <= v <= 300:
            raise ValueError("ohnisko musí být mezi 10 a 300 mm")
        return v

    def key(self) -> str:
        """Same camera -> same file: a repeated click reuses the render instead of drawing it again."""
        norm = {"t": [round(x, 4) for x in self.target], "a": round(self.azimuth % 360, 1),
                "e": round(self.elevation, 1), "d": round(self.distance, 4), "l": round(self.lens, 1)}
        return "cam-" + hashlib.sha1(json.dumps(norm, sort_keys=True).encode()).hexdigest()[:10]


class ReviewIn(BaseModel):
    reviewed: bool = True
    by: str = "operátor"


class StretchIn(BaseModel):
    dims: list[float]               # length, width, height in metres (from the source)
    part: str = "middle"
    source: str = ""                # where the dimensions come from


class CutoutIn(BaseModel):
    b64: str


# -- paid backends -------------------------------------------------------------

class FalModel3d:
    """One fal image-to-3D endpoint. Prices from the fal model pages on 2026-10-27 (DECISIONS 2026-10-27)."""

    # base price of one Geometry model; Hunyuan adds 0.15 USD for extra views (fal model pages, 2026-10-27)
    BASE = {"fal-trellis2": ("TRELLIS 2 obrázek → 3D (1024p)", 0.30),
            "fal-hunyuan3d": ("Hunyuan3D v3 Geometry", 0.225),
            "fal-hunyuan31pro": ("Hunyuan 3.1 Pro Geometry", 0.375)}

    def __init__(self, method: str, endpoint: str, label: str, eta_s: int, timeout_s: float):
        self.method, self.endpoint, self.label, self.eta = method, endpoint, label, eta_s
        self.timeout_s = timeout_s

    def items(self, views: list[str]) -> list[dict]:
        what, usd = self.BASE[self.method]
        extra = [v for v in views if v != "front"]
        return [{"what": what, "usd": usd}] + (
            [{"what": f"další pohledy ({', '.join(VIEW_LABEL[v] for v in extra)})", "usd": 0.15}]
            if extra and self.method != "fal-trellis2" else [])

    def validate(self, views: list[str]) -> None:
        if not views:
            raise Model3dError("chybí předloha")
        if self.method == "fal-trellis2" and len(views) != 1:
            raise Model3dError("TRELLIS 2 bere jednu předlohu; víc pohledů zvládne Hunyuan3D")
        if self.method != "fal-trellis2" and "front" not in views:
            raise Model3dError(f"{self.label} potřebuje předlohu zepředu")
        if len(set(views)) != len(views):
            raise Model3dError("každý pohled smí mít jen jednu předlohu")

    def arguments(self, urls: dict[str, str]) -> dict:
        if self.method == "fal-trellis2":
            return {"image_url": next(iter(urls.values())), "resolution": 1024, "seed": 7}
        # no face_count: fal bills a custom face count extra (0.15 USD); its default is the same 500k
        args = {"input_image_url": urls["front"], "generate_type": "Geometry"}
        args.update({f"{v}_image_url": u for v, u in urls.items() if v != "front"})
        return args

    def _client(self):
        import fal_client
        key = get_key("FAL_KEY", "FAL_API_KEY")
        if not key:
            raise Model3dError("fal: chybí FAL_KEY / FAL_API_KEY")
        return fal_client.SyncClient(key=key, default_timeout=self.timeout_s)

    def run(self, refs: dict[str, bytes], on_submitted) -> bytes:
        client = self._client()
        try:
            urls = {v: client.upload(png, "image/png") for v, png in refs.items()}
            handle = client.submit(self.endpoint, arguments=self.arguments(urls))
        except Exception as e:  # fal_client raises its own types
            raise Model3dError(f"fal {self.endpoint}: odeslání selhalo: {type(e).__name__}: {e}") from e
        on_submitted(handle.request_id)
        return self._wait(handle)

    def fetch(self, request_id: str) -> bytes:
        """The result of an already paid request (after a crash): no second payment."""
        return self._wait(self._client().get_handle(self.endpoint, request_id))

    def _wait(self, handle) -> bytes:
        import fal_client
        deadline = time.monotonic() + self.timeout_s
        try:
            while not isinstance(handle.status(), fal_client.Completed):
                if time.monotonic() > deadline:
                    raise Model3dError(f"fal {self.endpoint}: model nedoběhl do {int(self.timeout_s / 60)} min; "
                                       f"výsledek jde vyzvednout později bez druhé platby (request_id {handle.request_id})")
                time.sleep(3)
            url = handle.get()["model_glb"]["url"]
            return httpx.get(url, timeout=300).raise_for_status().content
        except Model3dError:
            raise
        except Exception as e:
            raise Model3dError(f"fal {self.endpoint}: {type(e).__name__}: {e}") from e


def make_backends3d(settings: Settings) -> dict:
    return {
        "fal-trellis2": FalModel3d("fal-trellis2", "fal-ai/trellis-2", "TRELLIS 2", 120, settings.fal3d_timeout_s),
        "fal-hunyuan3d": FalModel3d("fal-hunyuan3d", "fal-ai/hunyuan3d-v3/image-to-3d", "Hunyuan3D v3", 90,
                                    settings.fal3d_timeout_s),
        # KLAPKA rated it best from one image (KLAPKA docs/figury-3d.md, 2026-10-05); operator added it 2026-10-27
        "fal-hunyuan31pro": FalModel3d("fal-hunyuan31pro", "fal-ai/hunyuan-3d/v3.1/pro/image-to-3d",
                                       "Hunyuan 3.1 Pro", 90, settings.fal3d_timeout_s),
    }


def recommend(views: list[str]) -> str:
    """1 ref -> TRELLIS 2 (default, DECISIONS 2026-10-27), 2+ refs -> Hunyuan3D v3 (multi-view)."""
    return "fal-hunyuan3d" if len(views) > 1 else "fal-trellis2"


# -- library ----------------------------------------------------------------------

def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def is_glb(data: bytes) -> bool:
    return data[:4] == b"glTF"


class Model3dLibrary:
    def __init__(self, root: Path):
        self.root = root
        self._lock = threading.RLock()

    def _versions(self, model_id: str) -> list[int]:
        d = self.root / model_id
        if not d.is_dir():
            return []
        return sorted(int(m.group(1)) for p in d.iterdir() if p.is_dir() and (m := VERSION_RE.match(p.name)))

    def vdir(self, model_id: str, version: str) -> Path:
        if not re.fullmatch(r"[a-z0-9-]+", model_id) or not VERSION_RE.match(version):
            raise Model3dError("neplatné id modelu nebo verze")
        d = self.root / model_id / version
        if not (d / "model.json").is_file():
            raise Model3dError(f"model {model_id} {version} neexistuje")
        return d

    def read(self, model_id: str, version: str) -> dict:
        return json.loads((self.vdir(model_id, version) / "model.json").read_text(encoding="utf-8"))

    def update(self, model_id: str, version: str, **fields) -> dict:
        """Metadata only — model.glb and rendered views are never rewritten."""
        with self._lock:
            d = self.vdir(model_id, version)
            meta = json.loads((d / "model.json").read_text(encoding="utf-8"))
            meta.update(fields)
            tmp = d / "model.json.tmp"
            tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(d / "model.json")
            return meta

    def new_version(self, model_id: str | None, title: str, **meta) -> dict:
        with self._lock:
            if model_id is None:
                base = slugify(title or "model") if title else "model"
                base = "model" if base == "styl" else base
                model_id, i = base, 2
                while (self.root / model_id).exists():
                    model_id, i = f"{base}-{i}", i + 1
            elif not self._versions(model_id):
                raise Model3dError(f"model {model_id} neexistuje")
            else:
                title = title or self.latest(model_id)["title"]
            n = (self._versions(model_id) or [0])[-1] + 1
            d = self.root / model_id / f"v{n}"
            d.mkdir(parents=True)
            out = {"schema_version": SCHEMA_VERSION, "id": model_id, "version": f"v{n}", "title": title,
                   "created": _now(), "status": "queued", "refs": [], "cost_usd": 0.0, "views": {},
                   "review": None, "jobs": [], "error": None, **meta}
            (d / "model.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
            return out

    def latest(self, model_id: str) -> dict:
        return self.read(model_id, f"v{self._versions(model_id)[-1]}")

    def get(self, model_id: str) -> dict:
        versions = [self.read(model_id, f"v{n}") for n in self._versions(model_id)]
        if not versions:
            raise Model3dError(f"model {model_id} neexistuje")
        return {"id": model_id, "title": versions[-1]["title"], "versions": versions}

    def list(self) -> list[dict]:
        if not self.root.is_dir():
            return []
        out = []
        for d in self.root.iterdir():
            if d.is_dir() and self._versions(d.name):
                m = self.latest(d.name)
                out.append({**m, "versions": len(self._versions(d.name))})
        return sorted(out, key=lambda m: m["created"], reverse=True)

    def mark_interrupted(self) -> int:
        """A step that was running when the Engine stopped: the queue marks the job failed, here the
        version says so too (a paid one keeps its request_id, so `recover` can fetch it without paying)."""
        n = 0
        for m in self.list():
            for v in self.get(m["id"])["versions"]:
                if v["status"] in RUNNING:
                    self.update(v["id"], v["version"], status="failed", error="přerušeno restartem Engine")
                    n += 1
        return n

    def migrate_legacy(self) -> list[str]:
        """Measurement models (library/3d/<id>/model.glb from the 2026-10-23/27 spikes) -> <id>/v1/ as a copy;
        the originals stay where they are. Runs once per model (skipped when a version exists)."""
        done = []
        if not self.root.is_dir():
            return done
        for d in sorted(self.root.iterdir()):
            if not d.is_dir() or self._versions(d.name) or not (d / "model.glb").is_file():
                continue
            if not re.fullmatch(r"[a-z0-9-]+", d.name):
                continue
            try:
                legacy = json.loads((d / "model.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                legacy = {}
            backend = str(legacy.get("backend", ""))
            method = ("fal-trellis2" if "trellis" in backend else "fal-hunyuan3d" if "hunyuan" in backend
                      else "blender-script" if backend.startswith("blender") else "stretch" if legacy.get("source")
                      else "upload")
            v = d / "v1"
            v.mkdir()
            shutil.copy2(d / "model.glb", v / "model.glb")
            refs = []
            sources = legacy.get("views") or {}
            for p in sorted(d.glob("predloha*.png")):
                view = p.stem.removeprefix("predloha").lstrip("-") or "front"
                if view not in VIEWS:
                    continue
                shutil.copy2(p, v / f"ref-{view}.png")
                src = sources.get(view) or legacy.get("source_ref")
                refs.append({"view": view, "file": f"ref-{view}.png", "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                             "source": src, "license": _license_of(src)})
            thumb = next(iter(sorted(d.glob("clay-az*.png"))), None) or next(iter(sorted(d.glob("render-az*.png"))), None)
            if thumb:
                shutil.copy2(thumb, v / "legacy-thumb.png")
            meta = {"schema_version": SCHEMA_VERSION, "id": d.name, "version": "v1",
                    "title": legacy.get("title", d.name), "created": f"{legacy.get('made', '2026-10-27')}T00:00:00",
                    "status": "model", "method": method, "backend": backend or None, "refs": refs,
                    "cost_usd": float(legacy.get("usd", 0) or 0), "request_id": None, "views": {}, "review": None,
                    "jobs": [], "error": None, "glb_bytes": (v / "model.glb").stat().st_size,
                    "origin": legacy.get("script") or legacy.get("source") or legacy.get("spike"),
                    "legacy": {"dir": f"library/3d/{d.name}", "model_json": legacy}}
            (v / "model.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
            done.append(d.name)
        return done


def _license_of(source: str | None) -> str | None:
    m = re.search(r"(CC[ -]BY[^,()]*|CC0|public domain|licence neznámá)", source or "", re.I)
    return m.group(1).strip() if m else None


# -- Blender --------------------------------------------------------------------------

class GltfTransform:
    """glTF Transform CLI (engine/gltf/) as a subprocess with a time limit; output goes to a log like Blender's."""

    def __init__(self, settings: Settings):
        self.s = settings

    def optimize(self, src: Path, dst: Path, log_path: Path) -> dict:
        cmd = [*self.s.gltf_transform_cmd, *OPTIMIZE_ARGS[:1], str(src), str(dst), *OPTIMIZE_ARGS[1:]]
        t0 = time.time()
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=self.s.gltf_transform_timeout_s, stdin=subprocess.DEVNULL,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except FileNotFoundError as e:
            raise Model3dError(f"glTF Transform nenalezen ({self.s.gltf_transform_cmd[0]})") from e
        except subprocess.TimeoutExpired as e:
            raise Model3dError(f"glTF Transform nedoběhl do {int(self.s.gltf_transform_timeout_s)} s") from e
        log_path.write_text(f"$ {' '.join(cmd)}\nexit {p.returncode}\n{p.stdout}\n--- stderr ---\n{p.stderr}",
                            encoding="utf-8")
        if p.returncode != 0:
            tail = (p.stderr.strip() or p.stdout.strip()).splitlines()[-2:]
            raise Model3dError(f"glTF Transform skončil chybou {p.returncode}: {' / '.join(tail)[:300]} (log {log_path.name})")
        return {"seconds": round(time.time() - t0, 1), "tool": self._version()}

    def _version(self) -> str:
        try:
            p = subprocess.run([*self.s.gltf_transform_cmd, "--version"], capture_output=True, text=True, timeout=30,
                               stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return f"gltf-transform {p.stdout.strip().splitlines()[-1]}" if p.stdout.strip() else "gltf-transform"
        except (OSError, subprocess.TimeoutExpired):
            return "gltf-transform"


class Blender:
    """Blender as a subprocess with a time limit; stdout+stderr go to a log next to the version."""

    def __init__(self, settings: Settings):
        self.s = settings

    def run(self, script: Path, args: list[str], log_path: Path, timeout_s: float | None = None) -> str:
        timeout_s = timeout_s or self.s.blender_timeout_s
        cmd = [*self.s.blender_cmd, str(script), "--", *args]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=timeout_s, stdin=subprocess.DEVNULL,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except FileNotFoundError as e:
            raise Model3dError(f"Blender nenalezen ({self.s.blender_cmd[0]}); nastavte GRAFIK_BLENDER") from e
        except subprocess.TimeoutExpired as e:
            log_path.write_text(f"$ {' '.join(cmd)}\n{_s(e.stdout)}\n--- stderr ---\n{_s(e.stderr)}", encoding="utf-8")
            raise Model3dError(f"Blender nedoběhl do {int(timeout_s)} s (log {log_path.name})") from e
        log_path.write_text(f"$ {' '.join(cmd)}\nexit {p.returncode}\n{p.stdout}\n--- stderr ---\n{p.stderr}",
                            encoding="utf-8")
        if p.returncode != 0:
            tail = (p.stderr.strip() or p.stdout.strip()).splitlines()[-3:]
            raise Model3dError(f"Blender skončil chybou {p.returncode}: {' / '.join(tail)[:300]} (log {log_path.name})")
        return p.stdout


def _s(x) -> str:
    return x.decode("utf-8", "replace") if isinstance(x, bytes) else (x or "")


def view_dir(elevation: int) -> str:
    return f"views-e{elevation:02d}"


def opaque_share(png: Path) -> float:
    im = Image.open(png)
    if "A" not in im.getbands():
        return 1.0
    alpha = im.getchannel("A").resize((128, 128))
    return sum(alpha.histogram()[17:]) / (128 * 128)


# -- jobs ---------------------------------------------------------------------------

class Models3d:
    """Runs the three job kinds for the Worker and holds the library."""

    def __init__(self, settings: Settings, store, sd, gpu_lock, backends3d: dict, log_cost,
                 blender: Blender | None = None, gltf: GltfTransform | None = None):
        self.s, self.store, self.sd, self.gpu_lock = settings, store, sd, gpu_lock
        self.backends = backends3d
        self.log_cost = log_cost
        self.blender = blender or Blender(settings)
        self.gltf = gltf or GltfTransform(settings)
        self.lib = Model3dLibrary(settings.library_dir / "3d")

    def handlers(self) -> dict:
        return {"model3d": self.run_model, "viewer3d": self.run_viewer, "views3d": self.run_views,
                "camera3d": self.run_camera, "stretch3d": self.run_stretch}

    def enqueue(self, kind: str, caller: str, backend: str, request: dict) -> str:
        job_id = self.store.add_task(kind, caller, backend, request)
        with self.lib._lock:   # the API thread and the worker both add jobs to a version
            meta = self.lib.read(request["model_id"], request["version"])
            self.lib.update(request["model_id"], request["version"], jobs=meta["jobs"] + [{"job_id": job_id, "kind": kind}])
        return job_id

    def _fail(self, req: dict, e: Exception, status: str = "failed") -> None:
        try:
            self.lib.update(req["model_id"], req["version"], status=status, error=str(e))
        except Model3dError:
            pass

    # model ------------------------------------------------------------------
    def run_model(self, job_id: str, req: dict) -> dict:
        mid, ver = req["model_id"], req["version"]
        d = self.lib.vdir(mid, ver)
        meta = self.lib.read(mid, ver)
        backend = self.backends[meta["method"]]
        usd = meta["cost_usd"]
        cost_row = {"job_id": job_id, "caller": req.get("caller", "studio"), "backend": f"fal:{backend.endpoint}",
                    "n": 1, "usd": usd, "items": meta.get("items", []), "model3d": f"{mid}/{ver}"}
        self.lib.update(mid, ver, status="generating", started=_now(), error=None)
        t0 = time.time()
        try:
            if req.get("recover"):
                glb = backend.fetch(meta["request_id"])
            else:
                refs = {r["view"]: (d / r["file"]).read_bytes() for r in meta["refs"]}
                self.log_cost({**cost_row, "status": "pending"})   # write-ahead, before anything is sent

                def submitted(request_id: str) -> None:
                    self.lib.update(mid, ver, request_id=request_id, submitted=_now())

                try:
                    glb = backend.run(refs, submitted)
                except Exception:
                    if not self.lib.read(mid, ver).get("request_id"):
                        # never reached fal: nothing to pay
                        self.log_cost({**cost_row, "status": "failed", "usd": 0.0, "est_usd": usd})
                    raise
            if not is_glb(glb):
                raise Model3dError("fal vrátil soubor, který není GLB")
            (d / "model.glb").write_bytes(glb)   # saved before anything else can fail
            self.log_cost({**cost_row, "status": "ok", "request_id": self.lib.read(mid, ver).get("request_id")})
        except Exception as e:
            self._fail(req, e)
            raise
        self.lib.update(mid, ver, status="model", glb_bytes=len(glb), timing_s={"model": round(time.time() - t0, 1)})
        # the viewer copy, not the sheet: the sheet is on a button (DECISIONS 2026-10-27)
        viewer_job = self.enqueue("viewer3d", req.get("caller", "studio"), "blender", {"model_id": mid, "version": ver})
        return {"model_id": mid, "version": ver, "glb": str(d / "model.glb"), "viewer_job": viewer_job, "cost_usd": usd}

    # viewer -----------------------------------------------------------------
    def run_viewer(self, job_id: str, req: dict) -> dict:
        """viewer.glb: decimated geometry for the Studio viewer (CPU only, no render, so no GPU lock), then
        viewer.opt.glb next to it. `optimize_only`: a viewer.glb from before the optimizer gets only the copy."""
        mid, ver = req["model_id"], req["version"]
        d = self.lib.vdir(mid, ver)
        meta = self.lib.read(mid, ver)
        if req.get("optimize_only") and meta.get("viewer") and (d / "viewer.glb").is_file():
            viewer = {**meta["viewer"], "optimized": self._optimize_viewer(d)}
            self.lib.update(mid, ver, viewer=viewer)
            return {"model_id": mid, "version": ver, **viewer}
        before = meta["status"]
        self.lib.update(mid, ver, status="viewer", error=None)
        t0 = time.time()
        tmp = d / "viewer.tmp.glb"
        try:
            stdout = self.blender.run(DECIMATE_SCRIPT, [str(d / "model.glb"), str(tmp), str(VIEWER_TRIANGLES)],
                                      d / "blender-viewer.log")
            stats = _line_json(stdout, "STATS")
            if not stats.get("verts"):
                raise Model3dError("model nemá žádné vrcholy (prázdný nebo poškozený GLB)")
            if not tmp.is_file() or not is_glb(tmp.read_bytes()[:4]):
                raise Model3dError("Blender nezapsal zmenšený model pro prohlížeč (log blender-viewer.log)")
            (d / "viewer.opt.glb").unlink(missing_ok=True)   # made from the old viewer.glb
            tmp.replace(d / "viewer.glb")   # derived from model.glb, which stays untouched
        except Exception as e:
            tmp.unlink(missing_ok=True)
            self._fail(req, e, status="model")
            raise
        viewer = {"file": "viewer.glb", "bytes": (d / "viewer.glb").stat().st_size,
                  "triangles": _line_json(stdout, "VIEWER").get("triangles"), "job_id": job_id,
                  "seconds": round(time.time() - t0, 1)}
        viewer["optimized"] = self._optimize_viewer(d)
        # a model with a sheet already was "ready"; one fresh from fal/upload/stretch becomes ready now
        self.lib.update(mid, ver, status="ready" if before in ("model", "ready", "failed") else before,
                        viewer=viewer, stats=stats, blender=stats.get("blender"))
        return {"model_id": mid, "version": ver, **viewer}

    def _optimize_viewer(self, d: Path) -> dict:
        """viewer.glb -> viewer.opt.glb (provenance in model.json `viewer.optimized`). A failure is recorded and
        the job still succeeds: the Studio then loads viewer.glb, which stays as it was."""
        src, tmp = d / "viewer.glb", d / "viewer.opt.tmp.glb"
        try:
            run = self.gltf.optimize(src, tmp, d / "gltf-transform.log")
            if not tmp.is_file() or not is_glb(tmp.read_bytes()[:4]):
                raise Model3dError("glTF Transform nezapsal optimalizovaný model (log gltf-transform.log)")
            tmp.replace(d / "viewer.opt.glb")
        except Exception as e:
            tmp.unlink(missing_ok=True)
            (d / "viewer.opt.glb").unlink(missing_ok=True)   # never an optimized copy of an older viewer.glb
            return {"error": str(e), "at": _now()}
        return {"file": "viewer.opt.glb", "source": "viewer.glb", "bytes_before": src.stat().st_size,
                "bytes": (d / "viewer.opt.glb").stat().st_size, "args": OPTIMIZE_ARGS, **run, "at": _now()}

    # views ------------------------------------------------------------------
    def run_views(self, job_id: str, req: dict) -> dict:
        mid, ver, el = req["model_id"], req["version"], int(req.get("elevation", 20))
        d = self.lib.vdir(mid, ver)
        out = d / view_dir(el)
        if out.exists():   # a re-render never overwrites: the earlier set moves aside, numbered
            n = 2
            while (d / f"{view_dir(el)}-{n}").exists():
                n += 1
            out.rename(d / f"{view_dir(el)}-{n}")
        out.mkdir()
        self.lib.update(mid, ver, status="rendering", error=None)
        t0 = time.time()
        args = [str(d / "model.glb"), str(out), str(el)] + (["--cpu"] if self.s.render_cpu else [])
        try:
            # Blender always runs under the GPU lock (sc-4). Q1, measured in docs/spikes/2026-10-27-3d-t1.md:
            # Cycles on the CPU needs 0 MB of VRAM and ~38 s for 8 views, so a loaded FLUX stays loaded.
            # With EEVEE (render_cpu off) our own sd-server is stopped first, by its PID: EEVEE beside a loaded
            # FLUX crashed FLUX on 8 GB (LEARNINGS 2026-10-27).
            self.gpu_lock.acquire(self.s.gpu_lock_wait_s)
            try:
                if not self.s.render_cpu:
                    self.sd.stop("3D render v Blenderu (EEVEE)")
                stdout = self.blender.run(RENDER_SCRIPT, args, out / "blender.log")
            finally:
                self.gpu_lock.release()
            stats = _line_json(stdout, "STATS")
            if not stats.get("verts"):
                raise Model3dError("model nemá žádné vrcholy (prázdný nebo poškozený GLB)")
            files = []
            for az in AZIMUTHS:
                p = out / f"az{az:03d}.png"
                if not p.is_file():
                    raise Model3dError(f"Blender nevyrenderoval pohled {az}° (log blender.log)")
                if opaque_share(p) < 0.005:
                    raise Model3dError(f"pohled {az}° je prázdný: model je mimo záběr nebo neviditelný")
                files.append(p.name)
        except Exception as e:
            # a failed sheet leaves the model as it was: still in the viewer (v2) or still without views
            self._fail(req, e, status="ready" if self.lib.read(mid, ver).get("viewer") else "model")
            raise
        meta = self.lib.read(mid, ver)
        views = {**meta["views"], str(el): {"dir": out.name, "files": files, "job_id": job_id, "rendered": _now(),
                                           "seconds": round(time.time() - t0, 1),
                                           "engine": "cycles-cpu" if self.s.render_cpu else "eevee"}}
        self.lib.update(mid, ver, status="ready", views=views, stats=stats, blender=stats.get("blender"))
        return {"model_id": mid, "version": ver, "elevation": el, "dir": str(out), "files": files}

    # one view from the viewer's camera ----------------------------------------------
    def run_camera(self, job_id: str, req: dict) -> dict:
        mid, ver, key, camera = req["model_id"], req["version"], req["key"], CameraIn(**req["camera"])
        out = self.lib.vdir(mid, ver) / "camera"
        out.mkdir(exist_ok=True)
        png = out / f"{key}.png"
        if png.is_file():   # the same camera was rendered meanwhile (double click): never overwrite
            return {"model_id": mid, "version": ver, "key": key, "file": f"camera/{png.name}"}
        tmp = out / f"{key}.tmp.png"
        args = [str(self.lib.vdir(mid, ver) / "model.glb"), str(tmp), "--camera", json.dumps(camera.model_dump())] + (
            ["--cpu"] if self.s.render_cpu else [])
        t0 = time.time()
        try:
            self.gpu_lock.acquire(self.s.gpu_lock_wait_s)   # the same rules as the sheet (run_views)
            try:
                if not self.s.render_cpu:
                    self.sd.stop("3D render v Blenderu (EEVEE)")
                self.blender.run(RENDER_SCRIPT, args, out / f"{key}.log")
            finally:
                self.gpu_lock.release()
            if not tmp.is_file():
                raise Model3dError(f"Blender nevyrenderoval pohled z kamery (log camera/{key}.log)")
            if opaque_share(tmp) < 0.005:
                raise Model3dError("pohled z kamery je prázdný: model je mimo záběr (vraťte výchozí pohled)")
            tmp.replace(png)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
        info = {**camera.model_dump(), "key": key, "file": f"camera/{png.name}", "job_id": job_id, "rendered": _now(),
                "seconds": round(time.time() - t0, 1), "engine": "cycles-cpu" if self.s.render_cpu else "eevee"}
        (out / f"{key}.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
        return {"model_id": mid, "version": ver, **info}

    # stretch ----------------------------------------------------------------
    def run_stretch(self, job_id: str, req: dict) -> dict:
        mid, ver = req["model_id"], req["version"]
        src = self.lib.vdir(mid, req["parent"]) / "model.glb"
        d = self.lib.vdir(mid, ver)
        self.lib.update(mid, ver, status="stretching", error=None)
        L, W, H = req["dims"]
        try:
            stdout = self.blender.run(STRETCH_SCRIPT, [str(src), str(d / "model.glb"), str(L), str(W), str(H),
                                                       req["part"]], d / "blender-stretch.log")
            if not (d / "model.glb").is_file():
                raise Model3dError("Blender nezapsal natažený model (log blender-stretch.log)")
        except Exception as e:
            self._fail(req, e)
            raise
        bbox = next((json.loads(line[5:]) for line in stdout.splitlines() if line.startswith("BBOX ")), None)
        self.lib.update(mid, ver, status="model", glb_bytes=(d / "model.glb").stat().st_size,
                        stretch={**self.lib.read(mid, ver).get("stretch", {}), "bbox": bbox})
        viewer_job = self.enqueue("viewer3d", req.get("caller", "studio"), "blender", {"model_id": mid, "version": ver})
        return {"model_id": mid, "version": ver, "viewer_job": viewer_job, "bbox": bbox}


def _line_json(stdout: str, tag: str) -> dict:
    return next((json.loads(line[len(tag) + 1:]) for line in stdout.splitlines() if line.startswith(tag + " ")), {})


def decode_png(b64: str) -> bytes:
    raw = b64.split(",", 1)[1] if b64.startswith("data:") else b64
    try:
        data = base64.b64decode(raw, validate=True)
        im = Image.open(BytesIO(data))
        im.load()
    except Exception as e:  # PIL / base64 raise many types for broken input
        raise Model3dError(f"předloha není čitelný obrázek ({e})") from e
    buf = BytesIO()
    im.convert("RGBA" if "A" in im.getbands() else "RGB").save(buf, "PNG")
    return buf.getvalue()


_rembg_session = None
_rembg_lock = threading.Lock()


def cutout(png: bytes) -> bytes:
    """Background removal with rembg u2net on the CPU (as in the 2026-10-27 measurements), free."""
    global _rembg_session
    from rembg import new_session, remove
    with _rembg_lock:
        if _rembg_session is None:
            _rembg_session = new_session("u2net", providers=["CPUExecutionProvider"])
        out = remove(png, session=_rembg_session)
    return out
