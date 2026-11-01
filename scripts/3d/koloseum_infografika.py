# Infographic of the Colosseum as a panel document, through the Engine API, free:
#   python scripts/3d/koloseum_infografika.py [--engine http://127.0.0.1:8300] [--model koloseum --version v1] [--tema ruda] [--knihovna]
# Builds the model from scripts/3d/dily/koloseum.json when it is not in the library, renders the views (new renders/r-<n>, nothing is
# overwritten), creates a new document and exports it. Every sentence on the page has its source in docs/spikes/2026-11-01-koloseum.md.
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SPEC = REPO / "scripts" / "3d" / "dily" / "koloseum.json"
DECOR = ("sochy", "lide", "plachty", "zdvihadla")
CUTS = ("arkady", "vyrez", "ochoz", "schodiste", "sachty", "otvory", "dutina")
UNDER = ("hypogeum", "stred_", "bok_", "osa_", "krivka", "volne_", "zuby", "pavlac", "tramy", "arena_", "poklopy", "zaklad")
UNDER_DECOR = ("vytahy", "lide_chodba", "lide_pavlac")
LAYERS = {"okoli": "Terasa a terén", "podzemi": "Podzemí a aréna", "stavba": "Stavba v řezu", "ozdoby": "Sochy, lidé, plachty"}
ARENA_OPEN = [{"dily": ["arena_pisek", "arena_podlaha", "poklopy_stred", "poklopy_bok"], "azimut": [-225, -25]}, {"dily": ["tramy"], "azimut": [-205, -45]}]
SEATS = [[-4.0, 29.1, 5.8], [-4.6, 36.6, 10.5], [-6.0, 52.5, 22.0], [-7.1, 64.5, 36.0], [-7.6, 70.5, 41.5]]     # podium, primum, immum, summum, dřevěná galerie
FIGURE_Y = 1832
POLLICE_VERSO = "20261101-144717-b5c4"      # Gérôme 1872, public domain, knihovna předloh
# Obrázky z lokálního FLUX (0 USD) vybrané okem. Id místo zadání, protože nový běh dá jiný obrázek; zadání a semínka v docs/spikes/2026-11-01-koloseum.md.
OBRAZY = {"retiarius": "20261101-183006-de53a6/0",
          "secutor": "20261101-183246-10e8ba/0",
          "murmillo": "20261101-183755-49ed04/0",
          "thraex": "20261101-184008-de1acf/0",
          "hoplomachus": "20261101-184200-ce8371/0",
          "provocator": "20261101-184437-049d19/0",
          "palec_nahoru": "20261101-181031-d46f5e/0",
          "palec_dolu": "20261101-190456-0de809/0",
          "palec_pest": "20261101-183937-f0d4f3/0"}


def groups_of(spec: dict) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {k: [] for k in LAYERS}
    for part in spec["dily"]:
        name, kind = part["nazev"], part["typ"]
        if kind in CUTS:
            continue
        if part.get("okoli") or name == "lide_venku":
            out["okoli"].append(name)
        elif name.startswith(UNDER) or name in UNDER_DECOR:
            out["podzemi"].append(name)
        elif kind in DECOR:
            out["ozdoby"].append(name)
        else:
            out["stavba"].append(name)
    return out


def renders(spec: dict) -> dict[str, dict]:
    """Co se renderuje pro který panel. Zdarma, na GPU."""
    return {"hlavni": {"pohled": "ctvrt", "res": [2400, 1500], "samples": 128, "rez": "cerna", "sokl": {"z": 1.2, "pas": 12}, "odkryv": ARENA_OPEN, "kamera": {"el": 27}, "skupiny": groups_of(spec)}}


def label(text: str, small, kotva, x: float, y: float, align: str = "left", **extra) -> dict:
    return {"text": text, "small": small if isinstance(small, list) else [small], "kotva": kotva, "pos": [x, y], "align": align, **extra}


def gladiator(key: str, name: str, x: float, poradi: int) -> dict:
    return {"id": f"gl_{key}", "typ": "obraz", "poradi": poradi, "nazev": name, "rect": [x, FIGURE_Y, 240, 295], "zdroj": {"obraz": OBRAZY[key], "vyriznout": True, "stin": True}}


def gesture(key: str, name: str, y: float, poradi: int) -> dict:
    return {"id": f"palec_{key}", "typ": "obraz", "poradi": poradi, "nazev": name, "rect": [985, y, 195, 130], "zdroj": {"obraz": OBRAZY[f"palec_{key}"], "vyriznout": True}}


