"""Planner (Phase 9A) — decides which stage runs next, and with what budget.

Nothing is hardcoded: the planner reads the pipeline data + live state and picks the highest
*effective priority* eligible stage. Eligibility respects the trigger (schedule-due vs has-backlog),
pause, cooldown, dead-letter, and budget. Effective priority = base priority, lifted by backlog
pressure and starvation (long-overdue stages), lowered when a stage's budgets are running low or its
health is degraded. Budget grants shrink as the pool depletes — the control plane throttles itself
instead of blowing the ₹0 ceiling. Returns a `PlanDecision`, or `None` when nothing is eligible.
"""

from __future__ import annotations

import math
from datetime import datetime

from app.orchestrator.models import (
    BudgetKind,
    PlanDecision,
    StageContext,
    StageName,
    StageSpec,
    StageState,
    Trigger,
)
from app.orchestrator.pipeline import Pipeline
from app.orchestrator.scheduler import Scheduler


class Planner:
    def __init__(self, pipeline: Pipeline, *, scheduler: Scheduler | None = None) -> None:
        self._pipeline = pipeline
        self._scheduler = scheduler or Scheduler()

    # -- eligibility ---------------------------------------------------------

    def eligible(self, spec: StageSpec, state: StageState, now: datetime) -> bool:
        if not spec.enabled or self._scheduler.is_paused(spec, state):
            return False
        if self._scheduler.in_cooldown(state, now):
            return False
        if state.status.value == "dead_letter":
            return False
        schedule_due = self._scheduler.is_due(spec, state, now)
        backlog_due = state.backlog > 0
        if spec.trigger is Trigger.SCHEDULE:
            due = schedule_due
        elif spec.trigger is Trigger.BACKLOG:
            due = backlog_due
        else:
            due = schedule_due or backlog_due
        return due  # affordability is checked separately against the live budget pool

    def _affordable(self, spec: StageSpec, budget_remaining: dict[BudgetKind, int]) -> bool:
        return all(budget_remaining.get(k, 0) > 0 for k in spec.budgets)

    # -- scoring -------------------------------------------------------------

    def score(
        self,
        spec: StageSpec,
        state: StageState,
        now: datetime,
        *,
        budget_fraction: dict[BudgetKind, float],
    ) -> float:
        priority = spec.priority
        backlog_pressure = min(3.0, state.backlog * 0.5)
        starvation = 0.0
        if state.next_run is not None and now > state.next_run:
            overdue_s = (now - state.next_run).total_seconds()
            starvation = min(2.0, overdue_s / 3_600.0)  # up to +2 for very overdue
        # penalise expensive stages when their budgets are depleting
        budget_penalty = 0.0
        for kind in spec.budgets:
            frac = budget_fraction.get(kind, 1.0)
            if frac < 0.5:
                budget_penalty += (0.5 - frac) * 2.0  # up to +1 penalty per starved kind
        health_penalty = 1.5 if state.health.value == "degraded" else 0.0
        return priority + backlog_pressure + starvation - budget_penalty - health_penalty

    # -- budget grant --------------------------------------------------------

    def grant(
        self, spec: StageSpec, *, budget_fraction: dict[BudgetKind, float], remaining: dict
    ) -> dict[BudgetKind, int]:
        """Grant each requested budget kind, shrinking the ask as the pool depletes."""
        grant: dict[BudgetKind, int] = {}
        for kind, requested in spec.budgets.items():
            avail = remaining.get(kind, 0)
            frac = budget_fraction.get(kind, 1.0)
            ask = requested
            if frac < 0.25:  # pool nearly empty → throttle hard
                ask = max(1, math.ceil(requested * 0.5))
            grant[kind] = min(ask, avail)
        return grant

    # -- decision ------------------------------------------------------------

    def plan(self, state, now: datetime) -> PlanDecision | None:
        remaining = {k: state.budget.remaining(k) for k in BudgetKind}
        fraction = {k: state.budget.fraction_left(k) for k in BudgetKind}
        best: tuple[float, StageSpec] | None = None
        for spec in self._pipeline.enabled():
            st = state.stage(spec.name)
            if not self.eligible(spec, st, now):
                continue
            if not self._affordable(spec, remaining):
                continue
            s = self.score(spec, st, now, budget_fraction=fraction)
            if best is None or s > best[0]:
                best = (s, spec)
        if best is None:
            return None
        score, spec = best
        st = state.stage(spec.name)
        granted = self.grant(spec, budget_fraction=fraction, remaining=remaining)
        reason = self._reason(spec, st, now)
        ctx = StageContext(
            stage=spec.name,
            cycle=state.cycle,
            now=now,
            seeds=list(st.seeds),
            backlog=st.backlog,
            budgets=granted,
        )
        return PlanDecision(stage=spec.name, priority=round(score, 3), reason=reason, context=ctx)

    def _reason(self, spec: StageSpec, state: StageState, now: datetime) -> str:
        if state.status.value == "failed":
            return f"retry {state.retry_count}/{spec.schedule.retry_max} after failure"
        if state.backlog > 0 and spec.trigger is not Trigger.SCHEDULE:
            return f"backlog={state.backlog}"
        if state.last_run is None:
            return "first run"
        return f"scheduled ({spec.schedule.kind.value})"

    def recovery_stages(self, state) -> list[StageName]:
        """Stages left mid-flight (RUNNING) by a crash — to be replayed first on resume."""
        return [n for n, st in state.stages.items() if st.status.value == "running"]
