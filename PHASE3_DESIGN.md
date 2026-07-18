# Phase 3 — Massive Event Ingestion (Design)

**Status: APPROVED (2026-07-14) with the modifications in §0. Building in sub-phases.**

## 0. Approved direction (governing principles)

1. **Storage-agnostic repository abstraction is the load-bearing design.** SQLite is
   simply the *first* implementation behind `EventRepository`. No SQLite-specific
   assumptions leak into application logic; swapping in Postgres/Supabase later changes
   **no** application code — only which implementation is constructed. Postgres is not
   started until the abstraction is proven on SQLite.
2. **Database is the single source of truth.** Providers become **ingestion sources
   only**. Search reads **only** from the repository.
3. **Frozen contracts hold:** `Event`, `SearchQuery`, `QueryParser`, `EventProvider`
   interface, `SearchService` public interface, the HTTP API, and the frontend are
   untouched.
4. **Providers declare their own operational metadata** (refresh interval, timeout,
   retry policy, priority, rate limit, incremental-sync capability). The scheduler reads
   this metadata and adapts automatically — **no per-provider behavior is hardcoded** in
   the scheduler. This is what lets the system grow from ~100 events today to 50,000+
   without changing the architecture.

### Implementation order (approved)

- **3A** — Repository interface + SQLite implementation + event persistence + read/write tests.
- **3B** — Background scheduler + incremental provider sync + event expiration + retry/backoff + provider-health metrics (driven by per-provider metadata).
- **3C** — DB-backed search (`DatabaseSearchProvider`); existing API + frontend keep working unchanged.
- **3D** — Analytics: growth metrics, freshness metrics, provider-health dashboard.
- **3E** — Massive provider expansion (toward 50–100+ providers).

Postgres/Supabase is a later implementation of the *same* interface, added only once 3A–3D prove the abstraction.

## 1. Review of the current provider system

Today the app is an excellent *on-demand search* engine, but not an *ingestion platform*.

**How it works now:** `SearchService.search(text)` → parse → `get_provider().search(query)`
→ `CompositeProvider` fans out to 7 providers **concurrently**, each with a 30–60 min
in-memory `TTLCache` → merge → canonicalize city → classify → filter → dedup → rank →
return. Nothing is persisted.

**Strengths (keep these):** clean seams (`EventProvider`, `QueryParser`); strong
normalization / classification / dedup / ranking intelligence; resilient (isolated
failures, fallbacks); ₹0; stateless.

**Why it can't reach the vision (50 providers / 10k live events / real-time):**

| Limitation | Consequence at scale |
|---|---|
| Fetch is triggered by the user search | A cold search fans out to *all* providers and waits for the slowest (GDG ~10 s). At 50 providers this is seconds–minutes **per cold query**. |
| Data lives in per-process in-memory caches | Restart/redeploy = total data loss + cold re-fetch. Can't accumulate 10k events; each provider only holds its latest fetch. |
| No background refresh | Freshness = cache TTL; the *user* pays the fetch cost. |
| No persistence / source of truth | No history, no growth tracking, no cross-instance sharing. |
| No continuous health/observability | Analytics samples on demand only. |
| No expiration, no incremental writes | Past events linger; every cache-miss re-fetches the whole source. |

**Conclusion:** the search path is good and should stay; the *data model* must invert.

## 2. The inversion

- **Before:** providers = data source, fetched at search time, cached in memory.
- **After:** **the database is the source of truth.** Providers become **ingestion
  sources** run on schedules by a **background scheduler**; they write normalized,
  classified, deduped events into the DB. **Search reads only from the DB.**

This is the single most important idea: **decouple ingestion (write path, background)
from search (read path, one indexed DB query).**

## 3. New components

