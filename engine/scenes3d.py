"""3D scenes (brief B, docs/plans/2026-10-27-3d-sceny.md): several checked models from the 3D library, simple
shapes (box, cylinder) and a 1.72 m control figure placed on the ground in metres, rendered as one clay still from
the Studio viewer's camera (engine/blender/render_views.py --scene) and handed to the image generator as a
`geometry` ref with a sentence about the real sizes.

Library: library/scenes3d/<id>/v<n>/scene.json — a change of the objects is a new version, nothing is
overwritten; the viewer's last camera is metadata (updated in place). Renders: v<n>/snaps/<key>.png + .json,
key = hash of camera, frame and figure, so the same click reuses the file.

Field names `misto` (x, y on the ground, metres, z up), `otoceni` (degrees about the vertical, counter-clockwise
seen from above) and `rozmer` (the longest side in metres, uniform scale) are KLAPKA's (`rytina3d`), so a scene can
later become a KLAPKA shot without a dictionary.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from pathlib import Path

from pydantic import BaseModel, field_validator

from engine.config import REPO_ROOT
from engine.models3d import RENDER_SCRIPT, CameraIn, Model3dError, _line_json, _now, opaque_share
from engine.styles import slugify

SCHEMA_VERSION = 1
FIGURE_GLB = REPO_ROOT / "engine" / "assets" / "postava-172.glb"   # engine/blender/figure172.py
FIGURE_M = 1.72
SHAPES = {"kvadr": 3, "valec": 2}   # rozmery: [x, y, z] / [průměr, výška] in metres
SHAPE_LABEL = {"kvadr": "kvádr", "valec": "válec"}
ASPECTS = {"1:1": (1, 1), "4:3": (4, 3), "3:2": (3, 2), "16:10": (16, 10), "16:9": (16, 9)}
LONG_SIDE_PX = 1600
MAX_OBJECTS = 30
VERSION_RE = re.compile(r"^v(\d+)$")
KINDS = ("scene3d",)
RENDER_TIMEOUT_S = 900.0   # several full models on the CPU: longer than one model's 180 s


class SceneError(Model3dError):
    pass


# -- request bodies -----------------------------------------------------------------

class SceneObject(BaseModel):
    id: str = ""                    # unique in the scene; empty = from the model or shape
    model: str | None = None        # a model of the 3D library …
    model_version: str | None = None
    tvar: str | None = None         # … or a simple shape: kvadr | valec
    rozmery: list[float] = []       # shape size
    nazev: str = ""                 # a shape's name ("Molo")
    misto: list[float] = [0, 0]
    otoceni: float = 0
    rozmer: float | None = None     # model: the longest side in metres
    rozmer_zdroj: str = ""
    na: str | None = None           # stands on the top of another object (its id)

    @field_validator("misto")
    @classmethod
    def _misto(cls, v: list[float]) -> list[float]:
        if len(v) != 2:
            raise ValueError("místo: dvě souřadnice x, y v metrech")
        return v


class Figure(BaseModel):
    misto: list[float] = [0, 0]
    otoceni: float = 0
    na: str | None = None


class SceneIn(BaseModel):
    scene_id: str | None = None     # a new version of an existing scene
    title: str = ""
    objects: list[SceneObject] = []
    postava: Figure = Figure()
    aspect: str = "16:10"
    camera: CameraIn | None = None


class SceneRenderIn(BaseModel):
    camera: CameraIn
    aspect: str = "16:10"
    postava: bool = False           # the control figure in the still (default off, DECISIONS 2026-10-27)


class SceneCameraIn(BaseModel):
    camera: CameraIn


# -- library ------------------------------------------------------------------------

class SceneLibrary:
    def __init__(self, root: Path):
        self.root = root
        self._lock = threading.RLock()

    def _versions(self, scene_id: str) -> list[int]:
        d = self.root / scene_id
        if not d.is_dir():
            return []
        return sorted(int(m.group(1)) for p in d.iterdir() if p.is_dir() and (m := VERSION_RE.match(p.name)))

    def vdir(self, scene_id: str, version: str) -> Path:
        if not re.fullmatch(r"[a-z0-9-]+", scene_id) or not VERSION_RE.match(version):
            raise SceneError("neplatné id scény nebo verze")
        d = self.root / scene_id / version
        if not (d / "scene.json").is_file():
            raise SceneError(f"scéna {scene_id} {version} neexistuje")
        return d

    def read(self, scene_id: str, version: str) -> dict:
        return json.loads((self.vdir(scene_id, version) / "scene.json").read_text(encoding="utf-8"))

    def _write(self, d: Path, meta: dict) -> None:
        tmp = d / "scene.json.tmp"
        tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(d / "scene.json")

    def update(self, scene_id: str, version: str, **fields) -> dict:
        """Metadata only (camera, renders) — the objects of a version never change."""
        with self._lock:
            meta = self.read(scene_id, version)
            meta.update(fields)
            self._write(self.vdir(scene_id, version), meta)
            return meta

    def new_version(self, scene_id: str | None, title: str, body: dict) -> dict:
        with self._lock:
            if scene_id is None:
                base = slugify(title) if title else "scena"
                base = "scena" if base == "styl" else base
                scene_id, i = base, 2
                while (self.root / scene_id).exists():
                    scene_id, i = f"{base}-{i}", i + 1
            elif not self._versions(scene_id):
                raise SceneError(f"scéna {scene_id} neexistuje")
            else:
                title = title or self.latest(scene_id)["title"]
            n = (self._versions(scene_id) or [0])[-1] + 1
            d = self.root / scene_id / f"v{n}"
            d.mkdir(parents=True)
            out = {"schema_version": SCHEMA_VERSION, "id": scene_id, "version": f"v{n}", "title": title,
                   "created": _now(), "snaps": [], **body}
            self._write(d, out)
            return out

    def latest(self, scene_id: str) -> dict:
        return self.read(scene_id, f"v{self._versions(scene_id)[-1]}")

    def get(self, scene_id: str) -> dict:
        versions = [self.read(scene_id, f"v{n}") for n in self._versions(scene_id)]
        if not versions:
            raise SceneError(f"scéna {scene_id} neexistuje")
        return {"id": scene_id, "title": versions[-1]["title"], "versions": versions}

    def list(self) -> list[dict]:
        if not self.root.is_dir():
            return []
        out = [{**self.latest(d.name), "versions": len(self._versions(d.name))}
               for d in self.root.iterdir() if d.is_dir() and self._versions(d.name)]
        return sorted(out, key=lambda m: m["created"], reverse=True)


# -- checks ---------------------------------------------------------------------------

def short_title(title: str) -> str:
    """'Římská kvinquerema (TRELLIS 2)' -> 'Římská kvinquerema': the method is not part of the object's name."""
    return re.sub(r"\s*\([^)]*\)\s*$", "", title).strip() or title


