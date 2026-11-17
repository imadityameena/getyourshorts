"""Stage 2: faster-whisper transcription with word timestamps."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.errors import NoSpeech
from app.core.logging import get_logger
from app.pipeline.models import Segment, Transcript, Word

log = get_logger("transcribe")


@lru_cache(maxsize=1)
def _load_model(name: str, use_gpu: bool) -> Any:
    from faster_whisper import WhisperModel

    if use_gpu:
        try:
            # int8_float16 fits large-v3-turbo into 4 GB VRAM.
            return WhisperModel(name, device="cuda", compute_type="int8_float16")
        except Exception as e:  # CUDA/cuDNN missing → CPU, don't fail the job
            log.warning("gpu_unavailable_falling_back_to_cpu", error=str(e))
    return WhisperModel(name if not use_gpu else "small", device="cpu", compute_type="int8")


def transcribe(audio: Path, model_name: str, use_gpu: bool) -> Transcript:
    model = _load_model(model_name, use_gpu)
    segments_iter, info = model.transcribe(
        str(audio),
        word_timestamps=True,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
        beam_size=5,
        condition_on_previous_text=False,  # reduces hallucinated repeats on long audio
    )
    segments: list[Segment] = []
    for s in segments_iter:
        words = [
            Word(
                start=float(w.start),
                end=float(w.end),
                text=w.word.strip(),
                prob=float(w.probability),
            )
            for w in (s.words or [])
            if w.word.strip()
        ]
        if words:
            segments.append(
                Segment(start=float(s.start), end=float(s.end), text=s.text.strip(), words=words)
            )
    if not segments:
        raise NoSpeech(str(audio))
    t = Transcript(language=info.language, duration=float(info.duration), segments=segments)
    log.info("transcribed", language=t.language, segments=len(segments), words=len(t.words()))
    return t
