"""Poradní kontroly obrázku (`ngm_shared.image_checks`): prompty z testů T4 a T7, sjednocený výstup.
Claude je zamockovaný (`ask=`), nic se neplatí."""

import json

import pytest
from PIL import Image

from ngm_shared import claude
from ngm_shared import image_checks as ic


class Fake:
    def __init__(self, payload):
        self.payload, self.calls = payload, []

    def __call__(self, content, system, **kw):
        self.calls.append({"content": content, "system": system, **kw})
        return claude.Answer("Výsledek:\n" + json.dumps(self.payload, ensure_ascii=False), "claude-opus-5-5",
                             1056, 199, 0.0082, "end_turn")


def test_brief_check_sends_brief_and_checklist_and_sorts_by_severity():
    fake = Fake({"verdikt": "vrátit", "vady": [
        {"co": "talíř je bílý", "oprava": "modrý talíř do zadání", "zavaznost": "střední"},
        {"co": "jen jedna hruška", "oprava": "přidat druhou hrušku", "zavaznost": "vysoká"},
        {"co": "", "zavaznost": "nízká"}]})
    r = ic.check_brief(Image.new("RGB", (2048, 1024)), "Dvě zelené hrušky na modrém talíři.", ask=fake)
    call = fake.calls[0]
    assert call["model"] == "claude-opus-5-5" and call["effort"] == "low"
    assert call["content"][0]["type"] == "image"
    text = call["content"][1]["text"]
    assert text.startswith("ZADÁNÍ: Dvě zelené hrušky") and "anatomie" in text and "počet předmětů" in text
    assert r["advisory"] and r["verdict"] == "vrátit" and r["cost"]["usd"] == 0.0082
    assert [w["severity"] for w in r["warnings"]] == ["vysoká", "střední"]
    assert r["warnings"][0] == {"severity": "vysoká", "what": "jen jedna hruška", "why": "",
                                "fix": "přidat druhou hrušku"}


def test_brief_check_without_findings_is_ok_and_takes_own_checklist():
    fake = Fake({"verdikt": "ok", "vady": []})
    r = ic.check_brief(Image.new("RGB", (64, 64)), "Liška v lese.", checklist=["barva srsti"], ask=fake)
    assert r["verdict"] == "ok" and r["warnings"] == []
    assert "- barva srsti" in fake.calls[0]["content"][1]["text"] and "anatomie" not in fake.calls[0]["content"][1]["text"]


def test_logic_check_asks_where_the_action_leads_and_keeps_why():
    fake = Fake({"souhrn": "Jeřáb nedává smysl.", "ucel": "Kvádr se zvedá na zeď, která v obraze chybí.",
                 "problemy": [{"co": "lano vede z kola rovnou ke kvádru", "proc": "chybí kladka",
                               "oprava": "lano přes kladku na vrcholu stožáru", "zavaznost": "high"}]})
    r = ic.check_logic(Image.new("RGB", (64, 64)), "Dělníci zvedají jeřábem kvádr.", phase="plan",
                       layout="Šlapací kolo vlevo, stožár vedle.", ask=fake)
    assert "kam to směřuje" in fake.calls[0]["system"]
    text = fake.calls[0]["content"][1]["text"]
    assert text.startswith("FÁZE: plán před generováním.") and "Šlapací kolo" in text and "3D skica" in text
    assert r["kind"] == "logic" and r["phase"] == "plan" and r["purpose"].startswith("Kvádr")
    assert r["warnings"] == [{"severity": "vysoká", "what": "lano vede z kola rovnou ke kvádru",
                              "why": "chybí kladka", "fix": "lano přes kladku na vrcholu stožáru"}]


def test_logic_check_rejects_unknown_phase_and_bad_answer():
    with pytest.raises(ValueError):
        ic.check_logic(Image.new("RGB", (8, 8)), "x", phase="video", ask=Fake({}))

    def prose(content, system, **kw):
        return claude.Answer("Nevím.", "claude-opus-5-5", 10, 10, 0.0003, "end_turn")

    with pytest.raises(claude.ClaudeError, match="není JSON"):
        ic.check_logic(Image.new("RGB", (8, 8)), "x", ask=prose)
