"""AI Discovery domain models (Phase 6G / D4) — provenance-first.

The governing rule of D4: **AI may extract, classify, summarize, identify signals — but must never
fabricate.** Every extracted value carries `Provenance` (the exact source snippet it came from, the
reason, a confidence, the method, a timestamp). When evidence is insufficient a field is
`UNKNOWN` with a `None` value — never a guess. Nothing here is opaque.

All additive and self-contained: D4 produces Candidate Sources for the Discovery Inbox only — it
never ingests events, creates providers, or writes to the catalog.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class FieldStatus(StrEnum):
    """Whether a field was directly extracted, inferred, or left unknown (never guessed)."""

    EXTRACTED = "extracted"  # value read verbatim from a source snippet
    INFERRED = "inferred"  # value derived from evidence (e.g. India from a city)
    UNKNOWN = "unknown"  # insufficient evidence → value is None


class ExtractionMethod(StrEnum):
    """Provenance of *how* a value was obtained."""

    DETERMINISTIC = "deterministic"  # structured/regex extraction (D1/D2-style)
    AI = "ai"  # an AIExtractor (mock now, LLM later)
    HYBRID = "hybrid"  # deterministic seed refined by AI (or vice-versa)


@dataclass(frozen=True)
class Provenance:
    """Why a value is what it is. Present on every non-UNKNOWN field."""

    source_snippet: str  # the exact text the value came from (never invented)
    reason: str  # short explanation of the extraction rule / evidence
    confidence: float  # 0..1 confidence in THIS field
    method: ExtractionMethod
    timestamp: datetime | None = None


@dataclass(frozen=True)
class ExtractedField:
    """One extracted value + its provenance. `value` is None iff status is UNKNOWN."""

    value: object | None = None
    status: FieldStatus = FieldStatus.UNKNOWN
    provenance: Provenance | None = None

    @property
    def is_known(self) -> bool:
        return self.status is not FieldStatus.UNKNOWN and self.value not in (None, [], "")

    @property
    def confidence(self) -> float:
        return self.provenance.confidence if self.provenance else 0.0


def unknown() -> ExtractedField:
    """The canonical 'we don't know, and we won't guess' field."""
    return ExtractedField(value=None, status=FieldStatus.UNKNOWN, provenance=None)


# The 16 fields D4 extracts (exactly the phase brief's list).
EXTRACTION_FIELDS = (
    "organization",
    "event_platform",
    "community",
    "city",
    "state",
    "country",
    "technologies",
    "event_types",
    "audience",
    "organizer",
    "registration_links",
    "calendar_links",
    "recurring",
    "event_frequency",
    "tech_relevance",
    "india_relevance",
)


@dataclass
class AIExtraction:
    """The full, provenance-bearing understanding of one page. Stored in the AIExtractionStore."""

    url: str
    organization: ExtractedField = field(default_factory=unknown)
    event_platform: ExtractedField = field(default_factory=unknown)
    community: ExtractedField = field(default_factory=unknown)
    city: ExtractedField = field(default_factory=unknown)
    state: ExtractedField = field(default_factory=unknown)
    country: ExtractedField = field(default_factory=unknown)
    technologies: ExtractedField = field(default_factory=unknown)  # list[str]
    event_types: ExtractedField = field(default_factory=unknown)  # list[str]
    audience: ExtractedField = field(default_factory=unknown)  # list[str]
    organizer: ExtractedField = field(default_factory=unknown)
    registration_links: ExtractedField = field(default_factory=unknown)  # list[str]
    calendar_links: ExtractedField = field(default_factory=unknown)  # list[str]
    recurring: ExtractedField = field(default_factory=unknown)  # bool
    event_frequency: ExtractedField = field(default_factory=unknown)  # str
    tech_relevance: ExtractedField = field(default_factory=unknown)  # float 0..1
    india_relevance: ExtractedField = field(default_factory=unknown)  # float 0..1
    method: ExtractionMethod = ExtractionMethod.AI

    def fields(self) -> dict[str, ExtractedField]:
        return {name: getattr(self, name) for name in EXTRACTION_FIELDS}

    def known_fields(self) -> dict[str, ExtractedField]:
        return {name: f for name, f in self.fields().items() if f.is_known}

    def mean_confidence(self) -> float:
        known = [f.confidence for f in self.known_fields().values()]
        return sum(known) / len(known) if known else 0.0

    def as_dict(self) -> dict:
        def enc(f: ExtractedField) -> dict:
            prov = None
            if f.provenance is not None:
                prov = {
                    "source_snippet": f.provenance.source_snippet,
                    "reason": f.provenance.reason,
                    "confidence": f.provenance.confidence,
                    "method": f.provenance.method.value,
                    "timestamp": f.provenance.timestamp.isoformat()
                    if f.provenance.timestamp
                    else None,
                }
            return {"value": f.value, "status": f.status.value, "provenance": prov}

        return {
            "url": self.url,
            "method": self.method.value,
            "fields": {name: enc(f) for name, f in self.fields().items()},
        }


# ------------------------------ Classification ------------------------------


class SourceClass(StrEnum):
    TECH = "tech"
    NON_TECH = "non_tech"
    UNIVERSITY = "university"
    COMMUNITY = "community"
    GOVERNMENT = "government"
    COMPANY = "company"
    CONFERENCE = "conference"
    MEETUP = "meetup"
    HACKATHON = "hackathon"
    WEBINAR = "webinar"
    WORKSHOP = "workshop"
    STARTUP = "startup"
    PRODUCT = "product"
    OPEN_SOURCE = "open_source"


@dataclass(frozen=True)
class ClassLabel:
    label: SourceClass
    confidence: float
    reason: str


@dataclass
class AIClassification:
    """Ranked class labels. `primary` is the highest-confidence label (None if nothing fired)."""

    labels: list[ClassLabel] = field(default_factory=list)
    method: ExtractionMethod = ExtractionMethod.AI

    @property
    def primary(self) -> SourceClass | None:
        return self.labels[0].label if self.labels else None

    @property
    def is_tech(self) -> bool:
        return any(
            ceil.label in (SourceClass.TECH, SourceClass.OPEN_SOURCE) and ceil.confidence >= 0.5
            for ceil in self.labels
        )

    def as_dict(self) -> dict:
        return {
            "primary": self.primary.value if self.primary else None,
            "is_tech": self.is_tech,
            "method": self.method.value,
            "labels": [
                {"label": ceil.label.value, "confidence": ceil.confidence, "reason": ceil.reason}
                for ceil in self.labels
            ],
        }


# ------------------------------ Confidence ------------------------------


@dataclass(frozen=True)
class ConfidenceComponent:
    name: str  # deterministic | ai | structured | search
    score: float  # 0..1 raw signal
    weight: float  # normalized weight actually applied
    detail: str


@dataclass
class DiscoveryConfidence:
    """The combined, explainable Discovery Confidence (the realized Confidence Engine)."""

    total: float
    components: list[ConfidenceComponent] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "total": self.total,
            "reasons": list(self.reasons),
            "components": [
                {"name": c.name, "score": c.score, "weight": c.weight, "detail": c.detail}
                for c in self.components
            ],
        }


# ------------------------------ Validation ------------------------------


@dataclass
class ValidationResult:
    """Verdict of the safety validator."""

    passed: bool
    rejected_reasons: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)  # positive supporting evidence

    def as_dict(self) -> dict:
        return {
            "passed": self.passed,
            "rejected_reasons": list(self.rejected_reasons),
            "evidence": list(self.evidence),
        }
