"""Guided workflow "historický objekt", approved by the operator on 2026-10-22:
reference -> clean side elevation -> fix in a box -> rotated 3/4 view from above
-> labels as a vector layer (G5).

Prompts generalise the verified quinquereme prompts (models/flux3-klein/
prompt_quinq_side.txt, prompt_quinq_34.txt). Every step is an ordinary Engine
job, so it shows up in the version tree and other projects can call it too.
State: workflows/<id>.json.
"""
from __future__ import annotations

import json
import re
import secrets
import threading
import time
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from engine.models import ImageRequest, Ref

SIDE_SIZE = "1920x640"        # 3:1 elevation, as in the 22. 10. test (qside_*.png)
ROTATE_SIZE = "1280x720"      # rendered at 1.5x (1920x1072) and downscaled: small figures stay intact
ROTATE_SUPERSAMPLE = 1.5

SIDE_PROMPT = (
    "Repaint the object in <ref_image_0> — {object} — as a refined, smooth, high-end 3D illustration in a pure "
    "side elevation view (exact profile, no perspective), with exactly the same proportions, length, height and "
    "details as the reference; trace the reference closely and do not change the shape.{extra} Clean, polished, "
    "finely modelled surfaces with smooth curves and crisp edges, like a premium museum-model render. The whole "
    "object is visible and centred with some margin. Any people only tiny and simple at true scale. Even, soft "
    "studio light, plain smooth dark navy background with no texture. No text, no letters, no labels, no extra objects."
)
EXTRA_REFS = " Use {refs} only as additional references for details, not for the viewpoint."

VIEWS = {
    "34_left": ("in a dynamic three-quarter view from slightly above: the camera is about 30 degrees above the object, "
                "looking at its front end from the front left, so the whole top surface is visible and the object "
                "recedes diagonally from the lower left to the upper right"),
    "34_right": ("in a dynamic three-quarter view from slightly above: the camera is about 30 degrees above the object, "
                 "looking at its front end from the front right, so the whole top surface is visible and the object "
                 "recedes diagonally from the lower right to the upper left"),
    "front": "in a frontal view from slightly above: the camera is about 20 degrees above, looking straight at its front end",
}
BACKGROUNDS = {
    "studio": "plain dark slate-blue background without texture",
    "sea": "a calm smooth sea with soft reflections under a plain hazy sky",
}
ROTATE_PROMPT = (
    "The same object as in <ref_image_0> — {object} — with exactly the same shape, proportions, colours and every "
    "detail, now shown as a smooth high-end 3D museum-model render {view}. One single consistent camera perspective "
    "for the entire object: all parts converge to the same vanishing point. Any people only tiny and at true scale. "
    "Soft studio light, crisp clean edges, smooth polished surfaces, {background}. No text, no letters, no labels."
)


class WorkflowRef(BaseModel):
    ref_id: str
    role: str = "geometry"


class Workflow(BaseModel):
    id: str
    kind: str = "historical"
    object: str = ""
    refs: list[WorkflowRef] = []
    side_job: str | None = None
    side_pick: str | None = None     # "<job>/<n>" chosen clean elevation
    fixed: str | None = None         # latest accepted fix of side_pick (box edits); falls back to side_pick
    rotate_job: str | None = None
    pick: str | None = None          # chosen rotated view
    view: str = "34_left"
    background: str = "studio"
    created: str = ""
    updated: str = ""
    # kind="infografika", řetězec z tématu (engine/chain.py); téma je v `object`
    qid: str | None = None
    vzor: str | None = None              # ref_id vloženého vzoru
    model: str = ""
    caller: str = "studio"
    stage: str = ""                      # podklady | navrhy | vyber | kontrola | hotovo | stop
    research_id: str | None = None
    step_job: str | None = None
    budget_usd: float = 0.0              # schválená cena celého řetězce
    spent_usd: float = 0.0
    navrhy: list[dict] = []
    rozbor: dict | None = None           # co ze vzoru držet a co změnit
    vyber: int | None = None             # id vybraného návrhu
    kontrola: dict | None = None         # poradní kontrola logiky, nic neblokuje
    stop_reason: str | None = None
    resume_stage: str | None = None
    resume_usd: float = 0.0              # cena zbytku řetězce, když stojí

    @property
    def base(self) -> str | None:
        return self.fixed or self.side_pick


