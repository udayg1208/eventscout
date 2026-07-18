# Search Discovery Engine — D3 (Search-Based Source Discovery)

D3 turns EventScout from a crawler of **known** domains into a system that discovers **entirely
new** ones. D1 finds feeds on domains you already seeded; D2 finds framework-hidden data on domains
you already seeded. Neither finds a website EventScout has never heard of. D3 does: it asks a
web-search engine for pages matching deterministic queries, scores each discovered source, and
inserts the promising ones into the Discovery Inbox.

**Discovery only.** D3 does not ingest events, create providers, or write to the catalog. Output
stops at the Discovery Inbox (`status=NEW`), exactly like D1/D2. Everything is additive — no
change to ingestion, providers, catalog, scheduler, registry, the app's SearchService, frontend,
or API.

Code: `backend/app/discovery/search/` (new, self-contained) + additive fields on the existing
Discovery Inbox.

## Pipeline

```
QuerySpec ─▶ Generate Queries ─▶ Search ─▶ Parse ─▶ Rank ─▶ Deduplicate ─▶ Discovery Inbox
            query_builder.py   search.py  parser  ranking   dedup+frontier   store (SEARCH_RESULT)
```

| Module | Responsibility |
|---|---|
| `query_builder.py` | Expand a `QuerySpec` (city × tech × platform × event-type × university × company) into deterministic query strings. **No LLM.** |
| `search.py` | `SearchProvider` ABC (web-search seam) + `MockSearchProvider` (deterministic, corpus-backed, no network). |
| `parser.py` | Normalize each result → `ParsedResult` (canonical URL, registrable domain, title/snippet, provenance). Drop junk + in-set dupes. |
| `ranking.py` | Deterministic `DiscoveryScore` from title+snippet+url+domain. Weighted signals; off-topic penalties. |
| `frontier.py` | Track known/seen/pending URLs + known domains so identical pages are never rediscovered (seeded from the inbox → cross-run). |
| `dedup.py` | Collapse identical URLs surfaced by different queries, keeping the strongest rank. |
| `engine.py` | Orchestrate the pipeline; build `SEARCH_RESULT` candidates; upsert to the inbox. |
| `interfaces.py` | Future real-engine seams (Google/Bing/SerpAPI) — **interface only, no network**. |

## Why search precedes crawling

A crawler can only deepen coverage of domains it already has; it cannot expand the **set** of
domains. The event ecosystem's long tail — a single college's IEEE branch, a city's Python user
group, one company's dev-events page — is invisible until someone names the domain. A search engine
is precisely the index of "domains that exist and match these words." So the correct order is:

1. **Search** discovers *where* sources are (new domains/URLs) — cheap, broad, index-backed.
2. **Crawl (D1/D2)** determines *what* each source publishes (feeds, JSON-LD, hydration payloads).
3. **Ingest** (a later phase) pulls the actual events.

D3 is step 1. A `SEARCH_RESULT` candidate is a lead — a page the D1/D2 crawler should visit next.
That hand-off is why the frontier maintains a `pending` queue: discovered URLs are the crawler's
future seed list.

## Deterministic ranking

`score_source(parsed) -> DiscoveryScore` scores a discovered page from **search metadata alone**
(we have not crawled it yet). It is a **search-relevance rank** — "how worth inspecting is this
page?" — not the deferred Confidence Engine's onboarding verdict, which still requires a real crawl.

Weighted signals (`WEIGHTS`, single source of truth), reusing the catalog's own 5A tech taxonomy
and `city.detect_city` so "technology" and "India" mean the same here as everywhere else:

