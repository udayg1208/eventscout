# Framework Discovery — Detector Reference (D2)

How D2 extracts candidate event sources from modern-JS HTML **without executing JavaScript**.
Every routine here is deterministic regex / JSON parsing over the served HTML string. Companion
to **[DISCOVERY_D2.md](DISCOVERY_D2.md)** (the phase report, results, and self-review).

Modules: `backend/app/discovery/frameworks.py`, `hydration.py`, `endpoints.py`, `analysis.py`.

## Design principle

Modern frameworks **serialize their state into the initial HTML** so the browser can hydrate
without a second request. That serialized state — `__NEXT_DATA__`, RSC Flight chunks,
`window.__*__`, `<script type="application/json">` — is plain text in the response body. D2 reads
it directly. The browser's job is to *rebuild the DOM* from those bytes; D2's job is only to
*find the event data* in them, which needs parsing, not execution.

Two consequences shape every detector:

- **Recall over precision.** A candidate is a *lead to probe later*, not a verified source.
  Detectors err toward surfacing + signalling; judging is a later phase.
- **Bounded + total.** Every parser has hard limits (node counts, byte caps, result caps) and
  never raises on malformed input — unparseable payloads degrade to a deterministic text proxy,
  never a crash and never a silent skip.

---

## 1. FrameworkDetector — `frameworks.py`

`detect_framework(html) -> FrameworkInfo(name, version)`. First stable, static fingerprint wins;
version is reported **only** when a marker actually exposes it (never guessed).

| Framework | Fingerprint (in served HTML) | Version |
|---|---|---|
| Next.js (Pages) | `id="__next_data__"` | `pages-router` |
| Next.js (App/RSC) | `self.__next_f` / `__next_f.push` | `app-router` |
| Next.js (asset only) | `/_next/static/` | `None` |
| Nuxt 3 | `id="__nuxt_data__"` | `3` |
| Nuxt 2 | `window.__nuxt__` | `2` |
| Nuxt (asset only) | `/_nuxt/` | `None` |
| Remix | `__remixContext` / `__remixManifest` / `__remixRouteModules` | `None` |
| Gatsby | `id="___gatsby"` / `/page-data/` / `window.___gatsby` | `None` |
| SvelteKit | `__sveltekit` / `/_app/immutable/` | `None` |
| Astro | `astro-island` / `/_astro/` / `data-astro-` | `None` |
| Vite | `/@vite/client` / `type="module" src="/assets/index-…"` | `None` |
| React + Apollo | `window.__apollo_state__` | `None` (`React (Apollo)`) |
| React SPA | empty `<div id="root"></div>` + (`react` \| `/static/js/`) | `None` |

Order matters: Next.js and Nuxt are checked before generic React/Vite so a more specific match
isn't masked. No match → `FrameworkInfo(None, None)`.

**Detection is a signal, not a gate.** The extractors below run regardless of what (if anything)
`detect_framework` returns — GDG and Hasgeek yield events via embedded JSON with no framework
marker at all.

---

## 2. Hydration / state extractors — `hydration.py`

### `extract_next_data(html) -> object | None`
Parses the `<script id="__NEXT_DATA__" type="application/json">…</script>` body (and Nuxt 3's
`__NUXT_DATA__`) as JSON. Both are well-formed JSON script blocks → a single `json.loads`.
Returns `None` if absent or malformed.

### `extract_window_state(html, var) -> object | None`
Best-effort parse of `window.<var> = {…}` for `__NUXT__`, `__APOLLO_STATE__`, `__INITIAL_STATE__`,
`__PRELOADED_STATE__`. Locates the assignment, then `_balanced_after` walks the string tracking
brace/bracket depth **and string/escape state** to return the exact balanced `{…}`/`[…]` literal
(capped at 2 MB), which is then `json.loads`-ed.

> **Limit:** if the value is not a JSON literal — e.g. Nuxt 2's `window.__NUXT__=(function(){…})()`
> — the first char is `(`, `_balanced_after` returns `None`, and this yields nothing. That case
> falls through to the signature proxy (§5). This is the one framework D2 cannot cleanly parse.