def size_from_model(meta: dict) -> tuple[float | None, str]:
    """The longest side in metres the model itself knows: the stretch to source dimensions, or a size the operator
    typed in an earlier scene (`rozmer_m`, DECISIONS 2026-10-27 Q2)."""
    dims = (meta.get("stretch") or {}).get("dims")
    if dims:
        return float(max(dims)), f"natažení: {meta['stretch'].get('source') or 'rozměry ze zdroje'}"
    if meta.get("rozmer_m"):
        return float(meta["rozmer_m"]), meta.get("rozmer_zdroj") or "zadáno ručně"
    return None, ""


def normalize(body: SceneIn, models) -> tuple[list[dict], dict]:
    """The objects as stored (ids filled, sizes taken from the model where it knows them) and the figure.
    Raises SceneError (Czech) on anything that can never be drawn; a missing size is not such a thing — it is
    a problem `problems()` lists, so a half-done scene can be saved."""
    if len(body.objects) > MAX_OBJECTS:
        raise SceneError(f"nejvýš {MAX_OBJECTS} objektů ve scéně")
    if body.aspect not in ASPECTS:
        raise SceneError(f"poměr stran musí být jeden z {list(ASPECTS)}")
    out, ids = [], set()
    for n, o in enumerate(body.objects, 1):
        if bool(o.model) == bool(o.tvar):
            raise SceneError(f"objekt {n}: buď model z knihovny, nebo jednoduchý tvar")
        row = o.model_dump()
        if o.model:
            meta = models.lib.read(o.model, o.model_version) if o.model_version else models.lib.get(o.model)["versions"][-1]
            row["model_version"] = meta["version"]
            if not (models.lib.vdir(o.model, meta["version"]) / "model.glb").is_file():
                raise SceneError(f"objekt {n}: {meta['title']} {meta['version']} zatím nemá model")
            if o.rozmer is None:
                row["rozmer"], row["rozmer_zdroj"] = size_from_model(meta)
            elif o.rozmer <= 0:
                raise SceneError(f"objekt {n}: rozměr musí být kladný (metry)")
            row["nazev"] = o.nazev or short_title(meta["title"])
            base = o.model
            row["rozmery"] = []
        else:
            if o.tvar not in SHAPES:
                raise SceneError(f"objekt {n}: tvar musí být jeden z {list(SHAPES)}")
            if len(o.rozmery) != SHAPES[o.tvar] or min(o.rozmery) <= 0:
                what = "délka, šířka a výška" if o.tvar == "kvadr" else "průměr a výška"
                raise SceneError(f"objekt {n} ({SHAPE_LABEL[o.tvar]}): rozměry {what} v metrech, všechny kladné")
            row["nazev"] = o.nazev or SHAPE_LABEL[o.tvar].capitalize()
            row["rozmer"], row["rozmer_zdroj"], row["model_version"] = None, "", None
            base = slugify(row["nazev"]) or o.tvar
        oid = o.id or base
        if not o.id:
            i = 2
            while oid in ids:
                oid, i = f"{base}-{i}", i + 1
        if oid in ids:
            raise SceneError(f"objekt {n}: id {oid!r} už ve scéně je")
        if o.na is not None and o.na not in ids:
            raise SceneError(f"objekt {n}: „stojí na“ {o.na!r} musí být objekt výš v seznamu")
        ids.add(oid)
        out.append({**row, "id": oid})
    fig = body.postava.model_dump()
    if fig["na"] is not None and fig["na"] not in ids:
        raise SceneError(f"kontrolní postava: „stojí na“ {fig['na']!r} ve scéně není")
    return out, fig


