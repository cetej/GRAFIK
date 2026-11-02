# Fetches the bones for velsen_kostra.py: the lower body from BodyParts3D (CC BY-SA 2.1 JP, GitHub clone Kevin-Mattheus-Moerman/BodyParts3D), about 12 MB. Needs parts_list_e.txt from the same repository in BP3D_DIR.
#   python scripts/3d/velsen_kostra_data.py BP3D_DIR
import re
import sys
import time
import urllib.request
from pathlib import Path

BASE = "https://raw.githubusercontent.com/Kevin-Mattheus-Moerman/BodyParts3D/main/assets/BodyParts3D_data"
WANT = re.compile(r"^(right|left) (hip bone|femur|tibia|fibula|patella|talus|calcaneus|cuboid bone|navicular bone of foot|medial cuneiform bone|intermediate cuneiform bone|lateral cuneiform bone)$"
                  r"|^(right|left) (first|second|third|fourth|fifth) metatarsal bone$"
                  r"|^(proximal|middle|distal) phalanx of (right|left) (big|great|second|third|fourth|little|index|middle|ring) toe$"
                  r"|^(sacrum|coccyx|fifth lumbar vertebra)$")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    d = Path(sys.argv[1])
    d.mkdir(parents=True, exist_ok=True)
    listing = d / "parts_list_e.txt"
    if not listing.exists():
        listing.write_bytes(urllib.request.urlopen(f"{BASE}/parts_list_e.txt", timeout=60).read())
    rows = [line.split("\t") for line in listing.read_text(encoding="utf-8").splitlines()[1:]]
    names = {fma: name for fma, name in rows if WANT.match(name)}
    for fma in names:
        out = d / f"{fma}.stl"
        if not out.exists():
            out.write_bytes(urllib.request.urlopen(f"{BASE}/stl/{fma}.stl", timeout=60).read())
            time.sleep(0.1)
    (d / "nazvy.txt").write_text("\n".join(f"{fma}\t{name}" for fma, name in names.items()), encoding="utf-8")
    print(len(names), "kostí")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
