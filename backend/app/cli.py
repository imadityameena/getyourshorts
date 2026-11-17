"""Command-line entry point (roadmap phase 1): run the whole pipeline without the API.

python -m app.cli "https://youtu.be/VIDEO_ID" --clips 5 --min 30 --max 60
"""

from __future__ import annotations

import argparse
import sys

from app.core.config import get_config, get_settings
from app.core.errors import AppError
from app.core.logging import setup_logging
from app.db.crud import settings_hash
from app.pipeline.fetch import parse_video_id
from app.pipeline.models import CropMode, JobSettings
from app.pipeline.runner import Runner


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Generate YouTube Shorts from a video URL")
    p.add_argument("url")
    p.add_argument("--clips", type=int, default=5)
    p.add_argument("--min", type=float, default=30, dest="min_len")
    p.add_argument("--max", type=float, default=60, dest="max_len")
    p.add_argument("--crop", choices=[m.value for m in CropMode], default="face")
    p.add_argument("--captions", default="bold")
    a = p.parse_args(argv)

    env = get_settings()
    setup_logging(env.log_level, json_logs=False)
    cfg = get_config()
    try:
        vid = parse_video_id(a.url)
        js = JobSettings(
            num_clips=a.clips,
            min_len=a.min_len,
            max_len=a.max_len,
            crop_mode=CropMode(a.crop),
            caption_style=a.captions,
        )
        runner = Runner(
            video_id=vid,
            settings=js,
            settings_hash=settings_hash(js, cfg),
            env=env,
            cfg=cfg,
            report=lambda stage, pct: print(f"\r[{pct:3d}%] {stage:<14}", end="", flush=True),
        )
        res = runner.run()
    except AppError as e:
        print(f"\nError: {e.user_message}  ({e})", file=sys.stderr)
        return 1
    print()
    for c in res.selection.clips:
        tag = "" if c.ai_ranked else "  [AI ranking unavailable]"
        print(f"#{c.rank}  score={c.score:.3f}  {c.start:7.1f}-{c.end:7.1f}s  {c.title}{tag}")
        print(f"     {c.reason}")
    print(f"\nClips: {res.jpaths.clips_dir}\nZIP:   {res.jpaths.zip}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
