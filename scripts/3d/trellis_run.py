# Image -> 3D GLB via fal TRELLIS 2 (PAID: 0.25/0.30/0.35 USD for 512/1024/1536p; ask the operator first).
# python scripts/3d/trellis_run.py cutout.png out.glb 1024 7   (input: RGBA cutout from cutout.py)
import json, sys, time
from datetime import datetime
from pathlib import Path
import httpx, fal_client
sys.path.insert(0, "C:/Users/stock/Documents/000_NGM/GRAFIK")
from engine.keys import get_key
src, out, res, seed = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
usd = {512: 0.25, 1024: 0.30, 1536: 0.35}[res]
client = fal_client.SyncClient(key=get_key("FAL_KEY", "FAL_API_KEY"), default_timeout=900)
url = client.upload(src.read_bytes(), "image/png")
t = time.time()
r = client.subscribe("fal-ai/trellis-2", arguments={"image_url": url, "resolution": res, "seed": seed})
with open("C:/Users/stock/Documents/000_NGM/GRAFIK/library/costs.jsonl", "a", encoding="utf-8") as f:
    f.write(json.dumps({"ts": datetime.now().isoformat(timespec="seconds"), "job_id": None, "caller": "spike-3d",
                        "backend": "fal:fal-ai/trellis-2", "n": 1, "usd": usd,
                        "items": [{"what": f"TRELLIS 2 image-to-3D {res}p", "usd": usd}]}, ensure_ascii=False) + "\n")
glb = r["model_glb"]["url"]
out.write_bytes(httpx.get(glb, timeout=300).raise_for_status().content)
print(f"{time.time()-t:.0f}s", out.stat().st_size, {k: v for k, v in r.items() if k != "model_glb"})
