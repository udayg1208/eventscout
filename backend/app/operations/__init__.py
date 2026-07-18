"""Production Operations Platform (Phase 7B) — the controlled production control plane.

Everything after a 7A PromotionPlan: safely promote approved providers into the live ecosystem
(canary-first, health-gated), continuously monitor them, auto-rollback on hard failures, and learn
from real performance to calibrate future onboarding confidence — all deterministic, analytics-only
(no ML). "Controlled autonomous operations", not autonomous publishing.

Additive and reuse-only: it reuses the Provider State Store (health), the scheduler's rate util,
and 7A's PromotionPlan. It does NOT modify Search, the Event catalog, the Repository, the Discovery
Engine, provider implementations, the frontend, or API contracts.
"""

from app.operations.analytics import OperationsAnalytics, build_operations_analytics
from app.operations.engine import OperationsEngine
from app.operations.feedback import FeedbackSignals, OutcomeRecord, collect_feedback
from app.operations.health import HealthSnapshot, HealthTracker
from app.operations.learning import (
    CalibrationBucket,
    CalibrationModel,
    LearningReport,
    apply_calibration,
    learn,
)
from app.operations.production import (
    CanaryMetrics,
    CanaryResult,
    CanarySync,
    CanaryThresholds,
    MockCanarySync,
    PreflightResult,
    evaluate_canary,
    preflight,
)
from app.operations.registry import (
    ProductionRegistration,
    ProductionState,
    provider_id_for,
    registration_from_plan,
)
from app.operations.rollback import (
    RollbackDecision,
    RollbackEngine,
    RollbackReason,
    RollbackThresholds,
    evaluate_rollback,
)
from app.operations.scheduler import ScheduleConfig, build_schedule_config
from app.operations.store import (
    InMemoryOperationsStore,
    OperationsStore,
    SQLiteOperationsStore,
)

__all__ = [
    "OperationsEngine",
    # production / canary
    "preflight",
    "PreflightResult",
    "CanaryMetrics",
    "CanaryResult",
    "CanaryThresholds",
    "evaluate_canary",
    "CanarySync",
    "MockCanarySync",
    # registry / scheduler
    "ProductionRegistration",
    "ProductionState",
    "registration_from_plan",
    "provider_id_for",
    "ScheduleConfig",
    "build_schedule_config",
    # health / rollback
    "HealthTracker",
    "HealthSnapshot",
    "RollbackEngine",
    "RollbackDecision",
    "RollbackReason",
    "RollbackThresholds",
    "evaluate_rollback",
    # feedback / learning
    "OutcomeRecord",
    "FeedbackSignals",
    "collect_feedback",
    "learn",
    "LearningReport",
    "CalibrationModel",
    "CalibrationBucket",
    "apply_calibration",
    # analytics / store
    "OperationsAnalytics",
    "build_operations_analytics",
    "OperationsStore",
    "InMemoryOperationsStore",
    "SQLiteOperationsStore",
]
