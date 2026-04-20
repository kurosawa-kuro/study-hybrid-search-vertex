"""CacheStore adapters.

In-memory cache is the default MVP implementation. Redis-backed cache is a
future upgrade path and intentionally kept as a stub.
"""

from __future__ import annotations

from threading import RLock
from typing import Any

from cachetools import TTLCache

from ..ports.cache_store import CacheStore


class NoopCacheStore(CacheStore):
    def get(self, key: str) -> dict[str, Any] | None:
        return None

    def set(self, key: str, value: dict[str, Any], ttl_seconds: int) -> None:
        return None


class InMemoryTTLCacheStore(CacheStore):
    """Thread-safe process-local cache with TTL semantics.

    ``cachetools.TTLCache`` applies TTL at cache construction time, so this
    adapter uses ``default_ttl_seconds`` as the source of truth and accepts the
    ``ttl_seconds`` parameter for interface compatibility.
    """

    def __init__(self, *, maxsize: int = 2048, default_ttl_seconds: int = 120) -> None:
        self._ttl_seconds = max(1, int(default_ttl_seconds))
        self._cache: TTLCache[str, dict[str, Any]] = TTLCache(
            maxsize=maxsize,
            ttl=self._ttl_seconds,
        )
        self._lock = RLock()

    def get(self, key: str) -> dict[str, Any] | None:
        try:
            with self._lock:
                value = self._cache.get(key)
                if value is None:
                    return None
                return dict(value)
        except Exception:
            return None

    def set(self, key: str, value: dict[str, Any], ttl_seconds: int) -> None:
        _ = ttl_seconds
        try:
            with self._lock:
                self._cache[key] = dict(value)
        except Exception:
            return None


class MemorystoreRedisCacheStore(CacheStore):
    """Reserved for future Memorystore rollout.

    Phase R4 does not use Redis in this repository. Keep this class as a
    compatibility shim so DI can switch implementation later without changing
    service code.
    """

    def get(self, key: str) -> dict[str, Any] | None:
        return None

    def set(self, key: str, value: dict[str, Any], ttl_seconds: int) -> None:
        return None
