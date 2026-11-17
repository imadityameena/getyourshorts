import pytest

from app.core.config import CaptionsConfig, CaptionStyle
from app.pipeline.render.captions import (
    ass_color,
    ass_time,
    build_ass,
    build_events,
    group_words,
)
from tests.conftest import make_words

STYLE = CaptionStyle(primary="FFFFFF", highlight="00E5FF", uppercase=True)


def test_ass_color_is_bgr() -> None:
    assert ass_color("FF0000") == "&H000000FF"
    assert ass_color("#00E5FF") == "&H00FFE500"
    with pytest.raises(ValueError):
        ass_color("FFF")


def test_ass_time() -> None:
    assert ass_time(0) == "0:00:00.00"
    assert ass_time(61.234) == "0:01:01.23"
    assert ass_time(3725.5) == "1:02:05.50"
    assert ass_time(-1) == "0:00:00.00"


def test_groups_at_most_three_words() -> None:
    words = make_words("one two three four five six seven")
    groups = group_words(words, 3)
    assert all(1 <= len(g) <= 3 for g in groups)
    assert sum(len(g) for g in groups) == 7


def test_groups_break_on_punctuation_and_pause() -> None:
    words = make_words("hi there. so what now", gaps={4: 1.0})
    groups = group_words(words, 3)
    assert [[w.text for w in g] for g in groups] == [["hi", "there."], ["so", "what"], ["now"]]


def test_events_highlight_each_word_once_and_dont_overlap() -> None:
    words = make_words("alpha beta gamma delta epsilon")
    events = build_events(words, STYLE, 3)
    assert len(events) == 5
    hi = ass_color(STYLE.highlight)
    for e, w in zip(events, words, strict=True):
        assert e.text.count(hi) == 1
        assert f"{{\\c{hi}}}{w.text.upper()}" in e.text
    for a, b in zip(events, events[1:], strict=False):
        assert a.end <= b.start + 1e-9
        assert a.start < a.end


def test_event_timing_follows_words() -> None:
    words = make_words("a b c")
    events = build_events(words, STYLE, 3)
    assert events[0].start == words[0].start
    assert events[1].start == words[1].start
    assert events[0].end == words[1].start


def test_escapes_override_braces() -> None:
    words = make_words("{evil} \\N text")
    out = build_ass(words, CaptionsConfig(), "bold")
    body = out.split("[Events]")[1]
    assert "{evil}" not in body and "(EVIL)" in body


def test_build_ass_header_and_lines() -> None:
    words = make_words("hello world again")
    cfg = CaptionsConfig(font="Montserrat", font_size=84, outline=4, margin_v=560)
    out = build_ass(words, cfg, "bold")
    assert "PlayResX: 1080" in out and "PlayResY: 1920" in out
    assert "Style: Default,Montserrat,84," in out
    assert out.count("Dialogue:") == 3
    # unknown style falls back to the first configured one
    assert build_ass(words, cfg, "nope").count("Dialogue:") == 3


def test_lowercase_style() -> None:
    words = make_words("Hello")
    events = build_events(words, CaptionStyle(uppercase=False), 3)
    assert "Hello" in events[0].text
