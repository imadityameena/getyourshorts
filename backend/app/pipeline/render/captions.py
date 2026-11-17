"""Build an .ass subtitle file with word-by-word highlighting (2–3 words on screen)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.core.config import CaptionsConfig, CaptionStyle
from app.pipeline.models import Word

GROUP_BREAK_GAP_S = 0.45
HOLD_AFTER_S = 0.25
STYLE_FORMAT = (
    "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
    "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
    "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding"
)


def ass_color(rrggbb: str) -> str:
    """'RRGGBB' → ASS '&H00BBGGRR'."""
    h = rrggbb.lstrip("#").upper()
    if len(h) != 6:
        raise ValueError(f"bad color {rrggbb!r}")
    return f"&H00{h[4:6]}{h[2:4]}{h[0:2]}"


def ass_time(t: float) -> str:
    """Seconds → H:MM:SS.cc (centiseconds)."""
    cs = max(0, round(t * 100))
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, c = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{c:02d}"


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", " ")


def group_words(words: Sequence[Word], max_words: int) -> list[list[Word]]:
    """Up to max_words per group; break early after sentence punctuation or a pause."""
    groups: list[list[Word]] = []
    cur: list[Word] = []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        end_sentence = w.text.endswith((".", "?", "!", ","))
        pause = nxt is not None and nxt.start - w.end > GROUP_BREAK_GAP_S
        if len(cur) >= max_words or end_sentence or pause or nxt is None:
            groups.append(cur)
            cur = []
    return groups


@dataclass(frozen=True)
class Event:
    start: float
    end: float
    text: str


def build_events(words: Sequence[Word], style: CaptionStyle, max_words: int) -> list[Event]:
    groups = group_words(words, max_words)
    hi = ass_color(style.highlight)
    base = ass_color(style.primary)
    events: list[Event] = []
    for gi, g in enumerate(groups):
        next_start = groups[gi + 1][0].start if gi + 1 < len(groups) else None
        g_end = g[-1].end + HOLD_AFTER_S
        if next_start is not None:
            g_end = min(g_end, next_start)
        tokens = [_escape(w.text.upper() if style.uppercase else w.text) for w in g]
        for wi, w in enumerate(g):
            start = w.start if wi > 0 else g[0].start
            end = g[wi + 1].start if wi + 1 < len(g) else g_end
            if end - start < 0.02:
                continue
            parts = [
                (f"{{\\c{hi}}}{t}{{\\c{base}}}" if k == wi else t) for k, t in enumerate(tokens)
            ]
            events.append(Event(start=start, end=end, text=" ".join(parts)))
    return events


def build_ass(
    words: Sequence[Word],
    cfg: CaptionsConfig,
    style_name: str,
    width: int = 1080,
    height: int = 1920,
) -> str:
    style = cfg.styles.get(style_name) or next(iter(cfg.styles.values()))
    primary = ass_color(style.primary)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
{STYLE_FORMAT}
Style: Default,{cfg.font},{cfg.font_size},{primary},{primary},&H00000000,&H64000000,\
-1,0,0,0,100,100,0,0,1,{cfg.outline},2,2,60,60,{cfg.margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [
        f"Dialogue: 0,{ass_time(e.start)},{ass_time(e.end)},Default,,0,0,0,,{e.text}"
        for e in build_events(words, style, cfg.max_words)
    ]
    return header + "\n".join(lines) + "\n"
