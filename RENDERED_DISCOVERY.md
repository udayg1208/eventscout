# Rendered Discovery Engine — Phase 8E

Discovers events **hidden behind modern JS frameworks**. Many event sites (React/Next.js, Vue/Nuxt,
Angular, Astro, Remix, Gatsby, Svelte) ship almost no event HTML — the events live inside
`__NEXT_DATA__`, `window.__INITIAL_STATE__`, an Apollo/GraphQL cache, embedded JSON, or hydration
state, and the page fetches the rest from a **hidden API** (`/api/events` returning thousands of
rows). This engine reads the served bytes (HTML + JS + JSON), extracts those hydration blobs, counts
the events, discovers the hidden endpoints from JS call-sites, and runs a deterministic **AI
reasoning layer** that decides whether the site can become a provider — emitting a `ProviderCandidate`
with confidence, cited evidence, honestly-reported missing fields, and a recommended provider type.

**Discovery only. HTML/JS/JSON only — no browser, no JS execution, no network, no LLM.** Endpoints
are recorded as *leads and never called*. Output stops at the Discovery Inbox
(`discovered_by="rendered"`, `status=NEW`) — nothing is onboarded automatically.

Code: `backend/app/discovery/rendered/` (new subpackage — additive). It **reuses** D2's extractors
(`hydration`, `endpoints`, `frameworks`), D1's `urls` (domain/normalize) and `city.detect_city`, the
5A tech taxonomy, and the Discovery Inbox / `CandidateSource` model. It **modifies nothing** —
Search, Repository, Catalog, D1–D4, Expansion (8C), Social (8D), Onboarding (7A), Production (7B),
scheduler, frontend, and API are all untouched.

## Supported frameworks & hydration sources

| Framework | How events hide | Detected via |
|---|---|---|
| Next.js (Pages) | `<script id="__NEXT_DATA__" type="application/json">` | `__NEXT_DATA__` parse |
| Next.js (App/RSC) | `self.__next_f.push([...])` Flight stream | `__next_f` signature count |
| React + Apollo | `window.__APOLLO_STATE__` / `ROOT_QUERY` GraphQL cache | window-state parse |
| Vue / Nuxt | `window.__NUXT__` / `__INITIAL_STATE__` | window-state parse |
| Redux / generic SPA | `window.__PRELOADED_STATE__`, `window.__INITIAL_STATE__` | window-state parse |
| Any (webpack) | `webpackChunk`, `/_next/static/chunks/` | marker regex |
| Any (Vite) | `/@vite/client`, `/assets/index-*.js`, `import.meta.env` | marker regex |
| Any | `<script type="application/json">` blobs, microdata | embedded-JSON parse |

`HydrationSource` enumerates these. Framework *name* comes from D2's `detect_framework`; the
hydration layer works even when the framework is unknown (it keys on the blob shapes, not the name).

## Architecture

```
app/discovery/rendered/
  models.py      HydrationSource · EndpointKind · HydrationPayload · DiscoveredEndpoint
                 ProviderCandidate · RenderedReport
  hydration.py   collect_hydration() — reuses D2 extractors + Apollo/Nuxt/Preloaded/webpack/vite,
                 window_globals(), has_graphql_cache()
  endpoints.py   discover_endpoints() — D2 finders + fetch/axios/xhr/config/graphql/path/url call
                 sites; classify_endpoint() → REST/GraphQL/JSON/RSS/ICS/Calendar
  reasoning.py   AIReasoner (ABC) + MockAIReasoner — signals → ProviderCandidate (deterministic)
  prompts.py     SYSTEM_PROMPT + build_reasoning_prompt() — the contract a real LLM will get (unused)
  engine.py      RenderedDiscoveryEngine.discover(pages) → RenderedReport, upserts to the Inbox
  store.py       RenderedStore (InMemory + SQLite) — full per-URL reasoning record
  interfaces.py  future seams: GeminiReasoner · BrowserRenderer · ApiProber (all NotImplementedError)
```

