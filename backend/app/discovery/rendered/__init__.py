"""AI Rendered Discovery & Hidden Data Extraction (Phase 8E).

Discovers events hidden behind modern JS frameworks — pages that ship `__NEXT_DATA__` /
`window.__INITIAL_STATE__` / Apollo cache / hydration state / JSON blobs instead of HTML — and the
hidden event APIs those SPAs call. Extracts hydration payloads and endpoints from the served bytes
(reusing D2's extractors), then a deterministic **AI reasoning layer** (mock; real LLM is a future
seam) produces a `ProviderCandidate` with confidence, evidence, missing fields, and a recommended
provider type.

Strictly additive and discovery-only: HTML/JS/JSON only — no browser, no Playwright/Selenium, no JS
execution, no network. No changes to Search, the Repository, the Catalog, Production, or the
frontend. Output stops at the Discovery Inbox (`discovered_by="rendered"`, `status=NEW`).
"""

from app.discovery.rendered.endpoints import classify_endpoint, discover_endpoints
from app.discovery.rendered.engine import RenderedDiscoveryEngine, RenderedPage
from app.discovery.rendered.hydration import (
    collect_hydration,
    has_graphql_cache,
    window_globals,
)
from app.discovery.rendered.models import (
    DiscoveredEndpoint,
    EndpointKind,
    HydrationPayload,
    HydrationSource,
    ProviderCandidate,
    RenderedReport,
)
from app.discovery.rendered.reasoning import AIReasoner, MockAIReasoner
from app.discovery.rendered.store import (
    InMemoryRenderedStore,
    RenderedRecord,
    RenderedStore,
    SQLiteRenderedStore,
)

__all__ = [
    # engine
    "RenderedDiscoveryEngine",
    "RenderedPage",
    "RenderedReport",
    # hydration
    "collect_hydration",
    "window_globals",
    "has_graphql_cache",
    "HydrationPayload",
    "HydrationSource",
    # endpoints
    "discover_endpoints",
    "classify_endpoint",
    "DiscoveredEndpoint",
    "EndpointKind",
    # reasoning
    "AIReasoner",
    "MockAIReasoner",
    "ProviderCandidate",
    # store
    "RenderedStore",
    "InMemoryRenderedStore",
    "SQLiteRenderedStore",
    "RenderedRecord",
]
