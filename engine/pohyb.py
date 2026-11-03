"""Předávka do POHYBu: hotová infografika i s podklady jako zadání animace (operátor 3. 11.).

Engine složí balík v library/pohyb/<id>/ (manifest.json a kopie souborů, nic se nepřepisuje, každé odeslání má
novou složku) a pošle ho jako zip na POHYB `POST /api/predavky`. POHYB z něj udělá zakázku, která čeká na
operátora. Nic se neplatí.

Stránka balíku je hotový obrázek z Knihovny nebo infografika. Z vrstev rendereru (`<g id="Grafika">`,
`<g id="Texty">`) vznikne obraz bez textu, každý objekt jako samostatné PNG s polohou a popisky s místem,
kotvou a barvou: to byla ruční práce u klipu k vojákovi ve studni (POHYB spikes/velsen). Dokument s panely
přidá panely s body.json, model GLB, předlohy s autorem a licencí, dossier rešerše a fakta se zdroji.
"""
from __future__ import annotations

import copy
import io
import json
import re
import secrets
import shutil
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from PIL import Image
from pydantic import BaseModel

from engine import panels
from engine.infographics import InfoError, ai_note, canvas_size, rasterize

FORMAT = "grafik-predavka"
VERZE = 1
VIDEO_FORMATS = ("9:16", "16:9", "4:5", "1:1")      # POHYB Brief.format
MAX_PAGES = 12
MAX_MODEL_BYTES = 80_000_000
TITLE_IDS = ("Titulek", "Nadpis")
SOURCE_IDS = ("Zdroj", "Patička")
SERIES = re.compile(r"(\d+) ze (\d+)")
NS = "{http://www.w3.org/2000/svg}"


class Polozka(BaseModel):
    obrazek: str | None = None          # "<job>/<n>" hotový obrázek z Knihovny
    infografika: str | None = None      # id dokumentu


class PohybIn(BaseModel):
    polozky: list[Polozka]
    nazev: str = ""
    sdeleni: str = ""                   # co má animace sdělit, slovy operátora
    format: str = ""                    # formát videa; prázdný = podle první stránky


def _tag(el: ET.Element) -> str:
    return el.tag.rsplit("}", 1)[-1]


def _num(value: str | None) -> float:
    return float(re.sub(r"[^\d.\-]", "", value or "") or 0)


