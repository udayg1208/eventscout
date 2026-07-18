# Phase 4 — Search Infrastructure (Architecture Review & Design)

**Status: DESIGN ONLY. No implementation until approved.**
Principal-level review of the current search stack, then the target Search Infrastructure.

## 0. The one guarantee that makes this whole phase safe

Every component below lives **behind `get_provider()` → `DatabaseSearchProvider`**, which
implements the frozen `EventProvider.search(SearchQuery) -> list[Event]`. So the entire new
search engine — Query Planner, Retrievers, Search Index, Hybrid fusion, Semantic layer —
is an **internal evolution of the read-path provider**. `SearchService`, `QueryParser`, the
HTTP API, the frontend, the Repository public contract, and provider interfaces are all
**untouched**. Phase 3E already proved this seam works. Phase 4 fills it in.

---

## 1. Current review — challenge every component

Verdict legend: **KEEP** (survives as-is) · **KEEP+EVOLVE** (survives, internals grow) ·
**REPLACE** (must go for the targets).

| Component | Verdict | Why |
|---|---|---|
| **SearchService** | KEEP | Thin, correct orchestrator; the stable public contract. Its own results-cache is redundant with the new SearchCache (masks it) but frozen — leave it. Everything happens *below* it. |
| **QueryParser (Gemini)** | KEEP+EVOLVE (around it) | NL → `SearchQuery`, never fetches/invents — the right invariant. **But `SearchQuery` is impoverished** (keywords/city/categories/date/free) and **the raw text is discarded before the provider** (`search_by_query` passes only `SearchQuery`). So advanced intent must be *re-derived downstream* from `SearchQuery` — the parser stays, the planner compensates. |
| **Repository v2** | KEEP (contract) / REPLACE (SQLite backend) | The keyset `search(SearchCriteria) → Page` is perfect for **structured filters + pagination**. It is **wrong for keyword relevance** (`LIKE` full scan) and is a **single-writer, single-node SQLite file**. Keep the contract; the keyword/semantic path moves to a separate Search Index; the backend becomes Postgres. |
| **Ranking** | KEEP | Deterministic, isolated, weights-in-one-place — exactly the "rank candidates" phase. `score_source` is hardcoded (debt) and should become data-driven from provider health. Static signals (source/popularity/completeness) should be precomputed into the index; query-dependent signals stay per-candidate. |
| **Classification** | KEEP | Write-path; the stored category powers a category facet/filter in the index. |
| **Deduplication** | KEEP | Write-path; the catalog is dedup-free by construction, so the index inherits clean data. |
| **Entity Graph** | KEEP+EVOLVE | Already returns event keys (`EntityQueries`). Becomes a **first-class Entity Retriever** — this is how "events by Google" works, wired via the Query Planner **without changing SearchService**. |
| **AI parsing** | KEEP | Query understanding only. Its ceiling is `SearchQuery`'s expressiveness (frozen); a query *embedding* is a separate future concern (Semantic Layer), not the parser's job. |
| **SQLite usage** | REPLACE (as prod store) | Fine as the ₹0 dev/source-of-truth store to ~10⁵ rows. For 300–500 providers + 10⁵ active + 10⁶–10⁷ historical + sub-second + concurrent search/ingestion, **single-writer lock + no FTS + single-node** is disqualifying. → Postgres (concurrent, FTS, partitioning, replicas) behind the frozen Repository contract; SQLite stays for dev/tests. |

**The honest summary:** the *shape* built in 3E (retrieve-a-window-then-rank, behind the
provider seam) is correct and survives. The *retrieval mechanism* (`LIKE` + a freshness
window on single-node SQLite) is what fails the targets and must be replaced by an indexed,
pluggable retrieval layer.

---

## 2. Problems — can the current pipeline hit the targets?

| Target | Current reality | Verdict |
|---|---|---|
| 300–500 providers | Providers feed **ingestion** (write path), decoupled from search since 3E | ✅ search is unaffected by provider count |
| 100k active events | Structured filters use indexed columns (fine); **keyword `LIKE` is a full scan** | ⚠️ structured ✅, keyword ❌ |
| Millions historical | Search only touches active/upcoming (bounded window); but millions on **one SQLite file** = lock contention, no partitioning | ❌ needs Postgres + partitioning |
| Sub-second latency | ~1–2 ms at 102 events; `LIKE` at 10⁵ = 100 ms–seconds | ❌ for keyword at scale; needs FTS |
| AI search | Gemini parser exists; limited by `SearchQuery` + lost raw text | ⚠️ partial |
| Entity search | Graph + `EntityQueries` exist; **not wired to search** | ⚠️ needs a Retriever + Planner |
| Semantic search | **Nothing exists** | ❌ needs embeddings + vector index (interfaces now) |
| Recommendations | Nothing | ❌ future personalization layer (interface now) |

