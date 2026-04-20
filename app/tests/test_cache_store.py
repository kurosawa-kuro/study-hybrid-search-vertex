"""CacheStore adapter tests."""

from __future__ import annotations

import time

from app.adapters.cache_store import InMemoryTTLCacheStore, NoopCacheStore


def test_in_memory_cache_hit_and_miss() -> None:
    cache = InMemoryTTLCacheStore(default_ttl_seconds=120)
    key = "k1"
    assert cache.get(key) is None

    cache.set(key, {"v": 1}, ttl_seconds=120)
    assert cache.get(key) == {"v": 1}


def test_in_memory_cache_expires_by_ttl() -> None:
    cache = InMemoryTTLCacheStore(default_ttl_seconds=1)
    cache.set("k", {"v": 1}, ttl_seconds=1)
    assert cache.get("k") == {"v": 1}

    time.sleep(1.1)
    assert cache.get("k") is None


def test_noop_cache_store_is_graceful_fallback() -> None:
    cache = NoopCacheStore()
    cache.set("k", {"v": 1}, ttl_seconds=120)
    assert cache.get("k") is None
