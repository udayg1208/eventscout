"""Phase 4B: search infrastructure — index, retrievers, fusion, planner, metrics, pipeline.

Deterministic, network-free. Builds an FTS index and an entity graph from hand-made events
and exercises each retriever, RRF fusion, the query planner, search metrics, and the full
`DatabaseSearchProvider` pipeline end to end.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime

from app.entities.builder import GraphBuilder
from app.entities.queries import EntityQueries
from app.models.event import Event, EventCategory
from app.models.search import SearchQuery
from app.search.candidates import Candidate, CandidateSet
from app.search.db_provider import DatabaseSearchProvider
from app.search.hybrid import HybridRetriever
from app.search.index import IndexDocument, SQLiteFTS5Index
from app.search.metrics import SearchMetrics
from app.search.planner import QueryPlanner
from app.search.retrievers import EntityRetriever, KeywordRetriever, StructuredRetriever
from app.storage.models import StoredEvent
from app.storage.sqlite_repository import SQLiteEventRepository


def run(coro):
    return asyncio.run(coro)


NOW = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
TODAY = date(2026, 7, 15)


def _event(
    title,
    *,
    city="Bangalore",
    provider="seed",
    category=EventCategory.MEETUP,
    description=None,
    start=date(2026, 9, 1),
):
    return Event(
        title=title,
        url=f"https://x.example.com/{title.replace(' ', '-').replace('/', '-').lower()}",
        city=city,
        provider=provider,
        category=category,
        description=description,
        start_date=start,
    )


def _stored(event):
    return StoredEvent.from_event(event, seen_at=NOW)


def _repo(events):
    repo = SQLiteEventRepository()
    run(repo.bulk_upsert([_stored(e) for e in events]))
    return repo


def _index(events):
    index = SQLiteFTS5Index()
    docs = [
        IndexDocument(
            key=_stored(e).key, title=e.title, description=e.description or "", city=e.city or ""
        )
        for e in events
    ]
    run(index.rebuild(docs))
    return index


def _graph(events):
    return GraphBuilder().build([_stored(e) for e in events])


# --------------------------- SearchIndex (FTS5) ---------------------------


def test_fts_index_and_search():
    index = _index([_event("Applied Machine Learning"), _event("Cloud Native Day")])
    assert run(index.count()) == 2
    hits = run(index.search("machine", limit=10))
    assert len(hits) == 1
    key, score = hits[0]
    assert key.endswith("applied-machine-learning") and score > 0  # negated bm25 → higher better


def test_fts_stemming_beats_like():
    # "study" stems to "studi" and matches "Case Studies" — a substring LIKE '%study%'
    # would NOT (there is no "study" substring in "Studies"). This is FTS beating LIKE.
    index = _index([_event("Case Studies in AI")])
    assert len(run(index.search("study", limit=10))) == 1
    assert "study" not in "Case Studies in AI".casefold()  # LIKE would miss it


def test_fts_rebuild_and_delete():
    index = _index([_event("A"), _event("B")])
    run(index.rebuild([IndexDocument(key="k", title="Rebuilt Event")]))
    assert run(index.count()) == 1
    assert len(run(index.search("rebuilt", limit=10))) == 1
    run(index.delete(["k"]))
    assert run(index.count()) == 0


def test_fts_empty_query_returns_nothing():
    index = _index([_event("Anything")])
    assert run(index.search("", limit=10)) == []


# --------------------------- retrievers ---------------------------


def test_keyword_retriever():
    events = [_event("AI Summit"), _event("Cloud Workshop", description="kubernetes")]
    retriever = KeywordRetriever(_index(events))
    result = run(retriever.retrieve(SearchQuery(keywords=["kubernetes"]), 10))
    assert result.source == "keyword"
    assert [c.event_key for c in result.candidates] == [_stored(events[1]).key]
    assert run(retriever.retrieve(SearchQuery(), 10)).candidates == []  # no keywords → empty


def test_structured_retriever():
    events = [_event("blr", city="Bangalore"), _event("del", city="Delhi")]
    retriever = StructuredRetriever(_repo(events), clock=lambda: TODAY)
    result = run(retriever.retrieve(SearchQuery(city="Bangalore"), 10))
    assert result.source == "structured"
    assert [c.event_key for c in result.candidates] == [_stored(events[0]).key]


def test_entity_retriever():
    events = [_event("GDG DevFest", provider="gdg"), _event("Random Meetup", provider="luma")]
    retriever = EntityRetriever(_graph(events))
    result = run(retriever.retrieve(SearchQuery(keywords=["gdg"]), 10))
    assert result.source == "entity"
    assert [c.event_key for c in result.candidates] == [_stored(events[0]).key]
    assert run(retriever.retrieve(SearchQuery(keywords=["nonexistent"]), 10)).candidates == []


# --------------------------- RRF fusion ---------------------------


def test_rrf_fuses_and_dedupes():
    keyword = CandidateSet(
        "keyword", [Candidate("a", 5.0, "keyword"), Candidate("b", 4.0, "keyword")]
    )
    entity = CandidateSet("entity", [Candidate("b", 1.0, "entity"), Candidate("c", 1.0, "entity")])
    fused = HybridRetriever().fuse([keyword, entity], limit=10)
    keys = [c.event_key for c in fused]
    assert keys[0] == "b"  # appears in both lists → highest fused score
    assert set(keys) == {"a", "b", "c"}
    b = next(c for c in fused if c.event_key == "b")
    assert b.source == "entity+keyword"  # provenance of both


def test_rrf_single_set_passthrough_and_deterministic():
    cs = CandidateSet(
        "structured", [Candidate("x", 1.0, "structured"), Candidate("y", 0.5, "structured")]
    )
    first = [c.event_key for c in HybridRetriever().fuse([cs], limit=10)]
    second = [c.event_key for c in HybridRetriever().fuse([cs], limit=10)]
    assert first == ["x", "y"] == second


# --------------------------- query planner ---------------------------


def _planner(events):
    graph = _graph(events)
    repo = _repo(events)
    return QueryPlanner(
        keyword=KeywordRetriever(_index(events)),
        structured=StructuredRetriever(repo, clock=lambda: TODAY),
        entity=EntityRetriever(graph),
        entity_queries=EntityQueries(graph),
    )


def test_planner_strategies():
    planner = _planner([_event("GDG DevFest", provider="gdg")])
    assert planner.plan(SearchQuery(keywords=["gdg"])).strategy == "hybrid"
    assert planner.plan(SearchQuery(keywords=["kubernetes"])).strategy == "keyword"
    assert planner.plan(SearchQuery(city="Bangalore")).strategy == "structured"
    assert planner.plan(SearchQuery(categories=[EventCategory.AI])).strategy == "structured"
    assert planner.plan(SearchQuery()).strategy == "browse"


def test_planner_is_deterministic():
    planner = _planner([_event("Google I/O", provider="luma")])
    a = planner.plan(SearchQuery(keywords=["google"]))
    b = planner.plan(SearchQuery(keywords=["google"]))
    assert a.strategy == b.strategy == "hybrid"


# --------------------------- search metrics ---------------------------


def test_search_metrics_snapshot():
    metrics = SearchMetrics()
    metrics.record(
        retrieval_ms=2.0,
        ranking_ms=1.0,
        candidates_by_source={"keyword": 5},
        fused_count=5,
        result_count=3,
    )
    metrics.record(
        retrieval_ms=4.0,
        ranking_ms=2.0,
        candidates_by_source={"keyword": 3},
        fused_count=3,
        result_count=0,
    )
    snap = metrics.snapshot()
    assert snap["total_searches"] == 2
    assert snap["zero_result_searches"] == 1 and snap["zero_result_rate"] == 0.5
    assert snap["retrieval_latency_ms"]["p50"] >= 2.0
    assert snap["avg_candidates_per_retriever"]["keyword"] == 4.0
    assert snap["avg_fused_candidates"] == 4.0


# --------------------------- end-to-end pipeline ---------------------------


def _provider(events, **kw):
    return DatabaseSearchProvider(_repo(events), clock=lambda: TODAY, **kw)


def test_pipeline_keyword_search_via_fts():
    events = [_event("AI Summit"), _event("Cloud Workshop", description="kubernetes deep dive")]
    provider = _provider(events)
    results = run(provider.search(SearchQuery(keywords=["kubernetes"])))
    assert [e.title for e in results] == ["Cloud Workshop"]
    assert provider.metrics.snapshot()["total_searches"] == 1


def test_pipeline_entity_search():
    events = [_event("GDG DevFest", provider="gdg"), _event("Unrelated", provider="luma")]
    results = run(_provider(events).search(SearchQuery(keywords=["gdg"])))
    assert [e.title for e in results] == ["GDG DevFest"]


def test_pipeline_hybrid_keyword_and_entity():
    # "google" is both a keyword and a known organization → hybrid plan
    events = [
        _event("Google I/O 2026", provider="luma"),
        _event("Google Cloud Next", provider="luma"),
        _event("Postgres Meetup", provider="luma"),
    ]
    results = run(_provider(events).search(SearchQuery(keywords=["google"])))
    titles = {e.title for e in results}
    assert "Google I/O 2026" in titles and "Google Cloud Next" in titles
    assert "Postgres Meetup" not in titles


def test_pipeline_structured_and_metrics():
    events = [_event("A", city="Bangalore"), _event("B", city="Delhi")]
    provider = _provider(events)
    results = run(provider.search(SearchQuery(city="Bangalore")))
    assert [e.title for e in results] == ["A"]
    snap = provider.metrics.snapshot()
    assert "structured" in snap["avg_candidates_per_retriever"]


def test_pipeline_refresh_reflects_new_events_in_keyword_search():
    repo = _repo([_event("First Kubernetes Talk", description="kubernetes")])
    provider = DatabaseSearchProvider(repo, clock=lambda: TODAY)
    assert len(run(provider.search(SearchQuery(keywords=["kubernetes"])))) == 1
    run(repo.bulk_upsert([_stored(_event("Second Kubernetes Talk", description="kubernetes"))]))
    run(provider.invalidate())  # marks projections stale → rebuilt next search
    assert len(run(provider.search(SearchQuery(keywords=["kubernetes"])))) == 2
