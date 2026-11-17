"""Audio energy: RMS envelope of the 16 kHz mono WAV, computed with numpy.

(librosa's RMS is the same maths; numpy keeps the dependency tree smaller.)
"""

from __future__ import annotations

import wave
from collections.abc import Sequence
from pathlib import Path

import numpy as np


def rms_envelope(wav_path: Path, hop_s: float = 0.5) -> list[float]:
    """RMS per `hop_s` window, streamed so a 3-hour file doesn't blow up memory."""
    out: list[float] = []
    with wave.open(str(wav_path), "rb") as w:
        if w.getsampwidth() != 2:
            raise ValueError("expected 16-bit PCM")
        channels = w.getnchannels()
        hop = max(1, int(w.getframerate() * hop_s))
        while True:
            raw = w.readframes(hop)
            if not raw:
                break
            x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            if channels > 1:
                x = x.reshape(-1, channels).mean(axis=1)
            out.append(float(np.sqrt(np.mean(x * x))) if x.size else 0.0)
    return out


def relative_energy(rms: Sequence[float], hop_s: float, start: float, end: float) -> float:
    """Clip mean RMS relative to the whole video, mapped to 0..1 (video average → 0.5)."""
    if not rms:
        return 0.5
    arr = np.asarray(rms, dtype=np.float64)
    overall = float(arr.mean())
    if overall <= 1e-9:
        return 0.0
    i0 = max(0, int(start / hop_s))
    i1 = min(len(arr), max(i0 + 1, int(np.ceil(end / hop_s))))
    clip = float(arr[i0:i1].mean()) if i1 > i0 else 0.0
    return float(np.clip(clip / overall / 2.0, 0.0, 1.0))
