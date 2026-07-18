# Real Discovery Execution — Phase 10A

Replaces the mock discovery pipeline with **real-world execution**: the existing engines, wired to the
live internet and driven continuously by the orchestrator. This phase adds no architecture and no new
abstraction layer — it is the wiring that makes the platform autonomously discover new event sources
from public web content. Everything is additive; every engine is reused unchanged.

Code: `backend/app/execution/` (new package). **Public content only; robots.txt respected; rate-limited;
discovery only; the catalog is never touched; no browser, no JS execution, no auth.**

## What was reused (unchanged) vs. added (additive)

| Reused (frozen) | Role |
|---|---|
| `HttpxFetcher` / `StaticFetcher` / `Fetcher` (D1) | real HTTP fetch; `StaticFetcher` mocks it in CI |
| `RobotsCache` (D1) | real robots.txt fetch + parse + per-origin cache |
| `PoliteFetcher` + Google/Bing/SerpAPI/DuckDuckGo providers, `SearchCache`, `RateLimiter` (8B) | real search with 24h cache + rate limiting |
| `ExpansionEngine` (8C) | real polite crawl (robots + budget + freshness + graph) |
| `SocialDiscoveryEngine` (8D) · `RenderedDiscoveryEngine` (8E) | real extraction from fetched HTML |
| `WebDiscoveryEngine` (8B) · `DiscoveryInbox` (D1) | query→candidates; the terminal sink |
| `OrchestratorEngine` (9A) | the loop: retries, checkpoints, resume, graceful stop |

| Added in `app/execution/` | Role |
|---|---|
| `seeds.py` | the **versioned production seed list** (data) |
| `providers.py` | env-driven real-provider selection (lifts the 8B spike logic into app code) |
| `fetching.py` | `PageFetcher` — polite fetch-once glue (D1 fetcher + robots + cache) for the processor engines |
| `verification.py` | `SourceVerifier` + `VerifyingInbox` — the validation gate (implements the existing inbox ABC) |
| `metrics.py` | `ExecutionMetrics` / `DailyMetrics` — the operational daily numbers |
| `runners.py` | the real `StageRunner`s (the live implementations of the 9A seam) |
| `engine.py` | `RealDiscoveryPipeline` — the top-level wiring |

Nothing in `app/discovery`, `app/onboarding`, `app/operations`, the orchestrator, the frontend, or the
API was modified.

## Execution flow

```
production seed list (versioned)
   │  seed the frontier
   ▼
OrchestratorEngine  ── cycle ──▶ planner picks the next stage by priority + backlog + budget
   │
   ├─ Search    → WebDiscoveryEngine.run(spec)  → real provider (DuckDuckGo/Google/…) → candidates
   ├─ Expansion → ExpansionEngine.expand(seeds) → real polite crawl (robots+budget+freshness)
   ├─ Social    → PageFetcher.fetch(url) → SocialDiscoveryEngine.discover([(url, html)])
   └─ Rendered  → PageFetcher.fetch(url) → RenderedDiscoveryEngine.discover([RenderedPage])
   │
   ▼
VerifyingInbox  ── robots · accessibility · relevance · freshness · duplicate ──▶ Discovery Inbox (NEW)
   │
   ▼
ExecutionMetrics → DailyMetrics
```

The social and rendered engines don't fetch, so the runners fetch each seed page **once** through a
shared `PageFetcher` (robots-gated, cached) and hand the same real HTML to both — polite and efficient.
Search runs on its cadence (hourly) and then yields to the backlog-driven crawl/extract stages, so a
seeded batch drains Search → Expansion → Social/Rendered → Inbox and the loop goes idle.

## Verification — every candidate validated before the inbox

`VerifyingInbox` implements the existing `DiscoveryInbox` ABC, so the engines upsert through it with no
change. Each candidate must pass five checks or it never enters the inbox:

1. **Robots** — `RobotsCache.allowed(url)` (legality by construction).
2. **Accessibility** — a real public `http(s)` URL with a host.
3. **Event relevance** — carries a tech/event/structured signal (confidence, `ConfidenceSignals`,
   classification, or embedded-event count), not noise.
4. **Freshness** — a source seen within the revisit window (24h) isn't re-processed.
5. **Duplicate detection** — an already-known key is a duplicate, not a new discovery.

Rejected and duplicate candidates are counted, never inserted; the reasons feed the metrics.

## Real provider selection

`build_web_provider(fetcher, env)` picks the first configured provider —
`GOOGLE_API_KEY`+`GOOGLE_CX` → Google, else `BING_API_KEY` → Bing, else `SERPAPI_KEY` → SerpAPI —
and falls back to the **zero-key DuckDuckGo HTML provider**, so a real search source always exists.
This is the 8B spike's selection logic, now in application code.

## Daily metrics

`DailyMetrics`: **pages crawled, pages skipped, new domains, new sources, new inbox candidates,
accepted, rejected, duplicate rate, crawl cost (bytes), discovery precision** (accepted/(accepted+
rejected) at the gate). Fed by the `PageFetcher` stats, the crawler's report, and the `VerifyingInbox`
result callback. Complements the orchestrator's own loop metrics.

## Reliability — reused from the orchestrator

