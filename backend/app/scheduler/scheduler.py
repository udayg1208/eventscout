"""Intelligent Scheduler — decides *what* runs and *in what order*, from metadata only.

The scheduler contains **no** provider-specific logic. It asks the Provider State Store
which providers are due (an indexed query — enabled and `next_run_at <= now`, honoring the
backoff/cooldown the store already computed), then filters and orders them purely from
declared plugin metadata + persisted state:

- **in-flight guard** → per-provider concurrency of 1 (never run a provider twice at once);
- **permanent-failure** → auto-disable a provider stuck failing (metadata-derived cap);
- **rate limit** → respect the declared per-minute spacing;
- **circuit** → a due provider whose circuit is OPEN is dispatched as a single half-open probe;
- **priority** → order by declared metadata (refresh cadence, expected volume).

It returns jobs; it never executes them (that's the dispatcher).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from app.ingestion.plugin import ProviderPlugin
from app.ingestion.registry import ProviderRegistry
from app.scheduler.job import Job
from app.scheduler.ratelimit import RateLimiter, min_interval_seconds
from app.storage.provider_state import CircuitState, ProviderState, ProviderStateStore

logger = logging.getLogger("scheduler.scheduler")


def execution_priority(plugin: ProviderPlugin) -> tuple[float, int]:
    """Ordering key (ascending = higher priority), derived only from declared metadata:
    fresher-cadence providers first, then higher expected volume. No provider identity."""
    return (plugin.refresh_interval_seconds, -plugin.expected_volume)


def is_probe(state: ProviderState | None) -> bool:
    """A due provider with an OPEN circuit is a half-open probe (a single trial run whose
    outcome closes or re-opens the circuit via the state store)."""
    return state is not None and state.circuit_state is CircuitState.OPEN


@dataclass(frozen=True)
class RetryStrategy:
    """Permanent-failure policy. `max_consecutive_failures` (None = never) is the point at
    which a provider is auto-disabled instead of endlessly probed. Backoff and circuit
    timing are NOT here — they already live in the Provider State Store's RetryPolicy."""

    max_consecutive_failures: int | None = None

    def is_permanent_failure(self, state: ProviderState | None) -> bool:
        return (
            self.max_consecutive_failures is not None
            and state is not None
            and state.consecutive_failures >= self.max_consecutive_failures
        )


# Shared immutable default so signatures don't call RetryStrategy() in their defaults.
DEFAULT_RETRY_STRATEGY = RetryStrategy()


class Scheduler:
    def __init__(
        self,
        registry: ProviderRegistry,
        state_store: ProviderStateStore,
        *,
        rate_limiter: RateLimiter,
        retry_strategy: RetryStrategy = DEFAULT_RETRY_STRATEGY,
    ) -> None:
        self._registry = registry
        self._state = state_store
        self._rate = rate_limiter
        self._retry = retry_strategy

    async def due_jobs(self, *, now: datetime, exclude: set[str]) -> list[Job]:
        """Return the jobs to enqueue this tick, priority-ordered. `exclude` is the set of
        currently in-flight providers (per-provider concurrency)."""
        due_ids = await self._state.due_providers(now)
        jobs: list[Job] = []
        for provider_id in due_ids:
            if provider_id in exclude:
                continue  # already running — enforce per-provider concurrency = 1
            plugin = self._registry.get(provider_id)
            if plugin is None:
                continue  # registry is the source of truth; drop stale state rows

            state = await self._state.get_provider_state(provider_id)
            if self._retry.is_permanent_failure(state):
                await self._state.disable_provider(provider_id, at=now)
                logger.warning(
                    "provider auto-disabled (permanent failure) provider=%s failures=%d",
                    provider_id,
                    state.consecutive_failures if state else 0,
                    extra={"provider": provider_id, "result": "disabled"},
                )
                continue

            interval = min_interval_seconds(plugin.rate_limit_per_minute)
            if not self._rate.allow(provider_id, now=now, min_interval_seconds=interval):
                continue  # rate-limited — try again a later tick

            jobs.append(
                Job(
                    provider_id=provider_id,
                    enqueued_at=now,
                    is_probe=is_probe(state),
                    is_retry=bool(state and state.consecutive_failures > 0),
                )
            )

        jobs.sort(key=lambda job: execution_priority(self._registry.get(job.provider_id)))
        return jobs