def page(sources: dict[str, dict]) -> dict:
    """Dokument, `sources` dodá `zdroj` renderů. Každý panel odpovídá na otázku, kterou hlavní model nezodpoví. Věty a čísla mají zdroj v docs/spikes/2026-11-01-koloseum.md."""
    return {
        "title": "Koloseum",
        "subtitle": "Flaviovský amfiteátr, Řím, 70–80 n. l.\nStavba a hra o život",
        "size": "1600x2400",
        "accent": "#dcb062",
        "nadpis": {"x": 50, "y": 96},
        "sources": ("Wikipedia: Colosseum (en), Koloseum (cs), Colosseo (it), Kolosseum (de), Gladiator (en), Pollice verso (en), List of Roman gladiator types (en); Cavillargues medallion (en); Wikidata Q10285; A. Corbeill, Nature Embodied (2004) a v časopise Time (2017); "
                    "G. Ville podle hesla Gladiator; Rosengarten, A Handbook of Architectural Styles, obr. 225; půdorys Amphitheatrum Flavium (Commons); rekonstrukční řez z knihy dodaný editorem. "
                    "Hloubka podzemí a rozměry chodeb jsou odhad, řád metrů. Plachty a lidé jsou ukázka, jejich rozmístění je vymyšlené. Gladiátoři jsou ilustrace podle popisu výbavy, ne nálezy, ruka je ilustrace gesta."),
        "panels": [
            {"id": "hlavni", "typ": "obraz", "poradi": 1, "nazev": "Hlavní řez", "rect": [60, 95, 1480, 925], "zdroj": sources["hlavni"], "vrstvy": LAYERS, "fakta": ["f1", "f2", "f19", "f20", "f37"], "labels": [
                label("Velárium", ["plátno na síti lan", "zde jen ukázka"], [87.1, 15.1, 51.7], 1170, 110),
                label("240 stožárů", "nesly lana velária", [81.9, -39.1, 55.0], 1375, 255),
                label("Sochy v arkádách", "ve 2. a 3. patře", [72.55, -47.72, 15.0], 1375, 540),
                label("80 vstupů", "76 pro běžné diváky", [39.73, -70.46, 3.0], 1375, 719),
                label("Sloupky 18 m", "od zdi, účel nejistý", [32.34, -91.67, 3.0], 1375, 778),
                label("Aréna 83–87 × 48–55 m", "písek na dřevě", [12.0, 16.0, 0.12], 825, 615),
                label("Hypogeum", ["dvě patra chodeb a klecí", "80 šachet s výtahy do arény"], [-12.0, 2.0, -3.0], 763, 821),
                label("Základ z tufu", "7 až 13 m podle zdroje", "k_zaklad", 578, 895),
            ], "znacky": [{"text": str(i + 1), "kotva": point} for i, point in enumerate(SEATS)]},
            {"id": "mista", "typ": "fakta", "poradi": 2, "nazev": "Kdo kde seděl", "titulek": {"text": "Kdo kde seděl", "x": 50, "y": 214}, "rect": [50, 222, 240, 135], "smer": "sloupec", "size": 21, "small_size": 21, "krok": 27, "fakta": ["f32", "f33", "f34", "f44"], "items": [
                {"value": "1", "text": "senátoři"}, {"value": "2", "text": "jezdci"}, {"value": "3", "text": "bohatí občané"}, {"value": "4", "text": "chudí občané"}, {"value": "5", "text": "chudina, otroci, ženy"}]},
            {"id": "cisla", "typ": "fakta", "poradi": 17, "nazev": "Čísla", "rect": [50, 1018, 1500, 75], "size": 34, "small_size": 20, "fakta": ["f3", "f4", "f5", "f6", "f7"], "items": [
                {"value": "187–189 m", "text": "délka"}, {"value": "155–156 m", "text": "šířka"}, {"value": "48 m", "text": "výška"}, {"value": "24 000 m²", "text": "plocha"}, {"value": "50–80 tisíc", "text": "míst podle zdroje"}]},
            {"id": "scena", "typ": "obraz", "poradi": 3, "nazev": "Pollice Verso", "titulek": {"text": "Milost, nebo smrt?", "x": 50, "y": 1132}, "rect": [50, 1146, 900, 605], "zdroj": {"ref_id": POLLICE_VERSO}, "labels": [
                label("Poražený zvedá prsty", "žádá o milost, ad digitum", [1010, 975, 0], 610, 1590),
                label("Vítěz čeká na verdikt", "sám nerozhoduje", [640, 640, 0], 300, 1520, "right"),
                label("Císař v lóži", "rozhodoval, řídil se davem", [545, 440, 0], 281, 1440, "right"),
                label("Vestálky a palec dolů", "tenhle obraz ho rozšířil", [1470, 345, 0], 706, 1450),
            ], "pod": {"small": "J.-L. Gérôme: Pollice Verso, 1872. U opravdového boje stál i rozhodčí, na obraze chybí."}},
            {"id": "palec", "typ": "text", "poradi": 4, "nazev": "Palec", "titulek": {"text": "Palec nahoru, nebo dolů?", "x": 985, "y": 1132}, "rect": [985, 1142, 575, 85], "size": 24, "small_size": 20, "krok": 85, "items": [
                {"value": "Pollice verso", "text": "znamená jen „s otočeným palcem“. Kam se otáčel, žádný římský text přesně neříká."}]},
            gesture("nahoru", "Palec nahoru", 1222, 6),
            gesture("dolu", "Palec dolů", 1362, 7),
            gesture("pest", "Palec v pěsti", 1502, 8),
            {"id": "palec_vyklad", "typ": "text", "poradi": 5, "nazev": "Palec po řadě", "rect": [1195, 1228, 365, 400], "size": 24, "small_size": 20, "sirka": 38, "krok": 140, "items": [
                {"value": "Palec nahoru: smrt", "text": "Tasit meč a zabít. Shoduje se A. Corbeill i populární výklad."},
                {"value": "Palec dolů: spor", "text": "Gérômův obraz (1872): smrt. Populární výklad: meč do pochvy, život. Doklad z Říma nemá ani jeden."},
                {"value": "Palec v pěsti: milost", "text": "Meč zůstává v pochvě. Doklad: medailon z Cavillargues s nápisem STANTES MISSI."}]},
            {"id": "pocty", "typ": "fakta", "poradi": 16, "nazev": "Kolik jich umíralo", "rect": [985, 1650, 575, 90], "size": 30, "small_size": 19, "sirka": 30, "items": [
                {"value": "1 z 5", "text": "poražených zemřel, později 1 ze 4"}, {"value": "19 ze 100", "text": "zemřelo ze všech, kdo vstoupili do arény (G. Ville)"}]},
            gladiator("retiarius", "Retiarius", 50, 10),
            gladiator("secutor", "Secutor", 300, 11),
            gladiator("murmillo", "Murmillo", 550, 12),
            gladiator("thraex", "Thraex", 800, 13),
            gladiator("hoplomachus", "Hoplomachus", 1050, 14),
            gladiator("provocator", "Provocator", 1300, 15),
            {"id": "druhy", "typ": "fakta", "poradi": 9, "nazev": "Druhy gladiátorů", "titulek": {"text": "Šest druhů gladiátorů a kdo proti komu", "x": 50, "y": 1826}, "rect": [50, 2130, 1500, 150], "size": 26, "small_size": 19, "sirka": 28, "items": [
                {"value": "Retiarius", "text": "Trojzubec a síť, bez helmy. Proti němu secutor."},
                {"value": "Secutor", "text": "Hladká helma, ať se nezachytí v síti. Proti němu retiarius."},
                {"value": "Murmillo", "text": "Helma s hřebenem, vysoký štít. Proti němu thraex, hoplomachus."},
                {"value": "Thraex", "text": "Zahnutý meč, malý štít, gryf na helmě. Proti němu murmillo, hoplomachus."},
                {"value": "Hoplomachus", "text": "Kopí, meč, malinký kulatý štít. Proti němu murmillo, thraex."},
                {"value": "Provocator", "text": "Hledí a jediný s plátem na hrudi. Proti němu zase provocator."}]},
        ],
    }


