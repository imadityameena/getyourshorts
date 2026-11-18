"""Settings from environment (.env) plus tunables from config.yaml."""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Weights(BaseModel):
    heatmap: float = 0.35
    ai_virality: float = 0.40
    hook: float = 0.10
    audio: float = 0.08
    pace: float = 0.04
    visual: float = 0.03


class SelectionConfig(BaseModel):
    weights: Weights = Weights()
    prefilter_top_k: int = 40
    prefilter_max_overlap: float = 0.6
    max_overlap: float = 0.2
    pad_start_s: float = 0.15
    pad_end_s: float = 0.30
    max_inner_silence_s: float = 0.6
    sentence_gap_s: float = 1.2
    target_wps: float = 3.0
    max_cuts_per_min: float = 12.0


class ProviderConfig(BaseModel):
    name: str
    model: str


class LLMConfig(BaseModel):
    batch_size: int = 10
    timeout_s: float = 60
    providers: list[ProviderConfig] = Field(default_factory=list)


class LimitsConfig(BaseModel):
    max_video_minutes: int = 180
    max_download_height: int = 1080
    min_free_disk_gb: float = 3
    download_timeout_s: float = 1800
    ffmpeg_timeout_s: float = 900


class RenderConfig(BaseModel):
    fps: int = 30
    width: int = 1080
    height: int = 1920
    sample_fps: float = 5
    ema_alpha: float = 0.2
    dead_zone: float = 0.10
    max_face_gap_s: float = 1.0
    max_parallel_cpu: int = 2
    max_parallel_gpu: int = 3


class CaptionStyle(BaseModel):
    primary: str = "FFFFFF"
    highlight: str = "00E5FF"
    uppercase: bool = True


class CaptionsConfig(BaseModel):
    max_words: int = 3
    font: str = "Montserrat"
    font_size: int = 84
    outline: int = 4
    margin_v: int = 560
    styles: dict[str, CaptionStyle] = Field(default_factory=lambda: {"bold": CaptionStyle()})


class AppConfig(BaseModel):
    limits: LimitsConfig = LimitsConfig()
    selection: SelectionConfig = SelectionConfig()
    llm: LLMConfig = LLMConfig()
    render: RenderConfig = RenderConfig()
    captions: CaptionsConfig = CaptionsConfig()

    def fingerprint(self) -> str:
        """Hash of everything that changes output; part of the cache key."""
        data = {
            "selection": self.selection.model_dump(),
            "render": self.render.model_dump(),
            "captions": self.captions.model_dump(),
        }
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:12]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gemini_api_key: str = ""
    groq_api_key: str = ""
    ollama_url: str = "http://localhost:11434"
    whisper_model: str = ""  # empty → auto: large-v3-turbo on GPU, small on CPU
    use_gpu: bool = False
    max_video_minutes: int | None = None
    storage_dir: Path = BACKEND_DIR.parent / "storage"
    cleanup_hours: float = 24
    config_path: Path = BACKEND_DIR / "config.yaml"
    allowed_origins: str = "http://localhost:5173,http://localhost:8080"
    log_level: str = "INFO"

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.storage_dir / 'app.db'}"

    @property
    def huey_path(self) -> Path:
        return self.storage_dir / "huey.db"

    @property
    def resolved_whisper_model(self) -> str:
        return self.whisper_model or ("large-v3-turbo" if self.use_gpu else "small")


def load_app_config(path: Path) -> AppConfig:
    if not path.exists():
        # Defaults have no AI providers, so this would silently disable AI ranking.
        import logging

        logging.getLogger("config").error(
            "config.yaml not found at %s; using built-in defaults (no AI providers). "
            "Set CONFIG_PATH.",
            path,
        )
        return AppConfig()
    raw: dict[str, Any] = yaml.safe_load(path.read_text()) or {}
    return AppConfig.model_validate(raw)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.storage_dir.mkdir(parents=True, exist_ok=True)
    return s


@lru_cache
def get_config() -> AppConfig:
    settings = get_settings()
    cfg = load_app_config(settings.config_path)
    if settings.max_video_minutes is not None:
        cfg.limits.max_video_minutes = settings.max_video_minutes
    return cfg