Per page the flow is: **detect framework → `collect_hydration` → `discover_endpoints` → reason → gate
→ upsert candidate(s)**.

## Hydration extraction

`collect_hydration(html, scripts=None) -> list[HydrationPayload]` runs every extractor over the HTML
plus any supplied external JS, and for each blob counts event-shaped objects (reusing D2's
`find_event_objects`, which requires a name-key **and** a date-key, or `@type == "event"`). Each
`HydrationPayload` carries `{source, event_count, sample_title, top_keys}` — the top-level keys are
kept as evidence. Two correctness details:

- **No double-counting.** `__NEXT_DATA__` is itself `type="application/json"`, so the generic
  embedded-JSON extractor would re-match it; blobs equal to the parsed `__NEXT_DATA__` are skipped.
- **Unparseable payloads still count.** RSC Flight and webpack/Vite bundles can't be JSON-parsed, so
  they fall back to a deterministic text-signature count (Flight) or a presence marker (webpack/Vite)
  — nothing is silently dropped.

`window_globals(text)` lists every `window.__X__ =` global (hydration evidence); `has_graphql_cache`
flags an Apollo/`ROOT_QUERY`/`__typename` cache.

## Endpoint & API discovery — the hidden APIs

Instead of crawling HTML forever, `discover_endpoints(html, scripts, *, base)` finds the endpoint the
SPA fetches its events from. It scans **executable JavaScript only** (external scripts + inline
non-JSON `<script>` bodies) for call-sites, and runs D2's finders over the HTML **minus the JSON
hydration blobs**:

| Source | Pattern | Example |
|---|---|---|
| `fetch` | `fetch("…")` | `fetch("/api/events")` |
| `axios` | `axios.get/post/… ("…")` | `axios.get("https://api.host/v2/events")` |
| `xhr` | `.open("GET"\|"POST", "…")` | `xhr.open("GET","/api/e")` |
| `config` | `"apiUrl"\|"baseURL"\|… : "…"` | `{ apiUrl: "https://api.host" }` |
| `graphql` | any `…/graphql` reference | `"https://host/graphql"` |
| `js-path` | quoted **relative** `/api/…` or `/…events…` literal | `const API = "/api/events?city=blr"` |
| `js-url` | quoted **absolute** url naming `/api/`·`/events`·`.ics`·`.rss`·`/feed`·`/graphql` | `const cal = "https://host/events.ics"` |

`classify_endpoint(url)` → `REST` / `GRAPHQL` / `JSON` / `RSS` / `ICS` / `CALENDAR` / `UNKNOWN`.
Relative URLs resolve against the page `base`; templated/relative-fragment URLs we can't resolve
deterministically are skipped. Results are **event-relevant first** (URL contains "event"), then
alphabetical, capped at 25 to bound noise.

**Why scan executable JS only + strip the JSON blob?** A 250-event `__NEXT_DATA__` payload carries a
per-event detail URL for every row; scanning it would flood (and cap out) the real endpoint leads
with 250 detail pages. Excluding it keeps the genuine `/api/events` visible. This is a deliberate
precision choice, verified by test.

## AI reasoning layer

`MockAIReasoner.reason(url, *, framework, hydration, endpoints, html) -> ProviderCandidate` reasons
**deterministically** over the extracted signals (no LLM, no network — reproducible). It answers the
phase's questions and produces:

- `is_event_source` — true if any hydration blob carried events, or an event-relevant REST/JSON API
  was found, or a feed/calendar endpoint was found.
- `recommended_provider_type` — the cheapest reliable path to the events: `next_data` → `json_api`
  (hidden REST API) → `graphql` → `rss`/`ics` → `hydration_state` → `framework` → `crawl`.
- `confidence` (0–1), from **explainable evidence weights**: events in hydration `+0.4…0.6` (scales
  with count), an event API endpoint `+0.3`, a GraphQL endpoint `+0.2`, a feed/calendar `+0.15`, a
  detected framework `+0.1`.
