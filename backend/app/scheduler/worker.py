"""Worker — executes exactly one provider through the existing Ingestion Runner.

A worker's whole job is: resolve the plugin, run the (frozen) ingestion runner, and emit
a structured log + result. Timeout, fetch-retry, and provider-state updates already live
inside `run_ingestion`, so the worker delegates to it rather than duplicating them. It
adds nothing to the pipeline — only the execution envelope (logging, a typed result).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from app.ingestion.registry import ProviderRegistry
from app.ingestion.runner import IngestionReport, run_ingestion
from app.scheduler.job import Job
from app.storage.provider_state import ProviderStateStore
from app.storage.repository import EventRepository

logger = logging.getLogger("scheduler.worker")

Clock = Callable[[], datetime]


@dataclass(frozen=True)
class WorkerResult:
    job: Job
    report: IngestionReport

    @property
    def ok(self) -> bool:
        return self.report.ok


class Worker:
    """Runs one job via the frozen ingestion runner."""

    def __init__(
        self,
        registry: ProviderRegistry,
        repo: EventRepository,
        state_store: ProviderStateStore,
        *,
        clock: Clock,
    ) -> None:
        self._registry = registry
        self._repo = repo
        self._state = state_store
        self._clock = clock

    async def run(self, job: Job) -> WorkerResult:
        plugin = self._registry.get(job.provider_id)
        if plugin is None:  # registry is the source of truth; a stale job is dropped
            raise KeyError(f"unknown provider '{job.provider_id}'")

        report = await run_ingestion(plugin, self._repo, self._state, now=self._clock())

        logger.info(
            "worker executed provider=%s result=%s events=%d duplicates=%d rejected=%d "
            "duration_ms=%.1f probe=%s retry=%s errors=%d",
            plugin.id,
            "ok" if report.ok else "failed",
            report.accepted,
            report.duplicates,
            report.rejected,
            report.runtime_ms,
            job.is_probe,
            job.is_retry,
            len(report.errors),
            extra={
                "provider": plugin.id,
                "result": "ok" if report.ok else "failed",
                "events": report.accepted,
                "duration_ms": report.runtime_ms,
                "probe": job.is_probe,
                "retry": job.is_retry,
                "errors": len(report.errors),
            },
        )
        return WorkerResult(job=job, report=report)
