"""Rendered Discovery Engine (Phase 8E) — SPA → hydration → reasoning → Discovery Inbox.

For each page: detect the framework, extract hydration/state blobs, discover hidden API/GraphQL/feed
endpoints inside the HTML + JS, and let the AI reasoner decide whether it's an event source and how
it could become a provider. A confident event source becomes a Discovery Inbox candidate
(`discovered_by="rendered"`), and each discovered event API becomes its own JSON_API/GRAPHQL
candidate — the hidden API that likely fronts the full dataset. Reuses D2's extractors; HTML/JS/JSON
only, no browser, no network. Output stops at the Discovery Inbox.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.city import detect_city
from app.discovery.frameworks import detect_framework
from app.discovery.models import (
    CandidateSource,
    ConfidenceSignals,
    DiscoveryStatus,
    FeedType,
)
from app.discovery.rendered.endpoints import discover_endpoints
from app.discovery.rendered.hydration import collect_hydration, has_graphql_cache
from app.discovery.rendered.models import EndpointKind, ProviderCandidate, RenderedReport
from app.discovery.rendered.reasoning import AIReasoner, MockAIReasoner
from app.discovery.rendered.store import RenderedRecord, RenderedStore
from app.discovery.store import DiscoveryInbox
from app.discovery.urls import registrable_domain

_PTYPE_TO_FEED = {
    "next_data": FeedType.NEXT_DATA,
    "hydration_state": FeedType.HYDRATION_STATE,
    "framework": FeedType.EMBEDDED_JSON,
    "json_api": FeedType.JSON_API,
    "graphql": FeedType.GRAPHQL,
    "rss": FeedType.RSS,
    "ics": FeedType.ICS,
    "crawl": FeedType.SEARCH_RESULT,
}


@dataclass
class RenderedPage:
    url: str
    html: str
    scripts: list[str] = field(default_factory=list)


def _org_hint(domain: str) -> str:
    label = domain.split(".")[0]
    return label.upper() if len(label) <= 4 else label.capitalize()


class RenderedDiscoveryEngine:
    def __init__(
        self,
        inbox: DiscoveryInbox,
        *,
        reasoner: AIReasoner | None = None,
        store: RenderedStore | None = None,
        min_confidence: float = 0.0,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._inbox = inbox
        self._reasoner = reasoner or MockAIReasoner()
        self._store = store
        self._min_confidence = min_confidence
        self._clock = clock

    def _candidate(
        self, pc: ProviderCandidate, *, hydration, endpoints, html, now
    ) -> CandidateSource:
        domain = registrable_domain(pc.url)
        techs = pc.answers.get("technology")
        n_tech = len(techs) if isinstance(techs, list) else 0
        best = max(hydration, key=lambda p: p.event_count, default=None)
        india = 0.8 if detect_city(html[:20000]) else 0.0
        signals = ConfidenceSignals(
            has_framework=pc.framework is not None,
            has_nextjs=(pc.framework or "").startswith("Next"),
            has_hydration=bool(hydration),
            has_embedded_events=pc.expected_events > 0,
            has_json_array=bool(hydration),
            has_api_endpoint=any(
                e.kind in (EndpointKind.REST, EndpointKind.JSON) for e in endpoints
            ),
            has_graphql_endpoint=any(e.kind is EndpointKind.GRAPHQL for e in endpoints),
            tech_keyword_count=n_tech,
            india_reference_count=2 if india >= 0.8 else 0,
        )
        return CandidateSource(
            key=pc.url,
            url=pc.url,
            domain=domain,
            feed_type=_PTYPE_TO_FEED.get(pc.recommended_provider_type, FeedType.EMBEDDED_JSON),
            title=(best.sample_title if best else None),
            organization=_org_hint(domain),
            country="India" if india >= 0.5 else None,
            city=detect_city(html[:20000]),
            technology_confidence=round(min(1.0, n_tech / 3.0), 3),
            india_confidence=india,
            professional_confidence=round(0.6 * pc.is_event_source, 3),
            structured_data_score=signals.structured_count(),
            signals=signals,
            discovery_method="rendered-discovery",
            discovery_path=[],
            discovered_by="rendered",
            classification=pc.recommended_provider_type,
            discovery_confidence=pc.confidence,
            framework=pc.framework,
            api_endpoints=[
                e.url for e in endpoints if e.kind in (EndpointKind.REST, EndpointKind.JSON)
            ],
            graphql_endpoints=[e.url for e in endpoints if e.kind is EndpointKind.GRAPHQL],
            hydration_source=(best.source if best else None),
            embedded_event_count=pc.expected_events,
            status=DiscoveryStatus.NEW,
            crawl_timestamp=now,
            first_seen_at=now,
            last_seen_at=now,
        )

    def _endpoint_candidate(self, endpoint, *, now) -> CandidateSource:
        ft = FeedType.GRAPHQL if endpoint.kind is EndpointKind.GRAPHQL else FeedType.JSON_API
        domain = registrable_domain(endpoint.url)
        return CandidateSource(
            key=endpoint.url,
            url=endpoint.url,
            domain=domain,
            feed_type=ft,
            organization=_org_hint(domain),
            signals=ConfidenceSignals(has_api_endpoint=True),
            discovery_method="rendered-discovery",
            discovered_by="rendered",
            classification=endpoint.kind.value,
            status=DiscoveryStatus.NEW,
            crawl_timestamp=now,
            first_seen_at=now,
            last_seen_at=now,
        )

    async def discover(self, pages: list[RenderedPage]) -> RenderedReport:
        report = RenderedReport(pages=len(pages))
        for page in pages:
            now = self._clock()
            fw = detect_framework(page.html)
            hydration = collect_hydration(page.html, page.scripts)
            endpoints = discover_endpoints(page.html, page.scripts, base=page.url)
            report.hydration_payloads += len(hydration)
            report.events_found += sum(p.event_count for p in hydration)
            report.endpoints_found += len(endpoints)
            report.event_apis += sum(1 for e in endpoints if e.event_relevant)
            if fw.name:
                report.frameworks[fw.name] = report.frameworks.get(fw.name, 0) + 1

            pc = self._reasoner.reason(
                page.url,
                framework=fw.name,
                hydration=hydration,
                endpoints=endpoints,
                html=page.html,
            )
            _ = has_graphql_cache  # (available for future evidence)
            if not (pc.is_event_source and pc.confidence >= self._min_confidence):
                report.skipped += 1
                await self._save(pc, hydration, endpoints)
                continue

            report.provider_candidates += 1
            report.by_provider_type[pc.recommended_provider_type] = (
                report.by_provider_type.get(pc.recommended_provider_type, 0) + 1
            )
            outcome = await self._inbox.upsert(
                self._candidate(
                    pc, hydration=hydration, endpoints=endpoints, html=page.html, now=now
                )
            )
            report.candidates_inserted += outcome == "inserted"
            report.candidates_updated += outcome == "updated"
            # each discovered event API is its own future-provider candidate
            for e in endpoints:
                if e.event_relevant and e.kind in (
                    EndpointKind.REST,
                    EndpointKind.JSON,
                    EndpointKind.GRAPHQL,
                ):
                    out = await self._inbox.upsert(self._endpoint_candidate(e, now=now))
                    report.candidates_inserted += out == "inserted"
                    report.candidates_updated += out == "updated"
            await self._save(pc, hydration, endpoints)
        return report

    async def _save(self, pc, hydration, endpoints) -> None:
        if self._store is not None:
            await self._store.save(
                RenderedRecord(
                    pc.url,
                    pc.as_dict(),
                    [h.as_dict() for h in hydration],
                    [e.as_dict() for e in endpoints],
                )
            )
