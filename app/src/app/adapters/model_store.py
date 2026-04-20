"""Concrete adapters for :class:`ModelUriResolver` + :class:`ModelArtifactSource`.

``BigQueryModelResolver`` re-uses the ranker's :class:`RankerTrainingRepository`
via ``latest_model_path`` so the API and the training job agree on "what is the
current best model" without a separate lookup path.

``GcsModelSource`` / ``LocalModelSource`` / ``DispatchModelSource`` cover the
three ways a model artifact might be addressable at startup time.
"""

from __future__ import annotations

from pathlib import Path

from common.storage.gcs_artifact_store import GcsPrefix, download_file
from google.cloud import bigquery


class BigQueryModelResolver:
    """Resolves the latest model URI from ``mlops.training_runs``.

    The underlying ``bigquery.Client`` is constructed lazily on first lookup so
    override-only dev mode does not require ADC.
    """

    def __init__(
        self,
        *,
        project_id: str,
        training_runs_table: str,
    ) -> None:
        self._project_id = project_id
        self._training_runs_table = training_runs_table

    def latest(self) -> str | None:
        client = bigquery.Client(project=self._project_id)
        query = f"""
            SELECT model_path
            FROM `{self._training_runs_table}`
            WHERE finished_at IS NOT NULL
            ORDER BY finished_at DESC
            LIMIT 1
        """
        rows = list(client.query(query).result())
        return rows[0]["model_path"] if rows else None


class GcsModelSource:
    """Downloads ``gs://.../model.txt`` into ``local_dir/model.txt``."""

    def materialize(self, model_uri: str, local_dir: Path) -> Path:
        prefix = GcsPrefix.parse(model_uri)
        if not prefix.prefix.endswith(".txt"):
            raise ValueError(f"Expected gs://.../model.txt, got {model_uri!r}")
        local_dir.mkdir(parents=True, exist_ok=True)
        local_path = local_dir / "model.txt"
        download_file(model_uri, local_path)
        return local_path


class LocalModelSource:
    """Accepts local filesystem paths; ``file://`` prefix is allowed for dev."""

    def materialize(self, model_uri: str, local_dir: Path) -> Path:
        raw = model_uri[len("file://") :] if model_uri.startswith("file://") else model_uri
        local_path = Path(raw).expanduser()
        if not local_path.is_file():
            raise FileNotFoundError(f"Local model file not found: {local_path}")
        return local_path


class DispatchModelSource:
    """Routes ``gs://`` URIs to GCS, everything else to local FS."""

    def __init__(self, *, gcs: GcsModelSource, local: LocalModelSource) -> None:
        self._gcs = gcs
        self._local = local

    def materialize(self, model_uri: str, local_dir: Path) -> Path:
        if model_uri.startswith("gs://"):
            return self._gcs.materialize(model_uri, local_dir)
        return self._local.materialize(model_uri, local_dir)
