# Phase 3B+ Architecture Review — Opportunity Intelligence Platform

**Status: REVIEW / REDESIGN. No implementation until approved.**
**Author framing:** designing for a 5-year horizon — 500–1000+ providers, 50k–2M+ active
opportunities, continuous ingestion, near-real-time, thousands of searches/hour, many
opportunity *types*. Optimizing for **clean seams now, heavy implementations only when
metrics demand them.**

---

## 0. What actually changes going from MVP → platform

The MVP assumption was "a search engine over events." The platform assumption is "a
continuously-ingesting system of record for *opportunities*, projected into a search
experience." Three consequences drive everything below:

1. **The write path becomes the hard part**, not the read path. 1000 providers writing
   continuously is where the engineering is.
2. **Nothing may materialize the whole dataset in memory** — not dedup, not ranking, not
   analytics, not `all()`. Every full-set operation must stream or push down to the store.
3. **The record is no longer an Event.** Dates, category, and cost are all event-shaped
   assumptions that break for scholarships/grants/fellowships/internships.

The current repository *abstraction* (an interface the app depends on, backend swappable)
is correct and approved. The current *interface surface* is an MVP surface. This review
redesigns that surface **before** ingestion is written against it.

---

## 1. Repository Layer

### Verdict: the abstraction is right; the interface is insufficient. Redesign now.

Scored against the requirements:

| Requirement | Today (3A) | Gap |
|---|---|---|
| Millions of rows | `all()` returns `list` | **Footgun** — loads everything into RAM. Must go. |
| Bulk writes | row-by-row SELECT+INSERT in a loop | O(n) round-trips; no set-based upsert |
| Bulk updates | none (row-by-row) | need set-based deactivate/retag/expire |
| Pagination | `limit` only | **no offset/cursor** — can't page |
| Cursor iteration | none | need streaming `iterate()` for ingestion/analytics |
| Incremental sync checkpoints | none | providers with delta APIs have nowhere to store a watermark |
| Provider sync metadata | none | no per-provider run/health/next-run state |
| Event versioning | overwrite-on-change | no `version`, no change history |
| Soft delete | `is_active` boolean | conflates ended / withdrawn / archived |
| Archive strategy | none | hot table grows unbounded; indexes bloat |

**None of these are supported without interface change.** Per your instruction, the
interfaces are redesigned here, before implementation.

### Redesign — split one God-interface into three cohesive ports

A single repository that does CRUD + bulk + pagination + iteration + sync-state + health
+ archive is a God object. Split by *reason to change*:

```
OpportunityRepository   — the opportunity records (read/write/query/iterate/archive)
ProviderStateStore      — per-provider sync checkpoints + health/runtime state
(ArchiveStore)          — cold storage for ended/old records (can start as a table)
```

**`OpportunityRepository` (async ABC) — design sketch, not implementation:**

```
# Reads
search(criteria) -> Page[StoredOpportunity]          # keyset pagination, not offset
get(key) -> StoredOpportunity | None
get_many(keys) -> dict[str, StoredOpportunity]       # bulk candidate lookup (dedup)
find_candidates(*, on_date, city) -> list[...]       # dedup blocking, DB-side
iterate(criteria, *, batch_size) -> AsyncIterator[StoredOpportunity]   # streaming, bounded
count(criteria) -> int                               # optional/estimated at scale

# Writes (set-based)
bulk_upsert(records) -> UpsertResult                 # INSERT ... ON CONFLICT DO UPDATE
bulk_set_status(keys, status, *, reason) -> int
expire_ended(*, today) -> int
archive_before(*, cutoff) -> int

close()
```

Key changes vs 3A:
- **`search` returns `Page[T]`** = `{items, next_cursor, total?}`. **Keyset (cursor)
  pagination**, ordered by a stable tuple e.g. `(start_date, key)`; `WHERE (start_date,
  key) > cursor`. Offset pagination is O(offset) and dies at deep pages — banned.
- **`iterate()` replaces `all()`.** Streaming async generator, fixed memory. `all()` is
  deprecated/removed.
- **`bulk_upsert`** is set-based (native `ON CONFLICT`), chunked internally. Trade-off:
  exact inserted/updated/unchanged counts are cheap row-by-row but harder set-based;
  accept **aggregate** counts at scale (RETURNING on Postgres, `changes()` deltas on
  SQLite) — precise per-row classification is not worth O(n) SELECTs at 2M.
