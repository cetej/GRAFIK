"""Image backends. flux-local is the default and costs 0 USD; every other
backend is paid and runs only when the caller names it explicitly and confirms
the estimate (operator decision 2026-10-22). No backend ever falls back to
another one."""
from __future__ import annotations

import base64
import json
import math
import random
import re
from io import BytesIO
from dataclasses import dataclass

import httpx
from PIL import Image

from engine.config import Settings
from engine.keys import get_key
from engine.models import ImageRequest
from engine.sdserver import SdServer


class BackendError(RuntimeError):
    pass


@dataclass
class Generated:
    images: list[bytes]
    seeds: list[int | None]
    model: str
    params: dict


class FluxLocal:
    name = "flux-local"
    model = "flux-3-image-klein-q4 (sd.cpp a77d362)"

    def __init__(self, settings: Settings, server: SdServer):
        self.s = settings
        self.server = server

    def usd_for(self, req: ImageRequest) -> float:
        return 0.0

    def eta_s(self, req: ImageRequest) -> int:
        """Rough generation time on the RTX 4060: measured 0.59 MP 26 s, 1.05 MP 40 s (cold), 2.06 MP 85 s;
        with an image ref ~1.9x (1.03 MP edit 79-84 s)."""
        w, h = self.render_size(req)
        ref_factor = 1.9 if any(r.role != "style" for r in req.refs) else 1.0
        return round((5 + 38 * w * h / 1e6 * ref_factor) * req.n)

    def validate(self, req: ImageRequest) -> None:
        if req.width * req.height > self.s.max_pixels:
            raise BackendError(
                f"{req.size} je nad strop lokálního FLUX na 8 GB (nejvýš {self.s.max_pixels} px, např. 1920x1088)."
            )

    def render_size(self, req: ImageRequest) -> tuple[int, int]:
        """Size FLUX actually renders: size × supersample, capped to the pixel
        ceiling with the aspect ratio kept, floored to multiples of 16."""
        if not req.supersample or req.supersample <= 1:
            return req.width, req.height
        factor = min(req.supersample, math.sqrt(self.s.max_pixels / (req.width * req.height)))
        w, h = int(req.width * factor) // 16 * 16, int(req.height * factor) // 16 * 16
        return max(w, req.width), max(h, req.height)

    def payload(self, req: ImageRequest, prompt: str, ref_pngs: list[bytes], seed: int) -> dict:
        w, h = self.render_size(req)
        p = {
            "prompt": prompt, "width": w, "height": h, "seed": seed,
            "sample_params": {"sample_steps": req.steps or self.s.steps},
        }
        if ref_pngs:
            p["ref_images"] = [base64.b64encode(b).decode() for b in self.fit_refs(ref_pngs)]
        if w * h > self.s.vae_tiling_above_pixels:
            p["vae_tiling_params"] = {"enabled": True}
        return p

    # sd-server feeds refs at their own resolution; a 2048x1028 Commons photo plus a 1920x640 render
    # ran out of VRAM on 8 GB (2026-10-23). All refs together get ~1.1 MP, which keeps a single
    # 1344x768 edit parent untouched.
    REF_MAX_PIXELS = 1_100_000

    @classmethod
    def fit_refs(cls, pngs: list[bytes]) -> list[bytes]:
        imgs = [Image.open(BytesIO(b)) for b in pngs]
        total = sum(i.width * i.height for i in imgs)
        if total <= cls.REF_MAX_PIXELS:
            return pngs
        k = math.sqrt(cls.REF_MAX_PIXELS / total)
        out = []
        for img in imgs:
            buf = BytesIO()
            img.resize((max(16, int(img.width * k)), max(16, int(img.height * k))), Image.LANCZOS).save(buf, format="PNG")
            out.append(buf.getvalue())
        return out

    @staticmethod
    def downscale(png: bytes, width: int, height: int) -> bytes:
        img = Image.open(BytesIO(png))
        if img.size == (width, height):
            return png
        buf = BytesIO()
        img.resize((width, height), Image.LANCZOS).save(buf, format="PNG")
        return buf.getvalue()

    def run(self, req: ImageRequest, prompt: str, ref_pngs: list[bytes]) -> Generated:
        self.validate(req)
        base_seed = req.seed if req.seed is not None else random.randint(0, 2**31 - 1)
        images, seeds = [], []
        rw, rh = self.render_size(req)
        for i in range(req.n):
            seed = base_seed + i
            png = self.server.generate(self.payload(req, prompt, ref_pngs, seed))[0]
            images.append(self.downscale(png, req.width, req.height))
            seeds.append(seed)
        return Generated(images, seeds, self.model,
                         {"steps": req.steps or self.s.steps, "cfg_scale": self.s.cfg_scale,
                          "sampler": self.s.sampler, "size": req.size, "render_size": f"{rw}x{rh}"})