| Signal | Weight | Fires when |
|---|---|---|
| technology | 0.30 | taxonomy topic/tech terms in title+snippet (normalized by count) |
| india | 0.20 | `.in` domain, "india", or a detected Indian city |
| city | 0.10 | a known city is present |
| meetup | 0.15 | meetup/user-group/chapter/GDG terms, or a known meetup-platform domain |
| conference | 0.10 | conference/summit/devfest/PyCon/… terms |
| rss | 0.05 | URL looks like a feed (`/feed`, `.xml`) |
| jsonld | 0.05 | domain is a known schema.org-Event platform (Hasgeek/Eventbrite/…) |
| known_community | 0.15 | a curated community name (GDG/FOSS/CNCF/PyData/IEEE/…) in text or domain |

**Penalties** subtract for off-topic pages that superficially look "event-y": entertainment/music/
movies, tourism/travel, shopping/commerce terms (−0.4), and known off-topic domains like
`bookmyshow.com`, `makemytrip.com`, `flipkart.com` (−0.6). `total = clamp(raw − penalty, 0, 1)`.
Every score carries a `reasons` tuple, so any decision is explainable. Candidates below
`min_score` (default 0.3) are counted and dropped, never inbox'd.

## Extended Discovery Inbox (additive migration)

`CandidateSource` gains four provenance fields (defaults keep every existing D1/D2 candidate
valid): `discovered_by` (`"crawl"` | `"search"`), `search_query`, `search_rank`, `search_engine`.
A new `FeedType.SEARCH_RESULT` marks "a page found by search, type not yet crawled." In SQLite
these persist in an additive `search_data` JSON column with an `ALTER TABLE` migration for any
pre-D3 inbox — **no breaking schema change**, existing rows read back with `discovered_by="crawl"`.

Search sources key by **normalized URL** (each page is a distinct source), so the same page found by
ten queries collapses to one candidate.

## Live demonstration (mock, no network)

`spikes/d3_search_discovery.py` runs the full pipeline over a mock corpus standing in for Meetup /
GDG / FOSS / Hasgeek / IEEE / university / company / conference pages plus off-topic noise:

```
GENERATE  51 deterministic queries
SEARCH → PARSE → RANK → DEDUPLICATE → INBOX
    results found ......... 324   (parsed rows across all queries)
    unique after dedup .... 16
    duplicates removed .... 308
    below threshold ....... 3     (BookMyShow, MakeMyTrip, a signal-less college fest → rejected)
    accepted / inserted ... 13
    discovered domains .... 10    community.dev · fossunited.org · google.com · hasgeek.com ·
                                  iitb.ac.in · meetup.com · nitk.ac.in · pycon.org ·
                                  razorpay.com · reactindia.io
RUN 2 (frontier seeded from inbox): inserted=0, skipped_known=13 → never rediscovered
```

Note the honesty of the failure modes: Flipkart (shopping) matched **no** query and never surfaced;
BookMyShow/MakeMyTrip surfaced on city queries but were penalized below threshold; a college tech
fest with no technology keyword and no city scored 0.24 and was correctly dropped.

## Testing

`tests/test_search_discovery.py` — **17 deterministic tests, no network, no API keys**: query
generation (determinism, templating, dedupe, limit), the `site:`/terms query parser, the mock
provider (site filter incl. subdomain hosts, term ranking, empty results), result parsing
(normalization, junk/dupe rejection), ranking (high for real meetups, penalized noise, conference/
JSON-LD signals, determinism), URL dedup (best-rank retention), frontier novelty + cross-run
seeding, candidate construction + field mapping, SQLite provenance round-trip, and two end-to-end
engine runs (discovery+filtering, duplicate suppression + incremental no-op). Full backend suite:
**424 tests**.

## Future Google / Bing integration

`interfaces.py` fixes the seam now so a later phase supplies the HTTP call **without touching the
engine**. Each is a `SearchProvider` subclass whose `search()` currently raises `NotImplementedError`:

- `GoogleProgrammableSearchProvider` — Custom Search JSON API (`items[]` → `SearchResult`); free
  tier ~100 queries/day.
