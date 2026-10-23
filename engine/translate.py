"""Czech brief -> English prompt tuned for the target generator.

Verified 2026-10-23 on FLUX 3 Klein (docs/spikes/2026-10-23-g2-studio.md): an English
box edit recoloured the fox, the same instruction in Czech changed almost nothing;
a Czech text-to-image prompt kept colours and mood but turned "maják" into a house.
So the Engine translates every Czech text field (prompt, edit instruction, style)
before the prompt is built. Paid (Claude), so it is part of the shown estimate;
results are cached, a repeated text costs nothing.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import threading
from io import BytesIO
from pathlib import Path

from PIL import Image

from engine.backends import BackendError, claude_text
from engine.models import EditSpec, ImageRequest

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
             "and the desired result (e.g. 'the fox has silver-grey fur like an arctic fox'). For a swap write "
             "'replace X with Y'; turn a vague wish into a concrete visible change."),
    "style": "Translate the Czech style description into English style descriptors.",
}
# Sent with an edit instruction together with a crop of the edited box (PromptEnhancer analysis,
# cetej/GRAFIK#9): the user's Czech word for the object may not match what the box really shows.
CROP_GUIDE = ("The attached picture is the area of the image that will be edited. Name the object by what is actually "
              "visible in it (its kind, colour, material), not only by the word the user chose. Everything outside "
              "this area stays unchanged, so describe only the change inside it.")
# Text that should appear in the image (signs, captions) is in quotes; it must stay in its own language
# and spelling, otherwise the generator paints the English word (cetej/GRAFIK#9, point 1).
RULES = ("Keep every fact and do not add new objects, people or historical details. Text in quotation marks is "
         "lettering that must appear in the image: copy it unchanged, in its original language and spelling, inside "
         "double quotes. Keep tags such as <ref_image_0> or <edit_1> exactly as they are. Answer with the English "
         "text only.\n\nCzech text:\n")
# Terms from the editorial term database (engine/termdb.py), only the unambiguous ones (operator 2026-10-23).
GLOSSARY_GUIDE = ("Terminology from the editorial term database; where the Czech text means these, use the English "
                  "terms (a Latin name in brackets identifies the species): {terms}. ")
QUOTED = re.compile(r'"[^"]*"|„[^“”"]*[“”"]|“[^”]*”')
CROP_MAX_EDGE = 512


def family(backend: str) -> str:
    return "gemini" if "nano-banana" in backend or backend == "nb-pro" else "flux"


def is_czech(text: str | None) -> bool:
    return bool(text and CZECH.search(text))


def still_czech(en: str) -> bool:
    """A translation that did not happen: empty, or Czech outside the quoted lettering. A place name with
    diacritics ("Kutná Hora") may stay, so it takes more than a fifth of the words to count as Czech."""
    words = QUOTED.sub(" ", en).split()
    if not words:
        return not en.strip()
    return sum(bool(CZECH.search(w)) for w in words) > len(words) / 5


def edit_crop(path: str, edit: EditSpec) -> bytes:
    """The edited box of the parent image, at most CROP_MAX_EDGE px, as PNG."""
    img = Image.open(path).convert("RGB")
    w, h = img.size
    top, left, bottom, right = edit.bbox
    crop = img.crop((round(left * w / 1000), round(top * h / 1000), round(right * w / 1000), round(bottom * h / 1000)))
    crop.thumbnail((CROP_MAX_EDGE, CROP_MAX_EDGE))
    out = BytesIO()
    crop.save(out, "PNG")
    return out.getvalue()


def fields(req: ImageRequest) -> list[tuple[str, str, str, bytes | None]]:
    """(path, kind, text, image) of every Czech text field; path tells apply() where to write it back.
    An edit instruction carries the crop of its box (the API puts the parent first in refs)."""
    if req.translate == "off":
        return []
    out = []
    if req.edit:
        if is_czech(req.edit.instruction):
            parent = req.refs[0].path if req.refs and req.refs[0].path else None
            out.append(("edit", "edit", req.edit.instruction, edit_crop(parent, req.edit) if parent else None))
    elif is_czech(req.prompt):
        out.append(("prompt", "prompt", req.prompt, None))
    if is_czech(req.style):
        out.append(("style", "style", req.style, None))
    for i, r in enumerate(req.refs):
        if r.role == "style" and is_czech(r.text):
            out.append((f"ref:{i}", "style", r.text, None))
    return out


class Translator:
    def __init__(self, cache_path: Path, termdb=None):
        self.cache_path = cache_path
        self.termdb = termdb  # engine.termdb.TermDB or None
        self._lock = threading.Lock()
        self._cache: dict[str, str] = {}
        if cache_path.exists():
            for line in cache_path.read_text(encoding="utf-8").splitlines():
                if line:
                    e = json.loads(line)
                    self._cache[e["key"]] = e["en"]

    @staticmethod
    def key(backend: str, kind: str, text: str, image: bytes | None = None, glossary: list[str] | None = None) -> str:
        base = f"{family(backend)}|{kind}|{text.strip()}"
        if image:  # same words over a different box are a different translation
            base += "|" + hashlib.sha256(image).hexdigest()
        if glossary:  # a changed termdb entry gives a new translation
            base += "|" + "; ".join(glossary)
        return hashlib.sha256(base.encode()).hexdigest()

    def glossary(self, text: str) -> list[str]:
        return self.termdb.glossary(text) if self.termdb and self.termdb.available else []

    def pending(self, req: ImageRequest) -> tuple[int, int]:
        """(fields that would be paid for, how many of them send a crop) - Czech and not cached."""
        crops = [image is not None for _, kind, text, image in fields(req)
                 if self.key(req.backend, kind, text, image, self.glossary(text)) not in self._cache]
        return len(crops), sum(crops)

    def translate(self, backend: str, kind: str, text: str, image: bytes | None = None) -> tuple[str, bool]:
        """(English text, paid?). Raises BackendError when the answer is empty or still Czech; such an
        answer is never cached, so the next attempt asks again."""
        terms = self.glossary(text)
        k = self.key(backend, kind, text, image, terms)
        if k in self._cache:
            return self._cache[k], False
        gloss = GLOSSARY_GUIDE.format(terms="; ".join(terms)) if terms else ""
        instruction = f"{FAMILY_GUIDE[family(backend)]} {KIND_GUIDE[kind]} {gloss}{RULES}{text}"
        if image:
            content = [{"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                    "data": base64.b64encode(image).decode()}},
                       {"type": "text", "text": f"{CROP_GUIDE} {instruction}"}]
        else:
            content = instruction
        en = claude_text(content, 600, "překlad zadání")
        if still_czech(en):
            raise BackendError(f"překlad zadání selhal: odpověď je {'prázdná' if not en.strip() else 'pořád česky'} "
                               f"({en[:80]!r}); nic se negenerovalo, zkuste to znovu nebo zadání napište anglicky")
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
        for path, kind, text, image in fields(req):
            en, paid = self.translate(req.backend, kind, text, image)
            done.append({"field": path, "cs": text, "en": en, "paid": paid, "crop": image is not None,
                         "glossary": self.glossary(text)})
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
