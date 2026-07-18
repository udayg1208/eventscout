"""Execution engine — decides what runs, when, how often, and how many at once.

    Scheduler (decide) -> Job Queue -> Dispatcher (run) -> Worker -> Ingestion Runner

Metadata- and state-driven; contains no provider-specific logic and touches none of the
frozen pipeline. The in-process dispatcher/queue swap for distributed backends behind the
same interfaces without changing scheduler logic.
"""

from app.scheduler.dispatcher import Dispatcher, DispatcherStats, InProcessDispatcher
from app.scheduler.engine import IngestionEngine
from app.scheduler.job import AsyncioJobQueue, Job, JobQueue
from app.scheduler.metrics import EngineMetrics, Heartbeat
from app.scheduler.ratelimit import RateLimiter
from app.scheduler.scheduler import RetryStrategy, Scheduler, execution_priority
from app.scheduler.worker import Worker, WorkerResult

__all__ = [
    "IngestionEngine",
    "Scheduler",
    "RetryStrategy",
    "execution_priority",
    "Worker",
    "WorkerResult",
    "Dispatcher",
    "InProcessDispatcher",
    "DispatcherStats",
    "JobQueue",
    "AsyncioJobQueue",
    "Job",
    "RateLimiter",
    "EngineMetrics",
    "Heartbeat",
]
