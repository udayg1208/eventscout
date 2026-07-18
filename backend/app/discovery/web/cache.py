"""Search result cache (Phase 8B) — 24h TTL, normalized keys, invalidation, stats.

A query hit within the TTL is served from cache instead of re-calling the (rate-limited, possibly
paid) provider — this is both a cost control and the duplicate-suppression mechanism (the same
normalized query never calls out twice inside the window). Keyed by (provider, normalized query);
clock-injectable for deterministic tests.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.discovery.search import SearchResult

_WS = re.compile(r"\s+")


def normalize_query(query: str) -> str:
    """Case-fold + collapse whitespace so trivially-different queries share a cache entry."""
    return _WS.sub(" ", query.strip().casefold())


@dataclass
class _Entry:
    results: list[SearchResult]
    created_at: datetime


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return round(self.hits / total, 4) if total else 0.0


class SearchCache:
    def __init__(
        self,
        *,
        ttl_hours: float = 24.0,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._ttl = timedelta(hours=ttl_hours)
        self._clock = clock
        self._entries: dict[str, _Entry] = {}
        self.stats = CacheStats()

    @staticmethod
    def key(provider: str, query: str) -> str:
        return f"{provider}::{normalize_query(query)}"

    def get(self, provider: str, query: str) -> list[SearchResult] | None:
        entry = self._entries.get(self.key(provider, query))
        if entry is None or self._clock() - entry.created_at >= self._ttl:
            self.stats.misses += 1
            return None
        self.stats.hits += 1
        return list(entry.results)

    def put(self, provider: str, query: str, results: list[SearchResult]) -> None:
        self._entries[self.key(provider, query)] = _Entry(list(results), self._clock())

    def invalidate(self, *, provider: str | None = None, query: str | None = None) -> int:
        """Drop entries. No args → clear all; provider → all of a provider; +query → that one."""
        if provider is None and query is None:
            n = len(self._entries)
            self._entries.clear()
            return n
        if query is not None and provider is not None:
            return int(self._entries.pop(self.key(provider, query), None) is not None)
        prefix = f"{provider}::"
        drop = [k for k in self._entries if k.startswith(prefix)]
        for k in drop:
            del self._entries[k]
        return len(drop)

    def evict_expired(self) -> int:
        now = self._clock()
        drop = [k for k, e in self._entries.items() if now - e.created_at >= self._ttl]
        for k in drop:
            del self._entries[k]
        return len(drop)

    def size(self) -> int:
        return len(self._entries)
