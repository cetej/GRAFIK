"""Old path of the variants page: re-exports ngm_shared.variants_page (GRAFIK/shared/ngm_shared),
its canonical source (STOPA scripts/manual/variants_page.py re-exports it too). Same CLI: python clients/variants_page.py manifest.json -o out.html
Older copies of grafik_client in other projects load this file by path: they get the same names.
"""
import sys
from pathlib import Path

_shared = str(Path(__file__).resolve().parent.parent / "shared")
if _shared not in sys.path:
    sys.path.insert(0, _shared)

from ngm_shared import variants_page as _impl  # noqa: E402

if __name__ == "__main__":
    sys.exit(_impl.main())
globals().update({k: v for k, v in vars(_impl).items() if not k.startswith("__")})
sys.modules[__name__] = _impl
