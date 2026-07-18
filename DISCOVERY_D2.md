# Discovery Engine — D2 (Modern Web Framework Discovery)

D2 extends the Discovery Engine to find candidate event sources **hidden inside modern
JavaScript applications** — Next.js (`__NEXT_DATA__` / App Router Flight), Nuxt, Apollo,
`window.__INITIAL_STATE__`, generic embedded JSON, and client API / GraphQL endpoints — all
extracted from the **raw served HTML with zero JavaScript execution**. No Playwright, no
Selenium, no headless browser.

Like D1, D2 is **purely additive** and **discovers sources only**. Output stops at the
Discovery Inbox (`status=NEW`); nothing reaches the Catalog, Repository, Registry, Scheduler,
Search, Frontend, or API. Those systems are **untouched**.

Code: `backend/app/discovery/` (new files `frameworks.py`, `hydration.py`, `endpoints.py`,
`analysis.py`; additive edits to `models.py`, `signals.py`, `candidates.py`, `store.py`,
`engine.py`).

## Why D2 exists

D1's live verification exposed one blind spot precisely: **GDG and Lu.ma returned 0 candidates**.
Their pages carry no JSON-LD / RSS / ICS in the markup D1 inspects — the events live in a
hydration payload (`__NEXT_DATA__`) or an embedded JSON blob that the browser would turn into
DOM, but that D1 never looked inside. D2 looks inside.

The key realization: **this was never a JavaScript problem.** The event data is already present
in the initial HTML response as serialized JSON — it just isn't in `<script type="ld+json">`.
You don't need to *run* the app to read its hydration state; you need to *parse* it. D2 does
exactly that, deterministically.

## What D2 adds

| Capability | Detector | Source label |
|---|---|---|
| Next.js Pages Router | `__NEXT_DATA__` JSON script | `next_data` |
| Next.js App Router (RSC) | `self.__next_f.push([...])` Flight strings | `next_flight` |
| Nuxt 3 | `__NUXT_DATA__` JSON script | `next_data` |
| Nuxt 2 | `window.__NUXT__` (IIFE, fallback scan) | `embedded_json` |
| Apollo | `window.__APOLLO_STATE__` | `hydration_state` |
| Redux/other | `window.__INITIAL_STATE__`, `__PRELOADED_STATE__` | `hydration_state` |
| Generic embedded JSON | `<script type="application/json">` blobs | `embedded_json` |
| Client API endpoints | `/api/...` paths + absolute `…api…` URLs | `json_api` |
| GraphQL endpoints | `/graphql`, `/gql` references | `graphql` |

Every detector is **deterministic regex / JSON parsing** over the HTML string. Full detector
mechanics are in **[FRAMEWORK_DISCOVERY.md](FRAMEWORK_DISCOVERY.md)**.

### New deterministic signals

Added to `ConfidenceSignals` (still booleans/counts — **no weighted verdict**):
`has_framework, has_nextjs, has_hydration, has_embedded_events, has_json_array,
has_calendar_schema, has_api_endpoint, has_graphql_endpoint`. `has_embedded_events` and
`has_hydration` also count toward the transparent `structured_data_score`.

### New candidate fields

`CandidateSource` gains: `framework`, `framework_version`, `api_endpoints`, `graphql_endpoints`,
`hydration_source`, `embedded_event_count`. Persisted to SQLite in an additive `framework_data`
JSON column (with an `ALTER TABLE` migration for any pre-D2 inbox).

### Candidate keys (dedup)

