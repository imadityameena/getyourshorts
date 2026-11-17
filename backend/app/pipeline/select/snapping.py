"""Step 4: overlap removal, boundary snapping and inner-silence trimming."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, TypeVar

from app.pipeline.models import Interval, Word
from app.pipeline.select.candidates import overlap_fraction


class HasSpan(Protocol):
    @property
    def start(self) -> float: ...
    @property
    def end(self) -> float: ...


S = TypeVar("S", bound=HasSpan)


def remove_overlaps(ranked: Sequence[S], max_overlap: float, limit: int) -> list[S]:
    """Greedy: walk best-first, drop anything overlapping a chosen clip by > max_overlap.

    The overlap is measured relative to the candidate's own duration.
    """
    chosen: list[S] = []
    for c in ranked:
        if len(chosen) >= limit:
            break
        if all(overlap_fraction(c.start, c.end, k.start, k.end) <= max_overlap for k in chosen):
            chosen.append(c)
    return chosen


@dataclass(frozen=True)
class Snapped:
    start: float
    end: float
    keep: list[Interval]


def snap(
    words: Sequence[Word],
    *,
    pad_start: float,
    pad_end: float,
    max_silence: float,
    video_duration: float,
) -> Snapped:
    """Pad around the first/last word and cut silences longer than `max_silence`.

    Inside a long gap we keep `pad_end` after the previous word and `pad_start`
    before the next one, so words are never clipped.
    """
    if not words:
        raise ValueError("cannot snap an empty clip")
    start = max(0.0, words[0].start - pad_start)
    end = (
        min(video_duration, words[-1].end + pad_end)
        if video_duration > 0
        else words[-1].end + pad_end
    )
    keep: list[Interval] = []
    seg_start = start
    for a, b in zip(words, words[1:], strict=False):
        if b.start - a.end > max_silence:
            keep.append(Interval(start=seg_start, end=a.end + pad_end))
            seg_start = b.start - pad_start
    keep.append(Interval(start=seg_start, end=end))
    return Snapped(start=start, end=end, keep=_merge(keep))


def _merge(ivs: list[Interval]) -> list[Interval]:
    out: list[Interval] = []
    for iv in ivs:
        if out and iv.start <= out[-1].end:
            out[-1] = Interval(start=out[-1].start, end=max(out[-1].end, iv.end))
        else:
            out.append(iv)
    return out


def remap_time(t: float, keep: Sequence[Interval]) -> float | None:
    """Source time → output time after trimming; None if t falls in a removed gap."""
    acc = 0.0
    for iv in keep:
        if t < iv.start:
            return None
        if t <= iv.end:
            return acc + (t - iv.start)
        acc += iv.end - iv.start
    return None


def remap_words(words: Sequence[Word], keep: Sequence[Interval]) -> list[Word]:
    """Shift word timings onto the trimmed output timeline (clamped into kept spans)."""
    out: list[Word] = []
    for w in words:
        s = _remap_clamped(w.start, keep)
        e = _remap_clamped(w.end, keep)
        out.append(w.model_copy(update={"start": s, "end": max(e, s + 0.05)}))
    return out


def _remap_clamped(t: float, keep: Sequence[Interval]) -> float:
    acc = 0.0
    for iv in keep:
        if t <= iv.end:
            return acc + max(0.0, t - iv.start)
        acc += iv.end - iv.start
    return acc
