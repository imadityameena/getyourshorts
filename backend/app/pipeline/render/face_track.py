"""Face-tracked 9:16 crop path.

Samples frames at `sample_fps`, detects faces (MediaPipe, OpenCV Haar fallback),
picks the main face, then smooths the crop centre with an EMA and a dead zone.
Returns None when tracking isn't usable → caller uses blurred-background mode.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.config import RenderConfig
from app.core.logging import get_logger
from app.pipeline.models import Interval

log = get_logger("face_track")

# A detection: (center_x, center_y, width, height), all normalised 0..1.
Box = tuple[float, float, float, float]
Detector = Callable[[Any], list[Box]]

MEDIAPIPE_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_detector/"
    "blaze_face_short_range/float16/latest/blaze_face_short_range.tflite"
)


@dataclass(frozen=True)
class CropPath:
    crop_w: int  # source pixels
    crop_h: int
    times: list[float]  # output-timeline seconds
    xs: list[int]  # left edge of crop at each time


def _model_path() -> Path:
    from app.core.config import get_settings

    p = get_settings().storage_dir / ".models" / "blaze_face_short_range.tflite"
    if not p.exists():
        import httpx

        p.parent.mkdir(parents=True, exist_ok=True)
        r = httpx.get(MEDIAPIPE_MODEL_URL, timeout=60, follow_redirects=True)
        r.raise_for_status()
        p.write_bytes(r.content)
    return p


@lru_cache(maxsize=1)
def get_detector() -> Detector:
    try:
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions
        from mediapipe.tasks.python.vision import FaceDetector, FaceDetectorOptions

        det = FaceDetector.create_from_options(
            FaceDetectorOptions(
                base_options=BaseOptions(model_asset_path=str(_model_path())),
                min_detection_confidence=0.5,
            )
        )

        def _mp(frame_bgr: Any) -> list[Box]:
            import cv2

            h, w = frame_bgr.shape[:2]
            rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            res = det.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
            out: list[Box] = []
            for d in res.detections:
                b = d.bounding_box
                out.append(
                    (
                        (b.origin_x + b.width / 2) / w,
                        (b.origin_y + b.height / 2) / h,
                        b.width / w,
                        b.height / h,
                    )
                )
            return out

        return _mp
    except Exception as e:
        log.warning("mediapipe_unavailable_using_haar", error=str(e))
        import cv2

        # OpenCV 5 moved Haar cascades out of the base package (they remain in the
        # contrib build MediaPipe installs). Look them up dynamically and, if absent,
        # detect nothing: the clip then falls back to blurred-background framing.
        cascade_cls: Any = getattr(cv2, "CascadeClassifier", None)
        haar_dir: str | None = getattr(getattr(cv2, "data", None), "haarcascades", None)
        if cascade_cls is None or haar_dir is None:
            log.warning("no_face_detector_available")
            return lambda _frame: []
        cascade = cascade_cls(haar_dir + "haarcascade_frontalface_default.xml")

        def _haar(frame_bgr: Any) -> list[Box]:
            h, w = frame_bgr.shape[:2]
            gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
            faces = cascade.detectMultiScale(gray, 1.1, 5, minSize=(int(w * 0.04), int(w * 0.04)))
            return [((x + fw / 2) / w, (y + fh / 2) / h, fw / w, fh / h) for x, y, fw, fh in faces]

        return _haar


def sample_faces(
    video: Path, keep: Sequence[Interval], sample_fps: float, detector: Detector
) -> list[tuple[float, list[Box]]]:
    """Detections per sample, keyed by output-timeline time."""
    import cv2

    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open {video}")
    out: list[tuple[float, list[Box]]] = []
    step = 1.0 / sample_fps
    out_t = 0.0
    try:
        for iv in keep:
            t = iv.start
            while t < iv.end:
                cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
                ok, frame = cap.read()
                if ok:
                    if frame.shape[1] > 960:  # detection doesn't need full res
                        scale = 960 / frame.shape[1]
                        frame = cv2.resize(frame, None, fx=scale, fy=scale)
                    out.append((out_t + (t - iv.start), detector(frame)))
                t += step
            out_t += iv.end - iv.start
    finally:
        cap.release()
    return out


def choose_track(samples: Sequence[tuple[float, list[Box]]]) -> list[float | None]:
    """Pick the main face per sample: the one closest to the dominant face position.

    The dominant position is the area-weighted mode of face centres across all
    samples, so "largest" and "most often present" both count.
    """
    bins = [0.0] * 20
    for _, boxes in samples:
        for cx, _, bw, bh in boxes:
            bins[min(19, max(0, int(cx * 20)))] += bw * bh
    if not any(bins):
        return [None] * len(samples)
    dominant = (bins.index(max(bins)) + 0.5) / 20
    track: list[float | None] = []
    prev = dominant
    for _, boxes in samples:
        if not boxes:
            track.append(None)
            continue
        best = min(boxes, key=lambda b: abs(b[0] - prev) - 0.5 * b[2] * b[3])
        # ignore a sudden jump to a tiny face (likely a false positive)
        if abs(best[0] - prev) > 0.35 and best[2] * best[3] < 0.01:
            track.append(None)
            continue
        track.append(best[0])
        prev = best[0]
    return track


def longest_gap(times: Sequence[float], track: Sequence[float | None], total: float) -> float:
    gap_start: float | None = 0.0 if not track or track[0] is None else None
    worst = 0.0
    for t, x in zip(times, track, strict=True):
        if x is None and gap_start is None:
            gap_start = t
        elif x is not None and gap_start is not None:
            worst = max(worst, t - gap_start)
            gap_start = None
    if gap_start is not None:
        worst = max(worst, total - gap_start)
    return worst


def smooth(
    track: Sequence[float | None], alpha: float, dead_zone: float, crop_frac: float
) -> list[float]:
    """EMA + dead zone on normalised face centres; gaps hold the last position."""
    first = next((x for x in track if x is not None), 0.5)
    target = first
    cur = first
    out: list[float] = []
    threshold = dead_zone * crop_frac  # dead zone measured in crop widths
    for x in track:
        if x is not None and abs(x - target) > threshold:
            target = x
        cur = cur + alpha * (target - cur)
        out.append(cur)
    return out


def plan_crop(
    video: Path,
    keep: Sequence[Interval],
    src_w: int,
    src_h: int,
    cfg: RenderConfig,
    detector: Detector | None = None,
) -> CropPath | None:
    crop_h = src_h - src_h % 2
    crop_w = int(crop_h * cfg.width / cfg.height) // 2 * 2
    if crop_w >= src_w:
        return None  # source is already vertical-ish; blur-fit avoids black bars
    samples = sample_faces(video, keep, cfg.sample_fps, detector or get_detector())
    if not samples:
        return None
    times = [t for t, _ in samples]
    track = choose_track(samples)
    total = sum(i.end - i.start for i in keep)
    gap = longest_gap(times, track, total)
    if gap > cfg.max_face_gap_s:
        log.info("face_gap_fallback_blur", gap=round(gap, 2))
        return None
    crop_frac = crop_w / src_w
    centres = smooth(track, cfg.ema_alpha, cfg.dead_zone, crop_frac)
    xs = [int(min(max(c * src_w - crop_w / 2, 0), src_w - crop_w)) // 2 * 2 for c in centres]
    return CropPath(crop_w=crop_w, crop_h=crop_h, times=times, xs=xs)


def sendcmd_script(path: CropPath, fps: int, target: str = "crop@fc") -> str:
    """Interpolate keyframes to every output frame; emit a command only on change."""
    if not path.times:
        return ""
    lines: list[str] = []
    last: int | None = None
    end_t = path.times[-1]
    n = int(end_t * fps) + 1
    j = 0
    for f in range(n):
        t = f / fps
        while j + 1 < len(path.times) and path.times[j + 1] <= t:
            j += 1
        if j + 1 < len(path.times):
            t0, t1 = path.times[j], path.times[j + 1]
            a = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
            x = path.xs[j] + a * (path.xs[j + 1] - path.xs[j])
        else:
            x = path.xs[j]
        xi = round(x) // 2 * 2
        if xi != last:
            lines.append(f"{t:.4f} {target} x {xi};")
            last = xi
    return "\n".join(lines) + "\n"
