"""GRAFIK Engine settings. Every value can be overridden by an env var
(GRAFIK_<NAME>), tests override by constructing Settings directly."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FLUX_DIR = Path("C:/Users/stock/models/flux3-klein")


def _env(name: str, default):
    raw = os.environ.get(f"GRAFIK_{name}")
    if raw is None:
        return default
    return type(default)(raw) if not isinstance(default, Path) else Path(raw)


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: _env("DATA_DIR", REPO_ROOT))
    flux_dir: Path = field(default_factory=lambda: _env("FLUX_DIR", FLUX_DIR))
    sd_exe: str = "sd/sd-server.exe"
    sd_model: str = "FLUX-3-Image-Klein-AD-Q4_K.gguf"
    sd_llm: str = "text_encoders/Qwen3-VL-4B-Instruct-AD-Q4_K.gguf"
    sd_vae: str = "vae/ae.safetensors"
    sd_port: int = field(default_factory=lambda: _env("SD_PORT", 8390))
    # Same sampler setup as the 2026-10-22 measurements (models/flux3-klein/run.sh).
    steps: int = 16
    cfg_scale: float = 1.0
    sampler: str = "euler"
    idle_timeout_s: float = field(default_factory=lambda: _env("IDLE_TIMEOUT_S", 600.0))
    start_timeout_s: float = 120.0
    job_timeout_s: float = 900.0
    # FLUX Q4 needs ~4.45 GB of device memory per image (sd-server log 2026-10-23, auto-fit offloads
    # the rest); below this someone else (dubbing, Whisper, Illustrator) holds the GPU.
    min_free_vram_mib: int = field(default_factory=lambda: _env("MIN_FREE_VRAM_MIB", 4600))
    gpu_lock_path: Path = field(default_factory=lambda: _env("GPU_LOCK", Path.home() / ".gpu-lock"))
    gpu_lock_wait_s: float = 600.0
    # Q4 weights on 8 GB: 1920x1088 is the measured ceiling.
    max_pixels: int = 1920 * 1088
    vae_tiling_above_pixels: int = 1280 * 1280

    @property
    def library_dir(self) -> Path:
        return self.data_dir / "library"

    @property
    def run_dir(self) -> Path:
        return self.data_dir / "run"

    @property
    def log_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def db_path(self) -> Path:
        return self.run_dir / "jobs.sqlite"

    @property
    def reflib_dir(self) -> Path:
        return self.data_dir / "refs" / "library"

    @property
    def styles_dir(self) -> Path:
        return self.data_dir / "styles"

    @property
    def translations_path(self) -> Path:
        return self.library_dir / "translations.jsonl"

    @property
    def costs_path(self) -> Path:
        return self.library_dir / "costs.jsonl"
