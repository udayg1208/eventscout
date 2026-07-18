"""Budget Engine (Phase 10F) — allocate the four rate-limited resources, never exceed them.

Wraps a `GrowthBudget` (search / crawl / validation / onboarding) and refills it on a period
(default daily) using an injectable clock. Every allocation is clamped to what remains, so the loop
can never spend past a configured limit — the safety guarantee the autonomous scheduler needs to
stay within a ₹0 / free-tier envelope. Deterministic; no network.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from app.growth.models import GrowthBudget, GrowthResource

# Conservative per-period defaults for a free-tier envelope.
DEFAULT_LIMITS: dict[GrowthResource, int] = {
    GrowthResource.SEARCH: 100,
    GrowthResource.CRAWL: 200,
    GrowthResource.VALIDATION: 100,
    GrowthResource.ONBOARDING: 20,
}


class GrowthBudgetEngine:
    def __init__(
        self,
        limits: dict[GrowthResource, int] | None = None,
        *,
        refill_seconds: int = 86_400,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.budget = GrowthBudget(limits=dict(limits or DEFAULT_LIMITS))
        self._refill_seconds = refill_seconds
        self._clock = clock
        self._last_refill: datetime | None = None

    def can_afford(self, resource: GrowthResource, n: int = 1) -> bool:
        return self.budget.can_spend(resource, n)

    def remaining(self, resource: GrowthResource) -> int:
        return self.budget.remaining(resource)

    def allocate(self, resource: GrowthResource, n: int) -> int:
        """Grant up to `n` units, never past the limit. Returns what was actually granted."""
        return self.budget.spend(resource, n)

    def charge(self, cost: dict[GrowthResource, int]) -> dict[GrowthResource, int]:
        """Spend a step's reported cost across resources, clamped per resource."""
        return {r: self.budget.spend(r, n) for r, n in cost.items()}

    def refill_if_due(self, *, now: datetime | None = None) -> bool:
        """Reset consumption when a refill period has elapsed. Returns True if refilled."""
        now = now or self._clock()
        if self._last_refill is None:
            self._last_refill = now
            return False
        if (now - self._last_refill).total_seconds() >= self._refill_seconds:
            self.budget.reset()
            self._last_refill = now
            return True
        return False

    def as_dict(self) -> dict:
        return self.budget.as_dict()
