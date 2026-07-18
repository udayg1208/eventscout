"""Dispatcher — separates *deciding* to run work from *running* it.

The scheduler submits jobs; the dispatcher runs them through a pool of workers. Today the
pool is in-process asyncio tasks bounded by a global concurrency limit. Because the
scheduler only ever calls `submit()`/`drain()`/`shutdown()`, the execution mechanism can
be swapped for Redis/Celery/RabbitMQ/SQS/Kafka later without changing scheduler logic.

Failure isolation: a handler exception is logged and contained — one bad job never kills a
worker loop or the pool.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.scheduler.job import AsyncioJobQueue, Job, JobQueue

logger = logging.getLogger("scheduler.dispatcher")

JobHandler = Callable[[Job], Awaitable[None]]


@dataclass(frozen=True)
class DispatcherStats:
    workers: int
    running: int  # handlers currently executing
    idle: int  # workers blocked waiting for a job
    queue_depth: int


class Dispatcher(ABC):
    """Runs submitted jobs. The scheduler depends only on this surface."""

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def submit(self, job: Job) -> None: ...

    @abstractmethod
    async def drain(self) -> None:
        """Block until all submitted jobs have finished."""

    @abstractmethod
    async def shutdown(self, *, graceful: bool = True) -> None: ...

    @abstractmethod
    def stats(self) -> DispatcherStats: ...


class InProcessDispatcher(Dispatcher):
    """A fixed pool of asyncio worker loops. `concurrency` is the global concurrency
    limit — at most that many handlers run at once."""

    def __init__(
        self, handler: JobHandler, *, concurrency: int, queue: JobQueue | None = None
    ) -> None:
        self._handler = handler
        self._concurrency = max(1, concurrency)
        self._queue = queue or AsyncioJobQueue()
        self._loops: list[asyncio.Task] = []
        self._running = False
        self._active = 0

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._loops = [asyncio.create_task(self._loop(i)) for i in range(self._concurrency)]
        logger.info(
            "dispatcher started workers=%d", self._concurrency, extra={"workers": self._concurrency}
        )

    async def _loop(self, worker_id: int) -> None:
        while True:
            job = await self._queue.get()  # cancelled on shutdown while idle here
            self._active += 1
            try:
                await self._handler(job)
            except Exception:  # noqa: BLE001 - isolate: one job must not kill the pool
                logger.exception("dispatcher handler failed job=%s", job.provider_id)
            finally:
                self._active -= 1
                self._queue.task_done()

    async def submit(self, job: Job) -> None:
        await self._queue.put(job)

    async def drain(self) -> None:
        await self._queue.join()

    async def shutdown(self, *, graceful: bool = True) -> None:
        if graceful:
            await self._queue.join()  # let queued + in-flight jobs finish
        self._running = False
        for loop in self._loops:
            loop.cancel()
        await asyncio.gather(*self._loops, return_exceptions=True)
        self._loops = []
        logger.info("dispatcher shut down graceful=%s", graceful, extra={"graceful": graceful})

    def stats(self) -> DispatcherStats:
        workers = len(self._loops)
        return DispatcherStats(
            workers=workers,
            running=self._active,
            idle=max(0, workers - self._active),
            queue_depth=self._queue.qsize(),
        )
