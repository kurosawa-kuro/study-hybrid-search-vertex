FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    AIP_HTTP_PORT=8080

WORKDIR /workspace

RUN pip install --no-cache-dir --upgrade pip

COPY common /workspace/common
COPY jobs /workspace/jobs

RUN pip install --no-cache-dir /workspace/common /workspace/jobs

CMD ["python", "-m", "training.entrypoints.encoder_server"]
