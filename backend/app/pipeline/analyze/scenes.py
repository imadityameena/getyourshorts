"""Visual cut detection with PySceneDetect."""

from __future__ import annotations

import bisect
from collections.abc import Sequence
from pathlib import Path

from app.core.logging import get_logger

log = get_logger("scenes")


def detect_cuts(video: Path) -> list[float]:
    """Return cut timestamps in seconds. Failures degrade to [] (signal weight is tiny)."""
    try:
        from scenedetect import ContentDetector, detect

        scenes = detect(str(video), ContentDetector(threshold=27.0), show_progress=False)
        return [float(start.get_seconds()) for start, _ in scenes[1:]]
    except Exception as e:
        log.warning("scene_detection_failed", error=str(e))
        return []


def cuts_per_minute(cuts: Sequence[float], start: float, end: float) -> float:
    if end <= start:
        return 0.0
    n = bisect.bisect_right(cuts, end) - bisect.bisect_left(cuts, start)
    return n / ((end - start) / 60.0)
