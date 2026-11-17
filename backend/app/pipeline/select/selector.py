"""Glue for steps 1–4 of the selection algorithm."""

from __future__ import annotations

from collections.abc import Sequence

from app.core.config import SelectionConfig
from app.pipeline.models import (
    Candidate,
    JobSettings,
    LLMResult,
    ScoreBreakdown,
    SelectedClip,
    Selection,
    Signals,
    Transcript,
    Word,
)
from app.pipeline.select.candidates import build_candidates, build_sentences, prefilter
from app.pipeline.select.scoring import combine, prescore, raw_signals
from app.pipeline.select.snapping import remove_overlaps, snap


def shortlist(
    transcript: Transcript, signals: Signals, settings: JobSettings, cfg: SelectionConfig
) -> list[Candidate]:
    """Build all candidates, pre-score them cheaply, keep the top K for the AI."""
    words = transcript.words()
    sentences = build_sentences(words, gap_s=cfg.sentence_gap_s, max_len_s=settings.max_len)
    cands = build_candidates(sentences, settings.min_len, settings.max_len)
    if not cands:
        # Short or sparse video: fall back to the whole speech span chunked by max_len.
        cands = build_candidates(sentences, min(15.0, settings.min_len), settings.max_len)
    for c in cands:
        c.prescore = prescore(c, words, signals, cfg)
    return prefilter(cands, cfg.prefilter_top_k, cfg.prefilter_max_overlap)


def _fallback_title(text: str) -> str:
    words = text.split()
    t = " ".join(words[:9])
    return (t[:57] + "...") if len(t) > 60 else t


def _first_sentence(words: Sequence[Word]) -> str:
    out: list[str] = []
    for w in words:
        out.append(w.text)
        if w.text.endswith((".", "?", "!")) or len(out) >= 14:
            break
    return " ".join(out)[:80]


def select(
    shortlisted: Sequence[Candidate],
    llm: LLMResult,
    transcript: Transcript,
    signals: Signals,
    settings: JobSettings,
    cfg: SelectionConfig,
) -> Selection:
    words = transcript.words()
    scored: list[tuple[float, Candidate, ScoreBreakdown]] = []
    for c in shortlisted:
        rating = llm.ratings.get(c.id)
        score, bd = combine(raw_signals(c, words, signals, cfg, rating), cfg.weights)
        scored.append((score, c, bd))
    scored.sort(key=lambda x: x[0], reverse=True)

    by_id = {c.id: (s, bd) for s, c, bd in scored}
    ranked = [c for _, c, _ in scored]
    chosen = remove_overlaps(ranked, cfg.max_overlap, settings.num_clips)

    clips: list[SelectedClip] = []
    for rank, c in enumerate(chosen, start=1):
        cw = words[c.word_start : c.word_end]
        sn = snap(
            cw,
            pad_start=cfg.pad_start_s,
            pad_end=cfg.pad_end_s,
            max_silence=cfg.max_inner_silence_s,
            video_duration=signals.duration,
        )
        score, bd = by_id[c.id]
        r = llm.ratings.get(c.id)
        clips.append(
            SelectedClip(
                rank=rank,
                candidate_id=c.id,
                start=sn.start,
                end=sn.end,
                keep=sn.keep,
                score=score,
                breakdown=bd,
                title=(r.title if r and r.title else _fallback_title(c.text)),
                hook_line=(r.hook_line if r and r.hook_line else _first_sentence(cw)),
                reason=(
                    r.reason if r else "AI ranking unavailable; ranked by heatmap, audio and pace."
                ),
                ai_ranked=r is not None,
                word_start=c.word_start,
                word_end=c.word_end,
            )
        )
    return Selection(ai_provider=llm.provider, clips=clips)
