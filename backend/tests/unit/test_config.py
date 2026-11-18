import logging
from pathlib import Path

import pytest

from app.core.config import BACKEND_DIR, load_app_config


def test_repo_config_defines_ai_providers() -> None:
    cfg = load_app_config(BACKEND_DIR / "config.yaml")
    assert [p.name for p in cfg.llm.providers] == ["gemini", "groq", "ollama"]
    assert sum(cfg.selection.weights.model_dump().values()) == pytest.approx(1.0)
    assert {"bold", "neon", "minimal"} <= cfg.captions.styles.keys()


def test_missing_config_is_loud(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR):
        cfg = load_app_config(tmp_path / "nope.yaml")
    assert cfg.llm.providers == []
    assert "config.yaml not found" in caplog.text
