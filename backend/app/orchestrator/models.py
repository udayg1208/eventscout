"""Orchestrator core types (Phase 9A) — the data the control plane reasons over.

The orchestrator is engine-agnostic: it drives every existing discovery capability through one
uniform `StageRunner` seam (`StageContext` in → `StageOutcome` out). Concrete adapters (which call
`SearchDiscoveryEngine`, `WebDiscoveryEngine`, `ExpansionEngine`, `SocialDiscoveryEngine`,
`RenderedDiscoveryEngine`, `OnboardingEngine`, `OperationsEngine`, `OptimizationEngine`, the inbox,
and the Catalog) implement that seam — see interfaces.py. Nothing here imports those engines,
so the loop stays testable with mocks and additive to the frozen systems.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class StageName(StrEnum):
    SEARCH_DISCOVERY = "search_discovery"
    WEB_DISCOVERY = "web_discovery"
    EXPANSION = "expansion"
    SOCIAL_DISCOVERY = "social_discovery"
    RENDERED_DISCOVERY = "rendered_discovery"
    INBOX = "inbox"
    ONBOARDING = "onboarding"
    PRODUCTION_OPS = "production_ops"
    CATALOG_REFRESH = "catalog_refresh"
    OPTIMIZATION = "optimization"


class StageHealth(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    PAUSED = "paused"


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"
    DEAD_LETTER = "dead_letter"


class ScheduleKind(StrEnum):
    CONTINUOUS = "continuous"  # eligible whenever budget/backlog allows
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MANUAL = "manual"  # only when explicitly triggered


class Trigger(StrEnum):
    SCHEDULE = "schedule"  # runs on its cadence
    BACKLOG = "backlog"  # runs only when it has pending work (seeds/candidates)
    BOTH = "both"


class BudgetKind(StrEnum):
    CRAWL = "crawl"
    SEARCH = "search"
    AI = "ai"
    PAGE = "page"
    PROVIDER = "provider"
    DEPTH = "depth"


_INTERVAL_SECONDS: dict[ScheduleKind, int | None] = {
    ScheduleKind.CONTINUOUS: 0,
    ScheduleKind.HOURLY: 3_600,
    ScheduleKind.DAILY: 86_400,
    ScheduleKind.WEEKLY: 604_800,
    ScheduleKind.MANUAL: None,
}


# --------------------------------------------------------------------------- budgets


@dataclass
class Budget:
    kind: BudgetKind
    limit: int
    consumed: int = 0

    def remaining(self) -> int:
        return max(0, self.limit - self.consumed)

    def can_spend(self, n: int) -> bool:
        return n <= self.remaining()

    def spend(self, n: int) -> int:
        """Spend up to `n` (never past the limit); return what was actually spent."""
        spent = max(0, min(n, self.remaining()))
        self.consumed += spent
        return spent

    def fraction_left(self) -> float:
        return self.remaining() / self.limit if self.limit else 1.0

    def as_dict(self) -> dict:
        return {"kind": self.kind.value, "limit": self.limit, "consumed": self.consumed}


@dataclass
class BudgetPool:
    budgets: dict[BudgetKind, Budget] = field(default_factory=dict)

    def get(self, kind: BudgetKind) -> Budget | None:
        return self.budgets.get(kind)

    def remaining(self, kind: BudgetKind) -> int:
        b = self.budgets.get(kind)
        return b.remaining() if b else 0

    def fraction_left(self, kind: BudgetKind) -> float:
        b = self.budgets.get(kind)
        return b.fraction_left() if b else 1.0

    def spend(self, kind: BudgetKind, n: int) -> int:
        b = self.budgets.get(kind)
        return b.spend(n) if b else 0

    def as_dict(self) -> dict:
        return {k.value: b.as_dict() for k, b in self.budgets.items()}


# --------------------------------------------------------------------------- pipeline spec


@dataclass
class Schedule:
    kind: ScheduleKind = ScheduleKind.CONTINUOUS
    interval_seconds: int | None = None  # explicit override; else derived from `kind`
    retry_max: int = 3
    retry_backoff_seconds: int = 300
    cooldown_seconds: int = 0
    paused: bool = False

    def base_interval(self) -> int | None:
        if self.interval_seconds is not None:
            return self.interval_seconds
        return _INTERVAL_SECONDS[self.kind]

    def as_dict(self) -> dict:
        return {
            "kind": self.kind.value,
            "interval_seconds": self.base_interval(),
            "retry_max": self.retry_max,
            "retry_backoff_seconds": self.retry_backoff_seconds,
            "cooldown_seconds": self.cooldown_seconds,
            "paused": self.paused,
        }


@dataclass
class StageSpec:
    """Data-driven definition of one pipeline stage — no sequence is hardcoded in the planner."""

    name: StageName
    schedule: Schedule = field(default_factory=Schedule)
    priority: float = 1.0
    trigger: Trigger = Trigger.BOTH
    budgets: dict[BudgetKind, int] = field(default_factory=dict)  # per-run request per kind
    produces_for: list[StageName] = field(default_factory=list)  # seed/backlog flow downstream
    timeout_seconds: float = 30.0
    enabled: bool = True

    def as_dict(self) -> dict:
        return {
            "name": self.name.value,
            "schedule": self.schedule.as_dict(),
            "priority": self.priority,
            "trigger": self.trigger.value,
            "budgets": {k.value: v for k, v in self.budgets.items()},
            "produces_for": [s.value for s in self.produces_for],
            "timeout_seconds": self.timeout_seconds,
            "enabled": self.enabled,
        }


# --------------------------------------------------------------------------- stage I/O


@dataclass
class StageContext:
    """What a stage runner receives — the planner's grant of work + budget for this run."""

    stage: StageName
    cycle: int
    now: datetime
    seeds: list[str] = field(default_factory=list)
    backlog: int = 0
    budgets: dict[BudgetKind, int] = field(default_factory=dict)


