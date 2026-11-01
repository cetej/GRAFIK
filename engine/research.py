"""/api/v2/research… — dossier faktů a obrazových podkladů k tématu jako úloha `research` ve společné frontě.

Knihovna: `ngm_shared.research`. Volné zdroje (Wikidata, Wikipedia, Commons) jsou zdarma. Placené hledání na webu
doplňuje hotový dossier (`extends`), 402 bez `confirm_cost`, cena po každé odpovědi do `library/costs.jsonl`.

library/research/<slug>-v<n>/request.json   zadání a úloha
library/research/<slug>-v<n>/dossier.json   výsledek; nepřepisuje se, nový běh je nová verze
library/research/<slug>-v<n>/pages/*.txt    stažené texty stránek pro kontrolu faktů proti zdroji
library/research/<slug>-v<n>/podklady.html  přehled obrázků (ngm_shared.variants_page) s kopiemi obrázků vedle sebe
library/research/<slug>-v<n>/inspirace.json piny z Pinterestu; přibývají k hotovému dossieru, ten se nemění

Obrázky jdou do knihovny předloh s autorem a licencí, z Commons přes `engine.commons`, náhledy modelů ze Sketchfabu přímo. V Schránce se
nehlásí jako nové: operátor je vidí v dossieru. Neúspěšné stažení jednoho obrázku běh nezastaví, u obrázku zůstane `chyba`.
Piny z Pinterestu mají neznámou licenci: slouží jako předloha a inspirace, do hotového obrázku nikdy (DECISIONS, Pinterest).
"""
from __future__ import annotations

import json
import re
import threading
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from PIL import Image
from pydantic import BaseModel, Field

from engine import commons
from engine.reflib import PINTEREST_LICENSE, RefLibError
from ngm_shared import claude, research as rs, variants_page

KIND = "research"
PAGE = "podklady.html"
COPY_EDGE = 1600


class PinIn(BaseModel):
    pin: str
    obrazek: str
    nazev: str = ""
    dotaz: str = ""


class InspiraceIn(BaseModel):
    piny: list[PinIn] = Field(min_length=1, max_length=60)


class ResearchIn(BaseModel):
    topic: str = ""
    qid: str | None = None              # položka Wikidaty, když hledání najde něco jiného
    images: bool = True
    per_role: int = Field(default=4, ge=1, le=12)
    extends: str | None = None          # doplnit tento dossier placeným hledáním na webu (nová verze)
    question: str | None = None         # co přesně dohledat; jinak otázky bez odpovědi a rozpory z dossieru
    confirm_cost: bool = False
    caller: str = "studio"


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", rs._plain(text)).strip("-")[:60] or "tema"