# Gemini nano-banana-pro-preview, price per image 1K–2K from ai.google.dev (fetched 2026-08-15,
# old GRAFIK registry). The REST call mirrors grafik/providers/nbpro.py.
NB_MODEL = "nano-banana-pro-preview"
NB_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{NB_MODEL}:generateContent"
NB_RATIOS = {"1:1": 1.0, "3:4": 0.75, "4:3": 4 / 3, "16:9": 16 / 9, "9:16": 9 / 16}
NB_MAX_REFS = 3


class NanoBananaPro:
    name = "nb-pro"
    model = f"google/{NB_MODEL}"
    usd_per_image = 0.134

    def usd_for(self, req: ImageRequest) -> float:
        return self.usd_per_image * req.n

    def validate(self, req: ImageRequest) -> None:
        if req.supersample:
            raise BackendError("supersample umí jen flux-local")
        if sum(r.role != "style" for r in req.refs) > NB_MAX_REFS:
            raise BackendError(f"nb-pro: nejvýš {NB_MAX_REFS} obrazové předlohy")

    def run(self, req: ImageRequest, prompt: str, ref_pngs: list[bytes]) -> Generated:
        self.validate(req)
        key = get_key("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GEMINI_API_KEY")
        if not key:
            raise BackendError("nb-pro: chybí Gemini klíč (GEMINI_API_KEY / GOOGLE_GEMINI_API_KEY)")
        ratio = min(NB_RATIOS, key=lambda r: abs(NB_RATIOS[r] - req.width / req.height))
        image_size = "1K" if max(req.width, req.height) <= 1024 else "2K"
        parts = [{"text": prompt}] + [
            {"inlineData": {"mimeType": "image/png", "data": base64.b64encode(b).decode()}} for b in ref_pngs
        ]
        images = []
        for _ in range(req.n):
            images.append(self._call(key, parts, ratio, image_size))
        return Generated(images, [None] * req.n, self.model, {"aspect_ratio": ratio, "image_size": image_size})

    def _call(self, key: str, parts: list[dict], ratio: str, image_size: str) -> bytes:
        try:
            r = httpx.post(
                NB_URL, headers={"x-goog-api-key": key},
                json={"contents": [{"parts": parts}],
                      "generationConfig": {"responseModalities": ["TEXT", "IMAGE"],
                                           "imageConfig": {"aspectRatio": ratio, "imageSize": image_size}}},
                timeout=300,
            )
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise BackendError(f"nb-pro: volání selhalo: {e}") from e
        body = r.json()
        for cand in body.get("candidates") or []:
            for part in (cand.get("content") or {}).get("parts") or []:
                inline = part.get("inlineData") or part.get("inline_data")
                if inline and inline.get("data"):
                    return base64.b64decode(inline["data"])
        raise BackendError(f"nb-pro: odpověď bez obrázku: {str(body)[:300]}")


# Image-only style refs are turned into words by Claude Haiku (paid, opt-in like
# any paid step). Estimate: one image (~1.6k input tokens) + ~250 output tokens.
CLAUDE_MODEL = "claude-haiku-5-5"
STYLE_DESCRIBE_USD = 0.01
# Edit translation sends the box crop (<= 512 px, ~350 input tokens) on top of the text.
CROP_TRANSLATE_USD = 0.002
STYLE_INSTRUCTION = (
    "Describe only the visual STYLE of this image so an image generator can reproduce it on a different "
    "subject: medium, technique, colour palette, lighting, line quality, texture, rendering, composition "
    "habits. Do not describe the subject or content. One English paragraph, at most 80 words."
)


