"""Lexical retrieval abstraction (BM25-side candidate fetch)."""

from __future__ import annotations

from typing import Any, Protocol


class LexicalSearchPort(Protocol):
    """Returns lexical rank list as (property_id, lexical_rank)."""

    def search(
        self,
        *,
        query: str,
        filters: dict[str, Any],
        top_k: int,
    ) -> list[tuple[str, int]]: ...
