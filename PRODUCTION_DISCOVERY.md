# Production Discovery — operating the real pipeline (Phase 10A)

A companion to [REAL_DISCOVERY_EXECUTION.md](REAL_DISCOVERY_EXECUTION.md), focused on running the real
discovery pipeline in production: the seed strategy, what to configure, how to deploy it, what to watch,
and how it scales. ₹0-budget by default; every paid upgrade is optional.

## Seed strategy

Discovery starts from a **curated, versioned seed list** (`app/execution/seeds.py`,
`SEED_LIST_VERSION`). Seeds are public entry points across eight categories — universities, developer
communities, conferences, hackathons, OSS foundations, meetup communities, technology companies, public
calendars — chosen because they either *are* event sources or *link to* them densely. The crawler
expands their links, so a good seed is one whose page is rich in outbound event/community links.

Principles:
- **Versioned.** Every run records the seed-list version it started from, so a change in yield can be
  traced to a change in seeds. Bump the version when you edit the list.
- **Breadth over depth.** A wide, shallow seed set + link expansion finds more than a narrow, deep one.
- **Robots is the authority, not the list.** Listing a domain is a hint; the crawler still honours that
  site's robots.txt at fetch time, so a seed can never override a site's wishes.
- **Curate, don't scrape, the seed list.** It's hand-maintained data reviewed by a human — the one part
  of discovery that is intentionally not autonomous.

`ProductionSeedList.sample(n)` returns a deterministic, category-spread subset for a small run.

## Configuration

| Env var | Effect |
|---|---|
| `GOOGLE_API_KEY` + `GOOGLE_CX` | use Google Programmable Search for the Search stage |
| `BING_API_KEY` | use Bing Web Search |
| `SERPAPI_KEY` | use SerpAPI |
| *(none)* | **DuckDuckGo HTML** (zero-key default) |

Everything else has sane defaults: `respect_robots=True`, `revisit_hours=24`, `max_pages`, per-kind
budgets (crawl/search/AI/page/provider/depth), and an injectable clock. Pass a `SQLiteOrchestratorStore`
to make runs durable/resumable.

## Deployment

- **Daily batch (recommended start).** Run `RealDiscoveryPipeline.run_cycle(...)` once per day from a
  scheduler (cron / a scheduled job), seeded from the production list, writing to a `SQLiteDiscoveryInbox`
  and a `SQLiteOrchestratorStore`. Emit `DailyMetrics.as_dict()` to your logs/dashboard. This matches the
  "daily metrics" framing and keeps the footprint tiny (the spike run was ~0.8 MB of traffic for 12
  pages).
- **Resumable.** With the orchestrator store configured, a crashed or killed run resumes from its last
  checkpoint (`resume()` re-queues interrupted stages); the expansion checkpoint store additionally skips
  URLs crawled within the refresh window, so re-runs are cheap.
- **Politeness is non-negotiable in prod.** Keep robots on, keep the rate limiter and per-run budgets in
  place, and keep the user-agent identifiable (`EventScoutDiscoveryBot`). These are already the defaults.
- **Discovery only.** The pipeline stops at the Discovery Inbox (`status=NEW`). Onboarding/promotion and
  the catalog are separate, human-gated systems — the real pipeline never writes to them.

## What to watch (daily metrics)

| Metric | Healthy signal | Investigate when |
|---|---|---|
| pages crawled / skipped | steady; skips are mostly robots/non-HTML | skips spike (a site blocked us, or errors) |
| new domains / new sources | growing across days | flat (seed list stale or frontier exhausted) |
| accepted / rejected | rejects are a small, explainable set | rejects dominate (relevance threshold or robots) |
| duplicate rate | modest and stable | ~100% (re-discovering the same set — widen seeds) |
| crawl cost (bytes) | within budget | climbing without new sources (crawl-efficiency drop) |
| discovery precision (gate) | high | high *and* inbox review disagrees → gate too loose |

Precision here is the **gate** precision (accepted/judged); track it alongside human inbox-review
outcomes, because a lenient gate can show 100% while surfacing noise (e.g. individual GitHub profiles).

## Scaling path

- **Now (10A):** single process, one daily cycle, SQLite persistence, DuckDuckGo. Correct, ₹0, polite.
- **Better yield:** add a keyed search provider (one env var) and grow/curate the seed list. Biggest
  quality lever, small cost.
- **More throughput within a process:** the orchestrator already models concurrency via leases; run a few
  stages in parallel (guarded by the existing lease manager) before going distributed.
- **Horizontal (9B):** many workers sharing one pipeline via a distributed lease backend + task queue
  (the 9B seams). The crawl/fetch/verify components are already stateless per URL, so this is a backend
  swap, not a rewrite.
- **Reach pure-runtime SPAs (10B):** a headless browser (the 8E `BrowserRenderer` seam) for sites that
  expose nothing in served bytes — the one class of source 10A structurally cannot see.

## Limitations (operational, honest)

- **Yield depends on the seed list and the (free) provider.** Keyless search contributes little; most
  real discovery comes from crawling the seeds, so a stale seed list means a stale pipeline.
- **The gate is precision-lenient by design.** It filters robots/access/noise, not event *truth*. Expect
  some non-event sources (user profiles, generic pages) in the inbox for a human to reject.
- **No continuous daemon yet.** 10A gives a real, resumable *cycle*; running it forever on a schedule is
  an ops wiring step, not code proven in this phase.
- **Redundant fetches at scale.** Expansion and the page fetcher fetch some seed pages independently;
  fine for a daily batch, worth a shared cache before high-volume operation.
- **Single point of failure between checkpoints.** Durability is per-cycle (per stage); a crash mid-stage
  replays that stage, so engine runs must stay idempotent.

## Honest self-review

- **It really runs, but "production" is a daily batch, not a service.** The pipeline fetches the real web
  correctly and resumably; standing it up as an always-on, monitored service (alerting on the metrics
  above, rotating seed lists, quota management) is described here but not delivered.
- **Free-tier reality.** The ₹0 default (DuckDuckGo) is honest about its weakness — the docs and metrics
  make the low search yield visible rather than hiding it behind a paid key.
- **Politeness verified, not just claimed.** The live spike skipped robots-disallowed content and stayed
  within a small budget; the integration tests prove a disallowed origin is never discovered. That's the
  one guarantee we most need to be true, and it is.

---

**Status:** 10A complete — additive, real execution, public-content-only, robots-respected,
discovery-only; 594 tests green. **Stopping here — Phase 10B (Browser Rendering & JavaScript Execution)
NOT started.**
