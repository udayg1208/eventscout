"""Provider health tracking (Phase 7B) — reuses the Provider State Store (3B).

Every canary/continuous sync is recorded through the existing `ProviderStateStore`
(`update_after_run` / `update_after_failure` — the store's own locked, pure state transitions), so
uptime, failure streaks, circuit state, and rolling averages come from the same battle-tested code
the ingestion runner uses. Operations-specific signals the ProviderState schema doesn't carry
(parse quality, duplicate %, freshness, success trend) are tracked alongside and rolled into a
`HealthSnapshot`. Additive: the store is used as designed; nothing in `app/storage/` changes.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from app.operations.production import CanaryMetrics
from app.operations.registry import ProductionRegistration
from app.storage.provider_state import (
    DEFAULT_RETRY_POLICY,
    ProviderState,
    ProviderStateStore,
    RetryPolicy,
    new_provider_state,
)


@dataclass
class HealthSnapshot:
    provider_id: str
    health_status: str
    circuit_state: str
    uptime: float  # successes / runs
    latency_ms: float
    freshness_hours: float | None  # since last success (None = never succeeded)
    event_quality: float  # mean canary/sync parse quality
    duplicate_pct: float  # mean duplicate rate
    failures: int
    retries: int
    success_trend: str  # up | down | flat
    total_runs: int
    total_successes: int

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def _trend(samples: list[int]) -> str:
    if len(samples) < 2:
        return "flat"
    first, second = samples[: len(samples) // 2], samples[len(samples) // 2 :]
    a = sum(first) / len(first)
    b = sum(second) / len(second)
    if b > a + 1e-9:
        return "up"
    if b < a - 1e-9:
        return "down"
    return "flat"


class HealthTracker:
    def __init__(
        self,
        state_store: ProviderStateStore,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._store = state_store
        self._clock = clock
        self._ops: dict[str, dict] = {}  # provider_id → {quality[], dup[], trend[]}

    async def initialize(self, reg: ProductionRegistration) -> None:
        now = self._clock()
        await self._store.save_provider_state(
            new_provider_state(reg.provider_id, at=now, capabilities={"types": reg.capabilities})
        )
        self._ops[reg.provider_id] = {"quality": [], "dup": [], "trend": []}

    async def record_sync(
        self,
        provider_id: str,
        metrics: CanaryMetrics,
        *,
        policy: RetryPolicy = DEFAULT_RETRY_POLICY,
    ) -> ProviderState:
        now = self._clock()
        healthy_sync = metrics.fetch_success and metrics.failures == 0
        if healthy_sync:
            state = await self._store.update_after_run(
                provider_id,
                at=now,
                execution_ms=metrics.latency_ms,
                events_discovered=metrics.new_events,
                policy=policy,
            )
        else:
            state = await self._store.update_after_failure(
                provider_id,
                at=now,
                error="sync failure",
                execution_ms=metrics.latency_ms,
                policy=policy,
            )
        ops = self._ops.setdefault(provider_id, {"quality": [], "dup": [], "trend": []})
        ops["quality"].append(metrics.parse_quality)
        ops["dup"].append(metrics.duplicate_rate)
        ops["trend"].append(1 if healthy_sync else 0)
        return state

    async def snapshot(self, provider_id: str) -> HealthSnapshot | None:
        state = await self._store.get_provider_state(provider_id)
        if state is None:
            return None
        ops = self._ops.get(provider_id, {"quality": [], "dup": [], "trend": []})
        uptime = state.total_successes / state.total_runs if state.total_runs else 0.0
        freshness = None
        if state.last_success_at is not None:
            freshness = round((self._clock() - state.last_success_at).total_seconds() / 3600.0, 3)
        quality = round(sum(ops["quality"]) / len(ops["quality"]), 4) if ops["quality"] else 0.0
        dup = round(sum(ops["dup"]) / len(ops["dup"]), 4) if ops["dup"] else 0.0
        return HealthSnapshot(
            provider_id=provider_id,
            health_status=state.health_status.value,
            circuit_state=state.circuit_state.value,
            uptime=round(uptime, 4),
            latency_ms=round(state.avg_execution_ms, 2),
            freshness_hours=freshness,
            event_quality=quality,
            duplicate_pct=dup,
            failures=state.total_failures,
            retries=state.retry_count,
            success_trend=_trend(ops["trend"]),
            total_runs=state.total_runs,
            total_successes=state.total_successes,
        )
