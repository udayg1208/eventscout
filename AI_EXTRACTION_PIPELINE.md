# AI Extraction Pipeline — D4

The stage-by-stage flow that turns a raw prose page into a provenance-bearing Candidate Source (or
an explained rejection). Companion to **[AI_DISCOVERY_ENGINE.md](AI_DISCOVERY_ENGINE.md)** (the
architecture, safety model, and self-review).

```
Raw Page
   │
   ▼
Deterministic Extraction   (D1 detect_feeds + D2 analyze_frameworks)
   │
   ▼
Missing information?  ──yes──▶  D1/D2 already understand it → DETERMINISTIC_SUFFICIENT (AI skipped)
   │ no (nothing structured found)
   ▼
AI Extraction   (MockAIExtractor → AIExtraction with provenance on every field)
   │
   ▼
Validator   ──reject──▶  off-topic / insufficient evidence → AI_REJECTED (no candidate; audited)
   │ pass
   ▼
Confidence Engine   (deterministic + ai + structured + search → DiscoveryConfidence)
   │
   ├─ below min_confidence ─▶ LOW_CONFIDENCE (not inbox'd; audited)
   ▼
Discovery Inbox   (CandidateSource: feed_type=AI_EXTRACTED, discovered_by=ai, status=NEW)
   + AIExtractionStore (full provenance audit trail)
```

`AIDiscoveryPipeline.process(FetchResult) -> PipelineOutcome`; `.run([...]) -> AIDiscoveryReport`
for batches. Every outcome is one of four `Decision`s, each explained.

## Stage 1 — Deterministic extraction (the gate)

The pipeline runs the existing D1/D2 detectors on the page:

```python
detections = detect_feeds(result)                 # D1: RSS/JSON-LD/ICS/sitemap/…
analysis   = analyze_frameworks(result)           # D2: __NEXT_DATA__/hydration/embedded JSON
det_score, structured_present = _deterministic(detections, analysis.embedded_event_count)
```

`_deterministic` scores: `0.85` if an event-bearing feed or embedded events exist, `0.25` if there
is some non-event structure (a bare sitemap), `0.0` for pure prose. If `det_score ≥ 0.6` the page
is already understood — return `DETERMINISTIC_SUFFICIENT` and **do not call AI**. This is the
deterministic-first guarantee in code: AI is reached only for pages the structured detectors can't
handle.

## Stage 2 — AI extraction (16 fields, all with provenance)

For a page that reaches here, `AIExtractor.extract(ExtractionInput)` returns an `AIExtraction` with
these fields, each an `ExtractedField{value, status, provenance}`:

```
organization · event_platform · community · city · state · country · technologies ·
event_types · audience · organizer · registration_links · calendar_links · recurring ·
event_frequency · tech_relevance · india_relevance
```

`MockAIExtractor` (the deterministic stand-in) grounds each value in the text:

- **technologies** reuse the catalog's 5A taxonomy (so "technology" means the same as everywhere).
- **city** via `city.detect_city`; **country** = India, **EXTRACTED** if stated, **INFERRED** if
  only a city / `.in` domain implies it.
- **organization / organizer** only from an explicit "organized by …" phrase; **community** from a
  curated name list.
- **registration/calendar links** from URLs carrying register/RSVP/ticket or `.ics`/calendar hints.
- **recurring / event_frequency** from recurrence phrases ("every month" → monthly).

The inviolable rule: **a field with no supporting snippet is UNKNOWN** (`value=None`,
`provenance=None`) — never guessed. Values derived from evidence are marked `INFERRED`, never
`EXTRACTED`. A real LLM (future `GeminiAIExtractor`) slots in here unchanged, adding genuine
language understanding while keeping the identical provenance contract.

## Stage 3 — Classification

