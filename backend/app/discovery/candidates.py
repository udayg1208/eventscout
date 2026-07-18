"""Candidate builder — turns a (detection + signals) into a CandidateSource.

The per-dimension "confidence" fields are **transparent deterministic aggregates** of the
signals (documented in models.py), NOT the final onboarding confidence score (deferred).
"""

from __future__ import annotations

from datetime import datetime

from app.city import detect_city
from app.discovery.feeds import FeedDetection
from app.discovery.fetch import FetchResult
from app.discovery.models import CandidateSource, ConfidenceSignals, DiscoveryStatus, FeedType
from app.discovery.urls import normalize_url, registrable_domain

# Structured *pages* (one event each) collapse to one source-candidate per domain — the
# domain is the source, not each event page. Feeds/endpoints key by their own URL.
# D2 page-level payloads (hydration/embedded JSON) are also per-domain: the framework payload
# is a property of the page shell, not a distinct feed URL. Endpoints (JSON_API/GRAPHQL) key
# per URL.
_PAGE_LEVEL = {
    FeedType.JSONLD_EVENT,
    FeedType.MICRODATA_EVENT,
    FeedType.OPENGRAPH_EVENT,
    FeedType.NEXT_DATA,
    FeedType.NEXT_FLIGHT,
    FeedType.HYDRATION_STATE,
    FeedType.EMBEDDED_JSON,
}


def _organization_hint(url: str, title: str | None) -> str:
    label = registrable_domain(url).split(".")[0]
    return label.upper() if len(label) <= 4 else label.capitalize()


def build_candidate(
    *,
    result: FetchResult,
    detection: FeedDetection,
    signals: ConfidenceSignals,
    discovery_path: list[str],
    now: datetime,
    analysis: object | None = None,
) -> CandidateSource:
    url = detection.url
    domain = registrable_domain(url)
    key = (
        f"{domain}#{detection.feed_type.value}"
        if detection.feed_type in _PAGE_LEVEL
        else (normalize_url(url) or url)
    )
    tech_conf = min(1.0, signals.tech_keyword_count / 5.0)
    india_conf = (
        1.0
        if signals.india_reference_count >= 2
        else (0.5 if signals.india_reference_count == 1 else 0.0)
    )
    professional_conf = min(
        1.0,
        0.5 * (signals.tech_keyword_count > 0)
        + 0.3 * signals.has_organizer
        + 0.2 * signals.has_registration_link,
    )
    city = detect_city(detection.title or "", result.text[:20_000])

    return CandidateSource(
        key=key,
        url=url,
        domain=registrable_domain(url),
        feed_type=detection.feed_type,
        title=detection.title,
        organization=_organization_hint(url, detection.title),
        country="India" if india_conf >= 0.5 else None,
        city=city,
        technology_confidence=round(tech_conf, 3),
        india_confidence=india_conf,
        professional_confidence=round(professional_conf, 3),
        structured_data_score=signals.structured_count(),
        signals=signals,
        discovery_path=list(discovery_path),
        status=DiscoveryStatus.NEW,
        crawl_timestamp=now,
        first_seen_at=now,
        last_seen_at=now,
        framework=getattr(analysis, "framework", None),
        framework_version=getattr(analysis, "framework_version", None),
        api_endpoints=list(getattr(analysis, "api_endpoints", []) or []),
        graphql_endpoints=list(getattr(analysis, "graphql_endpoints", []) or []),
        hydration_source=getattr(analysis, "hydration_source", None),
        embedded_event_count=getattr(analysis, "embedded_event_count", 0) or 0,
    )
