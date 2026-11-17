"""Render one selected clip: crop plan → captions → FFmpeg → thumbnail."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from app.core.config import CaptionsConfig, RenderConfig
from app.core.logging import get_logger
from app.pipeline.models import CropMode, RenderedClip, SelectedClip, VideoMeta, Word
from app.pipeline.render.captions import build_ass
from app.pipeline.render.encode import CropSpec, build_command, encode, thumbnail
from app.pipeline.render.face_track import plan_crop, sendcmd_script
from app.pipeline.select.snapping import remap_words

log = get_logger("render")


def _crop_spec(
    mode: CropMode, source: Path, meta: VideoMeta, clip: SelectedClip, cfg: RenderConfig, work: Path
) -> tuple[CropSpec, CropMode]:
    vertical_or_square = meta.width * cfg.height <= meta.height * cfg.width
    if mode == CropMode.BLUR or vertical_or_square:
        return CropSpec("blur"), CropMode.BLUR
    if mode == CropMode.CENTER:
        return CropSpec("center"), CropMode.CENTER
    try:
        path = plan_crop(source, clip.keep, meta.width, meta.height, cfg)
    except Exception as e:  # tracking must never kill a render
        log.warning("face_tracking_failed", rank=clip.rank, error=str(e))
        path = None
    if path is None:
        return CropSpec("blur"), CropMode.BLUR
    cmd_file = work / f"clip_{clip.rank:02d}.sendcmd"
    cmd_file.write_text(sendcmd_script(path, cfg.fps))
    return (
        CropSpec(
            "track", crop_w=path.crop_w, crop_h=path.crop_h, x0=path.xs[0], sendcmd_file=cmd_file
        ),
        CropMode.FACE,
    )


def render_clip(
    *,
    source: Path,
    meta: VideoMeta,
    clip: SelectedClip,
    words: Sequence[Word],
    out: Path,
    thumb: Path,
    crop_mode: CropMode,
    caption_style: str,
    render_cfg: RenderConfig,
    captions_cfg: CaptionsConfig,
    use_gpu: bool,
    timeout: float,
) -> RenderedClip:
    work = out.parent
    temp_files: list[Path] = []
    try:
        crop, used = _crop_spec(crop_mode, source, meta, clip, render_cfg, work)
        if crop.sendcmd_file:
            temp_files.append(crop.sendcmd_file)

        ass_file: Path | None = None
        if caption_style != "none":
            clip_words = remap_words(words[clip.word_start : clip.word_end], clip.keep)
            ass_file = work / f"clip_{clip.rank:02d}.ass"
            ass_file.write_text(
                build_ass(
                    clip_words, captions_cfg, caption_style, render_cfg.width, render_cfg.height
                ),
                encoding="utf-8",
            )
            temp_files.append(ass_file)

        cmd = build_command(
            source=source,
            out=out,
            start=clip.start,
            end=clip.end,
            keep=clip.keep,
            crop=crop,
            ass_file=ass_file,
            cfg=render_cfg,
            src_w=meta.width,
            src_h=meta.height,
            use_gpu=use_gpu,
        )
        encode(cmd, out, timeout)
        thumbnail(out, thumb, at=min(1.0, clip.output_duration / 2))
    finally:
        for f in temp_files:
            f.unlink(missing_ok=True)
    return RenderedClip(
        rank=clip.rank,
        file=f"clips/{out.name}",
        thumb=f"clips/{thumb.name}",
        crop_used=used,
        duration=round(clip.output_duration, 2),
    )