**Root problems:** (1) keyword retrieval is an un-indexed scan — the sub-second cliff at
10⁵; (2) retrieval is **single-strategy** — the provider hardcodes "filter→window→rank",
so entity/semantic retrieval can't be added without a rewrite; (3) no **hybrid** fusion of
strategies; (4) SQLite single-node/single-writer; (5) query intent is capped by the frozen
`SearchQuery`; (6) no operational search metrics (latency percentiles, retrieval size, CTR).

---

## 3. "Scan events" → "retrieve candidates" → "rank candidates" (and why it scales)

- **Pre-3E:** *scan* — fan out to live providers, gather everything, rank. O(providers), seconds.
- **3E:** *retrieve a window* — structured filter + keyset window from the repo, then rank.
  Already "retrieve then rank," but retrieval = a **single structured window** (soonest-N),
  so broad-query ranking is freshness-biased and keyword retrieval is a scan.
- **Phase 4:** *retrieve candidates from indexes* — several **bounded top-K retrievers**
  (keyword via FTS by relevance, entity via graph, structured via filters, semantic via
  vectors later) each return a small, high-recall candidate set; a **Hybrid Retriever fuses**
  them (deduped by event key) into a few hundred candidates; **Ranking** then does expensive,
  high-precision scoring on that small set.

**Why it scales:** this is the standard IR two-stage design. **Retrieval is index-backed** —
O(log n) / O(matches) per retriever, *independent of catalog size* — and **ranking is O(K)**
on the fused candidate set, never O(catalog). The catalog can grow to 10⁷ and search stays
sub-second because **neither stage ever scans the catalog.** Recall comes from cheap
retrieval; precision comes from expensive ranking on a tiny set. That decoupling is the
entire point.

---

## 4. Future architecture — the components

The pipeline (all inside the `DatabaseSearchProvider`):

```
SearchQuery  (from SearchService — unchanged)
   │
   ▼  Query Understanding      (QueryParser — already done, frozen)
   ▼  Query Planner            → QueryPlan (which retrievers + params + fusion + filters)
   ▼  Retrieval Pipeline
        ├── Filter Engine       (structured predicates: city/category/date/free/active)
        ├── Keyword Retriever    → Search Index (FTS, bm25)
        ├── Entity Retriever     → Entity Graph (events by org/community/series)
        └── Semantic Retriever   → Vector Index      [INTERFACE ONLY — future]
   ▼  Hybrid Retriever         (fuse candidate lists → deduped, bounded candidate set)
   ▼  Ranking                  (deterministic; static signals from index + query signals)
   ▼  Personalization Layer     [INTERFACE ONLY — future]
   ▼  Final Results
  (Search Cache wraps the whole; Search Analytics + Search Metrics observe it)
```

### Search Index
- **Why:** `LIKE` can't do indexed, relevance-ranked, tokenized keyword search; a separate
  index is the only path to sub-second keyword search at scale (and the future home of vectors).
- **Responsibilities:** hold a queryable projection of the catalog (title/description/entity
  text + facets: category, city, is_free, dates, static ranking signals); answer keyword
  queries with a relevance score (bm25); later hold embeddings for ANN.
- **Interactions:** built from the catalog as a **projection** (rebuild or incremental on
  ingestion via an outbox); queried by the Keyword/Semantic Retrievers. **Not** part of the
  frozen Repository — a separate component behind a `SearchIndex` interface.
- **Scalability:** SQLite FTS5 (10⁵–10⁶) → Postgres FTS (10⁶–10⁷) → external engine (10⁷+).
- **Migration:** the `SearchIndex` interface (`index(events)`, `search(text, filters, k)`,
  `delete(keys)`, `rebuild()`) is stable; the backend swaps (see §5).

### Query Planner
- **Why:** different queries need different retrieval; hardcoding one strategy is the current
  ceiling. A city filter, a keyword, and "events by Google" are three different retrievals.
- **Responsibilities:** inspect the `SearchQuery` (+ consult the entity resolver/graph) and
  emit a **deterministic `QueryPlan`**: which retrievers to run, their params/K, the fusion
  policy, and the structured filters to push down.
- **Interactions:** the only decision-maker; the Retrieval Pipeline executes its plan.
- **Scalability:** a pure function — trivial.
- **Migration:** add a semantic branch later as one deterministic rule; no structural change.

