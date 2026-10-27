# Prepared views -> 3D GLB via fal Hunyuan3D v3 Geometry (PAID: 0.225 USD, +0.15 USD with any extra view;
# ask the operator first). Input: a folder with predloha-front.png and optionally predloha-back/left/right.png
#   python scripts/3d/hunyuan_run.py library/3d/<id>
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import fal_client
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from engine.keys import get_key  # noqa: E402

d = Path(sys.argv[1])
views = {v: d / f"predloha-{v}.png" for v in ("front", "back", "left", "right") if (d / f"predloha-{v}.png").exists()}
extra = [v for v in views if v != "front"]
usd = 0.225 + (0.15 if extra else 0)
client = fal_client.SyncClient(key=get_key("FAL_KEY", "FAL_API_KEY"), default_timeout=900)
urls = {v: client.upload(p.read_bytes(), "image/png") for v, p in views.items()}
args = {"input_image_url": urls["front"], "generate_type": "Geometry", "face_count": 500000}
args.update({f"{v}_image_url": urls[v] for v in extra})
ledger = Path(__file__).resolve().parents[2] / "library" / "costs.jsonl"
entry = {"job_id": None, "caller": "spike-3d", "backend": "fal:fal-ai/hunyuan3d-v3/image-to-3d", "n": 1, "usd": usd,
         "items": [{"what": "Hunyuan3D v3 Geometry", "usd": 0.225}] + ([{"what": "multi-view", "usd": 0.15}] if extra else [])}


def log(status):
    with open(ledger, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": datetime.now().isoformat(timespec="seconds"), **entry, "status": status}, ensure_ascii=False) + "\n")


log("pending")
t = time.time()
try:
    r = client.subscribe("fal-ai/hunyuan3d-v3/image-to-3d", arguments=args)
except Exception:
    log("failed")
    raise
log("ok")
(d / "model.glb").write_bytes(httpx.get(r["model_glb"]["url"], timeout=300).raise_for_status().content)
print(d.name, f"{time.time() - t:.0f}s", (d / "model.glb").stat().st_size, "views", list(views), "usd", usd)
