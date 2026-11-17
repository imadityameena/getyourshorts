"""FFmpeg command building and execution for one clip."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.core.config import RenderConfig
from app.core.errors import RenderFailed
from app.core.logging import get_logger
from app.core.retry import run_cmd
from app.pipeline.models import Interval

log = get_logger("encode")

FONTS_DIR = Path(__file__).resolve().parents[3] / "assets" / "fonts"


def escape_filter_path(p: Path) -> str:
    """Escape a path for use inside an FFmpeg filtergraph option value."""
    s = str(p).replace("\\", "/")
    return s.replace(":", r"\:").replace("'", r"\'").replace(",", r"\,")


def select_expr(keep: list[Interval], offset: float) -> str:
    parts = [f"between(t,{iv.start - offset:.3f},{iv.end - offset:.3f})" for iv in keep]
    return "+".join(parts)


@dataclass(frozen=True)
class CropSpec:
    mode: str  # "track" | "center" | "blur"
    crop_w: int = 0
    crop_h: int = 0
    x0: int = 0
    sendcmd_file: Path | None = None


def video_filter(crop: CropSpec, cfg: RenderConfig, src_w: int, src_h: int) -> str:
    """Filter chain (after select/setpts) producing a WxH frame, as `label`-free chain text."""
    w, h = cfg.width, cfg.height
    if crop.mode == "track" and crop.sendcmd_file is not None:
        y = (src_h - crop.crop_h) // 2
        return (
            f"sendcmd=f='{escape_filter_path(crop.sendcmd_file)}',"
            f"crop@fc=w={crop.crop_w}:h={crop.crop_h}:x={crop.x0}:y={y},"
            f"scale={w}:{h}:flags=lanczos,setsar=1"
        )
    if crop.mode == "center" and src_w * h > src_h * w:
        return f"crop=ih*{w}/{h}:ih,scale={w}:{h}:flags=lanczos,setsar=1"
    # blurred background: full frame fitted over an enlarged, blurred copy of itself
    return (
        f"split=2[bgsrc][fgsrc];"
        f"[bgsrc]scale={w // 4}:{h // 4}:force_original_aspect_ratio=increase,"
        f"crop={w // 4}:{h // 4},boxblur=10:2,scale={w}:{h}[bg];"
        f"[fgsrc]scale={w}:{h}:force_original_aspect_ratio=decrease:flags=lanczos[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1"
    )


@lru_cache(maxsize=1)
def nvenc_available() -> bool:
    try:
        run_cmd(
            [
                "ffmpeg",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=black:s=256x256:d=0.1",
                "-c:v",
                "h264_nvenc",
                "-f",
                "null",
                "-",
            ],
            timeout=30,
            what="nvenc probe",
        )
        return True
    except Exception:
        return False


def video_codec_args(use_gpu: bool) -> list[str]:
    if use_gpu and nvenc_available():
        return ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "23", "-b:v", "0"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21"]


def build_command(
    *,
    source: Path,
    out: Path,
    start: float,
    end: float,
    keep: list[Interval],
    crop: CropSpec,
    ass_file: Path | None,
    cfg: RenderConfig,
    src_w: int,
    src_h: int,
    use_gpu: bool,
) -> list[str]:
    sel = select_expr(keep, start)
    vchain = f"[0:v]fps={cfg.fps},select='{sel}',setpts=N/FRAME_RATE/TB,"
    vchain += video_filter(crop, cfg, src_w, src_h)
    if ass_file is not None:
        fonts = f":fontsdir='{escape_filter_path(FONTS_DIR)}'" if FONTS_DIR.exists() else ""
        vchain += f",subtitles=filename='{escape_filter_path(ass_file)}'{fonts}"
    vchain += ",format=yuv420p[v]"
    achain = (
        f"[0:a]aselect='{sel}',asetpts=N/SR/TB,"
        "loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000,"
        "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[a]"
    )
    return [
        "ffmpeg",
        "-y",
        "-v",
        "error",
        "-nostdin",
        "-ss",
        f"{start:.3f}",
        "-t",
        f"{end - start:.3f}",
        "-i",
        str(source),
        "-filter_complex",
        f"{vchain};{achain}",
        "-map",
        "[v]",
        "-map",
        "[a]",
        *video_codec_args(use_gpu),
        "-r",
        str(cfg.fps),
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-ar",
        "48000",
        "-movflags",
        "+faststart",
        str(out),
    ]


def encode(cmd: list[str], out: Path, timeout: float) -> None:
    tmp = out.with_name(out.stem + ".part.mp4")
    cmd = [*cmd[:-1], str(tmp)]
    try:
        run_cmd(cmd, timeout=timeout, what="ffmpeg render")
    except subprocess.CalledProcessError as e:
        if "h264_nvenc" in cmd:  # GPU encode failed → retry on CPU once
            log.warning("nvenc_failed_retrying_cpu", stderr=str(e.stderr)[-500:])
            i = cmd.index("h264_nvenc") - 1
            cpu = cmd[:i] + video_codec_args(False) + cmd[i + 10 :]
            try:
                run_cmd(cpu, timeout=timeout, what="ffmpeg render (cpu)")
            except subprocess.CalledProcessError as e2:
                raise RenderFailed(str(e2.stderr)[-800:]) from e2
        else:
            raise RenderFailed(str(e.stderr)[-800:]) from e
    finally:
        if not tmp.exists() or tmp.stat().st_size == 0:
            tmp.unlink(missing_ok=True)
    tmp.replace(out)


def thumbnail(clip: Path, out: Path, at: float = 1.0) -> None:
    run_cmd(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-ss",
            f"{at:.2f}",
            "-i",
            str(clip),
            "-frames:v",
            "1",
            "-vf",
            "scale=540:-2",
            "-q:v",
            "3",
            str(out),
        ],
        timeout=60,
        what="thumbnail",
    )
