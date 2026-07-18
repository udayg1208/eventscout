"""AI Reasoning Layer (Phase 8E) — hydration + endpoints → ProviderCandidate.

`AIReasoner` is the seam a real LLM plugs into (see interfaces.py / prompts.py). `MockAIReasoner`
reasons deterministically over the extracted signals — hydration payloads, discovered endpoints,
framework, and the tech taxonomy — to answer the phase's questions (is this an event source? can it
become a provider? which type?) with confidence, evidence, and honestly-reported missing fields.
No LLM call, no network — reproducible.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.discovery.rendered.models import (
    DiscoveredEndpoint,
    EndpointKind,
    HydrationPayload,
    HydrationSource,
    ProviderCandidate,
)
from app.enrichment.taxonomy import TECHNOLOGIES, TOPICS

_EVENT_ENDPOINT_KINDS = {EndpointKind.REST, EndpointKind.JSON, EndpointKind.GRAPHQL}


def _technologies(text: str) -> list[str]:
    low = text.lower()
    return sorted({name for name, pat in list(TOPICS) + list(TECHNOLOGIES) if pat.search(low)})


class AIReasoner(ABC):
    name: str = "reasoner"

    @abstractmethod
    def reason(
        self,
        url: str,
        *,
        framework: str | None,
        hydration: list[HydrationPayload],
        endpoints: list[DiscoveredEndpoint],
        html: str,
    ) -> ProviderCandidate: ...


class MockAIReasoner(AIReasoner):
    name = "mock-reasoner"

    def reason(self, url, *, framework, hydration, endpoints, html) -> ProviderCandidate:
        best = max(hydration, key=lambda p: p.event_count, default=None)
        best_count = best.event_count if best else 0
        event_endpoints = [
            e for e in endpoints if e.event_relevant and e.kind in _EVENT_ENDPOINT_KINDS
        ]
        feed_endpoints = [
            e
            for e in endpoints
            if e.kind in (EndpointKind.RSS, EndpointKind.ICS, EndpointKind.CALENDAR)
        ]
        gql_endpoints = [e for e in endpoints if e.kind is EndpointKind.GRAPHQL]

        is_event = best_count > 0 or bool(event_endpoints) or bool(feed_endpoints)

        # recommended provider type — cheapest reliable path to the events
        if best and best.source == HydrationSource.NEXT_DATA.value and best_count > 0:
            ptype = "next_data"
        elif event_endpoints:
            ptype = "json_api"
        elif gql_endpoints:
            ptype = "graphql"
        elif feed_endpoints:
            ptype = "rss" if feed_endpoints[0].kind is EndpointKind.RSS else "ics"
        elif best_count > 0:
            ptype = "hydration_state"
        elif hydration:
            ptype = "framework"
        else:
            ptype = "crawl"

        # confidence from evidence strength
        conf = 0.0
        evidence: list[str] = []
        if best_count > 0:
            conf += 0.4 + min(0.2, best_count / 50 * 0.2)
            evidence.append(
                f"{best.source} carried {best_count} event object(s)"
                + (f" (e.g. '{best.sample_title}')" if best.sample_title else "")
            )
        if event_endpoints:
            conf += 0.3
            evidence.append(
                f"event API endpoint: {event_endpoints[0].url} (via {event_endpoints[0].source})"
            )
        if gql_endpoints and not event_endpoints:
            conf += 0.2
            evidence.append(f"GraphQL endpoint: {gql_endpoints[0].url}")
        if feed_endpoints:
            conf += 0.15
            evidence.append(f"feed/calendar endpoint: {feed_endpoints[0].url}")
        if framework:
            conf += 0.1
            evidence.append(f"framework: {framework}")
        conf = round(min(1.0, conf), 4)

        # expected events: what we can see now; an event API likely fronts the FULL set
        expected = best_count
        if event_endpoints:
            evidence.append("event API present → full dataset likely larger than the hydrated page")

        techs = _technologies(html)
        # honest missing fields: we counted events but did not parse each event's full schema
        missing = [] if not is_event else ["date", "location", "organizer", "registration_url"]

        answers = {
            "is_event": is_event,
            "recurring": "unknown",  # not determinable from a count without parsing each event
            "organizer": "unknown",
            "location": "unknown",
            "registration_url": event_endpoints[0].url if event_endpoints else "unknown",
            "technology": techs or "unknown",
            "community": "unknown",
            "can_be_provider": is_event and conf >= 0.5,
        }
        return ProviderCandidate(
            url=url,
            is_event_source=is_event,
            confidence=conf,
            recommended_provider_type=ptype,
            expected_events=expected,
            evidence=evidence,
            missing_fields=missing,
            answers=answers,
            framework=framework,
        )
