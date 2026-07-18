"""Discovery Engine domain models (Phase 6D / D1).

Additive and self-contained: the Discovery Engine produces **Candidate Sources** only — it
never touches the Repository, Registry, Scheduler, or Catalog. A candidate describes a
discovered, potentially-ingestible source (a feed or an event-bearing page) plus the
**deterministic signals** collected about it. No final confidence score is computed in D1
(that is the later Confidence Engine's job) — only raw, explainable signals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class FeedType(StrEnum):
    """How a discovered source exposes its events."""

    RSS = "rss"
    ATOM = "atom"
    ICS = "ics"
    JSON_FEED = "json_feed"
    XML_SITEMAP = "xml_sitemap"
    EVENT_SITEMAP = "event_sitemap"
    JSONLD_EVENT = "jsonld_event"
    GOOGLE_CALENDAR = "google_calendar"
    MICRODATA_EVENT = "microdata_event"
    OPENGRAPH_EVENT = "opengraph_event"
    # --- D2: sources embedded in modern JS frameworks (extracted from raw HTML) ---
    NEXT_DATA = "next_data"  # Next.js Pages Router __NEXT_DATA__
    NEXT_FLIGHT = "next_flight"  # Next.js App Router RSC (self.__next_f)
    HYDRATION_STATE = "hydration_state"  # __NUXT__ / __APOLLO_STATE__ / __INITIAL_STATE__
    EMBEDDED_JSON = "embedded_json"  # generic <script type=application/json> with events
    JSON_API = "json_api"  # a discovered client API endpoint (source to probe later)
    GRAPHQL = "graphql"  # a discovered GraphQL endpoint
    # --- D3: a source page found via a search engine (type not yet crawled/determined) ---
    SEARCH_RESULT = "search_result"
    # --- D4: understood via AI extraction of unstructured page text (no structured data) ---
    AI_EXTRACTED = "ai_extracted"
    UNKNOWN = "unknown"


# Feed types that carry structured *event* data (vs. navigational like a plain sitemap).
STRUCTURED_EVENT_FEEDS = frozenset(
    {
        FeedType.RSS,
        FeedType.ATOM,
        FeedType.ICS,
        FeedType.JSON_FEED,
        FeedType.EVENT_SITEMAP,
        FeedType.JSONLD_EVENT,
        FeedType.GOOGLE_CALENDAR,
        FeedType.MICRODATA_EVENT,
        FeedType.NEXT_DATA,
        FeedType.NEXT_FLIGHT,
        FeedType.HYDRATION_STATE,
        FeedType.EMBEDDED_JSON,
    }
)

# Feed types that are endpoints to probe later, not directly-parseable event feeds.
ENDPOINT_FEEDS = frozenset({FeedType.JSON_API, FeedType.GRAPHQL})


class DiscoveryStatus(StrEnum):
    """Discovery Inbox lifecycle (see PROVIDER_AUTO_ONBOARDING_ARCHITECTURE §2). D1 only
    ever produces NEW; the rest exist so later phases (validation/onboarding) can advance a
    candidate without a schema change."""

    NEW = "new"
    ANALYZING = "analyzing"
    VALIDATED = "validated"
    REJECTED = "rejected"
    HUMAN_REVIEW = "human_review"
    APPROVED = "approved"
    PRODUCTION = "production"
    DISABLED = "disabled"
    ARCHIVED = "archived"


@dataclass(frozen=True)
class ConfidenceSignals:
    """Deterministic, explainable signals about a candidate. Booleans/counts only — NO
    weighted final score (that is deferred to the Confidence Engine)."""

    # structured-data presence
    has_jsonld_event: bool = False
    has_microdata_event: bool = False
    has_opengraph_event: bool = False
    has_rss: bool = False
    has_atom: bool = False
    has_ics: bool = False
    has_json_feed: bool = False
    has_sitemap: bool = False
    has_google_calendar: bool = False
    # content signals
    tech_keyword_count: int = 0
    india_reference_count: int = 0
    has_organizer: bool = False
    has_registration_link: bool = False
    has_recurring: bool = False  # multiple event-like URLs / feed entries
    event_count: int = 0  # events detected in the feed/page
    # --- D2: modern-framework signals ---
    has_framework: bool = False
    has_nextjs: bool = False
    has_hydration: bool = False
    has_embedded_events: bool = False
    has_json_array: bool = False
    has_calendar_schema: bool = False
    has_api_endpoint: bool = False
    has_graphql_endpoint: bool = False

    def structured_count(self) -> int:
        """How many distinct structured-data signals fired (the transparent
        `structured_data_score`)."""
        return sum(
            (
                self.has_jsonld_event,
                self.has_microdata_event,
                self.has_opengraph_event,
                self.has_rss,
                self.has_atom,
                self.has_ics,
                self.has_json_feed,
                self.has_sitemap,
                self.has_google_calendar,
                self.has_embedded_events,
                self.has_hydration,
            )
        )

    def as_dict(self) -> dict[str, int | bool]:
        return {
            "has_jsonld_event": self.has_jsonld_event,
            "has_microdata_event": self.has_microdata_event,
            "has_opengraph_event": self.has_opengraph_event,
            "has_rss": self.has_rss,
            "has_atom": self.has_atom,
            "has_ics": self.has_ics,
            "has_json_feed": self.has_json_feed,
            "has_sitemap": self.has_sitemap,
            "has_google_calendar": self.has_google_calendar,
            "tech_keyword_count": self.tech_keyword_count,
            "india_reference_count": self.india_reference_count,
            "has_organizer": self.has_organizer,
            "has_registration_link": self.has_registration_link,
            "has_recurring": self.has_recurring,
            "event_count": self.event_count,
            "has_framework": self.has_framework,
            "has_nextjs": self.has_nextjs,
            "has_hydration": self.has_hydration,
            "has_embedded_events": self.has_embedded_events,
            "has_json_array": self.has_json_array,
            "has_calendar_schema": self.has_calendar_schema,
            "has_api_endpoint": self.has_api_endpoint,
            "has_graphql_endpoint": self.has_graphql_endpoint,
        }


@dataclass
class CandidateSource:
    """One discovered source. `key` (normalized URL) is the dedup identity."""

    key: str  # normalized URL — primary identity
    url: str  # as-discovered URL
    domain: str  # registrable domain
    feed_type: FeedType
    title: str | None = None
    organization: str | None = None
    country: str | None = None
    city: str | None = None

    # transparent, deterministic per-dimension aggregates (0..1) — NOT the final
    # onboarding confidence; derived purely from `signals`.
    technology_confidence: float = 0.0
    india_confidence: float = 0.0
    professional_confidence: float = 0.0
    structured_data_score: int = 0

    signals: ConfidenceSignals = field(default_factory=ConfidenceSignals)
    discovery_method: str = "structured-crawl"
    discovery_path: list[str] = field(default_factory=list)  # seed → … → this url

    # --- D2: modern-framework fields ---
    framework: str | None = None
    framework_version: str | None = None
    api_endpoints: list[str] = field(default_factory=list)
    graphql_endpoints: list[str] = field(default_factory=list)
    hydration_source: str | None = None  # which payload carried events (e.g. "__NEXT_DATA__")
    embedded_event_count: int = 0

    # --- D3: search-discovery provenance (how a search-found source got here) ---
    discovered_by: str = "crawl"  # "crawl" (D1/D2) | "search" (D3) | "ai" (D4)
    search_query: str | None = None  # the query that surfaced this source
    search_rank: int | None = None  # 1-based position in the search results
    search_engine: str | None = None  # which SearchProvider returned it (e.g. "mock", "google")

    # --- D4: AI-extraction verdict. The realized Confidence Engine every prior phase deferred; the
    # full per-field AIExtraction + provenance lives in the AIExtractionStore, keyed by url. ---
    discovery_confidence: float | None = None  # combined confidence (0..1), None until D4 runs
    classification: str | None = None  # primary source class (e.g. "community", "conference")

    status: DiscoveryStatus = DiscoveryStatus.NEW
    status_reason: str = ""
    crawl_timestamp: datetime | None = None
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    version: int = 1


@dataclass(frozen=True)
class CrawlRecord:
    """A persisted crawl checkpoint entry — enables incremental crawling + resume."""

    url: str  # normalized URL
    domain: str
    crawled_at: datetime
    status: int
