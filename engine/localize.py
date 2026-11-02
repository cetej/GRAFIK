"""/api/v2/localize… — počeštění cizí infografiky vrstvou textu jako úloha `localize` ve společné frontě.

Knihovna: `ngm_shared.textlayer.localize` (Claude přečte → vymazat → vysázet PNG a SVG). Čtení stojí
peníze (Claude Opus 5.5, odhad READ_USD), proto 402 bez `confirm_cost`; s hotovými texty (`texts`
nebo `texts_from` = dřívější úloha) je to zdarma. Cena z `usage` jde do `library/costs.jsonl`.
`/api/v2/jobs` dál vrací jen obrázky; výsledek je i tak na `/api/v2/jobs/<id>/images/0`.
"""
from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime
from io import BytesIO
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from PIL import Image
from pydantic import BaseModel

from engine.reflib import RefLibError
from ngm_shared import claude
from ngm_shared.textlayer import localize as tl

KIND = "localize"
FILES = {"image-0.png": "image/png", "image-0.svg": "image/svg+xml", "image-0-bez-textu.png": "image/png",
         "image-0.texty.json": "application/json", "image-0.json": "application/json"}


class LocalizeIn(BaseModel):
    image: str | None = None            # "<job_id>/<n>" obrázek z knihovny
    ref_id: str | None = None           # předloha z knihovny předloh
    b64: str | None = None              # nahraný obrázek
    source_job: str | None = None       # job_id dřívějšího počeštění → stejný originál (oprava překladu)
    texts: dict | None = None           # přečtené (a opravené) texty → zdarma
    texts_from: str | None = None       # job_id dřívějšího počeštění → jeho texty, zdarma
    caller: str = "studio"
    confirm_cost: bool = False


