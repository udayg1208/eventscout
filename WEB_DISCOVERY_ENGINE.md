# Web Discovery Engine — Phase 8B

The first phase that talks to the **real internet**. It replaces the D3 mock search with real
search providers (Google Programmable Search, Bing, SerpAPI, DuckDuckGo) behind a 24-hour cache,
rate limiting, robots, and backoff — and continuously discovers entirely new event sources from the
public web. Output stops at the **Discovery Inbox**; nothing is onboarded or promoted.

Code: `backend/app/discovery/web/` (new subpackage — additive). No browser, no Playwright/Selenium,
no LLM. Strictly additive: Search, the Repository, the Catalog, providers, ingestion, the scheduler,
the frontend, and the API are all untouched.

## Architecture

The engine reuses the entire D3 pipeline and 8A prioritization, swapping only the search source from
mock to real:

```
QuerySpec → build_queries (D3) → prioritize (8A gaps + query optimizer)
          → execute (real provider, 24h cache, rate limit, budget)
          → normalize (strip tracking, canonical URL, domain)  → dedupe across queries
          → score (D3 ranking) → build candidate (D3) → Discovery Inbox (status=NEW)
```

```
app/discovery/web/
  interfaces.py   WebSearchProvider contract (= D3 SearchProvider + `configured`) + SearchProviderConfig
  google.py       GoogleProgrammableSearchProvider  (Custom Search JSON API)
  bing.py         BingWebSearchProvider             (Bing Web Search v7)
  serpapi.py      SerpApiSearchProvider             (SerpAPI google engine)
  duckduckgo.py   DuckDuckGoProvider                (zero-key: HTML SERP or Instant-Answer JSON)
  fetch.py        PoliteFetcher (UA + timeout + backoff) + RobotsGate (reuses D1 robots)
  cache.py        SearchCache (24h TTL, normalized keys, invalidation, stats)
  rate_limit.py   RateLimiter (per-provider spacing) + DomainGuard + Budget (query cap)
  normalizer.py   normalize_results (reuses D3 parser) + tracking-param stripping + dedupe_across
  engine.py       WebDiscoveryEngine.run(spec) → WebDiscoveryReport
```

## Provider layer

Every provider implements one method — `search(query) -> list[SearchResult]` — and **all
provider-specific request/response logic lives inside that provider**. The engine only ever sees
`SearchResult`s. A provider exposes `configured` so the engine can pick one that actually has its
credentials (Google/Bing/SerpAPI need keys; DuckDuckGo does not). Full comparison in
**[SEARCH_PROVIDER_ARCHITECTURE.md](SEARCH_PROVIDER_ARCHITECTURE.md)**.

## Caching

`SearchCache` is a 24-hour TTL cache keyed by `(provider, normalized query)`:

- **Query normalization** — case-fold + whitespace-collapse, so trivially different queries share an
  entry.
- **Duplicate suppression** — the same normalized query never calls out twice inside the window; a
  hit is served from cache instead of the (rate-limited, possibly paid) provider.
- **Invalidation** — clear all, per-provider, or a single query; plus `evict_expired`.
- **Stats** — hit/miss counts and hit rate. In the demo, a second identical run served 3/3 queries
  from cache (hit_rate climbing to 0.5 over both runs).

The cache is both a cost control (fewer paid API calls) and the primary politeness mechanism (fewer
outbound requests).

## Rate limiting & safety

Never hammer a provider or a domain:

- **RateLimiter** — enforces a minimum spacing between calls per provider (e.g. 12/min → ≥5 s
  apart), with an injectable clock/sleep (deterministic in tests).
- **DomainGuard** — a per-domain minimum interval so no single domain is queried back-to-back.
- **Budget** — a hard cap on queries per run (the crawl-budget ceiling).
- **Robots** — `RobotsGate` (reusing the D1 robots parser) checks the HTML-scrape host's robots.txt
  before fetching; the JSON APIs are authorized calls. Discovered URLs are *not* fetched here — the
  eventual D1/D2 crawl already robots-checks each page.
- **Backoff** — `PoliteFetcher` retries 429/5xx with exponential backoff, then gives up gracefully
  (a `ProviderError` the engine catches and counts — one bad query never crashes a run).

## Failure handling

