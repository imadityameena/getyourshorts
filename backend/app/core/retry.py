"""Retry-with-backoff and subprocess helpers used for every external call."""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable, Sequence
from typing import TypeVar

from app.core.errors import AppError, ExternalTimeout
from app.core.logging import get_logger

T = TypeVar("T")
log = get_logger("retry")


def with_retries(
    fn: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay: float = 2.0,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
    what: str = "call",
) -> T:
    """Run fn up to `attempts` times with exponential backoff.

    Non-retryable AppErrors are raised immediately.
    """
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except AppError as e:
            if not e.retryable or attempt == attempts:
                raise
            err: BaseException = e
        except retry_on as e:
            if attempt == attempts:
                raise
            err = e
        delay = base_delay * 2 ** (attempt - 1)
        log.warning("retrying", what=what, attempt=attempt, delay=delay, error=str(err)[:300])
        time.sleep(delay)
    raise AssertionError("unreachable")


def run_cmd(
    cmd: Sequence[str], *, timeout: float, what: str = "command"
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess with a timeout; raise with stderr tail on failure."""
    try:
        proc = subprocess.run(
            list(cmd), capture_output=True, text=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired as e:
        raise ExternalTimeout(f"{what} timed out after {timeout}s") from e
    if proc.returncode != 0:
        tail = (proc.stderr or "")[-1500:]
        raise subprocess.CalledProcessError(proc.returncode, list(cmd), proc.stdout, tail)
    return proc