class Localizer:
    def __init__(self, settings, store, log_cost, ask=claude.ask):
        self.s, self.store, self.log_cost, self.ask = settings, store, log_cost, ask

    def handlers(self) -> dict:
        return {KIND: self.run}

    def run(self, job_id: str, req: dict) -> dict:
        job_dir = self.s.library_dir / datetime.now().strftime("%Y-%m") / job_id
        caller = (self.store.get(job_id) or {}).get("caller")
        try:
            out = tl.localize(Path(req["image"]), job_dir, texts=req.get("texts"), ask=self.ask)
        except claude.ClaudeError as e:
            if e.cost:      # odpověď se naúčtovala, i když nejde použít
                self._log(job_id, caller, e.cost, "failed")
            raise
        cost = out["cost"]
        if cost:
            self._log(job_id, caller, cost, "ok")
        texts = json.loads(Path(out["texts"]).read_text(encoding="utf-8"))
        prov = {"job_id": job_id, "file": "image-0.png", "kind": KIND, "source": req.get("source"),
                "caller": caller, "texts_from": req.get("texts_from") or (f"claude:{cost['model']}" if cost else "zadané"),
                "image_kind": out["kind"], "warnings": out["warnings"], "layout": out["layout"],
                "vectorcraft_svg": Path(out["svg"]).name,
                "cost_usd": cost["usd"] if cost else 0.0, "usage": cost,
                # obraz je originál, text vysázel kód; překlad je od Claude → kontrola člověkem před zveřejněním
                "ai_generated": False, "ai_translated": bool(cost or req.get("texts_from")), "reviewed_by": None,
                "created": datetime.now().isoformat(timespec="seconds")}
        (job_dir / "image-0.json").write_text(json.dumps(prov, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"files": [out["png"]], "dir": str(job_dir), "svg": out["svg"], "base": out["base"],
                "texts": out["texts"], "image_kind": out["kind"], "warnings": out["warnings"],
                "elements": out["elements"], "cost_usd": cost["usd"] if cost else 0.0, "usage": cost,
                # text pro hledání v archivu: český a původní text popisků
                "text": " · ".join(el["cs"] for el in texts["elements"])[:4000],
                "text_src": " · ".join(el["en"] for el in texts["elements"])[:4000]}

    def _log(self, job_id: str, caller: str | None, cost: dict, status: str) -> None:
        self.log_cost({"job_id": job_id, "caller": caller, "backend": f"claude:{KIND}", "n": 1, "usd": cost["usd"],
                       "usage": cost, "status": status,
                       "items": [{"what": f"čtení textu z obrázku ({cost['model']})", "usd": cost["usd"]}]})


def register(app: FastAPI, loc: Localizer, store, reflib) -> None:
    uploads = loc.s.run_dir / "uploads"

    def original(job_id: str) -> tuple[Path, str]:
        job = store.get(job_id)
        if not job or job["kind"] != KIND or not Path(job["request"]["image"]).exists():
            raise HTTPException(404, f"originál počeštění {job_id} neexistuje")
        return Path(job["request"]["image"]), job["request"].get("source") or job_id

    def source(body: LocalizeIn) -> tuple[Path, str]:
        if body.source_job:
            return original(body.source_job)
        if body.image:
            path = store.image_path(body.image)
            if path is None:
                raise HTTPException(404, f"obrázek {body.image} neexistuje")
            return path, f"verze {body.image}"
        if body.ref_id:
            try:
                meta = reflib.get(body.ref_id)
            except RefLibError as e:
                raise HTTPException(400, str(e)) from e
            if meta is None:
                raise HTTPException(404, f"předloha {body.ref_id} v knihovně neexistuje")
            return reflib.image_path(body.ref_id), meta.get("page_url") or meta.get("title") or body.ref_id
        if body.b64:
            try:
                raw = base64.b64decode(body.b64.split(",", 1)[-1])
                with Image.open(BytesIO(raw)) as im:
                    im.load()
                    png = BytesIO()
                    im.convert("RGB").save(png, "PNG")
            except (ValueError, OSError) as e:
                raise HTTPException(400, f"obrázek nejde přečíst ({e})") from e
            data = png.getvalue()
            uploads.mkdir(parents=True, exist_ok=True)
            path = uploads / f"{hashlib.sha256(data).hexdigest()[:16]}.png"
            path.write_bytes(data)
            return path, "nahraný obrázek"
        raise HTTPException(400, "pošlete image (<job_id>/<n>), ref_id nebo b64")

    def earlier_texts(job_id: str) -> dict:
        job = store.get(job_id)
        if not job or job["kind"] != KIND or job["status"] != "done":
            raise HTTPException(404, f"hotové počeštění {job_id} neexistuje")
        return json.loads(Path(job["result"]["texts"]).read_text(encoding="utf-8"))

    @app.post("/api/v2/localize", status_code=202)
    def localize(body: LocalizeIn):
        path, src = source(body)
        texts = body.texts or (earlier_texts(body.texts_from) if body.texts_from else None)
        if texts is not None:
            try:
                texts = tl.normalize_texts(texts)
            except tl.LocalizeError as e:
                raise HTTPException(400, str(e)) from e
        usd = 0.0 if texts else tl.READ_USD
        if usd and not body.confirm_cost:
            return JSONResponse(status_code=402, content={
                "detail": "Čtení textu z obrázku je placené (Claude) — pošlete znovu s confirm_cost=true.",
                "estimate_usd": usd, "items": [{"what": f"čtení textu z obrázku ({tl.READ_MODEL})", "usd": usd}]})
        job_id = store.add_task(KIND, body.caller, f"claude:{tl.READ_MODEL}" if usd else "local", {
            "image": str(path), "source": src, "texts": texts, "texts_from": body.texts_from})
        job = store.get(job_id)
        return {"job_id": job_id, "status": job["status"], "position": job["position"], "estimate_usd": usd}

    @app.get("/api/v2/localize/jobs")
    def localize_jobs(limit: int = 30):
        return store.list(limit, kinds=(KIND,))

    @app.get("/api/v2/localize/estimate")
    def localize_estimate():
        return {"usd": tl.READ_USD}

    @app.get("/api/v2/localize/{job_id}/original")
    def localize_original(job_id: str):
        return FileResponse(original(job_id)[0])

    @app.get("/api/v2/localize/{job_id}/{name}")
    def localize_file(job_id: str, name: str):
        job = store.get(job_id)
        if not job or job["kind"] != KIND or job["status"] != "done" or name not in FILES:
            raise HTTPException(404, "soubor počeštění neexistuje")
        path = Path(job["result"]["dir"]) / name
        if not path.exists():
            raise HTTPException(404, "soubor počeštění neexistuje")
        return FileResponse(path, media_type=FILES[name])
