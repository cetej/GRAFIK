"""Poradní kontrola obrázku: proti zadání (test T4) a kontrola logiky scény (test T7).

Výstup je vždy jen poradní (operátor 2026-10-29: „jen jako doplněk, ne nepřekročitelná bariéra“): seznam
upozornění se závažností a návrhem opravy. Editor je přijme, nebo přeskočí; nic se neblokuje.

- `check_brief`: obrázek + zadání + kontrolní seznam (reálie, počet předmětů, text, anatomie).
  T4: 7/7 nastražených neshod, 0 falešných poplachů na 3 správných obrázcích, ~0,009 USD za obrázek.
- `check_logic`: plán se skicou (před generováním, oprava je nejlevnější) nebo hotový obrázek. Otázky: proč
  se děj odehrává a kam směřuje, fyzika, technika a reálie, měřítko. T7: 7 a 8 skutečných problémů,
  0,05 USD za kontrolu; účel děje T7 odhalil až u obrázku, proto se ptá výslovně „kam to směřuje“.

Model podle ceny a měření: Claude Opus 5.5, effort low (T4 i T7 tak běžely). Cena z `usage` je v `cost`.
"""
from __future__ import annotations

from typing import Callable

from ngm_shared import claude

MODEL = "claude-opus-5-5"
EFFORT = "low"
BRIEF_USD = 0.02            # odhad předem; T4 0,005–0,015 USD za obrázek
LOGIC_USD = 0.07            # T7 0,052 a 0,056 USD
SEVERITY = {"vysoká": "vysoká", "střední": "střední", "nízká": "nízká", "high": "vysoká", "medium": "střední",
            "low": "nízká"}
CHECKLIST = ["reálie a dobové věci vůči uvedené době", "počet předmětů, lidí a zvířat",
             "text v obraze (nápisy, popisky)", "anatomie (ruce, tváře, těla zvířat)"]

BRIEF_SYSTEM = (
    "Jsi kontrola obrázku před tím, než ho uvidí editor. Porovnej obrázek se zadáním. Vypiš jen skutečné nesoulady "
    "se zadáním (chybějící nebo přebývající prvky, počty, barvy, denní doba, styl, text, anachronismy vůči uvedené "
    "době) a zjevné vady (deformované tělo, ruce, předměty). Projdi i kontrolní seznam. Neuváděj nic, co zadání "
    "neurčuje. Odpověz jen JSON: "
    '{"verdikt": "ok" nebo "vrátit", "vady": [{"co": "...", "oprava": "co změnit v zadání nebo opravou v rámečku", '
    '"zavaznost": "vysoká|střední|nízká"}]}')
LOGIC_SYSTEM = (
    "Jsi poradní kontrola logiky scény pro redakci National Geographic. Neblokuješ, jen upozorňuješ. Posuď, zda "
    "scéna dává smysl: účel děje (proč se to děje a kam to směřuje: co bude dál, kam se věc nebo náklad přesouvá; "
    "chybí-li v obraze cíl děje, je to problém), fyzika (statika, lana a kladky, opory, gravitace, rovnováha), "
    "technika a dobové reálie, měřítko a vzájemné vztahy předmětů a lidí. U každého problému napiš, co je "
    "nelogické, proč, jak to opravit ve skice nebo v zadání, a závažnost. Jen skutečné problémy, žádné vkusové "
    "poznámky. Odpověz jen JSON: "
    '{"souhrn": "jedna věta", "ucel": "proč se děj odehrává a kam směřuje, jedna věta", '
    '"problemy": [{"co": "...", "proc": "...", "oprava": "...", "zavaznost": "vysoká|střední|nízká"}]}')

Ask = Callable[..., claude.Answer]


def _warnings(items, what_key: str = "co") -> list[dict]:
    out = []
    for it in items if isinstance(items, list) else []:
        if isinstance(it, dict) and str(it.get(what_key) or "").strip():
            out.append({"severity": SEVERITY.get(str(it.get("zavaznost", "")).strip().lower(), "střední"),
                        "what": str(it[what_key]).strip(), "why": str(it.get("proc") or "").strip(),
                        "fix": str(it.get("oprava") or "").strip()})
    order = {"vysoká": 0, "střední": 1, "nízká": 2}
    return sorted(out, key=lambda w: order[w["severity"]])


def check_brief(image, brief: str, *, checklist: list[str] | None = None, ask: Ask = claude.ask,
                model: str = MODEL, effort: str = EFFORT) -> dict:
    """Obrázek proti zadání. `image` = cesta, bajty nebo PIL obrázek."""
    blk, _, _ = claude.image_block(image, max_side=1024)
    items = "\n".join(f"- {c}" for c in (checklist or CHECKLIST))
    ans = ask([blk, {"type": "text", "text": f"ZADÁNÍ: {brief}\nKONTROLNÍ SEZNAM:\n{items}"}], BRIEF_SYSTEM,
              what="kontrola proti zadání", model=model, effort=effort, max_tokens=4000)
    data = claude.parse_json(ans.text, "kontrola proti zadání")
    warnings = _warnings(data.get("vady"))
    return {"kind": "brief", "advisory": True, "verdict": "vrátit" if warnings else "ok",
            "summary": "Bez neshody se zadáním." if not warnings else f"{len(warnings)} neshod se zadáním.",
            "warnings": warnings, "cost": ans.cost()}


def check_logic(image, brief: str, *, phase: str = "image", layout: str = "", ask: Ask = claude.ask,
                model: str = MODEL, effort: str = EFFORT) -> dict:
    """Logika scény. `phase` = "plan" (3D skica před generováním, `layout` = slovní popis rozmístění) nebo
    "image" (hotový obrázek)."""
    if phase not in ("plan", "image"):
        raise ValueError("phase je plan nebo image")
    blk, _, _ = claude.image_block(image, max_side=1280)
    if phase == "plan":
        text = f"FÁZE: plán před generováním.\nZADÁNÍ ZÁBĚRU: {brief}\n{layout}\nPřiložená je 3D skica.".replace("\n\n", "\n")
    else:
        text = f"FÁZE: hotový obrázek.\nZADÁNÍ ZÁBĚRU: {brief}"
    ans = ask([blk, {"type": "text", "text": text}], LOGIC_SYSTEM, what="kontrola logiky", model=model,
              effort=effort, max_tokens=6000)
    data = claude.parse_json(ans.text, "kontrola logiky")
    warnings = _warnings(data.get("problemy"))
    return {"kind": "logic", "phase": phase, "advisory": True, "summary": str(data.get("souhrn") or "").strip(),
            "purpose": str(data.get("ucel") or "").strip(), "warnings": warnings, "cost": ans.cost()}
