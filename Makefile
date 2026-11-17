# Backend commands run inside Docker (Python 3.12 + ffmpeg), so the host needs only Docker + Node.
DEV_IMG := shorts-backend:dev
RUN_DEV := docker run --rm -v $(CURDIR)/backend:/app -w /app $(DEV_IMG)

.PHONY: dev up up-gpu down image test test-all lint fmt typecheck fe-dev fe-test

image:            ## build the backend dev image
	docker build --target dev -t $(DEV_IMG) backend

dev:              ## API + worker + frontend with hot reload
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build

up:               ## production-style stack (CPU)
	docker compose up -d --build

up-gpu:           ## production-style stack with NVIDIA GPU
	docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build

down:
	docker compose down

test:             ## unit tests + coverage of the selection logic
	$(RUN_DEV) pytest -m "not integration" --cov=app.pipeline.select --cov-report=term-missing --cov-fail-under=70

test-all:         ## unit + integration (needs ffmpeg; generates a 2-min sample)
	$(RUN_DEV) pytest --cov=app --cov-report=term

lint:
	$(RUN_DEV) sh -c "ruff check . && ruff format --check ."

fmt:
	$(RUN_DEV) sh -c "ruff check --fix . && ruff format ."

typecheck:
	$(RUN_DEV) mypy app

fe-dev:
	cd frontend && npm run dev

fe-test:
	cd frontend && npm test -- --run
