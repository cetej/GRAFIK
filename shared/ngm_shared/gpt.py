"""Jedno volání OpenAI se stejným rozhraním jako `claude.ask`: volající jen vymění funkci a dostane `claude.Answer`.

Placené. Cenu počítá z tokenů, které API opravdu naúčtovalo (`usage`), do ledgeru ji zapisuje volající. Pod pytestem
platí stejná pojistka jako u Claude (`claude.LIVE_ENV`). Klíč z `OPENAI_API_KEY`, jinak ze sdílených `.env` přes STOPA
`scripts/load_keys.py`, nikdy z configu. Závislost: `openai` (`pip install -e GRAFIK/shared[gpt]`).
"""
from __future__ import annotations

import importlib.util
import os

from ngm_shared import claude

# USD za milion tokenů (vstup, výstup); developers.openai.com/api/docs/pricing 2026-11-01. Neznámý model nejdražší položkou.
PRICES = {"gpt-6.1-sol": (2.0, 10.0), "gpt-6.1-terra": (1.0, 5.0), "gpt-6-luna": (0.10, 0.50)}


def usd_for(model: str, input_tokens: int, output_tokens: int) -> float:
    p_in, p_out = PRICES.get(model, max(PRICES.values()))
    return round((input_tokens * p_in + output_tokens * p_out) / 1e6, 4)


def _client():
    if not os.environ.get("OPENAI_API_KEY") and claude.KEY_LOADER.is_file():
        spec = importlib.util.spec_from_file_location("stopa_load_keys", claude.KEY_LOADER)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.load_project_keys()
    if not os.environ.get("OPENAI_API_KEY"):
        raise claude.ClaudeError("chybí OPENAI_API_KEY (env ani .env v NG-ROBOT)")
    import openai
    return openai.OpenAI()


def _parts(content: list) -> list[dict]:
    """Bloky ve tvaru pro Claude (`claude.image_block`, text) → části vstupu Responses API."""
    parts = []
    for block in content:
        if block["type"] == "text":
            parts.append({"type": "input_text", "text": block["text"]})
        else:
            source = block["source"]
            parts.append({"type": "input_image", "image_url": f"data:{source['media_type']};base64,{source['data']}"})
    return parts


def ask(content: list, system: str, *, what: str, model: str, effort: str = "low", max_tokens: int = 16000) -> claude.Answer:
    """Jedno volání. Nedokončená nebo prázdná odpověď (odmítnutí, limit tokenů) je chyba s cenou, která se naúčtovala."""
    claude._guard(what)
    import openai
    try:
        reply = _client().responses.create(model=model, instructions=system, input=[{"role": "user", "content": _parts(content)}],
                                           reasoning={"effort": effort}, max_output_tokens=max_tokens)
    except openai.OpenAIError as e:
        raise claude.ClaudeError(f"{what}: {e}") from e
    u = reply.usage
    text = (reply.output_text or "").strip()
    answer = claude.Answer(text, reply.model, u.input_tokens, u.output_tokens, usd_for(model, u.input_tokens, u.output_tokens), reply.status)
    if reply.status != "completed" or not text:
        raise claude.ClaudeError(f"{what}: odpověď nedokončena (status={reply.status})", answer.cost())
    return answer