- **Lifecycle as an enum, not a boolean.** `status ∈ {active, expired, withdrawn,
  archived}` + `deactivated_at` + `deactivation_reason`. Distinguishes "event ended"
  from "source removed it" from "we archived it." Search defaults to `active`.
- **Versioning:** a `version: int` bumped on content change + `updated_at`. Full change
  history (a `revisions` append-only table + `history(key)`) is **reserved, not built** —
  the interface leaves room; we enable it only if a "what changed" feature needs it.
- **Archival:** `archive_before(cutoff)` moves cold rows out of the hot table (a separate
  table now; a partition or separate store under Postgres later). Keeps the hot index small.

**`ProviderStateStore` (async ABC):**

```
get_sync_state(provider) -> SyncState | None         # {last_synced_at, cursor, watermark}
save_sync_state(provider, state)
record_run(provider, RunReport)                      # success/failure, latency, counts
get_health(provider) -> ProviderHealth | None
list_health() -> list[ProviderHealth]
due_providers(*, now, limit) -> list[str]            # persisted next_run_at drives scheduling
```

This is what makes the scheduler restart-safe and metadata-driven (§2), and gives
delta-capable providers a place to store checkpoints (§3).

**Why redesign now:** 3C (ingestion) will call `bulk_upsert`, `find_candidates`,
`save_sync_state`, `record_run`; 3E (search) will call `search`→`Page`. If those bind to
the 3A surface, we rewrite them later. Cheap now, expensive after.

---

## 2. Scheduler Architecture (built for 1000 providers)

### Principle: separate scheduling POLICY from execution MECHANISM.

- **Policy** (when/what/priority/backoff/circuit) = pure, metadata-driven, testable.
- **Mechanism** (in-process pool now → durable queue later) = swappable behind a
  `Dispatcher` seam.

This is how we design for 1000 providers without building Celery today.

### Provider metadata: declared (static) vs runtime (computed) — a critical distinction

Your list mixed the two. They must be separated: declared metadata lives in code with the
plugin; runtime state lives in `ProviderStateStore`.

**Declared (in the plugin, static):**

| Field | Purpose |
|---|---|
| `id` / `name` | stable identity |
| `opportunity_types` | what it produces (event, scholarship, …) |
| `refresh_interval` | base cadence (duration, not a fixed tier) |
| `timeout` | per-fetch wall-clock cap |
| `retry_policy` | max_attempts + backoff base/factor/jitter + retryable errors |
| `rate_limit` | token-bucket (req / interval) — matters when paginating |
| `concurrency_limit` | max simultaneous in-flight requests to *this* source |
| `priority` | scheduling weight / ordering |
| `supports_incremental` | can fetch "changed since checkpoint"? |
| `supports_pagination` | pages? (drives runner loop + fan-out) |
| `supports_delta` | can report deletions, not just upserts? |
| `expected_daily_volume` | capacity planning + anomaly detection (10× or 0× ⇒ alarm) |
| `circuit_breaker` | failure threshold, open duration, half-open probes |

**Runtime (computed, stored — NOT declared):** `health_score`, `next_run_at`,
`last_run_at`, `last_success_at`, `consecutive_failures`, `circuit_state`, rolling latency.

### Scheduler design (evolutionary)

**Now (metadata-driven, in-process, restart-safe):**
```
tick (cron/heartbeat) ->
  due = ProviderStateStore.due_providers(now)          # persisted next_run_at, not in-RAM timers
  for provider in priority_order(due):
    dispatch(provider)  via bounded worker pool         # global asyncio.Semaphore(N)
      -> runner respects: circuit_state, rate_limit, concurrency_limit, timeout, retry_policy
      -> record_run(...) updates health + computes next_run_at (+ jitter)
```
- **Restart-safe:** schedule lives in the DB (`next_run_at`), not in-process timers, so a
  sleeping/restarting Render dyno doesn't lose the schedule. A cron/heartbeat drives ticks.
- **Anti-stampede:** jitter on `next_run_at`; never align all daily jobs to 00:00.
- **Two-level concurrency:** global semaphore (total in-flight providers) **and**
  per-provider `concurrency_limit` (pagination fan-out). Per-provider token-bucket rate limit.
- **Circuit breaker per provider:** K consecutive failures ⇒ open (skip until cooldown) ⇒
  half-open probe. Stops us wasting the run budget hammering a dead source.