- `evidence` — one cited line per contributing signal (e.g. *"`__NEXT_DATA__` carried 250 event
  object(s)"*, *"event API present → full dataset likely larger than the hydrated page"*).
- `missing_fields` — honestly, `[date, location, organizer, registration_url]` when it's an event
  source, because we counted events but did **not** parse each event's full schema.
- `answers` — `is_event / recurring / organizer / location / registration_url / technology /
  community / can_be_provider`. Anything the signals don't support is `"unknown"` — never guessed.

`prompts.py` holds the exact contract a future real LLM will be given (never fabricate, cite
evidence, return unknown, never call an endpoint). It is **not executed** in 8E.

## Output → Discovery Inbox

A page that reasons to `is_event_source` (and clears the configurable `min_confidence`, default
`0.0`) upserts a `CandidateSource` with `discovered_by="rendered"`, `status=NEW`, `feed_type` mapped
from the provider type (`next_data`→`NEXT_DATA`, `json_api`→`JSON_API`, `graphql`→`GRAPHQL`,
`rss`/`ics`→`RSS`/`ICS`, …), `discovery_confidence`, `embedded_event_count`, the framework, and the
D2 confidence signals. **Each event-relevant REST/JSON/GraphQL endpoint additionally becomes its own
`JSON_API`/`GRAPHQL` candidate** — the hidden API that likely fronts the full dataset. The complete
reasoning record (verdict + hydration payloads + endpoints) is persisted to the `RenderedStore` for
audit. Non-event pages are skipped (counted, not inserted).

## Safety

Structural, not advisory. The engine **never**: logs in, authenticates, bypasses robots, executes
JavaScript, calls/probes any endpoint, or brute-forces an API. It reads only public HTML/JS/JSON that
was already served. Discovered endpoints are recorded as **leads only**. The `BrowserRenderer` and
`ApiProber` seams (which *would* execute JS / call an endpoint) are interfaces that raise
`NotImplementedError` — deliberately unbuilt in 8E. Nothing is onboarded automatically; a human
reviews the inbox.

## Live demonstration

`backend/spikes/p8e_rendered_discovery.py` (fixtures, no network) runs the headline scenario plus a
Nuxt page, an Apollo/GraphQL page, an ICS-feed-only page, and a marketing page:

```
● https://techevents.in/events
    framework : Next.js
    hydration : __NEXT_DATA__        250 events e.g. 'React India Meetup #249'
    endpoint  : [rest   ] https://techevents.in/api/events?city=bangalore&page=1  (via js-path) ★ event API
    endpoint  : [graphql] https://api.example.com/graphql  (via html)
    VERDICT   : EVENT SOURCE | type=next_data | conf=1.0
                  • __NEXT_DATA__ carried 250 event object(s) (e.g. 'React India Meetup #249')
                  • event API endpoint: …/api/events?city=bangalore&page=1 (via js-path)
                  • event API present → full dataset likely larger than the hydrated page
    missing   : date, location, organizer, registration_url (needs per-event parse)

=== DISCOVERY INBOX (all discovered_by=rendered, status=NEW — nothing onboarded) ===
    [next_data ] next_data      conf=1.00 250ev  https://techevents.in/events
    [rest      ] json_api       conf= -     -    https://techevents.in/api/events?city=bangalore&page=1
    [json_api  ] json_api       conf=0.81   2ev  https://vueconf.in/
    [graphql   ] graphql        conf=0.70   1ev  https://summit.dev/graphql-summit
    [ics       ] ics            conf=0.15   -    https://pydata.org/calendar
```

The Next.js page shipped **zero event HTML** — 250 events lived in `__NEXT_DATA__`, and the hidden
`/api/events` (which likely fronts the *full* dataset) was recorded as a `JSON_API` candidate,
reachable in one call instead of crawling HTML forever. The marketing page was correctly judged not
an event source.

## Tests

`backend/tests/test_rendered_discovery.py` — **29 tests, fixtures only, no network/browser**:
hydration (each source/framework, no-double-count, external scripts), endpoints (classify, all call
sources, relative + absolute-variable resolution, JSON-blob exclusion, event-first ranking, cap),
reasoning (every provider-type branch, confidence/evidence/missing/answers, tech extraction), engine
end-to-end (250-events→inbox, endpoint candidates, non-event skip, idempotent upsert, min-confidence
floor, store persistence), both stores, and the future-seam `NotImplementedError` guarantees. Full
backend suite: **543 passed**.

## Honest self-review

**Truly true**
- The extraction is real and deterministic: `__NEXT_DATA__`/Nuxt/Apollo/Preloaded/embedded-JSON blobs
  are parsed and events counted; hidden `fetch`/`axios`/`xhr`/path/url endpoints are found; no blob
  is double-counted; the JSON-blob exclusion is verified. Safety is structural (no JS execution, no
  endpoint ever called). Evidence and `missing_fields` are honestly reported; unknown is never
  guessed.

**Weaknesses / limitations**
1. **The "AI" is a deterministic heuristic, not understanding.** `MockAIReasoner` applies fixed
   weights and keyword rules. It cannot understand a novel hydration shape, disambiguate an
   ambiguous blob, or read prose. `GeminiReasoner` is the seam for real reasoning; it is unbuilt.
2. **Event *counting*, not event *parsing*.** We report how many event-shaped objects a blob contains
   and one sample title — we do not extract each event's date/location/organizer/registration. Hence
   `missing_fields` is populated on every event source. Turning a candidate into structured events is
   a later step.
3. **Served-bytes only — pure-runtime SPAs are invisible.** If a site exposes *nothing* in the HTML
   or inline JS (all state arrives via a post-load XHR the browser makes), we see no hydration blob.
   Only the `BrowserRenderer` seam (execute JS to get the hydrated DOM) would reach those — out of
   8E's no-browser scope.
4. **Endpoints are unverified leads.** We record `/api/events` but never call it, so we can't confirm
   it returns events, how many, or whether it needs auth/params. "Full dataset likely larger" is an
   inference, not a measured fact. `ApiProber` (deferred) would confirm.
5. **Regex extraction is brittle and has blind spots.** Endpoints built dynamically
   (`fetch(base + path)`, template literals with `${}`, URLs assembled at runtime) are missed by
   design — resolving them needs JS execution. The `js-url` catch is deliberately narrow
   (`/api/`·`/events`·`.ics`·`.rss`·`/feed`·`/graphql`) to stay low-noise, so it will miss oddly-named
   event APIs.
6. **False positives.** A blob with name+date keys that isn't really an event, an `/api/events`
   endpoint that's actually analytics event-logging, or a GraphQL cache with no events — all can be
   surfaced. The engine leans to recall; the 25-cap, event-first ranking, and human inbox review are
   the safeguards. Nothing is onboarded automatically.
7. **The confidence numbers are calibrated by hand, not learned.** The weights are reasonable and
   explainable but arbitrary; a lone event API sits at 0.4 by fiat. They order candidates sensibly
   but shouldn't be read as probabilities.

## Where Phase 9 begins (NOT this phase)

8E reads the served bytes deterministically and stops at the inbox. **Phase 9 — Autonomous
Multi-Agent Discovery & Continuous Learning** — would add real LLM reasoning (`GeminiReasoner`),
browser-rendered extraction for pure-runtime SPAs (`BrowserRenderer`), endpoint probing
(`ApiProber`), and feedback-driven calibration of the confidence weights. All are larger capabilities
and require explicit approval.

---

**Status:** 8E complete. Additive; D1–D4 / 7A / 7B / 8A–8D / frozen systems untouched; 543 tests
green; HTML/JS/JSON-only, no browser/JS-execution/network, evidence-bearing, discovery-only.
**Stopping here — Phase 9 NOT started.**
