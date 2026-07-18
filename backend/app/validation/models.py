"""Seed Validation models (Phase 10E) — verify 10D Discovery Seeds into the Discovery Inbox.

This phase closes the discovery loop: a generated `ExpansionSeed` (10D) is a *hypothesis* ("GDG
Chennai probably exists"); validation verifies it through the existing pipeline (fetch → 10B
universal extraction → 10C organizer extraction → evidence → confidence merge → decision) and, only
when VERIFIED / PARTIALLY_VERIFIED, upserts a provenance-bearing `CandidateSource` into the
*existing* Discovery Inbox (`status=NEW`). Verification only — no provider creation, onboarding, or
promotion. Additive; no network in tests, no browser, no LLM; the catalog is never touched.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class VerificationDecision(StrEnum):
    VERIFIED = "verified"
    PARTIALLY_VERIFIED = "partially_verified"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    REJECTED = "rejected"


# the decisions that earn a Discovery Inbox candidate
ACCEPTED_DECISIONS = (VerificationDecision.VERIFIED, VerificationDecision.PARTIALLY_VERIFIED)


@dataclass
class Evidence:
    """Everything found while verifying a seed. Never fabricated — set only if observed."""

    reachable: bool = False
    homepage_url: str | None = None
    has_jsonld: bool = False
    events_found: int = 0
    feeds: list[str] = field(default_factory=list)
    calendars: list[str] = field(default_factory=list)
    organizer_name: str | None = None
    technologies: list[str] = field(default_factory=list)
    city: str | None = None
    registration_url: str | None = None
    universal_confidence: float = 0.0
    organizer_confidence: float = 0.0
    pages_fetched: int = 0
    snippets: list[str] = field(default_factory=list)  # provenance breadcrumbs

    def signal_count(self) -> int:
        return sum(
            [
                self.reachable,
                self.has_jsonld,
                self.events_found > 0,
                bool(self.feeds),
                bool(self.calendars),
                bool(self.organizer_name),
                bool(self.technologies),
                bool(self.city),
                bool(self.registration_url),
            ]
        )

    def merge(self, other: Evidence) -> None:
        self.reachable = self.reachable or other.reachable
        self.homepage_url = self.homepage_url or other.homepage_url
        self.has_jsonld = self.has_jsonld or other.has_jsonld
        self.events_found = max(self.events_found, other.events_found)
        self.feeds = sorted({*self.feeds, *other.feeds})
        self.calendars = sorted({*self.calendars, *other.calendars})
        self.organizer_name = self.organizer_name or other.organizer_name
        self.technologies = sorted({*self.technologies, *other.technologies})
        self.city = self.city or other.city
        self.registration_url = self.registration_url or other.registration_url
        self.universal_confidence = max(self.universal_confidence, other.universal_confidence)
        self.organizer_confidence = max(self.organizer_confidence, other.organizer_confidence)
        self.pages_fetched += other.pages_fetched
        self.snippets = [*self.snippets, *other.snippets][:12]

    def as_dict(self) -> dict:
        return {
            "reachable": self.reachable,
            "homepage_url": self.homepage_url,
            "has_jsonld": self.has_jsonld,
            "events_found": self.events_found,
            "feeds": self.feeds,
            "calendars": self.calendars,
            "organizer_name": self.organizer_name,
            "technologies": self.technologies,
            "city": self.city,
            "registration_url": self.registration_url,
            "universal_confidence": round(self.universal_confidence, 3),
            "organizer_confidence": round(self.organizer_confidence, 3),
            "pages_fetched": self.pages_fetched,
            "signal_count": self.signal_count(),
        }


@dataclass
class VerificationConfidence:
    total: float
    components: dict[str, float] = field(default_factory=dict)
    reasons: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "total": round(self.total, 4),
            "components": {k: round(v, 4) for k, v in self.components.items()},
            "reasons": self.reasons,
        }


@dataclass
class VerificationPlan:
    strategy: str  # the seed kind's strategy name
    search_query: str
    candidate_urls: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)  # the verification path

    def as_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "search_query": self.search_query,
            "candidate_urls": list(self.candidate_urls),
            "steps": list(self.steps),
        }


@dataclass
class VerificationResult:
    seed_target: str
    seed_kind: str
    decision: VerificationDecision
    confidence: VerificationConfidence
    evidence: Evidence
    plan: VerificationPlan
    reasons: list[str] = field(default_factory=list)
    inbox_outcome: str | None = None  # inserted | updated | duplicate | None
    candidate_key: str | None = None
    timestamp: datetime | None = None

    @property
    def accepted(self) -> bool:
        return self.decision in ACCEPTED_DECISIONS

    def as_dict(self) -> dict:
        return {
            "seed_target": self.seed_target,
            "seed_kind": self.seed_kind,
            "decision": self.decision.value,
            "confidence": self.confidence.as_dict(),
            "evidence": self.evidence.as_dict(),
            "plan": self.plan.as_dict(),
            "reasons": list(self.reasons),
            "inbox_outcome": self.inbox_outcome,
            "candidate_key": self.candidate_key,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


@dataclass
class RetryState:
    seed_key: str
    attempts: int = 0
    next_run: int = 0  # run number at which it is eligible again
    abandoned: bool = False
    last_decision: str | None = None

    def as_dict(self) -> dict:
        return {
            "seed_key": self.seed_key,
            "attempts": self.attempts,
            "next_run": self.next_run,
            "abandoned": self.abandoned,
            "last_decision": self.last_decision,
        }


@dataclass
class AuditRecord:
    seed_target: str
    seed_kind: str
    decision: str
    confidence: float
    evidence: dict
    reasons: list[str]
    verification_path: list[str]
    inbox_outcome: str | None
    timestamp: str

    def as_dict(self) -> dict:
        return {
            "seed_target": self.seed_target,
            "seed_kind": self.seed_kind,
            "decision": self.decision,
            "confidence": round(self.confidence, 4),
            "evidence": self.evidence,
            "reasons": self.reasons,
            "verification_path": self.verification_path,
            "inbox_outcome": self.inbox_outcome,
            "timestamp": self.timestamp,
        }


@dataclass
class ValidationReport:
    total: int = 0
    verified: int = 0
    partial: int = 0
    insufficient: int = 0
    rejected: int = 0
    accepted_to_inbox: int = 0
    duplicates: int = 0
    retries_scheduled: int = 0
    abandoned: int = 0
    skipped_cooldown: int = 0

    def as_dict(self) -> dict:
        return {
            "total": self.total,
            "verified": self.verified,
            "partial": self.partial,
            "insufficient": self.insufficient,
            "rejected": self.rejected,
            "accepted_to_inbox": self.accepted_to_inbox,
            "duplicates": self.duplicates,
            "retries_scheduled": self.retries_scheduled,
            "abandoned": self.abandoned,
            "skipped_cooldown": self.skipped_cooldown,
        }