```
app/
  storage/        # NEW — persistence (source of truth)
    repository.py     EventRepository interface (upsert/query/expire/health/snapshot)
    sqlite_repo.py    SQLite backend (dev/tests, stdlib sqlite3)
    postgres_repo.py  Supabase/Postgres backend (prod, durable, shared)  [3f]
    schema.sql        events / provider_health / ingestion_snapshots
  ingestion/      # NEW — write path
    plugins.py        Plugin registry: each entry pairs a provider with its declared
                      metadata (refresh interval, timeout, retry policy, priority,
                      rate limit, supports_incremental). The scheduler reads this —
                      no provider behavior is hardcoded in the scheduler.
    runner.py         Per-provider: rate-limit -> retry/backoff -> fetch ->
                      normalize_city + classify + hash -> dedup -> upsert -> health
    scheduler.py      Triggers plugins per interval tier; runs expiration job
    ratelimit.py      Per-provider token bucket / min-interval
  providers/      # UNCHANGED — reused as ingestion sources via search(SearchQuery())
  search/         # NEW thin adapter
    db_provider.py    DatabaseSearchProvider(EventProvider): query DB -> rank -> Events
```

**Key reuse:** ingestion calls each existing provider's `search(SearchQuery())` (empty
query = "give me everything"), then reuses `normalize_city`, `classify_category`, and
`deduplicate` — all existing code. **Providers are not modified.**

**Intelligence relocates cleanly:**
- **Ingestion time (write):** city canonicalization, classification, cross-source dedup.
- **Search time (read):** filtering + ranking (existing `ranking.rank`).
The DB stores the *classified category* and *canonical city*, and is *dedup-free by
construction*.

## 4. Data flow

```
[50+ provider plugins] --15m/1h/daily/weekly, per plugin-->
      | rate-limit gate + retry/exponential-backoff
      v
[runner] provider.search(SearchQuery())  ->  normalize_city + classify + content_hash
      v
[dedup + UPSERT]  dedup_key match -> choose_best_event -> INSERT new / UPDATE changed-hash / touch unchanged
      v
+============================ DATABASE (source of truth) ============================+
|  events (indexed: start_date, city, category, is_active)                          |
|  provider_health        ingestion_snapshots (growth over time)                    |
+===================================================================================+
      ^  expiration job: end_date < now -> is_active=false            |  query(filters + upcoming + active)
      |                                                               v
                                              [DatabaseSearchProvider.search(query)] -> rank()
                                                               v
                    SearchService -> POST /search -> Next.js frontend   (ALL UNCHANGED)
```

## 5. How each requirement is satisfied

| # | Requirement | Design |
|---|---|---|
| 1 | 50+ independent providers | Plugin registry; each plugin isolated + independently testable; adding one = one registry entry |
| 2 | 5k–10k live events | DB with indexes (Supabase free = 500 MB ≈ 100k+ events); search reads a filtered slice |
| 3 | Automatic refreshing | Scheduler triggers ingestion in the background |
| 4 | Per-provider intervals | Interval tier on each plugin: 15 m / 1 h / daily / weekly |
| 5 | Health monitoring | `provider_health` table: last_success, failure_count, avg_latency, success_rate, updated every run |
| 6 | Auto expiration | Expiration job sets `is_active=false` where `end_date < now`; search filters to active+upcoming |
| 7 | Incremental updates | `content_hash` per event → insert new / update changed / touch unchanged; source-side date windows where supported |
| 8 | Background scheduler | `scheduler.py` (APScheduler or asyncio loop); or cron-driven one-shot per tier (see risks) |
| 9 | Persistent DB = source of truth | `events` table is canonical; providers demoted to ingestion sources |
| 10 | Provider plugins, isolated + testable | Registry wraps existing `EventProvider`s + config; each tested via `MockTransport` as today |
| 11 | Retry + exponential backoff | `runner` wraps each fetch (e.g. 3 attempts, 2^n + jitter) |
| 12 | Rate limiting per provider | `ratelimit.py` token bucket / min-interval keyed by provider |
| 13 | Full observability | Analytics from DB: coverage, freshness, update frequency, failures, dup rate, growth-over-time (snapshots) |
| 14 | Zero changes to SearchService/QueryParser/frontend/API | Only `get_provider()` (the swap seam) returns `DatabaseSearchProvider`; `EventProvider` interface preserved |
| 15 | Existing providers unchanged | Reused verbatim as ingestion sources via `search(SearchQuery())` |

