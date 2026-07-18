"""Per-provider rate limiting — a scheduler-side min-interval gate.

Enforced at *scheduling* time (not inside a worker) so workers never block: a provider
that ran too recently is simply not re-dispatched yet. The interval comes from the
plugin's declared `rate_limit_per_minute` — no hardcoded per-provider rule. Global and
per-provider *concurrency* are enforced separately (by the dispatcher's worker pool and
the engine's in-flight set).
"""

from __future__ import annotations

from datetime import datetime


class RateLimiter:
    """Tracks the last dispatch time per provider and answers "may this run now?"."""

    def __init__(self) -> None:
        self._last_dispatch: dict[str, datetime] = {}

    def allow(self, provider_id: str, *, now: datetime, min_interval_seconds: float) -> bool:
        """True if `provider_id` has not been dispatched within `min_interval_seconds`."""
        if min_interval_seconds <= 0:
            return True
        last = self._last_dispatch.get(provider_id)
        return last is None or (now - last).total_seconds() >= min_interval_seconds

    def record(self, provider_id: str, *, now: datetime) -> None:
        self._last_dispatch[provider_id] = now


def min_interval_seconds(rate_limit_per_minute: float) -> float:
    """Translate a declared per-minute rate into a minimum spacing between dispatches."""
    return 60.0 / rate_limit_per_minute if rate_limit_per_minute > 0 else 0.0
