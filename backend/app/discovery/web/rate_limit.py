"""Rate limiting + crawl budget (Phase 8B) — never hammer a provider or a domain.

`RateLimiter` enforces a minimum spacing between calls per key (per provider) using an injectable
clock + sleep, so it is deterministic in tests. `DomainGuard` enforces a per-domain minimum
interval so no single domain is queried back-to-back. `Budget` caps the number of queries a run may
execute. Together they bound outbound traffic.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime


async def _noop_sleep(_seconds: float) -> None:
    return None


class RateLimiter:
    def __init__(
        self,
        *,
        per_minute: float = 10.0,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Callable[[float], Awaitable[None]] = _noop_sleep,
    ) -> None:
        self._min_interval = 60.0 / per_minute if per_minute > 0 else 0.0
        self._clock = clock
        self._sleep = sleep
        self._last: dict[str, datetime] = {}
        self.waits = 0

    async def acquire(self, key: str = "global") -> float:
        """Wait (if needed) so calls for `key` are spaced ≥ min_interval. Returns seconds waited."""
        last = self._last.get(key)
        now = self._clock()
        waited = 0.0
        if last is not None:
            elapsed = (now - last).total_seconds()
            if elapsed < self._min_interval:
                waited = self._min_interval - elapsed
                self.waits += 1
                await self._sleep(waited)
        self._last[key] = self._clock()
        return round(waited, 4)


class DomainGuard:
    """Refuse (or space) repeat hits on the same domain within a window."""

    def __init__(
        self,
        *,
        min_interval_seconds: float = 1.0,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._min = min_interval_seconds
        self._clock = clock
        self._last: dict[str, datetime] = {}

    def allow(self, domain: str) -> bool:
        now = self._clock()
        last = self._last.get(domain)
        if last is not None and (now - last).total_seconds() < self._min:
            return False
        self._last[domain] = now
        return True


class Budget:
    """A hard cap on how many queries a run may execute (a crawl-budget ceiling)."""

    def __init__(self, max_queries: int) -> None:
        self.max_queries = max_queries
        self.spent = 0

    def consume(self) -> bool:
        if self.spent >= self.max_queries:
            return False
        self.spent += 1
        return True

    @property
    def remaining(self) -> int:
        return max(0, self.max_queries - self.spent)
