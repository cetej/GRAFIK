"""Opotřebení modelu v TextureCraftu (open-source klon Substance Painteru, storytold): špína ve spárách a odřené
hrany kovu jako textury, nová verze modelu s texturami, 0 USD, bez okna (DECISIONS 2026-11-06).

TextureCraft 0.3.2 z GLB převezme geometrii a UV, materiály ne (prázdná vrstva, žádné obrázky), proto se
vzhled modelu nejdřív složí z glTF JSON: barva, drsnost a kovovost z faktorů, nebo obrázek baseColor a
rozdělená mapa metallicRoughness. Nad to přijdou vrstvy z generátorů TextureCraftu (`dirt`, `edgeWear`) s maskou
z mapy dutin a křivosti, kterou TextureCraft zapeče na GPU. Test 2026-11-06 (STOPA outputs/2026-11-06-craft-apps-
nabidka.md): motor 6 sad 2K za ~25 s, legionář ~30 s, výsledek deterministický, UV zachované.
"""
from __future__ import annotations

import io
import json
import os
import struct
import subprocess
from pathlib import Path

from PIL import Image

DEFAULT_CRAFT_HOME = "C:/Users/stock/Tools/Craft"
TIMEOUT_S = 900
EXPORT_PRESET = "glTF PBR Metal Roughness"

# síla = průhlednost vrstev; úrovně generátorů zůstávají výchozí (dirt 0,55, edgeWear 0,6). Výchozí plná síla
# na legionáři zakryla tuniku skoro celou (test 2026-11-06), proto je výchozí „střední“.
SILY = {"jemne": 0.35, "stredni": 0.6, "silne": 0.9}
SPINA = {"color": "#2e2418", "roughness": 0.9, "metallic": 0.0}
ODRENI = {"color": "#c8c4bc", "roughness": 0.25, "metallic": 1.0}


class TextureCraftError(RuntimeError):
    pass


def cli_path() -> Path:
    home = Path(os.environ.get("CRAFT_HOME", DEFAULT_CRAFT_HOME))
    return home / "texturecraft" / "texturecraft-cli.exe"


def read_glb(data: bytes) -> tuple[dict, bytes]:
    if data[:4] != b"glTF":
        raise TextureCraftError("soubor není GLB")
    off, js, binc = 12, None, b""
    while off < len(data):
        n, t = struct.unpack_from("<II", data, off)
        chunk = data[off + 8: off + 8 + n]
        if t == 0x4E4F534A:
            js = json.loads(chunk)
        elif t == 0x004E4942:
            binc = chunk
        off += 8 + n
    if js is None:
        raise TextureCraftError("GLB bez JSON části")
    return js, binc


def _image(g: dict, binc: bytes, tex_index: int) -> bytes:
    img = g["images"][g["textures"][tex_index]["source"]]
    if "bufferView" not in img:
        raise TextureCraftError("textura modelu není uvnitř GLB")
    bv = g["bufferViews"][img["bufferView"]]
    start = bv.get("byteOffset", 0)
    return binc[start: start + bv["byteLength"]]


def _hex(rgb: list[float]) -> str:
    def srgb(c: float) -> float:
        c = max(0.0, min(1.0, c))
        return c * 12.92 if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
    return "#" + "".join(f"{round(srgb(c) * 255):02x}" for c in rgb[:3])


def resolution(g: dict, binc: bytes) -> int:
    """Rozlišení sad: 2048, nebo 4096, když model nese větší texturu (2048 by ji změkčilo, test legionáře)."""
    biggest = 0
    for m in g.get("materials", []):
        tex = m.get("pbrMetallicRoughness", {}).get("baseColorTexture")
        if tex is not None:
            biggest = max(biggest, *Image.open(io.BytesIO(_image(g, binc, tex["index"]))).size)
    return 4096 if biggest > 2048 else 2048


