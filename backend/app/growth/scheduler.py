"""Growth Scheduler (Phase 10F) — decide which recurring activities are due.

Each `TaskKind` runs on a cadence (continuous / hourly / daily / weekly / manual). On each tick the
scheduler compares an injectable wall-clock against the last time each kind fired and enqueues the
due ones as `GrowthTask`s (targets supplied by a per-kind provider, so the scheduler stays
engine-agnostic). Deterministic given a fixed clock; no network. Reuses the cadence-interval pattern
without importing or modifying the frozen 9A scheduler.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.growth.models import (
    CADENCE_SECONDS,
    GrowthCadence,
    GrowthTask,
    TaskKind,
)
from app.growth.queue import GrowthQueue


@dataclass
class ScheduleSpec:
    kind: TaskKind
    cadence: GrowthCadence
    # produces the target(s) for this kind at fire time (e.g. organizer ids, or a single "batch")
    targets: Callable[[], list[str]] = field(default_factory=lambda: lambda: ["batch"])


# The default cadence policy for the five growth activities.
DEFAULT_SCHEDULE: dict[TaskKind, GrowthCadence] = {
    TaskKind.VALIDATION: GrowthCadence.HOURLY,
    TaskKind.PRODUCTION_MONITOR: GrowthCadence.HOURLY,
    TaskKind.ONBOARDING: GrowthCadence.HOURLY,
    TaskKind.EXPANSION: GrowthCadence.DAILY,
    TaskKind.ORGANIZER_REFRESH: GrowthCadence.WEEKLY,
}


class GrowthScheduler:
    def __init__(
        self,
        specs: list[ScheduleSpec] | None = None,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._specs = (
            specs
            if specs is not None
            else [ScheduleSpec(kind, cadence) for kind, cadence in DEFAULT_SCHEDULE.items()]
        )
        self._clock = clock
        self._last_fired: dict[TaskKind, datetime] = {}

    def is_due(self, kind: TaskKind, cadence: GrowthCadence, now: datetime) -> bool:
        interval = CADENCE_SECONDS[cadence]
        if interval is None:  # MANUAL — never auto-fires
            return False
        last = self._last_fired.get(kind)
        if last is None:
            return True  # first tick fires everything once
        return (now - last).total_seconds() >= interval

    def due(self, now: datetime | None = None) -> list[ScheduleSpec]:
        now = now or self._clock()
        return [s for s in self._specs if self.is_due(s.kind, s.cadence, now)]

    def tick(
        self, queue: GrowthQueue, *, run: int, now: datetime | None = None
    ) -> list[GrowthTask]:
        """Enqueue every due kind's tasks, record the fire time, and return what was enqueued.

        Uses ``force=True``: the cadence gate (``is_due``) already guarantees at most one fire per
        interval, so a periodic task whose previous run has completed is legitimately revived."""
        now = now or self._clock()
        enqueued: list[GrowthTask] = []
        for spec in self.due(now):
            for target in spec.targets():
                task = GrowthTask(
                    kind=spec.kind, target=target, reason=f"scheduled:{spec.cadence.value}"
                )
                if queue.enqueue(task, run=run, force=True) == "queued":
                    enqueued.append(task)
            self._last_fired[spec.kind] = now
        return enqueued

    def last_fired(self, kind: TaskKind) -> datetime | None:
        return self._last_fired.get(kind)