# Style card from 1–5 sample images (G4 sc-20): the same price as a style description, the images go
# downscaled to 768 px (~800 tokens each, Haiku 5.5 ~0.0005 USD for five).
STYLE_CARD_MAX_IMAGES = 5
STYLE_CARD_INSTRUCTION = (
    "These images share one visual style. Describe only that style so an image generator can reproduce it on "
    "any other subject; never describe what the images show. Answer with a JSON object and nothing else, keys:\n"
    '"label": a short Czech name for the style (2-4 words),\n'
    '"note": one Czech sentence saying what the style is good for,\n'
    '"medium": English, medium and technique (for example "watercolour on rough paper, loose wet-in-wet washes"),\n'
    '"light": English, lighting,\n'
    '"line": English, line quality, edges and surface texture,\n'
    '"composition": English, typical framing, background and use of space,\n'
    '"avoid": English, what would break the style,\n'
    '"signature": Czech, 3 short features that tell this style apart, separated by " · ".\n'
    "Each English value at most 25 words. Do not name colours, the palette is measured from the pixels."
)


def describe_style_card(images: list[bytes]) -> dict:
    content = []
    for data in images[:STYLE_CARD_MAX_IMAGES]:
        img = Image.open(BytesIO(data)).convert("RGB")
        img.thumbnail((768, 768))
        buf = BytesIO()
        img.save(buf, "PNG")
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                    "data": base64.b64encode(buf.getvalue()).decode()}})
    content.append({"type": "text", "text": STYLE_CARD_INSTRUCTION})
    text = claude_text(content, 900, "popis stylu")
    m = re.search(r"\{.*\}", text, re.S)
    try:
        card = json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        card = None
    if not isinstance(card, dict):
        raise BackendError(f"popis stylu: odpověď není JSON ({text[:120]!r})")
    return {k: str(card.get(k) or "").strip() for k in
            ("label", "note", "medium", "light", "line", "composition", "avoid", "signature")}


# Label proposal for an infographic (G5): parts of the object with a point on the image, never facts.
LABELS_USD = 0.01
LABELS_INSTRUCTION = (
    "This image shows: {title}. Propose 4 or 5 labels for an infographic: the most important visible parts of the "
    "main object. For each give the Czech name of the part (1-3 words), an optional short Czech detail (at most "
    "5 words, only what is visible, no numbers or dates), and the point on the image where the part is, as x and y "
    "on a 0-1000 grid of the image width and height (0,0 is the top-left corner). Prefer parts spread over the "
    "whole object. Answer with a JSON list and nothing else: "
    '[{{"text": "...", "small": "...", "x": 0, "y": 0}}]'
)


def suggest_labels(png: bytes, title: str) -> list[dict]:
    img = Image.open(BytesIO(png)).convert("RGB")
    img.thumbnail((1024, 1024))
    buf = BytesIO()
    img.save(buf, "PNG")
    text = claude_text([
        {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                     "data": base64.b64encode(buf.getvalue()).decode()}},
        {"type": "text", "text": LABELS_INSTRUCTION.format(title=title or "an object")}], 900, "návrh popisků")
    m = re.search(r"\[.*\]", text, re.S)
    try:
        items = json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        items = None
    if not isinstance(items, list):
        raise BackendError(f"návrh popisků: odpověď není JSON seznam ({text[:120]!r})")
    out = []
    for it in items[:6]:
        try:
            x, y = (min(1000, max(0, int(float(it[k])))) for k in ("x", "y"))
        except (KeyError, TypeError, ValueError):
            continue
        if str(it.get("text") or "").strip():
            out.append({"text": str(it["text"]).strip(), "small": str(it.get("small") or "").strip(), "anchor": [x, y]})
    return out


def claude_text(content, max_tokens: int, what: str, model: str = CLAUDE_MODEL) -> str:
    """One Claude Messages call -> text. Paid: callers gate it behind a shown estimate."""
    key = get_key("ANTHROPIC_API_KEY")
    if not key:
        raise BackendError(f"{what}: chybí ANTHROPIC_API_KEY")
    body = {"model": model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": content}]}
    if "haiku" in model:
        # Haiku 5.5 thinks by default and the thinking counts against max_tokens: a 500-token expand
        # came back with no text at all (2026-10-23). Short rewrites need no thinking.
        body["thinking"] = {"type": "disabled"}
    try:
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
            json=body,
            timeout=120,
        )
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise BackendError(f"{what} selhalo: {e}") from e
    data = r.json()
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()
    if not text:
        raise BackendError(f"{what}: Claude nevrátil žádný text (stop_reason={data.get('stop_reason')})")
    return text


