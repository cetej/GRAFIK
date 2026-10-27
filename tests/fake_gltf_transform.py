"""Stands in for `node …/gltf-transform/cli/bin/cli.js` in the 3D tests: `optimize SRC DST …` writes a GLB
half the size of SRC, `--version` prints 0.0.0-fake. FAKE_GLTF_MODE=crash exits 1, =garbage writes a non-GLB."""
import os
import sys
from pathlib import Path

args = sys.argv[1:]
if args == ["--version"]:
    print("0.0.0-fake")
    sys.exit(0)
mode = os.environ.get("FAKE_GLTF_MODE", "")
if mode == "crash":
    print("Error: unsupported extension", file=sys.stderr)
    sys.exit(1)
src, dst = Path(args[1]), Path(args[2])
data = src.read_bytes()
Path(dst).write_bytes(b"nope" if mode == "garbage" else data[: max(12, len(data) // 2)])
print(f"info: {src.name} -> {dst.name}")