### Retriever
- **Why:** a uniform contract over heterogeneous strategies so new ones drop in.
- **Responsibilities:** `retrieve(plan_step) -> list[Candidate]` where a `Candidate` is
  `(event_key, retrieval_score, source)`; each retriever returns a **bounded top-K**.
- **Interactions:** invoked by the pipeline per the plan; reads its backing store (index /
  graph / repo).
- **Scalability:** each retriever is index-bounded and independent → parallelizable.
- **Migration:** implementations — `FilterRetriever` (repo/index predicates), `KeywordRetriever`
  (FTS), `EntityRetriever` (graph), `SemanticRetriever` (future). New impl, no pipeline change.

### Hybrid Retriever
- **Why:** real queries want keyword **and** entity **and** (later) semantic recall together.
- **Responsibilities:** run the plan's retrievers (concurrently), **fuse** their candidate
  lists — **Reciprocal Rank Fusion** (rank-based, score-scale-agnostic) as the default, or a
  weighted union — dedupe by `event_key`, and bound the fused set (e.g. top 300).
- **Interactions:** composes `Retriever`s; hands the candidate set to Ranking.
- **Scalability:** fusion is O(sum of K); bounded regardless of catalog size.
- **Migration:** adding the Semantic Retriever = adding it to the fusion set — no rewrite.

### Filter Engine
- **Why:** structured constraints (city/category/date/free/active-upcoming) are orthogonal to
  text/semantic retrieval and must be applied efficiently, ideally pushed down.
- **Responsibilities:** translate `SearchQuery` constraints into predicates; apply as
  **push-down** into the index/repo query where possible, else as a post-filter on candidates.
- **Interactions:** used by every retriever (push-down) and by the pipeline (post-filter).
- **Scalability:** indexed predicates; the same predicates map to SQL / FTS / ES filters.
- **Migration:** predicate model is backend-agnostic.

### Search Cache
- **Why / status:** already built (3E) — query→results, TTL, invalidation, deterministic key,
  storage-independent. **Keep.**
- **Migration:** in-memory → Redis (drop-in `SearchCache` impl) for multi-instance + shared
  invalidation. Invalidation should be wired to ingestion (currently TTL-only) when
  `SearchService` is unfrozen to adopt it.

### Search Analytics (business)
- **Why:** understand and improve what users search for and where search fails.
- **Measures:** popular queries, **zero-result** searches (+ samples), retrieval size (avg
  candidates), popular categories/cities/topics. **CTR and ranking quality require a click
  signal from the frontend** (impression/click events) — define the interface now
  (`record_impression`, `record_click`), populate later; ranking quality then derives from
  CTR@k or manual judgments.
- **Migration:** in-memory counters → a store/warehouse; a read replica so analytics never
  contends with serving.

### Search Metrics (operational)
- **Why:** SLOs and observability — distinct from business analytics.
- **Measures:** latency **p50/p95/p99**, QPS, cache-hit rate, **per-retriever latency**,
  candidate-set sizes, empty-result rate, error rate.
- **Migration:** in-memory histograms → Prometheus/OpenTelemetry.

### Future Semantic Layer — interfaces only, no implementation
- **Why:** semantic ("events like X", conceptual matches) must be addable without rewriting.
- **Interfaces:** `Embedder.embed(text) -> vector`; `VectorIndex.upsert(key, vector)` +
  `search(vector, k, filters) -> list[Candidate]`; `SemanticRetriever(Retriever)`.
- **Interactions:** the Planner includes the Semantic Retriever only when embeddings exist
  **and** the query is free-text; the Hybrid Retriever fuses it in. Query embedding is derived
  from the keywords (lossy, given the frozen `SearchQuery`) — disclosed.
- **Migration:** implement later against pgvector / a vector store; **no interface here is
  built now.**

---

## 5. Search Index — the SQLite FTS5 decision

**Decision: YES — introduce SQLite FTS5 first, as a *separate* `SearchIndex` component.**

This **reverses the 3E "no"** — deliberately, and the reasons the "no" held then no longer
apply:
- In **3E**, adding FTS meant *modifying the frozen `SQLiteEventRepository`* (schema +
  triggers) and looked like throwaway before Postgres. Both were correct objections *then*.
- In **Phase 4**, FTS is a **separate component behind a `SearchIndex` interface** — its own
  FTS5 virtual table, populated from the catalog as a projection. **The Repository contract is
  untouched.** And it is **not throwaway**: the `SearchIndex` interface persists unchanged
  across the Postgres and external-engine migrations — only the implementation swaps.

