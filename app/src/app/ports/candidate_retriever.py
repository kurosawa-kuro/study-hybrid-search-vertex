"""Ports for candidate retrieval + ranking-log / feedback persistence.

Defined as Protocols so the /search service can be exercised by unit tests
without pulling ``google.cloud.bigquery``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class Candidate:
    """One candidate property returned from the lexical / vector search step."""

    property_id: str
    # BM25-side rank from lexical retrieval (Meilisearch).
    lexical_rank: int
    # VECTOR_SEARCH-side rank from semantic retrieval.
    semantic_rank: int
    me5_score: float
    property_features: dict[str, Any]


class CandidateRetriever(Protocol):
    def retrieve(
        self,
        *,
        query_text: str,
        query_vector: list[float],
        filters: dict[str, Any],
        top_k: int,
    ) -> list[Candidate]: ...


class FeedbackRecorder(Protocol):
    """Writes a feedback event (click / favorite / inquiry) to the log sink."""

    def record(self, *, request_id: str, property_id: str, action: str) -> None: ...


class RankingLogPublisher(Protocol):
    """Writes one row per (request_id, property_id) candidate to the ranking log.

    ``scores`` is ``[None, None, ...]`` in Phase 4 fallback mode (no booster);
    in Phase 6 rerank mode each entry matches the candidate by index.
    """

    def publish_candidates(
        self,
        *,
        request_id: str,
        candidates: list[Candidate],
        final_ranks: list[int],
        scores: list[float | None],
        model_path: str | None,
    ) -> None: ...
