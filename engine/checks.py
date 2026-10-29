"""POST /api/v2/checks — poradní kontrola obrázku proti zadání a kontrola logiky scény (ngm_shared.image_checks).

Placené (Claude Opus 5.5, effort low): 402 s odhadem bez `confirm_cost`. Odpověď přijde hned (jedno nebo dvě
volání, ~10–40 s), do fronty se nečeká. Výsledek je vždy poradní: upozornění se závažností a návrhem opravy,
nic se neblokuje. U obrázku z knihovny se výsledek připíše vedle něj do `image-<n>.checks.jsonl`.
"""
from __future__ import annotations

import base64
import json
from datetime import datetime
from io import BytesIO

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from PIL import Image
from pydantic import BaseModel

from engine.reflib import RefLibError
from ngm_shared import claude, image_checks as ic

ESTIMATE = {"brief": ic.BRIEF_USD, "logic": ic.LOGIC_USD}
LABEL = {"brief": "kontrola proti zadání", "logic": "kontrola logiky scény"}


class ChecksIn(BaseModel):
    brief: str                          # zadání obrázku nebo záběru
    image: str | None = None            # "<job_id>/<n>" obrázek z knihovny
    ref_id: str | None = None           # předloha (např. bílý snímek 3D skici)
    b64: str | None = None
    kinds: list[str] = ["brief"]        # brief | logic
    phase: str = "image"                # logika: plan (skica před generováním) | image (hotový obrázek)
    layout: str = ""                    # logika plánu: slovní popis rozmístění ve skice
    checklist: list[str] | None = None  # kontrola proti zadání: vlastní kontrolní seznam
    caller: str = "studio"
    confirm_cost: bool = False


def register(app: FastAPI, store, reflib, log_cost, ask=claude.ask) -> None:
    def image_of(body: ChecksIn):
        if body.image:
            path = store.image_path(body.image)
            if path is None:
                raise HTTPException(404, f"obrázek {body.image} neexistuje")
            return path
        if body.ref_id:
            try:
                path = reflib.image_path(body.ref_id)
            except RefLibError as e:
                raise HTTPException(400, str(e)) from e
            if path is None:
                raise HTTPException(404, f"předloha {body.ref_id} v knihovně neexistuje")
            return path
        if body.b64:
            try:
                raw = base64.b64decode(body.b64.split(",", 1)[-1])
                with Image.open(BytesIO(raw)) as im:
                    return im.convert("RGB")
            except (ValueError, OSError) as e:
                raise HTTPException(400, f"obrázek nejde přečíst ({e})") from e
        raise HTTPException(400, "pošlete image (<job_id>/<n>), ref_id nebo b64")

    @app.post("/api/v2/checks")
    def checks(body: ChecksIn):
        kinds = list(dict.fromkeys(body.kinds))
        if not kinds or any(k not in ESTIMATE for k in kinds):
            raise HTTPException(400, "kinds: brief a/nebo logic")
        if not body.brief.strip():
            raise HTTPException(400, "chybí zadání (brief)")
        if body.phase not in ("plan", "image"):
            raise HTTPException(400, "phase: plan nebo image")
        image = image_of(body)
        estimate = round(sum(ESTIMATE[k] for k in kinds), 4)
        if not body.confirm_cost:
            return JSONResponse(status_code=402, content={
                "detail": "Kontrola je placená (Claude) — pošlete znovu s confirm_cost=true.",
                "estimate_usd": estimate, "items": [{"what": LABEL[k], "usd": ESTIMATE[k]} for k in kinds]})
        results = []
        for kind in kinds:
            try:
                if kind == "brief":
                    r = ic.check_brief(image, body.brief, checklist=body.checklist, ask=ask)
                else:
                    r = ic.check_logic(image, body.brief, phase=body.phase, layout=body.layout, ask=ask)
            except claude.ClaudeError as e:
                if e.cost:
                    log(body, kind, e.cost, "failed")
                raise HTTPException(502, str(e)) from e
            log(body, kind, r["cost"], "ok")
            results.append(r)
        out = {"advisory": True, "image": body.image or body.ref_id or "b64", "brief": body.brief,
               "results": results, "cost_usd": round(sum(r["cost"]["usd"] for r in results), 4),
               "checked": datetime.now().isoformat(timespec="seconds")}
        if body.image:
            with open(store.image_path(body.image).with_suffix(".checks.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps({**out, "caller": body.caller}, ensure_ascii=False) + "\n")
        return out

    def log(body: ChecksIn, kind: str, cost: dict, status: str) -> None:
        log_cost({"job_id": None, "image": body.image, "caller": body.caller, "backend": f"claude:check-{kind}",
                  "n": 1, "usd": cost["usd"], "usage": cost, "status": status,
                  "items": [{"what": f"{LABEL[kind]} ({cost['model']})", "usd": cost["usd"]}]})
