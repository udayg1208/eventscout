"""Candidate normalization (Phase 8D) — a SocialExtraction → a Discovery Inbox candidate.

Builds a `CandidateSource` (`discovered_by="social"`, `status=NEW`) from the extraction + priority,
mapping the source kind to an existing `FeedType` (calendar→ICS, feed→RSS, else SEARCH_RESULT) so
the frozen Discovery models are untouched. The platform is recorded in `classification`, and the
priority score in `discovery_confidence`. The full provenance lives in the SocialStore.
"""

from __future__ import annotations

from datetime import datetime

from app.city import detect_city
from app.discovery.models import CandidateSource, ConfidenceSignals, DiscoveryStatus, FeedType
from app.discovery.social.models import SocialExtraction, SocialPriority
from app.discovery.urls import normalize_url, registrable_domain


def _org_hint(domain: str) -> str:
    label = domain.split(".")[0]
    return label.upper() if len(label) <= 4 else label.capitalize()


def _feed_type(ex: SocialExtraction) -> FeedType:
    if ex.calendar.is_known:
        return FeedType.ICS
    if ex.feed.is_known:
        return FeedType.RSS
    return FeedType.SEARCH_RESULT


def to_candidate(
    ex: SocialExtraction, priority: SocialPriority, *, now: datetime
) -> CandidateSource:
    url = normalize_url(ex.url) or ex.url
    domain = registrable_domain(url)
    techs = ex.technologies.value if ex.technologies.is_known else []
    tech_conf = round(min(1.0, len(techs) / 3.0), 3)  # type: ignore[arg-type]
    city = ex.location.value if ex.location.is_known else None
    city = (
        city if isinstance(city, str) and detect_city(city) else (detect_city(city or "") or None)
    )
    india_conf = 0.8 if city else 0.0

    organizer = None
    if ex.organizer.is_known:
        organizer = str(ex.organizer.value)
    elif ex.community.is_known:
        organizer = str(ex.community.value)
    else:
        organizer = _org_hint(domain)

    signals = ConfidenceSignals(
        tech_keyword_count=len(techs),  # type: ignore[arg-type]
        india_reference_count=1 if city else 0,
        has_organizer=ex.organizer.is_known or ex.community.is_known,
        has_registration_link=ex.registration_url.is_known,
    )
    return CandidateSource(
        key=url,
        url=url,
        domain=domain,
        feed_type=_feed_type(ex),
        title=str(ex.title.value) if ex.title.is_known else None,
        organization=organizer,
        country="India" if india_conf >= 0.5 else None,
        city=city,
        technology_confidence=tech_conf,
        india_confidence=india_conf,
        professional_confidence=round(
            0.5 * float(ex.organizer.is_known or ex.community.is_known)
            + 0.3 * float(ex.registration_url.is_known)
            + 0.2 * float(ex.date.is_known),
            3,
        ),
        structured_data_score=signals.structured_count(),
        signals=signals,
        discovery_method="social-discovery",
        discovery_path=[],
        discovered_by="social",
        classification=ex.platform.value,
        discovery_confidence=priority.total,
        status=DiscoveryStatus.NEW,
        crawl_timestamp=now,
        first_seen_at=now,
        last_seen_at=now,
    )
