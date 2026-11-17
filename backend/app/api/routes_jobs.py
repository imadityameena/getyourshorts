from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from sqlmodel import Session

from app.api.schemas import ClipOut, CreateJob, JobCreated, JobOut
from app.core.config import get_config, get_settings
from app.core.errors import AppError
from app.db import crud
from app.db.models import TERMINAL, Clip, Job, JobStatus
from app.db.session import get_engine, get_session
from app.pipeline.fetch import canonical_url, parse_video_id

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _enqueue(job_id: str) -> None:
    from app.worker.tasks import process_job

    process_job(job_id)


def _job_or_404(session: Session, job_id: str) -> Job:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return job


def to_job_out(j: Job) -> JobOut:
    return JobOut.model_validate(j, from_attributes=True)


def to_clip_out(c: Clip) -> ClipOut:
    return ClipOut(
        **c.model_dump(exclude={"file_path", "thumb_path", "job_id"}),
        file_url=f"/api/clips/{c.id}/file",
        thumb_url=f"/api/clips/{c.id}/thumb",
    )


def _files_present(session: Session, job: Job) -> bool:
    clips = crud.clips_for(session, job.id)
    return bool(clips) and all(Path(c.file_path).exists() for c in clips)


@router.post("", response_model=JobCreated, status_code=201)
def create_job(body: CreateJob, session: Session = Depends(get_session)) -> JobCreated:
    try:
        video_id = parse_video_id(body.url)
    except AppError as e:
        raise HTTPException(422, e.user_message) from e
    settings = body.to_settings()
    cfg = get_config()
    if settings.caption_style != "none" and settings.caption_style not in cfg.captions.styles:
        raise HTTPException(422, f"Unknown caption style '{settings.caption_style}'")
    shash = crud.settings_hash(settings, cfg)

    existing = crud.find_reusable(session, video_id, shash)
    if existing is not None and (
        existing.status != JobStatus.DONE or _files_present(session, existing)
    ):
        return JobCreated(job_id=existing.id, cached=existing.status == JobStatus.DONE)

    job = Job(
        video_id=video_id,
        url=canonical_url(video_id),
        settings_hash=shash,
        settings=settings.model_dump(mode="json"),
    )
    session.add(job)
    session.commit()
    _enqueue(job.id)
    return JobCreated(job_id=job.id, cached=False)


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: str, session: Session = Depends(get_session)) -> JobOut:
    return to_job_out(_job_or_404(session, job_id))


@router.get("/{job_id}/events")
async def job_events(job_id: str, request: Request) -> StreamingResponse:
    """Server-Sent Events: emits the job whenever stage/progress/status changes."""
    with Session(get_engine()) as s:
        _job_or_404(s, job_id)

    async def stream() -> AsyncIterator[str]:
        last = ""
        idle = 0
        while not await request.is_disconnected():
            with Session(get_engine()) as s:
                job = s.get(Job, job_id)
                if job is None:
                    yield 'event: error\ndata: {"detail": "Job not found"}\n\n'
                    return
                payload = to_job_out(job).model_dump_json()
                terminal = job.status in TERMINAL
            if payload != last:
                last = payload
                idle = 0
                yield f"data: {payload}\n\n"
            else:
                idle += 1
                if idle % 30 == 0:  # keep-alive comment every ~15s (proxies/tunnels)
                    yield ": ping\n\n"
            if terminal:
                return
            await asyncio.sleep(0.5)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{job_id}/clips", response_model=list[ClipOut])
def job_clips(job_id: str, session: Session = Depends(get_session)) -> list[ClipOut]:
    _job_or_404(session, job_id)
    return [to_clip_out(c) for c in crud.clips_for(session, job_id)]


@router.get("/{job_id}/zip")
def job_zip(job_id: str, session: Session = Depends(get_session)) -> FileResponse:
    job = _job_or_404(session, job_id)
    if job.status != JobStatus.DONE:
        raise HTTPException(409, "Job is not finished yet")
    path = get_settings().storage_dir / job.video_id / job.settings_hash / "shorts.zip"
    if not path.exists():
        raise HTTPException(410, "Files have expired; submit the video again")
    return FileResponse(path, media_type="application/zip", filename=f"shorts_{job.video_id}.zip")


@router.delete("/{job_id}", status_code=204)
def cancel_job(job_id: str, session: Session = Depends(get_session)) -> None:
    job = _job_or_404(session, job_id)
    if job.status not in TERMINAL:
        crud.update_job(session, job_id, status=JobStatus.CANCELLED, stage="cancelled")
    crud.delete_job_files(session, job, get_settings().storage_dir)
    crud.delete_job(session, job)
