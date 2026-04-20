"""Port for reranker inference providers."""

from __future__ import annotations

from typing import Protocol


class RerankerClient(Protocol):
    """Scores one batch of ranker-feature rows."""

    def predict(self, instances: list[list[float]]) -> list[float]: ...
