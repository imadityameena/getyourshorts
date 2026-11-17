"""Full pipeline on a 2-minute synthetic sample, with download, Whisper and AI mocked.

The sample is generated with FFmpeg into tests/fixtures/ on first run (not committed).
Run with:  pytest -m integration
"""

from __future__ import annotations

import json
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

from app.core.config import AppConfig, Settings, load_app_config
from app.pipeline.models import CropMode, JobSettings, Segment, Transcript, VideoMeta
from app.pipeline.runner import Runner
from app.storage.files import video_paths, write_model
from tests.conftest import make_words

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed"),
]

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
SAMPLE = FIXTURES / "sample_2min.mp4"
VID = "TESTVIDEO01"


def _make_sample() -> Path:
    if SAMPLE.exists():
        return SAMPLE
    FIXTURES.mkdir(exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=1280x720:rate=30:duration=120",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=120",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "35",
            "-c:a",
            "aac",
            "-shortest",
            str(SAMPLE),
        ],
        check=True,
    )
    return SAMPLE


class FakeLLM:
    name = "fake"

    def complete(self, system: str, user: str) -> str:
        ids = [int(x) for x in __import__("re").findall(r"\[id=(\d+)\]", user)]
        return json.dumps(
            {
                "ratings": [
                    {
                        "id": i,
                        "hook": 5 + i % 5,
                        "standalone": 7,
                        "payoff": 6,
                        "emotion": 5,
                        "title": f"Clip {i}",
                        "hook_line": "Hook!",
                        "reason": "Test.",
                    }
                    for i in ids
                ]
            }
        )


def _transcript() -> Transcript:
    text = " ".join("here is a sentence that has some words." for _ in range(40))
    words = make_words(text, start=1.0, wps=2.8)
    segs = [
        Segment(
            start=words[i].start,
            end=words[min(i + 7, len(words) - 1)].end,
            text=" ".join(w.text for w in words[i : i + 8]),
            words=words[i : i + 8],
        )
        for i in range(0, len(words), 8)
    ]
    return Transcript(language="en", duration=120, segments=segs)


@pytest.fixture
def env(tmp_path: Path) -> tuple[Settings, AppConfig]:
    settings = Settings(storage_dir=tmp_path, use_gpu=False)
    cfg = load_app_config(Path(__file__).resolve().parents[2] / "config.yaml")
    vp = video_paths(tmp_path, VID)
    shutil.copy(_make_sample(), vp.source)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(vp.source),
            "-ac",
            "1",
            "-ar",
            "16000",
            str(vp.audio),
        ],
        check=True,
    )
    write_model(
        vp.meta,
        VideoMeta(
            video_id=VID, title="Sample", duration=120, width=1280, height=720, fps=30, heatmap=None
        ),
    )
    write_model(vp.transcript, _transcript())
    return settings, cfg


@pytest.mark.parametrize("crop", [CropMode.CENTER, CropMode.BLUR])
def test_full_pipeline(env: tuple[Settings, AppConfig], crop: CropMode) -> None:
    settings, cfg = env
    js = JobSettings(num_clips=2, min_len=15, max_len=25, crop_mode=crop, caption_style="bold")
    progress: list[tuple[str, int]] = []
    runner = Runner(
        video_id=VID,
        settings=js,
        settings_hash=f"h-{crop}",
        env=settings,
        cfg=cfg,
        report=lambda s, p: progress.append((s, p)),
        providers=[FakeLLM()],
    )
    res = runner.run()

    assert len(res.selection.clips) == 2
    assert res.selection.ai_provider == "fake"
    pcts = [p for _, p in progress]
    assert pcts == sorted(pcts) and pcts[-1] == 100

    for rc in res.render.clips:
        f = res.jpaths.root / rc.file
        assert f.exists() and (res.jpaths.root / rc.thumb).exists()
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "stream=codec_type,width,height",
                "-of",
                "json",
                str(f),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        streams = json.loads(probe.stdout)["streams"]
        v = next(s for s in streams if s["codec_type"] == "video")
        assert (v["width"], v["height"]) == (1080, 1920)
        assert any(s["codec_type"] == "audio" for s in streams)

    with zipfile.ZipFile(res.jpaths.zip) as z:
        assert sorted(n for n in z.namelist() if n.endswith(".mp4")) == [
            "short_01.mp4",
            "short_02.mp4",
        ]

    # second run: everything cached → no stage does work, identical result
    again = Runner(
        video_id=VID, settings=js, settings_hash=f"h-{crop}", env=settings, cfg=cfg, providers=[]
    ).run()
    assert again.selection == res.selection


def test_resume_after_render_failure(env: tuple[Settings, AppConfig]) -> None:
    """Deleting a rendered clip (simulating a crash mid-render) only re-renders that stage."""
    settings, cfg = env
    js = JobSettings(
        num_clips=1, min_len=15, max_len=25, crop_mode=CropMode.CENTER, caption_style="none"
    )
    r = Runner(
        video_id=VID,
        settings=js,
        settings_hash="resume",
        env=settings,
        cfg=cfg,
        providers=[FakeLLM()],
    ).run()
    clip = r.jpaths.root / r.render.clips[0].file
    clip.unlink()
    r.jpaths.zip.unlink()
    llm_mtime = r.jpaths.llm.stat().st_mtime
    r2 = Runner(
        video_id=VID, settings=js, settings_hash="resume", env=settings, cfg=cfg, providers=[]
    ).run()
    assert clip.exists() and r2.jpaths.zip.exists()
    assert r2.jpaths.llm.stat().st_mtime == llm_mtime  # AI stage was not re-run
