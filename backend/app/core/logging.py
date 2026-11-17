"""structlog JSON logging; job_id / stage are bound via contextvars."""

from __future__ import annotations

import logging
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager

import structlog


def setup_logging(level: str = "INFO", json_logs: bool = True) -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level.upper())
    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer() if json_logs else structlog.dev.ConsoleRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level.upper())),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "app") -> structlog.stdlib.BoundLogger:
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger


@contextmanager
def log_stage(stage: str) -> Iterator[None]:
    """Bind `stage` to every log line inside and log how long the stage took."""
    log = get_logger("pipeline")
    with structlog.contextvars.bound_contextvars(stage=stage):
        start = time.perf_counter()
        log.info("stage_start")
        try:
            yield
        except Exception:
            log.warning("stage_failed", seconds=round(time.perf_counter() - start, 2))
            raise
        log.info("stage_done", seconds=round(time.perf_counter() - start, 2))
