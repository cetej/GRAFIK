"""Default Blender path: newest 5.2.x in the shared AppData install, fallback to the old tools copy."""
from __future__ import annotations

from engine.config import BLENDER_FALLBACK, find_blender


def _make(base, *names):
    for name in names:
        (base / name).mkdir(parents=True)
        (base / name / "blender.exe").write_bytes(b"")


def test_newest_52x_wins_and_other_series_is_ignored(tmp_path):
    _make(tmp_path, "blender-5.2.2-windows-x64", "blender-5.2.3-windows-x64", "blender-5.3.0-windows-x64")
    assert find_blender(tmp_path).endswith("blender-5.2.3-windows-x64/blender.exe")


def test_numeric_not_lexical_order(tmp_path):
    _make(tmp_path, "blender-5.2.9-windows-x64", "blender-5.2.10-windows-x64")
    assert "5.2.10" in find_blender(tmp_path)


def test_empty_or_missing_dir_falls_back(tmp_path):
    assert find_blender(tmp_path) == BLENDER_FALLBACK
    assert find_blender(tmp_path / "neexistuje") == BLENDER_FALLBACK
