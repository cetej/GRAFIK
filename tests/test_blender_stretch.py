"""engine/blender/stretch.py in a real Blender (skips itself when Blender is not installed).

The generators write GLBs with POSITION only, one welded mesh. Re-exported with Blender's default normals, every flat
face got its own vertices: the stretched Tatra 87 went from 249 976 vertices / 9 MB to 1 498 732 / 42 MB, and KLAPKA's
Line Art drew the border of every triangle (GRAFIK#73).
"""
from __future__ import annotations

import json
import struct
import subprocess
from pathlib import Path

import pytest

from engine.config import Settings
from engine.models3d import STRETCH_SCRIPT

CUBE = [(x, y, z) for x in (0.0, 1.0) for y in (0.0, 1.0) for z in (0.0, 1.0)]
CUBE_TRIS = [(0, 2, 3), (0, 3, 1), (4, 5, 7), (4, 7, 6), (0, 1, 5), (0, 5, 4),
             (2, 6, 7), (2, 7, 3), (0, 4, 6), (0, 6, 2), (1, 3, 7), (1, 7, 5)]


def _glb_without_normals(path: Path) -> None:
    pos = b"".join(struct.pack("<3f", *p) for p in CUBE)
    idx = b"".join(struct.pack("<3H", *t) for t in CUBE_TRIS)
    gltf = {
        "asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}],
        "buffers": [{"byteLength": len(pos) + len(idx)}],
        "bufferViews": [{"buffer": 0, "byteLength": len(pos)},
                        {"buffer": 0, "byteOffset": len(pos), "byteLength": len(idx)}],
        "accessors": [{"bufferView": 0, "componentType": 5126, "count": len(CUBE), "type": "VEC3",
                       "min": [0, 0, 0], "max": [1, 1, 1]},
                      {"bufferView": 1, "componentType": 5123, "count": 3 * len(CUBE_TRIS), "type": "SCALAR"}],
    }
    js = json.dumps(gltf).encode()
    js += b" " * (-len(js) % 4)
    binary = pos + idx
    binary += b"\x00" * (-len(binary) % 4)
    body = struct.pack("<II", len(js), 0x4E4F534A) + js + struct.pack("<II", len(binary), 0x004E4942) + binary
    path.write_bytes(struct.pack("<III", 0x46546C67, 2, 12 + len(body)) + body)


def _gltf_json(path: Path) -> dict:
    data = path.read_bytes()
    n = struct.unpack_from("<I", data, 12)[0]
    return json.loads(data[20:20 + n])


def test_stretch_keeps_the_mesh_welded(tmp_path):
    blender = Settings().blender_cmd
    if not Path(blender[0]).is_file():
        pytest.skip("Blender není nainstalovaný (GRAFIK_BLENDER)")
    src, dst = tmp_path / "cube.glb", tmp_path / "stretched.glb"
    _glb_without_normals(src)
    run = subprocess.run([*blender, str(STRETCH_SCRIPT), "--", str(src), str(dst), "4", "1", "1", "all"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    assert run.returncode == 0, run.stderr[-2000:]
    bbox = json.loads(next(line for line in run.stdout.splitlines() if line.startswith("BBOX "))[5:])
    assert sorted(bbox) == [1, 1, 4]
    gltf = _gltf_json(dst)
    attributes = [p["attributes"] for m in gltf["meshes"] for p in m["primitives"]]
    vertices = sum(gltf["accessors"][a["POSITION"]]["count"] for a in attributes)
    assert vertices == len(CUBE)                       # with per-face normals: 24
    assert all("NORMAL" not in a for a in attributes)
