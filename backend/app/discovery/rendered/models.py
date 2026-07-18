"""AI Rendered Discovery models (Phase 8E).

Discovers events hidden behind modern JS frameworks (React/Next/Vue/Nuxt/Angular/Astro/Remix/Gatsby/
Svelte) — where the page ships `__NEXT_DATA__` / `window.__INITIAL_STATE__` / Apollo cache / JSON
blobs / hydration state instead of HTML — and finds the hidden event APIs those SPAs call. A
deterministic **AI reasoning layer** (mock now; real LLM is a future seam) turns the extracted
signals into a `ProviderCandidate`. Output stops at the Discovery Inbox. HTML/JS/JSON only — no
browser, no JS execution, no network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class HydrationSource(StrEnum):
    NEXT_DATA = "__NEXT_DATA__"
    NEXT_FLIGHT = "__next_f"
    INITIAL_STATE = "__INITIAL_STATE__"
    NUXT = "__NUXT__"
    APOLLO_STATE = "__APOLLO_STATE__"
    PRELOADED_STATE = "__PRELOADED_STATE__"
    EMBEDDED_JSON = "embedded_json"
    WEBPACK = "webpack"
    VITE = "vite"


class EndpointKind(StrEnum):
    REST = "rest"
    GRAPHQL = "graphql"
    JSON = "json"
    RSS = "rss"
    ICS = "ics"
    CALENDAR = "calendar"
    UNKNOWN = "unknown"


@dataclass
class HydrationPayload:
    """One hydration/state blob found in the served bytes, plus what it appears to contain."""

    source: str  # a HydrationSource value (or a window global name)
    event_count: int = 0  # event-shaped objects found inside
    sample_title: str | None = None
    top_keys: list[str] = field(default_factory=list)  # evidence: top-level keys

    def as_dict(self) -> dict:
        return {
            "source": self.source,
            "event_count": self.event_count,
            "sample_title": self.sample_title,
            "top_keys": self.top_keys,
        }


@dataclass(frozen=True)
class DiscoveredEndpoint:
    """A network endpoint referenced in the page/JS (a potential future provider — never called)."""

    url: str
    kind: EndpointKind
    source: str  # fetch / axios / graphql / xhr / config / href
    event_relevant: bool = False

    def as_dict(self) -> dict:
        return {
            "url": self.url,
            "kind": self.kind.value,
            "source": self.source,
            "event_relevant": self.event_relevant,
        }


@dataclass
class ProviderCandidate:
    """The AI reasoning verdict: could this SPA become an event provider, and how?"""

    url: str
    is_event_source: bool
    confidence: float  # 0..1
    recommended_provider_type: str
    expected_events: int
    evidence: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    answers: dict = field(default_factory=dict)  # is_event / recurring / organizer / …
    framework: str | None = None

    def as_dict(self) -> dict:
        return {
            "url": self.url,
            "is_event_source": self.is_event_source,
            "confidence": self.confidence,
            "recommended_provider_type": self.recommended_provider_type,
            "expected_events": self.expected_events,
            "evidence": list(self.evidence),
            "missing_fields": list(self.missing_fields),
            "answers": self.answers,
            "framework": self.framework,
        }


@dataclass
class RenderedReport:
    pages: int = 0
    frameworks: dict = field(default_factory=dict)
    hydration_payloads: int = 0
    events_found: int = 0
    endpoints_found: int = 0
    event_apis: int = 0
    provider_candidates: int = 0
    candidates_inserted: int = 0
    candidates_updated: int = 0
    by_provider_type: dict = field(default_factory=dict)
    skipped: int = 0

    def as_dict(self) -> dict:
        return self.__dict__.copy()
