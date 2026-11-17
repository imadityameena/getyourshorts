"""Heatmap ("Most Replayed") signal: time-weighted average over a range."""

from __future__ import annotations

from collections.abc import Sequence

from app.pipeline.models import HeatPoint


def mean_over(heatmap: Sequence[HeatPoint], start: float, end: float) -> float:
    """Time-weighted mean of heatmap values over [start, end]; 0 if no coverage."""
    if end <= start:
        return 0.0
    total = 0.0
    covered = 0.0
    for p in heatmap:
        lo, hi = max(start, p.start), min(end, p.end)
        if hi > lo:
            total += p.value * (hi - lo)
            covered += hi - lo
    return total / covered if covered > 0 else 0.0
