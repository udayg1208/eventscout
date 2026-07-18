"""Growth Queue (Phase 10F) — the persistent backlog the planner draws from.

A priority queue of `GrowthTask`s with deduplication (one active task per kind+target), leases
(a leased task is invisible until its lease expires or completes), cooldown-based retries, and
abandonment at `max_attempts`. Pure in-memory logic driven by an integer `run` counter so it is
fully deterministic; persistence is delegated to a `GrowthStore`. Additive; no network.
"""

from __future__ import annotations

from app.growth.models import GrowthTask, TaskState


class GrowthQueue:
    def __init__(self, *, default_cooldown_runs: int = 1, default_lease_runs: int = 1) -> None:
        self._tasks: dict[str, GrowthTask] = {}  # dedup_key -> task
        self._cooldown_runs = default_cooldown_runs
        self._lease_runs = default_lease_runs

    # -- enqueue ------------------------------------------------------------

    def enqueue(self, task: GrowthTask, *, run: int = 0, force: bool = False) -> str:
        """Add a task. A key that already exists (active OR already completed) is treated as
        occupied — re-enqueue is a ``duplicate`` (active tasks keep the higher priority) so the
        opportunity/freshness engines can re-propose the same work idempotently without it
        re-running forever. Only ``force=True`` (the scheduler, gated by cadence) revives a
        completed key for a periodic re-run. An ABANDONED key may always be re-attempted."""
        existing = self._tasks.get(task.dedup_key)
        if existing is not None and existing.state is not TaskState.ABANDONED and not force:
            if existing.is_active() and task.priority > existing.priority:
                existing.priority = task.priority
                existing.reason = task.reason or existing.reason
            return "duplicate"
        task.created_run = run
        task.state = TaskState.QUEUED
        self._tasks[task.dedup_key] = task
        return "queued"

    def enqueue_all(self, tasks, *, run: int = 0) -> int:
        return sum(1 for t in tasks if self.enqueue(t, run=run) == "queued")

    # -- lease / selection --------------------------------------------------

    def eligible(self, run: int) -> list[GrowthTask]:
        """Tasks that may run now, highest priority first (ties: oldest first)."""
        out = [t for t in self._tasks.values() if t.eligible(run)]
        out.sort(key=lambda t: (-t.priority, t.created_run))
        return out

    def peek(self, run: int) -> GrowthTask | None:
        elig = self.eligible(run)
        return elig[0] if elig else None

    def lease(
        self, task: GrowthTask, run: int, *, owner: str = "growth", lease_runs: int | None = None
    ) -> GrowthTask:
        task.state = TaskState.LEASED
        task.lease_owner = owner
        task.lease_until = run + (lease_runs if lease_runs is not None else self._lease_runs)
        return task

    def acquire(self, run: int, *, owner: str = "growth") -> GrowthTask | None:
        """Peek the top eligible task and lease it in one step."""
        task = self.peek(run)
        if task is None:
            return None
        return self.lease(task, run, owner=owner)

    def reclaim_expired(self, run: int) -> int:
        """Return leased-but-expired tasks to QUEUED; returns how many were reclaimed."""
        n = 0
        for t in self._tasks.values():
            if t.state is TaskState.LEASED and run >= t.lease_until:
                t.state = TaskState.QUEUED
                t.lease_owner = ""
                n += 1
        return n

    # -- completion ---------------------------------------------------------

    def complete(
        self, task: GrowthTask, success: bool, run: int, *, cooldown_runs: int | None = None
    ) -> TaskState:
        """Mark a leased task done or (on failure) schedule a cooldown retry / abandon it."""
        if success:
            task.state = TaskState.DONE
            task.lease_owner = ""
            return task.state
        task.attempts += 1
        if task.attempts >= task.max_attempts:
            task.state = TaskState.ABANDONED
            task.lease_owner = ""
            return task.state
        cd = cooldown_runs if cooldown_runs is not None else self._cooldown_runs
        task.state = TaskState.COOLDOWN
        task.cooldown_until = run + max(1, cd)
        task.lease_owner = ""
        return task.state

    # -- introspection ------------------------------------------------------

    def get(self, dedup_key: str) -> GrowthTask | None:
        return self._tasks.get(dedup_key)

    def all(self) -> list[GrowthTask]:
        return list(self._tasks.values())

    def pending(self) -> list[GrowthTask]:
        return [t for t in self._tasks.values() if t.is_active()]

    def backlog(self) -> int:
        return len(self.pending())

    def leased(self) -> list[GrowthTask]:
        return [t for t in self._tasks.values() if t.state is TaskState.LEASED]

    def is_drained(self, run: int) -> bool:
        """No task can make progress now (queue empty of runnable work)."""
        return not self.eligible(run)

    def snapshot(self) -> list[dict]:
        return [t.as_dict() for t in sorted(self._tasks.values(), key=lambda t: -t.priority)]

    # -- persistence hydration ---------------------------------------------

    def load(self, tasks) -> None:
        for t in tasks:
            self._tasks[t.dedup_key] = t