class ResearchStore:
    def __init__(self, root: Path):
        self.root = root
        self._lock = threading.Lock()

    def _dir(self, research_id: str) -> Path:
        if not re.fullmatch(r"[a-z0-9\-]+", research_id or ""):
            raise HTTPException(400, "neplatné id rešerše")
        return self.root / research_id

    def new(self, topic: str, request: dict) -> str:
        slug = slugify(topic)
        with self._lock:
            self.root.mkdir(parents=True, exist_ok=True)
            versions = [int(m.group(1)) for p in self.root.glob(f"{slug}-v*") if (m := re.fullmatch(rf"{re.escape(slug)}-v(\d+)", p.name))]
            version = max(versions, default=0) + 1
            research_id = f"{slug}-v{version}"
            (self.root / research_id).mkdir()
        self.write_request(research_id, {**request, "id": research_id, "tema": topic, "verze": version,
                                         "created": datetime.now().isoformat(timespec="seconds")})
        return research_id

    def write_request(self, research_id: str, data: dict) -> None:
        (self._dir(research_id) / "request.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def request(self, research_id: str) -> dict | None:
        p = self._dir(research_id) / "request.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def dossier(self, research_id: str) -> dict | None:
        p = self._dir(research_id) / "dossier.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def finish(self, research_id: str, dossier: dict) -> None:
        d = self._dir(research_id)
        tmp = d / "dossier.json.tmp"
        tmp.write_text(json.dumps(dossier, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(d / "dossier.json")

    def inspiration(self, research_id: str) -> list[dict]:
        p = self._dir(research_id) / "inspirace.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []

    def save_inspiration(self, research_id: str, rows: list[dict]) -> None:
        d = self._dir(research_id)
        tmp = d / "inspirace.json.tmp"
        tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(d / "inspirace.json")

    def ids(self) -> list[str]:
        if not self.root.exists():
            return []
        return [p.parent.name for p in self.root.glob("*/request.json")]


class Researcher:
    def __init__(self, settings, store, reflib, log_cost, get=rs.get_json, web_turn=None, fetch_image=None, fetch_url=None):
        self.s, self.store, self.reflib, self.log_cost = settings, store, reflib, log_cost
        self.lib = ResearchStore(settings.library_dir / "research")
        self.get = get
        self.web_turn = web_turn or claude.web_turn
        self.fetch_image = fetch_image or (lambda file: commons.import_file(reflib, file))
        self.fetch_url = fetch_url or reflib.add_url

    def handlers(self) -> dict:
        return {KIND: self.run}

    def run(self, job_id: str, req: dict) -> dict:
        research_id = req["id"]
        if req.get("extends"):
            dossier = self._extend(job_id, req)
        else:
            dossier = rs.free_dossier(req["topic"], qid=req.get("qid"), per_role=req.get("per_role", 4), images=req.get("images", True), get=self.get)
            self._save_pages(research_id, dossier.pop("pages"))
            self._import_images(dossier)
        d = self.lib._dir(research_id)
        dossier.update(id=research_id, verze=req.get("verze"), vytvoreno=datetime.now().isoformat(timespec="seconds"))
        if dossier["images"]:
            self._build_page(d, dossier)
        self.lib.finish(research_id, dossier)
        return {"files": [], "dir": str(d), "research": research_id, "facts": len(dossier["facts"]), "images": len(dossier["images"]),
                "cost_usd": dossier.get("cost_usd", 0.0)}

    def _save_pages(self, research_id: str, pages: list[dict]) -> None:
        d = self.lib._dir(research_id) / "pages"
        d.mkdir(exist_ok=True)
        for page in pages:
            name = f"{page['lang']}-{slugify(page['title'])}.txt"
            (d / name).write_text(f"{page['permalink']}\n\n{page['text']}", encoding="utf-8")

    def _import_images(self, dossier: dict) -> None:
        for image in dossier["images"]:
            try:
                if image.get("puvod") == "sketchfab":
                    meta = self.fetch_url(image["url"], origin="web", title=image["nazev"], page_url=image.get("stranka"), author=image.get("autor"),
                                          license=image.get("licence"), license_url=image.get("licence_url"))
                else:
                    meta = self.fetch_image(image["file"])
                self.reflib.mark_seen(meta["id"])
                image["ref_id"] = meta["id"]
            except RefLibError as e:
                image["chyba"] = str(e)

    def add_pins(self, research_id: str, pins: list[PinIn]) -> dict:
        """Piny k dossieru: obrázek do knihovny předloh s adresou pinu. Stahuje se jen z i.pinimg.com, adresa přišla zvenčí."""
        rows = self.lib.inspiration(research_id)
        known = {r["pin"] for r in rows}
        added, errors = 0, []
        for pin in pins:
            if pin.pin in known:
                continue
            parts = urlparse(pin.obrazek)
            if parts.scheme != "https" or parts.hostname != "i.pinimg.com" or "pinterest." not in (urlparse(pin.pin).hostname or ""):
                errors.append({"pin": pin.pin, "chyba": "obrázek musí být z i.pinimg.com a pin z Pinterestu"})
                continue
            try:
                meta = self.fetch_url(pin.obrazek, origin="pinterest", title=pin.nazev or pin.dotaz, page_url=pin.pin)
                self.reflib.mark_seen(meta["id"])
            except RefLibError as e:
                errors.append({"pin": pin.pin, "chyba": str(e)})
                continue
            rows.append({"pin": pin.pin, "ref_id": meta["id"], "nazev": pin.nazev, "dotaz": pin.dotaz, "licence": PINTEREST_LICENSE,
                         "sirka": meta["width"], "vyska": meta["height"]})
            known.add(pin.pin)
            added += 1
        if added:
            self.lib.save_inspiration(research_id, rows)
        return {"pridano": added, "chyby": errors, "celkem": len(rows)}

    def _build_page(self, d: Path, dossier: dict) -> None:
        """Přehled obrázků: menší kopie vedle stránky, aby její relativní adresy fungovaly přes /api/v2/research/<id>/."""
        entries = []
        for i, image in enumerate(dossier["images"], 1):
            source = self.reflib.image_path(image["ref_id"]) if image.get("ref_id") else None
            if source is None:
                continue
            name = f"obr-{i:02d}.jpg"
            with Image.open(source) as im:
                copy = im.convert("RGB")
                copy.thumbnail((COPY_EDGE, COPY_EDGE))
                copy.save(d / name, quality=85)
            params = {"role": rs.ROLE_LABEL[image["role"]], "licence": image.get("licence"), "autor": image.get("autor"),
                      "stránka": image.get("stranka"), "předloha": image["ref_id"]}
            entries.append({"id": f"v{i:02d}", "src": name, "label": f"{rs.ROLE_LABEL[image['role']]}: {image['nazev']}",
                            "prompt": image.get("popis") or "", "params": {k: v for k, v in params.items() if v}})
        if entries:
            manifest = {"title": f"Podklady: {dossier['entita']['label']}", "note": f"{len(entries)} obrázků z Wikimedia Commons a Sketchfabu po rolích", "variants": entries}
            (d / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            variants_page.write_page(variants_page.load_manifest(d / "manifest.json"), d / PAGE)

    def _extend(self, job_id: str, req: dict) -> dict:
        base = self.lib.dossier(req["extends"])
        if base is None:
            raise rs.ResearchError(f"dossier {req['extends']} neexistuje")
        questions = [req["question"]] if req.get("question") else [
            *[q for q in base["otazky_bez_odpovedi"] if not q.startswith("Chybí obrázek")],
            *[f"Rozpor mezi zdroji: {f['tvrzeni']}" for f in base["facts"] if f["stav"] == "rozpor"]]
        if not questions:
            questions = [f"Co důležitého o {base['entita']['label']} ve faktech chybí?"]
        ledger = {"job_id": job_id, "caller": req.get("caller"), "backend": f"claude:{KIND}", "n": 1}
        spent: list[dict] = []

        def spend(cost: dict, status: str = "pending") -> None:
            spent.append(cost)
            self._log(ledger, spent, status)

        self.log_cost({**ledger, "usd": rs.WEB_USD, "status": "pending", "items": [{"what": "rešerše na webu (odhad)", "usd": rs.WEB_USD}]})
        try:
            web = rs.web_research(base["entita"]["label"], questions, base["facts"], spend=spend, turn=self.web_turn)
        except claude.ClaudeError as e:
            self._log(ledger, spent, "failed")
            raise rs.ResearchError(str(e)) from e
        except Exception:
            self._log(ledger, spent, "failed")
            raise
        self._log(ledger, spent, "ok")
        return rs.extend_dossier(base, web, sum(c["usd"] for c in spent))

    def _log(self, ledger: dict, spent: list[dict], status: str) -> None:
        """Jeden řádek na úlohu s dosavadní cenou: load_costs bere poslední, takže useknutý běh ukáže, co už stál."""
        usd = round(sum(c["usd"] for c in spent), 4)
        self.log_cost({**ledger, "usd": usd, "status": status, "usage": spent, "items": [{"what": f"rešerše na webu, {sum(c['searches'] for c in spent)} hledání", "usd": usd}]})


def register(app: FastAPI, researcher: Researcher, store) -> None:
    lib = researcher.lib

    def state(research_id: str) -> dict:
        req = lib.request(research_id)
        if req is None:
            raise HTTPException(404, f"rešerše {research_id} neexistuje")
        job = store.get(req.get("job_id") or "") or {}
        dossier = lib.dossier(research_id)
        return {"id": research_id, "tema": req["tema"], "verze": req.get("verze"), "created": req.get("created"), "job_id": req.get("job_id"),
                "extends": req.get("extends"), "status": "done" if dossier else job.get("status", "failed"), "error": job.get("error"), "dossier": dossier,
                "inspirace": lib.inspiration(research_id),
                "page": f"/api/v2/research/{research_id}/{PAGE}" if dossier and (lib._dir(research_id) / PAGE).exists() else None}

    def estimate(paid: bool) -> dict:
        items = [{"what": "volné zdroje: Wikidata, Wikipedia, Commons, Sketchfab", "usd": 0.0}]
        if paid:
            items.append({"what": f"hledání na webu, nejvýš {rs.MAX_SEARCHES} hledání ({rs.WEB_MODEL})", "usd": rs.WEB_USD})
        return {"total_usd": round(sum(i["usd"] for i in items), 4), "items": items}

    @app.get("/api/v2/research/estimate")
    def research_estimate(paid: bool = False):
        return estimate(paid)

    @app.post("/api/v2/research", status_code=202)
    def research_start(body: ResearchIn):
        if body.extends:
            base = lib.dossier(body.extends)
            if base is None:
                raise HTTPException(404, f"dossier {body.extends} neexistuje")
            if not body.confirm_cost:
                est = estimate(True)
                return JSONResponse(status_code=402, content={
                    "detail": "Hledání na webu je placené (Claude) — pošlete znovu s confirm_cost=true.",
                    "estimate_usd": est["total_usd"], "items": est["items"][1:]})
            topic = base["tema"]
        else:
            topic = body.topic.strip()
            if not topic and not body.qid:
                raise HTTPException(400, "napište téma")
        topic = topic or body.qid
        request = {"topic": topic, "qid": body.qid, "images": body.images, "per_role": body.per_role, "extends": body.extends,
                   "question": body.question, "caller": body.caller}
        research_id = lib.new(topic, request)
        saved = lib.request(research_id)
        job_id = store.add_task(KIND, body.caller, f"claude:{rs.WEB_MODEL}" if body.extends else "local", saved)
        lib.write_request(research_id, {**saved, "job_id": job_id})
        job = store.get(job_id)
        return {"id": research_id, "job_id": job_id, "status": job["status"], "position": job["position"],
                "estimate_usd": rs.WEB_USD if body.extends else 0.0}

    @app.get("/api/v2/research")
    def research_list(limit: int = 40):
        rows = []
        for research_id in lib.ids():
            st = state(research_id)
            d = st.pop("dossier") or {}
            st.pop("inspirace")
            facts = d.get("facts", [])
            rows.append({**st, "entita": (d.get("entita") or {}).get("label"), "facts": len(facts), "rozpory": sum(f["stav"] == "rozpor" for f in facts),
                         "images": len(d.get("images", [])), "cost_usd": d.get("cost_usd")})
        return sorted(rows, key=lambda r: r.get("created") or "", reverse=True)[:limit]

    @app.get("/api/v2/research/{research_id}")
    def research_get(research_id: str):
        return state(research_id)

    @app.post("/api/v2/research/{research_id}/inspirace")
    def research_inspiration(research_id: str, body: InspiraceIn):
        if lib.dossier(research_id) is None:
            raise HTTPException(404, f"dossier {research_id} neexistuje")
        return researcher.add_pins(research_id, body.piny)

    @app.get("/api/v2/research/{research_id}/{name}")
    def research_file(research_id: str, name: str):
        if not re.fullmatch(r"obr-\d+\.jpg|podklady\.html", name):
            raise HTTPException(404, "soubor rešerše neexistuje")
        path = lib._dir(research_id) / name
        if not path.exists():
            raise HTTPException(404, "soubor rešerše neexistuje")
        return FileResponse(path)
