"""Vertex custom prediction routine for multilingual-e5-base."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from common.embeddings.e5_encoder import E5Encoder
from common.storage.gcs_artifact_store import GcsPrefix, download_file
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


class EncoderInstance(BaseModel):
    text: str = Field(min_length=1)
    kind: str = Field(pattern="^(query|passage)$")


class EncoderRequest(BaseModel):
    instances: list[EncoderInstance]


class EncoderResponse(BaseModel):
    predictions: list[list[float]]


def _download_artifact_dir(gcs_uri: str, workdir: Path) -> Path:
    prefix = GcsPrefix.parse(gcs_uri)
    local_root = workdir / "model"
    local_root.mkdir(parents=True, exist_ok=True)
    if prefix.prefix and not prefix.prefix.endswith("/"):
        raise RuntimeError("AIP_STORAGE_URI must point to a directory prefix")
    from google.cloud import storage

    client = storage.Client()
    for blob in client.list_blobs(prefix.bucket, prefix=prefix.prefix):
        if blob.name.endswith("/"):
            continue
        rel = blob.name[len(prefix.prefix) :].lstrip("/") if prefix.prefix else blob.name
        download_file(f"gs://{prefix.bucket}/{blob.name}", local_root / rel)
    return local_root


def _load_encoder() -> E5Encoder:
    storage_uri = os.getenv("AIP_STORAGE_URI", "").strip()
    if not storage_uri:
        raise RuntimeError("AIP_STORAGE_URI is required")
    tmpdir = Path(tempfile.mkdtemp(prefix="encoder-model-"))
    model_dir = _download_artifact_dir(storage_uri, tmpdir)
    return E5Encoder.load(model_dir=model_dir)


app = FastAPI(title="vertex-encoder-server")
app.state.encoder = None


@app.on_event("startup")
def _startup() -> None:
    app.state.encoder = _load_encoder()


@app.get(os.getenv("AIP_HEALTH_ROUTE", "/health"))
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(os.getenv("AIP_PREDICT_ROUTE", "/predict"), response_model=EncoderResponse)
def predict(request: EncoderRequest) -> EncoderResponse:
    encoder: E5Encoder | None = app.state.encoder
    if encoder is None:
        raise HTTPException(status_code=503, detail="encoder not loaded")
    queries = [item.text for item in request.instances if item.kind == "query"]
    passages = [item.text for item in request.instances if item.kind == "passage"]
    results: list[list[float]] = []
    query_vectors = encoder.encode_queries(queries).tolist() if queries else []
    passage_vectors = encoder.encode_passages(passages).tolist() if passages else []
    query_index = 0
    passage_index = 0
    for item in request.instances:
        if item.kind == "query":
            results.append([float(v) for v in query_vectors[query_index]])
            query_index += 1
        else:
            results.append([float(v) for v in passage_vectors[passage_index]])
            passage_index += 1
    return EncoderResponse(predictions=results)


def main() -> None:
    import uvicorn

    uvicorn.run(
        app,
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("AIP_HTTP_PORT", os.getenv("PORT", "8080"))),
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
    )


if __name__ == "__main__":
    main()
