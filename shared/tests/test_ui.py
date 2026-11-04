"""ngm_shared.ui (GRAFIK#81): base.css čte jen tokeny z tokens.md, nic natvrdo."""
import re

from ngm_shared import ui


def test_base_css_has_no_hardcoded_colour_or_font():
    css = ui.css_path().read_text(encoding="utf-8")
    assert not re.findall(r"#[0-9a-fA-F]{3,8}\b", css)
    assert not re.findall(r"\b(rgb|rgba|hsl|hsla)\(", css)
    assert not re.findall(r"font-family\s*:", css)


def test_base_css_uses_only_documented_tokens():
    documented = set(re.findall(r"`(--[a-z-]+)`", ui.tokens_path().read_text(encoding="utf-8")))
    used = set(re.findall(r"var\((--[a-z-]+)\)", ui.css_path().read_text(encoding="utf-8")))
    assert used and used <= documented, used - documented


def test_floor_rules_are_there():
    css = ui.css_path().read_text(encoding="utf-8")
    assert ":focus-visible" in css and "@media (hover: hover) and (pointer: fine)" in css
    disabled = css.split(".ui-btn:disabled", 1)[1].split("}", 1)[0]
    assert all(p in disabled for p in ("background", "color", "cursor: not-allowed"))