`AIClassifier.classify(page, extraction)` labels the source across 14 classes (Tech, Non-tech,
University, Community, Government, Company, Conference, Meetup, Hackathon, Webinar, Workshop,
Startup, Product, Open Source). Tech vs non-tech is anchored on the *extraction's* technology
evidence, not keywords alone; every label carries a confidence and an evidence reason, sorted most-
confident first. `primary` is the top label; `is_tech` gates downstream trust.

## Stage 4 — Validator (safety gate)

`validate(page, extraction)` must pass before a candidate is produced:

1. **Hard reject** on tourism/travel/shopping/weddings/politics/religion/pornography/gambling.
2. **Soft reject** on entertainment/concerts/sports/festivals — *unless* `tech_relevance ≥ 0.33`
   (a real tech signal overrides an incidental mention).
3. **Insufficient evidence** — reject if there is no technology, event-type, or community signal.

A rejected page returns `AI_REJECTED` with explicit reasons and never becomes a candidate (it is
still written to the audit store, so the decision is reviewable).

## Stage 5 — Confidence Engine

`compute_confidence(deterministic, ai, structured, search)` blends the present signal families
(weights 0.30/0.30/0.25/0.15, renormalized over what's present). Absent families pass `None` and
are excluded — a prose page isn't penalized for lacking structured signals. If `total <
min_confidence` (default 0.4) the page is `LOW_CONFIDENCE` and not inbox'd (but audited).

## Stage 6 — Discovery Inbox + audit store

A page that passes becomes a `CandidateSource`:

```
feed_type            = FeedType.AI_EXTRACTED
discovered_by        = "ai"
discovery_method     = "ai-extraction"
title/city/country/organization  ← from the extraction's known fields
technology_confidence / india_confidence  ← extraction relevance scores
discovery_confidence = DiscoveryConfidence.total          # the realized Confidence Engine
classification       = primary class
search_query/rank/engine  ← carried through if the source came from D3
status               = NEW
```

The **full** `AIExtractionRecord` (every field's snippet/reason/confidence, the ranked
classification, the confidence component breakdown, the validation verdict) is saved to the
`AIExtractionStore` keyed by url — the complete, non-opaque audit trail. The candidate itself stays
lean; a reviewer opens the store record to see exactly why each value was extracted.

## Batch report

`pipeline.run(pages, ranks=…)` returns an `AIDiscoveryReport`: `processed`,
`deterministic_sufficient`, `ai_extracted`, `accepted`, `rejected`, `low_confidence`, `inserted`,
`discovered_domains`. The `ranks` map lets D3 search ranks feed the confidence engine per url.

## Worked example (from the live spike)

```
Raw page: https://cs.iitb.ac.in/techclub  (prose: "IIT Bombay Tech Club … Organized by IIT
          Bombay CSE … Python, AI, Kubernetes workshops and hackathons every month in Mumbai …")

Stage 1  detect_feeds=[]  embedded_events=0  → det_score 0.0  → AI needed
Stage 2  org=IIT Bombay CSE ('organized by' snippet) · city=Mumbai · state=Maharashtra ·
         country=India · technologies=[AI, Kubernetes, Python] · event_types=[hackathon, workshop] ·
         recurring=True · frequency=monthly · audience=[students, developers]   (each with provenance)
Stage 3  primary=TECH; labels: TECH, COMMUNITY, WORKSHOP, HACKATHON, UNIVERSITY
Stage 4  validate → PASS (evidence: technologies, event_types)
Stage 5  ai=0.85, search=1.00 (rank 1) → confidence 0.90
Stage 6  CandidateSource(feed_type=ai_extracted, discovered_by=ai, class=tech, conf=0.90) → inbox
         + full provenance record → store
```

## What is deterministic vs learned

Everything in D4 is deterministic today — the "AI" is a heuristic mock, so the whole pipeline is
reproducible and testable with zero network. The single seam that becomes learned is Stage 2's
`AIExtractor` (and optionally Stage 3's classifier): swap `MockAIExtractor` for `GeminiAIExtractor`
and real language understanding flows through the identical contract — provenance, UNKNOWN-on-doubt,
validator, confidence, store — all unchanged.