def problems(meta: dict) -> list[str]:
    """What stops a render, in Czech for the Studio (unchecked models stop only the ref: `unchecked`)."""
    out = []
    for o in meta["objects"]:
        if o.get("model") and not o.get("rozmer"):
            out.append(f"{o['nazev']}: chybí rozměr (nejdelší strana v metrech)")
    if not meta["objects"]:
        out.append("scéna je prázdná")
    return out


def unchecked(meta: dict, models) -> list[str]:
    out = []
    for o in meta["objects"]:
        if o.get("model") and not models.lib.read(o["model"], o["model_version"]).get("review"):
            out.append(f"{o['nazev']} ({o['model']} {o['model_version']})")
    return out


def _cs(x: float) -> str:
    return f"{x:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def size_hint(meta: dict) -> dict:
    """The sentence for the prompt (LEARNINGS 2026-10-23: the generator enlarges people; the height as a fraction
    of the main object helped). Main object = the largest model by its longest side; shapes are terrain."""
    sized = sorted((o for o in meta["objects"] if o.get("model") and o.get("rozmer")), key=lambda o: -o["rozmer"])
    if not sized:
        return {"cs": "", "en": ""}
    main, rest = sized[0], sized[1:]
    k = round(main["rozmer"] / FIGURE_M)
    # names stay in the nominative (no declension): "Loď 45 m (asi 26× výška člověka)"
    cs = (f"měřítko: člověk {_cs(FIGURE_M)} m, {main['nazev']} {_cs(main['rozmer'])} m"
          + (f" (asi {k}× výška člověka)" if k > 1 else ""))
    en = (f"a person is {FIGURE_M:g} m tall, about {'1/' + str(k) + ' of' if k > 1 else 'as tall as'} "
          f"the {main['nazev']} ({main['rozmer']:g} m)")
    seen = set()
    for o in rest:
        if o["nazev"] in seen:
            continue
        seen.add(o["nazev"])
        cs += f", {o['nazev']} {_cs(o['rozmer'])} m"
        en += f", {o['nazev']} {o['rozmer']:g} m"
    return {"cs": cs + "; postavy nezvětšuj", "en": en + "; do not enlarge people"}


