# Phase 3 — Production Ingestion Platform

**Staff Engineer review + architecture. Implementation-independent. No code.**
**Status: APPROVED with modifications (2026-07-15). Implementation begins at Repository v2 (3B).**

## Approved modifications (folded into this architecture)

1. **No hot-set size assumption.** The repository and search path are designed so the
   *searchable catalog* scales to **millions** of records with no architectural change —
   keyset pagination, streaming iteration, index-pushdown filters, bounded two-phase
   retrieve-then-rank, and an archive tier from day one; nothing ever loads the full set into
   memory. The small *active* set of today is an observation about current data, **not** a
   design constraint. (This supersedes challenge ① below — that section stands as data
   context, not as an architectural limit.)
2. **Event-driven is the production model.** Production assumes **continuous ingestion
   workers** reacting to schedule/catalog events off a durable queue. *Scheduled-batch is only
   a development / free-hosting trigger* running the same metadata-driven policy behind the
   Job-Queue/Worker seam. (Reframes Part 5.)
3. **Provider Capability Registry** (new component) — every provider *declares its supported
   features* (pagination, delta sync, speakers, organizers, categories, deadlines, online
   events, pricing, schedules, …). Every other component consumes declared capabilities
   instead of branching on provider identity. (Added to the Sourcing plane.)
4. **Provider Sandbox pipeline** (new component) — new providers are onboarded through
   Fetch → Validate → Normalize → Classify → Deduplicate → Preview → Approve → Production and
   do **not** enter the production catalog until validated and approved. (New Onboarding plane.)

The mission: replace "few-provider search-time fetch" with a continuously-running
ingestion platform that can support hundreds of providers and a large event catalog —
"the backend of Google News, not a scraper." This document reviews every existing module
against that bar, challenges the mission's own assumptions with evidence, and designs the
platform.

---

## Part 0 — Framing: adopt the patterns, right-size the envelope

Google News works because it **inverts** ingestion from reading (sources are pulled on a
schedule into a system of record; readers query the record), isolates sources as plugins,
deduplicates aggressively, and treats the index as a projection. **Those patterns are
exactly right and this design adopts all of them.**

But Google News runs at second-level freshness over millions of articles/day because news
decays in *hours*. Professional events decay over *weeks* and are announced days-to-months
ahead. So we take Google News's **shape** and not its **size** — building thousand-worker,
Kafka-scale infrastructure for an India-events working set would be over-engineering that
never ships. Part 2 quantifies the real envelope; the design in Part 3 is sized to it while
keeping the seams that let it grow 100× without a rewrite.

---

## Part 1 — Staff review of every existing module

Format per module: **✅ correct · 💥@500 providers · 💥@5M events · ♾ stays forever ·
⚠ must change · 🔒 must NOT change.** Evidence is drawn from the actual code.

### 1. Models — `app/models/event.py`, `app/models/search.py`, `app/storage/models.py`
- ✅ Frozen, normalized, provider-agnostic `Event`; the `StoredEvent` wrapper (domain record
  + ingestion metadata) and `content_hash`/`event_key` (3A) are the right shape for idempotent ingestion.
- 💥@500: nothing structural — the model doesn't fan out. But `EventCategory` (7-value enum)
  and the hardcoded field set can't express the opportunity types coming later.
- 💥@5M: `event_key = normalized URL` collides when sources share a URL (one listing page,
  many roles) or lack a stable URL → identity errors at scale. `content_hash` over a fixed
  field list means any future field change triggers a full re-hash/re-ingest.
- ♾ The immutable-normalized-record pattern; provenance (`provider`) on every record.
- ⚠ Add an identity fallback (`provider + source id`, else hash) before millions of rows.
- 🔒 The `Event` field set and `EventCategory` — **frozen by your instruction until Phase 5**;
  do not generalize now.

### 2. Providers — `app/providers/*.py` (`EventProvider`, 7 sources + Bevy base + mock)
- ✅ The `EventProvider` source-adapter contract is excellent and already the right seam.
  Each provider fetches, normalizes at the boundary, and degrades to `[]` on failure. `BevyEventProvider`
  proves shared-base reuse. Pagination with a logged page-cap (no silent truncation) is disciplined.
- 💥@500: **each provider carries its own per-instance `TTLCache` and opens its own httpx
  client per call** — fine for 7, meaningless once fetch is scheduled (freshness must come from
  ingestion cadence, not a per-process cache). Providers are hand-listed in `get_provider()`; 500
  can't be hand-wired. No declared metadata (interval/timeout/rate limit/priority) — behavior is
  hardcoded per class.
