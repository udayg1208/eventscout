# Universal Extraction Pipeline — Phase 10B

A companion to [UNIVERSAL_EVENT_ENGINE.md](UNIVERSAL_EVENT_ENGINE.md), focused on the *pipeline*: the
exact order data flows through, how the extraction tiers and early-stop interact, how many extractors
turn into one merged event, and how incremental extraction and performance work.

## The full flow

```
Input (url, bytes, content_type)
   ↓
Fingerprint            sha1(normalized bytes) — unchanged since last run? → return skipped
   ↓
Tier 1 · STRUCTURED    JsonLd · Microdata · NextData · Nuxt · Astro · Hydration · EmbeddedJson · Calendar
   ↓ (merge so far; confident? → stop)
Tier 2 · SEMI          OpenGraph · Table · DefinitionList
   ↓ (merge so far; confident? → stop)
Tier 3 · TEXTUAL       Markdown · FAQ · SemanticBlock
   ↓
Field extraction       each extractor already emits per-field ExtractedFields (title, date, city, …)
   ↓
Merge                  cluster RawEvents by title → best field per name (merged provenance)
   ↓
Normalization          dedupe tech · canonical mode/event_type · infer country from city
   ↓
Validator              reject shopping/politics/…; require a title; explain
   ↓
Confidence             8 components × weights → total, each explained
   ↓
UniversalEvent[]       sorted by confidence; 0..N per page
```

Metadata, JSON-LD, OpenGraph, hydration, `__NEXT_DATA__`, Nuxt, Astro, embedded JSON, Markdown,
tables, definition lists, FAQ, calendar, microdata, and semantic blocks are all just *extractors* on
this one pipeline — the brief's long list of "extraction steps" collapses into fourteen isolated
strategies plus a merge.

## Why tiers + early-stop

Extraction strategies are not equal. Structured serialized data (schema.org JSON-LD, a hydration blob,
an ICS feed) is authoritative and usually **complete** for a page; prose/visual scans (Markdown, FAQ,
semantic cards) are softer and mostly re-find the same events with less confidence. So the pipeline
runs structured first and **stops once a confident event is assembled** — the clean JSON-LD page in
the demo runs only its 8 structured extractors and never pays for the semantic scan. Within a tier the
extractors run in parallel (`asyncio.to_thread`), so a tier costs about as much as its slowest member.

The tradeoff is explicit: early-stop assumes the confident structured tier captured everything. A page
that mixes a JSON-LD event *and* a separate HTML table of more events could stop early and miss the
table. `early_stop` (default 0.8) is tunable; set it to `1.0` to always run every tier.

## From many extractors to one event

Each extractor emits `RawEvent`s — partial, per-field, provenance-bearing. The merge:

1. **Clusters** RawEvents by normalized title (falling back to date for titleless partials).
2. For each field, **keeps the best** `ExtractedField`: EXTRACTED > INFERRED, then higher confidence.
3. **Records every contributing extractor** in `sources`.

So three table rows become three events; JSON-LD + OpenGraph for the same conference become one event
with fields sourced from both. Determinism comes from stable extractor/tier ordering and a
tie-broken best-field rule.

## Multiple-event pages

A single page routinely yields many events, and the pipeline is built for it:
- **University event pages / department notices** → tables + semantic cards → one event per row/card.
- **Conference schedules / agendas** → `Date | Session | Venue` tables → one event per row.
- **Meetup archives / hackathon lists / club calendars** → hydration arrays or `<li>`/card lists.

The count is whatever the page actually contains — 0 for a page with no event, N for a schedule.

## Incremental extraction

`FingerprintStore` records a sha1 of each page's whitespace-normalized bytes. On a re-run, an unchanged
page returns immediately with `skipped_unchanged=True` — the cheap path for continuous/scheduled
re-extraction (10A's daily runs). The store is in-memory here; swapping in a durable one is trivial.

## Performance characteristics

- **Parallel within a tier**, **short-circuit across tiers** — best case (structured page) touches ~8
  extractors; worst case (prose page) touches all 14.
- **No network, no browser, no DOM library** — pure regex/JSON over bytes, so per-page cost is
  milliseconds and there are no external dependencies to fail.
- **Bounded scans** — the semantic extractor caps at 100 blocks and a fixed window; event walks are
  bounded; nothing on a hostile page runs unbounded.

## Honest self-review (pipeline view)

- **The ordering is a heuristic, not a proof.** Tiers encode "structured is more trustworthy and
  complete", which is usually but not always true. The early-stop tradeoff is real and documented; the
  safe setting (run all tiers) is one parameter away.
- **Merge-by-title is exact, not fuzzy.** It handles the common cross-extractor duplication well but
  will split "PyCon 2026" from "PyCon India 2026" and merge two unrelated "Workshop" rows if they share
  a title. A fuzzy matcher would help and isn't here.
- **Determinism holds despite parallelism** because results are collected in submission order and the
  merge is order-stable — verified by a `parallel == serial` test.
- **Byte-level is the ceiling.** Everything downstream is only as good as what the served bytes expose;
  the `BrowserRenderer` seam is where that ceiling lifts, and it is deliberately not built in 10B.

---

**Status:** 10B complete — additive, byte-level, framework-agnostic, provenance-first; 655 tests green;
no browser/LLM/network; discovery only. **Stopping here — Phase 10C NOT started.**
