import wave
from pathlib import Path

import numpy as np
import pytest

from app.pipeline.analyze.scenes import parse_cuts, scene_command
from app.pipeline.transcribe import load_wav


def _write_wav(path: Path, samples: np.ndarray, rate: int = 16000, channels: int = 1) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(samples.astype(np.int16).tobytes())


def test_load_wav_scales_to_float(tmp_path: Path) -> None:
    p = tmp_path / "a.wav"
    _write_wav(p, np.array([0, 16384, -32768, 32767]))
    x = load_wav(p)
    assert x.dtype == np.float32
    assert x.tolist() == pytest.approx([0.0, 0.5, -1.0, 32767 / 32768])


def test_load_wav_downmixes_stereo(tmp_path: Path) -> None:
    p = tmp_path / "s.wav"
    _write_wav(p, np.array([16384, 0, 0, 16384]), channels=2)
    assert load_wav(p).tolist() == pytest.approx([0.25, 0.25])


def test_load_wav_rejects_wrong_rate(tmp_path: Path) -> None:
    p = tmp_path / "r.wav"
    _write_wav(p, np.zeros(10), rate=44100)
    with pytest.raises(ValueError):
        load_wav(p)


def test_parse_cuts_sorts_and_merges_close_hits() -> None:
    out = """frame:0    pts:40   pts_time:10.0
lavfi.scene_score=0.51
frame:1    pts:41   pts_time:10.25
lavfi.scene_score=0.40
frame:2    pts:200  pts_time:50.5
lavfi.scene_score=0.90
frame:3    pts:20   pts_time:5
"""
    assert parse_cuts(out) == [5.0, 10.0, 50.5]
    assert parse_cuts("") == []


def test_scene_command_is_downscaled_and_audio_free() -> None:
    cmd = scene_command(Path("/v.mp4"))
    vf = cmd[cmd.index("-vf") + 1]
    assert "fps=4" in vf and "scale=160" in vf and "metadata=print" in vf
    assert "-an" in cmd
