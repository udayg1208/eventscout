"""Search cache — a storage-independent, invalidation-aware query cache.

Async and abstract so the in-memory implementation used today can be replaced by Redis
later with no change to callers. Keys are a deterministic canonical serialization of the
`SearchQuery`, so semantically-equal queries share a cache entry. Optional by design: a
`DatabaseSearchProvider` with `cache=None` simply always reads the repository.
"""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from collections.abc import Callable

from app.models.event import Event
from app.models.search import SearchQuery


def search_cache_key(query: SearchQuery) -> str:
    """A deterministic key: canonical JSON with list fields sorted, so equal queries collide."""
    data = query.model_dump(mode="json")
    data["keywords"] = sorted(data.get("keywords") or [])
    data["categories"] = sorted(data.get("categories") or [])
    return json.dumps(data, sort_keys=True, ensure_ascii=False)


class SearchCache(ABC):
    """Query -> results cache. A miss returns None (an empty list is a valid cached value)."""

    @abstractmethod
    async def get(self, key: str) -> list[Event] | None: ...

    @abstractmethod
    async def set(self, key: str, value: list[Event]) -> None: ...

    @abstractmethod
    async def invalidate(self, key: str) -> None:
        """Drop one entry (e.g. when the events behind that query changed)."""

    @abstractmethod
    async def clear(self) -> None:
        """Drop everything (e.g. after an ingestion run mutated the catalog)."""


class InMemorySearchCache(SearchCache):
    """Process-local TTL cache. Deterministic via an injectable clock. Redis is the
    drop-in replacement for a multi-instance deployment."""

    def __init__(
        self, ttl_seconds: float, *, time_fn: Callable[[], float] = time.monotonic
    ) -> None:
        self._ttl = ttl_seconds
        self._time = time_fn
        self._store: dict[str, tuple[float, list[Event]]] = {}

    async def get(self, key: str) -> list[Event] | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if self._time() >= expires_at:
            del self._store[key]
            return None
        return list(value)

    async def set(self, key: str, value: list[Event]) -> None:
        self._store[key] = (self._time() + self._ttl, list(value))

    async def invalidate(self, key: str) -> None:
        self._store.pop(key, None)

    async def clear(self) -> None:
        self._store.clear()

    def size(self) -> int:
        return len(self._store)
