from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.pipeline.models import CropMode, JobSettings


class CreateJob(BaseModel):
    url: str = Field(min_length=5, max_length=500)
    num_clips: int = Field(5, ge=1, le=10)
    min_len: float = Field(30, ge=15, le=90)
    max_len: float = Field(60, ge=15, le=90)
    crop_mode: CropMode = CropMode.FACE
    caption_style: str = Field("bold", pattern=r"^[a-z_]{1,20}$")

    @model_validator(mode="after")
    def _lengths(self) -> CreateJob:
        if self.min_len > self.max_len:
            raise ValueError("min_len must be <= max_len")
        if self.max_len - self.min_len < 5:
            raise ValueError("leave at least 5 seconds between min_len and max_len")
        return self

    def to_settings(self) -> JobSettings:
        return JobSettings(
            num_clips=self.num_clips,
            min_len=self.min_len,
            max_len=self.max_len,
            crop_mode=self.crop_mode,
            caption_style=self.caption_style,
        )


class JobCreated(BaseModel):
    job_id: str
    cached: bool


class JobOut(BaseModel):
    id: str
    video_id: str
    url: str
    status: str
    stage: str
    progress: int
    error: str | None
    video_title: str | None
    ai_provider: str | None
    settings: dict[str, Any]
    created_at: datetime
    finished_at: datetime | None


class ClipOut(BaseModel):
    id: str
    rank: int
    start: float
    end: float
    duration: float
    score: float
    score_breakdown: dict[str, Any]
    title: str
    hook: str
    reason: str
    ai_ranked: bool
    file_url: str
    thumb_url: str


class Health(BaseModel):
    status: str
    ffmpeg: bool
    nvenc: bool
    disk_free_gb: float
    ai_providers: dict[str, bool]
    gpu: bool