Every outward call is defensive. A provider that errors (network, quota, auth, parse) raises
`ProviderError`; the engine logs it, counts it in `provider_errors`, and continues with the next
query. A run therefore degrades gracefully: partial results, never a crash. The live demo section is
written the same way — any network failure is caught and reported honestly, and the offline section
still demonstrates the full pipeline.

## Cost analysis (per 1,000 queries)

| Provider | Cost model | ~Cost / 1k queries | Keyless? |
|---|---|---|---|
| Google Programmable Search | 100/day free, then $5/1k (cap 10k/day) | $5 (after free tier) | No |
| Bing Web Search v7 | tiered; ~$15–25/1k (S1–S6) | ~$15–25 | No |
| SerpAPI | plan-based; ~$8–15/1k depending on plan | ~$8–15 | No |
| DuckDuckGo (HTML/IA) | free | $0 | Yes |

The 24h cache is what makes this affordable: EventScout's query set (city × tech × platform) is
small and stable, so most cycles are near-100% cache hits and real API spend is a fraction of the
raw query count. DuckDuckGo is free but unreliable for structured discovery (see limitations).

## Live demonstration

`spikes/p8b_web_discovery.py` runs two sections:

- **LIVE (real internet):** the zero-key DuckDuckGo provider, polite (robots-checked, rate-limited,
  cached, budget 3). In this environment it executed 3 real queries with `provider_errors=0` (HTTP
  succeeded) but parsed **0** usable results — the keyless DDG HTML endpoint returned a page our
  scraper didn't match (DDG throttles / varies markup / serves a lite or consent page for
  bot-like clients). The spike reports this honestly.
- **OFFLINE (deterministic):** the identical engine over a static fixture SERP → 3 queries, 4
  results, 4 unique, **4 candidates inserted** across `meetup.com` + `community.dev`, all
  `discovered_by=search, status=NEW`; a second run served 3/3 from cache and re-discovered nothing.

Together they show the pipeline is real and correct, and that keyless DDG scraping is not a reliable
production source — which is precisely why an API-keyed provider is recommended for real use.

## Testing

`tests/test_web_discovery.py` — **13 tests, every provider mocked, NO real network**: response
mapping for Google/Bing/SerpAPI (+ missing-key → not configured / ProviderError), DuckDuckGo HTML
parsing (redirect decode), `PoliteFetcher` retry-then-succeed and give-up-after-retries, cache
hit/miss/expiry/invalidate + query normalization, rate-limiter spacing, budget cap, tracking-param
stripping + dedupe, and the end-to-end engine (discovers, caches on re-run, updates the inbox,
respects the budget, handles provider errors). Full backend suite: **492 tests**.

## Honest limitations

1. **Keyless DuckDuckGo is unreliable for structured discovery.** The HTML endpoint throttles and
   varies its markup for automated clients (the live demo parsed 0 results); the Instant-Answer API
   is stable but returns encyclopedic answers, not a `site:`-filtered SERP. DDG is a demonstrable
   zero-cost fallback, not a production source. **Real discovery needs an API-keyed provider**
   (Google/Bing/SerpAPI).
2. **No API keys in this environment.** All keyed providers are built and unit-tested against mocked
   HTTP, but none could be exercised live here. Their real behavior (quota errors, pagination,
   locale) is unverified against the actual APIs.
3. **HTML scraping is brittle by nature.** The DDG parser is regex over a specific class markup; any
   layout change breaks it. This is inherent to scraping and a reason to prefer JSON APIs.
4. **Discovery only, no crawl.** The engine discovers URLs; it does not fetch the discovered pages
   (that is D1/D2, which robots-checks each). "Respect robots" here covers the scrape host only.
5. **Prioritization is coarse.** 8A reuse floats gap-matching queries first and drops
   historically-retired ones, but it's a simple sort, not a learned scheduler.
6. **The cache is in-memory.** A 24h cache that survives process restarts needs the SQLite backend
   (the interface is ready; the persistent impl is future work).

## Where Phase 8C begins (NOT this phase)

8B discovers from the real web into the Discovery Inbox and stops. Phase 8C would go further —
autonomous, continuous web expansion driving itself from the optimizer's recommendations, multi-
provider fan-out with real keys, and closing the discover→act loop. That is a larger grant of
autonomy and requires explicit approval.

---

**Status:** 8B complete. Additive; frozen systems untouched; 492 tests green; real providers built +
tested, polite (robots/rate-limit/cache/backoff), stops at the Discovery Inbox. **Stopping here —
Phase 8C NOT started.**
