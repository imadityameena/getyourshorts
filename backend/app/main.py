from __future__ import annotations

import shutil
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import routes_clips, routes_jobs
from app.api.schemas import Health
from app.core.config import get_config, get_settings
from app.core.errors import AppError
from app.core.logging import setup_logging
from app.db.session import init_db
from app.storage.files import free_disk_gb


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    setup_logging(get_settings().log_level)
    init_db()
    yield


app = FastAPI(title="Shorts Generator", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().allowed_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(routes_jobs.router)
app.include_router(routes_clips.router)


@app.exception_handler(AppError)
async def _app_error(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse({"detail": exc.user_message}, status_code=422 if not exc.retryable else 503)


@app.get("/api/health", response_model=Health)
async def health() -> Health:
    s = get_settings()
    cfg = get_config()
    ffmpeg = shutil.which("ffmpeg") is not None
    disk = round(free_disk_gb(s.storage_dir), 1)
    providers = {"gemini": bool(s.gemini_api_key), "groq": bool(s.groq_api_key), "ollama": False}
    if s.ollama_url:
        try:
            async with httpx.AsyncClient(timeout=2) as c:
                providers["ollama"] = (
                    await c.get(f"{s.ollama_url.rstrip('/')}/api/tags")
                ).is_success
        except httpx.HTTPError:
            pass
    nvenc = False
    if s.use_gpu and ffmpeg:
        from app.pipeline.render.encode import nvenc_available

        nvenc = nvenc_available()
    ok = ffmpeg and disk >= cfg.limits.min_free_disk_gb
    status = "ok" if ok and any(providers.values()) else ("degraded" if ok else "error")
    return Health(
        status=status,
        ffmpeg=ffmpeg,
        nvenc=nvenc,
        disk_free_gb=disk,
        ai_providers=providers,
        gpu=s.use_gpu,
    )
