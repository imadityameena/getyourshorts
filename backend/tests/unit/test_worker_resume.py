from sqlmodel import Session

from app.db import crud
from app.db.models import Job, JobStatus
from app.db.session import get_engine, init_db
from app.worker import tasks


def _job(status: JobStatus) -> str:
    with Session(get_engine()) as s:
        j = Job(
            video_id="dQw4w9WgXcQ", url="u", settings_hash="h", status=status, stage="transcribing"
        )
        s.add(j)
        s.commit()
        return j.id


def _pending_job_ids() -> list[str]:
    return [t.args[0] for t in tasks.huey.pending()]


def test_startup_flushes_stale_lock_and_requeues_orphans() -> None:
    init_db()
    tasks.huey.flush()
    running = _job(JobStatus.RUNNING)
    orphan = _job(JobStatus.QUEUED)
    done = _job(JobStatus.DONE)

    # simulate a worker killed while holding the job lock
    lock = tasks.huey.lock_task(f"job-{running}")
    lock.__enter__()
    assert lock.is_locked()
    # A new process doesn't know about lock names created at runtime by the old one.
    tasks.huey._locks.discard(f"job-{running}")

    tasks._resume_interrupted()

    assert not lock.is_locked()
    pending = _pending_job_ids()  # other tests may leave queued jobs in the shared DB
    assert pending.count(running) == 1 and pending.count(orphan) == 1
    assert done not in pending
    with Session(get_engine()) as s:
        j = s.get(Job, running)
        assert j is not None and j.status == JobStatus.QUEUED and j.stage == "resuming"

    # a second startup must not enqueue duplicates for tasks already pending
    tasks._resume_interrupted()
    assert sorted(_pending_job_ids()) == sorted(pending)

    tasks.huey.flush()
    with Session(get_engine()) as s:
        for jid in (running, orphan, done):
            job = s.get(Job, jid)
            if job:
                crud.delete_job(s, job)