Retries (a failed stage backs off and dead-letters), **checkpoint resume** (`SQLiteOrchestratorStore`
persists state every cycle; `resume()` restores it), crawl continuation (the expansion checkpoint store
skips recently-crawled URLs), graceful shutdown (`stop()` is checked between cycles), and partial
restart (crashed stages are re-queued) all come from the 9A orchestrator, unchanged.

## Live demonstration (real internet)

`backend/spikes/p10a_real_execution.py` runs the real pipeline over five polite production seeds
(python.org/events, confs.tech, fossunited.org, hasgeek.com, cncf.io/events) with DuckDuckGo, a small
page budget, and robots respected. An actual run:

```
provider: duckduckgo
seed list: 5 polite seeds from production vspike

DISCOVERY INBOX (45 candidates, all status=NEW)
  [expansion] rss           https://peps.python.org/peps.rss
  [expansion] rss           https://pyfound.blogspot.com/feeds/posts/default?alt=rss
  [expansion] search_result https://github.com/python
  [expansion] search_result https://github.com/fossunited
  [expansion] search_result https://t.me/RustIndia
  …

DAILY METRICS
  pages crawled       : 12
  pages skipped       : 3   (robots / non-HTML / errors)
  new domains         : 6
  new sources         : 45
  accepted / rejected : 45 / 0
  duplicate rate      : 8.16%
  crawl cost          : 804,366 bytes
  discovery precision : 100.00%  (accepted / judged, at the gate)
```

Real public pages fetched, real feeds and communities discovered, robots honoured, nothing onboarded.

## Tests

`backend/tests/test_real_execution.py` — **14 tests, mocked HTTP (`StaticFetcher`) + fixture sites,
no network**: the versioned seed list; the env provider factory (all four providers); the `PageFetcher`
(fetch, cache-hit, robots-skip, non-HTML/error-skip); the `SourceVerifier` (each of the five checks);
the `VerifyingInbox` gate + delegation; the daily metrics (precision, duplicate rate, new domains); the
**full integration cycle** (Search→Expansion→Social→Rendered→inbox, a robots-blocked origin never
discovered, metrics populated); and reliability (checkpoint + resume, graceful shutdown). Full backend
suite: **594 passed**.

## Honest self-review

**Truly true**
- This is real execution: the spike fetched real pages over HTTP, honoured every site's robots.txt,
  and discovered real feeds/communities into the inbox. Every candidate passes an explicit five-check
  gate. CI stays hermetic because the one fetch interface (`Fetcher`) and the provider are injectable.

**Weaknesses / limitations**
1. **Keyless search is weak.** DuckDuckGo HTML throttles and its markup shifts, so the Search stage
   often contributes little; the real yield comes from crawling the seed list. A keyed provider
   (Google/Bing/SerpAPI) is a one-env-var upgrade but costs money — deliberately not required.
2. **Link-crawl noise.** Expansion surfaces every in-scope link, so crawling a contributors page yields
   individual GitHub *user* profiles (`github.com/<user>`) alongside real orgs. They pass the gate
   (accessible + community-ish) but aren't event sources. Precision here is *gate* precision
   (accepted/judged), **not** ground-truth precision — only human inbox review or a later validation
   pass confirms a source is real.
3. **Rendered reasoning is still the deterministic mock.** 10A makes the rendered engine process *real*
   fetched pages, but the reasoner is `MockAIReasoner` (rule-based). Real execution, mock reasoning — a
   real LLM reasoner remains a later, opt-in seam.
4. **Redundant fetches.** Expansion crawls a URL with its own crawler while the `PageFetcher` fetches
   the same seed pages for social/rendered; the two don't share a cache (different components). The
   `PageFetcher` cache dedups social↔rendered, and rate-limiting keeps it polite, but a seed page can be
   fetched more than once. Acceptable at this scale, wasteful at large scale.
5. **Social needs platform URLs.** The social engine only matches known platforms (LinkedIn/GitHub/…);
   generic seed pages route to expansion/rendered instead, so social contributes only when a seed *is* a
   social URL.
6. **Verification is pre-inbox, not post-inbox.** The gate checks robots/accessibility/relevance/
   freshness/duplicate at insert time. It does **not** re-fetch to confirm a source is still live, nor
   validate event *content* — that (and promotion) is onboarding's job, deliberately downstream.
7. **Single-process, one cycle per invocation.** The daily-metrics framing implies a scheduled daily
   run; wiring it to a real scheduler/cron and running continuously in production is an operational step
   (see [PRODUCTION_DISCOVERY.md](PRODUCTION_DISCOVERY.md)), not proven here.

## Where Phase 10B begins (NOT this phase)

10A reads served bytes only. **Phase 10B — Browser Rendering & JavaScript Execution** — would add a
headless browser to render pure-runtime SPAs (the `BrowserRenderer` seam from 8E) and observe their
network calls, reaching sources that expose nothing in the raw HTML. It needs browser automation and is
out of 10A's scope.

---

**Status:** 10A complete. Additive; every engine reused unchanged; 594 tests green; real HTTP + robots
+ rate limits; public content only; discovery only; catalog untouched; no browser/JS/auth. **Stopping
here — Phase 10B NOT started.**
