# Discovery Engine — D1 (Structured Discovery)

The first production implementation of the Event Discovery Engine. It **discovers candidate
event sources** from publicly accessible structured data — it does **not** ingest events.
Output stops at the Discovery Inbox (`status=NEW`); nothing reaches production automatically.

Code: `backend/app/discovery/` (new, fully additive). Frozen systems — SearchService,
Repository, Provider interfaces, Scheduler, Registry, Catalog, Search, Frontend, API — are
**untouched**.

## What D1 does

Given a small seed list of known organizer domains, it politely crawls each (robots-aware, no
JavaScript), detects structured event data (RSS/Atom/ICS/JSON-Feed/sitemap/JSON-LD/Google-
Calendar/Microdata/OpenGraph), builds a `CandidateSource` with **deterministic signals**, and
persists it to the Discovery Inbox — deduplicated. It answers *"which domains publish
ingestible events?"*, not *"what events exist"*.

## Package structure

```
app/discovery/
  models.py       FeedType, DiscoveryStatus, ConfidenceSignals, CandidateSource, CrawlRecord
  urls.py         normalize_url · registrable_domain · same_scope (dedup + scope)
  fetch.py        Fetcher protocol · HttpxFetcher (prod) · StaticFetcher (tests) — NO JS engine
  robots.py       parse_robots · RobotsPolicy.allowed · RobotsCache (per-origin)
  links.py        <a href> · <link rel=alternate> feeds · <loc> sitemap entries
  feeds.py        detect_feeds(FetchResult) -> [FeedDetection]  (the detection core)
  signals.py      collect_signals(...) -> ConfidenceSignals  (deterministic, reuses 5A taxonomy)
  candidates.py   build_candidate(...) -> CandidateSource
  store.py        DiscoveryInbox + CrawlCheckpointStore (InMemory + SQLite)
  crawler.py      Crawler (frontier · robots · scope · rate-limit · checkpoint · bounds)
  engine.py       DiscoveryEngine.run(seeds) -> DiscoveryReport  (the orchestrator)
```

## Candidate Source model

A candidate is a discovered *source* (a feed URL, or a domain that publishes event pages),
keyed for dedup. Structured *pages* (JSON-LD/Microdata/OpenGraph — one event each) collapse to
**one candidate per domain** (`example.org#jsonld_event`); *feeds* (RSS/ICS/sitemap) key by
their own URL. Stored fields include: `url, domain, feed_type, title, organization, country,
city`, the per-dimension **deterministic aggregates** (`technology_confidence, india_confidence,
professional_confidence, structured_data_score`), the raw `signals`, `discovery_path` (seed →
… → url), `status`, timestamps, `version`, and history.

**No final confidence score** is computed in D1 (that is the later Confidence Engine's job) —
only transparent booleans/counts. The "confidence" fields are simple documented aggregates of
signals, not a weighted verdict.

### Confidence signals (deterministic)

Structured presence: `has_jsonld_event, has_microdata_event, has_opengraph_event, has_rss,
has_atom, has_ics, has_json_feed, has_sitemap, has_google_calendar`. Content: `tech_keyword_count`
(via the catalog's own 5A tech taxonomy), `india_reference_count`, `has_organizer`,
`has_registration_link`, `has_recurring`, `event_count`.

## Discovery Inbox

Storage-agnostic (`DiscoveryInbox` ABC) with `InMemoryDiscoveryInbox` (tests) and
`SQLiteDiscoveryInbox` (persistence). Supports `upsert` (dedup by key — re-discovery updates +
bumps version, preserves `first_seen_at` and any manually-advanced status), `get`, `list`
(by status), `set_status` (manual approve/reject for later phases), `count`. A sibling
`CrawlCheckpointStore` (InMemory + SQLite) persists visited URLs + timestamps for **incremental
crawling** (skip recently-crawled) and resume.

## Crawler

Polite and bounded: honors `robots.txt` (Allow/Disallow longest-match, Crawl-delay, Sitemap
directives), stays inside configured domains, normalizes + dedups URLs (no loops), bounds work
(`max_pages`, `max_depth`, `max_sitemap_locs`), rate-limits via an injectable interval, and
consults the checkpoint store. **No JavaScript** — reads raw HTML/feed bytes only (no
Playwright/Selenium), as required. It seeds the frontier from robots-declared sitemaps, follows
feed-autodiscovery `<link rel=alternate>`, same-domain `<a>` links, and sitemap `<loc>` entries.

## Safety / additivity

- **Additive**: a self-contained package; imports only leaf utilities (`app.city`,
  `app.enrichment.taxonomy`) read-only. Touches no frozen module.
- **Nothing auto-promotes**: every candidate is `NEW`; advancing it is manual (`set_status`) and
  belongs to the later Auto-Onboarding phase.
- **Legality by construction**: identifiable UA (`EventScoutDiscoveryBot/1.0`), robots respected,
  rate-limited, bounded, no auth/anti-bot bypass.
- **Deterministic**: every detector/signal is a pure function of the fetched bytes (fixture-tested
  without network).

## Tests

`tests/test_discovery.py` — 15 deterministic, network-free tests (StaticFetcher + fixtures):
URL normalization, registrable-domain/scope, robots parsing (allow/disallow/delay/sitemap),
RSS/Atom/ICS/JSON-Feed/JSON-LD/Microdata/OpenGraph/Google-Calendar detection, event-vs-plain
sitemap, signal generation, candidate keys/aggregates, inbox dedup + status + SQLite persistence,
crawl checkpoint, crawler robots+scope enforcement, and a full engine end-to-end crawl.
**388 backend tests pass, lint clean.**

## Known limitations (D1)

- **SPAs are invisible to D1.** GDG and Lu.ma render events in JavaScript/`__NEXT_DATA__`, so
  raw-HTML structured discovery finds 0 (verified live). D1 finds server-rendered structured
  data only. Fixes: a `__NEXT_DATA__`/embedded-JSON detector (cheap, deterministic) or D3
  (AI/rendered extraction).
- **Discovery breadth = the seed list.** D1 expands *within* seed domains; it does not find *new*
  domains — that is D2 (search-engine discovery).
- **Candidate ≠ validated provider.** Signals are collected, not judged; onboarding is a later
  phase.

See `DISCOVERY_PIPELINE.md` for the stage-by-stage flow, live statistics, coverage report, and
critical self-review.
