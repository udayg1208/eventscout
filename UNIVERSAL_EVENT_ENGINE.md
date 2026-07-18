# Universal Event Understanding Engine — Phase 10B

Given **any** public webpage, decide whether it contains one or more real technology/professional
events and extract them **with provenance** — regardless of framework. The engine never asks "what
framework is this?"; it asks **"where is the event information?"** and runs every extraction strategy
that could answer, in parallel. It is the universal parser for the whole internet: HTML, blog,
university page, Notion, GitHub, Markdown, hydrated React/Next.js/Vue/Astro, JSON-LD, calendar, RSS,
FAQ, table, announcement — all the same to it.

Code: `backend/app/universal/` (new package — additive). It **reuses** D4's provenance model, D2's
hydration extractors, D1's feed/JSON-LD walking, the 5A tech taxonomy, and `city.detect_city`, and
**modifies nothing** (Discovery, D1–D4, 7A–7B, 8A–8D, 9A, 10A, Search, Repository, Registry,
Scheduler, Event model, API, Frontend). No browser, no Playwright/Selenium, no login, no LLM, no
network. Discovery only — nothing is written to the catalog.

## The pipeline

```
raw bytes (HTML/JSON/Markdown/ICS)
   │
   ▼  fingerprint — unchanged? → skip
   ▼
14 isolated extractors, run in 3 tiers (parallel within a tier)
   ├─ Tier 1 structured : JsonLd · Microdata · NextData · Nuxt · Astro · Hydration · EmbeddedJson · Calendar
   ├─ Tier 2 semi       : OpenGraph · Table · DefinitionList
   └─ Tier 3 textual    : Markdown · FAQ · SemanticBlock
   │        (stop early once a confident event is assembled)
   ▼  each returns ExtractionResult → RawEvents (per-field, with provenance)
   ▼
merge — cluster RawEvents by title, keep the best field per name (merged provenance)
   ▼
normalize → validate (reject off-topic) → confidence (8 explainable components)
   ▼
UniversalEvent[]   (0, 1, 5, 20, 100 per page)
```

## The isolated extractors

Each is independent and returns provenance-bearing `RawEvent`s; order within a tier is irrelevant
because the merge is deterministic.

| Extractor | Finds events in |
|---|---|
| `JsonLdExtractor` | `<script type="application/ld+json">` schema.org/Event (incl. `@graph`) — full field set |
| `MicrodataExtractor` | inline `itemscope itemtype=schema.org/Event` |
| `NextDataExtractor` | `__NEXT_DATA__` (reuses D2) → event-shaped objects |
| `NuxtExtractor` | `window.__NUXT__` / `__NUXT_DATA__` |
| `AstroExtractor` | `<astro-island props="…">` island JSON |
| `HydrationExtractor` | `__INITIAL_STATE__` / `__APOLLO_STATE__` / `__PRELOADED_STATE__` / `window.DATA` |
| `EmbeddedJsonExtractor` | any `<script type="application/json">` (excludes `__NEXT_DATA__`) |
| `CalendarExtractor` | iCalendar `VEVENT` + RSS/Atom `<item>` with an event signal |
| `OpenGraphExtractor` | `og:*` meta — the page-level event landing card |
| `TableExtractor` | `Date | Event | Venue` schedule/agenda tables (HTML + Markdown) |
| `DefinitionListExtractor` | `<dl>` When/Where/Cost lists |
| `MarkdownExtractor` | README/docs — dated headings + Markdown tables |
| `FaqExtractor` | When? / Where? / How to register? / Cost? Q&A blocks |
| `SemanticBlockExtractor` | cards / panels / accordions / hero / timeline / announcement blocks |

## The universal event schema

Every event carries these fields, each an `ExtractedField {value, status, provenance}` reused from D4:
**title, organizer, description, start_date, end_date, timezone, city, state, country, venue, mode
(online/offline/hybrid), registration_url, deadline, technologies, audience, event_type, fee,
speakers, sponsors, tags, images.** A field exists only if grounded in a real snippet; anything
unsupported is **UNKNOWN (value `None`) — never a guess**. Values derived from evidence (country from
an Indian city) are `INFERRED`, not `EXTRACTED`.

## Merged provenance

Different extractors describe the same event. The merge clusters `RawEvent`s by normalized title and,
per field, keeps the single best `ExtractedField` — **EXTRACTED beats INFERRED, then higher provenance
confidence wins** — recording every contributing extractor. So a page with JSON-LD *and* OpenGraph
yields one event whose date came from JSON-LD and whose organizer came from `og:site_name`, each still
citing its own snippet (`sources=['jsonld','opengraph']`).

## Confidence — explainable, eight components

`total = Σ(component × weight)`, weights summing to 1.0, every component explained:

| Component | Weight | Signal |
|---|---|---|
| structured | 0.22 | came from a structured source (JSON-LD/microdata/hydration/ICS)? |
| temporal | 0.18 | a real start date (end/deadline add a little) |
| provenance | 0.15 | average provenance confidence of the extracted fields |
| location | 0.12 | city / venue / country present |
| technology | 0.10 | recognised technologies present |
| registration | 0.08 | a registration URL present |
| organizer | 0.08 | an organizer present |
| semantic | 0.07 | richness (description, speakers, images, fee…) |

## Validator — keep tech events, reject the rest