- **Priority-weighted fairness:** high-volume/important sources run more often and first,
  without starving the long tail.

**Later (scale):** swap `dispatch()` from the in-process pool to a **durable task queue**
(Arq/Celery + managed Redis) with horizontal workers. The *policy* code is unchanged
because it only calls the `Dispatcher` seam. This is the 1000-provider / near-real-time
answer, adopted when metrics justify the Redis + worker cost — not before.

---

## 3. Ingestion Pipeline

### Your proposed order
`Provider → Normalize → AI Classification → Enrichment → Dedup → Repository → Index`

### Revised order (and why it must change)

```
SYNCHRONOUS  (per provider run — fast, must-not-lose, idempotent)
  1. Fetch            rate-limit · retry/backoff · timeout · pagination · delta-since-checkpoint
  2. Normalize/Validate   provider shape -> canonical Opportunity; city/date/url/price; drop malformed
  3. Classify (cheap)     deterministic type/category from existing fields (no LLM in hot path)
  4. Dedup vs DB          identity by key + fuzzy candidate lookup FROM THE REPOSITORY (blocked)
  5. Bulk upsert          persist canonical record (+ cluster_id, version, content_hash)
  6. Checkpoint + health  save_sync_state · record_run

ASYNCHRONOUS  (decoupled workers — best-effort, idempotent, updates DB + index)
  7. Enrichment       tags · geocode · embeddings · quality score · LLM re-classification
  8. Index/Project    update search index from the DB (outbox/CDC or periodic reindex)
```

**Why the order changed — three structural corrections:**

1. **Dedup must run against the DATABASE, not just the current batch.** A cross-source
   duplicate was probably ingested by *another* provider yesterday. Your linear pipeline
   dedups the in-flight batch only and would let cross-run duplicates through. So dedup
   sits **after normalize/classify but reads from the repository** (`find_candidates(on_date,
   city)`), blocked so it's bounded — never O(n²) over 2M rows. A stored `cluster_id`
   makes duplicate collapse deterministic and idempotent across runs.

2. **Enrichment moves AFTER persist, and off the hot path.** Enrichment (LLM,
   geocoding, embeddings) is slow, external, and failure-prone. Blocking ingestion on it
   destroys throughput and means a flaky geocoder can stall the whole platform. Persist the
   canonical record *fast* so it's searchable within seconds, then enrich asynchronously;
   an enrichment failure updates nothing and is retried, never losing the base record.

3. **"AI Classification" splits in two.** A **cheap deterministic** classification stays
   inline (search needs *a* category immediately). **LLM classification** is enrichment
   (§7) — at 2M records, per-item LLM calls inline are impossibly slow/costly, and the
   project rule stands: the LLM refines existing data, it never fetches or fabricates.

4. **Index is a projection of the DB, not a pipeline peer.** The DB is the source of
   truth; the search index is derived. If they're the same store (Postgres FTS) persist ==
   index. If separate (Meilisearch/Typesense/pgvector), the index is rebuilt from the DB
   via an outbox, so a failed index write never loses data and the index is reconstructable.

**Everything is idempotent** (key + content_hash), so any stage can be safely retried and
any provider safely re-run — the foundation for at-least-once workers.

---

## 4. Data Model — can `Event` become `Opportunity`?

**Verdict: the *pattern* is future-proof; the *fields* are event-shaped and several are
dangerous. Generalize before multi-type provider expansion — and ideally before the
Postgres schema is frozen, to avoid migrating twice.** (Design only — not implemented here.)

**Already future-proof (keep):**
- The **frozen, normalized, provider-agnostic canonical record** every source maps into —
  this discipline is exactly right; it's what makes generalization a guarded migration.
- `title`, `description`, `url`, `provider` provenance, participation mode
  (`city`/`location`/`is_online`).

**Needs abstraction (event-specific today):**
- **Temporal model.** `start_date`/`end_date` assume "a thing that happens on a date." A
  scholarship/grant/fellowship has an **application deadline**; an internship has an
  application window + start; a hiring drive is **rolling**. Generalize to a **typed
  temporal block**: `starts_at`, `ends_at`, `deadline`, `announced_at`, `is_rolling`.
