"""Batch of variants to pick from (the studio's "Dávka na výběr"; the client's variants() made on the Engine).

One batch = several ordinary Engine jobs (spread over styles, at most 4 images each) plus
library/variants/<id>/batch.json. Once every job has finished, varianty.html is built by
ngm_shared.variants_page (canonical source; STOPA re-exports it) next to the copied
PNGs, so the page's relative image URLs resolve under /api/v2/variants/<id>/.
"""
from __future__ import annotations

import html
import json
import re
import secrets
import shutil
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from engine.models import ImageRequest
from ngm_shared import variants_page

PAGE = "varianty.html"
_NAME = re.compile(r"^[\w.-]+$")


class VariantsIn(BaseModel):
    request: ImageRequest
    count: int = Field(default=8, ge=2, le=40)
    styles: list[str | None] = [None]          # slugs; None = the request's own style (or none)
    title: str | None = None


def plan(count: int, styles: list) -> list[tuple]:
    """count images spread over styles (round-robin share), each style cut into jobs of at most 4."""
    jobs = []
    for i, style in enumerate(styles):
        left = count // len(styles) + (i < count % len(styles))
        while left > 0:
            jobs.append((style, min(4, left)))
            left -= 4
    return jobs


class VariantStore:
    def __init__(self, root: Path):
        self.root = root

    def create(self, title: str, prompt: str, job_ids: list[str], count: int) -> dict:
        batch_id = datetime.now().strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(3)
        d = self.root / batch_id
        d.mkdir(parents=True)
        batch = {"id": batch_id, "title": title, "prompt": prompt, "job_ids": job_ids, "count": count,
                 "created": datetime.now().isoformat(timespec="seconds")}
        (d / "batch.json").write_text(json.dumps(batch, ensure_ascii=False, indent=2), encoding="utf-8")
        return batch

    def get(self, batch_id: str) -> dict | None:
        p = self.root / batch_id / "batch.json"
        if not _NAME.match(batch_id) or not p.is_file():
            return None
        return json.loads(p.read_text(encoding="utf-8"))

    def file(self, batch_id: str, name: str) -> Path | None:
        if not (_NAME.match(batch_id) and _NAME.match(name)):
            return None
        p = self.root / batch_id / name
        return p if p.is_file() else None

    def build_page(self, batch: dict, jobs: list[dict], image_path) -> Path:
        """PNGs of the finished jobs + manifest.json + varianty.html in the batch folder."""
        d = self.root / batch["id"]
        entries = []
        for job in jobs:
            if job["status"] != "done":
                continue
            req, res = job["request"], job["result"] or {}
            for n in range(len(res.get("files") or [])):
                vid = f"v{len(entries) + 1:02d}"
                shutil.copyfile(image_path(f"{job['job_id']}/{n}"), d / f"{vid}.png")
                params = {"styl": req.get("style_id") or req.get("style") or "bez stylu",
                          "seed": (res.get("seeds") or [None] * (n + 1))[n], "velikost": req.get("size"),
                          "backend": job.get("backend"), "verze": f"{job['job_id']}/{n}"}
                entries.append({"id": vid, "src": f"{vid}.png", "label": f"úloha {job['job_id']}/{n}",
                                "prompt": res.get("prompt_sent") or req.get("prompt"),
                                "params": {k: v for k, v in params.items() if v is not None}})
        manifest = {"title": batch["title"],
                    "note": f"{len(entries)} variant z GRAFIK Studia · zadání: {batch['prompt']}",
                    "variants": entries}
        (d / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return variants_page.write_page(variants_page.load_manifest(d / "manifest.json"), d / PAGE)


def waiting_page(batch: dict, done: int, total: int, failed: int) -> str:
    """Shown while the batch is still generating; reloads itself every 3 s."""
    extra = f" · {failed} selhalo" if failed else ""
    return (f'<!doctype html><html lang="cs"><head><meta charset="utf-8"><meta http-equiv="refresh" content="3">'
            f'<title>{html.escape(batch["title"])}</title><style>body{{font:16px system-ui;margin:3rem auto;'
            f'max-width:36rem;padding:0 1rem}}progress{{width:100%}}</style></head><body>'
            f'<h1>{html.escape(batch["title"])}</h1><p>Generuji varianty: {done} z {total} úloh hotovo{extra}.</p>'
            f'<progress value="{done}" max="{total}"></progress>'
            f'<p>Stránka se sama obnoví, až bude dávka hotová.</p></body></html>')
