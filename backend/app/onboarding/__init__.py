"""Autonomous Provider Onboarding Platform (Phase 7A).

Everything AFTER the Discovery Inbox. Takes discovered candidates and moves them through a
deterministic, explainable lifecycle to a resting verdict — APPROVED (a PromotionPlan is staged),
REVIEW (a ReviewPacket awaits a human), or REJECTED — with monitoring and analytics over the whole
pipeline.

Strictly additive and pre-production: no LLM, no browser, no catalog/registry/scheduler/ingestion/
provider/frontend/API changes, and NO automatic production promotion. The engine never drives a
candidate past PROMOTED; turning a plan into a live provider is Phase 7B, behind explicit approval.
"""

from app.onboarding.analytics import build_analytics
from app.onboarding.confidence import (
    DEFAULT_THRESHOLDS,
    WEIGHTS,
    Thresholds,
    score_onboarding,
)
from app.onboarding.engine import OnboardingEngine, simulate_sandbox
from app.onboarding.lifecycle import (
    IllegalTransition,
    allowed_transitions,
    can_transition,
    is_terminal,
    transition,
)
from app.onboarding.models import (
    RESTING_STATES,
    TERMINAL_REJECTIONS,
    AuditEntry,
    ConfidenceFactor,
    MonitoringSnapshot,
    OnboardingAnalytics,
    OnboardingCandidate,
    OnboardingConfidence,
    OnboardingState,
    PromotionPlan,
    Recommendation,
    ReviewPacket,
    SandboxOutcome,
)
from app.onboarding.monitor import build_monitoring
from app.onboarding.promotion import build_promotion_plan
from app.onboarding.review import build_review_packet
from app.onboarding.store import (
    InMemoryOnboardingStore,
    OnboardingStore,
    SQLiteOnboardingStore,
)

__all__ = [
    # engine
    "OnboardingEngine",
    "simulate_sandbox",
    # lifecycle
    "OnboardingState",
    "transition",
    "can_transition",
    "allowed_transitions",
    "is_terminal",
    "IllegalTransition",
    "RESTING_STATES",
    "TERMINAL_REJECTIONS",
    # models
    "OnboardingCandidate",
    "OnboardingConfidence",
    "ConfidenceFactor",
    "SandboxOutcome",
    "ReviewPacket",
    "PromotionPlan",
    "AuditEntry",
    "Recommendation",
    "MonitoringSnapshot",
    "OnboardingAnalytics",
    # engines
    "score_onboarding",
    "Thresholds",
    "DEFAULT_THRESHOLDS",
    "WEIGHTS",
    "build_review_packet",
    "build_promotion_plan",
    "build_monitoring",
    "build_analytics",
    # store
    "OnboardingStore",
    "InMemoryOnboardingStore",
    "SQLiteOnboardingStore",
]
