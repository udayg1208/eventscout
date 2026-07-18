# Repository Search

How the repository-backed search engine executes, scales, and where it will evolve. Code:
`backend/app/search/db_provider.py` (read path) + `backend/app/storage/sqlite_repository.py`
(the frozen Repository v2 it reads through).

## Two-phase: retrieve, then rank

Keyset pagination needs a **stable DB order** (`(start_date, key)`); ranking wants **score
order**. They can't be the same SQL order, so search is two-phase:

1. **Retrieve (in SQL):** `Repository.search(criteria)` applies all filters over indexed
   columns and returns a **bounded candidate window** — the soonest-upcoming matching events,
   `LIMIT candidate_limit` (default 500), ordered by `(start_date, key)` via **keyset** (never
   OFFSET). Memory is bounded; the full catalog is never loaded.
2. **Rank (in memory):** the deterministic scorer re-orders that window.

**Consequence (honest):** for **selective** queries (a city, a category, keywords) the whole
matching set fits in the window → **exact ranking**. For a **very broad** query (no filters
over millions of rows) the window is the soonest 500 → ranking is over a *freshness-biased
candidate set*, not the global set. That's the right trade for an upcoming-events product
(broad queries are browse; soonest-first is the sensible candidate pool), and it keeps search
O(candidate_limit), not O(catalog).

## Filtering — pushed into SQL

| Filter | Supported | Where |
|---|---|---|
| category | ✅ | `category IN (...)` (indexed) |
| city | ✅ | `lower(city) = lower(?)` (indexed) |
| free/paid | ✅ | `is_free = 1` |
| date range | ✅ | `COALESCE(end_date,start_date) >= ? AND start_date <= ?` |
| keywords | ✅ | `LIKE` on title/description (see FTS below) |
| active + upcoming | ✅ (always) | `status='active' AND COALESCE(end_date,start_date) >= today` |
| **topic** | ❌ | no field on `Event`/`SearchQuery` (Phase-5 Opportunity model) |
| **organizer** | ❌ | no field on `Event`/`SearchQuery` (Phase-5) |
| **online/offline** | ⚠️ | data exists (`Event.is_online`) but no query field (needs SearchQuery/parser unfreeze) |

## Indexing strategy

The frozen repo indexes: `(status, start_date, key)` (the filtered keyset read),
`(start_date, key)`, `city`, `category`. These serve the current filters well at 10³–10⁴
rows. At millions (Postgres, Phase 4): composite/partial indexes per common filter
combination, a GIN index for full-text, and **partitioning by `start_date`** so the hot
(upcoming) partition stays small and the archive partitions are rarely touched.

## Pagination

**Keyset only — no OFFSET.** The Repository exposes `Page{items, next_cursor}` with an opaque
`(start_date, key)` cursor (built in Phase 3B, tested there). Search uses it internally to
build the candidate window. The ranked *result* is a bounded list (the frozen `SearchService`
returns a list; the frontend paginates client-side). A future cursor-paginated **browse**
endpoint (date-ordered, unranked) can expose keyset pagination directly to clients without
OFFSET — the repository already supports it.

## Full-text search — why `LIKE` now, real FTS later

- **Now:** `LIKE '%kw%'`. Correct; adequate and fast at current scale. A full scan, yes — but
  over thousands of rows that's sub-millisecond (verified: keyword search ~1.6 ms over 102).
- **Not SQLite FTS5 now:** it requires modifying the **frozen** Repository v2 (FTS virtual
  table + sync triggers) and is throwaway before the Postgres migration. Adding it isn't a
  defect fix, so the freeze holds.
- **Later (Phase 4):** **Postgres full-text** (`tsvector` + GIN) gives indexed, ranked,
  language-aware keyword search natively; or a dedicated **search index projection**
  (Meilisearch/Typesense/pgvector) fed from the catalog via an outbox for typo-tolerance,
  facets, and semantic search. That's where FTS belongs — with the storage layer, not bolted
  onto a soon-to-be-replaced SQLite repo.

## Latency (measured, live, 102 events)

`everything` 1.97 ms · `AI category` 0.53 ms · `in Bangalore` 0.82 ms · `keyword 'ai'` 1.63 ms.
Versus the old live-fetch path's ~2–10 s cold. Cache hits are ~0 ms.

## What changes at scale

- **1M events:** still one SQLite/Postgres node. `LIKE` becomes the weak spot on broad keyword
  queries → move keyword search to Postgres FTS. Candidate window + keyset keep the hot path
  O(limit). Add partial indexes for common filter combos.
- **10M events:** Postgres, **partitioned by date**; the archive tier must be truly offloaded so
  the upcoming partition (the only thing search touches) stays small. Full-text on a GIN index
  is mandatory. Two-phase retrieve-then-rank is essential — never score more than the window.
- **100M events:** search runs off a **dedicated index** (Meilisearch/Typesense or pg
  FTS+pgvector) that is a *projection* of the catalog (outbox/CDC), not the OLTP store;
  retrieval returns top-K, ranking (possibly learned) re-ranks K; the OLTP catalog is the
  source of truth but is not on the query hot path. Analytics move to a read replica/warehouse.
