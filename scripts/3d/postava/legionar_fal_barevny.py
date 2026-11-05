# Obarvený model z podkladu operátora: Hunyuan3D v3 Normal + pohledy zezadu a zprava (0,375 + 0,15 = 0,525 USD).
# Spouštět s PYTHONPATH=<GRAFIK> (klíč přes engine.keys jako Engine). Výstup: barevny_hunyuan.glb + request.json.
import json
import sys
import time
from pathlib import Path

import fal_client
import httpx

from engine.keys import get_key

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HERE = Path(__file__).resolve().parent
ENDPOINT = "fal-ai/hunyuan3d-v3/image-to-3d"
client = fal_client.SyncClient(key=get_key("FAL_KEY", "FAL_API_KEY"), default_timeout=900)
urls = {v: client.upload((HERE / f"ref-{v}.png").read_bytes(), "image/png") for v in ("front", "back", "right")}
args = {"input_image_url": urls["front"], "back_image_url": urls["back"], "right_image_url": urls["right"],
        "generate_type": "Normal"}
handle = client.submit(ENDPOINT, arguments=args)
(HERE / "request.json").write_text(json.dumps({"endpoint": ENDPOINT, "request_id": handle.request_id, "args": args}, indent=1), encoding="utf-8")
print("request_id", handle.request_id, flush=True)
t0 = time.monotonic()
while not isinstance(handle.status(), fal_client.Completed):
    if time.monotonic() - t0 > 900:
        sys.exit(f"nedoběhlo do 15 min, vyzvednout přes request_id {handle.request_id}")
    time.sleep(5)
res = handle.get()
glb = httpx.get(res["model_glb"]["url"], timeout=300).raise_for_status().content
(HERE / "barevny_hunyuan.glb").write_bytes(glb)
print("hotovo", len(glb), "B za", int(time.monotonic() - t0), "s")
