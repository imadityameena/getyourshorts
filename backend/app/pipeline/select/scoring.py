"""Step 2: per-candidate signals (0..1) and the weighted score.

score = 0.35·H + 0.40·L + 0.10·K + 0.08·A + 0.04·P + 0.03·V
Missing signals (no heatmap, no AI rating) have their weight redistributed
proportionally over the signals that are present.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.core.config import SelectionConfig, Weights
from app.pipeline.analyze.audio import relative_energy
from app.pipeline.analyze.heatmap import mean_over
from app.pipeline.analyze.scenes import cuts_per_minute
from app.pipeline.models import Candidate, LLMRating, ScoreBreakdown, Signals, Word


@dataclass(frozen=True)
class RawSignals:
    heatmap: float | None
    ai_virality: float | None
    hook: float | None
    audio: float
    pace: float
    visual: float


def effective_weights(w: Weights, present: dict[str, bool]) -> dict[str, float]:
    """Drop absent signals and rescale the rest to sum to 1."""
    base = w.model_dump()
    kept = {k: v for k, v in base.items() if present.get(k, True)}
    total = sum(kept.values())
    if total <= 0:
        return {k: 0.0 for k in base}
    return {k: (kept[k] / total if k in kept else 0.0) for k in base}


def combine(sig: RawSignals, w: Weights) -> tuple[float, ScoreBreakdown]:
    present = {
        "heatmap": sig.heatmap is not None,
        "ai_virality": sig.ai_virality is not None,
        "hook": sig.hook is not None,
    }
    ew = effective_weights(w, present)
    values = {
        "heatmap": sig.heatmap or 0.0,
        "ai_virality": sig.ai_virality or 0.0,
        "hook": sig.hook or 0.0,
        "audio": sig.audio,
        "pace": sig.pace,
        "visual": sig.visual,
    }
    score = sum(ew[k] * values[k] for k in ew)
    bd = ScoreBreakdown(
        heatmap=sig.heatmap,
        ai_virality=sig.ai_virality,
        hook=sig.hook,
        audio=round(sig.audio, 4),
        pace=round(sig.pace, 4),
        visual=round(sig.visual, 4),
        weights={k: round(v, 4) for k, v in ew.items()},
    )
    return round(score, 4), bd


def pace_signal(
    words: Sequence[Word], start: float, end: float, target_wps: float, silence_s: float
) -> float:
    """Words/sec relative to target, minus the fraction of time lost to long silences."""
    dur = end - start
    if dur <= 0 or not words:
        return 0.0
    wps = len(words) / dur
    silent = sum(
        max(0.0, b.start - a.end)
        for a, b in zip(words, words[1:], strict=False)
        if b.start - a.end > silence_s
    )
    return max(0.0, min(1.0, wps / target_wps) - silent / dur)


def ai_signals(r: LLMRating | None) -> tuple[float | None, float | None]:
    """(L, K): L = mean(standalone, payoff, emotion)/10, K = hook/10."""
    if r is None:
        return None, None
    return (r.standalone + r.payoff + r.emotion) / 30.0, r.hook / 10.0


def raw_signals(
    c: Candidate,
    words: Sequence[Word],
    signals: Signals,
    cfg: SelectionConfig,
    rating: LLMRating | None = None,
) -> RawSignals:
    cw = words[c.word_start : c.word_end]
    l_sig, k_sig = ai_signals(rating)
    return RawSignals(
        heatmap=mean_over(signals.heatmap, c.start, c.end) if signals.heatmap else None,
        ai_virality=l_sig,
        hook=k_sig,
        audio=relative_energy(signals.rms, signals.rms_hop_s, c.start, c.end),
        pace=pace_signal(cw, c.start, c.end, cfg.target_wps, cfg.max_inner_silence_s),
        visual=min(1.0, cuts_per_minute(signals.scene_cuts, c.start, c.end) / cfg.max_cuts_per_min),
    )


def prescore(c: Candidate, words: Sequence[Word], signals: Signals, cfg: SelectionConfig) -> float:
    """Cheap score used before calling the AI: the formula without AI terms."""
    score, _ = combine(raw_signals(c, words, signals, cfg), cfg.weights)
    return score