def describe_style(png: bytes) -> str:
    return claude_text([
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": base64.b64encode(png).decode()}},
        {"type": "text", "text": STYLE_INSTRUCTION}], 300, "popis stylu")


# fal endpoints we allow, schemas from raw OpenAPI and prices from GET api.fal.ai/v1/models/pricing
# (both fetched 2026-10-23, docs/capabilities/fal-image-backends.md). fal silently ignores unknown
# fields, so only keys present in the schema are sent.
FAL_CATALOG = {
    "fal-ai/nano-banana-pro": {"edit": "fal-ai/nano-banana-pro/edit", "unit": "image", "usd": 0.15,
                               "size": "aspect_ratio"},
    "fal-ai/flux-2-pro": {"edit": "fal-ai/flux-2-pro/edit", "unit": "processed_mp", "usd": 0.03, "size": "wh"},
    "fal-ai/flux-pro/v1.1": {"edit": None, "unit": "mp", "usd": 0.04, "size": "wh"},
    "fal-ai/flux/krea": {"edit": None, "unit": "mp", "usd": 0.025, "size": "wh"},
}
FAL_RATIOS = {"21:9": 21 / 9, "16:9": 16 / 9, "3:2": 1.5, "4:3": 4 / 3, "5:4": 1.25, "1:1": 1.0,
              "4:5": 0.8, "3:4": 0.75, "2:3": 2 / 3, "9:16": 9 / 16}
# Refs are downscaled to MAX_REF_EDGE (2048) before upload -> at most ~4.2 MP each.
REF_MP_UPPER = 2048 * 2048 / 1e6


class FalBackend:
    """backend="fal:<endpoint>". With image refs the endpoint's /edit variant is called."""

    def __init__(self, endpoint: str):
        if endpoint not in FAL_CATALOG:
            raise BackendError(f"fal endpoint {endpoint!r} není v katalogu: {sorted(FAL_CATALOG)}")
        self.endpoint = endpoint
        self.spec = FAL_CATALOG[endpoint]
        self.name = f"fal:{endpoint}"
        self.model = endpoint

    def _image_refs(self, req: ImageRequest) -> int:
        return sum(r.role != "style" for r in req.refs)

    def usd_for(self, req: ImageRequest) -> float:
        """Upper-bound estimate: megapixels rounded up, each ref counted at its max size."""
        spec = self.spec
        if spec["unit"] == "image":
            return spec["usd"] * req.n
        out_mp = math.ceil(req.width * req.height / 1e6)
        if spec["unit"] == "processed_mp":
            out_mp += math.ceil(REF_MP_UPPER) * self._image_refs(req)
        return round(spec["usd"] * out_mp * req.n, 4)

    def validate(self, req: ImageRequest) -> None:
        if req.supersample:
            raise BackendError("supersample umí jen flux-local")
        if self._image_refs(req) and not self.spec["edit"]:
            raise BackendError(f"{self.endpoint} neumí předlohy; použijte fal-ai/flux-2-pro nebo fal-ai/nano-banana-pro")

    def arguments(self, req: ImageRequest, prompt: str, image_urls: list[str], seed: int | None) -> dict:
        args = {"prompt": prompt, "output_format": "png"}
        if seed is not None:
            args["seed"] = seed
        if self.spec["size"] == "wh":
            args["image_size"] = {"width": req.width, "height": req.height}
        else:
            args["aspect_ratio"] = min(FAL_RATIOS, key=lambda r: abs(FAL_RATIOS[r] - req.width / req.height))
            args["resolution"] = "1K" if max(req.width, req.height) <= 1024 else "2K"
        if image_urls:
            args["image_urls"] = image_urls
        return args

    def run(self, req: ImageRequest, prompt: str, ref_pngs: list[bytes]) -> Generated:
        self.validate(req)
        import fal_client
        key = get_key("FAL_KEY", "FAL_API_KEY")
        if not key:
            raise BackendError("fal: chybí FAL_KEY / FAL_API_KEY")
        client = fal_client.SyncClient(key=key, default_timeout=300)
        endpoint = self.spec["edit"] if ref_pngs else self.endpoint
        try:
            urls = [client.upload(b, "image/png") for b in ref_pngs]
            images, seeds = [], []
            base_seed = req.seed if req.seed is not None else random.randint(0, 2**31 - 1)
            for i in range(req.n):
                args = self.arguments(req, prompt, urls, base_seed + i)
                result = client.subscribe(endpoint, arguments=args)
                url = (result.get("images") or [{}])[0].get("url")
                if not url:
                    raise BackendError(f"fal {endpoint}: odpověď bez obrázku: {str(result)[:300]}")
                images.append(httpx.get(url, timeout=120).raise_for_status().content)
                seeds.append(result.get("seed", base_seed + i))
        except httpx.HTTPError as e:
            raise BackendError(f"fal {endpoint}: stažení výsledku selhalo: {e}") from e
        except BackendError:
            raise
        except Exception as e:  # fal_client raises its own error types
            raise BackendError(f"fal {endpoint}: {type(e).__name__}: {e}") from e
        return Generated(images, seeds, endpoint, {k: v for k, v in args.items() if k not in ("prompt", "image_urls")})


