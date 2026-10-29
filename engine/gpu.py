"""GPU guard: free VRAM via nvidia-smi. The machine-wide lock (~/.gpu-lock) lives in
ngm_shared.heavy_lock, shared with every project that runs heavy work."""
from __future__ import annotations

import subprocess


def free_vram_mib() -> int | None:
    """Free memory of GPU 0, or None when nvidia-smi is unavailable."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0 or not out.stdout.strip():
        return None
    return int(out.stdout.splitlines()[0].strip())
