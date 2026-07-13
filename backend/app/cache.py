"""A minimal in-memory TTL cache.

Generic and dependency-free. The clock is injectable so expiration can be tested
deterministically without sleeping. A miss returns None; callers must check
`is not None` so that a legitimately-empty cached value (e.g. an empty results list)
is treated as a hit, not a miss.

Not thread-safe: intended for a single-process async server. Concurrency notes are
in the M4 review.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class TTLCache(Generic[K, V]):
    def __init__(
        self,
        ttl_seconds: float,
        time_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = ttl_seconds
        self._time = time_fn
        self._store: dict[K, tuple[float, V]] = {}  # key -> (expires_at, value)

    def get(self, key: K) -> V | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if self._time() >= expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: K, value: V) -> None:
        self._store[key] = (self._time() + self._ttl, value)
