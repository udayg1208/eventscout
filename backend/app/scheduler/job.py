"""Job + Job Queue abstraction.

A `Job` is a unit of scheduled work (run one provider once). The `JobQueue` decouples the
scheduler (which produces jobs) from the dispatcher (which consumes them): the scheduler
calls the dispatcher, never the queue, so swapping the in-process `AsyncioJobQueue` for a
distributed queue (Redis/SQS/Kafka) later changes nothing upstream.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Job:
    """One scheduled execution of a provider."""

    provider_id: str
    enqueued_at: datetime
    is_probe: bool = False  # dispatched to probe an OPEN circuit (half-open trial)
    is_retry: bool = False  # provider had prior consecutive failures


class JobQueue(ABC):
    """Minimal queue contract the dispatcher depends on."""

    @abstractmethod
    async def put(self, job: Job) -> None: ...

    @abstractmethod
    async def get(self) -> Job: ...

    @abstractmethod
    def task_done(self) -> None: ...

    @abstractmethod
    async def join(self) -> None:
        """Block until every put job has been marked done."""

    @abstractmethod
    def qsize(self) -> int: ...


class AsyncioJobQueue(JobQueue):
    """In-process queue backed by ``asyncio.Queue``. The default today; a distributed
    backend implements the same interface tomorrow."""

    def __init__(self, maxsize: int = 0) -> None:
        self._queue: asyncio.Queue[Job] = asyncio.Queue(maxsize)

    async def put(self, job: Job) -> None:
        await self._queue.put(job)

    async def get(self) -> Job:
        return await self._queue.get()

    def task_done(self) -> None:
        self._queue.task_done()

    async def join(self) -> None:
        await self._queue.join()

    def qsize(self) -> int:
        return self._queue.qsize()
