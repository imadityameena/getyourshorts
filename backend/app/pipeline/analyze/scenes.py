"""Visual cut detection.

Uses FFmpeg's scene-change score on a downscaled, low-fps copy of the stream.
FFmpeg decodes with all cores, which makes this several times faster than
frame-by-frame OpenCV decoding (PySceneDetect) on long 1080p videos, and the
signal only carries 3% of the score, so a 4 fps sample is plenty.
"""

from __future__ import annotations

import bisect
import re
from collections.abc import Sequence
from pathlib import Path

from app.core.logging import get_logger
from app.core.retry import run_cmd

log = get_logger("scenes")

SAMPLE_FPS = 4
THRESHOLD = 0.35  # FFmpeg scene score 0..1; ~0.3-0.4 catches hard cuts, ignores motion
MIN_GAP_S = 0.5  # merge detections closer than this (one cut can span 2 samples)

_PTS_RE = re.compile(r"pts_time:([0-9.]+)")


def scene_command(video: Path) -> list[str]:
    vf = f"fps={SAMPLE_FPS},scale=160:-2,select='gt(scene\\,{THRESHOLD})',metadata=print:file=-"
    return [
        "ffmpeg", "-hide_banner", "-nostats", "-v", "error", "-threads", "0",
        # Every frame is still decoded (cuts aren't always on keyframes), but the
        # deblocking filter is skipped: invisible at 160 px, ~25% faster.
        "-skip_loop_filter", "all", "-flags2", "fast",
        "-an", "-sn", "-dn", "-i", str(video),
        "-vf", vf, "-f", "null", "-",
    ]  # fmt: skip


def parse_cuts(output: str) -> list[float]:
    times = sorted(float(m.group(1)) for m in _PTS_RE.finditer(output))
    cuts: list[float] = []
    for t in times:
        if not cuts or t - cuts[-1] >= MIN_GAP_S:
            cuts.append(round(t, 3))
    return cuts


def detect_cuts(video: Path, timeout: float = 1800) -> list[float]:
    """Return cut timestamps in seconds. Failures degrade to [] (the signal weight is tiny)."""
    try:
        out = run_cmd(scene_command(video), timeout=timeout, what="scene detection").stdout
        cuts = parse_cuts(out)
        log.info("scenes_detected", cuts=len(cuts))
        return cuts
    except Exception as e:
        log.warning("scene_detection_failed", error=str(e)[:300])
        return []


def cuts_per_minute(cuts: Sequence[float], start: float, end: float) -> float:
    if end <= start:
        return 0.0
    n = bisect.bisect_right(cuts, end) - bisect.bisect_left(cuts, start)
    return n / ((end - start) / 60.0)
