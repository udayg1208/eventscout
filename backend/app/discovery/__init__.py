"""Discovery Engine (Phase 6D / D1 + 6E / D2) — discovery of candidate event sources.

Additive package. It crawls seed domains, detects structured event data (JSON-LD/RSS/Atom/
ICS/JSON-Feed/sitemap/Google-Calendar/Microdata/OpenGraph — D1) and modern-framework payloads
(__NEXT_DATA__/Flight/hydration state/embedded JSON/client API + GraphQL endpoints — D2),
builds Candidate Sources with deterministic signals, and persists them to a Discovery Inbox.
It NEVER touches the Repository, Registry, Scheduler, or Catalog — output stops at the inbox
(status=NEW). No JavaScript is ever executed — everything is parsed from the served HTML.
"""

from app.discovery.analysis import FrameworkAnalysis, analyze_frameworks
from app.discovery.engine import DiscoveryEngine, DiscoveryReport, Seed, SeedResult
from app.discovery.fetch import DISCOVERY_UA, FetchResult, HttpxFetcher, StaticFetcher
from app.discovery.frameworks import FrameworkInfo, detect_framework
from app.discovery.models import (
    CandidateSource,
    ConfidenceSignals,
    DiscoveryStatus,
    FeedType,
)
from app.discovery.store import (
    DiscoveryInbox,
    InMemoryCrawlCheckpointStore,
    InMemoryDiscoveryInbox,
    SQLiteCrawlCheckpointStore,
    SQLiteDiscoveryInbox,
)

__all__ = [
    "DiscoveryEngine",
    "Seed",
    "SeedResult",
    "DiscoveryReport",
    "CandidateSource",
    "ConfidenceSignals",
    "FeedType",
    "DiscoveryStatus",
    "DiscoveryInbox",
    "InMemoryDiscoveryInbox",
    "SQLiteDiscoveryInbox",
    "InMemoryCrawlCheckpointStore",
    "SQLiteCrawlCheckpointStore",
    "HttpxFetcher",
    "StaticFetcher",
    "FetchResult",
    "DISCOVERY_UA",
    "FrameworkAnalysis",
    "analyze_frameworks",
    "FrameworkInfo",
    "detect_framework",
]