def render_key(scene_id: str, version: str, body: SceneRenderIn) -> str:
    norm = {"s": f"{scene_id}/{version}", "c": body.camera.key(), "a": body.aspect, "p": body.postava}
    return "snap-" + hashlib.sha1(json.dumps(norm, sort_keys=True).encode()).hexdigest()[:10]


def render_spec(meta: dict, models, body: SceneRenderIn) -> dict:
    """What engine/blender/render_views.py --scene reads: absolute GLB paths, sizes in metres, the camera."""
    objs = []
    for o in meta["objects"]:
        row = {k: o[k] for k in ("id", "misto", "otoceni", "na")}
        if o.get("model"):
            row |= {"kind": "glb", "glb": str(models.lib.vdir(o["model"], o["model_version"]) / "model.glb"),
                    "rozmer": o["rozmer"]}
        else:
            row |= {"kind": o["tvar"], "rozmery": o["rozmery"]}
        objs.append(row)
    if body.postava:
        objs.append({"kind": "glb", "id": "postava", "glb": str(FIGURE_GLB), "rozmer": FIGURE_M,
                     **{k: meta["postava"][k] for k in ("misto", "otoceni", "na")}})
    w, h = ASPECTS[body.aspect]
    size = [LONG_SIDE_PX, round(LONG_SIDE_PX * h / w)] if w >= h else [round(LONG_SIDE_PX * w / h), LONG_SIDE_PX]
    return {"objects": objs, "camera": body.camera.model_dump(), "size": size}


# -- job ------------------------------------------------------------------------------

class Scenes3d:
    """The `scene3d` job for the Worker and the scene library; Blender, the GPU lock and the sd-server are the
    3D step's (engine/models3d.py), with the same rules as a render from the viewer's camera."""

    def __init__(self, models3d):
        self.m = models3d
        self.lib = SceneLibrary(models3d.s.library_dir / "scenes3d")

    def handlers(self) -> dict:
        return {"scene3d": self.run_render}

    def run_render(self, job_id: str, req: dict) -> dict:
        sid, ver, key = req["scene_id"], req["version"], req["key"]
        body = SceneRenderIn(**req["body"])
        d = self.lib.vdir(sid, ver) / "snaps"
        d.mkdir(exist_ok=True)
        png = d / f"{key}.png"
        if png.is_file():   # the same still was rendered meanwhile (double click): never overwrite
            return {"scene_id": sid, "version": ver, "key": key, "file": f"snaps/{png.name}"}
        meta = self.lib.read(sid, ver)
        spec_path, tmp = d / f"{key}.spec.json", d / f"{key}.tmp.png"
        spec_path.write_text(json.dumps(render_spec(meta, self.m, body), ensure_ascii=False, indent=1), encoding="utf-8")
        s = self.m.s
        args = ["--scene", str(spec_path), str(tmp)] + (["--cpu"] if s.render_cpu else [])
        t0 = time.time()
        try:
            self.m.gpu_lock.acquire(s.gpu_lock_wait_s)
            try:
                if not s.render_cpu:
                    self.m.sd.stop("3D render scény v Blenderu (EEVEE)")
                stdout = self.m.blender.run(RENDER_SCRIPT, args, d / f"{key}.log", timeout_s=RENDER_TIMEOUT_S)
            finally:
                self.m.gpu_lock.release()
            if not tmp.is_file():
                raise SceneError(f"Blender nevyrenderoval snímek scény (log snaps/{key}.log)")
            if opaque_share(tmp) < 0.002:
                raise SceneError("snímek scény je prázdný: objekty jsou mimo záběr (vraťte výchozí pohled)")
            tmp.replace(png)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
        info = {"key": key, "file": f"snaps/{png.name}", "job_id": job_id, "rendered": _now(),
                "seconds": round(time.time() - t0, 1), "engine": "cycles-cpu" if s.render_cpu else "eevee",
                "stats": _line_json(stdout, "STATS"), **body.model_dump()}
        (d / f"{key}.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
        with self.lib._lock:
            self.lib.update(sid, ver, snaps=self.lib.read(sid, ver)["snaps"] + [
                {k: info[k] for k in ("key", "file", "rendered", "seconds", "aspect", "postava")}])
        return {"scene_id": sid, "version": ver, **info}
