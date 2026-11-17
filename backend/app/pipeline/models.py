"""Data passed between pipeline stages. Each is persisted as JSON on disk."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class CropMode(StrEnum):
    FACE = "face"
    CENTER = "center"
    BLUR = "blur"


class JobSettings(BaseModel):
    num_clips: int = Field(5, ge=1, le=10)
    min_len: float = Field(30, ge=15, le=90)
    max_len: float = Field(60, ge=15, le=90)
    crop_mode: CropMode = CropMode.FACE
    caption_style: str = "bold"  # "none" disables captions


# ---- fetch ---------------------------------------------------------------


class HeatPoint(BaseModel):
    start: float
    end: float
    value: float  # 0..1


class VideoMeta(BaseModel):
    video_id: str
    title: str
    duration: float
    width: int = 0
    height: int = 0
    fps: float = 30.0
    channel: str = ""
    heatmap: list[HeatPoint] | None = None


# ---- transcribe ----------------------------------------------------------


class Word(BaseModel):
    start: float
    end: float
    text: str
    prob: float = 1.0


class Segment(BaseModel):
    start: float
    end: float
    text: str
    words: list[Word]


class Transcript(BaseModel):
    language: str
    duration: float
    segments: list[Segment]

    def words(self) -> list[Word]:
        return [w for s in self.segments for w in s.words]


# ---- analyze -------------------------------------------------------------


class Signals(BaseModel):
    """Video-level signals, independent of job settings."""

    duration: float
    heatmap: list[HeatPoint] | None
    rms_hop_s: float
    rms: list[float]  # one value per hop
    scene_cuts: list[float]


class Sentence(BaseModel):
    start: float
    end: float
    text: str
    word_start: int  # index into transcript.words()
    word_end: int  # exclusive


class Candidate(BaseModel):
    id: int
    start: float
    end: float
    text: str
    word_start: int
    word_end: int
    prescore: float = 0.0

    @property
    def duration(self) -> float:
        return self.end - self.start


class Shortlist(BaseModel):
    candidates: list[Candidate]


class LLMRating(BaseModel):
    id: int
    hook: float = Field(ge=0, le=10)
    standalone: float = Field(ge=0, le=10)
    payoff: float = Field(ge=0, le=10)
    emotion: float = Field(ge=0, le=10)
    title: str = Field(max_length=120)
    hook_line: str = Field("", max_length=160)
    reason: str = Field("", max_length=400)


class LLMResult(BaseModel):
    provider: str | None
    ratings: dict[int, LLMRating]


# ---- select --------------------------------------------------------------


class ScoreBreakdown(BaseModel):
    heatmap: float | None
    ai_virality: float | None
    hook: float | None
    audio: float
    pace: float
    visual: float
    weights: dict[str, float]


class Interval(BaseModel):
    start: float
    end: float


class SelectedClip(BaseModel):
    rank: int
    candidate_id: int
    start: float
    end: float
    keep: list[Interval]  # source-time intervals kept after silence trimming
    score: float
    breakdown: ScoreBreakdown
    title: str
    hook_line: str
    reason: str
    ai_ranked: bool
    word_start: int
    word_end: int

    @property
    def output_duration(self) -> float:
        return sum(i.end - i.start for i in self.keep)


class Selection(BaseModel):
    ai_provider: str | None
    clips: list[SelectedClip]


# ---- render / package ----------------------------------------------------


class RenderedClip(BaseModel):
    rank: int
    file: str  # relative to the job directory
    thumb: str
    crop_used: CropMode
    duration: float


class RenderResult(BaseModel):
    clips: list[RenderedClip]