def slug(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", plain).strip("-")[:40] or "objekt"


def svg_size(root: ET.Element) -> tuple[int, int]:
    if root.get("width") and root.get("height"):
        return round(_num(root.get("width"))), round(_num(root.get("height")))
    box = (root.get("viewBox") or "0 0 0 0").split()
    return round(float(box[2])), round(float(box[3]))


def _points(text: str) -> list[list[float]]:
    nums = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", text or "")]
    return [[nums[i], nums[i + 1]] for i in range(0, len(nums) - 1, 2)]


def _leader(group: ET.Element | None) -> tuple[list[float] | None, list[list[float]] | None]:
    if group is None:
        return None, None
    circle = next((c for c in group if _tag(c) == "circle"), None)
    line = next((c for c in group if _tag(c) == "polyline"), None)
    return ([_num(circle.get("cx")), _num(circle.get("cy"))] if circle is not None else None,
            _points(line.get("points")) if line is not None else None)


def split_layers(svg: str) -> dict | None:
    """Vrstvy z rendereru: objekty Grafiky, popisky Textů a SVG bez textu. SVG bez těch dvou skupin = None.
    Popisek je skupina s vlastními `<text>`; kotva a vodítko jsou v ní (plakát), nebo ve skupině „Vodítko <id>“ v Grafice (dokument s panely).
    Skupina samých koleček bez textu jsou značky."""
    root = ET.fromstring(svg)
    top = {el.get("id"): el for el in root if el.get("id")}
    grafika, texty = top.get("Grafika"), top.get("Texty")
    if grafika is None or texty is None:
        return None
    width, height = svg_size(root)
    back = top.get("Pozadí")
    if back is None:
        back = next((g for g in grafika if g.get("id") == "Pozadí"), None)
        back = next((r for r in back if _tag(r) == "rect"), None) if back is not None else None
    pozadi = back.get("fill") if back is not None and (back.get("fill") or "").startswith("#") else None
    leaders = {g.get("id"): g for g in grafika.iter() if (g.get("id") or "").startswith("Vodítko ")}

    def alone(keep: list[ET.Element]) -> str:
        page = copy.copy(root)
        page[:] = [el for el in root if _tag(el) == "defs"] + keep
        return ET.tostring(page, encoding="unicode")

    objekty = [{"id": g.get("id"), "svg": alone([g]), "texty": sum(_tag(t) == "text" for t in g.iter())} for g in grafika
               if _tag(g) == "g" and g.get("id") and g.get("id") != "Pozadí" and not g.get("id").startswith("Vodítk")]
    texts = []
    for group in texty.iter():
        lines = [t for t in group if _tag(t) == "text"]
        dots = [c for c in group if _tag(c) == "circle"]
        if _tag(group) != "g" or not (lines or len(dots) > 1):
            continue
        name = group.get("id") or ""
        if not lines:       # skupina značek bez textu (studny s kostmi na mapě)
            texts.append({"id": name, "role": "znacky", "barva": dots[0].get("fill"),
                          "body": [[_num(c.get("cx")), _num(c.get("cy"))] for c in dots]})
            continue
        kotva, voditko = _leader(group) if any(_tag(c) == "circle" for c in group) else _leader(leaders.get(f"Vodítko {name}"))
        role = "titulek" if name in TITLE_IDS else "zdroj" if name in SOURCE_IDS else "popisek" if kotva else "text"
        texts.append({"id": name, "role": role, "kotva": kotva, "voditko": voditko, "radky": [
            {"text": "".join(t.itertext()), "x": _num(t.get("x")), "y": _num(t.get("y")), "velikost": _num(t.get("font-size")),
             "barva": t.get("fill"), "rez": t.get("font-weight") or "400", "zarovnani": t.get("text-anchor") or "start"}
            for t in lines]})
    no_text = copy.copy(root)
    no_text[:] = [el for el in root if el is not texty]
    clean = copy.copy(grafika)
    clean[:] = [g for g in grafika if not (g.get("id") or "").startswith("Vodítk")]
    no_text[:] = [clean if el is grafika else el for el in no_text]
    return {"rozmer": [width, height], "pozadi": pozadi, "objekty": objekty, "texty": texts,
            "bez_textu": ET.tostring(no_text, encoding="unicode")}


def render_pngs(svgs: list[str], width: int, height: int) -> list[bytes]:
    """Obraz bez textu a objekty jeden po druhém v jednom Chromiu; mimo obraz zůstane průhledno."""
    from playwright.sync_api import sync_playwright
    out = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            for svg in svgs:
                page.set_content(f'<!doctype html><html><body style="margin:0;background:transparent">{svg}</body></html>', wait_until="load")
                out.append(page.screenshot(clip={"x": 0, "y": 0, "width": width, "height": height}, omit_background=True))
        finally:
            browser.close()
    return out


def _crop(png: bytes) -> tuple[bytes, list[int]] | None:
    with Image.open(io.BytesIO(png)) as im:
        rgba = im.convert("RGBA")
    box = rgba.getchannel("A").getbbox()
    if box is None:
        return None
    buf = io.BytesIO()
    rgba.crop(box).save(buf, "PNG")
    return buf.getvalue(), [box[0], box[1], box[2] - box[0], box[3] - box[1]]


def video_format(width: int, height: int) -> str:
    return "9:16" if height > width * 1.1 else "16:9" if width > height * 1.1 else "1:1"


def zip_dir(folder: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(folder.rglob("*")):
            if path.is_file() and path.name != "odeslano.json":
                z.write(path, path.relative_to(folder).as_posix())
    return buf.getvalue()


class Bundler:
    """`prov(ref)` = provenience obrázku, `model_dir(zdroj)` = složka verze 3D modelu panelu (chyba = model se nepřidá)."""

    def __init__(self, settings, store, infos, reflib, workflows, research_lib, prov, model_dir):
        self.s, self.store, self.infos, self.reflib = settings, store, infos, reflib
        self.workflows, self.research_lib, self.prov, self.model_dir = workflows, research_lib, prov, model_dir

    @property
    def root(self) -> Path:
        return self.s.library_dir / "pohyb"

    # -- stránky ----------------------------------------------------------------
    def candidates(self, obrazek: str | None, infografika: str | None) -> dict:
        """Co dialog nabídne a co předvybere: série dokumentu podle `serie.wf`, u obrázku z Knihovny obrázky nahrané do minuty spolu."""
        if infografika:
            doc = self._doc(infografika)
            wf = (doc.get("serie") or {}).get("wf")
            docs = [d for d in self.infos.list() if wf and (d.get("serie") or {}).get("wf") == wf] or [doc]
            docs.sort(key=lambda d: (d.get("serie") or {}).get("stranka", 0))
            offer = [{"polozka": {"infografika": d["id"]}, "nazev": d.get("title") or d["id"],
                      "nahled": f"/api/v2/jobs/{d['base'].replace('/', '/images/')}?w=256" if d.get("base") else None} for d in docs]
            return {"nabidka": offer, "vybrane": [o["polozka"] for o in offer]}
        if not obrazek or self.store.image_path(obrazek) is None:
            raise HTTPException(404, f"obrázek {obrazek} neexistuje")
        finished = [j for j in self.store.list(2000) if j["backend"] == "local" and "source" in j["request"] and j["status"] == "done"]
        offer = [{"polozka": {"obrazek": f"{j['job_id']}/0"}, "nazev": j["request"].get("prompt") or j["request"]["source"],
                  "nahled": f"/api/v2/jobs/{j['job_id']}/images/0?w=256", "created": j["created"]} for j in finished[:24]]
        mine = next((o for o in offer if o["polozka"]["obrazek"] == obrazek), None)
        if mine is None:
            job = self.store.get(obrazek.split("/")[0])
            mine = {"polozka": {"obrazek": obrazek}, "nazev": job["request"].get("prompt") or obrazek,
                    "nahled": f"/api/v2/jobs/{obrazek.replace('/', '/images/')}?w=256", "created": job["created"]}
            offer.insert(0, mine)
        together = [o for o in offer if abs(o["created"] - mine["created"]) <= 60]

        def order(o: dict) -> tuple:
            m = SERIES.search(o["nazev"])
            return (int(m[1]) if m else 0, o["created"])
        return {"nabidka": [{k: v for k, v in o.items() if k != "created"} for o in offer],
                "vybrane": [o["polozka"] for o in sorted(together, key=order)]}

    def _doc(self, info_id: str) -> dict:
        try:
            doc = self.infos.get(info_id)
        except InfoError as e:
            raise HTTPException(400, str(e)) from e
        if doc is None:
            raise HTTPException(404, f"infografika {info_id} neexistuje")
        return doc

    def _page(self, item: Polozka) -> dict:
        """Co stránka nese, bez renderu: `png` je cesta nebo funkce, která obraz vykreslí."""
        if item.obrazek:
            path = self.store.image_path(item.obrazek)
            if path is None:
                raise HTTPException(404, f"obrázek {item.obrazek} neexistuje")
            prov = self.prov(item.obrazek) or {}
            job = self.store.get(item.obrazek.split("/")[0])
            layers = path.with_suffix(".svg")
            doc = self.infos.get(prov["infographic"]) if prov.get("infographic") else None
            return {"zdroj": {"obrazek": item.obrazek}, "nazev": (job["request"].get("prompt") or path.stem)[:120], "png": path,
                    "svg": layers.read_text(encoding="utf-8") if prov.get("vectorcraft_svg") and layers.exists() else None,
                    "prov": prov, "doc": doc, "ai": (doc or {}).get("ai_note") or ai_note(prov),
                    "refs": [(path.parent / "refs" / f"ref-{i}.png", r) for i, r in enumerate(prov.get("refs") or [])]}
        if not item.infografika:
            raise HTTPException(400, "položka nemá obrázek ani infografiku")
        doc = self._doc(item.infografika)
        folder = self.infos._dir(doc["id"])
        exports = [n for n in doc["exports"] if n.endswith(".png")]
        newest = folder / "exports" / exports[0] if exports else None
        made = json.loads(newest.with_name(f"{newest.name}.json").read_text(encoding="utf-8"))["created"] if newest else ""
        page = {"zdroj": {"infografika": doc["id"]}, "nazev": doc.get("title") or doc["id"], "prov": None, "doc": doc,
                "ai": doc.get("ai_note"), "refs": []}
        if newest and (made >= doc["updated"] or not panels.is_panel_doc(doc)):
            manual = newest.with_suffix(".svg") if "-rucni-" in newest.name else newest.with_name(f"{newest.name}.vrstvy")
            return {**page, "png": newest, "svg": manual.read_text(encoding="utf-8") if manual.exists() else None}
        if not panels.is_panel_doc(doc):
            raise HTTPException(400, f"infografika „{page['nazev']}“ nemá export: nejdřív ji exportujte jako PNG")
        svg = panels.render_svg(doc, folder)
        w, h = canvas_size(doc["size"])
        return {**page, "png": lambda: rasterize(svg, w, h, "png"), "svg": svg}

    # -- náhled a balík -----------------------------------------------------------
    def preview(self, body: PohybIn) -> dict:
        """Co pojede s balíkem, nic se nezapíše ani nevykreslí."""
        pages = self._pages(body)
        out, notes = [], []
        for page in pages:
            layers = split_layers(page["svg"]) if page["svg"] else None
            doc = page["doc"]
            out.append({"nazev": page["nazev"], "vrstvy": layers is not None,
                        "objekty": len(layers["objekty"]) if layers else 0,
                        "popisky": sum(t["role"] == "popisek" for t in layers["texty"]) if layers else 0,
                        "panely": len(doc.get("panels") or []) if doc else 0})
            if layers is None:
                notes.append(f"„{page['nazev']}“ nemá vrstvy: pojede jen hotový obraz s textem")
        extras = self._extras(pages)
        if not any(page["doc"] for page in pages):
            notes.append("u obrázků z Knihovny GRAFIK nezná předlohy ani rešerši, zdroje jsou z vrstvy Zdroj")
        first = pages[0]
        w, h = self._size(first)
        return {"stranky": out, "predlohy": len(extras["predlohy"]), "reserse": [r["id"] for r in extras["reserse"]],
                "fakta": len(extras["fakta"]), "format": video_format(w, h), "upozorneni": notes}

    def _pages(self, body: PohybIn) -> list[dict]:
        if not body.polozky:
            raise HTTPException(400, "vyberte aspoň jednu stránku")
        if len(body.polozky) > MAX_PAGES:
            raise HTTPException(400, f"nejvýš {MAX_PAGES} stránek")
        return [self._page(item) for item in body.polozky]

    def _size(self, page: dict) -> tuple[int, int]:
        if page["doc"] and not page["prov"]:
            return canvas_size(page["doc"]["size"])
        with Image.open(page["png"]) as im:
            return im.size

    def _extras(self, pages: list[dict]) -> dict:
        """Předlohy, rešerše a fakta celé série, každá jen jednou."""
        predlohy, reserse, fakta, seen = [], [], [], set()

        def add_ref(ref_id: str, role: str, puvod: str = "knihovna předloh") -> None:
            meta = self.reflib.get(ref_id)
            if meta and ref_id not in seen:
                seen.add(ref_id)
                predlohy.append({"ref_id": ref_id, "soubor": self.reflib.image_path(ref_id), "role": role, "nazev": meta.get("title"),
                                 "autor": meta.get("author"), "licence": meta.get("license"), "stranka": meta.get("page_url"),
                                 "puvod": meta.get("origin") or puvod})
        for page in pages:
            for path, ref in page["refs"]:
                if path.exists() and str(path) not in seen:
                    seen.add(str(path))
                    predlohy.append({"ref_id": None, "soubor": path, "role": ref.get("role"), "nazev": ref.get("source"),
                                     "autor": None, "licence": ref.get("license"), "stranka": None, "puvod": "předloha generátoru"})
            doc = page["doc"]
            for panel in (doc or {}).get("panels") or []:
                source = panel.get("zdroj") or {}
                if source.get("ref_id"):
                    add_ref(source["ref_id"], f"obraz panelu {panel['id']}")
            wf_id = ((doc or {}).get("serie") or {}).get("wf")
            wf = self.workflows.get(wf_id) if wf_id else None
            if wf and wf.research_id and wf.research_id not in {r["id"] for r in reserse}:
                dossier = self.research_lib.dossier(wf.research_id)
                if dossier:
                    reserse.append({"id": wf.research_id, "dossier": self.research_lib._dir(wf.research_id) / "dossier.json", "tema": dossier.get("tema")})
                    for image in dossier.get("images") or []:
                        if image.get("ref_id"):
                            add_ref(image["ref_id"], image.get("role") or "rešerše", image.get("puvod") or "rešerše")
                    for row in self.research_lib.inspiration(wf.research_id):
                        if row.get("ref_id"):
                            add_ref(row["ref_id"], "inspirace", "pinterest")
                    used = {f for p in doc.get("panels") or [] for f in p.get("fakta") or []}
                    fakta += [{"id": f["id"], "tvrzeni": f.get("tvrzeni"), "stav": f.get("stav"), "reserse": wf.research_id,
                               "zdroje": [{"nazev": z.get("nazev"), "url": z.get("url"), "citace": z.get("citace")} for z in f.get("zdroje") or []]}
                              for f in dossier.get("facts") or [] if f.get("id") in used]
        return {"predlohy": predlohy, "reserse": reserse, "fakta": fakta}

    def build(self, body: PohybIn) -> tuple[Path, dict]:
        pages = self._pages(body)
        if body.format and body.format not in VIDEO_FORMATS:
            raise HTTPException(400, f"formát videa {body.format!r}: jen {', '.join(VIDEO_FORMATS)}")
        bundle_id = datetime.now().strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(2)
        folder = self.root / bundle_id
        folder.mkdir(parents=True)
        try:
            manifest = self._write(folder, bundle_id, body, pages)
        except Exception:
            shutil.rmtree(folder, ignore_errors=True)       # žádný poloviční balík
            raise
        return folder, manifest

    def _write(self, folder: Path, bundle_id: str, body: PohybIn, pages: list[dict]) -> dict:
        rel = lambda p: p.relative_to(folder).as_posix()     # noqa: E731
        written, notes = [], []
        for n, page in enumerate(pages, 1):
            out = folder / "stranky" / str(n)
            out.mkdir(parents=True)
            png = page["png"]() if callable(page["png"]) else page["png"].read_bytes()
            (out / "hotovo.png").write_bytes(png)
            with Image.open(out / "hotovo.png") as im:
                width, height = im.size
            entry = {"poradi": n, "nazev": page["nazev"], "zdroj": page["zdroj"], "rozmer": [width, height], "hotovo": rel(out / "hotovo.png"),
                     "vrstvy": None, "bez_textu": None, "pozadi": None, "objekty": [], "texty": [], "hlavni": None,
                     "dokument": None, "panely": [], "ai": page["ai"], "zdroje": None, "puvod": None}
            layers = split_layers(page["svg"]) if page["svg"] else None
            if layers:
                (out / "vrstvy.svg").write_text(page["svg"], encoding="utf-8")
                lw, lh = layers["rozmer"]
                shots = render_pngs([layers["bez_textu"], *(o["svg"] for o in layers["objekty"])], lw, lh)
                (out / "bez_textu.png").write_bytes(shots[0])
                (out / "objekty").mkdir()
                for i, (obj, shot) in enumerate(zip(layers["objekty"], shots[1:]), 1):
                    cut = _crop(shot)
                    if cut is None:
                        continue
                    target = out / "objekty" / f"{i:02d}-{slug(obj['id'])}.png"
                    target.write_bytes(cut[0])
                    entry["objekty"].append({"id": obj["id"], "soubor": rel(target), "rect": cut[1]})
                    if obj["texty"]:
                        notes.append(f"stránka {n}: objekt „{obj['id']}“ má vlastní texty ({obj['texty']}), v obrazu bez textu zůstaly")
                entry.update(vrstvy=rel(out / "vrstvy.svg"), bez_textu=rel(out / "bez_textu.png"), pozadi=layers["pozadi"], texty=layers["texty"])
                if [lw, lh] != [width, height]:
                    notes.append(f"stránka {n}: vrstvy mají {lw}×{lh}, obraz {width}×{height}; souřadnice platí pro vrstvy")
                credit = [r["text"] for t in layers["texty"] if t["role"] == "zdroj" for r in t["radky"]]
                entry["zdroje"] = " ".join(credit) or None
                biggest = max(entry["objekty"], key=lambda o: o["rect"][2] * o["rect"][3], default=None)
                entry["hlavni"] = biggest["rect"] if biggest else None
            else:
                notes.append(f"stránka {n} „{page['nazev']}“ nemá vrstvy: jen hotový obraz s textem")
            if page["prov"]:
                (out / "puvod.json").write_text(json.dumps(page["prov"], ensure_ascii=False, indent=2), encoding="utf-8")
                entry["puvod"] = rel(out / "puvod.json")
            doc = page["doc"]
            if doc:
                self._write_doc(doc, out, entry, rel)
            written.append(entry)
        extras = self._extras(pages)
        refs = []
        for i, ref in enumerate(extras["predlohy"], 1):
            source = Path(ref["soubor"])
            target = folder / "predlohy" / f"{i:02d}-{slug(ref['nazev'] or source.stem)}{source.suffix}"
            target.parent.mkdir(exist_ok=True)
            shutil.copy2(source, target)
            refs.append({**ref, "soubor": rel(target)})
        research = []
        for r in extras["reserse"]:
            target = folder / "reserse" / r["id"] / "dossier.json"
            target.parent.mkdir(parents=True)
            shutil.copy2(r["dossier"], target)
            research.append({"id": r["id"], "tema": r["tema"], "dossier": rel(target)})
        if not any(page["doc"] for page in pages):
            notes.append("u obrázků z Knihovny GRAFIK nezná předlohy ani rešerši, zdroje jsou z vrstvy Zdroj")
        manifest = {"format": FORMAT, "verze": VERZE, "id": bundle_id, "vytvoreno": datetime.now().isoformat(timespec="seconds"),
                    "odkud": "GRAFIK", "nazev": body.nazev.strip() or written[0]["nazev"], "sdeleni": body.sdeleni.strip(),
                    "format_videa": body.format or video_format(*written[0]["rozmer"]),
                    "stranky": written, "predlohy": refs, "reserse": research, "fakta": extras["fakta"], "upozorneni": notes}
        (folder / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return manifest

    def _write_doc(self, doc: dict, out: Path, entry: dict, rel) -> None:
        """Dokument s panely: info.json, panely s body.json a vrstvami renderu, u modelu GLB."""
        src = self.infos._dir(doc["id"])
        (out / "dokument.json").write_text(json.dumps({k: v for k, v in doc.items() if k not in ("exports", "in_library")}, ensure_ascii=False, indent=2), encoding="utf-8")
        entry["dokument"] = rel(out / "dokument.json")
        entry["zdroje"] = doc.get("sources") or entry["zdroje"]
        if not panels.is_panel_doc(doc):
            return
        if (src / "panely").is_dir():
            shutil.copytree(src / "panely", out / "panely")
        hero = min((p for p in doc["panels"] if p["typ"] == "obraz"), key=lambda p: p["poradi"], default=None)
        entry["hlavni"] = [round(v) for v in hero["rect"]] if hero else entry["hlavni"]
        for panel in doc["panels"]:
            folder = out / "panely" / panel["id"]
            item = {k: panel[k] for k in ("id", "typ", "nazev", "rect", "poradi", "labels", "items", "fakta", "zdroj") if k in panel}
            if (folder / "obraz.png").is_file():
                item.update(obraz=rel(folder / "obraz.png"), vrstvy=[rel(p) for p in sorted(folder.glob("vrstva-*.png"))])
            if (folder / "body.json").is_file():
                item["body"] = rel(folder / "body.json")
            source = panel.get("zdroj") or {}
            if source.get("model_id"):
                try:
                    model = self.model_dir(source)
                except Exception:       # noqa: BLE001  model smazaný nebo neplatné id: panel jede bez GLB
                    model = None
                glb = model / "model.glb" if model else None
                if glb and glb.is_file() and glb.stat().st_size <= MAX_MODEL_BYTES:
                    target = out / "modely" / f"{panel['id']}.glb"
                    target.parent.mkdir(exist_ok=True)
                    shutil.copy2(glb, target)
                    item["model"] = rel(target)
                    if (model / "model.json").is_file():
                        shutil.copy2(model / "model.json", target.with_suffix(".json"))
            entry["panely"].append(item)

    # -- POHYB --------------------------------------------------------------------
    def pohyb_running(self) -> bool:
        try:
            return httpx.get(f"{self.s.pohyb_url}/api/health", timeout=3).status_code == 200
        except httpx.HTTPError:
            return False

    def send(self, folder: Path) -> dict:
        try:
            r = httpx.post(f"{self.s.pohyb_url}/api/predavky", files={"balik": (f"{folder.name}.zip", zip_dir(folder), "application/zip")}, timeout=180)
        except httpx.HTTPError as e:
            raise HTTPException(502, f"POHYB balík nepřevzal ({e}). Balík zůstal v library/pohyb/{folder.name}.") from e
        if r.status_code not in (200, 201):
            detail = (r.json() if r.headers.get("content-type", "").startswith("application/json") else {}).get("detail") or r.text[:300]
            raise HTTPException(502, f"POHYB balík odmítl (HTTP {r.status_code}: {detail}). Balík zůstal v library/pohyb/{folder.name}.")
        job = r.json()
        sent = {**job, "url": f"{self.s.pohyb_url}/#{job['id']}", "odeslano": datetime.now().isoformat(timespec="seconds")}
        (folder / "odeslano.json").write_text(json.dumps(sent, ensure_ascii=False, indent=2), encoding="utf-8")
        return sent


def register(app: FastAPI, bundler: Bundler) -> None:
    @app.get("/api/v2/pohyb/stranky")
    def pohyb_pages(obrazek: str | None = None, infografika: str | None = None):
        return {**bundler.candidates(obrazek, infografika), "pohyb_bezi": bundler.pohyb_running(), "pohyb_url": bundler.s.pohyb_url}

    @app.post("/api/v2/pohyb/nahled")
    def pohyb_preview(body: PohybIn):
        return bundler.preview(body)

    @app.post("/api/v2/pohyb", status_code=201)
    def pohyb_send(body: PohybIn):
        if not bundler.pohyb_running():
            raise HTTPException(503, f"POHYB neběží ({bundler.s.pohyb_url}). Spusťte ho (start-pohyb.bat) a pošlete znovu, nic se nezapsalo.")
        folder, manifest = bundler.build(body)
        sent = bundler.send(folder)
        return {"id": manifest["id"], "slozka": str(folder), "stranky": len(manifest["stranky"]), "upozorneni": manifest["upozorneni"], "pohyb": sent}