D2 page-level payloads are a property of the page shell, so they collapse **per-domain**:
`next_data`, `next_flight`, `hydration_state`, `embedded_json` → `domain#feed_type` (one
candidate per domain, like D1's JSON-LD). Endpoints (`json_api`, `graphql`) key by their **full
URL** — each endpoint is a distinct probe target.

## Pipeline integration

The engine loop is unchanged in shape — D2 slots in beside D1 detection:

```
crawl page → detect_feeds() [D1] ─┐
             analyze_frameworks() [D2] ─┴→ merge (dedup by feed_type+url)
           → collect_signals(…, analysis)   → build_candidate(…, analysis)   → inbox.upsert
```

`analyze_frameworks()` runs on **every** page. A page with no framework payload and no endpoints
yields an empty D2 detection list and costs only regex scans — the merge is then a no-op and
behavior is identical to D1.

## Live verification — D1 vs D2 (5 seeds, network, no JS)

`spikes/d2_discover.py`, same seeds as D1, bounded (≤18 pages/seed), robots-respecting,
rate-limited. Per page it computes **both** what D1 (`detect_feeds`) finds and what D2
(`analyze_frameworks`) adds, then reports the delta.

```
  seed          pages  framework                  embedded_events  D1_cands  D2_new  api gql
  GDG            18     —                                48          0         1       0   0
  Lu.ma          18     Next.js pages-router×18          64          0         1       0   0
  Hasgeek        18     —                                 8          1         1       3   0
  FOSS United    18     —                                 0          1         0       1   0
  CNCF           14     Next.js pages-router×9           70          1         9       7   0

  AGGREGATE
  pages crawled ............ 86
  frameworks detected ...... {'Next.js pages-router': 27}
  embedded events found .... 190
  D1 candidate sources ..... 3
  D2 NET-NEW candidates .... 12      ← sources D1 alone could not see
  D2 detection feed types .. {'next_data': 15, 'embedded_json': 10, 'json_api': 7}
  API endpoints discovered . 11
  GraphQL endpoints ........ 0
  inbox total (D1+D2) ...... 15
  false-positive guard ..... 2 framework pages had 0 events → emitted NO candidate
```

### What this proves

- **The named blind spot is closed.** GDG (0 → 1 candidate, via `embedded_json`, 48 event-shaped
  objects) and Lu.ma (0 → 1, via `next_data`, 14 objects on its richest page) — the two examples
  in the phase brief — now both produce candidates. D1 saw nothing on either.
- **D2 is strictly additive to coverage.** D1's 3 real candidates (Hasgeek JSON-LD, FOSS United
  RSS, CNCF JSON-LD) are all still found; D2 adds **12 net-new** on top (4× the D1 yield) without
  removing or altering any D1 result.
- **Framework detection is not a prerequisite.** GDG and Hasgeek expose events via
  `embedded_json` with **no** recognized framework marker — the extractors fire independently of
  `detect_framework`. Detection is a *signal*, not a *gate*.
- **The false-positive guard holds in the wild.** 2 Next.js pages carried a `__NEXT_DATA__`
  payload with zero event-shaped objects and correctly produced **no** event candidate.

## Testing

`tests/test_discovery.py` — **34 tests total, 19 new for D2**, fully deterministic, no network
(`StaticFetcher` + inline fixtures), one fixture per framework/payload shape:

- **FrameworkDetector** across all 11 families + the no-framework case.
- **Hydration/NextData/State/EmbeddedJSON extractors** — parse success, Nuxt2-function
  non-parse (documented limit), ld+json exclusion, Flight decode, event-object counting,
  signature counting.
- **API/GraphQL endpoint detection** — event-ranked ordering, absolute + relative, caps.
- **analyze_frameworks** — Pages Router, App Router Flight, Apollo, initial-state, framework-less
  embedded JSON, Nuxt2 fallback, endpoints, and the **marketing-page no-false-positive** case.
- **Signals + candidate builder** — D2 field population, `domain#type` vs per-URL keying,
  `event_count` folding.
- **SQLite `framework_data` round-trip.**
- **End-to-end**: a Next.js SPA whose events exist **only** in `__NEXT_DATA__` — asserts D1 finds
  no event feed, yet the engine emits a candidate with `framework=Next.js`,
  `embedded_event_count=2`.

Full suite: **407 passed** (388 pre-D2 + 19), ruff-clean.

## Critical self-review

### Remaining blind spots

