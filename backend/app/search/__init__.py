"""Read path — the catalog-backed search engine (Phase 4B retrieval pipeline).

Search is served entirely from the Repository via a plan → retrieve → fuse → rank pipeline:
`DatabaseSearchProvider` implements the frozen `EventProvider`, so `SearchService`, the HTTP
API, and the frontend are unchanged. Retrieval is pluggable (keyword FTS / structured /
entity, RRF-fused); a semantic retriever is interface-only.
"""

from app.search.analytics import SearchAnalytics
from app.search.cache import InMemorySearchCache, SearchCache, search_cache_key
from app.search.candidates import Candidate, CandidateSet
from app.search.criteria import to_criteria
from app.search.db_provider import DatabaseSearchProvider, build_search_provider
from app.search.hybrid import HybridRetriever
from app.search.index import IndexDocument, SearchIndex, SQLiteFTS5Index
from app.search.metrics import SearchMetrics
from app.search.pipeline import RetrievalPipeline
from app.search.planner import QueryPlan, QueryPlanner
from app.search.retrievers import (
    EntityRetriever,
    KeywordRetriever,
    Retriever,
    StructuredRetriever,
)

__all__ = [
    "DatabaseSearchProvider",
    "build_search_provider",
    "to_criteria",
    # retrieval components
    "Retriever",
    "KeywordRetriever",
    "StructuredRetriever",
    "EntityRetriever",
    "HybridRetriever",
    "QueryPlanner",
    "QueryPlan",
    "RetrievalPipeline",
    "Candidate",
    "CandidateSet",
    # index
    "SearchIndex",
    "SQLiteFTS5Index",
    "IndexDocument",
    # observability
    "SearchMetrics",
    "SearchAnalytics",
    # cache
    "SearchCache",
    "InMemorySearchCache",
    "search_cache_key",
]