@dataclass
class StageOutcome:
    """What a stage runner returns — counts, health, produced seeds, and budget actually spent."""

    health: StageHealth = StageHealth.HEALTHY
    discovered: int = 0
    promoted: int = 0
    rejected: int = 0
    duplicates: int = 0
    pages: int = 0
    ai_calls: int = 0
    false_positives: int = 0
    produced_seeds: list[str] = field(default_factory=list)
    budget_spent: dict[BudgetKind, int] = field(default_factory=dict)
    note: str = ""
    error: str | None = None

    def ok(self) -> bool:
        return self.error is None and self.health is not StageHealth.FAILED

    def as_dict(self) -> dict:
        return {
            "health": self.health.value,
            "discovered": self.discovered,
            "promoted": self.promoted,
            "rejected": self.rejected,
            "duplicates": self.duplicates,
            "pages": self.pages,
            "ai_calls": self.ai_calls,
            "false_positives": self.false_positives,
            "produced_seeds": list(self.produced_seeds),
            "budget_spent": {k.value: v for k, v in self.budget_spent.items()},
            "note": self.note,
            "error": self.error,
        }


# a stage runner is any async callable mapping a context to an outcome (see interfaces.py adapters)
StageRunner = Callable[[StageContext], Awaitable[StageOutcome]]


# --------------------------------------------------------------------------- persistent state


@dataclass
class StageState:
    name: StageName
    status: RunStatus = RunStatus.PENDING
    health: StageHealth = StageHealth.HEALTHY
    last_run: datetime | None = None
    next_run: datetime | None = None
    last_duration_s: float = 0.0
    runs: int = 0
    consecutive_failures: int = 0
    retry_count: int = 0
    cooldown_until: datetime | None = None
    paused: bool = False
    backlog: int = 0
    seeds: list[str] = field(default_factory=list)
    total_discovered: int = 0
    total_promoted: int = 0
    total_rejected: int = 0
    budget_consumed: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "name": self.name.value,
            "status": self.status.value,
            "health": self.health.value,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "last_duration_s": round(self.last_duration_s, 4),
            "runs": self.runs,
            "consecutive_failures": self.consecutive_failures,
            "retry_count": self.retry_count,
            "cooldown_until": self.cooldown_until.isoformat() if self.cooldown_until else None,
            "paused": self.paused,
            "backlog": self.backlog,
            "seeds": list(self.seeds),
            "total_discovered": self.total_discovered,
            "total_promoted": self.total_promoted,
            "total_rejected": self.total_rejected,
            "budget_consumed": dict(self.budget_consumed),
            "errors": list(self.errors[-10:]),
        }


@dataclass
class Lease:
    """A single-owner, time-bounded claim on a stage — the concurrency guard (executor.py)."""

    stage: StageName
    owner: str
    acquired_at: datetime
    expires_at: datetime
    heartbeat_at: datetime

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at