class Api:
    def __init__(self, base: str):
        self.base = base.rstrip("/")

    def call(self, method: str, path: str, body=None, timeout: int = 600):
        req = urllib.request.Request(self.base + path, data=None if body is None else json.dumps(body).encode("utf-8"), method=method, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise SystemExit(f"{method} {path}: {e.code} {e.read().decode('utf-8', 'replace')[:800]}") from e

    def wait(self, job_id: str, timeout: int = 1800) -> dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            job = self.call("GET", f"/api/v2/jobs/{job_id}")
            if job["status"] == "done":
                return job
            if job["status"] in ("failed", "cancelled"):
                raise SystemExit(f"úloha {job_id}: {job['status']} {job.get('error')}")
            time.sleep(3)
        raise SystemExit(f"úloha {job_id} nedoběhla")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = sys.argv[1:]
    opt = lambda name, default: args[args.index(name) + 1] if name in args else default
    api = Api(opt("--engine", "http://127.0.0.1:8300"))
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    model, version = opt("--model", None), opt("--version", None)
    if model is None:
        built = api.call("POST", "/api/v2/models3d/parts", {"title": "Koloseum", "spec": spec, "caller": "koloseum-infografika"})
        api.wait(built["job_id"])
        model, version = built["model_id"], built["version"]
        print("model", model, version)
    sources = {}
    for panel, request in renders(spec).items():
        started = api.call("POST", f"/api/v2/models3d/{model}/{version}/render", {**request, "caller": "koloseum-infografika"})
        job = api.wait(started["job_id"])
        sources[panel] = {"model_id": model, "version": version, "render": job["result"]["id"]}
        print(panel, job["result"]["id"], job["result"].get("seconds"), "s", flush=True)
    doc = api.call("POST", "/api/v2/infographics/panels", {**page(sources), "template": opt("--tema", "dark")})
    print("dokument", doc["id"], doc["ai_note"])
    for check in api.call("GET", f"/api/v2/infographics/{doc['id']}/kontrola"):
        print("ok" if check["ok"] else " !", check["text"])
    for fmt in ("png", "pdf", "svg"):
        print(api.call("POST", f"/api/v2/infographics/{doc['id']}/export", {"format": fmt}))
    png = next(n for n in api.call("GET", f"/api/v2/infographics/{doc['id']}")["exports"] if n.endswith(".png"))
    if "--knihovna" in args:
        print(api.call("POST", f"/api/v2/infographics/{doc['id']}/exports/{png}/library"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
