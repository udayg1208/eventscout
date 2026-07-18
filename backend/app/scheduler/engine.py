"""Ingestion Engine — the production execution loop.

Wires the Scheduler (decide), Dispatcher (run), Worker (execute one provider via the
frozen runner), Rate limiter, Heartbeat, and Metrics into one system:

    bootstrap fleet -> [ heartbeat -> find due -> enqueue -> workers consume ->
    runner executes -> update provider state ] -> sleep to next tick -> repeat

Everything is driven by provider metadata + persisted state — no provider-specific logic.
Time is injected (a clock), so the loop is deterministic under test; it sleeps one tick
interval and wakes early on shutdown (never busy-waits). Provider state and checkpoints are
persisted by the runner on every job, so a restart resumes cleanly.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime

from app.ingestion.registry import ProviderRegistry
from app.scheduler.dispatcher import Dispatcher, InProcessDispatcher
from app.scheduler.job import Job
from app.scheduler.metrics import EngineMetrics, Heartbeat
from app.scheduler.ratelimit import RateLimiter
from app.scheduler.scheduler import DEFAULT_RETRY_STRATEGY, RetryStrategy, Scheduler
from app.scheduler.worker import Worker
from app.storage.provider_state import ProviderStateStore, new_provider_state
from app.storage.repository import EventRepository

logger = logging.getLogger("scheduler.engine")

Clock = Callable[[], datetime]


def _default_clock() -> datetime:
    return datetime.now(UTC)


class IngestionEngine:
    def __init__(
        self,
        registry: ProviderRegistry,
        repo: EventRepository,
        state_store: ProviderStateStore,
        *,
        concurrency: int = 4,
        tick_interval_seconds: float = 30.0,
        clock: Clock = _default_clock,
        retry_strategy: RetryStrategy = DEFAULT_RETRY_STRATEGY,
        dispatcher: Dispatcher | None = None,
    ) -> None:
        self._registry = registry
        self._repo = repo
        self._state = state_store
        self._clock = clock
        self._tick_interval = tick_interval_seconds

        self._rate = RateLimiter()
        self._scheduler = Scheduler(
            registry, state_store, rate_limiter=self._rate, retry_strategy=retry_strategy
        )
        self._worker = Worker(registry, repo, state_store, clock=clock)
        self._dispatcher = dispatcher or InProcessDispatcher(self._handle, concurrency=concurrency)

        self._metrics = EngineMetrics(clock=clock)
        self._heartbeat = Heartbeat(started_at=clock())
        self._inflight: set[str] = set()
        self._stopping = asyncio.Event()
        self._started = False

    # --- lifecycle ----------------------------------------------------------------

    async def bootstrap(self) -> int:
        """Seed a state row for every registered provider (idempotent). Without this a cold
        catalog would have no due providers. Preserves existing state on restart."""
        created = 0
        now = self._clock()
        for plugin in self._registry.all():
            if await self._state.get_provider_state(plugin.id) is None:
                await self._state.save_provider_state(
                    new_provider_state(
                        plugin.id,
                        at=now,
                        version=plugin.version,
                        capabilities=plugin.capability_record(),
                    )
                )
                created += 1
        logger.info("engine bootstrap providers=%d new=%d", len(self._registry.all()), created)
        return created

    async def start(self) -> None:
        if self._started:
            return
        await self.bootstrap()
        await self._dispatcher.start()
        self._started = True

    async def run_forever(self) -> None:
        """Production loop: tick, then sleep to the next tick (waking early on shutdown)."""
        await self.start()
        logger.info("engine loop started tick_interval=%.0fs", self._tick_interval)
        while not self._stopping.is_set():
            await self.tick()
            await self._sleep_until_next_tick()
        logger.info("engine loop exited")

    async def shutdown(self, *, graceful: bool = True) -> None:
        """Stop the loop and drain workers. In-flight runs finish (graceful); provider state
        and checkpoints are already persisted per job, so restart resumes cleanly."""
        self._stopping.set()
        await self._dispatcher.shutdown(graceful=graceful)
        self._started = False
        logger.info("engine shutdown complete graceful=%s", graceful)

    # --- one tick -----------------------------------------------------------------

    async def tick(self) -> int:
        """One scheduling pass: refresh heartbeat, enqueue due jobs. Returns jobs enqueued."""
        now = self._clock()
        jobs = await self._scheduler.due_jobs(now=now, exclude=set(self._inflight))
        for job in jobs:
            self._inflight.add(job.provider_id)
            self._rate.record(job.provider_id, now=now)
            self._metrics.record_dispatch(is_retry=job.is_retry, is_probe=job.is_probe)
            await self._dispatcher.submit(job)
        self._refresh_heartbeat(now, enqueued=len(jobs))
        logger.info(
            "scheduler tick enqueued=%d inflight=%d queue=%d",
            len(jobs),
            len(self._inflight),
            self._dispatcher.stats().queue_depth,
            extra={"enqueued": len(jobs), "queue": self._dispatcher.stats().queue_depth},
        )
        return len(jobs)

    async def run_cycle(self) -> int:
        """Tick and wait for the enqueued jobs to finish. For tests / one-shot cycles."""
        if not self._started:
            await self.start()
        enqueued = await self.tick()
        await self._dispatcher.drain()
        return enqueued

    async def _handle(self, job: Job) -> None:
        """Dispatcher handler: run one job, record metrics, always clear the in-flight mark."""
        try:
            result = await self._worker.run(job)
            self._metrics.record_result(result)
        finally:
            self._inflight.discard(job.provider_id)

    # --- helpers ------------------------------------------------------------------

    async def _sleep_until_next_tick(self) -> None:
        """Sleep one tick interval but wake immediately on shutdown (no busy-wait)."""
        try:
            await asyncio.wait_for(self._stopping.wait(), timeout=self._tick_interval)
        except TimeoutError:
            pass

    def _refresh_heartbeat(self, now: datetime, *, enqueued: int) -> None:
        stats = self._dispatcher.stats()
        self._heartbeat.last_tick_at = now
        self._heartbeat.tick_count += 1
        self._heartbeat.workers_alive = stats.workers
        self._heartbeat.idle_workers = stats.idle
        self._heartbeat.queue_depth = stats.queue_depth
        self._heartbeat.running_providers = len(self._inflight)

    # --- observability ------------------------------------------------------------

    def heartbeat(self) -> dict[str, object]:
        return self._heartbeat.snapshot(self._clock())

    async def metrics(self) -> dict:
        health = await self._state.provider_health_summary()
        return self._metrics.snapshot(
            now=self._clock(), dispatcher=self._dispatcher.stats(), health=health
        )
