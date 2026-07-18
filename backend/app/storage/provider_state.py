"""Provider State Store — the persistent memory of every provider.

A sibling storage port to `EventRepository` (same storage-agnostic discipline; SQLite is
the first backend, Postgres later). It holds one durable record per provider — identity,
declared capabilities, enable/health/circuit state, sync checkpoint + cursor, and rolling
run statistics — so the future Scheduler, Worker, Retry Engine, and Analytics read and
advance provider state without knowing anything about the backend.

Forward-compatible by design: `capabilities` and `extra` are open JSON maps, so new
fields those future components need require **no schema change**.

The state-transition rules (`apply_success` / `apply_failure`) are pure functions here so
they are unit-testable in isolation; the backend runs them inside a single locked
read-modify-write, which is what makes concurrent updates safe.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from enum import StrEnum


class CircuitState(StrEnum):
    """Circuit-breaker position for a provider."""

    CLOSED = "closed"  # healthy — runs normally
    OPEN = "open"  # too many failures — backing off (gated by next_run_at)
    HALF_OPEN = "half_open"  # probing after cooldown (set by the scheduler in 3D)


class HealthStatus(StrEnum):
    """Derived health signal for dashboards and source-quality weighting."""

    UNKNOWN = "unknown"  # never run
    HEALTHY = "healthy"  # last run succeeded
    DEGRADED = "degraded"  # some consecutive failures, circuit still closed
    FAILING = "failing"  # circuit open


@dataclass(frozen=True)
class RetryPolicy:
    """Transition knobs. Supplied by the caller (from provider metadata in 3C/3D) so no
    per-provider behavior is ever hardcoded in the store. Deterministic (no jitter here;
    the scheduler adds jitter in 3D)."""

    failure_threshold: int = 5  # consecutive failures that open the circuit
    base_backoff_seconds: float = 60.0
    max_backoff_seconds: float = 3600.0
    circuit_cooldown_seconds: float = 1800.0  # min wait once the circuit opens
    refresh_interval_seconds: float = 3600.0  # next run after a success


# Shared immutable default so signatures don't call RetryPolicy() in their defaults.
DEFAULT_RETRY_POLICY = RetryPolicy()


@dataclass(frozen=True)
class ProviderState:
    """The full persisted state of one provider (a point-in-time snapshot)."""

    provider_id: str
    provider_version: int = 1
    capabilities: dict = field(default_factory=dict)
    enabled: bool = True
    health_status: HealthStatus = HealthStatus.UNKNOWN
    circuit_state: CircuitState = CircuitState.CLOSED
    last_success_at: datetime | None = None  # last successful sync
    last_attempt_at: datetime | None = None  # last attempted sync
    next_run_at: datetime | None = None  # next scheduled run (None = due now)
    consecutive_failures: int = 0
    total_runs: int = 0
    total_successes: int = 0
    total_failures: int = 0
    avg_execution_ms: float = 0.0
    avg_events: float = 0.0
    checkpoint: str | None = None  # last content hash / checkpoint
    cursor: str | None = None  # incremental sync cursor
    retry_count: int = 0
    last_error: str | None = None
    last_error_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    extra: dict = field(default_factory=dict)  # forward-compat escape hatch


@dataclass(frozen=True)
class HealthSummary:
    """Fleet-wide health rollup for analytics / the provider dashboard."""

    total: int
    enabled: int
    disabled: int
    by_health: dict[str, int]
    by_circuit: dict[str, int]
    total_runs: int
    total_successes: int
    total_failures: int
    success_rate: float
    avg_execution_ms: float


# --------------------------- pure state transitions ---------------------------


def new_provider_state(
    provider_id: str,
    *,
    at: datetime,
    version: int = 1,
    capabilities: dict | None = None,
) -> ProviderState:
    """A fresh, never-run provider record."""
    return ProviderState(
        provider_id=provider_id,
        provider_version=version,
        capabilities=capabilities or {},
        created_at=at,
        updated_at=at,
    )


def _incremental_mean(old_mean: float, value: float, count: int) -> float:
    """Running mean without keeping the full history (count includes `value`)."""
    return old_mean + (value - old_mean) / count


def _backoff_seconds(retry_count: int, policy: RetryPolicy) -> float:
    seconds = policy.base_backoff_seconds * (2 ** max(0, retry_count - 1))
    return min(seconds, policy.max_backoff_seconds)


def apply_success(
    state: ProviderState,
    *,
    at: datetime,
    execution_ms: float,
    events_discovered: int,
    checkpoint: str | None = None,
    cursor: str | None = None,
    policy: RetryPolicy = DEFAULT_RETRY_POLICY,
) -> ProviderState:
    """State after a successful run: advance stats, clear failure/circuit, schedule next."""
    total_runs = state.total_runs + 1
    total_successes = state.total_successes + 1
    return replace(
        state,
        last_attempt_at=at,
        last_success_at=at,
        consecutive_failures=0,
        retry_count=0,
        circuit_state=CircuitState.CLOSED,
        health_status=HealthStatus.HEALTHY,
        total_runs=total_runs,
        total_successes=total_successes,
        avg_execution_ms=_incremental_mean(state.avg_execution_ms, execution_ms, total_runs),
        avg_events=_incremental_mean(state.avg_events, events_discovered, total_successes),
        checkpoint=checkpoint if checkpoint is not None else state.checkpoint,
        cursor=cursor if cursor is not None else state.cursor,
        next_run_at=at + timedelta(seconds=policy.refresh_interval_seconds),
        updated_at=at,
    )


def apply_failure(
    state: ProviderState,
    *,
    at: datetime,
    error: str,
    execution_ms: float = 0.0,
    policy: RetryPolicy = DEFAULT_RETRY_POLICY,
) -> ProviderState:
    """State after a failed run: count it, back off, open the circuit at the threshold.
    `last_error`/`last_error_at` are historical (kept across later successes)."""
    total_runs = state.total_runs + 1
    total_failures = state.total_failures + 1
    consecutive = state.consecutive_failures + 1
    retry_count = state.retry_count + 1
    avg_execution_ms = (
        _incremental_mean(state.avg_execution_ms, execution_ms, total_runs)
        if execution_ms
        else state.avg_execution_ms
    )
    opened = consecutive >= policy.failure_threshold
    circuit = CircuitState.OPEN if opened else state.circuit_state
    backoff = _backoff_seconds(retry_count, policy)
    if circuit is CircuitState.OPEN:
        backoff = max(backoff, policy.circuit_cooldown_seconds)
    return replace(
        state,
        last_attempt_at=at,
        consecutive_failures=consecutive,
        retry_count=retry_count,
        total_runs=total_runs,
        total_failures=total_failures,
        avg_execution_ms=avg_execution_ms,
        circuit_state=circuit,
        health_status=HealthStatus.FAILING
        if circuit is CircuitState.OPEN
        else HealthStatus.DEGRADED,
        last_error=error,
        last_error_at=at,
        next_run_at=at + timedelta(seconds=backoff),
        updated_at=at,
    )


# --------------------------- the port ---------------------------


class ProviderStateStore(ABC):
    """Storage-agnostic persistent memory of every provider."""

    @abstractmethod
    async def get_provider_state(self, provider_id: str) -> ProviderState | None:
        """Return a provider's state, or None if never seen."""

    @abstractmethod
    async def save_provider_state(self, state: ProviderState) -> None:
        """Create or replace a provider's full state (e.g. registration)."""

    @abstractmethod
    async def update_after_run(
        self,
        provider_id: str,
        *,
        at: datetime,
        execution_ms: float,
        events_discovered: int,
        checkpoint: str | None = None,
        cursor: str | None = None,
        policy: RetryPolicy = DEFAULT_RETRY_POLICY,
    ) -> ProviderState:
        """Atomically record a successful run and return the new state."""

    @abstractmethod
    async def update_after_failure(
        self,
        provider_id: str,
        *,
        at: datetime,
        error: str,
        execution_ms: float = 0.0,
        policy: RetryPolicy = DEFAULT_RETRY_POLICY,
    ) -> ProviderState:
        """Atomically record a failed run and return the new state."""

    @abstractmethod
    async def due_providers(self, now: datetime, *, limit: int | None = None) -> list[str]:
        """Enabled providers whose `next_run_at` is due (or never scheduled), soonest
        first (never-run first). The circuit is honored implicitly: an open circuit pushes
        `next_run_at` out by the cooldown, so it simply isn't due until then."""

    @abstractmethod
    async def reset_circuit(self, provider_id: str, *, at: datetime | None = None) -> None:
        """Force the circuit closed and clear the failure streak (operator action)."""

    @abstractmethod
    async def enable_provider(self, provider_id: str, *, at: datetime | None = None) -> None:
        """Enable a provider (it becomes eligible for scheduling)."""

    @abstractmethod
    async def disable_provider(self, provider_id: str, *, at: datetime | None = None) -> None:
        """Disable a provider (excluded from `due_providers`)."""

    @abstractmethod
    async def provider_health_summary(self) -> HealthSummary:
        """Fleet-wide health rollup for analytics / the dashboard."""

    @abstractmethod
    async def close(self) -> None:
        """Release backend resources."""
