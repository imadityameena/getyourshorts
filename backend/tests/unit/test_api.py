from collections.abc import Iterator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.db.session import init_db
from app.main import app

VID = "dQw4w9WgXcQ"


@pytest.fixture
def client() -> Iterator[TestClient]:
    init_db()
    with patch("app.api.routes_jobs._enqueue") as enq, TestClient(app) as c:
        c.enqueued = enq  # type: ignore[attr-defined]
        yield c


def test_create_job_validates_url(client: TestClient) -> None:
    r = client.post("/api/jobs", json={"url": "https://www.youtube.com/playlist?list=PL1"})
    assert r.status_code == 422
    assert "Playlists" in r.json()["detail"]


def test_create_job_validates_lengths(client: TestClient) -> None:
    r = client.post(
        "/api/jobs", json={"url": f"https://youtu.be/{VID}", "min_len": 60, "max_len": 30}
    )
    assert r.status_code == 422
    r = client.post("/api/jobs", json={"url": f"https://youtu.be/{VID}", "num_clips": 11})
    assert r.status_code == 422


def test_create_and_dedupe(client: TestClient) -> None:
    body = {"url": f"https://youtu.be/{VID}", "num_clips": 3, "min_len": 20, "max_len": 45}
    r1 = client.post("/api/jobs", json=body)
    assert r1.status_code == 201
    jid = r1.json()["job_id"]
    # same video + settings while queued → same job, not a new one
    r2 = client.post("/api/jobs", json={**body, "url": f"https://www.youtube.com/watch?v={VID}"})
    assert r2.json()["job_id"] == jid
    # different settings → new job
    r3 = client.post("/api/jobs", json={**body, "num_clips": 4})
    assert r3.json()["job_id"] != jid

    j = client.get(f"/api/jobs/{jid}").json()
    assert j["status"] == "queued" and j["video_id"] == VID
    assert client.get(f"/api/jobs/{jid}/clips").json() == []
    assert client.get(f"/api/jobs/{jid}/zip").status_code == 409

    assert client.delete(f"/api/jobs/{jid}").status_code == 204
    assert client.get(f"/api/jobs/{jid}").status_code == 404


def test_unknown_caption_style(client: TestClient) -> None:
    r = client.post("/api/jobs", json={"url": f"https://youtu.be/{VID}", "caption_style": "comic"})
    assert r.status_code == 422


def test_events_stream_terminal_job(client: TestClient) -> None:
    from sqlmodel import Session

    from app.db import crud
    from app.db.models import JobStatus
    from app.db.session import get_engine

    jid = client.post("/api/jobs", json={"url": f"https://youtu.be/{VID}", "max_len": 89}).json()[
        "job_id"
    ]
    with Session(get_engine()) as s:
        crud.update_job(s, jid, status=JobStatus.FAILED, error="nope")
    with client.stream("GET", f"/api/jobs/{jid}/events") as r:
        body = "".join(r.iter_text())
    assert '"status":"failed"' in body


def test_404s(client: TestClient) -> None:
    assert client.get("/api/jobs/nope").status_code == 404
    assert client.get("/api/clips/nope/file").status_code == 404


def test_health(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    assert {"status", "ffmpeg", "disk_free_gb", "ai_providers"} <= r.json().keys()
