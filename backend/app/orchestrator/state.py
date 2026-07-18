"""State manager (Phase 9A) — the single writer of orchestrator state.

Owns every mutation of `OrchestratorState`: initialising per-stage state from the pipeline, marking
a stage running/finished, folding a `StageOutcome` into cumulative totals + budget consumption,
advancing the schedule (via the `Scheduler`), fanning produced seeds to downstream backlogs, and
tracking provider statistics. Keeping mutation in one place makes checkpoint/restore trivial and the
loop easy to reason about.
"""

from __future__ import annotations

from datetime import datetime

from app.orchestrator.models import (
    Budget,
    BudgetKind,
    BudgetPool,
    DeadLetterEntry,
    OrchestratorState,
    RunStatus,
    StageHealth,
    StageName,
    StageOutcome,
    StageState,
)
from app.orchestrator.pipeline import Pipeline
from app.orchestrator.scheduler import Scheduler


class StateManager:
    def __init__(
        self,
        pipeline: Pipeline,
        *,
        scheduler: Scheduler | None = None,
        budgets: dict[BudgetKind, int] | None = None,
    ) -> None:
        self._pipeline = pipeline
        self._scheduler = scheduler or Scheduler()
        self.state = OrchestratorState()
        for spec in pipeline.specs:
            self.state.stages[spec.name] = StageState(name=spec.name)
        if budgets:
            self.state.budget = BudgetPool({k: Budget(kind=k, limit=v) for k, v in budgets.items()})

    # -- lifecycle -----------------------------------------------------------

    def start(self, now: datetime) -> None:
        self.state.running = True
        self.state.started_at = self.state.started_at or now

    def stop(self) -> None:
        self.state.running = False

    def begin_cycle(self, now: datetime) -> int:
        self.state.cycle += 1
        self.state.last_cycle_at = now
        return self.state.cycle

    # -- stage transitions ---------------------------------------------------

    def mark_running(self, stage: StageName) -> None:
        st = self.state.stage(stage)
        st.status = RunStatus.RUNNING

    def apply_outcome(
        self,
        stage: StageName,
        outcome: StageOutcome,
        *,
        now: datetime,
        duration_s: float,
    ) -> None:
        spec = self._pipeline.spec(stage)
        st = self.state.stage(stage)
        st.runs += 1
        st.last_run = now
        st.last_duration_s = duration_s
        st.health = outcome.health
        st.total_discovered += outcome.discovered
        st.total_promoted += outcome.promoted
        st.total_rejected += outcome.rejected
        for kind, spent in outcome.budget_spent.items():
            self.state.budget.spend(kind, spent)
            st.budget_consumed[kind.value] = st.budget_consumed.get(kind.value, 0) + spent

        # this run drained the backlog it was granted
        st.backlog = max(0, st.backlog - 1) if spec.trigger.value != "schedule" else st.backlog
        st.seeds = []

        if outcome.ok():
            st.status = RunStatus.SUCCESS
            st.consecutive_failures = 0
            st.retry_count = 0
            st.errors = st.errors  # unchanged
            st.cooldown_until = self._scheduler.cooldown_until(spec, now)
            self._fan_out(stage, outcome, now=now)
        else:
            st.status = RunStatus.FAILED
            st.consecutive_failures += 1
            st.retry_count += 1
            if outcome.error:
                st.errors.append(outcome.error)
        st.next_run = self._scheduler.next_run_at(spec, st, now)
        self._refresh_provider_stats()

    def mark_dead_letter(self, stage: StageName) -> None:
        st = self.state.stage(stage)
        st.status = RunStatus.DEAD_LETTER

    # -- seed / backlog flow -------------------------------------------------

    def _fan_out(self, stage: StageName, outcome: StageOutcome, *, now: datetime) -> None:
        """Push produced seeds + a backlog tick to each downstream stage."""
        downstream = self._pipeline.downstream(stage)
        # what counts as "work produced" for the next stage
        produced = outcome.produced_seeds or (
            ["<candidate>"] * max(outcome.discovered, outcome.promoted)
            if (outcome.discovered or outcome.promoted)
            else []
        )
        if not produced:
            return
        for name in downstream:
            ds = self.state.stage(name)
            ds.backlog += 1
            if outcome.produced_seeds:
                ds.seeds = list({*ds.seeds, *outcome.produced_seeds})

    def enqueue_seeds(self, stage: StageName, seeds: list[str]) -> None:
        st = self.state.stage(stage)
        st.seeds = list({*st.seeds, *seeds})
        st.backlog += 1

    def has_backlog(self, stage: StageName) -> bool:
        return self.state.stage(stage).backlog > 0

    # -- provider stats ------------------------------------------------------

    def _refresh_provider_stats(self) -> None:
        promoted = sum(s.total_promoted for s in self.state.stages.values())
        rejected = sum(s.total_rejected for s in self.state.stages.values())
        discovered = sum(s.total_discovered for s in self.state.stages.values())
        self.state.provider_stats = {
            "discovered": discovered,
            "promoted": promoted,
            "rejected": rejected,
            "active": promoted,
        }

    # -- health rollup -------------------------------------------------------

    def overall_health(self) -> StageHealth:
        healths = [s.health for s in self.state.stages.values()]
        if any(h is StageHealth.FAILED for h in healths):
            return StageHealth.FAILED
        if any(h is StageHealth.DEGRADED for h in healths):
            return StageHealth.DEGRADED
        if healths and all(h is StageHealth.PAUSED for h in healths):
            return StageHealth.PAUSED
        return StageHealth.HEALTHY

    # -- checkpoint restore --------------------------------------------------

    def restore(self, state: OrchestratorState) -> None:
        self.state = state
        for spec in self._pipeline.specs:  # ensure every stage exists after restore
            self.state.stages.setdefault(spec.name, StageState(name=spec.name))


