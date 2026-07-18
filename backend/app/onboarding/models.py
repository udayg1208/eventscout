"""Provider Onboarding domain models (Phase 7A).

The platform takes Discovery Inbox candidates and moves them through a deterministic lifecycle to a
*resting* verdict — APPROVED (a PromotionPlan is staged), REVIEW (a ReviewPacket awaits a human),
or REJECTED. It **never** touches the catalog, registry, scheduler, ingestion, providers, frontend,
or API, and it **never** promotes to production automatically. Everything is additive and
explainable: every confidence score decomposes into weighted factors, every transition is audited.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class OnboardingState(StrEnum):
    """The provider-onboarding lifecycle (see PROVIDER_ONBOARDING_PLATFORM.md)."""

    DISCOVERED = "discovered"  # entered from the Discovery Inbox
    ANALYZED = "analyzed"  # evidence extracted from the candidate
    SANDBOXED = "sandboxed"  # dry-run validation over the discovery evidence
    SCORED = "scored"  # onboarding confidence computed
    AUTO_APPROVED = "auto_approved"  # high confidence → no human needed
    MANUAL_REVIEW = "manual_review"  # medium confidence → human review packet
    APPROVED = "approved"  # human (or auto) approval recorded
    PROMOTED = "promoted"  # PromotionPlan generated (staged, NOT applied) — 7A stops here
    MONITORING = "monitoring"  # post-promotion (7B territory; never auto-entered in 7A)
    ACTIVE = "active"  # live provider (7B territory)
    # ---- terminal rejections ----
    REJECTED = "rejected"  # low confidence / no evidence
    BLACKLISTED = "blacklisted"  # domain on the blacklist
    DUPLICATE = "duplicate"  # domain already onboarded / known provider
    FAILED_SANDBOX = "failed_sandbox"  # dry-run found no ingestible evidence


TERMINAL_REJECTIONS = frozenset(
    {
        OnboardingState.REJECTED,
        OnboardingState.BLACKLISTED,
        OnboardingState.DUPLICATE,
        OnboardingState.FAILED_SANDBOX,
    }
)
# States where 7A's automatic pipeline comes to rest (it never drives past these).
RESTING_STATES = frozenset(
    {OnboardingState.PROMOTED, OnboardingState.MANUAL_REVIEW, *TERMINAL_REJECTIONS}
)


class Recommendation(StrEnum):
    AUTO_APPROVE = "auto_approve"
    APPROVE = "approve"
    REVIEW = "review"
    REJECT = "reject"


# ------------------------------ Confidence ------------------------------


@dataclass(frozen=True)
class ConfidenceFactor:
    """One explainable input to the onboarding confidence — no hidden magic numbers."""

    name: str
    score: float  # 0..1 raw signal
    weight: float  # weight applied
    detail: str  # why this score

    @property
    def contribution(self) -> float:
        return round(self.score * self.weight, 4)


@dataclass
class OnboardingConfidence:
    total: float  # 0..1 weighted sum
    band: Recommendation  # auto / review / reject band the total falls into
    factors: list[ConfidenceFactor] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "total": self.total,
            "band": self.band.value,
            "reasons": list(self.reasons),
            "factors": [
                {
                    "name": f.name,
                    "score": f.score,
                    "weight": f.weight,
                    "contribution": f.contribution,
                    "detail": f.detail,
                }
                for f in self.factors
            ],
        }


# ------------------------------ Sandbox ------------------------------


@dataclass
class SandboxOutcome:
    """Deterministic dry-run over a candidate's discovered evidence (no network, no provider)."""

    tested: bool
    passed: bool
    plausible_events: int  # evidence of how many events the source likely exposes
    structured_score: int  # structured-data signals present
    quality: float  # 0..1 evidence quality
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "tested": self.tested,
            "passed": self.passed,
            "plausible_events": self.plausible_events,
            "structured_score": self.structured_score,
            "quality": self.quality,
            "notes": list(self.notes),
        }


# ------------------------------ Review packet ------------------------------


@dataclass
class ReviewPacket:
    """Everything a human reviewer needs to decide — nothing opaque."""

    url: str
    domain: str
    confidence: float
    confidence_reasons: list[str]
    extraction_summary: dict
    sample_events: list[str]
    sandbox: SandboxOutcome
    technologies: list[str]
    risks: list[str]
    recommendation: Recommendation

    def as_dict(self) -> dict:
        return {
            "url": self.url,
            "domain": self.domain,
            "confidence": self.confidence,
            "confidence_reasons": list(self.confidence_reasons),
            "extraction_summary": self.extraction_summary,
            "sample_events": list(self.sample_events),
            "sandbox": self.sandbox.as_dict(),
            "technologies": list(self.technologies),
            "risks": list(self.risks),
            "recommendation": self.recommendation.value,
        }


