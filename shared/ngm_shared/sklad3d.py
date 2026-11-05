"""3D část skladu (fáze F3–F5 návrhu STOPA `outputs/2026-11-04-sklad-namety-a-3d-modely.md`, DECISIONS 2026-11-05).

    NGM_SKLAD/3d/
      index.json                               jeden index všech modelů a HDRI (hledá `hledej`)
      polyhaven/models/<slug>/model.glb        Poly Haven (CC0), glTF s texturami 1k složený do jednoho GLB
      polyhaven/hdri/<slug>/<slug>_1k.hdr      Poly Haven HDRI (CC0)
      smithsonian/<balicek>/model.glb          Smithsonian 3D (CC0 podle Open Access), stahuje GRAFIK
      nase/<model>/<verze>/                    kopie našeho modelu z GRAFIK library/3d po kontrole (zaškrtnutí)
      */puvod.json                             u každé položky: odkud, autor, licence, kdy

Sklad je jen zásoba. Do výroby jde model přes GRAFIK `library/3d` (převzetí s licencí), POHYB a KLAPKA ho
berou odtud; POHYB si ze skladu bere jen HDRI. Do skladu jde jen CC0 a CC BY (`licence_ok`).
Index se staví z `puvod.json` na disku, takže ho jde kdykoli postavit znovu (`sestav_index`).

    python -m ngm_shared.sklad stahni polyhaven [--limit 20]
    python -m ngm_shared.sklad stahni hdri [--limit 20]
    python -m ngm_shared.sklad hledej3d amphora [--druh model]
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import struct
from datetime import datetime
from pathlib import Path
from typing import Callable

from ngm_shared import sklad
from ngm_shared.sklad import SkladError, _bez_diakritiky, _get, _write_atomic, _SLOVO

PH_API = "https://api.polyhaven.com"
PH_STRANKA = "https://polyhaven.com/a/"
ROZLISENI = "1k"  # operátor 2026-11-04: textury 1k
DRUHY = ("model", "hdri")


def dir3d() -> Path:
    return sklad.root() / "3d"


def licence_ok(label: str) -> tuple[bool, str | None]:
    """Stejné pravidlo jako GRAFIK `engine/hotove3d.py` (DECISIONS 2026-11-03): jen CC0 a CC BY."""
    if re.search(r"NonCommercial|\bNC\b", label, re.I):
        return False, "nekomerční licence (NC)"
    if re.search(r"NoDeriv|\bND\b", label, re.I):
        return False, "licence zakazuje úpravy (ND)"
    if re.search(r"ShareAlike|\bSA\b", label, re.I):
        return False, "ShareAlike"
    if re.match(r"(CC0|CC Attribution|CC BY|public domain)", label, re.I):
        return True, None
    return False, f"licence „{label or 'neuvedená'}“ není CC0 ani CC BY"


def _json(url: str) -> dict:
    try:
        return json.loads(_get(url))
    except ValueError as e:
        raise SkladError(f"{url}: nevrátil JSON") from e


def _ted() -> str:
    return datetime.now().isoformat(timespec="seconds")


# -- glTF → GLB -----------------------------------------------------------------------

_MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def gltf_na_glb(gltf: bytes, soubory: dict[str, bytes]) -> bytes:
    """Složí glTF s externími buffery a obrázky (`soubory`: cesta z uri → obsah) do jednoho GLB.

    Všechny buffery i obrázky jdou za sebou do jednoho BIN bloku (zarovnání na 4 B)."""
    doc = json.loads(gltf)
    blob = bytearray()

    def pridej(data: bytes) -> int:
        blob.extend(b"\0" * (-len(blob) % 4))
        start = len(blob)
        blob.extend(data)
        return start

    def obsah(uri: str) -> bytes:
        if uri not in soubory:
            raise SkladError(f"glTF odkazuje na {uri}, ale soubor chybí")
        return soubory[uri]

    zacatky = [pridej(obsah(b["uri"])) for b in doc.get("buffers", [])]
    for bv in doc.get("bufferViews", []):
        bv["byteOffset"] = bv.get("byteOffset", 0) + zacatky[bv.get("buffer", 0)]
        bv["buffer"] = 0
    for img in doc.get("images", []):
        if "uri" in img:
            uri = img.pop("uri")
            data = obsah(uri)
            doc.setdefault("bufferViews", []).append({"buffer": 0, "byteOffset": pridej(data), "byteLength": len(data)})
            img["bufferView"] = len(doc["bufferViews"]) - 1
            img.setdefault("mimeType", _MIME.get(Path(uri).suffix.lower(), "image/jpeg"))
    blob.extend(b"\0" * (-len(blob) % 4))
    doc["buffers"] = [{"byteLength": len(blob)}]
    js = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    js += b" " * (-len(js) % 4)
    telo = struct.pack("<II", len(js), 0x4E4F534A) + js + struct.pack("<II", len(blob), 0x004E4942) + bytes(blob)
    return struct.pack("<4sII", b"glTF", 2, 12 + len(telo)) + telo


# -- Poly Haven -----------------------------------------------------------------------

def _autor(asset: dict) -> str:
    return ", ".join((asset.get("authors") or {}).keys()) or "Poly Haven"


def _ph_zaznam(slug: str, asset: dict, druh: str, soubor: Path, nahled: Path | None, bajtu: int) -> dict:
    rozmery = asset.get("dimensions")
    return {"id": f"polyhaven/{slug}", "zdroj": "polyhaven", "druh": druh, "nazev": asset.get("name") or slug,
            "kategorie": asset.get("categories") or [], "tagy": asset.get("tags") or [],
            "popis": asset.get("description") or "", "licence": "CC0", "autor": _autor(asset),
            "stranka": PH_STRANKA + slug, "soubor": soubor.relative_to(sklad.root()).as_posix(),
            "nahled": nahled.relative_to(sklad.root()).as_posix() if nahled else None, "bajtu": bajtu,
            "rozmery_m": [round(x / 1000, 3) for x in rozmery] if druh == "model" and rozmery else None,
            "trojuhelniky": asset.get("polycount"), "files_hash": asset.get("files_hash"), "stazeno": _ted()}


def _aktualni(cil: Path, asset: dict) -> bool:
    p = cil / "puvod.json"
    if not p.exists():
        return False
    stary = json.loads(p.read_text(encoding="utf-8"))
    return stary.get("files_hash") == asset.get("files_hash") and (sklad.root() / stary["soubor"]).exists()


def _nahled(asset: dict, cil: Path) -> Path | None:
    url = asset.get("thumbnail_url")
    if not url:
        return None
    path = cil / "nahled.webp"
    try:
        _write_atomic(path, _get(url))
    except SkladError:
        return None
    return path


def _ph_model(slug: str, asset: dict) -> dict:
    cil = dir3d() / "polyhaven" / "models" / slug
    files = _json(f"{PH_API}/files/{slug}")
    g = ((files.get("gltf") or {}).get(ROZLISENI) or {}).get("gltf")
    if not g:
        raise SkladError(f"{slug}: nemá glTF {ROZLISENI}")
    soubory = {rel: _get(f["url"]) for rel, f in (g.get("include") or {}).items()}
    for rel, f in (g.get("include") or {}).items():
        if f.get("md5") and hashlib.md5(soubory[rel]).hexdigest() != f["md5"]:
            raise SkladError(f"{slug}: {rel} nesedí MD5")
    glb = gltf_na_glb(_get(g["url"]), soubory)
    _write_atomic(cil / "model.glb", glb)
    return _ph_zaznam(slug, asset, "model", cil / "model.glb", _nahled(asset, cil), len(glb))


def _ph_hdri(slug: str, asset: dict) -> dict:
    cil = dir3d() / "polyhaven" / "hdri" / slug
    files = _json(f"{PH_API}/files/{slug}")
    h = (((files.get("hdri") or {}).get(ROZLISENI)) or {}).get("hdr")
    if not h:
        raise SkladError(f"{slug}: nemá HDR {ROZLISENI}")
    data = _get(h["url"])
    if h.get("md5") and hashlib.md5(data).hexdigest() != h["md5"]:
        raise SkladError(f"{slug}: HDR nesedí MD5")
    path = cil / f"{slug}_{ROZLISENI}.hdr"
    _write_atomic(path, data)
    return _ph_zaznam(slug, asset, "hdri", path, _nahled(asset, cil), len(data))


def stahni_polyhaven(druh: str = "model", limit: int | None = None, log: Callable[[str], None] = print) -> dict:
    """Stáhne modely (`model`) nebo HDRI (`hdri`) z Poly Havenu. Opakovatelné: přeskočí, co má stejný `files_hash`."""
    if druh not in DRUHY:
        raise SkladError(f"neznámý druh {druh!r}, povolené: {', '.join(DRUHY)}")
    assets = _json(f"{PH_API}/assets?t={'models' if druh == 'model' else 'hdris'}")
    slugs = sorted(assets)[:limit] if limit else sorted(assets)
    nove = stejne = chyby = bajtu = 0
    for i, slug in enumerate(slugs, 1):
        cil = dir3d() / "polyhaven" / ("models" if druh == "model" else "hdri") / slug
        if _aktualni(cil, assets[slug]):
            stejne += 1
            continue
        try:
            zaznam = (_ph_model if druh == "model" else _ph_hdri)(slug, assets[slug])
        except SkladError as e:
            chyby += 1
            log(f"{slug}: {e}")
            continue
        _write_atomic(cil / "puvod.json", json.dumps(zaznam, ensure_ascii=False, indent=1).encode("utf-8"))
        nove += 1
        bajtu += zaznam["bajtu"]
        if i % 25 == 0:
            log(f"{i}/{len(slugs)}: {nove} nových, {bajtu / 1e6:.0f} MB")
    index = sestav_index()
    stav = {"druh": druh, "nabidka": len(assets), "zpracovano": len(slugs), "novych": nove, "beze_zmeny": stejne,
            "chyb": chyby, "novych_mb": round(bajtu / 1e6, 1), "v_indexu": len(index)}
    log(f"hotovo: {stav}")
    return stav


# -- uložení cizího nebo našeho modelu (Smithsonian stahuje GRAFIK, naše modely kopíruje GRAFIK) --

_BEZPECNE = re.compile(r"[A-Za-z0-9._-]+")


def uloz_model(zdroj: str, model_id: str, glb: bytes, info: dict) -> dict:
    """Uloží cizí GLB do `3d/<zdroj>/<model_id>/` s puvod.json. `info`: nazev, autor, licence, stranka, kategorie?, tagy?"""
    if not (_BEZPECNE.fullmatch(zdroj) and _BEZPECNE.fullmatch(model_id)) or zdroj in ("polyhaven", "nase"):
        raise SkladError(f"neplatný zdroj nebo id: {zdroj}/{model_id}")
    ok, proc = licence_ok(info.get("licence") or "")
    if not ok:
        raise SkladError(f"{zdroj}/{model_id}: {proc}")
    cil = dir3d() / zdroj / model_id
    _write_atomic(cil / "model.glb", glb)
    zaznam = {"id": f"{zdroj}/{model_id}", "zdroj": zdroj, "druh": "model", "nazev": info.get("nazev") or model_id,
              "kategorie": info.get("kategorie") or [], "tagy": info.get("tagy") or [], "popis": info.get("popis") or "",
              "licence": info["licence"], "autor": info.get("autor") or "", "stranka": info.get("stranka") or "",
              "soubor": (cil / "model.glb").relative_to(sklad.root()).as_posix(), "nahled": None, "bajtu": len(glb),
              "rozmery_m": None, "trojuhelniky": None, "stazeno": _ted()}
    _write_atomic(cil / "puvod.json", json.dumps(zaznam, ensure_ascii=False, indent=1).encode("utf-8"))
    return zaznam


def uloz_nas(vdir: Path, meta: dict) -> dict:
    """Kopie verze našeho modelu z GRAFIK `library/3d/<id>/<verze>/` do `3d/nase/<id>/<verze>/` (operátor 2026-11-05:
    kopie při kontrole). Nic se nepřepisuje: verze, která už ve skladu je, zůstane, jak byla."""
    model_id, verze = meta["id"], meta["version"]
    if not (_BEZPECNE.fullmatch(model_id) and _BEZPECNE.fullmatch(verze)):
        raise SkladError(f"neplatné id modelu {model_id}/{verze}")
    if not (vdir / "model.glb").is_file():
        raise SkladError(f"{model_id} {verze} nemá model.glb")
    cil = dir3d() / "nase" / model_id / verze
    puvod = cil / "puvod.json"
    if puvod.exists():
        return json.loads(puvod.read_text(encoding="utf-8"))
    tmp = cil.with_name(verze + ".tmp")
    if tmp.exists():
        shutil.rmtree(tmp)
    shutil.copytree(vdir, tmp)
    nahled = next((p for p in ("views/front.png", "views/e0/front.png") if (tmp / p).is_file()), None)
    zaznam = {"id": f"nase/{model_id}/{verze}", "zdroj": "nase", "druh": "model", "nazev": meta.get("title") or model_id,
              "kategorie": [], "tagy": [], "popis": meta.get("origin") or "",
              "licence": meta.get("license") or "vlastní (NGM)", "autor": meta.get("author") or "NGM GRAFIK",
              "stranka": meta.get("source_url") or "", "soubor": f"3d/nase/{model_id}/{verze}/model.glb",
              "nahled": f"3d/nase/{model_id}/{verze}/{nahled}" if nahled else None,
              "bajtu": (vdir / "model.glb").stat().st_size, "rozmery_m": None, "trojuhelniky": None,
              "grafik": {"model_id": model_id, "verze": verze, "zkontroloval": (meta.get("review") or {}).get("by")},
              "stazeno": _ted()}
    _write_atomic(tmp / "puvod.json", json.dumps(zaznam, ensure_ascii=False, indent=1).encode("utf-8"))
    tmp.replace(cil)
    sestav_index()
    return zaznam


# -- index a hledání ------------------------------------------------------------------

def sestav_index() -> list[dict]:
    """Index ze všech `puvod.json` pod `3d/` (bez rozpracovaných `.tmp`)."""
    base = dir3d()
    zaznamy = []
    for p in sorted(base.rglob("puvod.json")) if base.is_dir() else []:
        if any(part.endswith(".tmp") for part in p.relative_to(base).parts):
            continue
        try:
            zaznamy.append(json.loads(p.read_text(encoding="utf-8")))
        except ValueError:
            continue
    _write_atomic(base / "index.json", json.dumps(zaznamy, ensure_ascii=False, indent=1).encode("utf-8"))
    return zaznamy


def nacti_index() -> list[dict]:
    path = dir3d() / "index.json"
    if not path.exists():
        raise SkladError(f"{path} neexistuje, nejdřív `python -m ngm_shared.sklad stahni polyhaven`")
    return json.loads(path.read_text(encoding="utf-8"))


def hledej(dotaz: str = "", druh: str | None = None, zdroj: str | None = None, bez_zdroje: tuple[str, ...] = (),
           limit: int = 20, index: list[dict] | None = None) -> list[dict]:
    """Slova dotazu (bez diakritiky, od začátku slova) v názvu, tazích, kategoriích a popisu. Názvy a tagy jsou
    anglicky, české slovo najde jen náš model; volající má téma předat i anglicky."""
    slova = [s for s in re.split(r"\W+", _bez_diakritiky(dotaz)) if s]
    vysledek = []
    for z in index if index is not None else nacti_index():
        if (druh and z["druh"] != druh) or (zdroj and z["zdroj"] != zdroj) or z["zdroj"] in bez_zdroje:
            continue
        hlavni = _SLOVO.findall(_bez_diakritiky(" ".join([z["nazev"], *z["tagy"], *z["kategorie"]])))
        popis = _SLOVO.findall(_bez_diakritiky(z.get("popis") or ""))
        skore = sum(2 if any(w.startswith(s) for w in hlavni) else 1 if any(w.startswith(s) for w in popis) else 0
                    for s in slova)
        if slova and not skore:
            continue
        vysledek.append((skore, z))
    vysledek.sort(key=lambda p: (p[0], p[1]["stazeno"]), reverse=True)
    return [z for _, z in vysledek[:limit]]


def zaznam(id_: str, index: list[dict] | None = None) -> dict:
    for z in index if index is not None else nacti_index():
        if z["id"] == id_:
            return z
    raise SkladError(f"{id_} ve skladu není")


def cesta(z: dict, co: str = "soubor") -> Path | None:
    """Absolutní cesta k souboru (`soubor`) nebo náhledu (`nahled`) záznamu."""
    return sklad.root() / z[co] if z.get(co) else None


def hdri(dotaz: str = "", limit: int = 10) -> list[dict]:
    """HDRI pro render (POHYB): záznamy s absolutní cestou v `cesta`."""
    return [{**z, "cesta": str(cesta(z))} for z in hledej(dotaz, druh="hdri", limit=limit)]


def zapis_readme() -> None:
    text = """# NGM-SKLAD / 3d

Zásoba 3D modelů a HDRI. Spravuje ji `ngm_shared.sklad3d` (repo GRAFIK, `shared/`); ručně tu nic neupravuj.
Do výroby jde model jen přes GRAFIK (`library/3d`, Studio → 3D → Hotový model, „Převzít · 0 USD“), POHYB
a KLAPKA ho berou odtud. HDRI si POHYB bere přímo ze skladu.

| Složka | Zdroj | Licence |
|---|---|---|
| `polyhaven/models/` | https://polyhaven.com (glTF s texturami 1k složený do GLB) | CC0 |
| `polyhaven/hdri/` | https://polyhaven.com (HDR 1k) | CC0 |
| `smithsonian/` | https://3d.si.edu, vybrané podle témat | CC0 (Open Access) |
| `nase/` | kopie našich modelů z GRAFIK `library/3d` po kontrole | vlastní, u převzatých licence zdroje |

Každá položka má `puvod.json` (autor, licence, odkaz); `index.json` je spojí. Hledání:
`python -m ngm_shared.sklad hledej3d <slova> [--druh model|hdri]`.
"""
    _write_atomic(dir3d() / "README.md", text.encode("utf-8"))
