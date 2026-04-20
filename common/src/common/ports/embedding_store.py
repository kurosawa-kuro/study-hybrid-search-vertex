"""Ports for embedding persistence + property text fetch.

Concrete adapter: :class:`common.adapters.bigquery_embedding_store.BigQueryEmbeddingStore`.
Keeping the Protocol here lets the embedding-job and tests depend on the
interface without pulling ``google.cloud.bigquery``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class PropertyText:
    property_id: str
    title: str
    description: str


@dataclass(frozen=True)
class EmbeddingRow:
    property_id: str
    embedding: list[float]
    text_hash: str
    model_name: str
    generated_at: datetime


class PropertyTextRepository(Protocol):
    def fetch_all(self) -> list[PropertyText]: ...


class EmbeddingStore(Protocol):
    def existing_hashes(self) -> dict[str, str]: ...
    def upsert(self, rows: list[EmbeddingRow]) -> int: ...