### `extract_embedded_json(html) -> list[object]`
Every parseable `<script type="application/json">…</script>` blob. **Excludes** `application/ld+json`
(that is D1's JSON-LD detector) — the regex matches `type="application/json"` exactly, which does
not match `application/ld+json`. Malformed blobs are skipped, not raised.

### `extract_flight_strings(html) -> list[str]`
Decodes RSC Flight payloads pushed via `self.__next_f.push([n, "…"])`. The captured string is an
escaped JS string literal; `json.loads('"…"')` unescapes it so its inner (previously
`\"startDate\":`) JSON becomes scannable text.

---

## 3. Event-object detection — `hydration.py`

### `find_event_objects(obj) -> (count, sample_title)`
Iterative (stack-based, **bounded at 200k nodes**) walk of a parsed payload. A dict is
event-shaped when:

```
(has a name-key AND a date-key)  OR  @type/type == "event"
name-keys: name, title, event_name, eventname, summary
date-keys: start_date, start_at, startdate, startdatetime, start_time, starttime,
           start, date, datetime, start_date_time
```

Returns the count of event-shaped dicts and the first title found.

> **This is a recall proxy.** It counts objects that *look like* events — it does **not** dedup,
> filter to upcoming, or validate. A payload with past events or event-shaped non-events (venues,
> chapters) inflates the count. Read `embedded_event_count` as "how event-rich this payload is,"
> not "how many ingestible events exist." Clean extraction is D3.

### `count_event_signatures(text) -> int`
Regex proxy for payloads that can't be parsed into objects (Nuxt 2 functions, raw Flight): counts
quoted date-key signatures (`"startDate":`, `"start_at":`, …). A deterministic lower-effort
fallback so nothing event-bearing is silently dropped.

---

## 4. Endpoint detectors — `endpoints.py`

### `find_api_endpoints(html, base) -> list[str]`
Regex-matches quoted `/api/…` paths and absolute `…api…/…` URLs in the HTML (bundle refs, config,
inline fetches). Relative paths are resolved against the page origin and normalized.
**Event-ish endpoints (URL contains `event`) are ranked first**; capped at 20.

### `find_graphql_endpoints(html, base) -> list[str]`
Matches `/graphql` and `/gql` references (relative or absolute); normalized, capped at 5.

> **Limit:** endpoints are surfaced by string match only. A discovered URL may be **third-party**
> (e.g. `googleapis.com` Google Calendar) or a query-string near-duplicate. First-party filtering,
> dedup, and actually probing the endpoint are deferred to validation / D3. The endpoint is a
> *candidate to probe*, keyed by its own URL.

---

## 5. Orchestrator — `analysis.py`

`analyze_frameworks(result: FetchResult) -> FrameworkAnalysis`. Ties the above together:

```
fw          = detect_framework(html)
count, src  = _best_events(html)     # best across payloads (below)
api, gql    = find_api_endpoints(...), find_graphql_endpoints(...)
```

`_best_events` tries payloads in order and keeps the **max** event count:

1. `__NEXT_DATA__` / `__NUXT_DATA__` → `find_event_objects`
2. each `window.__*__` state → `find_event_objects`
3. each `<script type="application/json">` blob → `find_event_objects`
4. RSC Flight: decode strings, then `count_event_signatures` on the decoded text
5. fallback (still 0): `count_event_signatures` on raw HTML (catches Nuxt 2 quoted signatures)

It then emits:

- **FeedDetections** — one page-level detection for the winning payload (`next_data` /
  `next_flight` / `hydration_state` / `embedded_json`), a `json_api` detection per **event-ish**
  endpoint, and one `graphql` detection.
- **Signals dict** — the 8 D2 booleans (`has_framework, has_nextjs, has_hydration,
  has_embedded_events, has_json_array, has_calendar_schema, has_api_endpoint,
  has_graphql_endpoint`).
- **Candidate fields** — `framework, framework_version, hydration_source, embedded_event_count,
  api_endpoints, graphql_endpoints`.

The engine merges these detections with D1's (`_merge_detections`, deduped by `feed_type+url`),
runs `collect_signals(…, analysis)` and `build_candidate(…, analysis)`, and upserts. A page with
no payload and no endpoints produces an empty D2 list → the merge is a no-op → identical to D1.

---

## Determinism & safety guarantees

- **No JavaScript execution** anywhere — no Playwright, Selenium, or headless browser. Only
  `re` and `json` over the HTML string.
- **Total functions** — malformed JSON, truncated payloads, and exotic serializations degrade to
  a text-signature proxy or empty result; never raise.
- **Bounded** — node walk ≤ 200k, balanced-literal scan ≤ 2 MB, API endpoints ≤ 20, GraphQL ≤ 5.
- **Additive** — new files + additive edits only; every frozen contract (Search, Repository,
  Provider interfaces, Registry, Scheduler, Catalog, Frontend, API) is untouched; output stops at
  the Discovery Inbox.
