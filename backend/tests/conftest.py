from __future__ import annotations

import os
import tempfile
from pathlib import Path

# Isolate storage/DB before any app module reads settings.
_TMP = Path(tempfile.mkdtemp(prefix="shorts-test-"))
os.environ["STORAGE_DIR"] = str(_TMP)  # always isolate, even inside the Docker image
os.environ.setdefault("GEMINI_API_KEY", "")
os.environ.setdefault("GROQ_API_KEY", "")
os.environ.setdefault("OLLAMA_URL", "")

import pytest

from app.pipeline.models import Word


def make_words(
    text: str, start: float = 0.0, wps: float = 3.0, gaps: dict[int, float] | None = None
) -> list[Word]:
    """Evenly spaced words; `gaps` inserts extra silence before word index i."""
    gaps = gaps or {}
    out: list[Word] = []
    t = start
    step = 1.0 / wps
    for i, tok in enumerate(text.split()):
        t += gaps.get(i, 0.0)
        out.append(Word(start=round(t, 3), end=round(t + step * 0.8, 3), text=tok))
        t += step
    return out


@pytest.fixture
def storage_dir() -> Path:
    return _TMP
