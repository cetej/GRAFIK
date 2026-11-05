"""Průvodce „infografika“: téma nebo hotový dossier → podklady → návrhy skladby → výběr → poradní kontrola logiky → stránky série.

Jedna cena předem na celý řetězec (402 bez `confirm_cost`), krok nad schválenou cenu se zastaví a zeptá. Každý krok je úloha
`infografika` ve společné frontě a po doběhnutí si zařadí další, takže operátor kliká až u výběru návrhu.

Po restartu Engine řetězec naváže (`resume`, volá se po `recover_interrupted`). Úloha ve frontě běží dál sama. Přerušený krok
zdarma se zařadí znovu. Přerušený placený krok se nespustí sám: platba mohla proběhnout, proto se jeho odhad počítá do útraty
a řetězec se zeptá (fronta nikdy nespouští placenou úlohu dvakrát).

library/navrhy/<wf>/navrh-<n>.svg   náčrty návrhů
workflows/<wf>.json                 stav řetězce včetně návrhů
"""
from __future__ import annotations

import json
import re
import threading

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from typing import Literal

from PIL import Image
from pydantic import BaseModel

from engine import infographics, proposals, serie, textura3d, zadani as zd
from engine.infographics import InfoError
from engine.models3d import Model3dError
from engine.reflib import RefLibError
from engine.workflows import Workflow
from ngm_shared import claude, image_checks as ic, research as rs
from ngm_shared.research import ResearchError

KIND = "infografika"
LABEL = {"zadani": "Zadání", "podklady": "Podklady", "web": "Hledání na webu", "navrhy": "Návrhy skladby", "kontrola": "Kontrola logiky", "stranky": "Stránky série"}
STEPS = ("zadani", "podklady", "navrhy", "kontrola", "stranky")     # "web" jen na souhlas, když volné zdroje nestačí
COST_WHAT = {"zadani": "rozbor zadání a vzoru: co hledat a co ověřit", "podklady": "podklady: Wikidata, Wikipedia, Commons",
             "web": f"hledání na webu, nejvýš {rs.MAX_SEARCHES} hledání ({rs.WEB_MODEL})", "navrhy": "3 návrhy skladby, náčrty 0 USD",
             "kontrola": "poradní kontrola logiky vybraného návrhu", "stranky": "krátké české texty stránek z vybraných faktů"}


def rest(stage: str) -> tuple[str, ...]:
    """Kroky od `stage` do konce; web je jednorázová odbočka před návrhy."""
    return ("web", *STEPS[STEPS.index("navrhy"):]) if stage == "web" else STEPS[STEPS.index(stage):]


def _usd(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".").replace(".", ",") + " USD"


class ChainIn(BaseModel):
    topic: str = ""
    qid: str | None = None
    vzor: str | None = None             # ref_id vzoru z knihovny předloh
    research: str | None = None         # začít od hotového dossieru
    model: str | None = None            # jinak proposals.DEFAULT_MODEL
    urceni: Literal["web", "tisk"] = "web"
    confirm_cost: bool = False
    caller: str = "studio"


class PickIn(BaseModel):
    navrh: int
    stranky: list[int] | None = None    # bez výběru celá série


class ContinueIn(BaseModel):
    confirm_cost: bool = False
    bez_webu: bool = False              # stojí před hledáním na webu: pokračovat jen s volnými zdroji


