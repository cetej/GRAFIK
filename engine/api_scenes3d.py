"""/api/v2/scenes3d… — 3D scenes for infographics (docs/plans/2026-10-27-3d-sceny.md): save a scene as a new
version, remember the viewer's camera, render a clay still from it, hand the still to the generator as a
`geometry` ref once every model in it is checked."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from engine import scenes3d as sc
from engine.models3d import Model3dError
from engine.scenes3d import SceneCameraIn, SceneIn, SceneRenderIn, Scenes3d


def register(app: FastAPI, scenes: Scenes3d, models3d, store) -> None:
    lib = scenes.lib

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except Model3dError as e:
            raise HTTPException(404 if "neexistuje" in str(e) else 400, str(e)) from e

    def with_check(meta: dict) -> dict:
        return {**meta, "problems": sc.problems(meta), "unchecked": call(sc.unchecked, meta, models3d),
                "hint": sc.size_hint(meta)}

    @app.get("/api/v2/scenes3d")
    def scenes_list():
        return lib.list()

    @app.get("/api/v2/scenes3d/figure.glb")
    def scenes_figure():
        return FileResponse(sc.FIGURE_GLB, media_type="model/gltf-binary")

    @app.get("/api/v2/scenes3d/jobs")
    def scenes_jobs(limit: int = 30):
        return store.list(limit, kinds=sc.KINDS)

    @app.post("/api/v2/scenes3d", status_code=201)
    def scenes_create(body: SceneIn):
        objects, figure = call(sc.normalize, body, models3d)
        meta = call(lib.new_version, body.scene_id, body.title, {
            "objects": objects, "postava": figure, "aspect": body.aspect,
            "camera": body.camera.model_dump() if body.camera else None})
        # a size typed by hand goes to the model too, so the next scene has it (DECISIONS 2026-10-27, Q2)
        for o, raw in zip(objects, body.objects):
            if o.get("model") and raw.rozmer:
                m = models3d.lib.read(o["model"], o["model_version"])
                if sc.size_from_model(m)[0] is None:
                    models3d.lib.update(o["model"], o["model_version"], rozmer_m=raw.rozmer,
                                        rozmer_zdroj=raw.rozmer_zdroj or "zadáno ručně ve scéně")
        return with_check(meta)

    @app.get("/api/v2/scenes3d/{scene_id}")
    def scenes_get(scene_id: str):
        return call(lib.get, scene_id)

    @app.get("/api/v2/scenes3d/{scene_id}/{version}")
    def scenes_version(scene_id: str, version: str):
        return with_check(call(lib.read, scene_id, version))

    @app.post("/api/v2/scenes3d/{scene_id}/{version}/camera")
    def scenes_camera(scene_id: str, version: str, body: SceneCameraIn):
        return call(lib.update, scene_id, version, camera=body.camera.model_dump())

    @app.post("/api/v2/scenes3d/{scene_id}/{version}/render", status_code=202)
    def scenes_render(scene_id: str, version: str, body: SceneRenderIn):
        if body.aspect not in sc.ASPECTS:
            raise HTTPException(400, f"poměr stran musí být jeden z {list(sc.ASPECTS)}")
        meta = call(lib.read, scene_id, version)
        if bad := sc.problems(meta):
            raise HTTPException(409, "scénu zatím nejde vyrenderovat: " + "; ".join(bad))
        key = sc.render_key(scene_id, version, body)
        if (lib.vdir(scene_id, version) / "snaps" / f"{key}.png").is_file():
            return {"key": key, "job_id": None, "file": f"snaps/{key}.png"}
        job_id = store.add_task("scene3d", "studio", "blender", {
            "scene_id": scene_id, "version": version, "key": key, "body": body.model_dump()})
        return {"key": key, "job_id": job_id, "file": f"snaps/{key}.png"}

    def file_of(scene_id: str, version: str, name: str) -> Path:
        d = call(lib.vdir, scene_id, version)
        p = (d / name).resolve()
        if not p.is_file() or not p.is_relative_to(d.resolve()):
            raise HTTPException(404, "soubor neexistuje")
        return p

    @app.get("/api/v2/scenes3d/{scene_id}/{version}/files/{name:path}")
    def scenes_file(scene_id: str, version: str, name: str):
        return FileResponse(file_of(scene_id, version, name))

    @app.get("/api/v2/scenes3d/{scene_id}/{version}/as-ref")
    def scenes_as_ref(scene_id: str, version: str, snap: str):
        """The still as a generator ref (role geometry), only when every model in it is checked (sc-3), with the
        size sentence for the prompt."""
        meta = call(lib.read, scene_id, version)
        if bad := sc.unchecked(meta, models3d):
            raise HTTPException(409, "ve scéně jsou nezkontrolované modely: " + ", ".join(bad)
                                + " — zkontrolujte je v záložce Modely")
        png = file_of(scene_id, version, f"snaps/{snap}.png")
        info = file_of(scene_id, version, f"snaps/{snap}.json")
        figure = bool(json.loads(info.read_text(encoding="utf-8")).get("postava"))
        lic = sorted({r["license"] for o in meta["objects"] if o.get("model")
                      for r in models3d.lib.read(o["model"], o["model_version"])["refs"] if r.get("license")})
        names = ", ".join(dict.fromkeys(o["nazev"] for o in meta["objects"]))
        return {"path": str(png), "role": "geometry", "file": f"snaps/{snap}.png", "hint": sc.size_hint(meta, figure),
                "source": f"3D scéna {meta['title']} {version} ({names}), bílý snímek z kamery prohlížeče",
                "license": ", ".join(lic) or None}
