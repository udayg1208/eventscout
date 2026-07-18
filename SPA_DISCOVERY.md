# SPA Discovery — how EventScout sees events behind JavaScript (Phase 8E)

A companion to [RENDERED_DISCOVERY.md](RENDERED_DISCOVERY.md), focused on the *why*: how modern
single-page apps hide their event data, and the deterministic strategy 8E uses to recover it **without
a browser**.

## The problem: `View Source` is empty

Traditional discovery (D1) reads server-rendered HTML — `<article>`, JSON-LD, RSS. But a growing
share of event sites are SPAs: the server returns a near-empty shell —

```html
<div id="__next"></div>
<script id="__NEXT_DATA__" type="application/json">{ …250 events… }</script>
<script>const API="/api/events"; fetch(API).then(hydrate)</script>
```

— and the browser builds the page at runtime. A classic crawler sees an empty `<div>` and concludes
"no events here." The events are right there in the bytes, just not as HTML. **8E reads the bytes a
browser would hydrate from, instead of the HTML a browser would render.**

## Two ways in (no browser required)

### 1. Hydration state — the events are already in the page

Frameworks serialize their initial state into the served bytes so the client can hydrate without a
round-trip. That serialized state is a gift to discovery:

| Framework | Where the state lives |
|---|---|
| Next.js (Pages) | `__NEXT_DATA__` JSON script |
| Next.js (App Router) | `self.__next_f.push([...])` RSC Flight stream |
| Vue / Nuxt | `window.__NUXT__`, `window.__INITIAL_STATE__` |
| React + Apollo | `window.__APOLLO_STATE__` (GraphQL normalized cache, `ROOT_QUERY`) |
| Redux / generic | `window.__PRELOADED_STATE__`, `window.__INITIAL_STATE__` |
| Astro / Remix / Gatsby / Svelte | embedded `application/json` islands / loader data |

`collect_hydration()` parses each, and counts event-shaped objects inside (name-key **and** date-key,
or `@type=="event"`). A 250-event page yields one payload: `__NEXT_DATA__ → 250 events`.

### 2. Hidden APIs — follow what the page fetches

When the events *aren't* fully in the initial state, the page fetches them from an API. That endpoint
is the real prize: `/api/events` may return **thousands** of events in one call — a far richer, more
stable source than scraping paginated HTML. `discover_endpoints()` finds it from JS call-sites —
`fetch()`, `axios()`, `XMLHttpRequest.open()`, config objects, GraphQL references, and quoted
API/feed URL literals (including the common `const url = "…"; fetch(url)` variable-indirection) — and
records it as a **lead**. The endpoint is **never called** in 8E.

> A hidden `/api/events` endpoint turns "crawl 500 HTML pages" into "one JSON request." Finding it is
> often more valuable than parsing the current page.

## Why no browser — and what that costs

8E is deliberately **no-browser, no-JS-execution, no-network**. Benefits: it's deterministic (same
bytes → same result, fully testable with fixtures), fast, cheap (₹0), and safe (it cannot click,
log in, or trigger side effects). The cost is real and honestly acknowledged: a **pure-runtime SPA**
that ships no state and assembles its API URL dynamically at runtime exposes nothing to a byte
reader. Those need a headless browser to execute the JS and observe the hydrated DOM / network calls
— that's the `BrowserRenderer` seam, deferred to a later phase behind explicit approval.

In practice, most React/Next/Vue/Nuxt event sites *do* serialize state or reference their API in
readable JS, so the byte-level approach recovers the majority — and it does so with zero runtime risk.

## The AI decision

Extraction produces signals; the reasoning layer produces a **verdict**. For each page the (currently
deterministic, mock) `AIReasoner` answers: *Is this an event source? Which is the cheapest reliable
path to its events (hydration blob vs hidden REST API vs GraphQL vs feed)? Can it become a provider,
and as what type?* — attaching confidence, cited evidence, and an honest list of the fields it did
**not** yet parse. A real LLM (`GeminiReasoner`) plugs into the same seam later under the same
never-fabricate / cite-evidence / return-unknown contract.

## Where it stops

Every SPA the engine judges an event source becomes a Discovery Inbox candidate
(`discovered_by="rendered"`, `status=NEW`), and every hidden event API becomes its own `JSON_API` /
`GRAPHQL` candidate. **Nothing is onboarded automatically** — the inbox is a human review queue. See
[RENDERED_DISCOVERY.md](RENDERED_DISCOVERY.md) for the full architecture, the endpoint-source table,
the confidence weights, the live spike output, and the complete honest self-review.

## Honest self-review (SPA-specific)

- **Byte-level ≠ browser-level.** We recover serialized state and *referenced* endpoints, not runtime
  behavior. Pure-runtime SPAs (no serialized state, dynamically-built API URLs) are a genuine blind
  spot until the browser seam ships — not a bug, a scope boundary.
- **Framework detection is a hint, not a gate.** Extraction keys on blob *shapes*, so it survives an
  unrecognized framework — but a site using a bespoke hydration variable we don't enumerate will be
  missed by the state parser (though its API may still be found via JS call-sites).
- **"Full dataset likely larger" is an inference.** We never call `/api/events`, so we can't confirm
  it returns events or how many; the claim is a reasoned lead, and `ApiProber` (deferred) is what
  would verify it.
- **Recall over precision, by design.** Better to surface a lead for human review than to silently
  drop a real SPA event source. Some candidates won't pan out; the inbox review step is the safeguard.

---

**Status:** 8E complete. Additive, discovery-only, no browser/JS-execution/network; 543 tests green.
**Stopping here — Phase 9 (Autonomous Multi-Agent Discovery & Continuous Learning) NOT started.**
