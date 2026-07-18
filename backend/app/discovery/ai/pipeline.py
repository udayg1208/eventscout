"""AI Discovery Pipeline (Phase 6G / D4) — deterministic-first orchestration.

    Raw Page → Deterministic Extraction → Missing? → AI Extraction → Validator → Confidence → Inbox

AI runs **only when deterministic (D1/D2) extraction cannot confidently understand the page** — if
structured event data is present, D1/D2 already own it and D4 defers. Otherwise the AI extractor
reads the prose, the validator gates off-topic/insufficient pages, the Confidence Engine combines
all signals, and a page that clears the bar becomes an `ai`-provenance Candidate Source in the
Discovery Inbox (full provenance saved to the AIExtractionStore). No ingestion, no catalog writes.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from app.discovery.ai.classifier import AIClassifier
from app.discovery.ai.confidence import compute_confidence, search_score_from_rank
from app.discovery.ai.extractor import AIExtractor, ExtractionInput
from app.discovery.ai.models import (
    AIClassification,
    AIExtraction,
    DiscoveryConfidence,
    ValidationResult,
)
from app.discovery.ai.store import AIExtractionRecord, AIExtractionStore
from app.discovery.ai.validator import validate
from app.discovery.analysis import analyze_frameworks
from app.discovery.feeds import FeedDetection, detect_feeds
from app.discovery.fetch import FetchResult
from app.discovery.models import (
    STRUCTURED_EVENT_FEEDS,
    CandidateSource,
    ConfidenceSignals,
    DiscoveryStatus,
    FeedType,
)
from app.discovery.store import DiscoveryInbox
from app.discovery.urls import registrable_domain

_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


class Decision(StrEnum):
    DETERMINISTIC_SUFFICIENT = (
        "deterministic_sufficient"  # D1/D2 already understand it → AI skipped
    )
    AI_ACCEPTED = "ai_accepted"  # AI understood it, validated, confident → candidate
    AI_REJECTED = "ai_rejected"  # validator rejected (off-topic / insufficient evidence)
    LOW_CONFIDENCE = "low_confidence"  # understood but below min_confidence → not inbox'd


@dataclass
class PipelineOutcome:
    url: str
    decision: Decision
    used_ai: bool
    candidate: CandidateSource | None = None
    extraction: AIExtraction | None = None
    classification: AIClassification | None = None
    confidence: DiscoveryConfidence | None = None
    validation: ValidationResult | None = None
    reasons: list[str] = field(default_factory=list)


@dataclass
class AIDiscoveryReport:
    processed: int = 0
    deterministic_sufficient: int = 0
    ai_extracted: int = 0
    accepted: int = 0
    rejected: int = 0
    low_confidence: int = 0
    inserted: int = 0
    discovered_domains: list[str] = field(default_factory=list)


def _title_of(html: str) -> str | None:
    m = _TITLE.search(html)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else None


def _deterministic(detections: list[FeedDetection], embedded_events: int) -> tuple[float, bool]:
    """(deterministic strength 0..1, structured event data present?)."""
    event_feeds = [d for d in detections if d.feed_type in STRUCTURED_EVENT_FEEDS]
    if event_feeds or embedded_events > 0:
        return 0.85, True
    if detections:  # some structure (sitemap/unknown) but nothing event-bearing
        return 0.25, False
    return 0.0, False


def _org_hint(domain: str) -> str:
    label = domain.split(".")[0]
    return label.upper() if len(label) <= 4 else label.capitalize()


class AIDiscoveryPipeline:
    def __init__(
        self,
        extractor: AIExtractor,
        classifier: AIClassifier,
        inbox: DiscoveryInbox,
        *,
        store: AIExtractionStore | None = None,
        min_confidence: float = 0.4,
        deterministic_threshold: float = 0.6,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._extractor = extractor
        self._classifier = classifier
        self._inbox = inbox
        self._store = store
        self._min_confidence = min_confidence
        self._det_threshold = deterministic_threshold
        self._clock = clock

    def _build_candidate(
        self,
        page: ExtractionInput,
        ex: AIExtraction,
        classification: AIClassification,
        confidence: DiscoveryConfidence,
        *,
        search_query: str | None,
        search_rank: int | None,
        search_engine: str | None,
    ) -> CandidateSource:
        domain = registrable_domain(page.url)
        techs = ex.technologies.value if ex.technologies.is_known else []
        tech_conf = float(ex.tech_relevance.value) if ex.tech_relevance.is_known else 0.0
        india_conf = float(ex.india_relevance.value) if ex.india_relevance.is_known else 0.0
        signals = ConfidenceSignals(
            tech_keyword_count=len(techs),  # type: ignore[arg-type]
            india_reference_count=2 if india_conf >= 1.0 else (1 if india_conf >= 0.5 else 0),
            has_organizer=ex.organizer.is_known or ex.community.is_known,
            has_registration_link=ex.registration_links.is_known,
            has_google_calendar=ex.calendar_links.is_known,
            has_recurring=bool(ex.recurring.value) if ex.recurring.is_known else False,
        )
        org = ex.organization.value if ex.organization.is_known else _org_hint(domain)
        professional = min(
            1.0,
            0.4 * float(ex.event_types.is_known)
            + 0.3 * float(ex.community.is_known)
            + 0.3 * float(ex.organizer.is_known),
        )
        now = self._clock()
        return CandidateSource(
            key=page.url,
            url=page.url,
            domain=domain,
            feed_type=FeedType.AI_EXTRACTED,
            title=page.title,
            organization=str(org) if org else None,
            country=ex.country.value if ex.country.is_known else None,  # type: ignore[assignment]
            city=ex.city.value if ex.city.is_known else None,  # type: ignore[assignment]
            technology_confidence=round(tech_conf, 3),
            india_confidence=round(india_conf, 3),
            professional_confidence=round(professional, 3),
            structured_data_score=signals.structured_count(),
            signals=signals,
            discovery_method="ai-extraction",
            discovery_path=[search_query] if search_query else [],
            discovered_by="ai",
            search_query=search_query,
            search_rank=search_rank,
            search_engine=search_engine,
            discovery_confidence=confidence.total,
            classification=classification.primary.value if classification.primary else None,
            status=DiscoveryStatus.NEW,
            crawl_timestamp=now,
            first_seen_at=now,
            last_seen_at=now,
        )

    async def process(
        self,
        result: FetchResult,
        *,
        search_query: str | None = None,
        search_rank: int | None = None,
        search_engine: str | None = None,
    ) -> PipelineOutcome:
        page = ExtractionInput(url=result.url, text=result.text, title=_title_of(result.text))

        # 1. Deterministic extraction (D1 feeds + D2 framework) — the "is AI even needed?" gate.
        detections = detect_feeds(result)
        analysis = analyze_frameworks(result)
        det_score, structured_present = _deterministic(detections, analysis.embedded_event_count)

        if det_score >= self._det_threshold:
            return PipelineOutcome(
                url=result.url,
                decision=Decision.DETERMINISTIC_SUFFICIENT,
                used_ai=False,
                reasons=["structured event data present — D1/D2 own this page, AI skipped"],
            )

        # 2. AI extraction (prose understanding) + classification.
        ex = self._extractor.extract(page)
        classification = self._classifier.classify(page, ex)

        # 3. Validator (off-topic / insufficient evidence → reject, no candidate).
        validation = validate(page, ex)
        if not validation.passed:
            await self._maybe_save(result.url, ex, classification, _zero_conf(), validation)
            return PipelineOutcome(
                url=result.url,
                decision=Decision.AI_REJECTED,
                used_ai=True,
                extraction=ex,
                classification=classification,
                validation=validation,
                reasons=validation.rejected_reasons,
            )

        # 4. Confidence Engine (combine deterministic + AI + structured + search). Absent signal
        # families are None (excluded), NOT 0.0 — a prose page understood only by AI must not be
        # penalized for lacking the structured signals whose absence is the very reason AI ran.
        confidence = compute_confidence(
            deterministic=det_score if det_score > 0 else None,
            ai=ex.mean_confidence(),
            structured=1.0 if structured_present else None,
            search=search_score_from_rank(search_rank),
        )
        if confidence.total < self._min_confidence:
            await self._maybe_save(result.url, ex, classification, confidence, validation)
            return PipelineOutcome(
                url=result.url,
                decision=Decision.LOW_CONFIDENCE,
                used_ai=True,
                extraction=ex,
                classification=classification,
                confidence=confidence,
                validation=validation,
                reasons=[f"confidence {confidence.total:.2f} < min {self._min_confidence:.2f}"],
            )

        # 5. Discovery Inbox.
        candidate = self._build_candidate(
            page,
            ex,
            classification,
            confidence,
            search_query=search_query,
            search_rank=search_rank,
            search_engine=search_engine,
        )
        await self._inbox.upsert(candidate)
        await self._maybe_save(result.url, ex, classification, confidence, validation)
        return PipelineOutcome(
            url=result.url,
            decision=Decision.AI_ACCEPTED,
            used_ai=True,
            candidate=candidate,
            extraction=ex,
            classification=classification,
            confidence=confidence,
            validation=validation,
            reasons=[f"accepted at confidence {confidence.total:.2f}"],
        )

    async def _maybe_save(self, url, ex, classification, confidence, validation) -> None:
        if self._store is not None:
            await self._store.save(
                AIExtractionRecord(url, ex, classification, confidence, validation)
            )

    async def run(
        self, results: list[FetchResult], *, ranks: dict[str, int] | None = None
    ) -> AIDiscoveryReport:
        """Process a batch of pages; `ranks` optionally maps url → search rank (from D3)."""
        report = AIDiscoveryReport()
        domains: set[str] = set()
        for result in results:
            outcome = await self.process(
                result, search_rank=(ranks or {}).get(result.url), search_engine="mock"
            )
            report.processed += 1
            if outcome.decision is Decision.DETERMINISTIC_SUFFICIENT:
                report.deterministic_sufficient += 1
                continue
            report.ai_extracted += 1
            if outcome.decision is Decision.AI_ACCEPTED:
                report.accepted += 1
                report.inserted += 1
                domains.add(registrable_domain(result.url))
            elif outcome.decision is Decision.AI_REJECTED:
                report.rejected += 1
            elif outcome.decision is Decision.LOW_CONFIDENCE:
                report.low_confidence += 1
        report.discovered_domains = sorted(domains)
        return report


def _zero_conf() -> DiscoveryConfidence:
    return DiscoveryConfidence(total=0.0, components=[], reasons=["rejected before scoring"])
