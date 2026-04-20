"""BigQuery-backed adapter for :class:`EmbeddingStore` + property text fetch.

Used by the ``embedding-job`` (Cloud Run Jobs): read cleaned property text from
``feature_mart.properties_cleaned``, compare the stored ``text_hash`` column to
decide which rows to re-encode, then upsert via MERGE into
``feature_mart.property_embeddings``.
"""

from __future__ import annotations

from datetime import datetime, timezone

from google.cloud import bigquery

from ..logging import get_logger
from ..ports.embedding_store import (
    EmbeddingRow,
    PropertyText,
)

logger = get_logger(__name__)


class BigQueryPropertyTextRepository:
    """Reads property_id + title + description from properties_cleaned."""

    def __init__(
        self,
        *,
        project_id: str,
        cleaned_table: str,
        client: bigquery.Client | None = None,
    ) -> None:
        self._project_id = project_id
        self._cleaned_table = cleaned_table
        self._client = client or bigquery.Client(project=project_id)

    def fetch_all(self) -> list[PropertyText]:
        query = f"""
            SELECT property_id, title, description
            FROM `{self._cleaned_table}`
            WHERE title IS NOT NULL
        """
        rows = self._client.query(query).result()
        return [
            PropertyText(
                property_id=r["property_id"],
                title=r["title"] or "",
                description=r["description"] or "",
            )
            for r in rows
        ]


class BigQueryEmbeddingStore:
    """BQ-backed :class:`EmbeddingStore` adapter."""

    def __init__(
        self,
        *,
        project_id: str,
        embeddings_table: str,
        client: bigquery.Client | None = None,
    ) -> None:
        self._project_id = project_id
        self._embeddings_table = embeddings_table
        self._client = client or bigquery.Client(project=project_id)

    def existing_hashes(self) -> dict[str, str]:
        query = f"SELECT property_id, text_hash FROM `{self._embeddings_table}`"
        rows = self._client.query(query).result()
        return {r["property_id"]: r["text_hash"] for r in rows}

    def upsert(self, rows: list[EmbeddingRow]) -> int:
        if not rows:
            return 0
        # Stage via insert_rows_json into a temp table, then MERGE. For this
        # prototype we use plain DELETE + INSERT in a scripted statement; data
        # volume is small (~tens of thousands of rows).
        payload = [
            {
                "property_id": r.property_id,
                "embedding": r.embedding,
                "text_hash": r.text_hash,
                "model_name": r.model_name,
                "generated_at": r.generated_at.astimezone(timezone.utc).isoformat(),
            }
            for r in rows
        ]
        ids = [r.property_id for r in rows]
        delete_stmt = f"""
            DELETE FROM `{self._embeddings_table}`
            WHERE property_id IN UNNEST(@ids)
        """
        self._client.query(
            delete_stmt,
            job_config=bigquery.QueryJobConfig(
                query_parameters=[bigquery.ArrayQueryParameter("ids", "STRING", ids)]
            ),
        ).result()
        errors = self._client.insert_rows_json(self._embeddings_table, payload)
        if errors:
            raise RuntimeError(f"BigQuery insert_rows_json failed: {errors}")
        logger.info("Upserted %d embeddings into %s", len(rows), self._embeddings_table)
        return len(rows)


def _now() -> datetime:
    return datetime.now(timezone.utc)