- **Category.** A closed 7-value `EventCategory` enum can't hold 20+ types plus "future
  types," and it **conflates format with topic** (meetup/conference vs ai/startup — a
  tension already visible in `classify_category`). Split into `opportunity_type`
  (extensible, registry-backed) **and** `topics`/`tags` (many).
- **Value/cost.** `is_free`/`price` assume money flows *from* the user. For
  grants/scholarships/stipends it flows *to* them. Generalize to a **value block**: cost
  vs award vs stipend, currency, amount, `is_free`.
- **Missing fields** non-events need: `eligibility`, `application_url`, `organizer`,
  award/stipend amount, cohort/duration, `status` (lifecycle).

**Dangerous (call it out):**
1. **Single `start_date` as the only temporal anchor** — forces deadlines/rolling into the
   wrong slot. The #1 model risk.
2. **Closed `EventCategory` enum** conflating type + topic — code change per new type.
3. **`is_free`/`price` cost-direction assumption** — inverts for awards.
4. **`content_hash` over a fixed field list** — growing the model changes the hash
   definition and triggers a one-time mass "content changed" reindex. Plan for it.
5. **`event_key = URL`** — some opportunities lack a stable unique URL, or many roles share
   one listing URL. Identity needs a fallback (`provider + source_id`, else hash). Latent
   now, worse across types.

**Recommended shape (later phase):** a **narrow canonical core** (identity, type, topics,
temporal block, participation, value, status) **+ a `attributes` JSONB extension** for the
type-specific long tail (prize pool, award level, internship duration). JSONB + GIN
(Postgres) / JSON1 (SQLite) is the pragmatic scale answer — avoids both a 60-column sparse
table and full EAV query-hell. Keep `Event` as a thin compatibility projection during
migration so the **frozen API/frontend contract** doesn't break (see §7 migration risk).

---

## 5. Scaling — where this bottlenecks, and the trigger to act

| Subsystem | Bottleneck | Trigger to migrate | Move |
|---|---|---|---|
| **SQLite** | single writer; file-local (no multi-instance); weak replication | sustained concurrent ingestion, or >1 app instance, or ~1–5M rows | **Postgres** (MVCC, concurrent writers, replicas, partitioning, JSONB, FTS, pgvector) behind the same repo interface |
| **Scheduler** | single process; RAM-bound; dies on restart; run budget > interval | run can't finish within its tick; >~200 providers | persisted schedule (already) → **durable queue + horizontal workers** |
| **Provider execution** | 1000 outbound conns; slow/fragile scrapers; rate limits | tail latency dominates the tick | bounded concurrency + circuit breakers + workers |
| **Memory** | dedup/rank/`all()` materializing the set | any full-set op at >~100k | **stream/iterate + push filters to the store**; never hold the table |
| **Repository** | row-by-row upsert; offset paging; index bloat on a 2M hot table | ingestion write time; deep-page latency | bulk upsert, keyset paging, partial/covering indexes, **archive + partition** |
| **Search** | `LIKE %kw%` is a **full scan** | it's a cliff, not a slope — fine then suddenly not, ~100k+ | **FTS** (SQLite FTS5 / Postgres tsvector) → external engine (Meilisearch/Typesense) for typo-tolerance/facets |
| **Ranking** | scores every row in Python | candidate set > a few thousand | **two-phase**: store retrieves top-K, Python re-ranks only K; precompute static signals as columns |
| **Analytics** | live-fetch + `count(*)` + full scans | dashboards slow / contend with ingestion | incremental aggregates, materialized views, **read replica** |
| **Background jobs** | enrichment/expire/archive at 2M | jobs overrun | incremental, checkpointed, idempotent, rate-limited on workers |

**Design-for-growth-without-complexity-today:** put the **seams** in now — `Dispatcher`,
`SearchIndex`, `OpportunityRepository`, pipeline stages — so the heavy implementations
(Postgres, queue, external index) drop in later without touching policy code. Do **not**
build Redis/Meilisearch/Celery today.

**The one honest exception (see §7 ops):** "continuous ingestion" as a *production*
premise is incompatible with SQLite-on-ephemeral-disk. Dev/test SQLite is fine; the
**production source of truth needs durable managed storage (Postgres) earlier than a
strict "prove everything on SQLite first" reading implies.**

---

## 6. Roadmap — revised

Your list, annotated, with deviations justified:

