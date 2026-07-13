# Architecture

## Overview
Natural-language event discovery for India. The system is built around **two
abstraction seams** so every external dependency is replaceable:

- **`QueryParser`** — turns natural language into a validated `SearchQuery`.
- **`EventProvider`** — turns a `SearchQuery` into normalized `Event`s.

Everything else depends only on these contracts and on the shared models.

```
User
  → Next.js frontend            (next milestone)
  → FastAPI backend  ── POST /search ──▶ SearchService
        1. QueryParser.parse(text)       →  SearchQuery     [Gemini or deterministic]
           (parse-cache: skip Gemini on repeat text)
        2. EventProvider.search(query)   →  list[Event]     [CompositeProvider]
           (results-cache: skip provider on repeat query)
              └─ fan-out ‖ ConfsTech + Devfolio  (asyncio.gather)
                 → merge → canonical city → dedup → rank
  → ranked normalized Events → frontend
```

## Core models (`app/models`)
### `Event` — the one contract every provider maps into (immutable, `frozen=True`)
`title`, `description?`, `url` (HttpUrl), `city?`, `location?`, `is_online`,
`start_date` (date), `end_date?`, `category` (EventCategory), `is_free?` (tri-state:
`None` = unknown), `price?` (display string), `provider`.

Design stance: a field exists only if the UI must show it or the backend must filter
on it, and only if a real source can supply it honestly. `date` (not `datetime`)
because date-only sources are common. Deferred until needed: `id`, `country`,
`organizer`, `image`, numeric price.

### `EventCategory` (`StrEnum`)
`workshop, meetup, conference, hackathon, startup, ai, webinar`. The **same** enum is
used by `SearchQuery.categories`, so a provider can filter `event.category in
query.categories` directly.

### `SearchQuery` — the provider-facing search contract (and Gemini's output)
`keywords[]`, `city?`, `categories[]`, `date_from?`, `date_to?`, `free_only`.
Every field defaults to “no constraint”, so an empty query means “match everything”.
A validator enforces `date_from <= date_to`. Gemini is *one* producer of this object;
tests and the deterministic parser are others — which is why the pipeline is testable
without any AI.

## Seam 1 — `QueryParser` (`app/parsers`)
```
QueryParser (ABC).parse(text) -> SearchQuery      # never raises for user input
├── KeywordQueryParser   deterministic, no network; normalizes city aliases; no date logic
└── GeminiQueryParser    validate → retry once (corrective prompt) → fall back to KeywordQueryParser
```
- `get_query_parser()` picks Gemini if `GEMINI_API_KEY` is set, else the deterministic
  parser. Single swap point.
- Gemini SDK is **lazy-imported** inside `GeminiQueryParser._generate`; the module and
  tests load with no SDK and no key. `_generate` is the seam tests script.
- Failures caught and degraded: malformed JSON, schema violations (e.g. category
  `"concert"`), the date-range validator, and API errors (429/503) all route to
  retry → fallback. Empty input short-circuits to an empty `SearchQuery`.

## Seam 2 — `EventProvider` (`app/providers`)
```
EventProvider (ABC).search(query) -> list[Event]   # async: real providers are network-bound
├── ConfsTechProvider   Confs.tech GitHub JSON  → CONFERENCE events (keyless)
├── DevfolioProvider     Devfolio search API     → HACKATHON events (keyless)
├── MockProvider         in-memory seed data (tests only)
└── CompositeProvider    fans out to sub-providers in parallel, then
                         merge → canonical city → dedup → rank
```
- `get_provider()` is the single swap point; it returns
  `CompositeProvider([ConfsTechProvider(), DevfolioProvider()])`.
- Because `CompositeProvider` is *itself* an `EventProvider`, multi-provider search
  required **no change** to `SearchService`.
- Each real provider fetches its (near-static, query-independent) dataset once per
  short TTL (`TTLCache`), then filters in memory. Empty/failed loads are not cached,
  so an upstream outage self-heals. A failing sub-provider degrades to `[]`; the
  others still return.