class SideStep(BaseModel):
    n: int = Field(default=3, ge=1, le=4)
    confirm_cost: bool = False
    estimate_only: bool = False


class RotateStep(BaseModel):
    view: str = "34_left"
    background: str = "studio"
    n: int = Field(default=2, ge=1, le=4)
    confirm_cost: bool = False
    estimate_only: bool = False


def side_request(wf: Workflow, n: int, caller: str = "studio:pruvodce") -> ImageRequest:
    if not wf.object.strip():
        raise ValueError("popište objekt (co to je, z jaké doby)")
    image_refs = [r for r in wf.refs if r.role != "style"]
    if not image_refs:
        raise ValueError("přidejte aspoň jednu předlohu objektu")
    extra = EXTRA_REFS.format(refs=", ".join(f"<ref_image_{i}>" for i in range(1, len(image_refs)))) \
        if len(image_refs) > 1 else ""
    return ImageRequest(
        prompt=SIDE_PROMPT.format(object=wf.object.strip().rstrip("."), extra=extra), size=SIDE_SIZE, n=n,
        refs=[Ref(ref_id=r.ref_id, role=r.role) for r in image_refs], caller=caller)


def rotate_request(wf: Workflow, step: RotateStep, base_path: str, caller: str = "studio:pruvodce") -> ImageRequest:
    if step.view not in VIEWS or step.background not in BACKGROUNDS:
        raise ValueError(f"pohled {sorted(VIEWS)}, pozadí {sorted(BACKGROUNDS)}")
    return ImageRequest(
        prompt=ROTATE_PROMPT.format(object=wf.object.strip().rstrip("."), view=VIEWS[step.view],
                                    background=BACKGROUNDS[step.background]),
        size=ROTATE_SIZE, supersample=ROTATE_SUPERSAMPLE, n=step.n, parent=wf.base, caller=caller,
        refs=[Ref(path=base_path, role="subject", source=f"verze {wf.base}")])


class WorkflowStore:
    def __init__(self, root: Path):
        self.root = root
        self._lock = threading.Lock()

    def _path(self, wf_id: str) -> Path:
        if not re.fullmatch(r"[\w\-]+", wf_id):
            raise ValueError("neplatné id průvodce")
        return self.root / f"{wf_id}.json"

    def get(self, wf_id: str) -> Workflow | None:
        p = self._path(wf_id)
        return Workflow.model_validate_json(p.read_text(encoding="utf-8")) if p.exists() else None

    def save(self, wf: Workflow) -> Workflow:
        wf.updated = datetime.now().isoformat(timespec="seconds")
        path = self._path(wf.id)
        with self._lock:
            self.root.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(wf.model_dump_json(indent=2), encoding="utf-8")
            for attempt in range(5):        # atomic: a crash mid-write must not break resume; Windows refuses while a reader has the file open
                try:
                    tmp.replace(path)
                    break
                except PermissionError:
                    if attempt == 4:
                        raise
                    time.sleep(0.1)
        return wf

    def create(self, **fields) -> Workflow:
        now = datetime.now()
        wf = Workflow(id=now.strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(2),
                      created=now.isoformat(timespec="seconds"), **fields)
        return self.save(wf)

    def list(self) -> list[Workflow]:
        if not self.root.exists():
            return []
        items = []
        for p in self.root.glob("*.json"):
            try:
                items.append(Workflow.model_validate(json.loads(p.read_text(encoding="utf-8"))))
            except (ValueError, OSError) as e:      # one broken file must not stop the Engine start (chain.resume) or the whole list
                print(f"průvodce: {p.name} nejde přečíst: {e}", flush=True)
        return sorted(items, key=lambda w: w.updated, reverse=True)
