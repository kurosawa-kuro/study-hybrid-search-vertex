# Multi-stage build using uv — produces a slim Cloud Run Jobs image for LightGBM training.
# BuildKit cache mounts removed so the Dockerfile works under Cloud Build's
# `gcr.io/cloud-builders/docker` (no buildx) as well as GitHub Actions runners.

FROM ghcr.io/astral-sh/uv:0.5.4-python3.12-bookworm-slim AS builder

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /src

# Copy workspace manifests first for better caching
COPY pyproject.toml uv.lock* ./
COPY common/pyproject.toml common/pyproject.toml
COPY jobs/pyproject.toml    jobs/pyproject.toml
COPY app/pyproject.toml     app/pyproject.toml

# Sync only the jobs package and its transitive deps
RUN uv sync --frozen --no-dev --package jobs --no-install-project

# Now copy source and build the workspace packages
COPY common/ common/
COPY jobs/   jobs/
# --no-editable: see app/Dockerfile for rationale (runtime stage only copies
# /opt/venv, so editable installs pointing at /src/ would 404 at import time).
RUN uv sync --frozen --no-dev --package jobs --no-editable


FROM python:3.12-slim-bookworm AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LOG_AS_JSON=1

RUN useradd --system --uid 1001 --home-dir /home/app app \
    && mkdir -p /home/app && chown -R app:app /home/app
USER app
WORKDIR /home/app

ENTRYPOINT ["train"]
