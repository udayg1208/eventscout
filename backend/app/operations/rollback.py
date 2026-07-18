"""Rollback engine (Phase 7B) — automatic, safe, non-destructive.

Rolls a provider back when a sync shows a hard failure signal: too many failures, a duplicate
explosion, zero new events, spam, or parser breakdown. Rollback **never deletes history** — the
registration is marked ROLLED_BACK, the provider is *disabled* in the Provider State Store (so it's
excluded from scheduling, reusing the store's own mechanism), and the reason is recorded. A rolled-
back provider can be re-evaluated later; nothing is destroyed.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from app.operations.production import CanaryMetrics
from app.operations.registry import ProductionRegistration, ProductionState
from app.storage.provider_state import ProviderStateStore


class RollbackReason(StrEnum):
    FAILURE_THRESHOLD = "failure_threshold"
    DUPLICATE_EXPLOSION = "duplicate_explosion"
    ZERO_EVENTS = "zero_events"
    SPAM_DETECTED = "spam_detected"
    PARSER_FAILURE = "parser_failure"


@dataclass(frozen=True)
class RollbackThresholds:
    max_failures: int = 2
    max_duplicate_rate: float = 0.7
    min_parse_quality: float = 0.3


DEFAULT_ROLLBACK_THRESHOLDS = RollbackThresholds()


@dataclass
class RollbackDecision:
    should_rollback: bool
    reasons: list[RollbackReason] = field(default_factory=list)
    detail: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "should_rollback": self.should_rollback,
            "reasons": [r.value for r in self.reasons],
            "detail": list(self.detail),
        }


def evaluate_rollback(
    m: CanaryMetrics,
    thresholds: RollbackThresholds = DEFAULT_ROLLBACK_THRESHOLDS,
    *,
    spam: bool = False,
) -> RollbackDecision:
    reasons: list[RollbackReason] = []
    detail: list[str] = []
    if m.failures > thresholds.max_failures:
        reasons.append(RollbackReason.FAILURE_THRESHOLD)
        detail.append(f"failures {m.failures} > {thresholds.max_failures}")
    if m.duplicate_rate > thresholds.max_duplicate_rate:
        reasons.append(RollbackReason.DUPLICATE_EXPLOSION)
        detail.append(f"duplicate_rate {m.duplicate_rate:.2f} > {thresholds.max_duplicate_rate}")
    if m.fetched > 0 and m.new_events == 0:
        reasons.append(RollbackReason.ZERO_EVENTS)
        detail.append("fetched but produced zero new events")
    if spam:
        reasons.append(RollbackReason.SPAM_DETECTED)
        detail.append("spam signal raised")
    if m.fetched > 0 and m.parse_quality < thresholds.min_parse_quality:
        reasons.append(RollbackReason.PARSER_FAILURE)
        detail.append(f"parse_quality {m.parse_quality:.2f} < {thresholds.min_parse_quality}")
    return RollbackDecision(should_rollback=bool(reasons), reasons=reasons, detail=detail)


class RollbackEngine:
    def __init__(
        self,
        state_store: ProviderStateStore,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._store = state_store
        self._clock = clock

    async def rollback(self, reg: ProductionRegistration, decision: RollbackDecision) -> dict:
        """Withdraw a provider non-destructively. Returns the rollback history entry."""
        now = self._clock()
        reason = ", ".join(r.value for r in decision.reasons) or "manual"
        reg.record(ProductionState.ROLLED_BACK, f"rollback: {reason}", now)
        # reuse the state store: disabling excludes it from scheduling, without deleting its record
        await self._store.disable_provider(reg.provider_id, at=now)
        return {
            "provider_id": reg.provider_id,
            "domain": reg.domain,
            "reasons": [r.value for r in decision.reasons],
            "detail": list(decision.detail),
            "at": now.isoformat(),
        }
