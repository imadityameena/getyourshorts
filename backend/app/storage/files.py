"""Storage layout, atomic JSON I/O, cache validity checks and cleanup.

storage/{video_id}/                video-level cache (shared by all settings)
    source.mp4  audio.wav  meta.json  transcript.json  signals.json
storage/{video_id}/{settings_hash}/
    candidates.json  llm.json  selection.json  render.json  clips/clip_01.mp4 ...  shorts.zip
"""

from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.core.errors import InsufficientDisk

M = TypeVar("M", bound=BaseModel)


@dataclass(frozen=True)
class VideoPaths:
    root: Path

    @property
    def source(self) -> Path:
        return self.root / "source.mp4"

    @property
    def audio(self) -> Path:
        return self.root / "audio.wav"

    @property
    def meta(self) -> Path:
        return self.root / "meta.json"

    @property
    def transcript(self) -> Path:
        return self.root / "transcript.json"

    @property
    def signals(self) -> Path:
        return self.root / "signals.json"

    @property
    def scenes(self) -> Path:
        return self.root / "scenes.json"


@dataclass(frozen=True)
class JobPaths:
    root: Path

    @property
    def candidates(self) -> Path:
        return self.root / "candidates.json"

    @property
    def llm(self) -> Path:
        return self.root / "llm.json"

    @property
    def selection(self) -> Path:
        return self.root / "selection.json"

    @property
    def render(self) -> Path:
        return self.root / "render.json"

    @property
    def clips_dir(self) -> Path:
        return self.root / "clips"

    @property
    def zip(self) -> Path:
        return self.root / "shorts.zip"

    def clip(self, rank: int) -> Path:
        return self.clips_dir / f"clip_{rank:02d}.mp4"

    def thumb(self, rank: int) -> Path:
        return self.clips_dir / f"clip_{rank:02d}.jpg"


def video_paths(storage: Path, video_id: str) -> VideoPaths:
    p = VideoPaths(storage / video_id)
    p.root.mkdir(parents=True, exist_ok=True)
    return p


def job_paths(storage: Path, video_id: str, settings_hash: str) -> JobPaths:
    p = JobPaths(storage / video_id / settings_hash)
    p.clips_dir.mkdir(parents=True, exist_ok=True)
    return p


def write_model(path: Path, model: BaseModel) -> None:
    """Atomic write: a crash never leaves a half-written cache file."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(model.model_dump_json(indent=2))
    tmp.replace(path)


def read_model(path: Path, cls: type[M]) -> M:
    return cls.model_validate_json(path.read_text())


def load_valid(path: Path, cls: type[M]) -> M | None:
    """Return the cached model if the file exists and parses, else None."""
    if not path.exists():
        return None
    try:
        return read_model(path, cls)
    except (ValidationError, json.JSONDecodeError, OSError):
        path.unlink(missing_ok=True)
        return None


def file_ok(path: Path, min_bytes: int = 1024) -> bool:
    return path.exists() and path.stat().st_size >= min_bytes


def ensure_disk_space(path: Path, min_free_gb: float) -> None:
    free_gb = shutil.disk_usage(path).free / 1e9
    if free_gb < min_free_gb:
        raise InsufficientDisk(f"{free_gb:.1f} GB free < {min_free_gb} GB")


def free_disk_gb(path: Path) -> float:
    return shutil.disk_usage(path).free / 1e9


def cleanup_old(storage: Path, max_age_hours: float, keep: set[str] | None = None) -> list[str]:
    """Delete video folders not modified within max_age_hours. Returns removed ids."""
    cutoff = time.time() - max_age_hours * 3600
    removed: list[str] = []
    keep = keep or set()
    for d in storage.iterdir():
        if not d.is_dir() or d.name in keep or d.name.startswith("."):
            continue
        newest = max((f.stat().st_mtime for f in d.rglob("*")), default=d.stat().st_mtime)
        if newest < cutoff:
            shutil.rmtree(d, ignore_errors=True)
            removed.append(d.name)
    return removed
