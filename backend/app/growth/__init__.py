"""Continuous Autonomous Growth Scheduler (Phase 10F).

Makes EventScout self-growing. A control plane that continuously loops the existing discovery
ecosystem — 10C organizers → 10D ecosystem expansion → 10E seed validation → the Discovery Inbox →
7A onboarding (human-gated) → 7B production → observed health → back to expansion — scheduling each
activity on its cadence, planning what runs next under a budget, tracking freshness + opportunities,
learning posture recommendations, and reporting growth metrics + a dashboard snapshot. It **drives**
the frozen engines through one `GrowthStep` seam and modifies none of them. Additive; deterministic;
no browser, no LLM, no network; no automatic provider/weight/query/catalog changes.
"""

from __future__ import annotations

from app.growth.budget import DEFAULT_LIMITS, GrowthBudgetEngine
from app.growth.engine import GrowthEngine, GrowthInputs
from app.growth.freshness import DEFAULT_TTL, FreshnessEngine
from app.growth.interfaces import (
    ContinuousDaemon,
    LiveOnboardingBridge,
    LiveProductionMonitor,
)
from app.growth.learning import LearningEngine
from app.growth.metrics import GrowthMetricsEngine
from app.growth.models import (
    CADENCE_SECONDS,
    DEFAULT_PRIORITY,
    TASK_RESOURCE,
    CycleRecord,
    EntityKind,
    FreshnessRecord,
    GrowthBudget,
    GrowthCadence,
    GrowthMetricsSnapshot,
    GrowthOpportunity,
    GrowthReport,
    GrowthResource,
    GrowthSnapshot,
    GrowthStep,
    GrowthTask,
    OpportunityKind,
    Recommendation,
    RecommendationKind,
    StepContext,
    StepOutcome,
    TaskKind,
    TaskState,
)
from app.growth.opportunity import SEASONAL_CALENDAR, OpportunityEngine, OpportunitySignals
from app.growth.planner import GrowthPlanner
from app.growth.queue import GrowthQueue
from app.growth.scheduler import DEFAULT_SCHEDULE, GrowthScheduler, ScheduleSpec
from app.growth.steps import (
    SeedBuffer,
    make_constant_step,
    make_expansion_step,
    make_onboarding_step,
    make_organizer_refresh_step,
    make_production_monitor_step,
    make_validation_step,
)
from app.growth.store import GrowthStore, InMemoryGrowthStore, SQLiteGrowthStore

__all__ = [
    # engine
    "GrowthEngine",
    "GrowthInputs",
    # scheduler / planner / queue
    "GrowthScheduler",
    "ScheduleSpec",
    "DEFAULT_SCHEDULE",
    "GrowthPlanner",
    "GrowthQueue",
    # supporting engines
    "FreshnessEngine",
    "DEFAULT_TTL",
    "OpportunityEngine",
    "OpportunitySignals",
    "SEASONAL_CALENDAR",
    "GrowthBudgetEngine",
    "DEFAULT_LIMITS",
    "LearningEngine",
    "GrowthMetricsEngine",
    # steps (reuse seam)
    "GrowthStep",
    "SeedBuffer",
    "make_constant_step",
    "make_expansion_step",
    "make_validation_step",
    "make_onboarding_step",
    "make_production_monitor_step",
    "make_organizer_refresh_step",
    # models
    "TaskKind",
    "TaskState",
    "GrowthTask",
    "GrowthCadence",
    "GrowthResource",
    "GrowthBudget",
    "EntityKind",
    "FreshnessRecord",
    "OpportunityKind",
    "GrowthOpportunity",
    "RecommendationKind",
    "Recommendation",
    "StepContext",
    "StepOutcome",
    "CycleRecord",
    "GrowthMetricsSnapshot",
    "GrowthSnapshot",
    "GrowthReport",
    "CADENCE_SECONDS",
    "DEFAULT_PRIORITY",
    "TASK_RESOURCE",
    # stores
    "GrowthStore",
    "InMemoryGrowthStore",
    "SQLiteGrowthStore",
    # future seams
    "ContinuousDaemon",
    "LiveOnboardingBridge",
    "LiveProductionMonitor",
]
