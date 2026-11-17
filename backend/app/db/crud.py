"""Small DB helpers shared by the API and the worker."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlmodel import Session, col, delete, select

from app.core.config import AppConfig
from app.db.models import TERMINAL, Clip, Job, JobStatus
from app.pipeline.models import JobSettings


def settings_hash(s: JobSettings, cfg: AppConfig) -> str:
    payload = json.dumps(s.model_dump(mode="json"), sort_keys=True) + cfg.fingerprint()
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def find_reusable(session: Session, video_id: str, shash: str) -> Job | None:
    """Most recent non-failed job with the same cache key (F11)."""
    stmt = (
        select(Job)
        .where(Job.video_id == video_id, Job.settings_hash == shash)
        .where(col(Job.status).in_([JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.DONE]))
        .order_by(col(Job.created_at).desc())
    )
    return session.exec(stmt).first()


def update_job(session: Session, job_id: str, **fields: object) -> Job | None:
    job = session.get(Job, job_id)
    if job is None:
        return None
    for k, v in fields.items():
        setattr(job, k, v)
    if fields.get("status") in TERMINAL:
        job.finished_at = datetime.now(UTC)
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def clips_for(session: Session, job_id: str) -> list[Clip]:
    return list(session.exec(select(Clip).where(Clip.job_id == job_id).order_by(col(Clip.rank))))


def delete_job_files(session: Session, job: Job, storage: Path) -> None:
    """Remove the job's settings folder; remove the video folder if nothing else uses it."""
    others = session.exec(
        select(Job)
        .where(Job.video_id == job.video_id, Job.id != job.id)
        .where(col(Job.status).in_([JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.DONE]))
    ).all()
    same_key = [o for o in others if o.settings_hash == job.settings_hash]
    if not same_key:
        shutil.rmtree(storage / job.video_id / job.settings_hash, ignore_errors=True)
    if not others:
        shutil.rmtree(storage / job.video_id, ignore_errors=True)


def delete_job(session: Session, job: Job) -> None:
    session.exec(delete(Clip).where(col(Clip.job_id) == job.id))
    session.delete(job)
    session.commit()


def expired_jobs(session: Session, hours: float) -> list[Job]:
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    jobs = session.exec(select(Job).where(col(Job.status).in_(list(TERMINAL)))).all()
    return [j for j in jobs if _aware(j.created_at) < cutoff]


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)  # SQLite drops tzinfo
