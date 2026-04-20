"""Factory for BigQuery-backed embedding store + property text repository.

Thin wrappers that translate ``TrainSettings`` into the fully-qualified table
names expected by the ``common.adapters`` classes. The embedding-job entrypoint
injects these into the pure-logic orchestrator so unit tests can swap them out.
"""

from __future__ import annotations

from common.adapters.bigquery_embedding_store import (
    BigQueryEmbeddingStore,
    BigQueryPropertyTextRepository,
)

from ..config import TrainSettings


def create_property_text_repository(
    settings: TrainSettings,
) -> BigQueryPropertyTextRepository:
    cleaned_table = f"{settings.project_id}.{settings.bq_dataset_feature_mart}.properties_cleaned"
    return BigQueryPropertyTextRepository(
        project_id=settings.project_id,
        cleaned_table=cleaned_table,
    )


def create_embedding_store(settings: TrainSettings) -> BigQueryEmbeddingStore:
    embeddings_table = (
        f"{settings.project_id}.{settings.bq_dataset_feature_mart}.property_embeddings"
    )
    return BigQueryEmbeddingStore(
        project_id=settings.project_id,
        embeddings_table=embeddings_table,
    )