| Your order | Change | Why |
|---|---|---|
| 3A Repository | ✅ done | base store |
| 3B Ingestion | **insert Repository v2 first** | ingestion binds to bulk/paging/sync-state; freeze them first (§1) |
| 3C Scheduler | **split runner ≠ scheduler** | build the single-provider *runner* before orchestrating 1000 |
| 3D Repo-backed search | **move earlier** | flip to DB-as-truth ASAP; everything after is incremental |
| 3E Analytics | keep, after search | analytics reads the DB |
| 3F Postgres | **reframe as productionization** | adopt when SQLite hurts (§5), not "late" |
| 3G Search Index | keep | after FTS is outgrown |
| 3H AI Enrichment | keep, async | never inline (§3) |
| 3I Recommendations | keep | folds in the deferred Phase 2 #4/#5 |
| 3J Provider Expansion | keep, continuous | metadata-driven onboarding |
| — | **insert Data Model Generalization** | your list omits it; must precede multi-type expansion & Postgres schema freeze |
| — | **insert Task Queue + Workers** | your list omits it; the real 1000-provider mechanism |

**Recommended sequence:**

*Foundation*
- **3A** Storage repository ✅
- **3B** Repository v2 — bulk upsert, keyset `Page`, streaming `iterate`, `status`
  lifecycle + archive, `ProviderStateStore` (sync checkpoints + health), `version`. SQLite impl.
- **3C** Ingestion Runner — one provider end-to-end: fetch→normalize→classify→dedup-vs-DB→
  bulk upsert; retry/backoff/rate-limit/timeout; declared metadata; checkpoints; health.
- **3D** Scheduler — metadata-driven orchestration of many; `due_providers`, bounded
  concurrency, priority, circuit breaker, jitter; `Dispatcher` seam (in-process); expire + archive jobs.
- **3E** DB-backed Search + cutover — `DatabaseSearchProvider`, flip `get_provider()`,
  warm DB first, add FTS. **Frozen API/FE unchanged.**
- **3F** Observability — provider-health dashboard, growth/freshness/coverage from the DB
  (incremental), ingestion metrics, alert hooks.

*Productionization*
- **3G** Postgres backend — second repo impl (asyncpg), partition by date, JSONB
  attributes, FTS; durable scheduler state. (Bring forward if §5 triggers fire sooner.)
- **3H** Data Model Generalization — Event→Opportunity: typed temporal block, extensible
  type + topics, value/award block, eligibility/application_url/organizer, status; core
  columns + JSONB. Migrate providers. Keep an Event-compatible API projection.

*Scale & intelligence*
- **3I** External Search Index — Meilisearch/Typesense or pg FTS/pgvector; async projection
  from DB (outbox); two-phase retrieve→re-rank.
- **3J** Durable Task Queue + Workers — swap `Dispatcher` to Arq/Celery + Redis; horizontal
  ingestion/enrichment; near-real-time tiers.
- **3K** AI Enrichment — async, idempotent: embeddings, tags, dedup assist, quality
  scoring, LLM re-classification (refine, never fabricate).
