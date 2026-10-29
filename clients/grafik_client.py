"""Old path of the GRAFIK client: re-exports ngm_shared.grafik_client (GRAFIK/shared/ngm_shared).

`python clients/grafik_client.py ...` and `import grafik_client` with this folder on sys.path keep
working without installing ngm_shared. The import hands over the module itself (sys.modules), so
callers that set grafik_client.ENGINE_URL or monkeypatch it change the real module. Loading this
file by path (importlib spec_from_file_location) gets the same names.
"""
import sys
from pathlib import Path

_shared = str(Path(__file__).resolve().parent.parent / "shared")
if _shared not in sys.path:
    sys.path.insert(0, _shared)

from ngm_shared import grafik_client as _impl  # noqa: E402

if __name__ == "__main__":
    sys.exit(_impl.main())
globals().update({k: v for k, v in vars(_impl).items() if not k.startswith("__")})
sys.modules[__name__] = _impl
