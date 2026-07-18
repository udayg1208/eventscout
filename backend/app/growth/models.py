"""Growth control-plane types (Phase 10F) — the data the autonomous loop reasons over.

The Growth Scheduler is engine-agnostic: it drives the existing growth pipeline (10C organizers →
10D expansion → 10E validation → the Discovery Inbox → 7A onboarding → 7B production) through one
uniform `GrowthStep` seam (`StepContext` in → `StepOutcome` out). Concrete adapters that call the
real engines live in steps.py; nothing here imports them, so the loop stays testable with mocks and
additive to every frozen system. No browser, no LLM, no network.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class TaskKind(StrEnum):
    """The five recurring growth activities the scheduler drives."""

    ORGANIZER_REFRESH = "organizer_refresh"
    EXPANSION = "expansion"
    VALIDATION = "validation"
    ONBOARDING = "onboarding"
    PRODUCTION_MONITOR = "production_monitor"


class TaskState(StrEnum):
    QUEUED = "queued"
    LEASED = "leased"
    DONE = "done"
    FAILED = "failed"
    COOLDOWN = "cooldown"
    ABANDONED = "abandoned"


class GrowthCadence(StrEnum):
    CONTINUOUS = "continuous"  # eligible every cycle
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MANUAL = "manual"  # only when explicitly enqueued


class GrowthResource(StrEnum):
    """Rate-limited resources the budget engine allocates."""

    SEARCH = "search"
    CRAWL = "crawl"
    VALIDATION = "validation"
    ONBOARDING = "onboarding"


class OpportunityKind(StrEnum):
    NEW_CITY = "new_city"
    INACTIVE_ECOSYSTEM = "inactive_ecosystem"
    STALE_ORGANIZER = "stale_organizer"
    SEASONAL_EVENT = "seasonal_event"
    RECURRING_CONFERENCE = "recurring_conference"
    MISSING_UNIVERSITY_COVERAGE = "missing_university_coverage"


class EntityKind(StrEnum):
    """Things whose freshness (age) the freshness engine tracks."""

    ORGANIZER = "organizer"
    SEED = "seed"
    VALIDATION = "validation"
    PROVIDER = "provider"
    EXPANSION = "expansion"


class RecommendationKind(StrEnum):
    INCREASE_EXPANSION = "increase_expansion"
    REDUCE_EXPLORATION = "reduce_exploration"
    REVISIT_LATER = "revisit_later"
    MAINTAIN = "maintain"


# Cadence → wall-clock interval; the scheduler fires a kind when now - last_fired >= interval.
CADENCE_SECONDS: dict[GrowthCadence, int | None] = {
    GrowthCadence.CONTINUOUS: 0,
    GrowthCadence.HOURLY: 3_600,
    GrowthCadence.DAILY: 86_400,
    GrowthCadence.WEEKLY: 604_800,
    GrowthCadence.MANUAL: None,
}

# Higher = more urgent. The planner selects the highest-priority eligible, affordable task.
DEFAULT_PRIORITY: dict[TaskKind, int] = {
    TaskKind.VALIDATION: 90,
    TaskKind.ONBOARDING: 70,
    TaskKind.EXPANSION: 60,
    TaskKind.ORGANIZER_REFRESH: 50,
    TaskKind.PRODUCTION_MONITOR: 40,
}

# Which resource each task kind consumes (used for budget gating).
TASK_RESOURCE: dict[TaskKind, GrowthResource] = {
    TaskKind.ORGANIZER_REFRESH: GrowthResource.CRAWL,
    TaskKind.EXPANSION: GrowthResource.CRAWL,
    TaskKind.VALIDATION: GrowthResource.VALIDATION,
    TaskKind.ONBOARDING: GrowthResource.ONBOARDING,
    TaskKind.PRODUCTION_MONITOR: GrowthResource.CRAWL,
}


# --------------------------------------------------------------------------- tasks


@dataclass
class GrowthTask:
    """A unit of work in the growth queue. Deduplicated by (kind, target)."""

    kind: TaskKind
    target: str
    priority: int = -1
    state: TaskState = TaskState.QUEUED
    attempts: int = 0
    max_attempts: int = 3
    cooldown_until: int = 0  # run counter; eligible once run >= cooldown_until
    lease_owner: str = ""
    lease_until: int = 0  # run counter; lease expires (reclaimable) once run >= lease_until
    created_run: int = 0
    reason: str = ""
    task_id: str = ""

    def __post_init__(self) -> None:
        if self.priority < 0:
            self.priority = DEFAULT_PRIORITY.get(self.kind, 50)
        if not self.task_id:
            self.task_id = self.dedup_key

    @property
    def dedup_key(self) -> str:
        return f"{self.kind.value}:{self.target}"

    @property
    def resource(self) -> GrowthResource:
        return TASK_RESOURCE.get(self.kind, GrowthResource.CRAWL)

    def is_active(self) -> bool:
        """A task still occupying a queue slot (blocks a duplicate enqueue)."""
        return self.state in (TaskState.QUEUED, TaskState.LEASED, TaskState.COOLDOWN)

    def eligible(self, run: int) -> bool:
        if self.state == TaskState.QUEUED:
            return run >= self.cooldown_until
        if self.state == TaskState.COOLDOWN:
            return run >= self.cooldown_until
        if self.state == TaskState.LEASED:
            return run >= self.lease_until  # lease expired → reclaimable
        return False

    def as_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "kind": self.kind.value,
            "target": self.target,
            "priority": self.priority,
            "state": self.state.value,
            "attempts": self.attempts,
            "cooldown_until": self.cooldown_until,
            "lease_owner": self.lease_owner,
            "lease_until": self.lease_until,
            "created_run": self.created_run,
            "reason": self.reason,
        }


# --------------------------------------------------------------------------- budget


@dataclass
class GrowthBudget:
    """Per-resource allocation. Never lets consumption exceed the limit."""

    limits: dict[GrowthResource, int] = field(default_factory=dict)
    consumed: dict[GrowthResource, int] = field(default_factory=dict)

    def remaining(self, r: GrowthResource) -> int:
        return max(0, self.limits.get(r, 0) - self.consumed.get(r, 0))

    def can_spend(self, r: GrowthResource, n: int = 1) -> bool:
        return n <= self.remaining(r)

    def spend(self, r: GrowthResource, n: int) -> int:
        """Spend up to `n` (never past the limit); return what was actually spent."""
        spent = max(0, min(n, self.remaining(r)))
        self.consumed[r] = self.consumed.get(r, 0) + spent
        return spent

    def fraction_left(self, r: GrowthResource) -> float:
        limit = self.limits.get(r, 0)
        return self.remaining(r) / limit if limit else 1.0

    def reset(self) -> None:
        self.consumed = {}

    def as_dict(self) -> dict:
        return {
            r.value: {"limit": self.limits.get(r, 0), "consumed": self.consumed.get(r, 0)}
            for r in self.limits
        }


# --------------------------------------------------------------------------- freshness


@dataclass
class FreshnessRecord:
    entity_id: str
    kind: EntityKind
    last_touched: datetime
    ttl_seconds: int

    def age_seconds(self, now: datetime) -> float:
        return max(0.0, (now - self.last_touched).total_seconds())

    def is_stale(self, now: datetime) -> bool:
        return self.age_seconds(now) >= self.ttl_seconds

    def as_dict(self, now: datetime | None = None) -> dict:
        d = {
            "entity_id": self.entity_id,
            "kind": self.kind.value,
            "last_touched": self.last_touched.isoformat(),
            "ttl_seconds": self.ttl_seconds,
        }
        if now is not None:
            d["age_seconds"] = round(self.age_seconds(now), 1)
            d["stale"] = self.is_stale(now)
        return d


# --------------------------------------------------------------------------- opportunities


@dataclass
class GrowthOpportunity:
    kind: OpportunityKind
    target: str
    reason: str
    priority: int = 60
    evidence: dict = field(default_factory=dict)

    @property
    def dedup_key(self) -> str:
        return f"{self.kind.value}:{self.target}"

    def to_task(self) -> GrowthTask:
        """Opportunities become expansion work, except stale organizers → a refresh."""
        kind = (
            TaskKind.ORGANIZER_REFRESH
            if self.kind is OpportunityKind.STALE_ORGANIZER
            else TaskKind.EXPANSION
        )
        return GrowthTask(
            kind=kind,
            target=self.target,
            priority=self.priority,
            reason=f"opportunity:{self.kind.value}",
        )

    def as_dict(self) -> dict:
        return {
            "kind": self.kind.value,
            "target": self.target,
            "reason": self.reason,
            "priority": self.priority,
            "evidence": dict(self.evidence),
        }


# --------------------------------------------------------------------------- recommendations


@dataclass
class Recommendation:
    kind: RecommendationKind
    reason: str
    evidence: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"kind": self.kind.value, "reason": self.reason, "evidence": dict(self.evidence)}


# --------------------------------------------------------------------------- step seam


@dataclass
class StepContext:
    """Everything a growth step needs: the task, the current run, and the live budget."""

    task: GrowthTask
    run: int
    budget: GrowthBudget
    now: datetime


@dataclass
class StepOutcome:
    """What a growth step reports. Counts feed metrics; follow_ups re-enter the queue."""

    success: bool = True
    organizers_found: int = 0
    seeds_generated: int = 0
    seeds_validated: int = 0
    accepted: int = 0
    rejected: int = 0
    promoted: int = 0
    failures: int = 0
    follow_ups: list[GrowthTask] = field(default_factory=list)
    cost: dict[GrowthResource, int] = field(default_factory=dict)
    notes: str = ""

    def is_progress(self) -> bool:
        """Did this step grow the ecosystem? Used for steady-state detection."""
        return (self.organizers_found + self.seeds_generated + self.accepted + self.promoted) > 0

    def as_dict(self) -> dict:
        return {
            "success": self.success,
            "organizers_found": self.organizers_found,
            "seeds_generated": self.seeds_generated,
            "seeds_validated": self.seeds_validated,
            "accepted": self.accepted,
            "rejected": self.rejected,
            "promoted": self.promoted,
            "failures": self.failures,
            "follow_ups": [t.kind.value for t in self.follow_ups],
            "cost": {r.value: n for r, n in self.cost.items()},
            "notes": self.notes,
        }


# A growth step: given a context, do the work and report an outcome.
GrowthStep = Callable[[StepContext], Awaitable[StepOutcome]]


# --------------------------------------------------------------------------- reports & dashboard


@dataclass
class CycleRecord:
    run: int
    task_kind: str | None
    target: str | None
    outcome: dict
    reason: str
    timestamp: str

    def as_dict(self) -> dict:
        return {
            "run": self.run,
            "task_kind": self.task_kind,
            "target": self.target,
            "outcome": self.outcome,
            "reason": self.reason,
            "timestamp": self.timestamp,
        }


@dataclass
class GrowthMetricsSnapshot:
    cycles: int = 0
    new_organizers: int = 0
    new_seeds: int = 0
    validated: int = 0
    promoted: int = 0
    rejected: int = 0
    growth_velocity: float = 0.0  # accepted per cycle
    ecosystem_coverage: float = 0.0  # cities covered / cities known
    expansion_efficiency: float = 0.0  # accepted / seeds generated

    def as_dict(self) -> dict:
        return {
            "cycles": self.cycles,
            "new_organizers": self.new_organizers,
            "new_seeds": self.new_seeds,
            "validated": self.validated,
            "promoted": self.promoted,
            "rejected": self.rejected,
            "growth_velocity": round(self.growth_velocity, 4),
            "ecosystem_coverage": round(self.ecosystem_coverage, 4),
            "expansion_efficiency": round(self.expansion_efficiency, 4),
        }


@dataclass
class GrowthSnapshot:
    """The dashboard model — a read-only picture of the growth system at one instant. No UI."""

    run: int
    backlog: int
    queue: list[dict]
    opportunities: list[dict]
    budgets: dict
    health: dict
    freshness: list[dict]
    recommendations: list[dict]
    metrics: dict

    def as_dict(self) -> dict:
        return {
            "run": self.run,
            "backlog": self.backlog,
            "queue": self.queue,
            "opportunities": self.opportunities,
            "budgets": self.budgets,
            "health": self.health,
            "freshness": self.freshness,
            "recommendations": self.recommendations,
            "metrics": self.metrics,
        }


@dataclass
class GrowthReport:
    cycles: int = 0
    tasks_executed: int = 0
    idle_cycles: int = 0
    by_kind: dict[str, int] = field(default_factory=dict)
    reached_steady_state: bool = False

    def as_dict(self) -> dict:
        return {
            "cycles": self.cycles,
            "tasks_executed": self.tasks_executed,
            "idle_cycles": self.idle_cycles,
            "by_kind": dict(self.by_kind),
            "reached_steady_state": self.reached_steady_state,
        }
