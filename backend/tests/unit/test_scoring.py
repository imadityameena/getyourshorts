import pytest

from app.core.config import SelectionConfig, Weights
from app.pipeline.analyze.audio import relative_energy
from app.pipeline.analyze.heatmap import mean_over
from app.pipeline.analyze.scenes import cuts_per_minute
from app.pipeline.models import Candidate, HeatPoint, LLMRating, Signals
from app.pipeline.select.scoring import (
    RawSignals,
    ai_signals,
    combine,
    effective_weights,
    pace_signal,
    raw_signals,
)
from tests.conftest import make_words

W = Weights()


def test_weights_sum_to_one() -> None:
    assert sum(W.model_dump().values()) == pytest.approx(1.0)


def test_full_formula() -> None:
    sig = RawSignals(heatmap=1.0, ai_virality=0.5, hook=0.2, audio=0.4, pace=1.0, visual=0.0)
    score, bd = combine(sig, W)
    expected = 0.35 * 1 + 0.40 * 0.5 + 0.10 * 0.2 + 0.08 * 0.4 + 0.04 * 1 + 0.03 * 0
    assert score == pytest.approx(expected, abs=1e-4)
    assert bd.weights["heatmap"] == pytest.approx(0.35)


def test_missing_heatmap_redistributes_proportionally() -> None:
    ew = effective_weights(W, {"heatmap": False})
    assert ew["heatmap"] == 0
    assert sum(ew.values()) == pytest.approx(1.0)
    assert ew["ai_virality"] == pytest.approx(0.40 / 0.65)
    assert ew["audio"] / ew["pace"] == pytest.approx(0.08 / 0.04)


def test_missing_ai_and_heatmap() -> None:
    sig = RawSignals(heatmap=None, ai_virality=None, hook=None, audio=1.0, pace=1.0, visual=1.0)
    score, bd = combine(sig, W)
    assert score == pytest.approx(1.0)
    assert bd.heatmap is None and bd.ai_virality is None


def test_all_zero_weights_safe() -> None:
    ew = effective_weights(Weights(heatmap=0, ai_virality=0, hook=0, audio=0, pace=0, visual=0), {})
    assert all(v == 0 for v in ew.values())


def test_score_is_monotonic_in_each_signal() -> None:
    base = RawSignals(heatmap=0.5, ai_virality=0.5, hook=0.5, audio=0.5, pace=0.5, visual=0.5)
    s0, _ = combine(base, W)
    for field in ("heatmap", "ai_virality", "hook", "audio", "pace", "visual"):
        bumped = RawSignals(**{**base.__dict__, field: 0.9})
        assert combine(bumped, W)[0] > s0


def test_ai_signals() -> None:
    r = LLMRating(id=0, hook=8, standalone=6, payoff=9, emotion=3, title="t")
    l_sig, k_sig = ai_signals(r)
    assert l_sig == pytest.approx(0.6)
    assert k_sig == pytest.approx(0.8)
    assert ai_signals(None) == (None, None)


def test_pace_penalises_silence() -> None:
    dense = make_words(" ".join(["w"] * 30), wps=3)
    sparse = make_words(" ".join(["w"] * 30), wps=3, gaps={10: 3.0, 20: 3.0})
    p_dense = pace_signal(dense, dense[0].start, dense[-1].end, 3.0, 0.6)
    p_sparse = pace_signal(sparse, sparse[0].start, sparse[-1].end, 3.0, 0.6)
    assert p_dense > 0.9
    assert p_sparse < p_dense - 0.2
    assert pace_signal([], 0, 10, 3, 0.6) == 0.0


def test_heatmap_time_weighted_mean() -> None:
    hm = [HeatPoint(start=0, end=10, value=0.2), HeatPoint(start=10, end=20, value=1.0)]
    assert mean_over(hm, 0, 20) == pytest.approx(0.6)
    assert mean_over(hm, 5, 15) == pytest.approx(0.6)
    assert mean_over(hm, 15, 20) == pytest.approx(1.0)
    assert mean_over(hm, 30, 40) == 0.0
    assert mean_over(hm, 5, 5) == 0.0


def test_relative_energy() -> None:
    rms = [0.1] * 10 + [0.3] * 10  # mean 0.2
    assert relative_energy(rms, 1.0, 10, 20) == pytest.approx(0.75)
    assert relative_energy(rms, 1.0, 0, 10) == pytest.approx(0.25)
    assert relative_energy([], 1.0, 0, 10) == 0.5
    assert relative_energy([0.0] * 5, 1.0, 0, 5) == 0.0


def test_cuts_per_minute() -> None:
    assert cuts_per_minute([5, 10, 50, 70], 0, 60) == pytest.approx(3.0)
    assert cuts_per_minute([], 0, 60) == 0.0
    assert cuts_per_minute([1], 10, 10) == 0.0


def test_raw_signals_end_to_end() -> None:
    words = make_words(" ".join(["w"] * 90), wps=3)  # 30 s
    sig = Signals(duration=30, heatmap=None, rms_hop_s=0.5, rms=[0.2] * 60, scene_cuts=[5, 10, 15])
    c = Candidate(id=0, start=0, end=30, text="", word_start=0, word_end=90)
    rs = raw_signals(c, words, sig, SelectionConfig())
    assert rs.heatmap is None and rs.ai_virality is None
    assert rs.audio == pytest.approx(0.5)
    assert rs.visual == pytest.approx(6 / 12)
    assert 0.9 < rs.pace <= 1.0
