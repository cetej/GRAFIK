# Díly výstroje (přilba, zbroj, opasek…) jako samostatné předměty pro postavu s kostrou.
# Postup a proč: docs/3d-postava-postup.md, oddíl „Výstroj po dílech“.
#
#   python scripts/3d/postava/vystroj_dily.py vyrez   <zadani.json>              # lokální FLUX, 0 USD
#   python scripts/3d/postava/vystroj_dily.py generuj <zadani.json> --confirm-cost  # fal Hunyuan3D v3 Normal, 0,525 USD za díl
#
# zadani.json:
# {"podklad": "<složka s ref-front.png, ref-back.png, ref-right.png>", "vystup": "<složka>",
#  "dily": {"prilba": {"popis": "one Roman ... helmet ...", "box": {"front": [x0,y0,x1,y1], "back": [...], "right": [...]},
#                      "seed": 21, "seed_pohled": {"back": 23}, "popis_pohled": {"back": "..."}}}}
# Výstup: <vystup>/<díl>/vyrez-<pohled>.png (výřez z podkladu), flux/… (všechny pokusy), ref-<pohled>.png (vybraný pohled),
# model.glb a request.json. Pohledy před `generuj` prohlédni: FLUX umí přidat díl, který na pohledu není (zástěra zezadu),
# nebo mezeru mezi kusy; takový pohled vygeneruj znovu s jiným seedem nebo s `popis_pohled`.
import argparse
import json
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "shared"))
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace"); sys.stderr.reconfigure(encoding="utf-8", errors="replace")
VIEWS = {"front": "seen straight from the front", "back": "seen straight from the back", "right": "seen straight from its right side, in profile"}
EP = "fal-ai/hunyuan3d-v3/image-to-3d"
USD = 0.525


def vyrez(cfg, only=None):
    from ngm_shared import grafik_client as g
    src, out = Path(cfg["podklad"]), Path(cfg["vystup"])
    for d, dc in cfg["dily"].items():
        if only and d not in only:
            continue
        for v, box in dc["box"].items():
            im = Image.open(src / f"ref-{v}.png").convert("RGB").crop(tuple(box))
            s = max(im.size); sq = Image.new("RGB", (s, s), im.getpixel((2, 2))); sq.paste(im, ((s - im.width) // 2, (s - im.height) // 2))
            o = out / d; o.mkdir(parents=True, exist_ok=True); vp = o / f"vyrez-{v}.png"; sq.resize((1024, 1024), Image.LANCZOS).save(vp)
            popis = dc.get("popis_pohled", {}).get(v, dc["popis"])
            p = (f"Museum product photo of {popis}, displayed on its own as an empty object, nobody wearing it, no person, no head, no body, no arms, no clothes inside. "
                 f"Same design, shape, proportions and colours as the reference, {VIEWS[v]}, centred, whole object in frame with margin, plain pure white background, soft even studio light, sharp detail.")
            seed = dc.get("seed_pohled", {}).get(v, dc.get("seed", 21))
            r = g.generate(p, out_dir=o / "flux", seed=seed, refs=[{"path": str(vp), "role": "subject"}], caller="vystroj-dily")
            shutil.copy(r[0], o / f"ref-{v}.png")
            print(d, v, "seed", seed, "->", o / f"ref-{v}.png", flush=True)


def generuj(cfg, only=None):
    import fal_client
    import httpx
    from engine.keys import get_key
    out = Path(cfg["vystup"]); ledger = ROOT / "library" / "costs.jsonl"
    client = fal_client.SyncClient(key=get_key("FAL_KEY", "FAL_API_KEY"), default_timeout=900); hs = {}

    def log(d, status):
        with open(ledger, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": datetime.now().isoformat(timespec="seconds"), "job_id": None, "caller": "vystroj-dily", "backend": f"fal:{EP}", "n": 1, "usd": USD,
                                "items": [{"what": f"Hunyuan3D v3 Normal {d}", "usd": 0.375}, {"what": "multi-view", "usd": 0.15}], "status": status}, ensure_ascii=False) + "\n")
    for d in cfg["dily"]:
        if only and d not in only:
            continue
        o = out / d; u = {v: client.upload((o / f"ref-{v}.png").read_bytes(), "image/png") for v in ("front", "back", "right") if (o / f"ref-{v}.png").exists()}
        args = {"input_image_url": u["front"], "generate_type": "Normal", **{f"{v}_image_url": x for v, x in u.items() if v != "front"}}
        h = client.submit(EP, arguments=args); hs[d] = h; log(d, "pending")
        (o / "request.json").write_text(json.dumps({"endpoint": EP, "request_id": h.request_id, "args": args}, indent=1), encoding="utf-8")
        print(d, "request_id", h.request_id, flush=True)
    t0 = time.monotonic()
    while hs and time.monotonic() - t0 < 1200:
        for d, h in list(hs.items()):
            if isinstance(h.status(), fal_client.Completed):
                try:
                    glb = httpx.get(h.get()["model_glb"]["url"], timeout=300).raise_for_status().content
                    (out / d / "model.glb").write_bytes(glb); log(d, "ok"); print(d, "hotovo", len(glb), "B", flush=True)
                except Exception as e:
                    log(d, "failed"); print(d, "CHYBA", e, flush=True)
                del hs[d]
        time.sleep(5)
    for d, h in hs.items():
        print(d, "nedoběhlo, request_id", h.request_id)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("krok", choices=["vyrez", "generuj"]); ap.add_argument("zadani"); ap.add_argument("--dil", nargs="*")
    ap.add_argument("--confirm-cost", action="store_true")
    a = ap.parse_args(); cfg = json.loads(Path(a.zadani).read_text(encoding="utf-8"))
    if a.krok == "vyrez":
        vyrez(cfg, a.dil)
    else:
        n = len(a.dil or cfg["dily"])
        if not a.confirm_cost:
            sys.exit(f"placené: {n} × {USD} USD = {n * USD:.2f} USD; spusť s --confirm-cost až po souhlasu operátora")
        generuj(cfg, a.dil)