def build_steps(g: dict, binc: bytes, work: Path, sila: str, spina: bool, hrany: bool) -> list[dict]:
    """Kroky dávky: zapéct mapy, složit vzhled modelu, přidat špínu a odření, exportovat GLB s texturami."""
    if sila not in SILY:
        raise TextureCraftError(f"síla musí být jedna z {sorted(SILY)}")
    opacity = SILY[sila]
    steps: list[dict] = [{"id": "bake.run", "params": {"ts": "all"}}]
    for ts, m in enumerate(g.get("materials", [])):
        pbr = m.get("pbrMetallicRoughness", {})
        metal = pbr.get("metallicFactor", 1.0)
        steps.append({"id": "textureSet.select", "params": {"ts": ts}})
        if "baseColorTexture" in pbr:
            col = work / f"m{ts}_basecolor.png"
            col.write_bytes(_image(g, binc, pbr["baseColorTexture"]["index"]))
            steps += [{"id": "resource.import", "params": {"path": str(col)}},
                      # jméno zdroje je celé jméno souboru i s příponou
                      {"id": "layer.add.image", "params": {"name": col.name, "channel": "baseColor", "projection": "uv"}}]
            if "metallicRoughnessTexture" in pbr:
                mr = Image.open(io.BytesIO(_image(g, binc, pbr["metallicRoughnessTexture"]["index"]))).convert("RGB")
                _, rough_ch, metal_ch = mr.split()
                for ch, im in (("roughness", rough_ch), ("metallic", metal_ch)):
                    p = work / f"m{ts}_{ch}.png"
                    im.save(p)
                    steps += [{"id": "resource.import", "params": {"path": str(p)}},
                              {"id": "layer.fill.set", "params": {"channel": ch, "image": p.name}}]
            kov = False   # kovové části v jedné textuře neodlišíme od látky, odření jen u kovových materiálů
        else:
            steps.append({"id": "layer.add.fill", "params": {
                "name": "zaklad", "color": _hex(pbr.get("baseColorFactor", [0.8, 0.8, 0.8, 1])),
                "roughness": pbr.get("roughnessFactor", 1.0), "metallic": metal}})
            kov = metal >= 0.5
        if hrany and kov:
            steps += _vrstva("odreni_hran", ODRENI, "edgeWear", opacity)
        if spina:
            steps += _vrstva("spina", SPINA, "dirt", opacity)
    steps += [
        {"id": "file.exportTextures", "params": {"dir": str(work / "tex"), "preset": EXPORT_PRESET, "ts": "all"}},
        {"id": "file.exportMesh", "params": {"path": str(work / "model.glb"), "format": "glb"}},
    ]
    return steps


def _vrstva(name: str, look: dict, generator: str, opacity: float) -> list[dict]:
    return [{"id": "layer.add.fill", "params": {"name": name, **look}},
            {"id": "layer.blend", "params": {"channel": "all", "opacity": opacity}},
            {"id": "mask.add.black", "params": {}},
            {"id": "effect.add.generator", "params": {"generator": generator}}]


def run(src_glb: Path, work: Path, sila: str = "stredni", spina: bool = True, hrany: bool = True,
        timeout_s: float = TIMEOUT_S) -> dict:
    """Celá dávka v TextureCraftu; vrátí cestu k novému GLB a souhrn. Volající drží zámek GPU."""
    cli = cli_path()
    if not cli.is_file():
        raise TextureCraftError(f"TextureCraft není nainstalovaný ({cli}); CRAFT_HOME")
    if not (spina or hrany):
        raise TextureCraftError("vyberte špínu, odřené hrany, nebo obojí")
    src_glb, work = src_glb.resolve(), work.resolve()   # CLI běží s cwd=work
    work.mkdir(parents=True, exist_ok=True)
    g, binc = read_glb(src_glb.read_bytes())
    res = resolution(g, binc)
    project = work / "projekt.tcraft"
    _cli(cli, ["new", str(src_glb), str(project), "--resolution", str(res)], work, timeout_s)
    batch = {"open": str(project), "steps": build_steps(g, binc, work, sila, spina, hrany)}
    (work / "batch.json").write_text(json.dumps(batch, ensure_ascii=False, indent=1), encoding="utf-8")
    out = _cli(cli, ["batch", str(work / "batch.json")], work, timeout_s)
    glb = work / "model.glb"
    if not glb.is_file() or glb.read_bytes()[:4] != b"glTF":
        raise TextureCraftError("TextureCraft nezapsal GLB (log texturecraft.log)")
    project.unlink(missing_ok=True)   # pracovní projekt má stovky MB a nic ho dál nečte
    try:
        tracer = json.loads(out)["results"][0].get("tracer")
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        tracer = None
    return {"glb": glb, "resolution": res, "materials": len(g.get("materials", [])), "tracer": tracer,
            "version": _cli(cli, ["--version"], work, 30).strip()}


def _cli(cli: Path, args: list[str], work: Path, timeout_s: float) -> str:
    # subprocess.run čte výstup průběžně: dávka vypíše přes 4 KB JSON a roura Windows pojme 4 KB, takže čtení
    # až po skončení procesu by ho zablokovalo (test 2026-11-06 to nejdřív vydával za zamrznutí TextureCraftu)
    try:
        p = subprocess.run([str(cli), *args], cwd=work, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout_s, stdin=subprocess.DEVNULL,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired as e:
        raise TextureCraftError(f"TextureCraft nedoběhl do {int(timeout_s)} s") from e
    with (work / "texturecraft.log").open("a", encoding="utf-8") as f:
        f.write(f"$ texturecraft-cli {' '.join(args)}\nexit {p.returncode}\n{p.stdout[-20000:]}\n--- stderr ---\n{p.stderr}\n")
    if p.returncode != 0:
        tail = (p.stderr.strip() or p.stdout.strip()).splitlines()[-2:]
        raise TextureCraftError(f"TextureCraft skončil chybou {p.returncode}: {' / '.join(tail)[:300]}")
    return p.stdout