- 💥@5M: providers themselves don't hold the catalog, so they don't break on row count — but
  the empty-`SearchQuery()`-means-"everything" convention + fixed page caps (`_MAX_PAGES=5`) mean a
  provider silently returns a *bounded slice*, not "all," which is wrong for a system of record.
- ♾ The normalize-at-the-boundary contract; per-provider fetch/parse logic (reused verbatim
  as ingestion sources).
- ⚠ Wrap providers as **ingestion plugins with declared metadata**; make "fetch all"
  (with real pagination/delta) an **explicit capability**, not a convention; drop the per-instance cache.
- 🔒 The individual providers' fetch + normalization internals — reuse **unchanged**.

### 3. Composite — `app/providers/composite.py`
- ✅ Being itself an `EventProvider` (so `SearchService` is untouched) is the cleanest possible
  seam. The pipeline (merge → refine → filter → dedup → rank) is correct *as logic*.
- 💥@500: **fatal.** It fans out to *every* provider via `asyncio.gather` on *every* search —
  500 concurrent outbound fetches per query, unbounded, no rate limit, waiting for the slowest.
  This is the single biggest thing that must die.
- 💥@5M: it merges, dedups and ranks **in memory per search** — cannot hold or process
  millions per query.
- ♾ The *logic stages* (refine/classify/dedup/rank) survive — but they **relocate**: dedup +
  classify + city move to the ingestion write path; rank stays on the read path.
- ⚠ Retire composite-as-search. Its fan-out becomes the **ingestion fan-out** (bounded,
  scheduled, isolated); search reads the catalog instead.
- 🔒 Nothing of the object survives, but the stage functions it calls do.

### 4. Normalization — per-provider + `app/city.py` + `app/providers/filtering.py`
- ✅ Normalization at the boundary + `normalize_city`/`detect_city` (alias map) + shared
  `matches()` filter is clean and reused across providers.
- 💥@500: the city alias map is hand-maintained; 500 sources bring far more geographic spread
  than a static map covers.
- 💥@5M: `matches()` is an in-memory per-event predicate — irrelevant once filtering is pushed
  into the store (`SearchCriteria` already does this in 3A).
- ♾ `normalize_city`/`detect_city` as reusable pure resolvers (seed of Location resolution).
- ⚠ Location normalization becomes a first-class, data-driven step at ingestion write time.
- 🔒 The pure resolver functions.

### 5. Classification — `app/providers/classify.py`
- ✅ Deterministic, high-precision, text-only (nothing invented); correctly refines only
  generic `meetup`.
- 💥@500: the taxonomy is **hardcoded regexes**; adding types/topics/skills across hundreds of
  sources means editing code, and it conflates *format* (meetup/conference) with *topic* (ai/startup).
- 💥@5M: runs per event — fine inline (cheap) at write time, but can't grow into topics/skills
  without a real taxonomy.
- ♾ The principle: a cheap deterministic classification is assigned at write time (search never
  waits on AI).
- ⚠ Externalize taxonomy into **data** (Taxonomy Engine) in Phase 5; keep this as the inline
  classifier feeding it.
- 🔒 Its determinism + "refine, never invent" policy.

### 6. Deduplication — `app/providers/dedup.py`
- ✅ Deterministic rapidfuzz with date+city hard gates, keep-richest merge — genuinely good,
  hardened against WRatio false positives.
- 💥@500: more overlapping sources → **entity resolution becomes the dominant cost**, and it
  currently runs over a single search's batch, blind to what other providers already ingested.
- 💥@5M: blocks by exact `start_date` then O(block²) clustering — a popular date (e.g. a big
  conference day, or many same-day online events) yields a huge block → quadratic blowup.
