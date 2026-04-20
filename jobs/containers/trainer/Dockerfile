FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /workspace

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --upgrade pip

COPY common /workspace/common
COPY jobs /workspace/jobs

RUN pip install --no-cache-dir /workspace/common /workspace/jobs

CMD ["python", "-m", "training.entrypoints.rank_cli", "--mode", "kfp"]
