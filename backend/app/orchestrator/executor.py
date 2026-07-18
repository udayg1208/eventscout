"""Executor (Phase 9A) — runs one stage safely, exactly once at a time.

`LeaseManager` is the concurrency guard: a stage runs only while its caller holds a live, single
owner lease. A lease has a TTL and is kept alive by heartbeats; a lease whose TTL lapsed (owner
crashed) can be *stolen* by a new owner — that is how a crashed cycle recovers without a stuck lock.
`StageExecutor` acquires the lease, runs the stage runner under a timeout, and always releases — a
timeout or exception becomes a FAILED `StageOutcome`, never a hang. Local, in-process, and
deterministic; a distributed lease backend (Redis/DB) is a future seam (interfaces.py).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from app.orchestrator.models import (
    Lease,
    StageContext,
    StageHealth,
    StageName,
    StageOutcome,
    StageRunner,
)


class LeaseError(RuntimeError):
    """Raised when a stage lease cannot be acquired because a live one is held."""


class LeaseManager:
    def __init__(self, *, ttl_seconds: float = 30.0) -> None:
        self._ttl = ttl_seconds
        self._leases: dict[StageName, Lease] = {}

    def held(self, stage: StageName, now: datetime) -> bool:
        lease = self._leases.get(stage)
        return lease is not None and not lease.is_expired(now)

    def acquire(
        self, stage: StageName, owner: str, now: datetime, *, ttl_seconds: float | None = None
    ) -> Lease:
        existing = self._leases.get(stage)
        if existing is not None and not existing.is_expired(now) and existing.owner != owner:
            raise LeaseError(f"{stage.value} already leased by {existing.owner}")
        ttl = ttl_seconds if ttl_seconds is not None else self._ttl
        lease = Lease(
            stage=stage,
            owner=owner,
            acquired_at=now,
            expires_at=now + timedelta(seconds=ttl),
            heartbeat_at=now,
        )
        self._leases[stage] = lease  # a stale lease is silently stolen here
        return lease

    def heartbeat(self, lease: Lease, now: datetime, *, ttl_seconds: float | None = None) -> Lease:
        ttl = ttl_seconds if ttl_seconds is not None else self._ttl
        lease.heartbeat_at = now
        lease.expires_at = now + timedelta(seconds=ttl)
        return lease

    def release(self, lease: Lease) -> None:
        current = self._leases.get(lease.stage)
        if current is not None and current.owner == lease.owner:
            del self._leases[lease.stage]

    def reap_expired(self, now: datetime) -> list[StageName]:
        """Drop every lapsed lease (owners presumed dead); return the stages freed."""
        dead = [s for s, lease in self._leases.items() if lease.is_expired(now)]
        for s in dead:
            del self._leases[s]
        return dead


class StageExecutor:
    def __init__(
        self,
        leases: LeaseManager | None = None,
        *,
        owner: str = "orchestrator",
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._leases = leases or LeaseManager()
        self._owner = owner
        self._clock = clock

    @property
    def leases(self) -> LeaseManager:
        return self._leases

    async def execute(
        self,
        runner: StageRunner,
        ctx: StageContext,
        *,
        timeout_seconds: float = 30.0,
        monotonic: Callable[[], float] | None = None,
    ) -> tuple[StageOutcome, float]:
        """Run `runner(ctx)` under a lease + timeout. Returns (outcome, duration_seconds).

        Never raises for a stage failure: a timeout or exception is converted to a FAILED outcome so
        the loop can record it, back off, and continue.
        """
        now = self._clock()
        try:
            lease = self._leases.acquire(ctx.stage, self._owner, now, ttl_seconds=timeout_seconds)
        except LeaseError as exc:
            return StageOutcome(health=StageHealth.DEGRADED, error=str(exc)), 0.0

        clk = monotonic or time.monotonic
        start = clk()
        try:
            outcome = await asyncio.wait_for(runner(ctx), timeout=timeout_seconds)
        except TimeoutError:
            outcome = StageOutcome(
                health=StageHealth.FAILED, error=f"timeout after {timeout_seconds}s"
            )
        except Exception as exc:  # a stage runner blew up — capture, don't propagate
            outcome = StageOutcome(health=StageHealth.FAILED, error=f"{type(exc).__name__}: {exc}")
        finally:
            self._leases.heartbeat(lease, self._clock())
            self._leases.release(lease)
        duration = max(0.0, clk() - start)
        return outcome, duration


# a lightweight callable form some callers prefer when wiring adapters
StageCallable = Callable[[StageContext], Awaitable[StageOutcome]]
