"""Archiv výstupů fronty GRAFIK Engine s hledáním (krok 8 algoritmu operátora, plán STOPA 2026-10-29 § 3/8).

Čte `GRAFIK/run/jobs.sqlite` jen pro čtení (zapisuje do ní dál jen Engine), takže hledat může kterýkoli
projekt i bez běžícího Engine. Hledá zdarma v textu, který už existuje: zadání, jak ho poslal volající,
prompt poslaný generátoru, pokyn k úpravě, styl, název 3D modelu a český i původní text počeštění. Slova
se hledají bez ohledu na velikost písmen a diakritiku („krkonose“ najde „Krkonoše“), všechna musí být.
Filtry: volající (obsahuje), druh úlohy, datum od–do, stav. Výsledek nese cestu k obrázku a k náhledu
a adresy v Engine. Jen stdlib; náhled (`thumbnail`) potřebuje Pillow.
"""
from __future__ import annotations

import json
import os
import sqlite3
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

DEFAULT_DB = Path(os.environ.get("GRAFIK_JOBS_DB") or "C:/Users/stock/Documents/000_NGM/GRAFIK/run/jobs.sqlite")
ENGINE = "http://127.0.0.1:8300"
THUMB_W = 256
# (sloupec, cesta JSON, klíč ve výsledku); text pro hledání jsou všechny
FIELDS = [("request", "$.prompt", "prompt"), ("request", "$.edit.instruction", "edit"), ("request", "$.style", "style"),
          ("request", "$.style_id", "style_id"), ("request", "$.title", "title"), ("request", "$.model_id", "model_id"),
          ("request", "$.source", "source"), ("result", "$.prompt_sent", "prompt_sent"), ("result", "$.text", "text"),
          ("result", "$.text_src", "text_src")]


class ArchiveError(ValueError):
    """Neplatný dotaz (datum) nebo chybějící databáze."""


def norm(text: str) -> str:
    """Malá písmena bez diakritiky: „Krkonoše“ → „krkonose“."""
    return "".join(c for c in unicodedata.normalize("NFKD", str(text)) if not unicodedata.combining(c)).casefold()


def _day(value: str, end: bool = False) -> float:
    try:
        d = datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise ArchiveError(f"datum {value!r} není ve tvaru RRRR-MM-DD") from None
    return (d + timedelta(days=1) if end else d).timestamp()


def _connect(db: Path) -> sqlite3.Connection:
    db = Path(db)
    if not db.is_file():
        raise ArchiveError(f"archiv {db} neexistuje")
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _json(col: str, path: str) -> str:
    return f"CASE WHEN json_valid({col}) THEN json_extract({col}, '{path}') END"


def thumb_path(image: Path, w: int = THUMB_W) -> Path:
    """Stejné jméno, jaké dává náhledu Engine (`/api/v2/jobs/<id>/images/<n>?w=`): sdílí jednu mezipaměť."""
    return image.with_name(f"thumb-{image.stem}-{w}.jpg")


def thumbnail(image: Path, w: int = THUMB_W) -> Path:
    """Náhled JPEG vedle obrázku; vytvoří ho, když chybí."""
    out = thumb_path(Path(image), w)
    if not out.exists():
        from PIL import Image
        with Image.open(image) as im:
            im = im.convert("RGB")
            im.thumbnail((w, w * 4))
            im.save(out, quality=85)
    return out


def search(q: str = "", *, caller: str | None = None, kind: str | None = None, since: str | None = None,
           until: str | None = None, status: str | None = "done", limit: int = 50, db: Path = DEFAULT_DB,
           engine: str = ENGINE, thumbs: bool = False) -> list[dict]:
    """Úlohy od nejnovější. `since`/`until` = RRRR-MM-DD (místní čas, `until` včetně), `status=None` = všechny,
    `thumbs=True` náhledy rovnou vytvoří (jinak `thumb_path` jen tam, kde už je)."""
    where, args = [], []
    if kind:
        where.append("COALESCE(kind, 'image') = ?")
        args.append(kind)
    if caller:
        where.append("instr(lower(caller), ?) > 0")
        args.append(caller.lower())
    if status:
        where.append("status = ?")
        args.append(status)
    if since:
        where.append("created >= ?")
        args.append(_day(since))
    if until:
        where.append("created < ?")
        args.append(_day(until, end=True))
    cols = ", ".join(f"{_json(c, p)} AS {k}" for c, p, k in FIELDS)
    sql = (f"SELECT id, COALESCE(kind, 'image') AS kind, caller, status, backend, created, {cols}, "
           f"{_json('result', '$.files')} AS files, {_json('result', '$.dir')} AS dir FROM jobs "
           f"{'WHERE ' + ' AND '.join(where) if where else ''} ORDER BY created DESC")
    words = norm(q).split()
    out = []
    with _connect(db) as con:
        for row in con.execute(sql, args):
            if words:
                hay = norm(" ".join(str(row[k]) for k in ("caller", *[f[2] for f in FIELDS]) if row[k]))
                if not all(w in hay for w in words):
                    continue
            out.append(_record(row, engine, thumbs))
            if len(out) >= limit:
                break
    return out


def _record(row: sqlite3.Row, engine: str, thumbs: bool) -> dict:
    images = []
    for n, f in enumerate(json.loads(row["files"]) if row["files"] else []):
        path = Path(f)
        # obrázky a počeštění mají úplnou cestu a adresu v Engine; pohledy 3D modelu jen jméno ve složce `dir`
        url = f"{engine}/api/v2/jobs/{row['id']}/images/{n}" if path.is_absolute() else None
        if not path.is_absolute() and row["dir"]:
            path = Path(row["dir"]) / path
        thumb = thumbnail(path) if thumbs and path.exists() else thumb_path(path)
        images.append({"n": n, "path": str(path), "exists": path.exists(), "url": url,
                       "thumb_path": str(thumb) if thumb.exists() else None,
                       "thumb_url": f"{url}?w={THUMB_W}" if url else None})
    return {"job_id": row["id"], "kind": row["kind"], "caller": row["caller"], "status": row["status"],
            "backend": row["backend"], "created": datetime.fromtimestamp(row["created"]).isoformat(timespec="seconds"),
            **{k: row[k] for _, _, k in FIELDS if row[k]}, "dir": row["dir"], "images": images}


def facets(db: Path = DEFAULT_DB) -> dict:
    """Co jde filtrovat: volající a druhy úloh s počty, první a poslední den."""
    with _connect(db) as con:
        callers = dict(con.execute("SELECT caller, COUNT(*) FROM jobs GROUP BY caller ORDER BY 2 DESC").fetchall())
        kinds = dict(con.execute("SELECT COALESCE(kind, 'image'), COUNT(*) FROM jobs GROUP BY 1 ORDER BY 2 DESC")
                     .fetchall())
        first, last, total = con.execute("SELECT MIN(created), MAX(created), COUNT(*) FROM jobs").fetchone()
    day = lambda t: datetime.fromtimestamp(t).strftime("%Y-%m-%d") if t else None      # noqa: E731
    return {"total": total, "callers": callers, "kinds": kinds, "first": day(first), "last": day(last)}