class Chain:
    def __init__(self, settings, store, workflows, researcher, reflib, log_cost, ask=None, check_ask=claude.ask):
        self.s, self.store, self.wfs, self.researcher, self.reflib, self.log_cost = settings, store, workflows, researcher, reflib, log_cost
        self.ask = ask                  # testy; jinak podle modelu (proposals.propose)
        self.check_ask = check_ask
        self.raster = infographics.rasterize
        self.make_doc = None            # engine/app.py: pole stránky → dokument s panely
        self.pages_3d = None            # engine/app.py: (tvor3d, StrankaIn, extra) → dokumenty z vrstev 3D tvora (textura3d.make_pages)
        self.root = settings.library_dir / "navrhy"
        self._enqueue_lock = threading.Lock()   # worker si stav přečte až po zápisu `step_job`

    def handlers(self) -> dict:
        return {KIND: self.run}

    def step_usd(self, wf: Workflow, stage: str) -> float:
        reads = wf.vzor or not wf.qid       # zadání čte model jen u vzoru nebo tématu bez položky Wikidaty
        return {"zadani": zd.USD if reads else 0.0, "podklady": 0.0, "web": rs.WEB_USD, "navrhy": proposals.estimate_usd(wf.model),
                "kontrola": ic.LOGIC_USD, "stranky": serie.estimate_usd(wf.model)}[stage]

    def estimate(self, wf: Workflow, stages=STEPS) -> dict:
        items = [{"what": COST_WHAT[s] + (f" ({wf.model})" if s == "navrhy" else ""), "usd": self.step_usd(wf, s)} for s in stages]
        return {"total_usd": round(sum(i["usd"] for i in items), 4), "items": items}

    def run(self, job_id: str, req: dict) -> dict:
        with self._enqueue_lock:
            wf = self.wfs.get(req["wf"])
        stage = req["stage"]
        try:
            return {"zadani": self._zadani, "podklady": self._podklady, "web": self._web, "navrhy": self._navrhy,
                    "kontrola": self._kontrola, "stranky": self._stranky}[stage](wf, job_id)
        except Exception as e:
            self.stop(wf, stage, f"{LABEL[stage]}: {e}")
            raise

    def stop(self, wf: Workflow, stage: str, reason: str) -> None:
        wf.stage, wf.resume_stage, wf.stop_reason, wf.step_job = "stop", stage, reason, None
        wf.resume_usd = self.estimate(wf, rest(stage))["total_usd"]
        self.wfs.save(wf)

    def enqueue(self, wf: Workflow, stage: str) -> None:
        """Další krok, nebo zastavení s dotazem, když se do schválené ceny nevejde."""
        usd = self.step_usd(wf, stage)
        if usd and wf.spent_usd + usd > wf.budget_usd + 1e-9:
            self.stop(wf, stage, f"{LABEL[stage]} stojí asi {_usd(usd)} a do schválené ceny {_usd(wf.budget_usd)} se nevejde (utraceno {_usd(wf.spent_usd)}).")
            return
        with self._enqueue_lock:
            wf.stage, wf.resume_stage, wf.stop_reason = stage, None, None
            backend = ("local" if not usd else f"{proposals.vendor(wf.model)}:{wf.model}" if stage in ("navrhy", "stranky")
                       else f"claude:{zd.MODEL}" if stage == "zadani" else f"claude:{rs.WEB_MODEL}" if stage == "web" else f"claude:{ic.MODEL}")
            wf.step_job = self.store.add_task(KIND, wf.caller, backend, {"wf": wf.id, "stage": stage})
            self.wfs.save(wf)

    def resume(self) -> None:
        """Po restartu: viz docstring modulu."""
        for wf in self.wfs.list():
            if wf.kind != KIND or wf.stage not in LABEL:
                continue
            job = self.store.get(wf.step_job) if wf.step_job else None
            if job and job["status"] == "queued":
                continue
            usd = self.step_usd(wf, wf.stage)
            if job and usd:
                wf.spent_usd = round(wf.spent_usd + usd, 4)
                self.stop(wf, wf.stage, f"{LABEL[wf.stage]}: krok přerušil restart Engine. Platba mohla proběhnout, počítám s {_usd(usd)}.")
            else:
                self.enqueue(wf, wf.stage)

    def _zadani(self, wf: Workflow, job_id: str) -> dict:
        """Vzor a téma přečte model dřív než rešerše: z otázky heslo, z otázky a vzoru co ověřit na webu."""
        estimate = self.step_usd(wf, "zadani")
        if not estimate:
            self.enqueue(wf, "podklady")
            return {"files": [], "cost_usd": 0.0}
        vzor = self.reflib.image_path(wf.vzor) if wf.vzor else None
        ledger = {"job_id": job_id, "caller": wf.caller, "backend": "claude:zadani", "n": 1}
        self.log_cost({**ledger, "usd": estimate, "status": "pending", "items": [{"what": "rozbor zadání, odhad", "usd": estimate}]})
        try:
            out = zd.read(wf.object, vzor, ask=self.ask)
        except claude.ClaudeError as e:
            cost = e.cost or {"usd": 0.0}
            self.log_cost({**ledger, "usd": cost["usd"], "status": "failed", "usage": cost, "items": [{"what": "rozbor zadání", "usd": cost["usd"]}]})
            wf.spent_usd = round(wf.spent_usd + cost["usd"], 4)
            raise ResearchError(str(e)) from e
        cost = out.pop("cost")
        self.log_cost({**ledger, "usd": cost["usd"], "status": "ok", "usage": cost, "items": [{"what": "rozbor zadání", "usd": cost["usd"]}]})
        wf.spent_usd = round(wf.spent_usd + cost["usd"], 4)
        wf.zadani = out
        self.enqueue(wf, "podklady")
        return {"files": [], "cost_usd": cost["usd"]}

    def _podklady(self, wf: Workflow, job_id: str) -> dict:
        """Volné zdroje. Když heslo nenajdou, zkusí anglické; když ani to, nebo zadání ptá dál než heslo, zastaví se s nabídkou webu."""
        lib = self.researcher.lib
        z = wf.zadani or {}
        topic = z.get("predmet") or wf.object
        if not wf.research_id:
            wf.research_id = lib.new(topic, {"topic": topic, "qid": wf.qid, "images": True, "per_role": 4, "extends": None, "question": None, "caller": wf.caller})
            self.wfs.save(wf)
        request = {**lib.request(wf.research_id), "job_id": job_id}
        lib.write_request(wf.research_id, request)
        if lib.dossier(wf.research_id) is None:
            tries = [request["topic"], *([z["predmet_en"]] if z.get("predmet_en") and not wf.qid else [])]
            for n, name in enumerate(tries, 1):
                try:
                    self.researcher.run(job_id, {**request, "topic": name})
                    break
                except rs.NotFound:
                    if n == len(tries):
                        lib.finish(wf.research_id, empty_dossier(wf.research_id, request.get("verze"), topic, z.get("druh", "vec")))
        dossier = lib.dossier(wf.research_id)
        questions = zd.web_questions(wf.zadani)
        if dossier["facts"] and not questions:
            self.enqueue(wf, "navrhy")
        else:
            web = _usd(rs.WEB_USD)
            self.stop(wf, "web", f"K „{topic}“ jsem na Wikipedii nenašel žádná fakta. Hledání na webu stojí asi {web}." if not dossier["facts"] else
                      f"Wikipedie dala {len(dossier['facts'])} faktů o „{dossier['entita']['label']}“, na otázky zadání a vzoru ale neodpovídá. "
                      f"Hledání na webu stojí asi {web}, nebo pokračujte jen s Wikipedií.")
        return {"files": [], "research": wf.research_id, "cost_usd": 0.0}

    def _web(self, wf: Workflow, job_id: str) -> dict:
        """Placené doplnění dossieru z webu otázkami zadání a vzoru; nová verze dossieru, stará zůstává."""
        lib = self.researcher.lib
        base = lib.dossier(wf.research_id)
        questions = zd.web_questions(wf.zadani) or [wf.object]
        if wf.object not in questions[0]:
            questions = [f"Otázka zadání: {wf.object}", *questions]
        new_id = lib.new(base["tema"], {"topic": base["tema"], "qid": None, "images": False, "per_role": 4, "extends": wf.research_id,
                                        "question": None, "questions": questions, "caller": wf.caller})
        request = {**lib.request(new_id), "job_id": job_id}
        lib.write_request(new_id, request)
        try:
            self.researcher.run(job_id, request)
        except Exception:
            wf.spent_usd = round(wf.spent_usd + rs.WEB_USD, 4)      # přesná cena je v ledgeru, do rozpočtu počítám odhad
            raise
        dossier = lib.dossier(new_id)
        usd = round(dossier.get("cost_usd", 0.0) - base.get("cost_usd", 0.0), 4)
        wf.spent_usd, wf.research_id = round(wf.spent_usd + usd, 4), new_id
        if not dossier["facts"]:
            raise ResearchError("ani na webu jsem nenašel fakta se zdrojem, není z čeho navrhovat")
        self.enqueue(wf, "navrhy")
        return {"files": [], "research": new_id, "cost_usd": usd}

    def _navrhy(self, wf: Workflow, job_id: str) -> dict:
        dossier = self.researcher.lib.dossier(wf.research_id)
        if not dossier["facts"]:
            raise ResearchError("v dossieru nejsou fakta, není z čeho navrhovat, nic se neplatilo; zkuste jinou položku Wikidaty")
        if wf.zadani and wf.zadani["predmet"] != wf.object:
            dossier = {**dossier, "otazka": wf.object}
        vzor = self.reflib.image_path(wf.vzor) if wf.vzor else None
        estimate = self.step_usd(wf, "navrhy")
        ledger = {"job_id": job_id, "caller": wf.caller, "backend": f"{proposals.vendor(wf.model)}:navrhy", "n": 1}
        what = f"návrhy skladby ({wf.model})"
        self.log_cost({**ledger, "usd": estimate, "status": "pending", "items": [{"what": f"{what}, odhad", "usd": estimate}]})
        try:
            out = proposals.propose(dossier, vzor=vzor, model=wf.model, ask=self.ask, urceni=wf.urceni, own=serie.own_pictures(self.s.library_dir, dossier))
        except claude.ClaudeError as e:
            cost = e.cost or {"usd": 0.0}
            self.log_cost({**ledger, "usd": cost["usd"], "status": "failed", "usage": cost, "items": [{"what": what, "usd": cost["usd"]}]})
            wf.spent_usd = round(wf.spent_usd + cost["usd"], 4)
            raise ResearchError(str(e)) from e
        except Exception:
            self.log_cost({**ledger, "usd": 0.0, "status": "failed", "est_usd": estimate, "items": [{"what": what, "usd": 0.0}]})
            raise
        cost = out["cost"]
        self.log_cost({**ledger, "usd": cost["usd"], "status": "ok", "usage": cost, "items": [{"what": what, "usd": cost["usd"]}]})
        wf.spent_usd = round(wf.spent_usd + cost["usd"], 4)
        d = self.root / wf.id
        d.mkdir(parents=True, exist_ok=True)
        for proposal in out["navrhy"]:
            for n, page in enumerate(proposals.pages(proposal), 1):
                (d / f"navrh-{proposal['id']}{f'-{n}' if n > 1 else ''}.svg").write_text(proposals.sketch(page), encoding="utf-8")
        wf.navrhy, wf.rozbor, wf.stage, wf.step_job = out["navrhy"], out["rozbor"], "vyber", None
        self.wfs.save(wf)
        return {"files": [], "navrhy": len(out["navrhy"]), "cost_usd": cost["usd"]}

    def _kontrola(self, wf: Workflow, job_id: str) -> dict:
        """Poradní: selhání ani nález řetězec nezastaví, jen se ukáže u výběru."""
        proposal = next(p for p in wf.navrhy if p["id"] == wf.vyber)
        ledger = {"job_id": job_id, "caller": wf.caller, "backend": "claude:check-logic", "n": 1}
        self.log_cost({**ledger, "usd": ic.LOGIC_USD, "status": "pending", "items": [{"what": "kontrola logiky návrhu, odhad", "usd": ic.LOGIC_USD}]})
        try:
            width, height = proposals.sketch_size(proposal)
            png = self.raster(proposals.sketch(proposal), width, height, "png")
            brief = f"Infografika: {wf.object}. {proposal['nazev']}: {proposal['veta']}"
            result = ic.check_logic(png, brief, phase="plan", layout=proposals.layout_text(proposal, wf.stranky), ask=self.check_ask)
            wf.kontrola = {k: result[k] for k in ("summary", "purpose", "warnings")}
            status, cost = "ok", result["cost"]
        except Exception as e:      # i rozbitý převod náčrtu na obrázek: kontrola je poradní
            wf.kontrola = {"chyba": str(e)}
            status, cost = "failed", getattr(e, "cost", None) or {"usd": 0.0}
        usd = cost["usd"]
        self.log_cost({**ledger, "usd": usd, "status": status, "usage": cost, "items": [{"what": "kontrola logiky návrhu", "usd": usd}]})
        wf.spent_usd = round(wf.spent_usd + usd, 4)
        wf.stage, wf.step_job = "hotovo", None
        self.wfs.save(wf)
        return {"files": [], "cost_usd": usd}

    def _stranky(self, wf: Workflow, job_id: str) -> dict:
        """Texty za peníze, pak dokument na stránku. Stránka, která nejde složit, řekne proč; ostatní zůstanou, texty už jsou zaplacené."""
        dossier = self.researcher.lib.dossier(wf.research_id)
        proposal = next(p for p in wf.navrhy if p["id"] == wf.vyber)
        estimate = self.step_usd(wf, "stranky")
        ledger = {"job_id": job_id, "caller": wf.caller, "backend": f"{proposals.vendor(wf.model)}:texty", "n": 1}
        what = f"texty stránek ({wf.model})"
        self.log_cost({**ledger, "usd": estimate, "status": "pending", "items": [{"what": f"{what}, odhad", "usd": estimate}]})
        images, notes = serie.pick_images(dossier, proposal, wf.stranky, serie.own_pictures(self.s.library_dir, dossier))
        try:
            written = serie.write_texts(dossier, proposal, wf.stranky, model=wf.model, ask=self.ask, images=images)
        except claude.ClaudeError as e:
            cost = e.cost or {"usd": 0.0}
            self.log_cost({**ledger, "usd": cost["usd"], "status": "failed", "usage": cost, "items": [{"what": what, "usd": cost["usd"]}]})
            wf.spent_usd = round(wf.spent_usd + cost["usd"], 4)
            raise ResearchError(str(e)) from e
        except Exception:
            self.log_cost({**ledger, "usd": 0.0, "status": "failed", "est_usd": estimate, "items": [{"what": what, "usd": 0.0}]})
            raise
        cost = written["cost"]
        self.log_cost({**ledger, "usd": cost["usd"], "status": "ok", "usage": cost, "items": [{"what": what, "usd": cost["usd"]}]})
        wf.spent_usd = round(wf.spent_usd + cost["usd"], 4)
        pages = proposals.pages(proposal)
        title_share = serie.series_title([text["titulek"] for text in written["stranky"].values()])
        done = []
        for n in wf.stranky:
            said = written["hlaseni"].get(n, []) + notes.get(n, [])
            text = written["stranky"].get(n)
            if text is None:
                done.append({"stranka": n, "nazev": pages[n - 1]["nazev"], "doc": None, "hlaseni": [*said, "Model k téhle stránce nevrátil text."]})
                continue
            if (images.get((n, 1)) or {}).get("tvor3d"):
                done.append(self._page_3d(wf, n, images[(n, 1)], text, said))
                continue
            try:
                fields, more = serie.page_fields(n, pages[n - 1], text, images, dossier, self.picture_of, title_share=title_share)
                doc = self.make_doc({**fields, "urceni": wf.urceni, "serie": {"wf": wf.id, "stranka": n, "celkem": len(wf.stranky)}})
                done.append({"stranka": n, "nazev": text["titulek"], "doc": doc["id"], "hlaseni": [*said, *more]})
            except InfoError as e:
                done.append({"stranka": n, "nazev": text["titulek"], "doc": None, "hlaseni": [*said, str(e)]})
        wf.serie, wf.stage, wf.step_job = done, "hotovo", None
        self.wfs.save(wf)
        return {"files": [], "stranky": len(done), "cost_usd": cost["usd"]}

    def _page_3d(self, wf: Workflow, n: int, image: dict, text: dict, said: list[str]) -> dict:
        """Hlavní obraz je 3D tvor (fáze 3b): stránka z jeho vrstev, vnitřek v obrysu kůže a záře postavy, popisky u bodů modelu.
        Na výšku (telefon) první, na šířku vedle; položka bez bodu na takové stránce nemá místo a řekne to hlášení.
        Nadpis popisku je název části z obrazy.json, ne to, co model napsal: u tlamy stálo „Krakatice“ (řetězec 5. 11.)."""
        tvor, names = image["tvor3d"], image.get("popisky") or {}
        popisky, out = {}, []
        for item in text["polozky"]:
            if item["bod"] in names and item["bod"] not in popisky:
                value, body = item["value"].strip(), item["text"].strip()
                more = body if not value or value.casefold() == names[item["bod"]].casefold() else f"{value}: {body[:1].lower()}{body[1:]}" if body else value
                popisky[item["bod"]] = "\n".join(t for t in (names[item["bod"]], more) if t)
            else:
                out.append(f"Na 3D obraz se nevešlo: {serie._said(item)}")
        page = {"stranka": n, "nazev": text["titulek"], "doc": None}
        if not popisky:
            return {**page, "hlaseni": [*said, *out, "Žádný popisek nemíří na bod 3D modelu, stránka nevznikla."]}
        req = textura3d.StrankaIn(hotovo=tvor["hotovo"], titulek=text["titulek"], popisky=popisky, formaty=["9:16", "16:9"])
        extra = {"urceni": wf.urceni, "serie": {"wf": wf.id, "stranka": n, "celkem": len(wf.stranky)}}
        try:
            docs, dropped = self.pages_3d(tvor, req, extra)
        except (Model3dError, InfoError) as e:
            return {**page, "hlaseni": [*said, *out, str(e)]}
        return {**page, "doc": docs[0]["id"], "dokumenty": [{"id": d["id"], "size": d["size"]} for d in docs], "hlaseni": [*said, *out, *dropped]}

    def picture_of(self, image: dict) -> dict:
        """Obraz pro rozvržení: zdroj dokumentu, rozměr, průhlednost a pojmenované body."""
        if image.get("slozka"):
            folder = self.s.library_dir / image["slozka"]
            path, points = folder / "obraz.png", json.loads((folder / "body.json").read_text(encoding="utf-8")).get("points", {})
            source = {"slozka": image["slozka"], **({"ai": image["ai"]} if image.get("ai") else {}),
                      **({k: image["model"][k] for k in ("model_id", "version")} if image.get("model") else {})}     # model za obrazem jde s předávkou do POHYBu
        else:
            path, points, source = self.reflib.image_path(image["ref_id"]), {}, {"ref_id": image["ref_id"]}
            meta = self.reflib.get(image["ref_id"]) or {}
        with Image.open(path) as im:
            alpha = im.getchannel("A").copy() if im.mode == "RGBA" else None
            found = {"zdroj": source, "_res": im.size, "_alpha": alpha, "_points": points}
        return {**found, "_autor": meta.get("author"), "_licence": meta.get("license")} if image.get("ref_id") and not image.get("slozka") else found


