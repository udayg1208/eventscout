"""Growth Engine (Phase 10F) — the continuous autonomous loop, one cycle at a time.

Each cycle: refill budgets → reclaim expired leases → let the scheduler enqueue due periodic work →
fold in freshness refreshes and detected opportunities → let the planner select the single best
affordable, unblocked task → run its step (a real-engine adapter) → charge the budget, complete the
task, enqueue follow-ups, touch freshness, record metrics, and feed the learning engine. `run()`
repeats cycles until a steady state (a window of no-growth cycles with a drained queue) or a cycle
cap. Everything is explainable and deterministic; no browser, no LLM, no network, and no automatic
provider/weight/query/catalog mutation — onboarding stays human-gated. Additive over every frozen
engine, which it only *drives* through the step seam.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.growth.budget import GrowthBudgetEngine
from app.growth.freshness import FreshnessEngine
from app.growth.learning import LearningEngine
from app.growth.metrics import GrowthMetricsEngine
from app.growth.models import (
    CycleRecord,
    EntityKind,
    GrowthReport,
    GrowthSnapshot,
    GrowthStep,
    StepContext,
    StepOutcome,
    TaskKind,
)
from app.growth.opportunity import OpportunityEngine, OpportunitySignals
from app.growth.planner import GrowthPlanner
from app.growth.queue import GrowthQueue
from app.growth.scheduler import GrowthScheduler
from app.growth.store import GrowthStore

# Which freshness entity a completed task of each kind refreshes.
_TOUCH_KIND: dict[TaskKind, EntityKind] = {
    TaskKind.EXPANSION: EntityKind.EXPANSION,
    TaskKind.ORGANIZER_REFRESH: EntityKind.ORGANIZER,
    TaskKind.VALIDATION: EntityKind.VALIDATION,
    TaskKind.ONBOARDING: EntityKind.PROVIDER,
    TaskKind.PRODUCTION_MONITOR: EntityKind.PROVIDER,
}


@dataclass
class GrowthInputs:
    """A per-cycle read of live state, supplied by the wiring (buffer/graph). Defaults are inert."""

    signals: OpportunitySignals = field(default_factory=OpportunitySignals)
    has_seed_backlog: bool = True
    has_onboarding_backlog: bool = True
    cities_known: set[str] = field(default_factory=set)
    cities_covered: set[str] = field(default_factory=set)


class GrowthEngine:
    def __init__(
        self,
        *,
        steps: dict[TaskKind, GrowthStep],
        scheduler: GrowthScheduler | None = None,
        planner: GrowthPlanner | None = None,
        queue: GrowthQueue | None = None,
        freshness: FreshnessEngine | None = None,
        opportunity: OpportunityEngine | None = None,
        budget: GrowthBudgetEngine | None = None,
        learning: LearningEngine | None = None,
        metrics: GrowthMetricsEngine | None = None,
        store: GrowthStore | None = None,
        inputs_provider: Callable[[], GrowthInputs] | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        owner: str = "growth",
    ) -> None:
        self._steps = steps
        self._clock = clock
        self.scheduler = scheduler or GrowthScheduler(clock=clock)
        self.planner = planner or GrowthPlanner()
        self.queue = queue or GrowthQueue()
        self.freshness = freshness or FreshnessEngine(clock=clock)
        self.opportunity = opportunity or OpportunityEngine()
        self.budget = budget or GrowthBudgetEngine(clock=clock)
        self.learning = learning or LearningEngine()
        self.metrics = metrics or GrowthMetricsEngine()
        self._store = store
        self._inputs = inputs_provider or (lambda: GrowthInputs())
        self._owner = owner
        self._run = 0

    # -- one cycle ----------------------------------------------------------

    async def run_cycle(self, *, now: datetime | None = None) -> CycleRecord:
        self._run += 1
        run = self._run
        now = now or self._clock()
        inputs = self._inputs()

        self.budget.refill_if_due(now=now)
        self.queue.reclaim_expired(run)
        self.scheduler.tick(self.queue, run=run, now=now)

        opportunities = self.opportunity.detect(inputs.signals)
        self.planner.refill_queue(
            self.queue,
            run=run,
            freshness_tasks=self.freshness.recommend_refreshes(now=now),
            opportunities=opportunities,
        )
        self.metrics.observe_cities(known=inputs.cities_known, covered=inputs.cities_covered)

        task, reason = self.planner.select(
            self.queue,
            self.budget,
            run,
            has_seed_backlog=inputs.has_seed_backlog,
            has_onboarding_backlog=inputs.has_onboarding_backlog,
        )

        if task is None:
            outcome = StepOutcome(success=True, notes="idle")
            self.metrics.record_cycle(outcome)
            record = CycleRecord(run, None, None, outcome.as_dict(), reason, now.isoformat())
            await self._persist(record)
            return record

        self.queue.lease(task, run, owner=self._owner)
        step = self._steps.get(task.kind)
        if step is None:
            outcome = StepOutcome(success=False, notes=f"no step for {task.kind.value}")
        else:
            ctx = StepContext(task=task, run=run, budget=self.budget.budget, now=now)
            outcome = await step(ctx)

        self.budget.charge(outcome.cost)
        self.queue.complete(task, outcome.success, run)
        self.queue.enqueue_all(outcome.follow_ups, run=run)
        self.freshness.touch(task.target, _TOUCH_KIND[task.kind], now=now)
        self.metrics.record_cycle(outcome)
        self.learning.observe(outcome)

        record = CycleRecord(
            run, task.kind.value, task.target, outcome.as_dict(), reason, now.isoformat()
        )
        await self._persist(record)
        return record

    # -- many cycles --------------------------------------------------------

    async def run(
        self,
        max_cycles: int = 50,
        *,
        until_steady: bool = True,
        steady_idle: int = 3,
        now: datetime | None = None,
    ) -> GrowthReport:
        """Run cycles until a steady state — ``steady_idle`` consecutive cycles where the planner
        found nothing to do (no growth, remaining tasks unselectable) — or ``max_cycles``.
        The idle streak, not queue drain, defines steady state: a perpetually-scheduled task with no
        backlog (e.g. validation waiting for seeds) is eligible but never selected, so it must not
        block termination."""
        report = GrowthReport()
        idle_streak = 0
        for _ in range(max_cycles):
            rec = await self.run_cycle(now=now)
            report.cycles += 1
            if rec.task_kind is None:
                report.idle_cycles += 1
                idle_streak += 1
            else:
                report.tasks_executed += 1
                report.by_kind[rec.task_kind] = report.by_kind.get(rec.task_kind, 0) + 1
                idle_streak = 0
            if until_steady and idle_streak >= steady_idle:
                report.reached_steady_state = True
                break
        return report

    # -- dashboard ----------------------------------------------------------

    def snapshot(self, *, now: datetime | None = None) -> GrowthSnapshot:
        now = now or self._clock()
        inputs = self._inputs()
        opportunities = self.opportunity.detect(inputs.signals)
        health = {
            "backlog": self.queue.backlog(),
            "leased": len(self.queue.leased()),
            "abandoned": sum(1 for t in self.queue.all() if t.state.value == "abandoned"),
        }
        return GrowthSnapshot(
            run=self._run,
            backlog=self.queue.backlog(),
            queue=self.queue.snapshot(),
            opportunities=[o.as_dict() for o in opportunities],
            budgets=self.budget.as_dict(),
            health=health,
            freshness=self.freshness.snapshot(now=now),
            recommendations=[r.as_dict() for r in self.learning.recommend()],
            metrics=self.metrics.snapshot().as_dict(),
        )

    def recommendations(self) -> list:
        return self.learning.recommend()

    def run_count(self) -> int:
        return self._run

    async def _persist(self, record: CycleRecord) -> None:
        if self._store is None:
            return
        await self._store.append_cycle(record)
        await self._store.save_queue(self.queue.all())
        await self._store.save_freshness(self.freshness.records())
