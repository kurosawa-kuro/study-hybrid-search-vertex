"""/search + /feedback endpoint tests — Phase 4 completion gate."""

from __future__ import annotations


def _search_payload() -> dict:
    return {
        "query": "赤羽駅徒歩10分 ペット可",
        "filters": {"max_rent": 150_000, "pet_ok": True},
        "top_k": 3,
    }


def test_search_returns_200_with_results(search_client) -> None:
    r = search_client.post("/search", json=_search_payload())
    assert r.status_code == 200
    body = r.json()
    assert "request_id" in body
    assert len(body["results"]) == 3


def test_search_results_preserve_lexical_rank_when_rerank_disabled(search_client) -> None:
    """Phase 4 gate: final_rank == lexical_rank until booster is wired (Phase 6)."""
    r = search_client.post("/search", json=_search_payload())
    body = r.json()
    for item in body["results"]:
        assert item["final_rank"] == item["lexical_rank"]
        assert item["score"] is None  # no booster.predict in Phase 4


def test_search_emits_ranking_log(app_with_search_stub) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(app_with_search_stub)
    r = client.post("/search", json=_search_payload())
    assert r.status_code == 200
    publisher = app_with_search_stub.state.ranking_log_publisher
    assert len(publisher.calls) == 1
    call = publisher.calls[0]
    # All 3 retrieved candidates are logged, not just top_k — so offline eval
    # keeps the full pool even when top_k < 100.
    assert len(call["candidates"]) == 3
    assert call["final_ranks"] == [1, 2, 3]
    assert call["model_path"] is None


def test_search_top_k_truncates_response(search_client) -> None:
    payload = _search_payload()
    payload["top_k"] = 2
    r = search_client.post("/search", json=payload)
    assert r.status_code == 200
    assert len(r.json()["results"]) == 2


def test_search_cache_hit_skips_second_retrieval(app_with_search_stub) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(app_with_search_stub)
    payload = _search_payload()
    r1 = client.post("/search", json=payload)
    assert r1.status_code == 200
    r2 = client.post("/search", json=payload)
    assert r2.status_code == 200

    retriever = app_with_search_stub.state.candidate_retriever
    assert len(retriever.calls) == 1


def test_search_rejects_empty_query(search_client) -> None:
    payload = _search_payload()
    payload["query"] = ""
    r = search_client.post("/search", json=payload)
    assert r.status_code == 422


def test_search_503_when_disabled(app_with_search_stub) -> None:
    from fastapi.testclient import TestClient

    app_with_search_stub.state.encoder = None
    client = TestClient(app_with_search_stub)
    r = client.post("/search", json=_search_payload())
    assert r.status_code == 503


def test_feedback_accepts_click(app_with_search_stub) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(app_with_search_stub)
    r = client.post(
        "/feedback",
        json={"request_id": "abc", "property_id": "P-001", "action": "click"},
    )
    assert r.status_code == 200
    assert r.json() == {"accepted": True}
    recorder = app_with_search_stub.state.feedback_recorder
    assert recorder.events == [{"request_id": "abc", "property_id": "P-001", "action": "click"}]


def test_feedback_rejects_unknown_action(app_with_search_stub) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(app_with_search_stub)
    r = client.post(
        "/feedback",
        json={"request_id": "abc", "property_id": "P-001", "action": "teleport"},
    )
    assert r.status_code == 422


def test_readyz_ok_when_search_enabled(app_with_search_stub) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(app_with_search_stub)
    r = client.get("/readyz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ready"
    assert body["search_enabled"] is True


def test_readyz_503_when_retriever_missing(app_with_search_stub) -> None:
    from fastapi.testclient import TestClient

    app_with_search_stub.state.candidate_retriever = None
    client = TestClient(app_with_search_stub)
    r = client.get("/readyz")
    assert r.status_code == 503


def test_healthz_unconditional(app_with_search_stub) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(app_with_search_stub)
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_readyz_reports_rerank_disabled_when_booster_missing(app_with_search_stub) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(app_with_search_stub)
    body = client.get("/readyz").json()
    assert body["rerank_enabled"] is False
    assert body["model_path"] is None


def test_readyz_reports_rerank_enabled_when_booster_set(app_with_search_stub) -> None:
    import numpy as np
    from fastapi.testclient import TestClient

    class _StubBooster:
        def predict(self, X: np.ndarray) -> np.ndarray:
            return -X[:, 8]

    app_with_search_stub.state.booster = _StubBooster()
    app_with_search_stub.state.model_path = "gs://stub/model.txt"
    client = TestClient(app_with_search_stub)
    body = client.get("/readyz").json()
    assert body["rerank_enabled"] is True
    assert body["model_path"] == "gs://stub/model.txt"


def test_search_returns_scores_when_booster_loaded(app_with_search_stub) -> None:
    import numpy as np
    from fastapi.testclient import TestClient

    class _StubBooster:
        def predict(self, X: np.ndarray) -> np.ndarray:
            return -X[:, 8]

    app_with_search_stub.state.booster = _StubBooster()
    app_with_search_stub.state.model_path = "gs://stub/lgbm/x/y/model.txt"

    client = TestClient(app_with_search_stub)
    r = client.post("/search", json=_search_payload())
    assert r.status_code == 200
    body = r.json()
    assert body["model_path"] == "gs://stub/lgbm/x/y/model.txt"
    for item in body["results"]:
        assert item["score"] is not None, "rerank-on must populate per-item score"


def test_ranking_log_receives_scores_when_booster_loaded(app_with_search_stub) -> None:
    import numpy as np
    from fastapi.testclient import TestClient

    class _StubBooster:
        def predict(self, X: np.ndarray) -> np.ndarray:
            return -X[:, 8]

    app_with_search_stub.state.booster = _StubBooster()
    app_with_search_stub.state.model_path = "gs://stub/model.txt"
    client = TestClient(app_with_search_stub)
    client.post("/search", json=_search_payload())
    publisher = app_with_search_stub.state.ranking_log_publisher
    call = publisher.calls[-1]
    assert all(isinstance(s, float) for s in call["scores"])
    assert call["model_path"] == "gs://stub/model.txt"
