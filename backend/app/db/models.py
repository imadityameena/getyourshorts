from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def _now() -> datetime:
    return datetime.now(UTC)


def _uuid() -> str:
    return uuid.uuid4().hex


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL = {JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED}


class Job(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    video_id: str = Field(index=True)
    url: str
    settings_hash: str = Field(index=True)
    settings: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    status: JobStatus = Field(default=JobStatus.QUEUED, index=True)
    stage: str = "queued"
    progress: int = 0
    error: str | None = None
    video_title: str | None = None
    ai_provider: str | None = None
    created_at: datetime = Field(default_factory=_now)
    finished_at: datetime | None = None


class Clip(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    job_id: str = Field(foreign_key="job.id", index=True)
    rank: int
    start: float
    end: float
    duration: float
    score: float
    score_breakdown: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    title: str
    hook: str
    reason: str
    ai_ranked: bool = True
    file_path: str
    thumb_path: str
