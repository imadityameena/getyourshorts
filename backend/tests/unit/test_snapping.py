from dataclasses import dataclass

import pytest

from app.pipeline.models import Interval
from app.pipeline.select.snapping import remap_time, remap_words, remove_overlaps, snap
from tests.conftest import make_words


@dataclass
class Span:
    start: float
    end: float
    name: str = ""


def test_remove_overlaps_keeps_best_and_drops_heavy_overlap() -> None:
    ranked = [Span(0, 30, "a"), Span(25, 55, "b"), Span(10, 40, "c"), Span(60, 90, "d")]
    chosen = remove_overlaps(ranked, max_overlap=0.2, limit=5)
    # b overlaps a by 5/30 ≈ 0.167 → kept; c overlaps a by 20/30 → dropped
    assert [c.name for c in chosen] == ["a", "b", "d"]


def test_remove_overlaps_respects_limit() -> None:
    ranked = [Span(i * 100, i * 100 + 30, str(i)) for i in range(10)]
    assert len(remove_overlaps(ranked, 0.2, 3)) == 3


def test_snap_pads_boundaries() -> None:
    words = make_words("a b c d e f", start=10.0)
    sn = snap(words, pad_start=0.15, pad_end=0.3, max_silence=0.6, video_duration=100)
    assert sn.start == pytest.approx(10.0 - 0.15)
    assert sn.end == pytest.approx(words[-1].end + 0.3)
    assert len(sn.keep) == 1


def test_snap_clamps_to_video_bounds() -> None:
    words = make_words("a b", start=0.05)
    sn = snap(
        words, pad_start=0.15, pad_end=0.3, max_silence=0.6, video_duration=words[-1].end + 0.1
    )
    assert sn.start == 0.0
    assert sn.end == pytest.approx(words[-1].end + 0.1)


def test_snap_trims_inner_silence_without_cutting_words() -> None:
    words = make_words("a b c d", start=0.0, gaps={2: 2.0})
    sn = snap(words, pad_start=0.15, pad_end=0.3, max_silence=0.6, video_duration=100)
    assert len(sn.keep) == 2
    first, second = sn.keep
    assert first.end == pytest.approx(words[1].end + 0.3)
    assert second.start == pytest.approx(words[2].start - 0.15)
    for w in words:  # every word lies fully inside a kept interval
        assert any(iv.start <= w.start and w.end <= iv.end for iv in sn.keep)


def test_snap_short_gap_not_trimmed() -> None:
    words = make_words("a b c d", gaps={2: 0.3})
    sn = snap(words, pad_start=0.15, pad_end=0.3, max_silence=0.6, video_duration=100)
    assert len(sn.keep) == 1


def test_snap_merges_when_padding_overlaps() -> None:
    words = make_words("a b", gaps={1: 0.7})  # gap ≈ 0.77 s > 0.6 s
    sn = snap(words, pad_start=0.5, pad_end=0.5, max_silence=0.6, video_duration=100)
    assert len(sn.keep) == 1  # 0.5 + 0.5 padding covers the gap → merged


def test_snap_empty_raises() -> None:
    with pytest.raises(ValueError):
        snap([], pad_start=0.1, pad_end=0.1, max_silence=0.6, video_duration=10)


def test_remap_time() -> None:
    keep = [Interval(start=10, end=20), Interval(start=30, end=35)]
    assert remap_time(10, keep) == 0
    assert remap_time(15, keep) == 5
    assert remap_time(25, keep) is None
    assert remap_time(32, keep) == 12
    assert remap_time(40, keep) is None
    assert remap_time(5, keep) is None


def test_remap_words_monotonic_and_inside_output() -> None:
    words = make_words("a b c d", start=10, gaps={2: 2.0})
    sn = snap(words, pad_start=0.15, pad_end=0.3, max_silence=0.6, video_duration=100)
    out = remap_words(words, sn.keep)
    total = sum(iv.end - iv.start for iv in sn.keep)
    assert out[0].start == pytest.approx(0.15)
    starts = [w.start for w in out]
    assert starts == sorted(starts)
    assert all(0 <= w.start < w.end <= total + 0.05 for w in out)
