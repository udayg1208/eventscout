"""Heartbeat + execution metrics for the ingestion engine.

`Heartbeat` is liveness (uptime, last tick, queue/running snapshot). `EngineMetrics`
accumulates execution outcomes and renders a live snapshot combining engine counters,
dispatcher state, and the provider-state fleet health. All time comes from an injected
clock so both are deterministic under test.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from app.scheduler.dispatcher import DispatcherStats
from app.scheduler.worker import WorkerResult
from app.storage.provider_state import HealthSummary

Clock = Callable[[], datetime]


@dataclass
class Heartbeat:
    """System liveness signal, refreshed every scheduler tick."""

    started_at: datetime
    last_tick_at: datetime | None = None
    tick_count: int = 0
    workers_alive: int = 0
    idle_workers: int = 0
    queue_depth: int = 0
    running_providers: int = 0

    def uptime_seconds(self, now: datetime) -> float:
        return (now - self.started_at).total_seconds()

    def snapshot(self, now: datetime) -> dict[str, object]:
        return {
            "uptime_seconds": round(self.uptime_seconds(now), 1),
            "tick_count": self.tick_count,
            "last_tick_at": self.last_tick_at.isoformat() if self.last_tick_at else None,
            "workers_alive": self.workers_alive,
            "idle_workers": self.idle_workers,
            "running_providers": self.running_providers,
            "queue_depth": self.queue_depth,
        }


@dataclass
class EngineMetrics:
    """Cumulative execution metrics."""

    clock: Clock
    started_at: datetime = field(init=False)
    providers_executed: int = 0
    successes: int = 0
    failures: int = 0
    retries: int = 0
    probes: int = 0
    events_ingested: int = 0
    duplicates: int = 0
    total_runtime_ms: float = 0.0

    def __post_init__(self) -> None:
        self.started_at = self.clock()

    def record_dispatch(self, *, is_retry: bool, is_probe: bool) -> None:
        if is_retry:
            self.retries += 1
        if is_probe:
            self.probes += 1

    def record_result(self, result: WorkerResult) -> None:
        self.providers_executed += 1
        self.total_runtime_ms += result.report.runtime_ms
        if result.ok:
            self.successes += 1
            self.events_ingested += result.report.accepted
            self.duplicates += result.report.duplicates
        else:
            self.failures += 1

    def snapshot(
        self, *, now: datetime, dispatcher: DispatcherStats, health: HealthSummary
    ) -> dict:
        executed = self.providers_executed
        elapsed_seconds = (now - self.started_at).total_seconds()

        def per_minute(count: int) -> float:
            # Report a rate only once there's a measurable window (>= 1s); otherwise the
            # near-zero divisor produces meaningless astronomically-large rates.
            return round(count / (elapsed_seconds / 60.0), 2) if elapsed_seconds >= 1.0 else 0.0

        return {
            "providers_executed": executed,
            "currently_running": dispatcher.running,
            "queue_depth": dispatcher.queue_depth,
            "idle_workers": dispatcher.idle,
            "workers": dispatcher.workers,
            "successes": self.successes,
            "failures": self.failures,
            "retries": self.retries,
            "probes": self.probes,
            "success_rate": round(self.successes / executed, 4) if executed else 0.0,
            "failure_rate": round(self.failures / executed, 4) if executed else 0.0,
            "avg_execution_ms": round(self.total_runtime_ms / executed, 1) if executed else 0.0,
            "throughput_per_min": per_minute(executed),
            "events_ingested": self.events_ingested,
            "events_per_min": per_minute(self.events_ingested),
            "provider_health": health.by_health,
        }
