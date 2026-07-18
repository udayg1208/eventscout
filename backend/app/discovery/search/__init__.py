"""Search Discovery (Phase 6F / D3) — find ENTIRELY NEW event sources via web search.

D1 finds feeds on known domains; D2 finds framework-hidden data on known domains. Neither finds
new websites. This package asks a web-search engine for pages matching deterministic queries
(city × technology × platform × event-type × university × company), scores each discovered source,
and inserts the promising ones into the Discovery Inbox as `SEARCH_RESULT` candidates.

Strictly additive and discovery-only: no LLM, no browser, no real search API (MockSearchProvider
only), no ingestion, no provider/catalog/scheduler/registry/SearchService/frontend/API changes.
Output stops at the Discovery Inbox (`status=NEW`).
"""

from app.discovery.search.dedup import by_domain, dedupe, key_for
from app.discovery.search.engine import (
    SearchDiscoveryEngine,
    SearchDiscoveryReport,
    build_search_candidate,
)
from app.discovery.search.frontier import Frontier
from app.discovery.search.parser import ParsedResult, parse_result, parse_results
from app.discovery.search.query_builder import (
    DEFAULT_SPEC,
    QuerySpec,
    build_queries,
)
from app.discovery.search.ranking import WEIGHTS, DiscoveryScore, score_source
from app.discovery.search.search import (
    MockPage,
    MockSearchProvider,
    SearchProvider,
    SearchResult,
)

__all__ = [
    "SearchProvider",
    "SearchResult",
    "MockSearchProvider",
    "MockPage",
    "QuerySpec",
    "DEFAULT_SPEC",
    "build_queries",
    "ParsedResult",
    "parse_result",
    "parse_results",
    "DiscoveryScore",
    "score_source",
    "WEIGHTS",
    "Frontier",
    "dedupe",
    "by_domain",
    "key_for",
    "SearchDiscoveryEngine",
    "SearchDiscoveryReport",
    "build_search_candidate",
]
