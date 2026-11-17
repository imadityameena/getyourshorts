# GetYourShorts

Paste a YouTube link and get back ready-to-upload vertical Shorts: the best moments picked using
real viewer data ("Most Replayed") plus AI ranking, cut on sentence boundaries, face-tracked to
9:16, with animated word-by-word captions and loudness-normalized audio.

Built entirely on free and open-source tools and free API tiers.

## Features

- **Smart clip selection.** Candidates come from the transcript's sentences. Each is scored on the
  heatmap, AI virality, hook strength, audio energy, speech pace and scene changes. Overlapping
  clips are removed and boundaries snap to whole words, with long silences trimmed.
- **AI with fallbacks.** Gemini → Groq → local Ollama. If every provider is unavailable, clips are
  still ranked using the other signals and marked "AI ranking unavailable".
- **Upload-ready output.** 1080×1920, face tracking with a smooth crop path (blurred-background
  fallback), highlighted captions, −14 LUFS audio, `+faststart` MP4s, thumbnails and a ZIP.
- **Resumable and cached.** Each stage writes its result to disk and is skipped if the result
  already exists. A crashed job resumes from the failed stage, and the same video with the same
  settings comes back instantly.
- **GPU support.** faster-whisper on CUDA and NVENC encoding, with automatic fallback to CPU.

## Quick start (Docker)

```bash
cp .env.example .env       # add GEMINI_API_KEY / GROQ_API_KEY (both optional)

docker compose up -d --build                                            # CPU
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build   # NVIDIA GPU
```

Open **http://localhost:8080**. The API is at http://localhost:8000 (interactive docs at `/docs`).

The first job downloads the Whisper model (about 0.5 GB on CPU, 1.6 GB on GPU) into `storage/.models`.

### Command line

```bash
docker compose run --rm worker python -m app.cli "https://youtu.be/VIDEO_ID" --clips 5 --min 30 --max 60
```

Options: `--crop face|center|blur`, `--captions bold|neon|minimal|none`.

## Configuration

| `.env` | Purpose |
|---|---|
| `GEMINI_API_KEY`, `GROQ_API_KEY` | Free-tier AI keys; providers without a key are skipped |
| `OLLAMA_URL` | Local LLM fallback (`http://host.docker.internal:11434` from Docker) |
| `WHISPER_MODEL` | Empty = auto (`large-v3-turbo` on GPU, `small` on CPU) |
| `USE_GPU` | `true` to use CUDA + NVENC |
| `MAX_VIDEO_MINUTES` | Reject longer videos (default 180) |
| `CLEANUP_HOURS` | Delete jobs and files after this long (default 24) |
| `ALLOWED_ORIGINS` | CORS origins, e.g. your Cloudflare Pages URL |

`backend/config.yaml` holds the tunables: scoring weights, AI models, caption style, crop
smoothing and render settings. Changing them invalidates the cache for new jobs.

## How clips are chosen

```
score = 0.35·Heatmap + 0.40·AI virality + 0.10·Hook + 0.08·Audio + 0.04·Pace + 0.03·Visual
```

When a video has no heatmap or no AI rating, those weights are redistributed proportionally across
the remaining signals. The top 40 candidates by a cheap pre-score go to the AI in batches. The final
list is sorted by score, deduplicated (no more than 20% overlap) and snapped to word boundaries.

## Architecture

```
React (Vite) ──HTTP/SSE──> FastAPI ──> SQLite job queue (Huey) ──> worker
                                                                     │
   1 Fetch → 2 Transcribe → 3 Analyze → 4 Select → 5 Render → 6 Package
   yt-dlp    faster-whisper  heatmap,    score,     crop,      thumbs,
                             audio,      snap,      captions,  ZIP
                             scenes, AI  dedupe     encode
                                                                     │
                              storage/{video_id}/  (cache for every stage)
```

```
backend/app/
  api/          REST routes + Pydantic schemas
  core/         config, logging, errors, retry helpers
  db/           SQLModel tables + helpers
  pipeline/     fetch, transcribe, analyze/, select/, render/, runner
  worker/       Huey tasks (job processing, resume on restart, cleanup)
frontend/src/
  components/   UrlInput, SettingsPanel, ProgressBar, ClipCard
  pages/        Home, Results
  hooks/        useJob (SSE progress), useHashRoute
  lib/          typed API client, formatting
```

## API

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/jobs` | Start a job: `{url, num_clips, min_len, max_len, crop_mode, caption_style}` |
| GET | `/api/jobs/{id}` | Status, stage, progress, error |
| GET | `/api/jobs/{id}/events` | Live progress (Server-Sent Events) |
| GET | `/api/jobs/{id}/clips` | Clips with scores, titles, hooks and reasons |
| GET | `/api/clips/{id}/file` | Stream (`?download=true` to download) one clip |
| GET | `/api/jobs/{id}/zip` | All clips as a ZIP |
| DELETE | `/api/jobs/{id}` | Cancel a job and delete its files |
| GET | `/api/health` | FFmpeg, GPU encoder, disk and AI provider status |

## Development

```bash
make image        # build the backend dev image (Python 3.12 + ffmpeg)
make test         # unit tests, ≥70% coverage on selection logic
make test-all     # + integration test: full pipeline on a 2-min sample
make lint         # ruff
make typecheck    # mypy --strict

cd frontend && npm install && npm run dev    # http://localhost:5173, proxies /api to :8000
npx vitest --run
```

CI (GitHub Actions) runs ruff, mypy, pytest and the frontend tests and build on every push.

## Hosting for free

YouTube often blocks downloads from data-center IPs, so the backend runs best on your own PC:

| Part | Where |
|---|---|
| Frontend | Cloudflare Pages / Vercel (build with `VITE_API_BASE=https://your-tunnel-url`) |
| Backend + worker | Your PC (home connection) |
| Connection | Cloudflare Tunnel (`cloudflared tunnel --url http://localhost:8000`) |

Add the Pages URL to `ALLOWED_ORIGINS`. The site works while your PC is on.

## Legal

Only clip videos you own or have permission to use. Downloading may be restricted by YouTube's
Terms of Service. Keep yt-dlp up to date (`pip install -U yt-dlp`), because YouTube changes often.
