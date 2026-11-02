# The seated man for the well: the paid 3D model (Hunyuan 3.1 Pro, 0.375 USD) from his picture, plus what velsen_studna.py needs to colour it: the picture and the frame of the figure in it.
#   python scripts/plakaty/velsen_muz.py OBRAZ.png OUT --confirm-cost
import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "shared")]
from ngm_shared import grafik_client as gc  # noqa: E402


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    image, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    from rembg import new_session, remove
    rgb = Image.open(image).convert("RGB")
    alpha = remove(rgb, session=new_session("u2net")).getchannel("A")
    bbox = alpha.point(lambda v: 255 if v > 32 else 0).getbbox()
    # the grey wall must not bleed onto the model: outside the figure the nearest colour of the figure
    mask = ndi.binary_erosion(np.asarray(alpha) > 96, iterations=4)
    idx = ndi.distance_transform_edt(~mask, return_distances=False, return_indices=True)
    Image.fromarray(np.asarray(rgb)[idx[0], idx[1]]).save(out / "textura.png")
    alpha.save(out / "maska.png")
    (out / "ramec.json").write_text(json.dumps({"bbox": list(bbox), "size": list(rgb.size)}), encoding="utf-8")
    print("ramec", bbox, rgb.size)
    if not (out / "model.glb").exists():
        m = gc.model3d(refs=[{"path": str(image), "view": "front", "source": "lokální FLUX podle rekonstrukce v knize (obr. 11.1)"}], title="Velsen sedici", method="fal-hunyuan31pro",
                       origin="scripts/plakaty/velsen_muz.py", confirm_cost="--confirm-cost" in sys.argv, timeout=1500)
        print({k: m.get(k) for k in ("id", "model_id", "version", "cost_usd", "status")})
    if not (out / "model.glb").exists():      # the finished model lies in the library, never pay twice
        shutil.copy(sorted(Path(r"C:/Users/stock/Documents/000_NGM/GRAFIK/library/3d").glob("velsen-sedici*/v*/model.glb"))[-1], out / "model.glb")
    print((out / "model.glb").stat().st_size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