def empty_dossier(research_id: str, verze, topic: str, druh: str) -> dict:
    """Heslo na Wikipedii není: dossier bez faktů jako základ pro hledání na webu (`extends`)."""
    return {"tema": topic, "entita": {"qid": None, "label": topic, "popis": "", "url": None, "commons_category": None, "sitelinks": {}, "druh": druh},
            "facts": [], "images": [], "pinterest": [], "otazky_bez_odpovedi": [f"Na Wikipedii není heslo „{topic}“."], "zdroje": [],
            "cost_usd": 0.0, "id": research_id, "verze": verze}


def register(app: FastAPI, chain: Chain, workflows) -> None:
    lib = chain.researcher.lib

    def get(wf_id: str) -> Workflow:
        try:
            wf = workflows.get(wf_id)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        if wf is None or wf.kind != KIND:
            raise HTTPException(404, "řetězec neexistuje")
        return wf

    def payment(est: dict, what: str) -> JSONResponse:
        return JSONResponse(status_code=402, content={"detail": f"{what} je placené — pošlete znovu s confirm_cost=true.", "estimate_usd": est["total_usd"], "items": est["items"]})

    @app.get("/api/v2/workflows/infografika/estimate")
    def chain_estimate(model: str | None = None, research: str | None = None):
        wf = Workflow(id="odhad", kind=KIND, model=model or proposals.DEFAULT_MODEL)
        return chain.estimate(wf, rest("navrhy") if research else STEPS)

    @app.post("/api/v2/workflows/infografika", status_code=201)
    def chain_start(body: ChainIn):
        model = body.model or proposals.DEFAULT_MODEL
        topic = body.topic.strip() or body.qid or ""
        if body.research:
            dossier = lib.dossier(body.research)
            if dossier is None:
                raise HTTPException(404, f"dossier {body.research} neexistuje")
            topic = dossier["tema"]
        elif not topic:
            raise HTTPException(400, "napište téma")
        try:
            if body.vzor and chain.reflib.image_path(body.vzor) is None:
                raise HTTPException(404, f"vzor {body.vzor} v knihovně předloh neexistuje")
        except RefLibError as e:
            raise HTTPException(400, str(e)) from e
        draft = Workflow(id="odhad", kind=KIND, model=model, qid=body.qid, vzor=body.vzor)
        est = chain.estimate(draft, rest("navrhy") if body.research else STEPS)
        if not body.confirm_cost:
            return payment(est, "Řetězec")
        wf = workflows.create(kind=KIND, object=topic, qid=body.qid, vzor=body.vzor, model=model, urceni=body.urceni, caller=body.caller, research_id=body.research, budget_usd=est["total_usd"], stranky_usd=chain.step_usd(draft, "stranky"))
        chain.enqueue(wf, "navrhy" if body.research else "zadani")
        return wf

    @app.post("/api/v2/workflows/{wf_id}/pick")
    def chain_pick(wf_id: str, body: PickIn):
        wf = get(wf_id)
        if wf.stage not in ("vyber", "hotovo"):     # hotovo: operátor si to rozmyslel, kontrola proběhne znovu v rámci ceny
            raise HTTPException(409, "návrh jde vybrat, až řetězec čeká na výběr")
        proposal = next((p for p in wf.navrhy if p["id"] == body.navrh), None)
        if proposal is None:
            raise HTTPException(404, f"návrh {body.navrh} neexistuje")
        count = len(proposals.pages(proposal))
        chosen = sorted(set(body.stranky)) if body.stranky is not None else list(range(1, count + 1))
        if not chosen or chosen[0] < 1 or chosen[-1] > count:
            raise HTTPException(400, f"vyberte aspoň jednu stránku z {count}")
        wf.vyber, wf.stranky, wf.serie = body.navrh, chosen, []
        chain.enqueue(wf, "kontrola")
        return workflows.get(wf_id)

    @app.post("/api/v2/workflows/{wf_id}/stranky")
    def chain_pages(wf_id: str):
        """Složit vybrané stránky. Cena je ve schválené ceně řetězce, starší řetězec se zastaví a zeptá."""
        wf = get(wf_id)
        if wf.stage != "hotovo" or wf.vyber is None:
            raise HTTPException(409, "stránky jdou složit, až je vybraný návrh a kontrola doběhla")
        if wf.serie:
            raise HTTPException(409, "stránky jsou složené; nová série chce nový výběr návrhu")
        chain.enqueue(wf, "stranky")
        return workflows.get(wf_id)

    @app.post("/api/v2/workflows/{wf_id}/continue")
    def chain_continue(wf_id: str, body: ContinueIn):
        wf = get(wf_id)
        if wf.stage != "stop" or not wf.resume_stage:
            raise HTTPException(409, "řetězec nestojí, není co obnovit")
        if body.bez_webu:
            if wf.resume_stage != "web":
                raise HTTPException(409, "řetězec nestojí před hledáním na webu")
            if not lib.dossier(wf.research_id)["facts"]:
                raise HTTPException(409, "bez webu nejsou žádná fakta, není z čeho navrhovat")
            wf.resume_stage = "navrhy"
        est = chain.estimate(wf, rest(wf.resume_stage))
        if est["total_usd"] and not body.confirm_cost:
            return payment(est, "Pokračování")
        wf.budget_usd = round(wf.spent_usd + est["total_usd"], 4)
        chain.enqueue(wf, wf.resume_stage)
        return workflows.get(wf_id)

    @app.get("/api/v2/workflows/{wf_id}/navrhy/{name}")
    def chain_sketch(wf_id: str, name: str):
        get(wf_id)
        if not re.fullmatch(r"navrh-\d+(-\d+)?\.svg", name):
            raise HTTPException(404, "náčrt neexistuje")
        path = chain.root / wf_id / name
        if not path.exists():
            raise HTTPException(404, "náčrt neexistuje")
        return FileResponse(path, media_type="image/svg+xml")
