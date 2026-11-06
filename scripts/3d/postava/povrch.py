# Povrch postavy: render z 3D postavy (foto/<póza>-*.png z kostra/postava_s_vystroji.py) -> obraz jako fotka.
# Tvar, pózu a výstroj drží 3D, model obrazu dodá pleť, ruce, látku a kov (srovnání docs/spikes/2026-11-06-legionar-vzhled.md).
#   python povrch.py flux <render.png> <out_dir> [--n 3]                 lokální FLUX přes Engine, 0 USD (náčrt, výběr pózy)
#   python povrch.py gpt  <render.png> <out_dir> [--n 1] --confirm-cost  GPT Image 2 edit, drží výřez i každý plát (infografika), ~0,33 USD/ks
#   python povrch.py nb   <render.png> <out_dir> [--n 1] --confirm-cost  Nano Banana Pro edit, nejvěrnější fotka (ilustrace), 0,15 USD/ks;
#                                                                         občas změní výřez: takový obrázek vyřadit
# Popis postavy: --popis "…" (výchozí legionář). Placené jen s --confirm-cost; request_id a cena jdou do library/costs.jsonl hned po odeslání.
import argparse, json, sys
from datetime import datetime
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[3]; sys.path[:0] = [str(ROOT), str(ROOT / "shared")]
LEGIONAR = ("a Roman legionary reenactor: imperial Gallic helmet, segmented iron lorica segmentata with shoulder plates, "
            "leather belt with hanging studded straps, dark red wool tunic to above the knees with short sleeves, leather caligae sandals")
CENA = {"gpt": ("fal-ai/gpt-image-2/edit", 0.33), "nb": ("fal-ai/nano-banana-pro/edit", 0.15)}

def ledger_path():
    # ve worktree vede evidence cen do hlavního checkoutu (jako vystroj_dily.py)
    lib = ROOT / "library"
    if ".claude" in ROOT.parts:
        lib = Path(*ROOT.parts[:ROOT.parts.index(".claude")]) / "library"
    return lib / "costs.jsonl"

def log(ep, usd, n, rid, status, src):
    with open(ledger_path(), "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": datetime.now().isoformat(timespec="seconds"), "job_id": None, "caller": "postava-povrch", "backend": f"fal:{ep}",
                            "n": n, "usd": round(usd * n, 3), "request_id": rid, "items": [{"what": f"povrch {src}", "usd": usd}], "status": status},
                           ensure_ascii=False) + "\n")

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("mode", choices=("flux", "gpt", "nb")); ap.add_argument("render"); ap.add_argument("out")
    ap.add_argument("--n", type=int, default=None); ap.add_argument("--popis", default=LEGIONAR); ap.add_argument("--confirm-cost", action="store_true")
    a = ap.parse_args(); src, out = Path(a.render), Path(a.out); out.mkdir(parents=True, exist_ok=True)
    if a.mode == "flux":
        from ngm_shared import grafik_client as g
        prompt = (f"Studio photograph of a real man, {a.popis}, standing exactly as in the reference, same framing and plain grey background. "
                  "Natural tanned Mediterranean skin with pores and fine hair, realistic hands with relaxed fingers, real wool with soft folds, "
                  "worn iron, soft even studio light, sharp focus.")
        for i in range(a.n or 3):
            for p in g.generate(prompt, out_dir=out, size="768x1152", seed=11 + i, refs=[{"path": str(src), "role": "geometry"}], caller="postava-povrch"):
                print(p, flush=True)
        return
    ep, usd = CENA[a.mode]; n = a.n or 1
    if not a.confirm_cost:
        print(f"{ep}: {n} × {usd} USD = {usd * n:.2f} USD (GPT účtuje tokeny, cena je odhad). Spustit jen se svolením a s --confirm-cost."); sys.exit(1)
    import fal_client, httpx
    from engine.keys import get_key
    cl = fal_client.SyncClient(key=get_key("FAL_KEY", "FAL_API_KEY"), default_timeout=600)
    prompt = (f"Turn this 3D render into a photograph of a real man, {a.popis}, in a studio. Keep EXACTLY the same pose, body proportions, camera, "
              "framing, background and every piece of equipment. Do not add, remove or move anything. Only make it photoreal: natural skin with pores "
              "and fine hair, realistic anatomically correct hands with five relaxed fingers and visible knuckles and nails, real fabric with natural folds, "
              "real worn metal and leather, soft studio light.")
    args = {"prompt": prompt, "image_urls": [cl.upload(src.read_bytes(), "image/png")], "num_images": n}
    args |= {"resolution": "2K"} if a.mode == "nb" else {"quality": "high"}
    h = cl.submit(ep, arguments=args); log(ep, usd, n, h.request_id, "pending", src.name)
    (out / "request.json").write_text(json.dumps({"endpoint": ep, "request_id": h.request_id, "zdroj": str(src)}, indent=1), encoding="utf-8")
    print("request_id", h.request_id, flush=True)
    try:
        r = h.get()
    except Exception:
        log(ep, usd, n, h.request_id, "failed", src.name); raise
    for i, im in enumerate(r["images"]):
        (out / f"{a.mode}-{i}.png").write_bytes(httpx.get(im["url"], timeout=300).raise_for_status().content); print(out / f"{a.mode}-{i}.png", flush=True)
    log(ep, usd, len(r["images"]), h.request_id, "ok", src.name)

if __name__ == "__main__":
    main()
