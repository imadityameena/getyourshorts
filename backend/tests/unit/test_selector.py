from app.core.config import SelectionConfig
from app.pipeline.models import (
    HeatPoint,
    JobSettings,
    LLMRating,
    LLMResult,
    Segment,
    Signals,
    Transcript,
)
from app.pipeline.select.candidates import overlap_fraction
from app.pipeline.select.selector import select, shortlist
from tests.conftest import make_words


def _transcript(minutes: float = 10) -> Transcript:
    n_sent = int(minutes * 60 / 5)
    text = " ".join("this is a fairly normal sentence with words." for _ in range(n_sent))
    words = make_words(text, wps=2.0)  # 10 words/sentence → ~5 s per sentence
    return Transcript(
        language="en",
        duration=words[-1].end,
        segments=[Segment(start=words[0].start, end=words[-1].end, text=text, words=words)],
    )


def _signals(t: Transcript, heat_peak: float | None) -> Signals:
    hm = None
    if heat_peak is not None:
        hm = [
            HeatPoint(start=s, end=s + 10, value=1.0 if abs(s - heat_peak) < 40 else 0.1)
            for s in range(0, int(t.duration) + 10, 10)
        ]
    return Signals(
        duration=t.duration,
        heatmap=hm,
        rms_hop_s=0.5,
        rms=[0.1] * int(t.duration * 2 + 2),
        scene_cuts=[],
    )


def test_selection_respects_count_length_and_overlap() -> None:
    t = _transcript()
    sig = _signals(t, heat_peak=300)
    js = JobSettings(num_clips=4, min_len=20, max_len=40)
    cfg = SelectionConfig()
    sl = shortlist(t, sig, js, cfg)
    assert 0 < len(sl) <= cfg.prefilter_top_k
    sel = select(sl, LLMResult(provider=None, ratings={}), t, sig, js, cfg)
    assert len(sel.clips) == 4
    assert [c.rank for c in sel.clips] == [1, 2, 3, 4]
    scores = [c.score for c in sel.clips]
    assert scores == sorted(scores, reverse=True)
    for c in sel.clips:
        assert 20 - 1 <= c.output_duration <= 40 + 1
        assert not c.ai_ranked and "unavailable" in c.reason
    for i, a in enumerate(sel.clips):
        for b in sel.clips[i + 1 :]:
            assert overlap_fraction(b.start, b.end, a.start, a.end) <= cfg.max_overlap + 0.02
    # the top clip sits on the heatmap peak
    assert 250 <= sel.clips[0].start <= 350


def test_ai_rating_can_promote_a_clip() -> None:
    t = _transcript(5)
    sig = _signals(t, heat_peak=None)
    js = JobSettings(num_clips=1, min_len=20, max_len=30)
    cfg = SelectionConfig()
    sl = shortlist(t, sig, js, cfg)
    target = sl[-1]
    ratings = {
        target.id: LLMRating(
            id=target.id,
            hook=10,
            standalone=10,
            payoff=10,
            emotion=10,
            title="Banger",
            hook_line="Watch this",
            reason="Peak.",
        )
    }
    sel = select(sl, LLMResult(provider="gemini", ratings=ratings), t, sig, js, cfg)
    assert sel.clips[0].candidate_id == target.id
    assert sel.clips[0].title == "Banger" and sel.clips[0].ai_ranked
    assert sel.ai_provider == "gemini"


def test_short_video_still_yields_a_clip() -> None:
    t = _transcript(0.4)  # 24 s of speech, shorter than min_len 30
    sig = _signals(t, None)
    js = JobSettings(num_clips=3, min_len=30, max_len=60)
    sl = shortlist(t, sig, js, SelectionConfig())
    assert sl
