"""Cache store abstraction for /search responses."""

from __future__ import annotations

from typing import Any, Protocol


class CacheStore(Protocol):
    """Simple key/value cache used by the API edge."""

    def get(self, key: str) -> dict[str, Any] | None: ...

    def set(self, key: str, value: dict[str, Any], ttl_seconds: int) -> None: ...
