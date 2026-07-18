"""Real Web Discovery Engine (Phase 8B) — discover new event sources from the public web.

Replaces the D3 mock search with REAL providers (Google Programmable Search, Bing, SerpAPI,
DuckDuckGo) behind a 24h cache, rate limiting, robots, and backoff. The engine reuses the D3
pipeline (query builder → parser → ranking → candidate builder) and 8A prioritization, and stops at
the Discovery Inbox — nothing is onboarded or promoted.

This is the first phase that talks to the real internet. It is strictly additive: no browser, no
Playwright/Selenium, no LLM, and no changes to Search, the Repository, the Catalog, providers,
ingestion, the scheduler, the frontend, or the API.
"""

from app.discovery.web.bing import BingWebSearchProvider
from app.discovery.web.cache import CacheStats, SearchCache, normalize_query
from app.discovery.web.duckduckgo import DuckDuckGoProvider, parse_ddg_html
from app.discovery.web.engine import WebDiscoveryEngine, WebDiscoveryReport
from app.discovery.web.fetch import DISCOVERY_WEB_UA, FetchResponse, PoliteFetcher, RobotsGate
from app.discovery.web.google import GoogleProgrammableSearchProvider
from app.discovery.web.interfaces import (
    ProviderError,
    SearchProviderConfig,
    SearchResult,
    WebSearchProvider,
)
from app.discovery.web.normalizer import dedupe_across, normalize_results
from app.discovery.web.rate_limit import Budget, DomainGuard, RateLimiter
from app.discovery.web.serpapi import SerpApiSearchProvider

__all__ = [
    # contract
    "WebSearchProvider",
    "SearchProviderConfig",
    "SearchResult",
    "ProviderError",
    # providers
    "GoogleProgrammableSearchProvider",
    "BingWebSearchProvider",
    "SerpApiSearchProvider",
    "DuckDuckGoProvider",
    "parse_ddg_html",
    # infrastructure
    "PoliteFetcher",
    "FetchResponse",
    "RobotsGate",
    "DISCOVERY_WEB_UA",
    "SearchCache",
    "CacheStats",
    "normalize_query",
    "RateLimiter",
    "DomainGuard",
    "Budget",
    "normalize_results",
    "dedupe_across",
    # engine
    "WebDiscoveryEngine",
    "WebDiscoveryReport",
]
