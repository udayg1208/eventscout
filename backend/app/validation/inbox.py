"""Discovery Inbox integration (Phase 10E) — verified seed → CandidateSource(status=NEW).

Only VERIFIED / PARTIALLY_VERIFIED results earn a Discovery Inbox candidate. Builds a
provenance-bearing `CandidateSource` (the existing D1 model) from the collected evidence and
upserts it into the *existing* `DiscoveryInbox` — reusing its key-based dedup (D1/D3/7A duplicate
logic), never bypassing it. No provider creation, no onboarding, no catalog write.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.discovery.models import (
    CandidateSource,
    ConfidenceSignals,
    DiscoveryStatus,
    FeedType,
)
from app.discovery.urls import registrable_domain
from app.validation.models import VerificationResult


class CandidateBuilder:
    def build(self, result: VerificationResult, *, now: datetime | None = None) -> CandidateSource:
        now = now or datetime.now(UTC)
        ev = result.evidence
        url = ev.homepage_url or ""
        domain = registrable_domain(url) if url else ""
        feed_type = (
            FeedType.ICS
            if ev.calendars
            else FeedType.RSS
            if ev.feeds
            else FeedType.AI_EXTRACTED
            if ev.has_jsonld or ev.events_found
            else FeedType.SEARCH_RESULT
        )
        tech = ev.technologies or []
        india = 0.8 if ev.city else 0.0
        signals = ConfidenceSignals(
            has_embedded_events=ev.events_found > 0,
            has_json_array=ev.has_jsonld,
            tech_keyword_count=len(tech),
            india_reference_count=2 if india >= 0.8 else 0,
        )
        return CandidateSource(
            key=url or f"validation:{result.seed_target}",
            url=url,
            domain=domain,
            feed_type=feed_type,
            title=ev.organizer_name or result.seed_target,
            organization=ev.organizer_name,
            country="India" if ev.city else None,
            city=ev.city,
            technology_confidence=round(min(1.0, len(tech) / 3.0), 3),
            india_confidence=india,
            professional_confidence=round(result.confidence.total, 3),
            structured_data_score=signals.structured_count(),
            signals=signals,
            discovery_method="seed-validation",
            discovery_path=[result.seed_kind],
            discovered_by="validation",
            classification=result.seed_kind,
            discovery_confidence=result.confidence.total,
            status=DiscoveryStatus.NEW,
            crawl_timestamp=now,
            first_seen_at=now,
            last_seen_at=now,
        )