## 6. Why this scales to tens of thousands

1. **Search cost is O(1) in provider count** — one indexed DB query (ms), not N network
   fetches. This is the core scalability win.
2. **Ingestion is background, parallel, scheduled, incremental** — no user ever waits;
   hash-diff avoids re-writing unchanged rows.
3. **DB handles 10k rows trivially** with indexes; Supabase free tier has ample headroom.
4. **Dedup at write time** → search never pays dedup cost and returns canonical data.
5. **Read scales horizontally** (many web instances, one shared DB); **expiration keeps
   the working set bounded** (only upcoming events).

## 7. Risks and mitigations

1. **Scheduler + persistence on ₹0.** Render free web dynos sleep when idle and have
   ephemeral disks (SQLite would be wiped; an in-process scheduler wouldn't run
   reliably). **Mitigation:** use **Supabase Postgres (free, durable, shared)** as the
   DB and drive ingestion via **cron** (Render Cron Jobs / GitHub Actions scheduled
   workflow / Supabase scheduled function) invoking a one-shot ingest per tier. *This is
   the primary deployment decision.*
2. **New dependencies** (a DB driver). **Mitigation:** `EventRepository` abstraction;
   SQLite (stdlib) for dev/tests, Postgres for prod — thin and swappable.
3. **Provider ToS / rate limits at 50 sources.** **Mitigation:** per-provider limits,
   conservative intervals, backoff, honor ToS/robots.
4. **"Incremental fetch" is source-limited** (few sources have delta APIs).
   **Mitigation:** hash-diff on write (cheap); longer intervals for static sources;
   source-side windowing only where supported.
5. **Empty/failed fetch must not wipe data.** **Mitigation:** never deactivate on a
   failed/empty run — only after *N consecutive confirmed-absent* successful runs
   (extends the existing "don't cache empty/failed" rule).
6. **Cross-source dedup precision** grows in importance with more real cross-posts.
   **Mitigation:** the hardened, gated threshold from Phase 2 #3; monitor dup rate.
7. **DB-as-truth = last-snapshot freshness**, not live. **Mitigation:** 15-min tier for
   fast sources; acceptable since events are announced days/weeks ahead.
8. **Cutover:** an empty DB = empty search. **Mitigation:** run one ingestion pass to
   warm the DB *before* flipping `get_provider()`; optional live-provider fallback while
   the DB warms.

## 8. Implementation sub-phases (approved order — small, tested, reviewable)

- **3A** `EventRepository` (storage-agnostic ABC) + SQLite implementation + event persistence (incremental upsert via `content_hash`) + read/write tests. *(this sub-phase)*
- **3B** Ingestion runner + background scheduler driven by **per-provider metadata**; incremental sync; retry/exponential-backoff; per-provider rate limit; event expiration; provider-health metrics. Reuses existing providers verbatim + `dedup`/`classify`/`normalize_city`.
- **3C** `DatabaseSearchProvider(EventProvider)`; flip `get_provider()`; SearchService / HTTP API / frontend keep working unchanged (warm the DB first).
- **3D** Analytics from the DB: coverage, freshness, growth-over-time snapshots, provider-health dashboard.
- **3E** Grow toward 50–100+ providers (new plugins), guided by the Gap Analysis.

**Postgres/Supabase** is added later as a second implementation of the *same*
`EventRepository` interface — only after 3A–3D prove the abstraction on SQLite. No
application logic changes when it lands.

## 9. Frozen-contract preservation
`Event`, `SearchQuery`, `QueryParser`, `EventProvider` interface, `SearchService` public
interface, HTTP API, and frontend are **untouched**. The only change to the search path
is what `get_provider()` returns (its documented job — the swap point). Existing provider
code is reused verbatim.
```
