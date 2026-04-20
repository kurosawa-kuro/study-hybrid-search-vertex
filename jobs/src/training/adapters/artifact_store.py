"""GCS-backed :class:`ArtifactUploader` adapter."""

from __future__ import annotations

from pathlib import Path

from common.storage.gcs_artifact_store import model_prefix, upload_directory


class GcsArtifactUploader:
    """Uploads artifacts under ``gs://{bucket}/lgbm/{date}/{run_id}/``."""

    def __init__(self, *, bucket: str) -> None:
        self._bucket = bucket

    def upload(self, local_dir: Path, *, run_id: str, date_str: str) -> str:
        dest = model_prefix(bucket=self._bucket, run_id=run_id, date_str=date_str)
        upload_directory(local_dir, dest)
        return dest.uri("model.txt")
