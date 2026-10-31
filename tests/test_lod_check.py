"""scripts/3d/lod_check.py: the numbers it judges a model by; engine/blender/inspect_model.py in a real Blender
(skips itself when Blender is not installed)."""
from __future__ import annotations

import importlib.util
import json
import struct
import subprocess
from pathlib import Path

import numpy as np
import pytest

from engine.config import Settings

REPO = Path(__file__).resolve().parents[1]
INSPECT = REPO / "engine" / "blender" / "inspect_model.py"
_spec = importlib.util.spec_from_file_location("lod_check", REPO / "scripts" / "3d" / "lod_check.py")
lod_check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lod_check)

TRIS = [(0, 2, 3), (0, 3, 1), (4, 5, 7), (4, 7, 6), (0, 1, 5), (0, 5, 4),
        (2, 6, 7), (2, 7, 3), (0, 4, 6), (0, 6, 2), (1, 3, 7), (1, 7, 5)]


def _box(lo, hi):
    return [(x, y, z) for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]


def _glb(path: Path, boxes) -> None:
    """Boxes in glTF order (x, y up, z), every face corner its own vertex as the generators write them."""
    verts = [p for box in boxes for tri in TRIS for p in (box[i] for i in tri)]
    pos = b"".join(struct.pack("<3f", *p) for p in verts)
    arr = np.array(verts)
    gltf = {
        "asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
        "buffers": [{"byteLength": len(pos)}], "bufferViews": [{"buffer": 0, "byteLength": len(pos)}],
        "accessors": [{"bufferView": 0, "componentType": 5126, "count": len(verts), "type": "VEC3",
                       "min": arr.min(axis=0).tolist(), "max": arr.max(axis=0).tolist()}],
    }
    js = json.dumps(gltf).encode()
    js += b" " * (-len(js) % 4)
    body = struct.pack("<II", len(js), 0x4E4F534A) + js + struct.pack("<II", len(pos), 0x004E4942) + pos
    path.write_bytes(struct.pack("<III", 0x46546C67, 2, 12 + len(body)) + body)


def _report(**kw):
    base = {"delka": 4.74, "sirka": 1.67, "vyska": 1.5, "prurezy": {},
            "casti": {"bez_kontaktu": [], "fragmentu_navic": 0}}
    return base | kw


def test_dims_come_from_the_script_table(tmp_path):
    lod = tmp_path / "lod_x.py"
    lod.write_text('import bpy\nDIM = {"length": 4.0, "width": 2.0, "height": 1.0, "wheel": 0.3}\n', encoding="utf-8")
    assert lod_check.dims_from_lod(lod) == [4.0, 2.0, 1.0]
    lod.write_text('DIM = {"shoulder": 3.0}\n', encoding="utf-8")
    assert lod_check.dims_from_lod(lod) is None
    assert lod_check.dims_from_lod(REPO / "scripts" / "3d" / "lod_tatra87.py") == [4.74, 1.67, 1.50]


def test_ratio_inside_and_outside_the_tolerance():
    dims = [4.74, 1.67, 1.5]
    assert lod_check.problems(_report(vyska=1.568), dims, 5, None) == []     # the Tatra from dimensions: +3.8 %
    found = lod_check.problems(_report(delka=1.0935, sirka=0.5787, vyska=0.4772), dims, 5, None)  # raw Hunyuan3D
    assert len(found) == 2 and "+50.2 %" in found[0]


def test_loose_parts_and_extra_limbs_are_problems():
    casti = {"bez_kontaktu": [{"stred": [-1.95, 0, 1.75], "rozmer": [0.1, 0.1, 0.1], "mezera": 0.3}],
             "fragmentu_navic": 2}
    assert len(lod_check.problems(_report(casti=casti), None, 5, None)) == 2
    cuts = {"0.25": [[0, 0]] * 6, "0.75": [[0, 0]] * 9}                      # above half of the height it may be anything
    assert len(lod_check.problems(_report(prurezy=cuts), None, 5, 5)) == 1
    assert lod_check.problems(_report(prurezy=cuts), None, 5, 6) == []


def test_outline_compares_shape_at_the_same_length():
    ref = np.zeros((300, 1000), np.uint8)
    ref[100:300, :] = 1
    same = lod_check.compare_outline(ref, ref)
    assert same["iou"] == 1.0 and same["obrys_odchylka_pct"]["konec"] == 0
    short_tail = ref.copy()
    short_tail[100:200, 700:] = 0                                            # lower only over the last third
    off = lod_check.compare_outline(short_tail, ref)
    assert off["obrys_odchylka_pct"]["konec"] == pytest.approx(9, abs=0.1)   # 300 of the third's 334 columns, 10 % each
    assert off["obrys_odchylka_pct"]["zacatek"] == 0


def test_inspect_finds_the_loose_part_in_a_real_blender(tmp_path):
    blender = Settings().blender_cmd
    if not Path(blender[0]).is_file():
        pytest.skip("Blender není nainstalovaný (GRAFIK_BLENDER)")
    glb = tmp_path / "model.glb"
    _glb(glb, [_box((0, 0, 0), (4, 1, 2)),            # body
               _box((1, -0.5, 0.5), (2, 0.5, 1.5)),   # sinks into the body: touching
               _box((6, 0, 0), (6.5, 0.5, 0.5))])     # 2 m away
    run = subprocess.run([*blender, str(INSPECT), "--", str(glb), str(tmp_path), "--no-render"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    assert run.returncode == 0, run.stderr[-2000:]
    report = json.loads((tmp_path / "inspect.json").read_text(encoding="utf-8"))
    assert report["casti"]["celkem"] == 3
    assert report["hrany_otevrene"] == 0 and report["hrany_sdilene_vic_nez_2"] == 0   # welded although unwelded on disk
    loose = report["casti"]["bez_kontaktu"]
    assert len(loose) == 1 and loose[0]["mezera"] == pytest.approx(2.0, abs=0.01)
    assert report["delka"] == pytest.approx(6.5, abs=0.01)
    assert len(report["prurezy"]["0.50"]) == 2                                # body with the sinking box, separate box
