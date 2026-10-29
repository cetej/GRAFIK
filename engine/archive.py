"""GET /api/v2/archive — hledání ve všech výstupech fronty (ngm_shared.archive nad run/jobs.sqlite).

Zdarma a jen pro čtení: text zadání, promptu a počeštění, filtry volající / druh úlohy / datum / stav. Adresy
obrázků a náhledů jsou relativní (Studio jde přes proxy :5174 → :8300). Náhledy vznikají se stejným jménem jako
u `/api/v2/jobs/<id>/images/<n>?w=`, takže je sdílí. Studio UI zatím hledání nenabízí (čeká na algoritmus).
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException

from ngm_shared import archive


def register(app: FastAPI, settings) -> None:
    @app.get("/api/v2/archive")
    def archive_search(q: str = "", caller: str | None = None, kind: str | None = None, since: str | None = None,
                       until: str | None = None, status: str = "done", limit: int = 50, thumbs: bool = True):
        try:
            results = archive.search(q, caller=caller, kind=kind, since=since, until=until,
                                     status=None if status == "all" else status, limit=max(1, min(limit, 200)),
                                     db=settings.db_path, engine="", thumbs=thumbs)
        except archive.ArchiveError as e:
            raise HTTPException(400, str(e)) from e
        return {"count": len(results), "results": results,
                "query": {"q": q, "caller": caller, "kind": kind, "since": since, "until": until, "status": status}}

    @app.get("/api/v2/archive/facets")
    def archive_facets():
        try:
            return archive.facets(settings.db_path)
        except archive.ArchiveError as e:
            raise HTTPException(404, str(e)) from e
