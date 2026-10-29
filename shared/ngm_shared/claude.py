"""Jedno volání Claude pro sdílené funkce (čtení textu z obrázku, kontroly) → text a cena z `usage`.

Placené. Cenu počítá z tokenů, které API opravdu naúčtovalo (`usage`), a volající ji zapíše do svého
ledgeru (GRAFIK Engine do `library/costs.jsonl`). Pod pytestem se bez `GRAFIK_LIVE_TESTS=1` nezavolá
nic: testy předávají vlastní `ask` a zapomenutý mock skončí chybou, ne platbou (HEGEMON 2026-10-29:
holé `pytest` třikrát pustilo 17 agentů proti živému API).

Klíč z `ANTHROPIC_API_KEY`, jinak ze sdílených `.env` přes STOPA `scripts/load_keys.py`
(`load_project_keys()`), nikdy z configu. Závislost: `anthropic` (`pip install -e GRAFIK/shared[text]`).
"""
from __future__ import annotations

import base64
import importlib.util
import io
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

MODEL = "claude-opus-5-5"
# USD za milion tokenů (vstup, výstup); claude-api skill 2026-10-06. Odpověď ze záložního modelu
# (fallbacks) se počítá cenou modelu, který ji opravdu dal, neznámý model nejdražší položkou.
PRICES = {"claude-opus-5-5": (4.0, 20.0), "claude-sonnet-5-5": (2.0, 10.0), "claude-haiku-5-5": (0.10, 0.50),
          "claude-opus-5": (5.0, 25.0), "claude-opus-4-8": (5.0, 25.0), "claude-fable-5-1": (10.0, 50.0)}
LIVE_ENV = "GRAFIK_LIVE_TESTS"
KEY_LOADER = Path("C:/Users/stock/Documents/000_NGM/STOPA/scripts/load_keys.py")
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class ClaudeError(RuntimeError):
    """Volání se nepovedlo, odmítlo, nebo by v testu stálo peníze. `cost` = co se i tak naúčtovalo (do ledgeru)."""

    def __init__(self, message: str, cost: dict | None = None):
        super().__init__(message)
        self.cost = cost


@dataclass
class Answer:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    usd: float
    stop: str

    def cost(self) -> dict:
        return {"model": self.model, "in": self.input_tokens, "out": self.output_tokens, "usd": self.usd}


def usd_for(model: str, input_tokens: int, output_tokens: int) -> float:
    p_in, p_out = PRICES.get(model, max(PRICES.values()))
    return round((input_tokens * p_in + output_tokens * p_out) / 1e6, 4)


def _guard(what: str) -> None:
    if "pytest" in sys.modules and os.environ.get(LIVE_ENV) != "1":
        raise ClaudeError(f"{what}: placené volání Claude v testu; mockujte `ask`, živě jen s {LIVE_ENV}=1")


def _client():
    if not os.environ.get("ANTHROPIC_API_KEY") and KEY_LOADER.is_file():
        spec = importlib.util.spec_from_file_location("stopa_load_keys", KEY_LOADER)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.load_project_keys()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise ClaudeError("chybí ANTHROPIC_API_KEY (env ani .env v NG-ROBOT / ADOBE-AUTOMAT)")
    import anthropic
    return anthropic.Anthropic()


def ask(content: list, system: str, *, what: str, model: str = MODEL, effort: str = "low",
        max_tokens: int = 16000) -> Answer:
    """Jedno volání (stream kvůli dlouhému přemýšlení při vyšším effort). Odmítnutí po záložním modelu = chyba."""
    _guard(what)
    import anthropic
    try:
        with _client().beta.messages.stream(
                model=model, max_tokens=max_tokens, system=system, output_config={"effort": effort},
                messages=[{"role": "user", "content": content}],
                betas=[FALLBACK_BETA], fallbacks="default") as stream:
            msg = stream.get_final_message()
    except anthropic.APIError as e:
        raise ClaudeError(f"{what}: {e}") from e
    text = "".join(b.text for b in msg.content if b.type == "text").strip()
    u = msg.usage
    answer = Answer(text, msg.model, u.input_tokens, u.output_tokens, usd_for(msg.model, u.input_tokens,
                                                                              u.output_tokens), msg.stop_reason)
    if msg.stop_reason == "refusal":
        raise ClaudeError(f"{what}: Claude odmítl ({getattr(msg.stop_details, 'category', None)})", answer.cost())
    if msg.stop_reason == "max_tokens" or not text:
        raise ClaudeError(f"{what}: odpověď nedokončena (stop={msg.stop_reason})", answer.cost())
    return answer


def image_block(image, max_side: int = 1568) -> tuple[dict, tuple[int, int], float]:
    """Obrázek (cesta, bajty nebo PIL) → (blok pro Claude, rozměr poslané kopie, měřítko poslané / původní)."""
    from PIL import Image
    im = image if isinstance(image, Image.Image) else Image.open(
        io.BytesIO(image) if isinstance(image, (bytes, bytearray)) else image)
    im = im.convert("RGB")
    scale = min(1.0, max_side / max(im.size))
    if scale < 1:
        im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return ({"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                         "data": base64.standard_b64encode(buf.getvalue()).decode()}},
            im.size, scale)


def parse_json(text: str, what: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    try:
        data = json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        data = None
    if not isinstance(data, dict):
        raise ClaudeError(f"{what}: odpověď není JSON objekt ({text[:160]!r})")
    return data
