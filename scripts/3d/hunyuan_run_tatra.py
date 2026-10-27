# Hunyuan3D v3 Geometry with front + left + back views (PAID ~0.375 USD, approved by operator up to 0.50 USD).
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import fal_client
import httpx
from PIL import Image
from rembg import new_session, remove

sys.path.insert(0, "C:/Users/stock/Documents/000_NGM/GRAFIK")
from engine.keys import get_key  # noqa: E402

src = Path(sys.argv[1])
out = Path("C:/Users/stock/Documents/000_NGM/GRAFIK/library/3d/tatra87-hunyuan3d")
out.mkdir(parents=True, exist_ok=True)
crops = {"front": (0.05, 0.02, 0.9, 0.9), "left": (0.06, 0.1, 0.94, 0.64), "back": (0.15, 0.14, 0.99, 0.9)}
files = {"front": "front.jpg", "left": "side.jpg", "back": "rear.jpg"}
sess = new_session("u2net")
paths = {}
for k, (l, t, r, b) in crops.items():
    im = Image.open(src / files[k]).convert("RGB")
    w, h = im.size
    cut = remove(im.crop((int(l * w), int(t * h), int(r * w), int(b * h))), session=sess)
    bg = Image.new("RGBA", cut.size, (255, 255, 255, 255))
    bg.alpha_composite(cut)
    if k == "left":  # another car behind the windscreen in the side photo
        from PIL import ImageDraw
        W, H = bg.size
        poly = [(0, 0), (0.40, 0), (0.37, 0.09), (0.33, 0.17), (0.25, 0.23), (0, 0.23)]
        ImageDraw.Draw(bg).polygon([(x * W, y * H) for x, y in poly], fill=(255, 255, 255, 255))
    p = out / f"predloha-{k}.png"
    bg.convert("RGB").save(p)
    paths[k] = p
if "--dry" in sys.argv:
    sys.exit(0)
client = fal_client.SyncClient(key=get_key("FAL_KEY", "FAL_API_KEY"), default_timeout=900)
urls = {k: client.upload(p.read_bytes(), "image/png") for k, p in paths.items()}
usd = 0.375
ledger = Path("C:/Users/stock/Documents/000_NGM/GRAFIK/library/costs.jsonl")
entry = {"ts": datetime.now().isoformat(timespec="seconds"), "job_id": None, "caller": "spike-3d",
         "backend": "fal:fal-ai/hunyuan3d-v3/image-to-3d", "n": 1, "usd": usd,
         "items": [{"what": "Hunyuan3D v3 Geometry", "usd": 0.225}, {"what": "multi-view", "usd": 0.15}]}
with open(ledger, "a", encoding="utf-8") as f:
    f.write(json.dumps({**entry, "status": "pending"}, ensure_ascii=False) + "\n")
t = time.time()
try:
    r = client.subscribe("fal-ai/hunyuan3d-v3/image-to-3d", arguments={
        "input_image_url": urls["front"], "left_image_url": urls["left"], "back_image_url": urls["back"],
        "generate_type": "Geometry", "face_count": 500000})
except Exception:
    with open(ledger, "a", encoding="utf-8") as f:
        f.write(json.dumps({**entry, "status": "failed"}, ensure_ascii=False) + "\n")
    raise
with open(ledger, "a", encoding="utf-8") as f:
    f.write(json.dumps({**entry, "ts": datetime.now().isoformat(timespec="seconds"), "status": "ok"}, ensure_ascii=False) + "\n")
print("keys", list(r.keys()))
glb = (r.get("model_glb") or r.get("model_mesh") or {}).get("url")
if not glb:
    print(json.dumps(r)[:1500]); sys.exit(1)
(out / "model.glb").write_bytes(httpx.get(glb, timeout=300).raise_for_status().content)
print(f"{time.time()-t:.0f}s", (out / "model.glb").stat().st_size)