- **3L** Recommendations / personalization — preferences, embedding similarity, saved
  searches, alerts (absorbs Phase 2 #4/#5).
- **3M** Provider Expansion to 500–1000+ — provider template/SDK, automated health gating.

**Ordering tension to decide (§7):** 3G (Postgres) vs 3H (generalization). Generalizing
*before* freezing the Postgres schema avoids migrating twice; adopting Postgres *before*
generalizing gets durability sooner. My recommendation: **generalize the model on paper
during 3B–3C, land Postgres (3G) with the already-generalized schema, then do the code
migration (3H).** i.e. let the model design lead the Postgres schema even if the code
migration trails.

---

## 7. Critical self-review (as an adversarial Staff reviewer)

**Architectural weaknesses**
- **Repository is drifting toward a God interface.** Splitting into three ports helps but
  risks over-fragmentation before the need is proven. Judgement call; watch it.
- **Dedup ↔ repository coupling.** DB-side candidate lookup ties dedup to the temporal/geo
  columns and their indexes; when the model generalizes (3H), dedup + indexes move too.
- **`content_hash` is a subtle contract.** Fields *in* it cause churn when added; fields
  *out* of it mean changes don't propagate to search/index. Easy to get wrong silently.
- **Two-sources-of-truth risk** once the search index is separate from the DB — they
  drift; requires an outbox/reconciliation, itself a classic bug source.
- **Redundant visibility gates.** `status=active` and `upcoming_on_or_after` both hide
  rows and can disagree (an "active" but past row). Define **one** rule; I currently have two.

**Future migration risks**
- **SQLite→Postgres dialect leakage.** Upsert/RETURNING, JSON1 vs JSONB, FTS5 vs tsvector,
  boolean/type affinity. If 3C–3F write SQLite-specific SQL, Postgres is more than a swap.
  Mitigation: keep SQL inside the impl; **stand up a thin Postgres impl early to keep the
  abstraction honest** (your "prove on SQLite first" instinct is right, but waiting too
  long lets SQLite-isms ossify).
- **Event→Opportunity vs the frozen API/FE.** The generalization touches every provider,
  the response schema, and frontend types — colliding with the "frozen API" promise.
  Mitigation: an Event-compatible projection / versioned API. This is real and unavoidable.
- **`content_hash`/`key` redefinition** forces a full re-ingest/reindex — a planned, but
  non-trivial, one-time event.

**Hidden coupling**
- **The empty-`SearchQuery`-means-everything convention** is an implicit contract; not
  every provider paginates/returns "all" identically. Ingestion completeness silently
  depends on each provider's empty-query behavior. Needs to become an explicit
  `fetch_all()` capability on the plugin, not a convention.
- **`score_source` hardcodes per-provider quality.** Unmaintainable at 1000 providers →
  must become data-driven (derived from health/dup-rate/completeness).
- **`classify_category` couples taxonomy to keyword regexes** — fights type generalization.
- **CompositeProvider today does city+classify+dedup+rank inline.** Splitting these across
  ingestion (write) and search (read) risks divergent duplicated logic during transition;
  they must share the same pure functions, called from two places.

**Scalability concerns (honest)**
- **In-process scheduler + SQLite is single-node by construction.** The plan defers the
  fix correctly, but there is a **valley of pain** where SQLite is stressed before Postgres
  lands. We need explicit metric triggers (§5), not vibes, to time the jump.
- **Dedup has pathological blocks** (many same-day online events in one city ⇒ O(block²)).
  Needs `cluster_id` + per-block caps.
- **`LIKE` search is a cliff.** It works at thousands and falls off a cliff — must move to
  FTS *before* the cliff, not after users notice.

**Operational concerns**
- **₹0 hosting vs continuous ingestion is a genuine contradiction.** Render free dynos
  sleep; disks are ephemeral ⇒ SQLite-in-prod loses data on redeploy, and an in-process
  scheduler doesn't run while asleep. **The production source of truth must be durable
  managed storage (Supabase/Postgres) sooner than "prove everything on SQLite first" reads.**
  Stated plainly so we plan for it rather than discover it.
- **No migrations framework.** The schema will churn hard; we need Alembic (or equivalent)
  before that churn, or every change is manual and risky.
- **Missing prod muscles:** backups, monitoring/alerting, dead-provider detection,
  poison-payload quarantine, per-provider secret/config management at 1000 sources.

**Technical debt (current, honest)**
- `all()` footgun — I shipped it in 3A; deprecate it in 3B for `iterate()`.
- Single global lock in the SQLite repo (serializes reads vs write-batches).
- `is_active` boolean conflates lifecycle states.
- `content_hash` field list hardcoded.
- Empty-query "give me everything" is an implicit provider contract.
- No provider registry with metadata yet (providers are hand-wired in `get_provider()`).

---

## 8. Decisions needed before 3B

1. **Adopt Repository v2 now** (bulk / keyset `Page` / `iterate` / `status` lifecycle /
   `ProviderStateStore` / `version`) as the interface 3C–3E build on? (Strongly recommend yes.)
2. **Postgres timing** — accept that production durability needs Postgres/Supabase earlier
   than a strict SQLite-first reading, and stand up a thin Postgres impl relatively early to
   keep the abstraction honest? Or hold the line on SQLite until §5 triggers fire?
3. **Model generalization ordering** — design `Opportunity` on paper during 3B–3C and let
   it lead the Postgres schema (my recommendation), or defer the model discussion entirely
   until 3H?
4. **One visibility rule** — settle `status` lifecycle vs date-based `upcoming` as the
   single source of "is this shown," to avoid the redundant-gate bug.

Nothing above is implemented. On approval (with any changes to the above), 3B begins with
the Repository v2 interfaces + SQLite implementation + migration of the 3A tests.
