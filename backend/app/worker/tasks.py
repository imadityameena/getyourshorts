"""Huey tasks. Queue lives in SQLite, so queued jobs survive restarts; jobs that
were mid-run when the worker died are re-enqueued on startup and resume from the
last completed stage thanks to the on-disk stage cache.

Run with:  huey_consumer app.worker.tasks.huey -w 1 -k thread
"""

from __future__ import annotations

import time
from typing import Any

import structlog
from huey import SqliteHuey, crontab
from sqlmodel import Session, col, select

from app.core.config import get_config, get_settings
from app.core.errors import AppError, JobCancelled
from app.core.logging import get_logger, setup_logging
from app.db import crud
from app.db.models import Clip, Job, JobStatus
from app.db.session import get_engine, init_db
from app.pipeline.models import JobSettings
from app.pipeline.runner import PipelineResult, Runner
from app.storage.files import cleanup_old

settings = get_settings()
setup_logging(settings.log_level)
huey = SqliteHuey("shorts", filename=str(settings.huey_path))
log = get_logger("worker")

MAX_RETRIES = 2


@huey.on_startup()
def _resume_interrupted() -> None:
    init_db()
    with Session(get_engine()) as s:
        stuck = s.exec(select(Job).where(col(Job.status) == JobStatus.RUNNING)).all()
        for job in stuck:
            log.info("resuming_interrupted_job", job_id=job.id, stage=job.stage)
            crud.update_job(s, job.id, status=JobStatus.QUEUED, stage="resuming")
            process_job(job.id)


@huey.task(retries=MAX_RETRIES, retry_delay=15, context=True)
def process_job(job_id: str, task: Any = None) -> None:
    with huey.lock_task(f"job-{job_id}"), structlog.contextvars.bound_contextvars(job_id=job_id):
        _process(job_id, retries_left=getattr(task, "retries", 0))


def _process(job_id: str, retries_left: int) -> None:
    engine = get_engine()
    with Session(engine) as s:
        job = s.get(Job, job_id)
        if job is None or job.status in (JobStatus.CANCELLED, JobStatus.DONE):
            return
        crud.update_job(s, job_id, status=JobStatus.RUNNING, error=None)
        video_id, shash = job.video_id, job.settings_hash
        job_settings = JobSettings.model_validate(job.settings)

    last_write = [0.0]

    def report(stage: str, pct: int) -> None:
        now = time.monotonic()
        if now - last_write[0] < 0.5 and pct % 5:
            return  # throttle DB writes
        last_write[0] = now
        with Session(engine) as s2:
            crud.update_job(s2, job_id, stage=stage, progress=pct)

    def cancelled() -> bool:
        with Session(engine) as s2:
            j = s2.get(Job, job_id)
            return j is None or j.status == JobStatus.CANCELLED

    runner = Runner(
        video_id=video_id,
        settings=job_settings,
        settings_hash=shash,
        env=get_settings(),
        cfg=get_config(),
        report=report,
        cancelled=cancelled,
    )
    try:
        result = runner.run()
    except JobCancelled:
        log.info("job_cancelled")
        return
    except AppError as e:
        _fail_or_retry(job_id, e, e.user_message, e.retryable, retries_left)
        return
    except Exception as e:  # never let one video crash the worker
        log.exception("job_crashed")
        _fail_or_retry(
            job_id, e, "Unexpected error while processing this video.", True, retries_left
        )
        return
    _store_result(job_id, result)


def _fail_or_retry(
    job_id: str, err: Exception, msg: str, retryable: bool, retries_left: int
) -> None:
    with Session(get_engine()) as s:
        if retryable and retries_left > 0:
            log.warning("job_retrying", error=str(err)[:500], retries_left=retries_left)
            crud.update_job(s, job_id, stage="retrying", error=msg)
            raise err  # Huey re-schedules; the next attempt resumes from the failed stage
        log.error("job_failed", error=str(err)[:1000])
        crud.update_job(s, job_id, status=JobStatus.FAILED, error=msg)


def _store_result(job_id: str, r: PipelineResult) -> None:
    rendered = {c.rank: c for c in r.render.clips}
    with Session(get_engine()) as s:
        for old in crud.clips_for(s, job_id):
            s.delete(old)
        for c in r.selection.clips:
            rc = rendered.get(c.rank)
            if rc is None:
                continue
            s.add(
                Clip(
                    job_id=job_id,
                    rank=c.rank,
                    start=c.start,
                    end=c.end,
                    duration=rc.duration,
                    score=c.score,
                    score_breakdown=c.breakdown.model_dump(),
                    title=c.title,
                    hook=c.hook_line,
                    reason=c.reason,
                    ai_ranked=c.ai_ranked,
                    file_path=str(r.jpaths.root / rc.file),
                    thumb_path=str(r.jpaths.root / rc.thumb),
                )
            )
        s.commit()
        crud.update_job(
            s,
            job_id,
            status=JobStatus.DONE,
            stage="done",
            progress=100,
            video_title=r.meta.title,
            ai_provider=r.selection.ai_provider,
        )
    log.info("job_done", clips=len(rendered))


@huey.periodic_task(crontab(minute="*/30"))
def cleanup() -> None:
    """F12: delete jobs and files older than CLEANUP_HOURS."""
    st = get_settings()
    with Session(get_engine()) as s:
        for job in crud.expired_jobs(s, st.cleanup_hours):
            crud.delete_job_files(s, job, st.storage_dir)
            crud.delete_job(s, job)
        active = {
            j.video_id
            for j in s.exec(
                select(Job).where(col(Job.status).in_([JobStatus.QUEUED, JobStatus.RUNNING]))
            ).all()
        }
    removed = cleanup_old(st.storage_dir, st.cleanup_hours, keep=active | {".models"})
    log.info("cleanup_done", removed_videos=len(removed))
