# Search Provider Architecture — Phase 8B

How EventScout talks to real search engines: one contract, four implementations, and a clear-eyed
comparison of Google vs SerpAPI vs Bing vs DuckDuckGo. Companion to
**[WEB_DISCOVERY_ENGINE.md](WEB_DISCOVERY_ENGINE.md)** (the engine that consumes them).

## The contract

Every provider implements a single method — the D3 `SearchProvider` contract plus a `configured`
flag:

```python
class WebSearchProvider(SearchProvider):
    name: str
    @property
    def configured(self) -> bool: ...            # has the credentials it needs
    async def search(self, query, *, limit=10) -> list[SearchResult]: ...
```

`SearchResult` is `{title, url, snippet, rank, engine}` — the same object the D3 pipeline already
consumes, so parser, ranking, and candidate-building are reused unchanged. **All provider-specific
logic (endpoint, auth, params, response shape) lives inside the provider**; the engine never branches
on provider identity. Adding a fifth provider is one file — implement `search`, map the response to
`SearchResult`. Credentials come from `SearchProviderConfig` (env/secrets), never hardcoded.

## The four providers

### Google Programmable Search (`google.py`)
- **Endpoint:** `GET https://www.googleapis.com/customsearch/v1?key=…&cx=…&q=…`
- **Auth:** API key + a Programmable Search Engine id (`cx`).
- **Response:** `items[]` → `{title, link, snippet}`.
- **Quota:** 100 queries/day free; then $5 / 1,000, capped at 10k/day. Max 10 results/page.
- **Verdict:** the highest-quality first-party index; the free tier is tiny, so the cache is
  essential. Best default when a key is available.

### Bing Web Search v7 (`bing.py`)
- **Endpoint:** `GET https://api.bing.microsoft.com/v7.0/search` with `Ocp-Apim-Subscription-Key`.
- **Response:** `webPages.value[]` → `{name, url, snippet}`.
- **Quota:** tiered subscription (S1–S6); roughly $15–25 / 1,000.
- **Verdict:** strong coverage, generous page size (up to 50), good `mkt` locale control for India.
  Pricier than Google's paid tier. (Note: Microsoft has announced changes to Bing Search APIs;
  verify availability before committing.)

### SerpAPI (`serpapi.py`)
- **Endpoint:** `GET https://serpapi.com/search.json?engine=google&q=…&api_key=…`
- **Response:** `organic_results[]` → `{title, link, snippet, position}`.
- **Quota:** plan-based; ~$8–15 / 1,000 depending on plan.
- **Verdict:** returns *Google* results without Google's `cx`/quota friction, plus rich SERP
  features. A paid aggregator — convenient, not cheap. Good when you want Google quality with less
  setup.

### DuckDuckGo (`duckduckgo.py`) — zero-key
- **HTML mode:** `GET https://html.duckduckgo.com/html/?q=…`, parse `result__a` anchors, decode the
  `/l/?uddg=…` redirector back to the real URL.
- **IA mode:** `GET https://api.duckduckgo.com/?q=…&format=json`, read `RelatedTopics[].FirstURL`.
- **Auth:** none.
- **Verdict:** the only free/keyless option — invaluable for a demo and a fallback, but **not
  production-grade**: the HTML endpoint throttles and varies markup for automated clients (the live
  spike parsed 0 results), and the IA API returns encyclopedic answers, not a `site:`-filtered SERP.

## Comparison at a glance

| | Google PSE | Bing v7 | SerpAPI | DuckDuckGo |
|---|---|---|---|---|
| Key required | key + cx | subscription key | api_key | none |
| Response | JSON `items[]` | JSON `webPages` | JSON `organic_results` | HTML scrape / IA JSON |
| Free tier | 100/day | trial | trial | unlimited* |
| ~Cost / 1k | $5 | $15–25 | $8–15 | $0 |
| `site:` support | yes | yes | yes | HTML: partial |
| Result quality | highest | high | high (Google) | variable |
| Reliability | high | high | high | low (scrape) |
| Best for | default (keyed) | locale/volume | Google-via-API | demo / fallback |

\* subject to throttling / anti-bot.

## Recommended configuration

- **Production:** Google Programmable Search as the primary (best quality/cost with the cache),
  SerpAPI as a paid fallback when Google's daily cap is hit. Set `GOOGLE_API_KEY` + `GOOGLE_CX`.
- **Cost control:** the 24h cache + query budget keep real API spend a fraction of raw query count
  (EventScout's query set is small and stable). Tier queries so high-yield ones (8A boost) run more
  often.
- **Demo / no budget:** DuckDuckGo, understanding it's best-effort.

The engine picks the first configured provider automatically (`_configured_provider` in the spike),
so switching is an env-var change — no code change.

## Failure & quota handling

Each provider raises `ProviderError` on network failure, non-2xx (after `PoliteFetcher` backoff),
auth/quota errors (e.g. Google's `error.message`, SerpAPI's `error`), or unparseable JSON. The
engine catches it per query, counts it, and continues — a single quota-exhausted or flaky query
never aborts a discovery run. Quota exhaustion therefore degrades to "fewer new candidates this
cycle", not a crash.

## Honest limitations

- **No keys were available in this environment**, so Google/Bing/SerpAPI are built and unit-tested
  against mocked HTTP but unverified against the live APIs (real pagination, quota codes, locale
  behavior may differ in detail).
- **DuckDuckGo scraping is inherently brittle** and demonstrably returned nothing live — it is a
  fallback, not a dependency.
- **Provider quality/cost figures are indicative**, not contractual; verify current pricing and API
  availability before production.
- **One page per query.** The providers request a single result page (≤ the provider's page cap);
  deep pagination is deferred.

---

**Status:** four real providers behind one reused contract, credential-driven and hot-swappable via
env, with defensive failure/quota handling. The engine stays provider-agnostic; the cache keeps it
affordable. Keyed providers are the production path; DuckDuckGo is the keyless fallback.
