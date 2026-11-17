"""Stage 1: validate the URL, download ≤1080p video + 16 kHz mono audio + heatmap."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from app.core.config import AppConfig
from app.core.errors import (
    DownloadBlocked,
    DownloadFailed,
    InvalidUrl,
    LiveStream,
    TooLong,
    VideoUnavailable,
)
from app.core.logging import get_logger
from app.core.retry import run_cmd, with_retries
from app.pipeline.models import HeatPoint, VideoMeta
from app.storage.files import VideoPaths, ensure_disk_space, file_ok, write_model

log = get_logger("fetch")

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}


def parse_video_id(url: str) -> str:
    """Extract the 11-char video id; reject playlists and non-YouTube links (F1)."""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    u = urlparse(url)
    host = (u.hostname or "").lower()
    if host not in _HOSTS:
        raise InvalidUrl(f"not a youtube host: {host}")
    vid: str | None = None
    if host == "youtu.be":
        vid = u.path.lstrip("/").split("/")[0]
    elif u.path == "/watch":
        vid = parse_qs(u.query).get("v", [None])[0]
    elif u.path.startswith(("/shorts/", "/live/", "/embed/", "/v/")):
        vid = u.path.split("/")[2] if len(u.path.split("/")) > 2 else None
    elif u.path.startswith("/playlist"):
        raise InvalidUrl("playlist", user_message="Playlists aren't supported; paste one video.")
    if not vid or not _ID_RE.match(vid):
        raise InvalidUrl(f"no video id in {url}")
    return vid


def canonical_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def _classify(err: Exception) -> Exception:
    msg = str(err).lower()
    if "sign in to confirm" in msg or "not a bot" in msg or "http error 429" in msg:
        return DownloadBlocked(str(err))
    if any(
        s in msg
        for s in (
            "video unavailable",
            "private video",
            "has been removed",
            "members-only",
            "not available in your country",
            "age",
        )
    ):
        return VideoUnavailable(str(err))
    return DownloadFailed(str(err))


def _ydl_opts(cfg: AppConfig) -> dict[str, Any]:
    return {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 30,
        "retries": 3,
        "fragment_retries": 3,
        "noprogress": True,
    }


def probe(video_id: str, cfg: AppConfig) -> dict[str, Any]:
    """Fetch metadata without downloading; enforce live/length limits."""
    import yt_dlp

    def _do() -> dict[str, Any]:
        try:
            with yt_dlp.YoutubeDL(_ydl_opts(cfg)) as ydl:
                info: dict[str, Any] = ydl.extract_info(canonical_url(video_id), download=False)
                return info
        except yt_dlp.utils.DownloadError as e:
            raise _classify(e) from e

    info = with_retries(_do, what="yt-dlp probe")
    if info.get("is_live") or info.get("live_status") in ("is_live", "is_upcoming"):
        raise LiveStream(video_id)
    minutes = float(info.get("duration") or 0) / 60
    if minutes > cfg.limits.max_video_minutes:
        raise TooLong(minutes, cfg.limits.max_video_minutes)
    return info


def _heatmap(info: dict[str, Any]) -> list[HeatPoint] | None:
    raw = info.get("heatmap")
    if not raw:
        return None
    pts = [
        HeatPoint(start=float(p["start_time"]), end=float(p["end_time"]), value=float(p["value"]))
        for p in raw
    ]
    top = max((p.value for p in pts), default=0.0)
    if top <= 0:
        return None
    return [p.model_copy(update={"value": p.value / top}) for p in pts]


def download(video_id: str, paths: VideoPaths, cfg: AppConfig) -> VideoMeta:
    """Run stage 1. Skips work whose outputs already exist."""
    import yt_dlp

    ensure_disk_space(paths.root, cfg.limits.min_free_disk_gb)
    info = probe(video_id, cfg)
    h = cfg.limits.max_download_height

    if not file_ok(paths.source):
        opts = {
            **_ydl_opts(cfg),
            # prefer H.264 (cheap to decode), else best ≤ height, else a muxed file
            "format": (
                f"bv*[height<={h}][vcodec^=avc1]+ba[ext=m4a]/bv*[height<={h}]+ba/b[height<={h}]"
            ),
            "merge_output_format": "mp4",
            "outtmpl": str(paths.root / "download.%(ext)s"),
        }

        def _dl() -> None:
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([canonical_url(video_id)])
            except yt_dlp.utils.DownloadError as e:
                raise _classify(e) from e

        with_retries(_dl, what="yt-dlp download", base_delay=5)
        produced = sorted(paths.root.glob("download.*"), key=lambda p: p.stat().st_size)
        produced = [p for p in produced if p.suffix in (".mp4", ".mkv", ".webm")]
        if not produced:
            raise DownloadFailed("yt-dlp produced no file")
        _to_mp4(produced[-1], paths.source, cfg)
        for p in paths.root.glob("download.*"):
            p.unlink(missing_ok=True)

    if not file_ok(paths.audio):
        extract_audio(paths.source, paths.audio, cfg.limits.ffmpeg_timeout_s)

    w, hgt, fps = probe_video(paths.source)
    meta = VideoMeta(
        video_id=video_id,
        title=str(info.get("title") or video_id),
        duration=float(info.get("duration") or 0),
        width=w,
        height=hgt,
        fps=fps,
        channel=str(info.get("channel") or info.get("uploader") or ""),
        heatmap=_heatmap(info),
    )
    write_model(paths.meta, meta)
    log.info("fetched", title=meta.title, duration=meta.duration, heatmap=meta.heatmap is not None)
    return meta


def _to_mp4(src: Path, dst: Path, cfg: AppConfig) -> None:
    if src.suffix == ".mp4":
        src.replace(dst)
        return
    tmp = dst.with_suffix(".tmp.mp4")
    run_cmd(
        ["ffmpeg", "-y", "-v", "error", "-i", str(src), "-c", "copy", str(tmp)],
        timeout=cfg.limits.ffmpeg_timeout_s,
        what="remux",
    )
    tmp.replace(dst)


def extract_audio(src: Path, dst: Path, timeout: float) -> None:
    tmp = dst.with_suffix(".tmp.wav")
    run_cmd(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(src),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(tmp),
        ],
        timeout=timeout,
        what="extract audio",
    )
    tmp.replace(dst)


def probe_video(path: Path) -> tuple[int, int, float]:
    """(width, height, fps) via ffprobe."""
    out = (
        run_cmd(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height,r_frame_rate",
                "-of",
                "csv=p=0",
                str(path),
            ],
            timeout=60,
            what="ffprobe",
        )
        .stdout.strip()
        .splitlines()[0]
    )
    w, h, rate = out.split(",")[:3]
    num, _, den = rate.partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 30.0
    return int(w), int(h), fps
