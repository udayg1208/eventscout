"""Continuous Autonomous Discovery Orchestrator (Phase 9A).

The control plane that continuously executes every existing discovery capability (D1–D4, 7A–7B,
8A–8E) through one uniform stage seam — planning, scheduling, budgeting, executing, checkpointing,
recovering, and measuring — without modifying any of them. Additive; no browser, no LLM, no network.
"""

from __future__ import annotations

from app.orchestrator.engine import OrchestratorEngine
from app.orchestrator.executor import LeaseError, LeaseManager, StageExecutor
from app.orchestrator.metrics import MetricsEngine
from app.orchestrator.models import (
    Budget,
    BudgetKind,
    BudgetPool,
    Checkpoint,
    CycleReport,
    DeadLetterEntry,
    Lease,
    MetricsSnapshot,
    OrchestratorReport,
    OrchestratorState,
    PlanDecision,
    RunStatus,
    Schedule,
    ScheduleKind,
    StageContext,
    StageHealth,
    StageName,
    StageOutcome,
    StageRunner,
    StageSpec,
    StageState,
    Trigger,
)
from app.orchestrator.pipeline import Pipeline, default_pipeline
from app.orchestrator.planner import Planner
from app.orchestrator.recovery import DeadLetterQueue, RecoveryManager
from app.orchestrator.scheduler import Scheduler
from app.orchestrator.state import StateManager, deserialize_state
from app.orchestrator.store import (
    InMemoryOrchestratorStore,
    OrchestratorStore,
    SQLiteOrchestratorStore,
)

__all__ = [
    "OrchestratorEngine",
    "Pipeline",
    "default_pipeline",
    "Planner",
    "Scheduler",
    "StateManager",
    "deserialize_state",
    "StageExecutor",
    "LeaseManager",
    "LeaseError",
    "MetricsEngine",
    "RecoveryManager",
    "DeadLetterQueue",
    "OrchestratorStore",
    "InMemoryOrchestratorStore",
    "SQLiteOrchestratorStore",
    # models
    "Budget",
    "BudgetKind",
    "BudgetPool",
    "Checkpoint",
    "CycleReport",
    "DeadLetterEntry",
    "Lease",
    "MetricsSnapshot",
    "OrchestratorReport",
    "OrchestratorState",
    "PlanDecision",
    "RunStatus",
    "Schedule",
    "ScheduleKind",
    "StageContext",
    "StageHealth",
    "StageName",
    "StageOutcome",
    "StageRunner",
    "StageSpec",
    "StageState",
    "Trigger",
]
