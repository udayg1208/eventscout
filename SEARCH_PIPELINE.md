# Search Pipeline

The complete read path, end to end. No network, no providers, no fetching — everything
comes from the Event catalog.

```
Natural-language query
      │
      ▼   QueryParser (Gemini → validated, or deterministic keyword fallback)
Structured SearchQuery
      │
      ▼   DatabaseSearchProvider
[ SearchCache lookup ] ── hit ──► ranked results (record analytics: cache_hit)
      │ miss
      ▼   to_criteria(): SearchQuery → SearchCriteria (active + upcoming + filters + limit)
Repository.search()  ── bounded candidate window, keyset order, filters pushed into SQL
      │
      ▼   Ranking (deterministic weighted scorer, over the candidate window)
Ranked results  ──►  SearchCache.set  ──►  record analytics  ──►  Response
```

## Stage by stage

1. **QueryParser** (unchanged) turns natural language into a `SearchQuery`. Gemini understands
   the query and never fetches or invents events; a deterministic keyword parser is the
   validated fallback. (In tests/offline the keyword parser is used directly.)

2. **SearchCache** (storage-independent, TTL, invalidation-aware). A hit returns immediately
   (an empty list is a valid cached value). Keyed by a canonical, order-independent
   serialization of the `SearchQuery`, so equal queries collide. Optional — `cache=None`
   always reads the repository.

3. **`to_criteria`** maps the frozen `SearchQuery` to a storage `SearchCriteria`, always
   scoping to **ACTIVE + upcoming** events and attaching the candidate `limit`. Supported
   filters: category, city, free/paid, date range, keywords. (Topic/organizer/online await
   the Phase-5 model — see REPOSITORY_SEARCH.md.)

4. **`Repository.search`** executes the filters **in SQL** over indexed columns and returns a
   **bounded, keyset-ordered** candidate window (`(start_date, key)`, never OFFSET, never the
   whole catalog).

5. **Ranking** (unchanged, deterministic) re-orders the candidate window with the weighted
   scorer: 40% relevance · 20% freshness · 15% location · 10% source quality · 10% popularity ·
   5% completeness. AI classification is already baked into each event's stored category, so
   category relevance reflects it. Deterministic tie-break: sooner date, then title.

6. **Response** — a ranked `list[Event]`, returned through the unchanged `SearchService` and
   HTTP API. The frontend paginates client-side over this list.

## Ranking flow (why it's still faithful)

The stored event already carries its **classified category** and **canonical city** (applied
at ingestion), so ranking sees exactly what the old read-path composite produced — just
sourced from the DB instead of a live fetch. `test_ranking_is_applied_and_matches_ranker`
asserts the provider's output equals `rank()` applied to the retrieved candidates, and
`test_ranking_is_deterministic` asserts stable ordering across identical searches.

## Caching

- **Query cache**: `SearchQuery` → ranked results, TTL, deterministic key.
- **Invalidation**: `provider.invalidate()` clears the cache — call it after an ingestion run
  mutates the catalog (freshness without waiting for TTL).
- **Optional & storage-independent**: in-memory today; Redis is a drop-in `SearchCache`
  implementation for multi-instance deployments.
- **Interaction with `SearchService`**: `SearchService` has its own pre-existing in-memory
  results-cache (frozen). Until it's unfrozen to adopt this abstraction, it sits above and
  absorbs exact repeats within its TTL — so DB-layer cache/analytics undercount those. Known,
  disclosed, benign (both are short-TTL).

## Analytics (platform-level; no user tracking)

Recorded on every search that reaches the read-path provider: total searches, latency,
result counts, cache hits, empty searches, and popularity histograms for categories, cities,
and topics (keywords). Exposed via `provider.analytics.snapshot()`. Live sample (7 searches):
`avg_latency_ms ≈ 0.97`, `popular_categories: [('ai', 3)]`, `popular_cities: [('bangalore', 2)]`.
