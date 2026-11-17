"""Typed errors. `user_message` is safe to show in the UI; `retryable` drives the worker."""

from __future__ import annotations


class AppError(Exception):
    user_message = "Something went wrong while processing this video."
    retryable = True

    def __init__(self, detail: str = "", *, user_message: str | None = None) -> None:
        super().__init__(detail or self.user_message)
        if user_message:
            self.user_message = user_message


class InvalidUrl(AppError):
    user_message = "That doesn't look like a single YouTube video link."
    retryable = False


class VideoUnavailable(AppError):
    user_message = "This video is private, removed, or region-locked."
    retryable = False


class LiveStream(AppError):
    user_message = "Live streams and premieres can't be clipped. Try again after it ends."
    retryable = False


class TooLong(AppError):
    retryable = False

    def __init__(self, minutes: float, limit: int) -> None:
        super().__init__(
            f"duration {minutes:.0f} min > {limit} min",
            user_message=f"This video is {minutes:.0f} minutes long; the limit is {limit}.",
        )


class DownloadBlocked(AppError):
    user_message = (
        "YouTube blocked the download (bot check). Run the backend on a home connection "
        "or update yt-dlp."
    )


class DownloadFailed(AppError):
    user_message = "The video could not be downloaded. Please try again."


class NoSpeech(AppError):
    user_message = "No speech was found in this video, so there is nothing to caption or rank."
    retryable = False


class LLMFailed(AppError):
    user_message = "AI ranking unavailable."


class InsufficientDisk(AppError):
    user_message = "The server is low on disk space. Try again later."


class RenderFailed(AppError):
    user_message = "Rendering a clip failed."


class ExternalTimeout(AppError):
    user_message = "An external tool took too long to respond."


class JobCancelled(AppError):
    user_message = "Job cancelled."
    retryable = False