- ♾ The pure similarity functions (`normalize_title`/`title_similarity`/`event_similarity`).
- ⚠ Move to **write-time Entity Resolution against DB candidates** (blocked, bounded,
  cluster-id'd), assembling a canonical record with provenance instead of discarding rows.
- 🔒 The similarity math.

### 7. Ranking / Search read path — `app/providers/ranking.py`, `app/services/search_service.py`
- ✅ Ranking is isolated, pure, weights-in-one-constant; `SearchService` (two-tier cache,
  injected deps, metrics) is a clean read edge.
- 💥@500: `_SOURCE_QUALITY` is a **hand-maintained per-provider dict** — unmaintainable at
  hundreds of sources.
- 💥@5M: `rank()` scores and sorts the **entire candidate list** in memory — needs two-phase
  (store retrieves top-K, rank re-orders only K).
- ♾ Ranking as a separable, pure read-side stage; the `SearchService`/`QueryParser` seams.
- ⚠ Make source quality **data-driven** (from health/dup-rate/completeness); bound the
  candidate set at the store before ranking.
- 🔒 `SearchService` public interface, `QueryParser` interface, the ranking algorithm shape.

### 8. Repository / Storage — `app/storage/` (3A)
- ✅ Storage-agnostic `EventRepository` + SQLite impl; idempotent 3-way upsert; `SearchCriteria`
  pushes filters into the store. The abstraction is the right foundation.
- 💥@500: row-by-row upsert (a SELECT then write per record) can't keep up with many providers
  writing continuously; no provider-state/checkpoint store for the scheduler.
- 💥@5M: `all()` loads everything into memory (**footgun**); no keyset pagination or streaming
  iteration; `is_active` boolean can't express expired/withdrawn/archived; no archive tier → the
  hot table and its indexes grow unbounded.
- ♾ The storage-agnostic abstraction itself.
- ⚠ **Repository v2** (this is 3B): bulk upsert, keyset pagination, streaming iterate, `status`
  lifecycle + archive, provider-state/checkpoints, versioning; remove `all()`.
- 🔒 The abstraction/port; the app never binds to a concrete backend.

### 9. Database — SQLite (the current backend)
- ✅ Zero-dependency, durable on a real disk, perfect for dev/test and the first proof.
- 💥@500: **single-writer.** Concurrent workers writing serialize behind one lock; file-local
  means no multi-instance. Fine for a *single scheduled batch writer*; wrong for concurrent workers.
- 💥@5M: workable to low millions with good indexes, but archival/partitioning/replication are
  weak; on ₹0 hosting the disk is **ephemeral** → data loss on redeploy.
- ♾ Nothing about SQLite specifically is forever — it lives behind the abstraction.
- ⚠ Adopt a durable managed backend (Postgres/Supabase) as a second implementation of the same
  abstraction when concurrency/durability demand it (Phase 4), and keep SQLite for dev/test.
- 🔒 n/a.

### 10. Analytics — `analytics/provider_analytics.py`
- ✅ Clean network/pure split (`collect` vs `build_stats`/`render_markdown`), unit-tested math.
- 💥@500: `collect()` runs providers **sequentially** with live cold fetches — 500 sources = a
  very long run; and the `WORKING`/`SKIPPED` registry is **hand-maintained and separate from
  `get_provider()`** → guaranteed drift.
- 💥@5M: recomputes over live fetches, not the stored catalog — can't scale; no growth/freshness
  history.
- ♾ The aggregate→render split.
- ⚠ Point analytics at the **provider-state store + catalog** (not live network); make the
  provider **registry the single source of truth** both ingestion and analytics read.
- 🔒 The pure aggregate/render structure.

### 11. Scheduler — **does not exist**
- ⚠ Must be built: metadata-driven, restart-safe, bounded-concurrency orchestration (Part 3).
  Today freshness is paid by the user at search time; there is no background refresh at all.

### 12. Background Workers / Job Queue — **do not exist**
- ⚠ Must be built as **abstractions** (Part 3) so the execution mechanism (scheduled-batch
  in-process now → durable queue + workers later) can swap without touching scheduling policy.

### 13. Provider State / Health / Checkpoints — **do not exist**
- ⚠ Must be built: per-provider sync checkpoints, health metrics, circuit state, next-run —
  the memory that makes scheduling, delta sync, and fault isolation possible.

---

## Part 2 — Challenging the mission's assumptions (with evidence)

You asked me to argue if I think the framing is wrong. Five challenges — each **narrows scope
and saves complexity**, none weakens the vision.

**① "Millions of events" conflates the hot working set with the archive.**
The *active* (upcoming, not-yet-expired) set is what search touches. India professional/tech
events, even with 500 sources and heavy cross-posting collapsed by dedup, realistically yield
**tens of thousands of distinct upcoming events**, not millions. Evidence: 7 curated sources
produced 108 deduped; distinct-event growth is sublinear in provider count because sources
overlap. Millions is only reached by accumulating **historical/expired** events over years.
**Implication:** the hot search path must be fast over ~10⁴–10⁵ rows (a single Postgres does
this trivially — no distributed hot store needed); the **millions figure belongs to the cold
archive**, which has cheap, different requirements. Designing the hot path for millions is
premature optimization; designing the archive for millions is correct.

**② Raw provider count is the wrong optimization target.**
Coverage-per-provider has steep diminishing returns (GAP_ANALYSIS: 3 cities = 61% of events).
Past ~50–80 well-chosen sources + a few aggregators, additional providers mostly add
**duplicates of events already ingested**, which increases **entity-resolution load
super-linearly** rather than coverage. **Implication:** the architecture must *scale to* 500,
but the *real* scaling problem is entity resolution and health-gating hundreds of
low-reliability sources — not fetch throughput. Optimize unique-coverage-per-provider; treat
resolution, not parallel fetching, as the hard problem.

**③ "Near real-time" is the wrong freshness target.**
Events are announced days-to-months ahead; deadlines/venues rarely change within minutes.
Second/minute-level freshness is unnecessary *and*, on ₹0, impossible. A **tiered** model —
a few high-velocity sources every ~15–30 min, most daily, static sources weekly — delivers the
same user value at a fraction of the cost. Target **"predictably fresh, tiered by source
velocity,"** not near-real-time.

**④ "Think like Google News" — take the shape, not the size.**
News decays in hours (hence second-level freshness, millions/day, thousand-worker fleets);
events decay in weeks. The *patterns* transfer; the *scale/freshness envelope is 3–5 orders of
magnitude smaller*. Building Google-News-scale infrastructure here would never ship. This
design uses source-plugins + dedup + projections + health, sized to the real envelope.

**⑤ ₹0 vs "continuous synchronization + background workers" is a hard contradiction.**
Continuous background ingestion + durable storage requires **always-on compute + a managed
durable database**. ₹0 (Render free: dynos sleep when idle, disks are ephemeral) provides
neither — an in-process scheduler doesn't run while asleep, and SQLite is wiped on redeploy.
Evidence: Render free-tier behavior. **Honest resolution:** redefine "continuous" as
**scheduled-batch on a free trigger** (GitHub Actions cron / Supabase scheduled function /
Render cron) writing to **free managed Postgres (Supabase)**. The metadata-driven *policy* is
identical to an always-on worker; only the *trigger* differs — and the Job-Queue/Worker
abstractions (Part 3) make upgrading to always-on workers a swap, not a rewrite. This must be
a conscious decision now, not a production surprise.

**Bonus — "historical preservation forever" needs tiering.** Keeping every expired event, full-
fidelity, in the hot store forever bloats indexes and cost. Preserve **series/trends/outcomes**
forever (the valuable part); tier full expired rows into a compacted archive. "Preserve
history" ✅ as a principle; "keep every full row in the hot store forever" ✗.

---

## Part 3 — The Ingestion Architecture

Organized into five planes. Each component: **why it exists · responsibilities · lifecycle ·
interactions · scalability · migration.** All implementation-independent.

```
                          ┌──────────────── CONTROL PLANE ────────────────┐
        declares          │  Scheduler → Job Queue → Worker Pool          │
 Plugins ──metadata──►  Registry            (retry · rate-limit · circuit) │
   │                      └───────┬───────────────────────────────────────┘
   │ fetch (delta/full)          │ runs one ingestion job per provider
   ▼                             ▼
 SOURCING PLANE            INGESTION RUN:  Fetch → Normalize → Classify → Resolve(dedup vs DB)
   │                                              │
   │                                              ▼
 STATE PLANE  ◄── checkpoints/health ──   Bulk Upsert into ─────►  DATA PLANE
 (Provider State Store)                       CATALOG (system of record)
                                                   │  emits "changed" events
                                        ┌──────────┴───────────┐
                                        ▼                      ▼
                              async ENRICHMENT           PROJECTIONS (search index,
                              (best-effort workers)       analytics, recommendations)
                                                              │
                                              read path:  Search reads catalog/index → rank
                                                          (SearchService/API/frontend UNCHANGED)
```

### SOURCING PLANE

**Provider Plugin System** — *why:* isolate every source behind one uniform contract so 500
heterogeneous sources look identical to the platform (zero coupling). *Responsibilities:* fetch
raw data (full or delta), normalize to the canonical record, expose an explicit "fetch-all" and
(if capable) "fetch-since-checkpoint" capability. *Lifecycle:* registered → scheduled → invoked
per run → reports outcome. *Interactions:* invoked by a Worker; reads its checkpoint from the
State Store; writes normalized records into the pipeline. *Scalability:* stateless and
independently testable; adding one = one registration. *Migration:* today's 7 providers are
wrapped **unchanged** as plugins.

**Provider Registry** — *why:* one authoritative list of providers + metadata that **both**
ingestion and analytics read (kills today's registry drift). *Responsibilities:* enumerate
plugins, hold their declared metadata, gate them by health/enabled state. *Lifecycle:* the
startup/discovery source of truth. *Interactions:* the Scheduler and Analytics read it.
*Scalability:* data-driven; supports hundreds of entries and future dynamic/partner
registration. *Migration:* replaces the hand-wired `get_provider()` list and the analytics
`WORKING` registry with one source of truth.

**Provider Metadata** — *why:* the Scheduler adapts to each provider from **declared data**, never
hardcoded branches. *Responsibilities:* declare refresh interval, timeout, retry policy, backoff,
rate limit, concurrency limit, priority, `supports_incremental`/`pagination`/`delta`, expected
volume, circuit-breaker config, and the provider's parser **version**. *Lifecycle:* static, in the
plugin; versioned with it. *Interactions:* read by Scheduler, Retry Engine, Rate Limiter, Circuit
Breaker. *Scalability:* the mechanism that lets one scheduler run 500 heterogeneous providers.
*Migration:* new declaration added when each provider is wrapped.

**Provider Capability Registry** — *why:* consumers must adapt to *what a provider can do and
supply* without ever branching on provider identity (the enemy of "zero provider coupling").
*Responsibilities:* each provider **declares its capabilities** along two axes — (a) *fetch
modes*: pagination, full-crawl, delta/incremental sync, schedules; (b) *data features it
yields*: speakers, organizers, categories, topics, deadlines, online-vs-physical, pricing,
eligibility, venue, series/recurrence. *Lifecycle:* declared statically with the plugin,
versioned with it; validated during onboarding. *Interactions:* the **Ingestion Runner** reads
fetch-mode capabilities (delta vs full, paginate or not); **Normalization/Entity Resolution/
Enrichment** read data-feature capabilities to know which fields to expect and which enrichment
to attempt; the **Scheduler** reads them for cadence hints; **Analytics** reports coverage by
capability. *Scalability:* the platform generalizes to hundreds of heterogeneous sources and,
later, to the richer Opportunity model (speakers/organizers/deadlines map to graph entities)
**without a single provider-specific `if`**. *Migration:* introduced with the plugin registry
(3C); today's providers declare a minimal, honest capability set (most yield only title/date/
city/category).

**Provider Versioning** — *why:* a source's structure and our parser evolve; we must know which
parser version produced a record, and be able to re-parse. *Responsibilities:* stamp records
with the parser/plugin version; enable targeted re-ingestion when a parser is fixed.
*Lifecycle:* bumped when a plugin's parsing changes. *Interactions:* recorded with provenance in
the catalog. *Scalability:* makes fixes auditable and replayable across millions of records.
*Migration:* introduced with the plugin registry.

### ONBOARDING PLANE

**Provider Sandbox Pipeline** — *why:* at hundreds of sources, an unvetted provider can flood
the catalog with malformed, duplicate, or spam records; onboarding must be a **gated pipeline**,
not a code deploy. *Responsibilities:* run a new provider through
**Fetch → Validate → Normalize → Classify → Deduplicate → Preview → Approve → Production**:
- *Fetch* a sample under the provider's declared capabilities/limits.
- *Validate* structure, required fields, declared-capability honesty, volume sanity, error rate.
- *Normalize* to the canonical record and *Classify* — exactly as production would.
- *Deduplicate* against the **existing catalog** to measure novelty vs. overlap (does this source
  add unique coverage, or just re-post known events?).
- *Preview* a report — sample records, coverage/novelty, quality flags — for human review.
- *Approve* → the provider graduates to production ingestion; until then its records live only in
  a sandbox space and never reach the production catalog. A provider can be demoted back.
*Lifecycle:* `sandboxed → validated → preview → approved → production` (or `rejected` /
`demoted`), tracked in the Provider State Store. *Interactions:* reuses the same
Normalize/Classify/Entity-Resolution stages as production; reads the Capability Registry to know
what to validate; writes onboarding status to the State Store. *Scalability:* protects catalog
quality as provider count grows — the gate that makes 500 providers safe rather than dangerous.
*Migration:* built once the ingestion runner exists (3C) and hardened in 3F; today's 7 providers
are grandfathered in as already-approved.

### CONTROL PLANE

**Provider Scheduler** — *why:* decide *when and what* to ingest across hundreds of providers
without stampede, using metadata + health. *Responsibilities:* compute due providers from a
**persisted next-run** (restart-safe), order by priority, apply jitter (anti-stampede), enqueue
jobs, trigger expiry/archive jobs. *Lifecycle:* runs each tick (a heartbeat or an external cron
trigger). *Interactions:* reads Registry + State Store; submits to the Job Queue. *Scalability:*
policy is pure and metadata-driven; the number of providers is just data. *Migration:* built in
Phase 3 (3D); runs in-process now, unchanged when execution moves to workers.

**Job Queue abstraction** — *why:* decouple *deciding* to run a job from *executing* it, so the
execution mechanism can change without touching policy. *Responsibilities:* accept jobs, hand
them to workers, preserve priority, survive (later) process restarts. *Lifecycle:* a job is
enqueued → claimed → completed/failed/retried. *Interactions:* Scheduler produces; Workers
consume. *Scalability:* **the key seam** — an in-process bounded queue now, a durable
distributed queue later, same interface. *Migration:* abstraction defined in Phase 3; durable
backend adopted only when metrics demand it.

**Worker abstraction + Background Workers** — *why:* execute one ingestion (or enrichment) job in
isolation so one bad provider can't harm others or the read path. *Responsibilities:* run the
ingestion-run lifecycle for one provider under its rate/concurrency/timeout, capture the outcome,
record health. *Lifecycle:* claim job → execute → report → release. *Interactions:* pull from Job
Queue; drive the plugin; write to Catalog + State Store. *Scalability:* bounded global concurrency
now; horizontally-scaled worker processes later — same abstraction. *Migration:* in-process pool
in Phase 3; separate worker processes when compute allows.

**Retry Engine** — *why:* transient failures (timeouts, 5xx, rate-limit) must not lose a run.
*Responsibilities:* apply the provider's retry policy — bounded attempts, exponential backoff +
jitter, only on retryable errors. *Lifecycle:* wraps each fetch attempt. *Interactions:* reads
metadata; cooperates with the Circuit Breaker. *Scalability:* per-provider, isolated.
*Migration:* Phase 3 with the runner.

**Rate Limiter** — *why:* respect source limits and our own outbound capacity across 500 sources.
*Responsibilities:* pace requests per provider (token bucket) and cap fan-out during pagination.
*Lifecycle:* gates every outbound request. *Interactions:* reads metadata; enforced by Workers.
*Scalability:* two-level (global + per-provider) prevents 500-way connection storms.
*Migration:* Phase 3.

**Circuit Breaker** — *why:* stop hammering a dead/broken source and wasting the run budget.
*Responsibilities:* open after N consecutive failures → skip until cooldown → half-open probe →
close on success. *Lifecycle:* state transitions stored per provider. *Interactions:* Scheduler
skips open providers; State Store holds the state. *Scalability:* essential fault isolation at
hundreds of unreliable sources. *Migration:* Phase 3.

### STATE PLANE

**Provider State Store** — *why:* the platform's memory of each provider, without which
scheduling, delta sync, and fault isolation are impossible. *Responsibilities:* persist per
provider: sync checkpoint/watermark, health metrics (success/latency/volume), circuit state,
next-run. *Lifecycle:* updated every run. *Interactions:* written by Workers, read by Scheduler +
Analytics. *Scalability:* one small row per provider — trivial. *Migration:* Phase 3, behind the
same storage abstraction as the catalog.

**Checkpoint System** — *why:* enable "fetch only what changed since last time" for capable
sources. *Responsibilities:* store and advance a per-provider position (timestamp/cursor/token);
never advance on a failed run. *Lifecycle:* read before fetch, advanced after a confirmed
successful ingest. *Interactions:* used by the plugin's delta capability. *Scalability:* turns a
full re-crawl into a small delta for capable sources. *Migration:* Phase 3; used opportunistically
where `supports_incremental`.

**Provider Health** — *why:* observability + automated trust/quality decisions. *Responsibilities:*
rolling success rate, latency, volume, freshness, failure patterns; feed source-quality weighting
and anomaly detection (volume→0). *Lifecycle:* recomputed per run. *Interactions:* Scheduler
(skip/deprioritize), Ranking (data-driven source quality), Analytics. *Scalability:* replaces the
hardcoded `_SOURCE_QUALITY` dict with data. *Migration:* Phase 3 → feeds ranking in Phase 4.

### DATA PLANE

**Storage abstraction (Catalog = system of record)** — *why:* one authoritative, backend-agnostic
store the whole platform treats as truth. *Responsibilities:* durably hold canonical records +
provenance + lifecycle; serve reads. *Lifecycle:* the spine everything else reacts to.
*Interactions:* written by ingestion, read by search/analytics/enrichment. *Scalability:* SQLite →
Postgres (partitioned/replicated) behind the unchanged port. *Migration:* Repository v2 in Phase 3.

**Bulk Upsert** — *why:* row-by-row writes can't sustain many providers. *Responsibilities:*
set-based insert-or-update keyed by identity, using content-hash to classify new/changed/unchanged.
*Lifecycle:* one batch per ingestion run. *Interactions:* the write end of every run.
*Scalability:* turns N round-trips into one batched operation. *Migration:* part of Repository v2.

**Content Hashing** — *why:* change detection + idempotency. *Responsibilities:* a stable hash of
meaningful fields; unchanged → cheap touch, changed → rewrite. *Lifecycle:* computed at
normalization. *Interactions:* drives upsert branch + version bump. *Scalability:* re-seeing 10⁵
unchanged events costs touches, not rewrites. *Migration:* exists (3A); hardened with an identity
fallback.

**Incremental Sync / Delta Fetching** — *why:* avoid re-crawling everything every cycle where a
source supports "since X." *Responsibilities:* fetch only changes since the checkpoint; fall back
to bounded full crawl otherwise. *Lifecycle:* per run, guided by metadata + checkpoint.
*Interactions:* Checkpoint System + plugin. *Scalability:* bounds cost for high-velocity sources.
*Migration:* Phase 3 where capable; hash-diff covers the rest.

**Expiration Strategy** — *why:* keep the working set to upcoming events. *Responsibilities:* mark
ended events `expired` (not deleted); search shows only active/upcoming. *Lifecycle:* a scheduled
job + write-time date checks. *Interactions:* Scheduler job on the Catalog. *Scalability:* bounds
the hot set regardless of total history. *Migration:* Phase 3 (extends 3A `deactivate_ended`).

**Archive Strategy** — *why:* stop the hot store growing unbounded. *Responsibilities:* move old
expired records to a cold tier (compacted); keep the hot index small. *Lifecycle:* periodic
archival past a cutoff. *Interactions:* Catalog → Archive; analytics reads cold for history.
*Scalability:* the answer to "5M events" — most are cold. *Migration:* Phase 3 defines the seam;
real cold tier when volume warrants.

**Soft Delete / Lifecycle** — *why:* distinguish ended vs source-removed vs archived vs active.
*Responsibilities:* a `status` lifecycle (not a boolean) + reason + timestamp; **one** visibility
rule (active + upcoming). *Lifecycle:* transitions on expiry/removal/archive. *Interactions:*
search filters on it. *Scalability:* clean semantics at scale. *Migration:* replaces `is_active`
in Repository v2.

**Failure Recovery / Historical Preservation** — *why:* a crashed run must not lose or duplicate
data; history must survive. *Responsibilities:* idempotent runs (safe re-execution), never destroy
data on a failed/empty fetch (only deactivate after N confirmed-absent successful runs), preserve
series/outcomes. *Lifecycle:* every run is replay-safe. *Interactions:* upsert idempotency +
checkpoints + provenance. *Scalability:* correctness under continuous operation. *Migration:*
Phase 3 invariant.

### INTELLIGENCE PLANE (write-time, + async)

**Normalization → Classification → Entity Resolution (dedup)** — the write-path stages, relocated
from the composite: map to canonical, assign a cheap deterministic classification, and resolve
against **existing catalog candidates** (blocked by date/city) into a canonical record with a
cluster id + provenance. **Async Enrichment** (embeddings, topics/skills, quality score, LLM
re-classification) runs *after* persist on best-effort workers — never blocking ingestion, always
idempotent, and — per the frozen invariant — **refining existing data, never fetching or inventing**.

**Provider Analytics** — recomputed from the **State Store + Catalog** (not live network),
incrementally, with growth/freshness/coverage history; the Registry is its single source of truth.

---

## Part 4 — Data flow, control loop, and fault isolation

**Control loop (per tick):** Scheduler reads Registry + State Store → selects due, non-open,
priority-ordered providers with jitter → enqueues jobs → Workers claim jobs under global +
per-provider concurrency.

**Ingestion run (per provider, isolated):** read checkpoint → Rate Limiter gate → Fetch (delta or
bounded-full) under Retry Engine + timeout → Normalize → Classify → **Entity-Resolve against DB
candidates** → **Bulk Upsert** (content-hash: new/changed/unchanged) with provenance + cluster id
→ advance checkpoint → record health/circuit. A failure retries, trips the breaker, and records
health — **it never poisons other providers or the catalog** (fault isolation), and never
deactivates data on an empty/failed fetch.

**Projection + read path:** catalog changes emit "changed"; projections (search index, analytics,
later recommendations) update from the catalog. Search reads the catalog/index and ranks a
bounded top-K. **`SearchService`, the HTTP API, and the frontend are unchanged** — only what
`get_provider()` returns flips to the catalog-backed reader, warmed by an ingestion pass before cutover.

**The invariant:** the Catalog is the single source of truth; everything else is a rebuildable
projection or a reaction to catalog events.

---

## Part 5 — Execution model: event-driven is canonical

**The production architecture is event-driven and continuous** (modification 2). Ingestion
workers run continuously, consuming jobs from a durable queue that is fed by the Scheduler
(time-based due events) and by catalog events (e.g. an approved provider, a re-parse request).
Catalog writes emit "changed" events that drive projections and enrichment. This is the
canonical model everything is designed against.

The **policy** (metadata-driven scheduling, retry, rate-limit, circuit, checkpoints, capability-
aware fetching) is identical regardless of how workers are triggered. Only the **trigger +
storage substrate** vary by environment, entirely behind the Job-Queue/Worker seam:

- **Production:** continuous worker processes pulling a **durable queue**, writing to **managed
  durable Postgres**. Freshness is tiered by source velocity; workers react to events, not a clock.
- **Development / ₹0 free hosting:** a *scheduled-batch* trigger (GitHub Actions cron / Supabase
  scheduled function / Render cron) invokes one orchestrated pass over due providers with bounded
  in-process concurrency, writing to SQLite (dev) or free managed Postgres. This is a **degraded
  trigger for the same policy** — a stand-in for continuous workers where always-on compute isn't
  available, never the target architecture.

Because both run the same policy behind the same abstractions, moving from the free-hosting
scheduled-batch to production continuous workers is a **deployment swap, not a rewrite**. The
architecture assumes continuous event-driven ingestion; scheduled-batch is only how we operate it
cheaply until always-on compute is in place.

---

## Part 6 — Migration path (sub-phases, small & test-guarded)

- **3B Repository v2** — bulk upsert · keyset pagination · streaming iterate (retire `all()`) ·
  `status` lifecycle + archive seam · Provider State Store + checkpoints · versioning. SQLite impl.
- **3C Ingestion Runner + Capability Registry + Sandbox** — wrap today's providers as plugins
  (unchanged) with declared metadata **and capabilities**; one provider end-to-end: fetch →
  normalize → classify → resolve-vs-DB → bulk upsert → checkpoint → health; Retry/Rate-limit/
  Circuit around the fetch (capability-aware: delta vs full, paginate or not). New providers
  onboard through the **Sandbox pipeline** (validated before production). Manually triggerable.
- **3D Scheduler + Job Queue/Worker abstractions** — metadata-driven due-selection, bounded
  concurrency, priority, jitter; in-process execution behind the queue/worker seams; expiry + archive jobs.
- **3E Catalog-backed Search + cutover** — read from the catalog behind the unchanged provider
  contract; warm the catalog first; flip `get_provider()`; add full-text search.
- **3F Observability** — analytics from the State Store + Catalog; provider-health dashboard;
  growth/freshness history; Registry as the single source of truth.
- **Phase 4+** — Postgres/Supabase backend (same abstraction), search index projection, data-driven
  source quality, then the domain generalization and user-facing phases from the mapping.

---

## Part 7 — Consolidated: freeze vs change

**Frozen (do not touch):** the `EventProvider` source-adapter contract · `SearchService` &
`QueryParser` interfaces + AI-safety invariant · the storage abstraction/port · the
`get_provider()` swap seam · the published HTTP/discovery contract · the frontend · the `Event`
field set + `EventCategory` (until Phase 5) · the individual providers' fetch/normalize internals
(reused verbatim) · the pure dedup/city/ranking functions.

**Must change before/at implementation:** retire composite-as-search (fan-out becomes bounded
scheduled ingestion) · Repository v2 (bulk/paginate/iterate/status/archive/state, remove `all()`) ·
providers gain declared metadata + explicit fetch-all/delta (drop per-instance cache) · dedup →
write-time entity resolution vs DB candidates · analytics reads state+catalog via one registry ·
`_SOURCE_QUALITY` → data-driven from health · `event_key` identity fallback.

---

## Decisions — resolved (2026-07-15)

1. **Scope envelope:** the searchable catalog is designed to scale to **millions** with no
   architectural change (modification 1); the small active set is data context, not a constraint.
   Freshness is tiered by source velocity; entity resolution (not fetch) is the real hard problem.
2. **Execution model:** **event-driven continuous workers are the production model** (modification
   2); scheduled-batch + managed Postgres is the dev/free-hosting trigger behind the same policy.
3. **3B scope:** proceed with **Repository v2** as scoped in Part 6, plus the **Provider State
   Store** (both are storage). The **Capability Registry** (3C) and **Sandbox pipeline** (3C/3F)
   are now part of the plan.

Architecture documents stop here. Implementation proceeds at **3B — Repository v2**.