- Shared logic:
  - `filtering.matches(event, query)` — city/category/keyword/date-overlap/free;
    city is normalized on both sides so "Bengaluru" matches a "Bangalore" query.
  - `dedup.deduplicate` — keyed by (normalized title, start_date), keeps the most
    complete record.
  - `ranking.rank` — score = 0.50·relevance + 0.35·date-proximity + 0.15·completeness.
  - `city.normalize_city` — canonical Indian city names, applied at the boundary.

## Orchestration — `SearchService` (`app/services`)
Thin layer behind the API. `search(text)`: parse (parse-cache) → fetch (results-cache
→ provider). Two-tier `TTLCache` (`app/cache.py`, injectable clock): a repeat query
skips both Gemini and the provider. Provider failure → logged, returns `[]`, not
cached. Lightweight metrics (requests, cache hit-rates, latency, provider/Gemini/
fallback counts) exposed at `GET /debug/metrics` (non-production only). Public
interface is frozen: `search()`, `search_by_query()`, `metrics()`.

## API (`app/api/routes`)
- `GET /health` — liveness/identity (`HealthResponse`).
- `POST /search` — body `{query: text}`, returns `{query, count, events, cached}`
  (`SearchResponse`). The primary natural-language endpoint.
- `POST /events/search` — body is a structured `SearchQuery` (no AI); same response
  shape. Shares the results cache; useful for debugging the provider path.
- `GET /debug/metrics` — pipeline metrics; registered only when not production.

## Configuration (`app/config.py`)
`pydantic-settings`, env-only. `CORS_ORIGINS` is a comma string parsed via a validator;
the field is annotated `NoDecode` so pydantic-settings doesn’t JSON-decode it first
(see Lessons). Gemini: `GEMINI_API_KEY`, `GEMINI_MODEL` (default
`gemini-2.0-flash-lite`; **override to `gemini-flash-lite-latest` in `.env`** — see
Lessons).

## Tooling
- Tests: `pytest` (77 tests, network-free — real fetch paths use `httpx.MockTransport`).
- Lint + format: `ruff` (config in `pyproject.toml`, line length 100). `spikes/` excluded.

## Validation artifacts (`backend/spikes`, not production)
Throwaway scripts documenting how each external source was validated live: the
Confs.tech spike (M2.5), the Gemini live/model-quota investigation (M3), and the
M4–M6 pipeline/engine demos. Not imported by the app; excluded from lint.

## Milestones
M1 scaffold · M2 models + provider seam · M2.5 real-provider validation · M3
QueryParser seam · M4 Search Orchestrator + cache + metrics · M5 Confs.tech provider ·
M6 multi-provider engine (Devfolio, composite, city-normalize, dedup, rank) ·
**backend frozen** · next: frontend (Next.js + Tailwind) · then deploy.

## Lessons learned (M3 live verification)
1. **`CORS_ORIGINS` crash (real bug, fixed).** A `list[str]` settings field made
   pydantic-settings JSON-decode the env value before our validator ran. Latent since
   M1; surfaced only once a `.env` existed. Fixed with `Annotated[list[str], NoDecode]`
   + regression tests. *Live verification earns its keep by exercising real config.*
2. **Gemini `limit: 0` was a model-ID quota quirk, not a project/region/billing issue.**
   Systematic REST probing showed the API enabled, the account free-tier eligible, and
   `gemini-flash-lite-latest` serving 200 — while the dated `gemini-2.0-*` IDs had
   `free_tier limit: 0`. Fix was a one-line `.env` model change. *Diagnose the root
   cause before replacing credentials.*
3. **Free tier is ~15 req/min.** Bursting >15 calls self-throttles (429). Real usage
   won't, and M4's cache will cut calls further; the fallback covers any 429.
4. **The fallback is load-bearing.** Throughout the quota saga the app never broke —
   every failure degraded to the deterministic parser and returned a valid `SearchQuery`.