# "Rozepsat zadání": short (often Czech) brief -> richer English FLUX prompt. Paid like any
# Claude call; the UI shows the estimate first. Same per-call estimate as describe_style.
EXPAND_USD = 0.01
# Structure and rules follow the PromptEnhancer analysis (cetej/GRAFIK#9), written in our own words.
EXPAND_INSTRUCTION = (
    "Rewrite this image brief as one English prompt for the FLUX image model. Build it in three steps. First one "
    "sentence with the whole picture: main subject, setting, camera viewpoint. Then the parts, in a fixed spatial "
    "order from background to foreground (or left to right), naming each position with explicit words such as "
    "'in the background', 'on the left', 'in front of': objects, materials, colours, lighting, level of detail. "
    "Then close with one sentence about the whole again; this last sentence names the overall style and type of "
    "image (for example 'a museum-style technical illustration' or 'a documentary photograph'). "
    "Rules: keep every fact from the brief and invent nothing historical that is not implied; keep the scene "
    "physically consistent (light direction, shadows, scale, perspective); describe only what can be seen, no "
    "judgements such as 'beautiful' or 'sad'; give exact counts of objects and people; if people or small figures "
    "appear, state their size and distance; turn vague wishes into concrete visible changes. Lettering in quotation "
    "marks must appear in the image: copy it unchanged, in its original language and spelling, inside double quotes. "
    "No other text in the image. Keep it to one paragraph of at most 180 words. Answer with the prompt only.\n\nBrief: "
)


def expand_prompt(text: str) -> str:
    return claude_text(EXPAND_INSTRUCTION + text, 900, "rozepsání zadání")


def make_backends(settings: Settings, server: SdServer) -> dict:
    backends = {"flux-local": FluxLocal(settings, server), "nb-pro": NanoBananaPro()}
    backends.update({f"fal:{e}": FalBackend(e) for e in FAL_CATALOG})
    return backends


def estimate_usd(req: ImageRequest, backend, translations: int = 0, crops: int = 0) -> dict:
    """Cost estimate shown before anything paid runs. `translations` = Czech fields not in the cache,
    `crops` = how many of them send the crop of the edited box along."""
    items = []
    if translations:
        items.append({"what": f"překlad zadání do angličtiny (Claude) × {translations}", "usd": 0.01 * translations,
                      "kind": "translation"})
    if crops:
        items.append({"what": f"výřez rámečku k překladu pokynu (Claude) × {crops}",
                      "usd": round(CROP_TRANSLATE_USD * crops, 4), "kind": "translation"})
    usd = backend.usd_for(req)
    if usd:
        items.append({"what": f"{backend.name} × {req.n}", "usd": round(usd, 4)})
    describe = sum(1 for r in req.refs if r.role == "style" and not r.text)
    if describe:
        items.append({"what": f"popis stylu slovy (Claude Haiku) × {describe}",
                      "usd": round(STYLE_DESCRIBE_USD * describe, 4)})
    return {"total_usd": round(sum(i["usd"] for i in items), 4), "items": items}
