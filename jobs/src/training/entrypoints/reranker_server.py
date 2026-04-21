"""Vertex custom prediction routine for LightGBM reranker."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import lightgbm as lgb
from common.storage.gcs_artifact_store import download_file
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


class RerankerRequest(BaseModel):
    instances: list[list[float]] = Field(min_length=1)


class RerankerResponse(BaseModel):
    predictions: list[float]


def _load_booster() -> lgb.Booster:
    storage_uri = os.getenv("AIP_STORAGE_URI", "").strip()
    if not storage_uri:
        raise RuntimeError("AIP_STORAGE_URI is required")
    tmpdir = Path(tempfile.mkdtemp(prefix="reranker-model-"))
    model_path = download_file(f"{storage_uri.rstrip('/')}/model.txt", tmpdir / "model.txt")
    return lgb.Booster(model_file=str(model_path))


app = FastAPI(title="vertex-reranker-server")
app.state.booster = None


@app.on_event("startup")
def _startup() -> None:
    app.state.booster = _load_booster()


@app.get(os.getenv("AIP_HEALTH_ROUTE", "/health"))
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(os.getenv("AIP_PREDICT_ROUTE", "/predict"), response_model=RerankerResponse)
def predict(request: RerankerRequest) -> RerankerResponse:
    booster: lgb.Booster | None = app.state.booster
    if booster is None:
        raise HTTPException(status_code=503, detail="booster not loaded")
    predictions = booster.predict(request.instances)
    return RerankerResponse(predictions=[float(value) for value in predictions])


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
