"""Seed Validation & Autonomous Growth Loop (Phase 10E).

Closes the discovery loop: takes the Discovery Seeds produced by 10D and verifies them through the
existing pipeline (fetch → 10B universal extraction → 10C organizer extraction → evidence →
confidence merge → decision), upserting only VERIFIED / PARTIALLY_VERIFIED results as
`CandidateSource(status=NEW)` into the *existing* Discovery Inbox. Verification only — no provider
creation, no onboarding, no promotion. Additive; reuses D1 inbox + 10B + 10C; no network in tests,
no browser, no LLM; the catalog is never touched.
"""

from __future__ import annotations

from app.validation.confidence import WEIGHTS as CONFIDENCE_WEIGHTS
from app.validation.confidence import VerificationConfidenceMerger
from app.validation.decision import DecisionEngine
from app.validation.engine import SeedValidationEngine
from app.validation.evidence import EvidenceCollector
from app.validation.inbox import CandidateBuilder
from app.validation.interfaces import GrowthLoopScheduler, LiveSeedSearcher, SeedSearcher
from app.validation.metrics import ValidationMetrics
from app.validation.models import (
    ACCEPTED_DECISIONS,
    AuditRecord,
    Evidence,
    RetryState,
    ValidationReport,
    VerificationConfidence,
    VerificationDecision,
    VerificationPlan,
    VerificationResult,
)
from app.validation.planner import VerificationPlanner, VerificationStrategy, slugify
from app.validation.retry import RetryPolicy
from app.validation.store import (
    InMemoryValidationStore,
    SQLiteValidationStore,
    ValidationStore,
)

__all__ = [
    "SeedValidationEngine",
    "VerificationDecision",
    "VerificationResult",
    "VerificationConfidence",
    "VerificationPlan",
    "Evidence",
    "RetryState",
    "AuditRecord",
    "ValidationReport",
    "ACCEPTED_DECISIONS",
    "VerificationPlanner",
    "VerificationStrategy",
    "slugify",
    "EvidenceCollector",
    "VerificationConfidenceMerger",
    "CONFIDENCE_WEIGHTS",
    "DecisionEngine",
    "RetryPolicy",
    "CandidateBuilder",
    "ValidationMetrics",
    "SeedSearcher",
    "LiveSeedSearcher",
    "GrowthLoopScheduler",
    "ValidationStore",
    "InMemoryValidationStore",
    "SQLiteValidationStore",
]
