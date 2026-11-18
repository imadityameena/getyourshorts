# CPU image (default). For NVIDIA GPUs use Dockerfile.gpu via docker-compose.gpu.yml.
FROM python:3.12-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/data/.models/hf

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg fontconfig libgl1 libegl1 libgles2 libglib2.0-0 curl \
 && rm -rf /var/lib/apt/lists/*

# Caption font (SIL Open Font License)
RUN mkdir -p /usr/share/fonts/truetype/montserrat \
 && for w in Bold ExtraBold Black; do \
      curl -fsSL -o /usr/share/fonts/truetype/montserrat/Montserrat-$w.ttf \
        "https://raw.githubusercontent.com/JulietaUla/Montserrat/master/fonts/ttf/Montserrat-$w.ttf"; \
    done \
 && fc-cache -f

WORKDIR /app
COPY pyproject.toml ./
# Install dependencies first (cached layer), then the code.
RUN mkdir app && touch app/__init__.py \
 && pip install ".[ml]" \
 && rm -rf app

COPY . .
# Run from source (not site-packages) so config.yaml and assets resolve next to the code.
ENV PYTHONPATH=/app \
    CONFIG_PATH=/app/config.yaml \
    STORAGE_DIR=/data
VOLUME ["/data"]
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ---- dev / CI image: adds test + lint tooling ---------------------------------
FROM base AS dev
RUN pip install ".[ml,dev]"

# ---- GPU image: CUDA libraries for faster-whisper (CTranslate2) --------------
# NVENC encoding needs nothing extra: Debian's ffmpeg loads the driver's libnvidia-encode.
FROM base AS gpu
RUN pip install "nvidia-cublas-cu12" "nvidia-cudnn-cu12==9.*"
ENV LD_LIBRARY_PATH=/usr/local/lib/python3.12/site-packages/nvidia/cublas/lib:/usr/local/lib/python3.12/site-packages/nvidia/cudnn/lib \
    USE_GPU=true \
    NVIDIA_DRIVER_CAPABILITIES=compute,video,utility