- `BingWebSearchProvider` — Bing Web Search (`webPages.value[]` → `SearchResult`).
- `SerpApiSearchProvider` — third-party SERP aggregator.
- `RateLimitedSearchProvider` — wrapper enforcing per-engine rate limit / daily quota (same limiter
  shape as the scheduler), required before any paid/quota'd engine goes live.
- `SearchProviderConfig` — the config surface (api_key/endpoint/engine_id/quota), supplied via
  secrets, **never hardcoded**.

### Migration path

1. Implement one provider's `search()` (map the engine's JSON to `SearchResult`).
2. Wrap it in `RateLimitedSearchProvider` with a `SearchProviderConfig` from env/secrets.
3. Swap it in for `MockSearchProvider` at the engine's construction site.
4. **Everything downstream — parser → ranking → dedup → frontier → inbox — is unchanged.** The mock
   already exercises the exact same contract, so tests stay green and only the network edge is new.

## Scaling to millions of discovered pages

- **Query volume is a product, not a fetch.** `|cities| × |tech| × |platforms| + …` grows fast;
  `build_queries` de-duplicates and accepts a `limit`, and a real engine's rate limit (not CPU) is
  the bound. Scale by tiering queries (run high-yield templates often, long-tail rarely) rather than
  running the full cross-product every cycle.
- **The frontier is the scaling primitive.** Identity is URL/domain strings only; it seeds from the
  inbox so cross-run rediscovery is O(1) set membership. At millions of URLs this becomes a
  persisted set / Bloom filter (interface already isolates it) — never re-scoring or re-searching a
  known page.
- **Ranking is O(1) per result** (regex + set lookups, no network, no model), so scoring millions of
  results is bounded by search throughput, not compute.
- **Dedup collapses the long tail early** — the demo's 324 rows → 16 unique (95% duplication) is
  typical; the same handful of real sources recur across many queries, so inbox growth is far slower
  than query growth.
- **Storage** is the existing storage-agnostic inbox (SQLite now, Postgres later with zero app
  change), so the discovered-source table scales the same way the catalog does.

## Limitations (honest)

1. **No real engine yet** — by constraint, D3 runs on `MockSearchProvider`. The mock's substring
   matching is simpler than a real ranker; real SERPs bring spam, SEO noise, and paywalls the mock
   doesn't model. The pipeline is proven; live precision is unverified until a real provider lands.
2. **Ranking sees only the snippet.** A page's true value (does it actually list upcoming events?)
   is unknown until D1/D2 crawls it. D3 deliberately optimizes **recall of candidate domains**, not
   precision of event-bearing pages — some accepted candidates will crawl to nothing.
3. **Curated keyword/community lists** (known communities, penalty terms, JSON-LD domains) are
   hand-maintained and India-tuned; they won't generalize to new regions without extension, and a
   novel legitimate community with an unfamiliar name gets no `known_community` boost.
4. **Threshold is a blunt instrument.** A single `min_score` trades recall vs. noise globally; the
   college-fest example (0.24) shows real-but-weak sources can fall just under. Tuning per query
   family is future work.
5. **No feedback loop.** Queries are static templates; D3 doesn't yet learn which queries/domains
   historically yield ingestible sources (see SEARCH_QUERY_STRATEGY.md → future work).
6. **`site:` reach depends on the engine.** Discovery of `meetup.com/<group>` long-tail pages is
   only as complete as the engine's index of that site.

## Where D4 (AI extraction) begins

D3 hands D1/D2 a queue of new domains to crawl. Everything remains deterministic and explainable.
The moment a step needs to *understand* a discovered page's unstructured content — read a prose
"upcoming events" section a search snippet only hinted at, or judge relevance semantically rather
than by keyword — it is D4 (AI extraction), not D3.

---

**Status:** D3 complete. Additive; frozen contracts untouched; 424 tests green; discovery-only,
stops at the Discovery Inbox. **Stopping here — D4 (AI Extraction) not started.**