@dataclass
class DeadLetterEntry:
    stage: StageName
    cycle: int
    attempts: int
    error: str
    created_at: datetime
    context: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "stage": self.stage.value,
            "cycle": self.cycle,
            "attempts": self.attempts,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "context": self.context,
        }


@dataclass
class Checkpoint:
    cycle: int
    stage: StageName | None
    created_at: datetime
    state: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "cycle": self.cycle,
            "stage": self.stage.value if self.stage else None,
            "created_at": self.created_at.isoformat(),
            "state": self.state,
        }


@dataclass
class OrchestratorState:
    running: bool = False
    cycle: int = 0
    started_at: datetime | None = None
    last_cycle_at: datetime | None = None
    stages: dict[StageName, StageState] = field(default_factory=dict)
    budget: BudgetPool = field(default_factory=BudgetPool)
    dead_letter: list[DeadLetterEntry] = field(default_factory=list)
    provider_stats: dict[str, int] = field(default_factory=dict)

    def stage(self, name: StageName) -> StageState:
        st = self.stages.get(name)
        if st is None:
            st = StageState(name=name)
            self.stages[name] = st
        return st

    def as_dict(self) -> dict:
        return {
            "running": self.running,
            "cycle": self.cycle,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "last_cycle_at": self.last_cycle_at.isoformat() if self.last_cycle_at else None,
            "stages": {k.value: v.as_dict() for k, v in self.stages.items()},
            "budget": self.budget.as_dict(),
            "dead_letter": [d.as_dict() for d in self.dead_letter],
            "provider_stats": dict(self.provider_stats),
        }


# --------------------------------------------------------------------------- planning & reporting


@dataclass
class PlanDecision:
    stage: StageName
    priority: float
    reason: str
    context: StageContext


@dataclass
class CycleReport:
    cycle: int
    stage: StageName | None
    status: RunStatus
    duration_s: float = 0.0
    reason: str = ""
    outcome: StageOutcome | None = None

    def as_dict(self) -> dict:
        return {
            "cycle": self.cycle,
            "stage": self.stage.value if self.stage else None,
            "status": self.status.value,
            "duration_s": round(self.duration_s, 4),
            "reason": self.reason,
            "outcome": self.outcome.as_dict() if self.outcome else None,
        }


@dataclass
class MetricsSnapshot:
    elapsed_s: float = 0.0
    events_discovered: int = 0
    events_per_hour: float = 0.0
    new_providers: int = 0
    providers_per_day: float = 0.0
    new_sources: int = 0
    sources_per_day: float = 0.0
    promotion_rate: float = 0.0
    duplicate_rate: float = 0.0
    crawl_efficiency: float = 0.0
    ai_calls: int = 0
    queue_sizes: dict[str, int] = field(default_factory=dict)
    stage_latency_s: dict[str, float] = field(default_factory=dict)
    throughput_per_cycle: float = 0.0
    catalog_size: int = 0
    precision: float = 0.0
    recall: float = 0.0
    false_positives: int = 0

    def as_dict(self) -> dict:
        return {
            "elapsed_s": round(self.elapsed_s, 2),
            "events_discovered": self.events_discovered,
            "events_per_hour": round(self.events_per_hour, 2),
            "new_providers": self.new_providers,
            "providers_per_day": round(self.providers_per_day, 2),
            "new_sources": self.new_sources,
            "sources_per_day": round(self.sources_per_day, 2),
            "promotion_rate": round(self.promotion_rate, 4),
            "duplicate_rate": round(self.duplicate_rate, 4),
            "crawl_efficiency": round(self.crawl_efficiency, 4),
            "ai_calls": self.ai_calls,
            "queue_sizes": dict(self.queue_sizes),
            "stage_latency_s": {k: round(v, 4) for k, v in self.stage_latency_s.items()},
            "throughput_per_cycle": round(self.throughput_per_cycle, 4),
            "catalog_size": self.catalog_size,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "false_positives": self.false_positives,
        }


@dataclass
class OrchestratorReport:
    cycles: int = 0
    stages_run: dict[str, int] = field(default_factory=dict)
    dead_lettered: int = 0
    per_cycle: list[CycleReport] = field(default_factory=list)
    metrics: MetricsSnapshot = field(default_factory=MetricsSnapshot)

    def as_dict(self) -> dict:
        return {
            "cycles": self.cycles,
            "stages_run": dict(self.stages_run),
            "dead_lettered": self.dead_lettered,
            "per_cycle": [c.as_dict() for c in self.per_cycle],
            "metrics": self.metrics.as_dict(),
        }