# ------------------------------ Promotion plan ------------------------------


@dataclass
class PromotionPlan:
    """A blueprint for how this source *would* become a provider. NEVER applied in 7A."""

    url: str
    domain: str
    provider_type: str
    configuration: dict
    refresh_interval_hours: int
    retry_policy: dict
    capabilities: list[str]
    expected_volume: str  # low | medium | high
    risk_assessment: dict
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "url": self.url,
            "domain": self.domain,
            "provider_type": self.provider_type,
            "configuration": self.configuration,
            "refresh_interval_hours": self.refresh_interval_hours,
            "retry_policy": self.retry_policy,
            "capabilities": list(self.capabilities),
            "expected_volume": self.expected_volume,
            "risk_assessment": self.risk_assessment,
            "notes": list(self.notes),
        }


# ------------------------------ Audit ------------------------------


@dataclass(frozen=True)
class AuditEntry:
    key: str
    timestamp: datetime | None
    from_state: str | None
    to_state: str
    actor: str  # "auto" | "human:<name>" | "system"
    reason: str

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "actor": self.actor,
            "reason": self.reason,
        }


# ------------------------------ Candidate record ------------------------------


@dataclass
class OnboardingCandidate:
    """One source moving through onboarding. The discovery evidence is snapshotted (decoupled from
    the live Discovery Inbox); lifecycle/confidence/plan state lives here."""

    key: str
    url: str
    domain: str
    feed_type: str
    discovered_by: str
    source_snapshot: dict  # distilled discovery fields (title/city/tech/confidences/…)
    state: OnboardingState = OnboardingState.DISCOVERED
    confidence: OnboardingConfidence | None = None
    sandbox: SandboxOutcome | None = None
    review_packet: ReviewPacket | None = None
    promotion_plan: PromotionPlan | None = None
    review_notes: list[str] = field(default_factory=list)
    promotion_history: list[dict] = field(default_factory=list)
    confidence_history: list[float] = field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    version: int = 1

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "url": self.url,
            "domain": self.domain,
            "feed_type": self.feed_type,
            "discovered_by": self.discovered_by,
            "source_snapshot": self.source_snapshot,
            "state": self.state.value,
            "confidence": self.confidence.as_dict() if self.confidence else None,
            "sandbox": self.sandbox.as_dict() if self.sandbox else None,
            "review_packet": self.review_packet.as_dict() if self.review_packet else None,
            "promotion_plan": self.promotion_plan.as_dict() if self.promotion_plan else None,
            "review_notes": list(self.review_notes),
            "promotion_history": list(self.promotion_history),
            "confidence_history": list(self.confidence_history),
            "version": self.version,
        }


# ------------------------------ Monitoring & analytics ------------------------------


@dataclass
class MonitoringSnapshot:
    total: int = 0
    auto_approved: int = 0
    manual_review: int = 0
    approved: int = 0
    promoted: int = 0
    rejected: int = 0
    duplicate: int = 0
    failed_sandbox: int = 0
    blacklisted: int = 0
    approval_rate: float = 0.0
    rejection_rate: float = 0.0
    duplicate_rate: float = 0.0
    sandbox_failure_rate: float = 0.0
    promotion_success_rate: float = 0.0
    avg_confidence: float = 0.0
    avg_quality: float = 0.0
    stale_review: int = 0
    false_positive_estimate: int = 0

    def as_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class OnboardingAnalytics:
    inbox_size: int = 0
    review_queue: int = 0
    auto_approvals: int = 0
    human_approvals: int = 0
    rejections: int = 0
    promotion_candidates: int = 0
    average_confidence: float = 0.0
    by_state: dict = field(default_factory=dict)
    by_feed_type: dict = field(default_factory=dict)
    by_discovered_by: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "inbox_size": self.inbox_size,
            "review_queue": self.review_queue,
            "auto_approvals": self.auto_approvals,
            "human_approvals": self.human_approvals,
            "rejections": self.rejections,
            "promotion_candidates": self.promotion_candidates,
            "average_confidence": self.average_confidence,
            "by_state": self.by_state,
            "by_feed_type": self.by_feed_type,
            "by_discovered_by": self.by_discovered_by,
        }
