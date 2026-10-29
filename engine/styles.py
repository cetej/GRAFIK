"""Style library (G4, spec sc-20…sc-23) over the shared library of phase 4 (`ngm_shared.knihovna`).

KNIHOVNA/styles/<slug>.yaml          the shared style card, source of truth for GRAFIK and KLAPKA
KNIHOVNA/styles/<slug>/samples/      example images (jpg, <= 768 px)
KNIHOVNA/styles/<slug>/STYLE.md      the same card as prose for people, rewritten on every save
KNIHOVNA/styles/<slug>.png           KLAPKA's preview of the style, served read-only as sample `nahled.png`

The API keeps the flat card of G4 (label, medium, light, line, composition, avoid, signature, palette …);
`to_grafik()` maps the shared card onto it and `save()` merges back, keeping what KLAPKA wrote (look, film,
constraints). The three default styles tracked in git (`styles/`) seed a library that has no styles yet.

A style reaches the generator only as words (FLUX cannot transfer style from an image,
verified 2026-10-22): `knihovna.image_text()` turns the card into the sentence that follows
"Style:" in the prompt. The palette is measured from pixels (k-means), the prose comes
from the operator or from Claude looking at sample images (paid, opt-in).
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image

from ngm_shared import knihovna, knihovna_prevod

SAMPLE_EDGE = 768
PREVIEW = "nahled.png"
# Plain colour words for the prompt: FLUX reads "ochre" better than "#c9a03a".
COLOR_NAMES = {
    "black": (20, 20, 20), "charcoal": (54, 54, 54), "dark grey": (90, 90, 90), "grey": (128, 128, 128),
    "light grey": (190, 190, 190), "off-white": (238, 234, 225), "white": (250, 250, 250),
    "cream": (240, 228, 200), "beige": (215, 195, 160), "sand": (200, 175, 130), "tan": (180, 145, 100),
    "brown": (120, 80, 50), "dark brown": (70, 45, 30), "rust": (170, 75, 40), "terracotta": (195, 105, 75),
    "red": (200, 40, 40), "crimson": (150, 20, 40), "pink": (230, 150, 170), "orange": (235, 130, 40),
    "ochre": (200, 150, 50), "gold": (215, 175, 60), "yellow": (240, 210, 60), "olive": (120, 120, 50),
    "moss green": (100, 120, 70), "green": (60, 140, 70), "dark green": (30, 75, 45), "teal": (40, 120, 120),
    "turquoise": (60, 180, 180), "sky blue": (135, 185, 230), "blue": (50, 100, 190), "steel blue": (80, 115, 140),
    "navy": (25, 40, 75), "slate": (65, 80, 95), "purple": (110, 60, 140), "violet": (150, 110, 200),
    "lavender": (190, 175, 215),
}


class StyleError(ValueError):
    pass


def slugify(text: str) -> str:
    s = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:48] or "styl"


def color_name(hex_: str) -> str:
    rgb = np.array([int(hex_[i:i + 2], 16) for i in (1, 3, 5)], float)
    return min(COLOR_NAMES, key=lambda n: float(np.sum((rgb - COLOR_NAMES[n]) ** 2)))


def palette(images: list[bytes], k: int = 6, seed: int = 0) -> list[dict]:
    """k-means over the pixels of all images together; colours sorted by share."""
    px = []
    for data in images:
        img = Image.open(BytesIO(data)).convert("RGB")
        img.thumbnail((160, 160))
        px.append(np.asarray(img, float).reshape(-1, 3))
    x = np.concatenate(px)
    k = max(1, min(k, len(np.unique(x, axis=0))))
    rng = np.random.default_rng(seed)
    centers = x[rng.choice(len(x), k, replace=False)]
    for _ in range(25):
        labels = np.argmin(((x[:, None, :] - centers[None]) ** 2).sum(2), 1)
        new = np.array([x[labels == i].mean(0) if np.any(labels == i) else centers[i] for i in range(k)])
        if np.allclose(new, centers, atol=0.5):
            break
        centers = new
    share = np.bincount(labels, minlength=k) / len(x)
    out = []
    for i in np.argsort(-share):
        hex_ = "#{:02x}{:02x}{:02x}".format(*(int(round(c)) for c in centers[i]))
        out.append({"hex": hex_, "name": color_name(hex_), "share": round(float(share[i]), 3)})
    return out


def _palette(entries) -> list[dict]:
    """Valid palette entries, each with a colour name (the prompt says "ochre #c9a03a")."""
    return [{"hex": c["hex"].lower(), "name": c.get("name") or color_name(c["hex"].lower())}
            for c in entries or [] if isinstance(c, dict) and re.fullmatch(r"#[0-9a-fA-F]{6}", c.get("hex") or "")]


def to_grafik(slug: str, card: dict) -> dict:
    """The shared card as the flat G4 card of the API (same keys as the old style.json)."""
    obraz = card.get("obraz") if isinstance(card.get("obraz"), dict) else {}
    palette = _palette(obraz.get("palette"))
    text = lambda v: v if isinstance(v, str) else ""  # noqa: E731
    return {"slug": slug, "label": text(card.get("name")) or slug, "note": text(card.get("note")),
            "origin": card.get("origin") or "manual",
            **{f: text(obraz.get(f)) for f in ("medium", "light", "line", "composition")},
            "avoid": text(card.get("avoid", card.get("negative"))), "signature": text(obraz.get("signature")),
            "palette": palette, "puvod": text(card.get("puvod")),
            "created": text(card.get("created")), "updated": text(card.get("updated")),
            "prompt": knihovna.image_text({**card, "obraz": {**obraz, "palette": palette}})}


class StyleLibrary:
    def __init__(self, root: Path, defaults: Path | None = None):
        """`root` is the shared library (KNIHOVNA); `defaults` the styles tracked in git, copied in once
        when the library has no styles yet."""
        self.root = root
        if defaults is not None and defaults.is_dir() and not (root / "styles").exists() \
                and any(defaults.glob("*/style.json")):
            knihovna_prevod.run(klapka=None, grafik=defaults, target=root)

    def _check(self, slug: str) -> None:
        try:
            knihovna.card_path("style", slug, self.root)
        except knihovna.KnihovnaError as e:
            raise StyleError(f"neplatný název stylu {slug!r} (jen písmena bez diakritiky, číslice, - a _)") from e

    def _samples(self, slug: str) -> Path:
        return knihovna.item_dir("style", slug, self.root) / "samples"

    def _preview(self, slug: str) -> Path:
        return knihovna.card_path("style", slug, self.root).with_suffix(".png")

    def _public(self, slug: str, card: dict) -> dict:
        out = to_grafik(slug, card)
        samples = self._samples(slug)
        prompt = out.pop("prompt")
        out["samples"] = sorted(f.name for f in samples.glob("*.jpg")) if samples.exists() else []
        if self._preview(slug).exists():
            out["samples"].append(PREVIEW)
        out["prompt"] = prompt
        return out

    def get(self, slug: str) -> dict | None:
        self._check(slug)
        try:
            card = knihovna.read("style", slug, self.root)
        except knihovna.KnihovnaError as e:
            raise StyleError(str(e)) from e
        return None if card is None else self._public(slug, card)

    def list(self) -> list[dict]:
        try:
            cards = knihovna.cards("style", self.root)
        except knihovna.KnihovnaError as e:
            raise StyleError(str(e)) from e
        return sorted((self._public(s, c) for s, c in cards.items()),
                      key=lambda c: (c.get("origin") != "default", c["label"].lower()))

    def save(self, slug: str | None, data: dict) -> dict:
        label = (data.get("label") or "").strip()
        if not label:
            raise StyleError("styl potřebuje název")
        slug = slug or slugify(label)
        self._check(slug)
        now = datetime.now().isoformat(timespec="seconds")
        with knihovna.lock("style", slug, self.root):
            card = knihovna.read("style", slug, self.root) or {}
            # what KLAPKA keeps on the card (look, film, constraints, ...) stays as it is
            old = card.get("obraz") if isinstance(card.get("obraz"), dict) else {}
            obraz = {k: v for k, v in old.items() if k not in knihovna.OBRAZ}
            obraz |= {f: (data.get(f) or "").strip() for f in ("medium", "light", "line", "composition", "signature")}
            obraz["palette"] = _palette(data.get("palette"))
            obraz = {k: v for k, v in obraz.items() if v}
            card.pop("negative", None)
            card |= {"name": label, "note": (data.get("note") or "").strip(), "obraz": obraz,
                     "avoid": (data.get("avoid") or "").strip(),
                     "origin": data.get("origin") or card.get("origin") or "manual",
                     "puvod": (data.get("puvod") or card.get("puvod") or "").strip(),
                     "created": card.get("created") or now, "updated": now}
            card = {k: v for k, v in card.items() if v not in ("", {}) or k == "constraints"}
            film = card.get("film") if isinstance(card.get("film"), dict) else {}
            if not any(obraz.get(f) for f in ("medium", "light", "line", "composition", "palette")) \
                    and not card.get("look") and not (film.get("lens") or film.get("grade")):
                raise StyleError("karta je prázdná: vyplňte aspoň médium a techniku nebo paletu")
            knihovna.write("style", slug, card, self.root)
        return self.get(slug)

    def add_sample(self, slug: str, data: bytes) -> dict:
        self._check(slug)
        try:
            img = Image.open(BytesIO(data)).convert("RGB")
        except Exception as e:  # PIL raises many types for broken input
            raise StyleError(f"není to čitelný obrázek ({e})") from e
        img.thumbnail((SAMPLE_EDGE, SAMPLE_EDGE), Image.LANCZOS)
        with knihovna.lock("style", slug, self.root):
            if knihovna.read("style", slug, self.root) is None:
                raise StyleError("styl neexistuje")
            d = self._samples(slug)
            d.mkdir(parents=True, exist_ok=True)
            n = 1 + max((int(p.stem) for p in d.glob("*.jpg") if p.stem.isdigit()), default=0)
            img.save(d / f"{n}.jpg", quality=88)
        return self.get(slug)

    def remove_sample(self, slug: str, name: str) -> dict:
        self._check(slug)
        if name == PREVIEW:
            raise StyleError("náhled stylu je z KLAPKY, mění se tam")
        p = self._samples(slug) / name
        if not re.fullmatch(r"\d+\.jpg", name) or not p.exists():
            raise StyleError("ukázka neexistuje")
        p.unlink()
        return self.get(slug)

    def sample_path(self, slug: str, name: str) -> Path | None:
        self._check(slug)
        p = self._preview(slug) if name == PREVIEW else self._samples(slug) / name
        return p if (name == PREVIEW or re.fullmatch(r"\d+\.jpg", name)) and p.exists() else None

    def delete(self, slug: str) -> str:
        """Moves the card to the library's .trash/ (never rm): a style may be the operator's own work."""
        self._check(slug)
        try:
            return str(knihovna.trash("style", slug, self.root))
        except knihovna.KnihovnaError as e:
            raise StyleError("styl neexistuje") from e
