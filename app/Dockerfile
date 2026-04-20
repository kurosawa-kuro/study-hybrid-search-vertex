# Multi-stage uv build for Cloud Run Service (FastAPI + LightGBM).
# BuildKit cache mounts removed so the Dockerfile works under Cloud Build's
# `gcr.io/cloud-builders/docker` (no buildx) as well as GitHub Actions runners.

FROM ghcr.io/astral-sh/uv:0.5.4-python3.12-bookworm-slim AS builder

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /src

COPY pyproject.toml uv.lock* ./
COPY common/pyproject.toml common/pyproject.toml
COPY jobs/pyproject.toml    jobs/pyproject.toml
COPY app/pyproject.toml     app/pyproject.toml

RUN uv sync --frozen --no-dev --package app --no-install-project

COPY common/ common/
COPY app/    app/
# --no-editable: workspace packages (`common`, `app`) are physically copied
# into /opt/venv/lib/python3.12/site-packages instead of being registered as
# editable installs that point at /src/. The runtime stage only copies
# /opt/venv, so an editable install would produce ModuleNotFoundError.
RUN uv sync --frozen --no-dev --package app --no-editable


FROM python:3.12-slim-bookworm AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    LOG_AS_JSON=1 \
    GCP_LOGGING_ENABLED=1

RUN useradd --system --uid 1001 --home-dir /home/app app \
    && mkdir -p /home/app /tmp/model \
    && chown -R app:app /home/app /tmp/model
USER app
WORKDIR /home/app

EXPOSE 8080
CMD ["sh", "-c", "uvicorn app.entrypoints.api:app --host 0.0.0.0 --port ${PORT}"]
