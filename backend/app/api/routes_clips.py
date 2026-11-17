from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import Session

from app.db.models import Clip
from app.db.session import get_session

router = APIRouter(prefix="/api/clips", tags=["clips"])


def _clip(session: Session, clip_id: str) -> Clip:
    clip = session.get(Clip, clip_id)
    if clip is None:
        raise HTTPException(404, "Clip not found")
    return clip


@router.get("/{clip_id}/file")
def clip_file(
    clip_id: str, download: bool = False, session: Session = Depends(get_session)
) -> FileResponse:
    """Streams with HTTP Range support (Starlette FileResponse) so <video> can seek."""
    clip = _clip(session, clip_id)
    path = Path(clip.file_path)
    if not path.exists():
        raise HTTPException(410, "File has expired")
    name = f"short_{clip.rank:02d}.mp4"
    return FileResponse(
        path,
        media_type="video/mp4",
        filename=name if download else None,
        content_disposition_type="attachment" if download else "inline",
    )


@router.get("/{clip_id}/thumb")
def clip_thumb(clip_id: str, session: Session = Depends(get_session)) -> FileResponse:
    clip = _clip(session, clip_id)
    path = Path(clip.thumb_path)
    if not path.exists():
        raise HTTPException(410, "File has expired")
    return FileResponse(path, media_type="image/jpeg")
