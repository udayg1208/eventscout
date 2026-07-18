# Search Infrastructure (Phase 4B — implemented)

The retrieval pipeline that replaced the single-strategy search, exactly per
[PHASE4_SEARCH_ARCHITECTURE.md](PHASE4_SEARCH_ARCHITECTURE.md). Everything lives **behind
`DatabaseSearchProvider`** (the frozen `EventProvider` seam), so `SearchService`,
`QueryParser`, the API, the frontend, the Repository contracts, provider interfaces, and the
`Event` model are all unchanged.

## Architecture as implemented

```
SearchQuery  (from SearchService — unchanged)
   │  DatabaseSearchProvider
   ▼  Search Cache        (hit → return; storage-independent, TTL, invalidation)
   ▼  Query Planner       → deterministic strategy: hybrid | keyword | structured | browse
   ▼  Retrievers (run concurrently, each returns a CandidateSet of event KEYS)
        ├── KeywordRetriever    → SearchIndex (SQLite FTS5, bm25)
        ├── StructuredRetriever → Repository filters (city/category/date/free, freshness order)
        └── EntityRetriever     → Entity Graph (events by org/community/series/venue)
   ▼  Hybrid Retriever    → Reciprocal Rank Fusion → deduped, bounded candidate set
   ▼  load events         → Repository.get_many(keys)   (events loaded ONLY after fusion)
   ▼  Filter Engine       → structured constraints + active/upcoming (not keywords)
   ▼  Ranking             → existing deterministic engine, unchanged
   ▼  results             → list[Event]     (Search Metrics recorded per search)
```

Semantic retrieval is **interface-only** (`app/search/semantic.py`): `Embedder`,
`VectorIndex`, `SemanticRetriever` are defined and never emitted by the planner.

## Components

| Component | File | Role |
|---|---|---|
| `Candidate` / `CandidateSet` | `candidates.py` | event key + score + source (+ optional metadata); **no Event objects** |
| `SearchIndex` / `SQLiteFTS5Index` | `index.py` | keyword-searchable **projection** of the catalog (bm25); Repository untouched |
| `Retriever` + Keyword/Structured/Entity | `retrievers.py` | `retrieve(query, limit) → CandidateSet`; each knows only its own store |
| `HybridRetriever` | `hybrid.py` | RRF fusion (rank-based, score-scale-agnostic), deterministic |
| `QueryPlanner` / `QueryPlan` | `planner.py` | deterministic strategy selection; no AI/LLM |
| Filter Engine | `filters.py` | structured constraints post-fusion (not keywords) |
| `RetrievalPipeline` | `pipeline.py` | plan → retrieve → fuse → load → filter → rank |
| `SearchMetrics` | `metrics.py` | retrieval/ranking latency p50/95/99, candidate/fusion counts, zero-result |
| Semantic interfaces | `semantic.py` | `Embedder` / `VectorIndex` / `SemanticRetriever` — **no implementation** |
| `DatabaseSearchProvider` | `db_provider.py` | wires it all; builds projections lazily from the catalog |

## Retrieval flow (why keys, not events)

Retrievers return **event keys + scores** only. Events are loaded from the Repository
(`get_many`) **once, after fusion** — so retrieval stays index-bounded and cheap, and only
the small fused candidate set is ever materialized. Ranking then runs unchanged over those
candidate events, so **ranking is exactly as before** — the pipeline changes *how candidates
are found*, not *how they are scored*.

## Planner strategies (deterministic)

- keywords + a keyword resolves to a known entity → **hybrid** (KeywordRetriever + EntityRetriever)
- keywords, no entity match → **keyword** (KeywordRetriever)
- no keywords, has filters → **structured** (StructuredRetriever)
- no keywords, no filters → **browse** (StructuredRetriever, freshness order)

Pure function of the `SearchQuery` shape + deterministic entity presence in the graph — no
randomness, no external services.

## Projections (index + entity graph)

The Search Index and Entity Graph are **rebuildable projections** of the catalog, built
lazily from the Repository on first search and rebuilt on `invalidate()`. The Repository is
the source of truth and is never modified. **Known limitation:** the projection is a full
rebuild (no incremental/outbox yet), so after ingestion `invalidate()` must be called to
refresh keyword/entity results; structured/browse always reads the live Repository.

## Known limitations (honest)

1. **Structured/browse do a double-load.** The StructuredRetriever loads `StoredEvent`s from
   `repo.search`, keeps only keys (per the "candidates carry no events" rule), and the pipeline
   then `get_many`-reloads them — ~2× the old cost for pure-structured queries (see
   [SEARCH_BENCHMARK.md](SEARCH_BENCHMARK.md)). Sub-second regardless; a single-retriever
   fast-path is the obvious optimization.
2. **Projection rebuild is full, not incremental** — fine at 10⁴–10⁵; an outbox/CDC feed from
   ingestion is the scale answer (blocked by the frozen ingestion runner; wire on unfreeze).
3. **Filters applied post-fusion, not pushed into the keyword retriever** — at large scale a
   very selective post-filter over a keyword top-K could lose recall; push-down into FTS
   columns (city) is the fix.
4. **Query intent capped by the frozen `SearchQuery`** — online/organizer/tags are future-safe
   (index columns exist, empty today); topic/organizer arrive with the Phase-5 Opportunity model.

## Migration path — PostgreSQL FTS

`SearchIndex` is the seam. A `PostgresFTSIndex` implements the same interface using a
`tsvector` column + GIN index and `ts_rank`/`websearch_to_tsquery`. It ships with the
Postgres catalog migration (Phase 4C): the index becomes a column/materialized view of the
catalog table (or a sibling table), populated incrementally in the same transaction as the
upsert. **Retrievers, planner, fusion, and every public interface are unchanged** — only the
constructed `SearchIndex` implementation changes.

## Migration path — Meilisearch / Typesense

A `MeilisearchIndex` / `TypesenseIndex` implements `SearchIndex` against the external
service's HTTP API (`index`/`rebuild`/`search`/`delete`). It is fed the same catalog
projection via an outbox. Gains: typo-tolerance, faceting, instant-search relevance. Cost: a
separate service to run and keep in sync (a second store → reconciliation). Adopted only when
facets/typo-tolerance/scale demand it; again, **no change above the `SearchIndex` interface**.

## Future semantic retriever integration

When embeddings are added: implement `Embedder` (text→vector) and `VectorIndex` (ANN), then a
`SemanticRetriever` producing a `CandidateSet` from the query embedding. The Query Planner
gains one deterministic branch (include it when embeddings exist and the query is free-text);
the Hybrid Retriever fuses it in via RRF exactly like the others. **Nothing else changes** —
not the other retrievers, not ranking, not any public interface. No semantic code exists in
Phase 4B (interfaces only).
