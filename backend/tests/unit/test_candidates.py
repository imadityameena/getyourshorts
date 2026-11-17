from app.pipeline.models import Candidate, Sentence
from app.pipeline.select.candidates import (
    build_candidates,
    build_sentences,
    overlap_fraction,
    prefilter,
)
from tests.conftest import make_words


def test_sentences_split_on_punctuation() -> None:
    words = make_words("Hello there. How are you? Fine!")
    s = build_sentences(words)
    assert [x.text for x in s] == ["Hello there.", "How are you?", "Fine!"]
    assert s[0].word_start == 0 and s[0].word_end == 2
    assert s[1].word_start == 2 and s[2].word_end == 6


def test_sentences_split_on_long_pause_without_punctuation() -> None:
    words = make_words("one two three four", gaps={2: 2.0})
    s = build_sentences(words, gap_s=1.2)
    assert [x.text for x in s] == ["one two", "three four"]


def test_sentences_split_when_too_long() -> None:
    words = make_words(" ".join(["w"] * 120), wps=3)  # 40 s with no punctuation
    s = build_sentences(words, max_len_s=10)
    assert len(s) >= 4
    assert all(x.end - x.start <= 10.5 for x in s)


def _sent(start: float, end: float, i: int) -> Sentence:
    return Sentence(start=start, end=end, text=f"s{i}", word_start=i, word_end=i + 1)


def test_candidates_respect_length_window() -> None:
    sents = [_sent(i * 10.0, i * 10.0 + 9.5, i) for i in range(10)]
    cands = build_candidates(sents, min_len=20, max_len=40)
    assert cands
    for c in cands:
        assert 20 <= c.end - c.start <= 40
    # every candidate starts and ends on a sentence boundary
    starts = {s.start for s in sents}
    ends = {s.end for s in sents}
    assert all(c.start in starts and c.end in ends for c in cands)
    assert [c.id for c in cands] == list(range(len(cands)))


def test_candidates_empty_when_nothing_fits() -> None:
    assert build_candidates([_sent(0, 5, 0)], 15, 30) == []


def test_overlap_fraction() -> None:
    assert overlap_fraction(0, 10, 5, 15) == 0.5
    assert overlap_fraction(0, 10, 20, 30) == 0.0
    assert overlap_fraction(0, 10, 0, 10) == 1.0
    assert overlap_fraction(5, 5, 0, 10) == 0.0


def _cand(i: int, start: float, end: float, pre: float) -> Candidate:
    return Candidate(id=i, start=start, end=end, text="", word_start=0, word_end=0, prescore=pre)


def test_prefilter_prefers_diverse_then_fills() -> None:
    cands = [
        _cand(0, 0, 30, 0.9),
        _cand(1, 1, 31, 0.85),  # near-duplicate of 0
        _cand(2, 100, 130, 0.5),
        _cand(3, 200, 230, 0.4),
    ]
    out = prefilter(cands, top_k=3, max_overlap=0.6)
    assert [c.id for c in out] == [0, 2, 3]
    out = prefilter(cands, top_k=4, max_overlap=0.6)
    assert {c.id for c in out} == {0, 1, 2, 3}
