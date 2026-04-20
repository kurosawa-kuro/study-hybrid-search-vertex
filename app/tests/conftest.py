"""Shared fixtures for the /search + /feedback FastAPI tests."""

from __future__ import annotations

import pytest
from app.adapters.cache_store import InMemoryTTLCacheStore
from app.config import ApiSettings
from app.entrypoints.api import create_app
from fastapi.testclient import TestClient


class _StubEncoderClient:
    def embed(self, text: str, kind: str) -> list[float]:
        assert kind == "query"
        assert text
        return [1.0, 0.0, 0.0, 0.0]


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

    ``reranker_client`` / ``model_path`` default to None → rerank-off.
    Tests that want rerank-on can assign a stub reranker onto app.state.
    """
    from contextlib import asynccontextmanager

    app = create_app()
    app.state.encoder_client = _StubEncoderClient()
    app.state.candidate_retriever = _StubCandidateRetriever()
    app.state.ranking_log_publisher = _StubRankingLogPublisher()
    app.state.feedback_recorder = _StubFeedbackRecorder()
    app.state.search_cache = InMemoryTTLCacheStore(default_ttl_seconds=120)
    app.state.settings = ApiSettings()
    app.state.reranker_client = None
    app.state.model_path = None

    @asynccontextmanager
    async def noop_lifespan(_app):
        yield

    app.router.lifespan_context = noop_lifespan
    return app


@pytest.fixture
def search_client(app_with_search_stub):
    return TestClient(app_with_search_stub)
