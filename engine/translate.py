"""Czech brief -> English prompt tuned for the target generator.

Verified 2026-10-23 on FLUX 3 Klein (docs/spikes/2026-10-23-g2-studio.md): an English
box edit recoloured the fox, the same instruction in Czech changed almost nothing;
a Czech text-to-image prompt kept colours and mood but turned "maják" into a house.
So the Engine translates every Czech text field (prompt, edit instruction, style)
before the prompt is built. Paid (Claude), so it is part of the shown estimate;
results are cached, a repeated text costs nothing.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
from pathlib import Path

from engine.backends import claude_text
from engine.models import ImageRequest

TRANSLATE_USD = 0.01
CZECH = re.compile(r"[ěščřžýáíéůúťďňóĚŠČŘŽÝÁÍÉŮÚŤĎŇÓ]")

FAMILY_GUIDE = {
    "flux": ("You write prompts for FLUX image models. They follow descriptive English prose best: concrete nouns, "
             "materials, colours, composition and camera viewpoint, lighting, medium."),
    "gemini": ("You write prompts for Google's Gemini image model (Nano Banana). It follows clear, natural English "
               "instructions; keep the structure of the request."),
}
KIND_GUIDE = {
    "prompt": "Translate the Czech image description into one English prompt.",
    "edit": ("Translate the Czech image-edit instruction into one short, concrete English phrase that names the object "
             "and the desired result (e.g. 'the fox has silver-grey fur like an arctic fox')."),
    "style": "Translate the Czech style description into English style descriptors.",
}
RULES = ("Keep every fact and do not add new objects, people or historical details. Keep tags such as <ref_image_0> "
         "or <edit_1> exactly as they are. Answer with the English text only.\n\nCzech text:\n")


def family(backend: str) -> str:
    return "gemini" if "nano-banana" in backend or backend == "nb-pro" else "flux"


def is_czech(text: str | None) -> bool:
    return bool(text and CZECH.search(text))


def fields(req: ImageRequest) -> list[tuple[str, str, str]]:
    """(path, kind, text) of every Czech text field; path tells apply() where to write it back."""
    if req.translate == "off":
        return []
    out = []
    if req.edit:
        if is_czech(req.edit.instruction):
            out.append(("edit", "edit", req.edit.instruction))
    elif is_czech(req.prompt):
        out.append(("prompt", "prompt", req.prompt))
    if is_czech(req.style):
        out.append(("style", "style", req.style))
    for i, r in enumerate(req.refs):
        if r.role == "style" and is_czech(r.text):
            out.append((f"ref:{i}", "style", r.text))
    return out


class Translator:
    def __init__(self, cache_path: Path):
        self.cache_path = cache_path
        self._lock = threading.Lock()
        self._cache: dict[str, str] = {}
        if cache_path.exists():
            for line in cache_path.read_text(encoding="utf-8").splitlines():
                if line:
                    e = json.loads(line)
                    self._cache[e["key"]] = e["en"]

    @staticmethod
    def key(backend: str, kind: str, text: str) -> str:
        return hashlib.sha256(f"{family(backend)}|{kind}|{text.strip()}".encode()).hexdigest()

    def pending(self, req: ImageRequest) -> int:
        """How many fields would be paid for (Czech and not cached)."""
        return sum(self.key(req.backend, kind, text) not in self._cache for _, kind, text in fields(req))

    def translate(self, backend: str, kind: str, text: str) -> tuple[str, bool]:
        """(English text, paid?)"""
        k = self.key(backend, kind, text)
        if k in self._cache:
            return self._cache[k], False
        en = claude_text(f"{FAMILY_GUIDE[family(backend)]} {KIND_GUIDE[kind]} {RULES}{text}", 600, "překlad zadání")
        with self._lock:
            self._cache[k] = en
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"key": k, "family": family(backend), "kind": kind, "cs": text, "en": en},
                                   ensure_ascii=False) + "\n")
        return en, True

    def apply(self, req: ImageRequest) -> tuple[ImageRequest, list[dict]]:
        """Request with Czech fields replaced by English, plus a record of what was translated."""
        done, update, refs = [], {}, list(req.refs)
        for path, kind, text in fields(req):
            en, paid = self.translate(req.backend, kind, text)
            done.append({"field": path, "cs": text, "en": en, "paid": paid})
            if path == "prompt":
                update["prompt"] = en
            elif path == "style":
                update["style"] = en
            elif path == "edit":
                update["edit"] = req.edit.model_copy(update={"instruction": en})
            else:
                i = int(path.split(":")[1])
                refs[i] = refs[i].model_copy(update={"text": en})
        if any(d["field"].startswith("ref:") for d in done):
            update["refs"] = refs
        return req.model_copy(update=update), done
