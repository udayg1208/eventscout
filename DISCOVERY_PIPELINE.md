# Discovery Pipeline — D1

The D1 flow, the live discovery statistics, a coverage report, and a critical self-review.

## Pipeline

```
 Seed URLs                     curated organizer domains (GDG, FOSS United, Hasgeek, Lu.ma, CNCF)
   │
   ▼
 Crawler                       polite (robots + rate-limit + scope + checkpoint), NO JavaScript
   │   fetched raw bytes
   ▼
 Link Extractor                <a href> (same-domain) · <link rel=alternate> feeds · <loc> sitemaps
   │
   ▼
 Feed Detector ┐               RSS · Atom · ICS · JSON Feed · XML/Event sitemap · Google Calendar
 Structured    │  detect_feeds  JSON-LD Event · Microdata Event · OpenGraph event
 Data Detector ┘               (one page → possibly several detections)
   │
   ▼
 Candidate Builder             page-level types → one candidate per domain; feeds → per-URL
   │
   ▼
 Confidence Signals            deterministic booleans/counts (NO final score)
   │
   ▼
 Discovery Inbox               persisted, deduped, status=NEW  ── STOP (no onboarding, no ingestion)
```

Each stage is a pure, testable unit. The crawler seeds its frontier from robots-declared
sitemaps, then expands via feed-autodiscovery links, same-domain `<a>` links, and sitemap
`<loc>` entries — all bounded by `max_pages` / `max_depth` and gated by robots + scope +
checkpoint.

## Live discovery statistics (real run, `spikes/d1_discover.py`)

5 seeds, `max_pages=18`, `max_depth=2`, 0.2s rate-limit, SQLite persistence.

| Seed | Pages | Candidates | Feed types |
|---|---|---|---|
| hasgeek.com | 18 | 8 detections | JSON-LD Event |
| fossunited.org | 18 | 1 | **RSS (feed with 20 events)** |
| gdg.community.dev | 18 | 0 | — (SPA) |
| community2.cncf.io | 14 | 9 detections | JSON-LD Event |
| lu.ma | 18 | 0 | — (SPA / `__NEXT_DATA__`) |

**Aggregate:** 86 pages fetched · 18 detections → **3 unique candidate sources** (inserted=3,
updated=15 — within-run page-level dedup) · 90 crawl checkpoints persisted.

**Candidate sample:**

| feed_type | domain | structured | tech_conf | india_conf | events | title |
|---|---|---|---|---|---|---|
| jsonld_event | cncf.io | 1 | 1.0 | **0.0** | 1 | KCD Suisse Romande 2026 |
| jsonld_event | hasgeek.com | 1 | 0.6 | 0.5 | 1 | July 2023 Rust Meetup |
| rss | fossunited.org | 1 | 1.0 | 1.0 | 20 | (FOSS United feed) |

**Incremental re-run (Run 2, same checkpoint):** pages=0 · inserted=0 · updated=0 → inbox still
3. **Duplicates prevented** two ways: crawl-checkpoint (no re-fetch) + inbox dedup (no duplicate
candidate).

## Coverage report

- **Sources discovered:** 3 distinct candidate sources from 5 seeds — a **JSON-LD** source
  (Hasgeek), a **JSON-LD** source (CNCF), and a real **RSS feed with 20 events** (FOSS United)
  found fully automatically.
- **Feed-type coverage exercised live:** JSON-LD Event, RSS. The other detectors (ICS/Atom/JSON-
  Feed/sitemap/Google-Calendar/Microdata/OpenGraph) are covered by deterministic fixture tests.
- **Signal quality:** the India signal correctly separated the Swiss KCD page (`india=0.0`) from
  the India sources (`india=0.5–1.0`); tech signal fired on all three. These are exactly the
  signals a later Confidence Engine + validator will gate on.
- **Dedup:** 18 raw detections → 3 sources (6× compression) via domain-level collapse; 0
  duplicates on re-run.
- **Politeness:** robots respected; identifiable UA; rate-limited; bounded.

## Critical self-review (challenging the implementation)

**Limitations**
- **SPA blindness (the big one):** GDG + Lu.ma yielded **0** because their events are JS/`__NEXT_
  DATA__`-rendered — D1 reads raw HTML only. This under-counts modern community platforms. Cheap
  fix: add a deterministic `__NEXT_DATA__`/embedded-JSON detector (Lu.ma/Next.js sites expose
  event JSON in the shell); deeper fix: D3 rendered/AI extraction.
- **Seed-bound breadth:** D1 only expands *within* seed domains. It cannot find *new* organizers
  — that is precisely D2 (search-engine discovery).
- **Candidate granularity:** a domain-level JSON-LD candidate says "this domain publishes events"
  but not *where the repeatable listing/feed is* — a later step must resolve the actual ingestion
  endpoint.

**Failure modes**
- **Bot-blocking:** a Cloudflare/anti-bot seed returns non-200/None → 0 candidates (handled: the
  fetcher returns None, the crawler counts an error and continues; we never bypass protection).
- **Robots over-restriction:** a strict robots.txt legitimately blocks crawl → low yield (correct
  behavior, not a bug).
- **Malformed/huge feeds:** bounded by `max_bytes` + defensive parsing (bad JSON/XML → skipped).
- **Crawl traps:** mitigated by URL normalization + visited-set + `max_pages`/`max_depth` +
  sitemap-loc cap.

**False positives**
- A **JSON-LD Event on a non-tech or non-India page** becomes a candidate — but the signals
  capture it (`india_conf=0.0`, low `tech`), so the later validator/Confidence Engine can reject
  it. D1 deliberately favors **recall** (collect + signal) over precision (judge) — judging is a
  later phase. The Swiss KCD candidate is the intended shape: kept, but flagged non-India.
- A stale single-event page could be surfaced; domain-level dedup + `has_recurring`/`event_count`
  signals give the validator what it needs to discount it.

**False negatives**
- SPAs (above); sites exposing events only via authenticated APIs; feeds requiring headers we
  don't send. Accepted for D1.

## Future integration

- **D2 — search-engine discovery:** feed the crawler's seed frontier from search-API results
  (`site:meetup.com <city> <topic>`, `site:*.community.dev`), unlocking *new* domains beyond the
  seed list. The pipeline downstream of "Seed URLs" is unchanged — D2 just supplies more seeds.
- **AI (later, assist-only):** a `__NEXT_DATA__`/unstructured-HTML extractor for SPA sites, an
  organizer-clustering step, and a quality/relevance pre-filter — all **grounded** (validated
  against the fetched page) and never auto-promoting a candidate. AI proposes; the deterministic
  pipeline + human review dispose.

**Stop:** D1 is complete. D2 is **not** started.
