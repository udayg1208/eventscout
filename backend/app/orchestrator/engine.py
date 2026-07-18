"""Orchestrator engine (Phase 9A) — the continuous control loop.

Each cycle: **plan → execute one stage → apply outcome → update metrics → checkpoint → optimise →
sleep**. The planner picks the single highest-priority eligible stage; the executor runs it under a
lease + timeout; the state manager folds the outcome in, advances the schedule, and fans produced
seeds to downstream backlogs; a failed stage retries on backoff, dead-letters when out of tries.
`run(max_cycles=…)` bounds the loop for tests and demos — there is no unbounded loop in test code.
`resume_from_store()` restores the last checkpoint and replays any stage caught mid-run by a
crash. Deterministic: clock and sleeper are injected; the default sleeper only sleeps when the
configured interval is > 0.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from app.orchestrator.executor import LeaseManager, StageExecutor
from app.orchestrator.metrics import MetricsEngine
from app.orchestrator.models import (
    BudgetKind,
    CycleReport,
    OrchestratorReport,
    RunStatus,
    StageContext,
    StageHealth,
    StageName,
    StageOutcome,
    StageRunner,
)
from app.orchestrator.pipeline import Pipeline
from app.orchestrator.planner import Planner
from app.orchestrator.recovery import DeadLetterQueue, RecoveryManager
from app.orchestrator.scheduler import Scheduler
from app.orchestrator.state import StateManager
from app.orchestrator.store import OrchestratorStore


async def _default_sleeper(seconds: float) -> None:
    if seconds > 0:
        await asyncio.sleep(seconds)


async def _noop_runner(ctx: StageContext) -> StageOutcome:
    return StageOutcome(health=StageHealth.HEALTHY, note="no runner registered")


class OrchestratorEngine:
    def __init__(
        self,
        pipeline: Pipeline | None = None,
        runners: dict[StageName, StageRunner] | None = None,
        *,
        store: OrchestratorStore | None = None,
        budgets: dict[BudgetKind, int] | None = None,
        metrics: MetricsEngine | None = None,
        owner: str = "orchestrator",
        cycle_interval_seconds: float = 0.0,
        auto_tune: bool = False,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleeper: Callable[[float], Awaitable[None]] = _default_sleeper,
    ) -> None:
        self._pipeline = pipeline or Pipeline()
        self._runners: dict[StageName, StageRunner] = dict(runners or {})
        self._store = store
        self._clock = clock
        self._sleeper = sleeper
        self._interval = cycle_interval_seconds
        self._auto_tune = auto_tune
        self._scheduler = Scheduler()
        self._sm = StateManager(self._pipeline, scheduler=self._scheduler, budgets=budgets)
        self._planner = Planner(self._pipeline, scheduler=self._scheduler)
        self._executor = StageExecutor(LeaseManager(), owner=owner, clock=clock)
        self._recovery = RecoveryManager(self._pipeline)
        self._dlq = DeadLetterQueue(self._sm.state)
        self._metrics = metrics or MetricsEngine(clock=clock)

    # -- accessors -----------------------------------------------------------

    @property
    def state(self):
        return self._sm.state

    @property
    def metrics(self) -> MetricsEngine:
        return self._metrics

    @property
    def dead_letter(self) -> DeadLetterQueue:
        return self._dlq

    def register(self, stage: StageName, runner: StageRunner) -> None:
        self._runners[stage] = runner

    # -- controls ------------------------------------------------------------

    def seed(self, stage: StageName, seeds: list[str]) -> None:
        self._sm.enqueue_seeds(stage, seeds)

    def pause(self, stage: StageName) -> None:
        self._sm.state.stage(stage).paused = True

    def resume_stage(self, stage: StageName) -> None:
        self._sm.state.stage(stage).paused = False

    def stop(self) -> None:
        self._sm.stop()

    # -- recovery ------------------------------------------------------------

    async def resume_from_store(self) -> bool:
        """Restore the last persisted state and re-queue any stage interrupted mid-run."""
        if self._store is None:
            return False
        restored = await self._store.load_state()
        if restored is None:
            return False
        self._sm.restore(restored)
        self._dlq = DeadLetterQueue(self._sm.state)
        for stage in self._recovery.crash_replay_stages(self._sm.state):
            st = self._sm.state.stage(stage)
            st.status = RunStatus.PENDING  # replay: make it eligible again
            st.backlog = max(st.backlog, 1)
        return True

    # -- the loop ------------------------------------------------------------

    async def run_once(self) -> CycleReport:
        now = self._clock()
        cycle = self._sm.begin_cycle(now)
        self._metrics.observe_cycle()

        decision = self._planner.plan(self._sm.state, now)
        if decision is None:
            await self._persist(None, now)
            return CycleReport(cycle=cycle, stage=None, status=RunStatus.SKIPPED, reason="idle")

        stage = decision.stage
        spec = self._pipeline.spec(stage)
        self._sm.mark_running(stage)
        runner = self._runners.get(stage, _noop_runner)
        outcome, duration = await self._executor.execute(
            runner, decision.context, timeout_seconds=spec.timeout_seconds
        )
        self._sm.apply_outcome(stage, outcome, now=now, duration_s=duration)
        self._metrics.observe_stage(stage, outcome, duration)

        st = self._sm.state.stage(stage)
        status = st.status
        if status is RunStatus.FAILED and st.retry_count >= spec.schedule.retry_max:
            self._dlq.add(
                self._recovery.dead_letter_entry(
                    stage, cycle, st.retry_count, outcome.error or "failed", now
                )
            )
            self._sm.mark_dead_letter(stage)
            status = RunStatus.DEAD_LETTER

        if self._auto_tune:
            self._optimize()
        await self._persist(stage, now)
        return CycleReport(
            cycle=cycle,
            stage=stage,
            status=status,
            duration_s=duration,
            reason=decision.reason,
            outcome=outcome,
        )

    async def run(
        self, *, max_cycles: int | None = None, stop_when_idle: bool = False
    ) -> OrchestratorReport:
        """Run the loop. Bounded by `max_cycles` (required in tests) and/or `stop_when_idle`."""
        now = self._clock()
        self._sm.start(now)
        if self._metrics._start is None:
            self._metrics.start(now)
        report = OrchestratorReport()
        while self._sm.state.running:
            if max_cycles is not None and report.cycles >= max_cycles:
                break
            cr = await self.run_once()
            report.cycles += 1
            report.per_cycle.append(cr)
            if cr.stage is not None:
                report.stages_run[cr.stage.value] = report.stages_run.get(cr.stage.value, 0) + 1
            if cr.status is RunStatus.SKIPPED and stop_when_idle:
                break
            await self._sleeper(self._interval)
        self._sm.stop()
        report.metrics = self._metrics.snapshot(self._clock())
        report.dead_lettered = self._dlq.size()
        return report

    # -- helpers -------------------------------------------------------------

    async def _persist(self, stage: StageName | None, now: datetime) -> None:
        if self._store is None:
            return
        await self._store.save_state(self._sm.state)
        checkpoint = self._recovery.make_checkpoint(self._sm.state, stage, now)
        await self._store.save_checkpoint(checkpoint)

    def _optimize(self) -> None:
        """Bounded, reversible self-tuning: throttle a stage that is mostly finding duplicates,
        reward the discovery frontier when promotions flow. Recommend-only unless auto_tune."""
        snap = self._metrics.snapshot(self._clock())
        if snap.duplicate_rate > 0.5:
            spec = self._pipeline.spec(StageName.EXPANSION)
            spec.priority = max(1.0, spec.priority - 0.25)
        if snap.promotion_rate > 0.3:
            spec = self._pipeline.spec(StageName.SEARCH_DISCOVERY)
            spec.priority = min(10.0, spec.priority + 0.25)

    def optimize_recommendations(self) -> list[str]:
        """Non-mutating view of what auto-tune would do (matches 8A's recommend-only philosophy)."""
        snap = self._metrics.snapshot(self._clock())
        recs: list[str] = []
        if snap.duplicate_rate > 0.5:
            recs.append(f"throttle expansion (duplicate_rate={snap.duplicate_rate:.2f})")
        if snap.promotion_rate > 0.3:
            recs.append(f"boost search frontier (promotion_rate={snap.promotion_rate:.2f})")
        if snap.crawl_efficiency < 0.1 and snap.events_discovered:
            recs.append(f"low crawl efficiency ({snap.crawl_efficiency:.2f}) — tighten scope")
        return recs