**Why FTS5 first (not straight to an external engine):**
- **₹0, zero new infrastructure** — stdlib, same process; validates the entire retrieval
  pipeline + `SearchIndex` interface cheaply.
- **Massive, immediate win over `LIKE`:** indexed keyword search with **bm25 relevance**,
  tokenization, prefix/phrase queries — sub-second at 10⁵–10⁶ where `LIKE` falls off a cliff.
- It de-risks the interface: if the abstraction survives FTS5 → Postgres FTS → external, it's right.

**Migration path (interface stable throughout — no public-contract change):**

| Stage | Backend | When | Gains |
|---|---|---|---|
| now | **SQLite FTS5** | 10⁵–10⁶, ₹0 | bm25 keyword, sub-second, no infra |
| next | **Postgres FTS** (`tsvector`+GIN) | with the Postgres catalog migration | concurrent, integrated with the source of truth, partition-aware |
| scale | **Meilisearch / Typesense** | typo-tolerance, facets, instant-search UX | fast, developer-friendly, but a separate service to sync |
| heavy | **Elasticsearch / OpenSearch** | complex relevance, huge scale, aggregations | most powerful, heaviest ops |

Each swap implements the same `SearchIndex` interface and is fed by the same catalog
projection (outbox/rebuild). Retrievers, Planner, Ranking, and every public interface are
unchanged.

---

## 6. Query Planner — deterministic rules

A pure function `plan(query, entity_resolver) -> QueryPlan`. No randomness, no LLM.

```
filters   = structured predicates from {city, categories, date_from/to, free_only} + active+upcoming
retrievers = []
if query.keywords:
    if any keyword resolves to a known entity (org/community/series/venue):
        retrievers += EntityRetriever(entity, filters)      # "events by Google", "from GDG"
    retrievers += KeywordRetriever(keywords, filters)       # FTS over title/description
if not query.keywords:
    retrievers += FilterRetriever(filters, order=freshness) # city/category/date browse
if query is empty:
    retrievers += FilterRetriever(active+upcoming, order=freshness)   # browse
# future, gated deterministically:
if SEMANTIC_ENABLED and query.keywords:
    retrievers += SemanticRetriever(embed(keywords), filters)
fusion = RRF if len(retrievers) > 1 else passthrough
return QueryPlan(retrievers, fusion, filters)
```

- **keyword search** → KeywordRetriever (FTS). **city/category** → filters pushed into every
  retriever (or a FilterRetriever when no text). **entity search** → EntityRetriever when a
  keyword resolves to an entity. **hybrid** → multiple retrievers + RRF fusion. **semantic** →
  a future deterministic branch. The plan is fully determined by the `SearchQuery` + the
  (deterministic) entity resolver, so results are reproducible and testable.

---

## 7. Hybrid retrieval — interfaces for a future semantic engine (no implementation)

```
Candidate      = (event_key: str, score: float, source: str)
Retriever      : retrieve(step: PlanStep) -> list[Candidate]           # bounded top-K
HybridRetriever: retrieve(plan: QueryPlan) -> list[Candidate]          # run + RRF-fuse + dedupe + bound
Embedder       : embed(text: str) -> Sequence[float]                   # FUTURE
VectorIndex    : upsert(key, vector); search(vector, k, filters) -> list[Candidate]   # FUTURE
SearchIndex    : index(events); search(text, filters, k) -> list[Candidate]; delete(keys); rebuild()
```

Embeddings are **not implemented** — only the `Embedder`/`VectorIndex`/`SemanticRetriever`
interfaces exist so a semantic engine (pgvector, a vector DB) slots into the Hybrid Retriever
later **without touching** the Planner's structure, the other retrievers, Ranking, or any
public interface.

---

## 8. Analytics & metrics

| Signal | Now | Needs |
|---|---|---|
| popular queries | ✅ counter | — |
| zero-result searches | ✅ counter + samples | — |
| retrieval size (avg candidates) | ✅ | pipeline instrumentation |
| latency p50/p95/p99 | ✅ (metrics) | histograms |
| cache hit rate | ✅ | — |
| per-retriever latency | ✅ (metrics) | pipeline instrumentation |
| **CTR** | ❌ | a **click signal** from the frontend (impression/click events) — define interface now, populate later |
| **ranking quality** | ❌ | CTR@k or manual relevance judgments (needs the click signal or a judgment set) |

Business **Analytics** (what users want, where search fails) and operational **Metrics**
(latency/QPS/errors — SLOs) are kept separate: different owners, different stores, different
cadence.

---

