# Phase 3E — Search Architecture (Repository Cutover)

The largest architectural transition in the project: **search no longer fetches live
providers.** The provider ecosystem feeds the Event catalog through ingestion; every
search is served entirely from the Repository. This is the Google-News inversion.

## Old architecture (removed from the search path)

```
User → SearchService → CompositeProvider → fan out to 7 live providers (network!)
     → merge → city-normalize → classify → dedup → rank → User
```

Every search paid the full fetch cost (~2–10 s cold), depended on provider availability,
and did normalize/classify/dedup **at read time**.

## New architecture (Phase 3E)

```
WRITE PATH (background):  Providers → Scheduler → Ingestion Runner
                          → normalize + classify + dedup → Repository.bulk_upsert

READ PATH  (per search):  User → SearchService → QueryParser → DatabaseSearchProvider
                          → Repository.search (bounded, keyset, in SQL) → Ranking → User
```

Search touches **no provider and no network** — proven live: with the engine stopped, and
even with a search provider that has zero provider ecosystem, searches return in ~1–2 ms;
after a restart over the durable catalog, they still work. The application is now
independent of live provider availability.

## What changed — exactly

| Component | Before | After |
|---|---|---|
| `get_provider()` | `CompositeProvider` (live fan-out) | `DatabaseSearchProvider` (reads Repository) |
| `SearchService` | unchanged | **unchanged** (same public interface) |
| `QueryParser` | unchanged | **unchanged** |
| Ranking | inside `CompositeProvider.search` | inside `DatabaseSearchProvider.search` (same code) |
| normalize / classify / dedup | read path (per search) | **write path** (ingestion, Phase 3C) |
| HTTP API / frontend | unchanged | **unchanged** |

The cutover is a single seam-swap: `get_provider()` returns the catalog-backed provider.
Because that provider implements the frozen `EventProvider` interface, everything above it
is untouched.

## New read-path components (`app/search/`)

- **`DatabaseSearchProvider`** — translates `SearchQuery` → `SearchCriteria`, retrieves a
  bounded candidate window from the Repository, ranks it, caches, records analytics.
- **`SearchCache`** — storage-independent, TTL, invalidation-aware query cache
  (`InMemorySearchCache` now; Redis-ready).
- **`SearchAnalytics`** — platform-level metrics (volume, latency, result counts, cache
  hits, empty searches, popular categories/cities/topics). No user tracking.
- **`app/catalog.py`** — `get_repository()` / `get_state_store()` singletons so the write
  and read paths share one source of truth.

## CompositeProvider disposition — **deprecated, not deleted**

It's removed from `get_provider()` and marked deprecated, but remains a valid
`EventProvider` for tests/reference and as a possible manual catalog warm-up tool. Deleting
it would churn tests for no gain and remove a rollback path; its intelligence already moved
to ingestion.

## Full-text search decision — **not now**

SQLite FTS5 is **not** introduced in this phase. Reasons:
1. It would require modifying the **frozen** `SQLiteEventRepository` (FTS virtual table +
   sync triggers) — not justified as a defect fix.
2. `LIKE`-based keyword matching is correct and fast at today's scale (10³–10⁴ rows).
3. The real scale answer is **Postgres full-text (`tsvector`/GIN) in Phase 4**, or a
   dedicated search-index projection — bolting SQLite FTS5 onto a frozen repo now is
   throwaway work before that migration.

So: keep `LIKE`, and introduce real FTS with the storage migration. (Details in
[REPOSITORY_SEARCH.md](REPOSITORY_SEARCH.md).)

## Known gap — filters the frozen models can't express

`SearchQuery`/`Event` (frozen) support **category, city, free/paid, date, keywords**.
**Topic** and **organizer** are not fields on either model (they arrive with the Phase-5
Opportunity generalization); **online/offline** data exists on `Event.is_online` but there's
no query field for it. These are documented, not faked — they land when the models generalize.

## Migration strategy (how the cutover stays safe)

1. Ingestion (3C/3D) populates the catalog in the background — **warm the catalog first**.
2. Flip `get_provider()` to the `DatabaseSearchProvider` (the only search-path change).
3. The frozen `SearchService` results-cache still sits above (TTL) — a redundant layer now;
   it's replaced by the invalidation-aware `SearchCache` when `SearchService` is unfrozen.
4. Rollback is a one-line revert of `get_provider()` (CompositeProvider still works).
