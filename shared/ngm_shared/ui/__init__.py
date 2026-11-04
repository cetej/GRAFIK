"""Společné názvy UI tokenů a komponenty „tlačítko vs. informace“ pro webové aplikace projektů (GRAFIK#81).

Sdílí se význam, ne vzhled: aplikace si nechá své barvy a písma a jen je pojmenuje podle `tokens.md`.
`base.css` čte jen tyto tokeny. Server aplikace ho servíruje z `css_path()`, bez kopie.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent


def css_path() -> Path:
    """Cesta k `base.css` (FastAPI: `FileResponse(css_path())`, Flask: `send_file(css_path())`)."""
    return HERE / "base.css"


def tokens_path() -> Path:
    return HERE / "tokens.md"