## 9. Migration strategy (proposed sub-phases — for a later approval)

- **4A** — this document.
- **4B** — `SearchIndex` interface + **SQLite FTS5** impl; **Query Planner** + `Retriever`/
  `HybridRetriever`/`FilterRetriever`/`KeywordRetriever`/`EntityRetriever` (entity graph wired
  in); RRF fusion; **Search Metrics**; extend Analytics. All inside `DatabaseSearchProvider`.
  `SearchService`/API/frontend unchanged. Semantic = interfaces only.
- **4C** — **Postgres** catalog (behind the frozen Repository contract) + **Postgres FTS**
  `SearchIndex` impl; Redis `SearchCache`.
- **4D** — external index (Meilisearch/Typesense/ES) *if* facets/typo-tolerance/scale demand it.
- **Later** — **Semantic Layer** (pgvector/vector store) as a `SemanticRetriever`;
  **Personalization** layer.

Every step swaps an implementation behind an interface; **no public contract changes** at any
point.

---

## 10. Scalability analysis

| Subsystem | 10⁵ active | 10⁶ | 10⁷ (+ historical) |
|---|---|---|---|
| Structured filters | indexed SQL, sub-ms | Postgres indexes + partial indexes | partition by date; hot partition only |
| Keyword retrieval | **SQLite FTS5** bm25, sub-second | **Postgres FTS** GIN | external engine (Meili/Typesense/ES) |
| Entity retrieval | graph traversal, in-memory | persisted graph (SQL adjacency) | indexed graph / graph service |
| Semantic | — | pgvector ANN | dedicated vector store |
| Ranking | O(K) candidates | O(K) — unchanged | O(K) — unchanged (the point) |
| Catalog store | SQLite (single-writer) | **Postgres** (MVCC, replicas) | Postgres partitioned + read replicas |
| Cache | in-memory | **Redis** | Redis cluster / CDN edge |
| Analytics | in-memory | store | warehouse / replica |

The invariant across every column: **retrieval is index-bounded and ranking is O(K)** — total
catalog size never enters the hot-path cost. That is why the architecture scales.

---

## 11. Tradeoffs

- **SQLite FTS5**: +₹0, +bm25, +sub-second, +no infra; −single-node, −no typo-tolerance,
  −no facits/aggregations, −no semantic. Right *first* step, not the *last*.
- **Postgres FTS**: +concurrent, +integrated with source of truth, +partition-aware; −still
  weak typo-tolerance vs a dedicated engine.
- **Meilisearch/Typesense**: +typo-tolerance, +facets, +instant-search; −a separate service
  to run and keep in sync (two-sources-of-truth risk).
- **Elasticsearch**: +most powerful; −heaviest ops, overkill until very large.
- **Hybrid fusion (RRF)**: +combines strategies simply and score-scale-agnostically; −tuning
  which retrievers/weights per query is an ongoing quality effort.
- **Frozen `SearchQuery` + lost raw text**: +stability; −caps query richness (entity/semantic
  intent must be re-derived from keywords) — the deepest architectural constraint, resolved
  only if `SearchService`/`QueryParser` are eventually unfrozen or a richer query object is added.

---

## 12. Recommendations

1. **Build 4B first and stop there for a while.** `SearchIndex` + **SQLite FTS5** + Query
   Planner + Retriever/Hybrid/Filter abstractions + wiring the **entity graph as a Retriever**
   is the highest value-per-effort, at ₹0, and validates every interface. It kills the `LIKE`
   cliff and unlocks entity search **without changing SearchService**.
2. **Introduce the abstractions even where only one impl exists** (e.g., a Planner that today
   emits keyword+structured+entity) — so Postgres FTS, external engines, and semantic drop in
   later with zero churn.
3. **Define semantic interfaces, implement nothing.** Gate them behind a deterministic planner
   flag.
4. **Add operational Search Metrics** alongside business Analytics from day one of 4B.
5. **Plan the Postgres catalog migration (4C)** as the real scale step — it removes the
   single-writer lock and brings native FTS; do it before, not after, the 10⁶ wall.
6. **Make `score_source` data-driven** from the Provider State Store's health (the data now
   exists) — retiring hardcoded per-provider quality.

---

## 13. Constraints honored

Untouched, by design: **`SearchService` interface, `QueryParser` interface, API routes,
frontend, Repository public contracts, provider interfaces.** All new machinery lives inside
`DatabaseSearchProvider` (behind the `EventProvider` seam) and the new `SearchIndex` /
retrieval components. This is the architecture only — **nothing is implemented; awaiting
approval before Phase 4B.**
```
