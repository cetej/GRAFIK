"""Style library (G4, spec sc-20…sc-23): style cards in the POHYB format.

styles/<slug>/style.json  machine part, the source of truth (fields below)
styles/<slug>/STYLE.md    the same card as prose for people, rewritten on every save
styles/<slug>/samples/    example images (jpg, <= 768 px)

A style reaches the generator only as words (FLUX cannot transfer style from an image,
verified 2026-10-22): `prompt_text()` turns the card into the sentence that follows
"Style:" in the prompt. The palette is measured from pixels (k-means), the prose comes
from the operator or from Claude looking at sample images (paid, opt-in).
"""
from __future__ import annotations

import json
import re
import shutil
import threading
import unicodedata
from datetime import datetime
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image

SAMPLE_EDGE = 768
TEXT_FIELDS = ("medium", "light", "line", "composition", "avoid", "signature")
FIELD_LABELS = {"medium": "Médium a technika", "light": "Světlo", "line": "Linka a povrch",
                "composition": "Kompozice", "avoid": "Vyhnout se", "signature": "Podpisové znaky"}
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


def prompt_text(card: dict) -> str:
    """The words that follow "Style:" in the prompt."""
    parts = [card[f].strip().rstrip(".") for f in ("medium", "light", "line", "composition") if card.get(f, "").strip()]
    if card.get("palette"):
        parts.append("colour palette: " + ", ".join(f"{c.get('name') or color_name(c['hex'])} {c['hex']}"
                                                    for c in card["palette"]))
    if card.get("avoid", "").strip():
        parts.append("avoid " + card["avoid"].strip().rstrip("."))
    return ". ".join(p[0].upper() + p[1:] for p in parts)


def style_md(card: dict) -> str:
    lines = [f"# {card['label']}", "",
             "Karta stylu GRAFIK ve formátu POHYB. Strojová část je `style.json`; tento soubor se přepisuje při "
             "každém uložení, upravujte kartu ve studiu (záložka Styly) nebo ve `style.json`.", ""]
    if card.get("note"):
        lines += ["## Podstata", "", card["note"], ""]
    for f in TEXT_FIELDS:
        if card.get(f):
            lines += [f"## {FIELD_LABELS[f]}", "", card[f], ""]
    if card.get("palette"):
        lines += ["## Barvy", ""] + [f"- `{c['hex']}` {c.get('name', '')}" for c in card["palette"]] + [""]
    lines += ["## Do promptu (slovy, nikdy jako obrázek)", "", f"Style: {prompt_text(card)}.", ""]
    if card.get("puvod"):
        lines += ["## Původ", "", card["puvod"], ""]
    return "\n".join(lines)


class StyleLibrary:
    def __init__(self, root: Path):
        self.root = root
        self._lock = threading.Lock()

    def _dir(self, slug: str) -> Path:
        if not re.fullmatch(r"[a-z0-9][a-z0-9\-]{0,47}", slug or ""):
            raise StyleError("neplatný název stylu (jen malá písmena bez diakritiky, číslice a pomlčky)")
        return self.root / slug

    def get(self, slug: str) -> dict | None:
        p = self._dir(slug) / "style.json"
        if not p.exists():
            return None
        card = json.loads(p.read_text(encoding="utf-8"))
        samples = self._dir(slug) / "samples"
        card["samples"] = sorted(f.name for f in samples.glob("*.jpg")) if samples.exists() else []
        card["prompt"] = prompt_text(card)
        return card

    def list(self) -> list[dict]:
        if not self.root.exists():
            return []
        cards = [self.get(p.parent.name) for p in self.root.glob("*/style.json")]
        return sorted((c for c in cards if c), key=lambda c: (c.get("origin") != "default", c["label"].lower()))

    def save(self, slug: str | None, data: dict) -> dict:
        label = (data.get("label") or "").strip()
        if not label:
            raise StyleError("styl potřebuje název")
        slug = slug or slugify(label)
        d = self._dir(slug)
        old = self.get(slug) or {}
        card = {
            "slug": slug, "label": label, "note": (data.get("note") or "").strip(),
            "origin": data.get("origin") or old.get("origin") or "manual",
            **{f: (data.get(f) or "").strip() for f in TEXT_FIELDS},
            "palette": [{"hex": c["hex"].lower(), "name": c.get("name") or color_name(c["hex"].lower())}
                        for c in data.get("palette") or [] if re.fullmatch(r"#[0-9a-fA-F]{6}", c.get("hex", ""))],
            "puvod": (data.get("puvod") or old.get("puvod") or "").strip(),
            "created": old.get("created") or datetime.now().isoformat(timespec="seconds"),
            "updated": datetime.now().isoformat(timespec="seconds"),
        }
        if not any(card[f] for f in ("medium", "light", "line", "composition")) and not card["palette"]:
            raise StyleError("karta je prázdná: vyplňte aspoň médium a techniku nebo paletu")
        with self._lock:
            (d / "samples").mkdir(parents=True, exist_ok=True)
            (d / "style.json").write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")
            (d / "STYLE.md").write_text(style_md(card), encoding="utf-8")
        return self.get(slug)

    def add_sample(self, slug: str, data: bytes) -> dict:
        d = self._dir(slug)
        if not (d / "style.json").exists():
            raise StyleError("styl neexistuje")
        try:
            img = Image.open(BytesIO(data)).convert("RGB")
        except Exception as e:  # PIL raises many types for broken input
            raise StyleError(f"není to čitelný obrázek ({e})") from e
        img.thumbnail((SAMPLE_EDGE, SAMPLE_EDGE), Image.LANCZOS)
        with self._lock:
            (d / "samples").mkdir(exist_ok=True)
            n = 1 + max((int(p.stem) for p in (d / "samples").glob("*.jpg") if p.stem.isdigit()), default=0)
            img.save(d / "samples" / f"{n}.jpg", quality=88)
        return self.get(slug)

    def remove_sample(self, slug: str, name: str) -> dict:
        p = self._dir(slug) / "samples" / name
        if not re.fullmatch(r"\d+\.jpg", name) or not p.exists():
            raise StyleError("ukázka neexistuje")
        p.unlink()
        return self.get(slug)

    def sample_path(self, slug: str, name: str) -> Path | None:
        p = self._dir(slug) / "samples" / name
        return p if re.fullmatch(r"\d+\.jpg", name) and p.exists() else None

    def delete(self, slug: str) -> str:
        """Moves the card to styles/.trash/ (never rm): a style may be the operator's own work."""
        d = self._dir(slug)
        if not d.exists():
            raise StyleError("styl neexistuje")
        dest = self.root / ".trash" / f"{datetime.now():%Y%m%d-%H%M%S}-{slug}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(d), str(dest))
        return str(dest)