Rejects **shopping, politics, religion, gambling, adult, entertainment, travel/tourism, coupons, jobs,
products** — but only when a reject keyword matches (in the event's fields *or the page context*) **and
there is no positive tech/event signal**, so a real hackathon that mentions "jobs" or "travel"
survives. Requires a minimum event shape (a title). Every verdict is explained. Deterministic, no LLM.

## Multiple events, and performance

One page produces **0, 1, 5, 20, or 100** events — university event lists, conference schedules,
meetup archives, hackathon lists all fan out through the table/hydration/semantic extractors. Two
performance levers: extractors in a tier run **in parallel** (`asyncio.to_thread`), and the engine
**stops early** once a confident event is assembled — a clean JSON-LD page never pays for the semantic
scan (verified: only the 8 structured extractors run). **Incremental** extraction fingerprints each
page (sha1 over normalized bytes) and skips it if unchanged.

## Live demonstration

`backend/spikes/p10b_universal.py` (fixtures, no network) runs 8 page shapes:

```
● University (JSON-LD)        → 1 event  [0.81]  (early-stop: only 8 structured extractors ran)
● Conference schedule (table) → 3 events [0.55]  Kubernetes / Rust / AI, each with tech + venue
● Community (Next.js)         → 2 events [0.66]
● GitHub README (Markdown)    → 2 events [0.49]  PyCon India, Rust Hackathon (type=hackathon)
● Notion-style FAQ            → 1 event  [0.50]  date/venue/registration/fee from Q&A
● Public calendar (ICS)       → 1 event  [0.74]
● Blog (OpenGraph)            → 1 event  [0.65]  DevOps/Kubernetes, organizer from og:site_name
● Shopping page               → 0 events, REJECTED (off-topic)
  → 11 events across 8 pages, every field provenance-bearing, one rejected
```

## Tests

`backend/tests/test_universal.py` — **61 tests, fixtures only, no network/browser/LLM**: the date/
text helpers; provenance; each extractor (JSON-LD full/graph/virtual/empty, OpenGraph, microdata,
NextData/Nuxt/Astro/Hydration/EmbeddedJson incl. the no-double-count of `__NEXT_DATA__`, Markdown,
Table incl. header-role gating, DefinitionList, FAQ, ICS/RSS, semantic); merge (cross-extractor
cluster, best-field-wins, distinct titles); normalize; validator (each reject category, tech-signal
survival, context rejection); the eight-component confidence (weights sum to 1, total = Σ, explained);
fingerprint; and the engine end-to-end (every page type, merged provenance, shopping rejected, min-
confidence filter, early-stop, fingerprint skip, sorting, parallel==serial). Full backend suite:
**655 passed**.

## Honest self-review

**Truly true**
- It is genuinely framework-agnostic and provenance-first: the same engine extracts from JSON-LD,
  Next.js hydration, a Markdown README, an ICS feed, and an FAQ, and every field cites the snippet it
  came from. UNKNOWN is preferred over guessing, off-topic pages are rejected, and merged provenance
  across extractors works.

**Weaknesses / limitations**
1. **Regex/heuristic parsing, not a real DOM.** No `bs4`/`lxml` — extraction is regex over bytes. It's
   fast and dependency-free but brittle on malformed HTML, deeply nested tables, or unusual markup; the
   semantic extractor is a *windowed scan*, so complex layouts can mis-bound a block.
2. **Byte-level only — pure-runtime SPAs are invisible.** If a page ships no serialized state and builds
   everything via post-load XHR, there's nothing to read. That's the `BrowserRenderer` seam (below),
   deliberately unbuilt.
3. **Deterministic date parsing is limited.** Common formats (ISO / "Nov 1, 2026" / "1 November 2026" /
   dd/mm/yyyy) only; no `dateutil`, no relative dates ("next Friday"), and **timezone is essentially
   never extracted** — the `timezone` field is almost always UNKNOWN. Ambiguous `dd/mm` vs `mm/dd` is
   assumed `dd/mm/yyyy`.
4. **Confidence is hand-calibrated, structural — not ground truth.** The weights are explainable but
   chosen by hand; a high score means "well-structured and complete", not "verified real". Human review
   is still the arbiter.
5. **The validator is keyword-based and evadable.** The tech-signal guard both protects real events and
   can let a slick "product launch" masquerading as a tech event through, or (rarely) reject a genuine
   event with no detectable tech signal. It's a coarse gate, not content understanding (no LLM).
6. **Merge clusters by title.** Two genuinely different events with identical titles merge into one;
   near-duplicate titles across extractors mostly merge but the match is exact-normalized, not fuzzy.
7. **Multi-event vs. early-stop tension.** Early-stop assumes a confident structured tier captured the
   page's events. A page mixing a JSON-LD event *and* an HTML table of *more* events could stop after
   tier 1 and miss the table. Raising `early_stop` (or disabling it) trades speed for completeness; the
   default favours the common case.
8. **Sparse fields are honestly sparse.** `audience`, `sponsors`, `tags`, `deadline`, `timezone` are
   rarely populated because few sources expose them — reported as UNKNOWN rather than invented.

## Future `BrowserRenderer` seam (NOT this phase)

`app/universal/interfaces.py` defines `BrowserRenderer` (raises `NotImplementedError`): a later phase
would execute a page's JS to obtain the hydrated DOM and feed that HTML **back into this same engine**
— extending reach to pure-runtime SPAs with zero change to the extractors. Out of 10B's no-browser
scope.

---

**Status:** 10B complete. Additive; every frozen system untouched; 655 tests green; byte-level,
framework-agnostic, provenance-bearing; no browser/LLM/network; discovery only. **Stopping here —
Phase 10C NOT started.**
