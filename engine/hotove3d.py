"""Hotové 3D modely zdarma, než se generuje: sklad na D: (`ngm_shared.sklad3d`), Smithsonian 3D a Sketchfab.

Sklad: hledá se nejdřív, lokálně a bez sítě (Poly Haven CC0, Smithsonian CC0 stažený dopředu); naše vlastní
modely (`nase`) ve skladu nabízené nejsou, ty už jsou v knihovně.

Smithsonian: hledání v 3d-api.si.edu bez klíče, licence z Open Access API (`usage.access` u balíčku);
klíč `SI_API_KEY` z api.data.gov, jinak `DEMO_KEY` s nízkým hodinovým limitem, proto jen při stažení.
Sketchfab: hledání bez účtu, stažení jen s `SKETCHFAB_API_TOKEN` (token účtu operátora).
Do knihovny jde jen CC0 a CC BY. NC a ND nejdou použít komerčně, ShareAlike by vnutil licenci
odvozenému obrazu; takový model zůstane v nabídce jen s odkazem jako předloha.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request

from engine.keys import get_key
from engine.reflib import UA
from ngm_shared import sklad3d
from ngm_shared.sklad import SkladError

SI_SEARCH = "https://3d-api.si.edu/api/v1.0/content/file/search"
SI_OA = "https://api.si.edu/openaccess/api/v1.0/search"
SI_VIEWER = "https://3d-api.si.edu/voyager/"
SF_API = "https://api.sketchfab.com/v3"
MAX_BYTES = 200 * 1024 * 1024
SI_QUALITY = ("Medium", "High", "Low")  # Medium: 150k trojúhelníků, textura 2048


class Hotove3dError(ValueError):
    pass


def licence_ok(label: str) -> tuple[bool, str | None]:
    """Smí model do knihovny? Vrací (ano/ne, důvod odmítnutí)."""
    if re.search(r"NonCommercial|\bNC\b", label, re.I):
        return False, "nekomerční licence (NC), NG ji použít nesmí"
    if re.search(r"NoDeriv|\bND\b", label, re.I):
        return False, "licence zakazuje úpravy (ND)"
    if re.search(r"ShareAlike|\bSA\b", label, re.I):
        return False, "ShareAlike: odvozený obraz by musel mít stejnou licenci; jen předloha"
    if re.match(r"(CC0|CC Attribution|CC BY|public domain)", label, re.I):
        return True, None
    return False, f"licence „{label or 'neuvedená'}“ není CC0 ani CC BY"


def _get(url: str, params: dict | None = None, headers: dict | None = None) -> bytes:
    """urllib, ne httpx: Sketchfab na httpx odpovídá 202 s prázdným tělem (ochrana proti botům, 2026-11-03)."""
    full = url + ("?" + urllib.parse.urlencode(params) if params else "")
    host = url.split("/")[2]
    try:
        with urllib.request.urlopen(urllib.request.Request(full, headers={**UA, **(headers or {})}), timeout=60) as r:
            if r.status != 200:
                raise Hotove3dError(f"{host} vrátil {r.status}")
            return r.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as e:
        raise Hotove3dError(f"{host} vrátil {e.code}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise Hotove3dError(f"{host} nedostupný: {e}") from e


def _json(url: str, params: dict | None = None, headers: dict | None = None) -> dict:
    data = _get(url, params, headers)
    try:
        return json.loads(data)
    except ValueError as e:
        raise Hotove3dError(f"{url.split('/')[2]} nevrátil JSON") from e


# -- Smithsonian ----------------------------------------------------------------------

def search_si(q: str, limit: int = 12) -> list[dict]:
    rows = _json(SI_SEARCH, {"q": q}).get("rows", [])
    found: dict[str, dict] = {}
    for row in rows:
        pkg = row["content"]["model_url"]
        found.setdefault(pkg, {"zdroj": "smithsonian", "id": pkg.split(":", 1)[-1], "nazev": row["title"], "autor": "Smithsonian Institution",
                               "licence": "CC0 (ověří se při stažení)", "stranka": SI_VIEWER + pkg, "nahled": None,
                               "lze_stahnout": True, "proc_ne": None})
        if len(found) >= limit:
            break
    return list(found.values())


def si_record(package_id: str) -> dict:
    """Licence a údaje záznamu z Open Access API; balíček bez CC0 se nestáhne."""
    pkg = f"3d_package:{package_id}"
    key = get_key("SI_API_KEY", "API_DATA_GOV_KEY") or "DEMO_KEY"
    data = _json(SI_OA, {"q": f'"{package_id}"', "rows": 5, "api_key": key})
    for row in data.get("response", {}).get("rows", []):
        dnr = row.get("content", {}).get("descriptiveNonRepeating", {})
        for m in dnr.get("online_media", {}).get("media", []):
            if m.get("id") == pkg:
                return {"nazev": row.get("title"), "licence": (m.get("usage") or {}).get("access"),
                        "autor": f"Smithsonian Institution, {dnr.get('data_source') or row.get('unitCode')}",
                        "stranka": dnr.get("record_link") or SI_VIEWER + pkg}
    raise Hotove3dError(f"Smithsonian: záznam balíčku {package_id} nenalezen, licenci nejde ověřit")


def fetch_si(package_id: str) -> tuple[bytes, dict]:
    rec = si_record(package_id)
    if rec["licence"] != "CC0":
        raise Hotove3dError(f"Smithsonian: balíček má licenci „{rec['licence']}“, ne CC0")
    rows = _json(SI_SEARCH, {"q": package_id}).get("rows", [])
    glbs = {r["content"]["quality"]: r["content"]["uri"] for r in rows
            if r["content"]["model_url"].endswith(package_id) and r["content"]["file_type"] == "glb"}
    url = next((glbs[q] for q in SI_QUALITY if q in glbs), None)
    if not url:
        raise Hotove3dError("Smithsonian: balíček nemá GLB")
    return _download(url), {**rec, "soubor": url, "licence": "CC0"}


# -- Sketchfab ------------------------------------------------------------------------

def _sf_candidate(row: dict) -> dict:
    label = (row.get("license") or {}).get("label") or ""
    ok, why = licence_ok(label)
    images = sorted((row.get("thumbnails") or {}).get("images", []), key=lambda i: i.get("width") or 0)
    thumb = next((i["url"] for i in images if (i.get("width") or 0) >= 256), images[-1]["url"] if images else None)
    return {"zdroj": "sketchfab", "id": row["uid"], "nazev": row["name"], "autor": (row.get("user") or {}).get("displayName"),
            "licence": label, "stranka": row.get("viewerUrl"), "nahled": thumb, "trojuhelniky": row.get("faceCount"),
            "lze_stahnout": ok, "proc_ne": why}


def search_sf(q: str, limit: int = 24) -> list[dict]:
    rows = _json(f"{SF_API}/search", {"type": "models", "q": q, "downloadable": "true", "count": limit}).get("results", [])
    return [_sf_candidate(r) for r in rows]


def fetch_sf(uid: str) -> tuple[bytes, dict]:
    token = get_key("SKETCHFAB_API_TOKEN")
    if not token:
        raise Hotove3dError("Sketchfab: stažení potřebuje SKETCHFAB_API_TOKEN (token účtu operátora v .env)")
    cand = _sf_candidate(_json(f"{SF_API}/models/{uid}"))  # licence znovu těsně před stažením
    if not cand["lze_stahnout"]:
        raise Hotove3dError(f"Sketchfab: {cand['proc_ne']}")
    links = _json(f"{SF_API}/models/{uid}/download", headers={"Authorization": f"Token {token}"})
    glb = links.get("glb")
    if not glb:
        raise Hotove3dError("Sketchfab: model nemá GLB ke stažení (jen glTF v zipu)")
    if (glb.get("size") or 0) > MAX_BYTES:
        raise Hotove3dError(f"Sketchfab: GLB má {glb['size'] / 1e6:.0f} MB, strop je {MAX_BYTES / 1e6:.0f} MB")
    return _download(glb["url"]), {k: cand[k] for k in ("nazev", "autor", "licence", "stranka")}


# -- sklad na D: (DECISIONS 2026-11-05) ------------------------------------------------

SKLAD_NAHLED = "/api/v2/models3d/sklad/nahled?id="


def search_sklad(q: str, limit: int = 24) -> list[dict]:
    try:
        nalez = sklad3d.hledej(q, druh="model", bez_zdroje=("nase",), limit=limit)
    except (SkladError, OSError) as e:
        raise Hotove3dError(f"sklad {sklad3d.dir3d()} nedostupný: {e}") from e
    return [{"zdroj": "sklad", "id": z["id"], "nazev": z["nazev"], "autor": z["autor"], "licence": z["licence"],
             "stranka": z["stranka"], "nahled": SKLAD_NAHLED + urllib.parse.quote(z["id"]) if z.get("nahled") else None,
             "trojuhelniky": z.get("trojuhelniky"), "rozmery_m": z.get("rozmery_m"), "lze_stahnout": True, "proc_ne": None}
            for z in nalez]


def fetch_sklad(id_: str) -> tuple[bytes, dict]:
    try:
        z = sklad3d.zaznam(id_)
        if z["druh"] != "model" or z["zdroj"] == "nase":
            raise Hotove3dError(f"sklad: {id_} není cizí model")
        ok, why = licence_ok(z["licence"])
        if not ok:
            raise Hotove3dError(f"sklad: {why}")
        glb = sklad3d.cesta(z).read_bytes()
    except (SkladError, OSError) as e:
        raise Hotove3dError(f"sklad: {e}") from e
    if len(glb) > MAX_BYTES:
        raise Hotove3dError(f"GLB má {len(glb) / 1e6:.0f} MB, strop je {MAX_BYTES / 1e6:.0f} MB")
    return glb, {"nazev": z["nazev"], "autor": z["autor"], "licence": z["licence"], "stranka": z["stranka"],
                 "sklad_id": z["id"], "puvodni_zdroj": z["zdroj"]}


# -- společné -------------------------------------------------------------------------

def _download(url: str) -> bytes:
    data = _get(url)
    if len(data) > MAX_BYTES:
        raise Hotove3dError(f"GLB má {len(data) / 1e6:.0f} MB, strop je {MAX_BYTES / 1e6:.0f} MB")
    return data


def search(q: str) -> dict:
    """Kandidáti ze skladu, pak z obou webových zdrojů; výpadek jednoho zdroje nezastaví ostatní."""
    out, errors = [], []
    for name, fn in (("sklad", search_sklad), ("smithsonian", search_si), ("sketchfab", search_sf)):
        try:
            out += fn(q)
        except Hotove3dError as e:
            errors.append(f"{name}: {e}")
    return {"kandidati": out, "chyby": errors, "sketchfab_stazeni": bool(get_key("SKETCHFAB_API_TOKEN"))}


def fetch(zdroj: str, model_id: str) -> tuple[bytes, dict]:
    if zdroj == "smithsonian":
        glb, info = fetch_si(model_id)
    elif zdroj == "sketchfab":
        glb, info = fetch_sf(model_id)
    elif zdroj == "sklad":
        glb, info = fetch_sklad(model_id)
    else:
        raise Hotove3dError(f"neznámý zdroj {zdroj}")
    jmeno = {"smithsonian": "Smithsonian 3D", "sketchfab": "Sketchfab"}.get(zdroj) or f"Sklad ({info['puvodni_zdroj']})"
    info["origin"] = f"{jmeno}: {info['nazev']}, {info['autor']}, {info['licence']}, {info['stranka']}"
    return glb, info