# --------------------------------------------------------------------------- serde


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def deserialize_state(data: dict) -> OrchestratorState:
    """Rebuild a typed `OrchestratorState` from its `as_dict()` form (checkpoint recovery)."""
    state = OrchestratorState(
        running=data.get("running", False),
        cycle=data.get("cycle", 0),
        started_at=_dt(data.get("started_at")),
        last_cycle_at=_dt(data.get("last_cycle_at")),
        provider_stats=dict(data.get("provider_stats", {})),
    )
    budgets = {}
    for kv in data.get("budget", {}).values():
        kind = BudgetKind(kv["kind"])
        budgets[kind] = Budget(kind=kind, limit=kv["limit"], consumed=kv["consumed"])
    state.budget = BudgetPool(budgets)

    for name_str, sd in data.get("stages", {}).items():
        name = StageName(name_str)
        state.stages[name] = StageState(
            name=name,
            status=RunStatus(sd["status"]),
            health=StageHealth(sd["health"]),
            last_run=_dt(sd.get("last_run")),
            next_run=_dt(sd.get("next_run")),
            last_duration_s=sd.get("last_duration_s", 0.0),
            runs=sd.get("runs", 0),
            consecutive_failures=sd.get("consecutive_failures", 0),
            retry_count=sd.get("retry_count", 0),
            cooldown_until=_dt(sd.get("cooldown_until")),
            paused=sd.get("paused", False),
            backlog=sd.get("backlog", 0),
            seeds=list(sd.get("seeds", [])),
            total_discovered=sd.get("total_discovered", 0),
            total_promoted=sd.get("total_promoted", 0),
            total_rejected=sd.get("total_rejected", 0),
            budget_consumed=dict(sd.get("budget_consumed", {})),
            errors=list(sd.get("errors", [])),
        )
    for d in data.get("dead_letter", []):
        state.dead_letter.append(
            DeadLetterEntry(
                stage=StageName(d["stage"]),
                cycle=d["cycle"],
                attempts=d["attempts"],
                error=d["error"],
                created_at=datetime.fromisoformat(d["created_at"]),
                context=d.get("context", {}),
            )
        )
    return state