1. **`embedded_event_count` is a recall proxy, not a verified count.** It counts *event-shaped*
   dicts (a name-key **and** a date-key, or `@type:Event`). GDG's 48 and CNCF's 43 almost
   certainly include **past events, chapter metadata, and duplicated objects** — it is an
   upper-bound-ish relevance signal, **not** a promise of N ingestible upcoming events. This is
   deliberate (D2 favors recall; judging is deferred), but it must not be read as a clean count.
2. **Third-party endpoint noise.** CNCF surfaced 7 `googleapis.com` `json_api` candidates — these
   are Google Calendar API URLs referenced by the page, i.e. **cross-domain, third-party, and
   near-duplicate**. The endpoint detector surfaces any event-ish URL; it does not yet distinguish
   first-party event APIs from third-party services, nor dedup query-string variants. First-party
   filtering + endpoint dedup belong in the later validation phase.
3. **Page metadata bleeds onto endpoint candidates.** An endpoint candidate inherits the
   *discovering page's* `framework` and `embedded_event_count` (e.g. the googleapis candidates
   show `fw=Next.js ev=3`). That is the page's context, not the endpoint's own — defensible as a
   relevance hint, but a reviewer must not read it as "this endpoint returned 3 events."
4. **Nuxt 2 IIFE payloads are not truly parsed.** `window.__NUXT__=(function(){…})()` is a
   function body, not a JSON literal. We fall back to a **text signature scan** of the raw HTML,
   which only catches quoted date-key signatures. Unquoted-key or minified Nuxt2 state can slip
   through with `embedded_event_count=0` even when events exist.
5. **App Router Flight and GraphQL were not exercised live.** All 5 seeds are Next.js *Pages*
   Router or framework-less; none stream RSC Flight, none reference `/graphql`. Both detectors are
   built and unit-tested, but their live behavior on real App-Router / GraphQL sites is still
   unverified — a genuine gap, not a claim of coverage.
6. **Deeply nested or truncated payloads.** `find_event_objects` is bounded (200k nodes) and
   `_balanced_after` caps at 2 MB. A pathologically large or server-truncated hydration blob can
   under-count. Bounded-by-design (DoS safety) but a real recall ceiling.

### Why browser automation is still unnecessary

Every one of the 190 embedded events and 15 candidates was extracted from the **initial HTML
response** with **no JS executed**. Modern frameworks serialize their state *into the HTML* for
hydration — `__NEXT_DATA__`, Flight chunks, `window.__*__`, `<script type=application/json>` are
all present in the raw bytes precisely so the client can rehydrate without a second round-trip.
Running a headless browser would reconstruct the same DOM from the same bytes we already read —
at 10–100× the cost, with new failure modes (timeouts, anti-bot, resource limits) and a much
larger, harder-to-audit dependency surface. For **source discovery**, parsing the payload
dominates executing it. Browser automation only becomes arguably necessary for sites that fetch
**all** event data client-side after load with **nothing** serialized in the initial HTML — and
for those, the honest answer is the discovered **API endpoint** (D2's `json_api`), which is
cheaper to probe directly than to drive a browser.

### Where D3 (AI extraction) begins

D2 finds *where* events are and *roughly how many*. D3 turns that into clean, structured events:

- **Semantic event extraction** — collapse the 48/43 recall-proxy counts into a deduplicated,
  upcoming-only list mapped to the event schema. Requires understanding arbitrary, unlabeled JSON
  shapes — the job of a model, not a regex.
- **Schema-agnostic endpoint mapping** — probe a discovered `json_api`, receive JSON in an unknown
  shape, and map it to `title/date/city/url`. Also: tell a first-party event API from
  `googleapis.com` noise by **meaning**, not string match.
- **Tolerant payload parsing** — Nuxt 2 function bodies, truncated/streamed Flight, and other
  non-JSON serializations that deterministic parsing can only proxy.

D2's boundary is deliberate: **deterministic recall of candidate sources**, everything explainable
from the bytes. The moment a step needs to *understand* content rather than *locate* it, it is D3.

---

**Status:** D2 complete. Additive; frozen contracts untouched; 407 tests green; blind spot closed
and measured. **Stopping here — D3 not started.**
