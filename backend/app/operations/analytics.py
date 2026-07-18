"""Operations analytics (Phase 7B) — the control-plane report.

Deterministic aggregation over production registrations + outcomes + the learning report: promotion
and canary success, rollbacks, discovery/review precision, confidence calibration error, growth
velocity, and health/state trends. Read-only.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.operations.feedback import OutcomeRecord
from app.operations.learning import LearningReport
from app.operations.registry import ProductionRegistration, ProductionState


@dataclass
class OperationsAnalytics:
    total_promotions: int = 0
    failed_preflight: int = 0
    canary: int = 0
    active: int = 0
    rolled_back: int = 0
    promotion_success_rate: float = 0.0
    canary_success_rate: float = 0.0
    rollback_rate: float = 0.0
    discovery_precision: float = 0.0
    review_precision: float = 0.0
    confidence_calibration_error: float = 0.0
    growth_velocity: float = 0.0
    by_provider_type: dict = field(default_factory=dict)
    by_state: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "total_promotions": self.total_promotions,
            "failed_preflight": self.failed_preflight,
            "canary": self.canary,
            "active": self.active,
            "rolled_back": self.rolled_back,
            "promotion_success_rate": self.promotion_success_rate,
            "canary_success_rate": self.canary_success_rate,
            "rollback_rate": self.rollback_rate,
            "discovery_precision": self.discovery_precision,
            "review_precision": self.review_precision,
            "confidence_calibration_error": self.confidence_calibration_error,
            "growth_velocity": self.growth_velocity,
            "by_provider_type": self.by_provider_type,
            "by_state": self.by_state,
        }


def _rate(n: int, d: int) -> float:
    return round(n / d, 4) if d else 0.0


def build_operations_analytics(
    registrations: list[ProductionRegistration],
    outcomes: list[OutcomeRecord],
    learning_report: LearningReport,
) -> OperationsAnalytics:
    a = OperationsAnalytics(total_promotions=len(registrations))
    for reg in registrations:
        a.by_state[reg.state.value] = a.by_state.get(reg.state.value, 0) + 1
        if reg.state is ProductionState.ACTIVE:
            a.by_provider_type[reg.provider_type] = a.by_provider_type.get(reg.provider_type, 0) + 1

    a.failed_preflight = a.by_state.get(ProductionState.FAILED_PREFLIGHT.value, 0)
    a.canary = a.by_state.get(ProductionState.CANARY.value, 0)
    a.active = a.by_state.get(ProductionState.ACTIVE.value, 0)
    a.rolled_back = a.by_state.get(ProductionState.ROLLED_BACK.value, 0)

    passed_preflight = a.total_promotions - a.failed_preflight
    canary_run = a.active + a.rolled_back
    a.promotion_success_rate = _rate(a.active, passed_preflight)
    a.canary_success_rate = _rate(a.active, canary_run)
    a.rollback_rate = _rate(a.rolled_back, canary_run)
    a.discovery_precision = _rate(a.active, a.total_promotions)

    manual = [o for o in outcomes if o.was_manual]
    a.review_precision = _rate(sum(1 for o in manual if not o.rolled_back), len(manual))
    a.confidence_calibration_error = learning_report.calibration_error
    a.growth_velocity = float(a.active)  # net providers now serving (per-window in a real deploy)
    return a
