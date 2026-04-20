"""Pure orchestration for /search.

Two rerank modes coexist:

* **Phase 4 fallback** (``booster=None``): ``final_rank = lexical_rank`` — the
  VECTOR_SEARCH order is returned as-is, ``score`` is ``None`` everywhere.
* **Phase 6 rerank** (``booster`` supplied): features are assembled via
  ``common.feature_engineering.build_ranker_features``, ``booster.predict()``
  produces a per-candidate score, candidates are sorted by score descending
  and their ``final_rank`` is the new 1-based position.

The ranking_log publisher always receives the full candidate pool plus the
score list (``None`` in fallback mode) so offline evaluation can compare
both regimes even during a gradual rollout.

This module stays free of GCP SDK imports so tests can exercise it with the
fake adapters in ``app/tests/conftest.py``.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Protocol

import numpy as np
from common.feature_engineering import build_ranker_features

from common import FEATURE_COLS_RANKER

from ..ports.candidate_retriever import Candidate, CandidateRetriever, RankingLogPublisher

RRF_K: int = 60
DEFAULT_SEARCH_CACHE_TTL_SECONDS: int = 120


class _Booster(Protocol):
    """Structural type for anything with a ``predict(np.ndarray) -> np.ndarray`` surface.

    Declared locally so this module does not import ``lightgbm`` (the
    boundary test bans it for pure-logic services).
    """

    def predict(self, X: np.ndarray) -> np.ndarray: ...


def _score_candidates(candidates: list[Candidate], booster: _Booster) -> list[float]:
    """Build the feature matrix in FEATURE_COLS_RANKER order and call predict."""
    rows = [
        build_ranker_features(
            property_features=cand.property_features,
            me5_score=cand.me5_score,
            lexical_rank=cand.lexical_rank,
            semantic_rank=cand.semantic_rank,
        )
        for cand in candidates
    ]
    matrix = np.array([[row[col] for col in FEATURE_COLS_RANKER] for row in rows], dtype=float)
    return [float(x) for x in booster.predict(matrix)]


def run_search(
    *,
    retriever: CandidateRetriever,
    publisher: RankingLogPublisher,
    request_id: str,
    query_text: str,
    query_vector: list[float],
    filters: dict[str, Any],
    top_k: int,
    booster: _Booster | None = None,
    model_path: str | None = None,
) -> list[tuple[Candidate, int]]:
    """Execute one search and return ``[(candidate, final_rank), ...]`` truncated to top_k.

    If ``booster`` is ``None`` the fallback path kicks in (Phase 4 contract).
    Either way, ranking_log receives one row per retrieved candidate (not just
    the top_k) so offline eval keeps the full pool.
    """
    candidates = retriever.retrieve(
        query_text=query_text,
        query_vector=query_vector,
        filters=filters,
        top_k=top_k,
    )
    if not candidates:
        publisher.publish_candidates(
            request_id=request_id,
            candidates=[],
            final_ranks=[],
            scores=[],
            model_path=model_path if booster is not None else None,
        )
        return []

    if booster is not None:
        scores = _score_candidates(candidates, booster)
        # Stable descending sort; higher score wins. Ties preserve lexical order
        # because ``sorted`` is stable and candidates are already lexically ordered.
        order = sorted(range(len(candidates)), key=lambda i: -scores[i])
        ranked = [(candidates[i], rank + 1) for rank, i in enumerate(order)]
        # publish in lexical (original) order so ranking_log matches the
        # candidates' `lexical_rank` column 1:1.
        scores_nullable: list[float | None] = list(scores)
        publisher.publish_candidates(
            request_id=request_id,
            candidates=candidates,
            final_ranks=[
                next(rank for cand, rank in ranked if cand.property_id == c.property_id)
                for c in candidates
            ],
            scores=scores_nullable,
            model_path=model_path,
        )
        return ranked[:top_k]

    # Fallback: rerank disabled or booster missing.
    final_ranks = [c.lexical_rank for c in candidates]
    publisher.publish_candidates(
        request_id=request_id,
        candidates=candidates,
        final_ranks=final_ranks,
        scores=[None] * len(candidates),
        model_path=None,
    )
    paired = list(zip(candidates, final_ranks, strict=True))
    paired.sort(key=lambda cr: cr[1])
    return paired[:top_k]


def normalize_search_cache_key(*, query: str, filters: dict[str, Any], top_k: int) -> str:
    """Stable SHA256 cache key for /search requests."""
    payload = {
        "query": query.strip(),
        "filters": filters,
        "top_k": int(top_k),
    }
    normalized = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def rrf_fuse(
    *,
    lexical_results: list[tuple[str, int]],
    semantic_results: list[tuple[str, int]],
    top_n: int,
    k: int = RRF_K,
) -> list[str]:
    """Reciprocal Rank Fusion over two rank lists.

    Inputs are ``(property_id, rank)`` tuples where rank is 1-based.
    """
    scores: dict[str, float] = {}
    for property_id, rank in lexical_results:
        scores[property_id] = scores.get(property_id, 0.0) + 1.0 / (k + rank)
    for property_id, rank in semantic_results:
        scores[property_id] = scores.get(property_id, 0.0) + 1.0 / (k + rank)

    sorted_ids = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return [property_id for property_id, _ in sorted_ids[:top_n]]
