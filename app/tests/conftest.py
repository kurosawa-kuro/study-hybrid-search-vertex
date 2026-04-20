"""Shared fixtures for the /search + /feedback FastAPI tests.

The lifespan (which hits BigQuery + loads sentence-transformers) is bypassed
by swapping ``app.router.lifespan_context`` with a no-op; stub adapters are
assigned directly to ``app.state`` so request handlers see the Port surface
they expect.
"""

from __future__ import annotations

import numpy as np
import pytest
from app.config import ApiSettings
from app.entrypoints.api import create_app
from app.adapters.cache_store import InMemoryTTLCacheStore
from fastapi.testclient import TestClient


class _StubEncoder:
    model_name = "stub-e5"
    vector_dim = 4

    def encode_queries(self, queries):
        return np.array([[1.0, 0.0, 0.0, 0.0] for _ in queries], dtype=float)

    def encode_passages(self, passages):
        return self.encode_queries(passages)


class _StubCandidateRetriever:
    def __init__(self):
        self.calls: list[dict] = []

    def retrieve(self, *, query_text, query_vector, filters, top_k):
        from app.ports.candidate_retriever import Candidate

        self.calls.append({"filters": filters, "top_k": top_k})
        return [
            Candidate(
                property_id=f"P-{i:03d}",
                lexical_rank=i,
                semantic_rank=i,
                me5_score=0.9 - 0.1 * i,
                property_features={
                    "rent": 100_000 + 1000 * i,
                    "walk_min": 5 + i,
                    "age_years": 10,
                    "area_m2": 30.0,
                    "ctr": 0.1,
                    "fav_rate": 0.02,
                    "inquiry_rate": 0.01,
                },
            )
            for i in range(1, 4)
        ]


class _StubRankingLogPublisher:
    def __init__(self):
        self.calls: list[dict] = []

    def publish_candidates(self, *, request_id, candidates, final_ranks, scores, model_path):
        self.calls.append(
            {
                "request_id": request_id,
                "candidates": list(candidates),
                "final_ranks": list(final_ranks),
                "scores": list(scores),
                "model_path": model_path,
            }
        )


class _StubFeedbackRecorder:
    def __init__(self):
        self.events: list[dict] = []

    def record(self, *, request_id, property_id, action):
        self.events.append({"request_id": request_id, "property_id": property_id, "action": action})


@pytest.fixture
def app_with_search_stub():
    """App wired up with fake encoder + retriever + publishers (no BQ / torch).

    ``booster`` / ``model_path`` default to None → rerank-off (Phase 4 fallback).
    Tests that want to exercise the Phase 6 rerank path should assign a stub
    booster onto ``app.state.booster`` before invoking the test client.
    """
    from contextlib import asynccontextmanager

    app = create_app()
    app.state.encoder = _StubEncoder()
    app.state.candidate_retriever = _StubCandidateRetriever()
    app.state.ranking_log_publisher = _StubRankingLogPublisher()
    app.state.feedback_recorder = _StubFeedbackRecorder()
    app.state.search_cache = InMemoryTTLCacheStore(default_ttl_seconds=120)
    app.state.settings = ApiSettings()
    app.state.booster = None
    app.state.model_path = None

    @asynccontextmanager
    async def noop_lifespan(_app):
        yield

    app.router.lifespan_context = noop_lifespan
    return app


@pytest.fixture
def search_client(app_with_search_stub):
    return TestClient(app_with_search_stub)
