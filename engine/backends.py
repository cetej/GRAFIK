"""Image backends. flux-local is the default and costs 0 USD; every other
backend is paid and runs only when the caller names it explicitly and confirms
the estimate (operator decision 2026-10-22). No backend ever falls back to
another one."""
from __future__ import annotations

import base64
import math
import random
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
            p["ref_images"] = [base64.b64encode(b).decode() for b in ref_pngs]
        if w * h > self.s.vae_tiling_above_pixels:
            p["vae_tiling_params"] = {"enabled": True}
        return p

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
STYLE_INSTRUCTION = (
    "Describe only the visual STYLE of this image so an image generator can reproduce it on a different "
    "subject: medium, technique, colour palette, lighting, line quality, texture, rendering, composition "
    "habits. Do not describe the subject or content. One English paragraph, at most 80 words."
)


def claude_text(content, max_tokens: int, what: str) -> str:
    """One Claude Messages call -> text. Paid: callers gate it behind a shown estimate."""
    key = get_key("ANTHROPIC_API_KEY")
    if not key:
        raise BackendError(f"{what}: chybí ANTHROPIC_API_KEY")
    try:
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
            json={"model": CLAUDE_MODEL, "max_tokens": max_tokens, "messages": [{"role": "user", "content": content}]},
            timeout=120,
        )
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise BackendError(f"{what} selhalo: {e}") from e
    return "".join(b.get("text", "") for b in r.json().get("content", [])).strip()


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
EXPAND_INSTRUCTION = (
    "Rewrite this image brief as one English prompt for the FLUX image model. Describe the scene concretely: "
    "subject, setting, composition and camera viewpoint, medium and rendering, lighting, colour palette, level of "
    "detail. Keep every fact from the brief, invent nothing historical that is not implied. If people or small "
    "figures appear, state their size and distance. No text in the image. Answer with the prompt only.\n\nBrief: "
)


def expand_prompt(text: str) -> str:
    return claude_text(EXPAND_INSTRUCTION + text, 500, "rozepsání zadání")


def make_backends(settings: Settings, server: SdServer) -> dict:
    backends = {"flux-local": FluxLocal(settings, server), "nb-pro": NanoBananaPro()}
    backends.update({f"fal:{e}": FalBackend(e) for e in FAL_CATALOG})
    return backends


def estimate_usd(req: ImageRequest, backend, translations: int = 0) -> dict:
    """Cost estimate shown before anything paid runs. `translations` = Czech fields not in the cache."""
    items = []
    if translations:
        items.append({"what": f"překlad zadání do angličtiny (Claude) × {translations}", "usd": 0.01 * translations,
                      "kind": "translation"})
    usd = backend.usd_for(req)
    if usd:
        items.append({"what": f"{backend.name} × {req.n}", "usd": round(usd, 4)})
    describe = sum(1 for r in req.refs if r.role == "style" and not r.text)
    if describe:
        items.append({"what": f"popis stylu slovy (Claude Haiku) × {describe}",
                      "usd": round(STYLE_DESCRIBE_USD * describe, 4)})
    return {"total_usd": round(sum(i["usd"] for i in items), 4), "items": items}
