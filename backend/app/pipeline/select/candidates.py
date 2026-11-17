"""Step 1: sentences → sliding-window candidates → cheap pre-score → top K."""

from __future__ import annotations

from collections.abc import Sequence

from app.pipeline.models import Candidate, Sentence, Word

_END_PUNCT = (".", "?", "!", "…", "。", "？", "！")


def build_sentences(
    words: Sequence[Word], gap_s: float = 1.2, max_len_s: float = 20.0
) -> list[Sentence]:
    """Split words into sentences on terminal punctuation, long pauses, or excessive length."""
    out: list[Sentence] = []
    start = 0
    for i, w in enumerate(words):
        last = i == len(words) - 1
        ends = w.text.rstrip("\"')]").endswith(_END_PUNCT)
        long_gap = not last and words[i + 1].start - w.end >= gap_s
        too_long = w.end - words[start].start >= max_len_s
        if last or ends or long_gap or too_long:
            chunk = words[start : i + 1]
            out.append(
                Sentence(
                    start=chunk[0].start,
                    end=chunk[-1].end,
                    text=" ".join(x.text for x in chunk),
                    word_start=start,
                    word_end=i + 1,
                )
            )
            start = i + 1
    return out


def build_candidates(
    sentences: Sequence[Sentence], min_len: float, max_len: float
) -> list[Candidate]:
    """Every run of consecutive sentences whose span is within [min_len, max_len]."""
    out: list[Candidate] = []
    n = len(sentences)
    for i in range(n):
        for j in range(i, n):
            dur = sentences[j].end - sentences[i].start
            if dur > max_len:
                break
            if dur >= min_len:
                out.append(
                    Candidate(
                        id=len(out),
                        start=sentences[i].start,
                        end=sentences[j].end,
                        text=" ".join(s.text for s in sentences[i : j + 1]),
                        word_start=sentences[i].word_start,
                        word_end=sentences[j].word_end,
                    )
                )
    return out


def overlap_fraction(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    """Overlap as a fraction of interval a's length."""
    inter = max(0.0, min(a_end, b_end) - max(a_start, b_start))
    length = a_end - a_start
    return inter / length if length > 0 else 0.0


def prefilter(cands: Sequence[Candidate], top_k: int, max_overlap: float) -> list[Candidate]:
    """Top-K by prescore, preferring diverse regions so the AI sees the whole video.

    First pass keeps candidates that don't overlap an already-kept one by more than
    `max_overlap`; if that yields fewer than K, the best remaining fill the gap.
    """
    ranked = sorted(cands, key=lambda c: c.prescore, reverse=True)
    kept: list[Candidate] = []
    rest: list[Candidate] = []
    for c in ranked:
        if len(kept) >= top_k:
            break
        if all(overlap_fraction(c.start, c.end, k.start, k.end) <= max_overlap for k in kept):
            kept.append(c)
        else:
            rest.append(c)
    if len(kept) < top_k:
        seen = {c.id for c in kept}
        for c in rest + ranked:
            if len(kept) >= top_k:
                break
            if c.id not in seen:
                kept.append(c)
                seen.add(c.id)
    return kept
