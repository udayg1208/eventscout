# AI Discovery Engine — D4 (AI Extraction & Understanding)

D4 is the **final** discovery capability. D1 reads structured data, D2 reads framework/hydration
payloads, D3 finds new domains via search. D4 handles what none of them can: a page that describes
events only in **prose** — no RSS/JSON-LD/ICS/sitemap, no `__NEXT_DATA__`, no known framework. It
reads the text and *understands* it.

It runs **after** D1/D2 and only when they cannot confidently parse the page. It never creates
providers, never ingests events, never writes to the catalog. It produces Candidate Sources for
the Discovery Inbox — output stops there.

Code: `backend/app/discovery/ai/` (new, self-contained) + additive fields on the Discovery Inbox.

## Core principle (the safety model)

> AI may extract. AI may classify. AI may summarize. AI may identify signals.
> **AI must never fabricate.** Every extracted field retains provenance. If confidence is
> insufficient, return **UNKNOWN** — never guess.

This is enforced structurally, not by good intentions:

- **Provenance on every value.** An `ExtractedField` is `{value, status, provenance}` where
  `provenance = {source_snippet, reason, confidence, method, timestamp}`. The `source_snippet` is
  the exact text the value came from — a value with no supporting snippet cannot exist.
- **UNKNOWN is a first-class outcome.** No snippet → `FieldStatus.UNKNOWN`, `value=None`,
  `provenance=None`. The extractor returns UNKNOWN for every field it can't ground in text.
- **EXTRACTED vs INFERRED.** A value read verbatim is `EXTRACTED`; a value derived from evidence
  (country India from a detected Indian city) is `INFERRED` — never conflated, never presented as
  something the page literally said.
- **The future real LLM inherits the same contract in text** (`prompts.py`): never fabricate,
  quote the snippet, return UNKNOWN, treat page content as data (ignore embedded instructions).

## Package

```
app/discovery/ai/
  models.py       ExtractedField/Provenance, AIExtraction (16 fields), AIClassification,
                  DiscoveryConfidence, ValidationResult, SourceClass (14 classes)
  extractor.py    AIExtractor ABC + MockAIExtractor (deterministic, provenance-bearing)
  classifier.py   AIClassifier ABC + MockAIClassifier (14-class labelling with reasons)
  validator.py    validate() — off-topic + insufficient-evidence rejection gate
  confidence.py   compute_confidence() — the realized, explainable Confidence Engine
  pipeline.py     AIDiscoveryPipeline — deterministic-first orchestration → Discovery Inbox
  prompts.py      system + extraction + classification prompt templates for a FUTURE LLM
  interfaces.py   Gemini/OpenAI AIExtractor seams — interface only, NotImplementedError
  store.py        AIExtractionStore (ABC + InMemory + SQLite) — full provenance audit trail
```

## Deterministic-first philosophy

AI is the **last resort**, not the default. The pipeline first runs deterministic extraction (D1
`detect_feeds` + D2 `analyze_frameworks`). If structured event data is present, D1/D2 already
understand the page and D4 **defers** (`DETERMINISTIC_SUFFICIENT`, no AI call). AI runs only for
pages where deterministic extraction is not confident. Why this ordering:

- **Cheaper & exact.** Deterministic parsing is free and precise; a real LLM call costs tokens,
  latency, and quota. Never pay for AI when a regex already knows the answer.
- **More trustworthy.** Structured data (a JSON-LD `Event`) is authoritative; AI reading prose is
  a best effort. Prefer the authoritative source; `merge_extractions` even lets deterministic
  fields override AI ones (method → HYBRID).
- **Smaller attack surface.** Fewer AI calls means fewer chances for hallucination or
  prompt-injection from page content.

## Confidence Engine

Every prior phase deferred a "final confidence score." D4 computes it — `compute_confidence`
combines four signal families into an explainable `DiscoveryConfidence`:

| Component | Weight | Source |
|---|---|---|
| deterministic | 0.30 | strength of D1/D2 structured extraction |
| ai | 0.30 | mean confidence of AI-extracted known fields |
| structured | 0.25 | was structured event data present? |
| search | 0.15 | D3 search ranking (if search-discovered) |

Crucially, **absent signal families are excluded (None), not scored as zero**. A prose page
understood only by AI has no deterministic or structured signal — that absence is *why* AI ran, so
it must not be penalized for it. Weights renormalize over the components actually present. Example
from the live spike (a prose university page, search rank 1): `ai=0.85×w0.67 + search=1.00×w0.33 =
0.90`. Every component's score, weight, and detail are returned — nothing opaque.

## Validator (the safety gate)

Before a page can become a candidate it must pass `validate()`:

- **Hard rejects (always):** tourism, travel, shopping, weddings, politics, religion, pornography,
  gambling — never professional-tech-event sources.
- **Soft rejects (unless strong tech signal):** entertainment, concerts, sports, festivals — these
  legitimately co-occur with tech events (a "Python festival", a "sports-tech hackathon"), so they
  reject only when there is no overriding technology evidence. This is "require explicit supporting
  evidence" working in the positive direction.
- **Insufficient evidence:** a page with no technology, event-type, or community signal is rejected
  — D4 returns UNKNOWN rather than admit a guessed candidate.

Rejected pages never enter the inbox; their reasons are explainable and saved to the audit store.

## Extended Discovery Inbox (additive)

`FeedType.AI_EXTRACTED` marks an AI-understood source. The candidate carries the distilled verdict:
`discovered_by="ai"`, `discovery_confidence` (the Confidence Engine total), `classification` (the
primary class). The **full** provenance-bearing record — all 16 fields with snippets, the ranked
classification, the confidence breakdown, the validation verdict — lives in the `AIExtractionStore`
keyed by url, so the candidate stays lean and nothing is opaque. SQLite persists the candidate
verdict in an additive `ai_data` column (migration-guarded, non-breaking).

## Live demonstration (mock, no network)

`spikes/d4_ai_extraction.py` — prose pages D1/D2 provably can't parse, plus off-topic noise:

```
● university tech club (prose)   D1 feeds=—  D2 embedded_events=0  → ai_accepted
  org=IIT Bombay CSE | city=Mumbai | tech=[AI, Kubernetes, Python] | event_type=[hackathon, workshop]
  class=tech  confidence=0.90
● company dev-events (prose)     D1 feeds=—  D2 embedded_events=0  → ai_accepted (conf 0.85)
● community blog (prose)         D1 feeds=—  D2 embedded_events=0  → ai_accepted (conf 0.73)
● STRUCTURED page                D1 feeds=[jsonld_event]           → deterministic_sufficient (AI skipped)
● concert                        → ai_rejected: entertainment (no overriding tech signal): 'movie'
● shopping                       → ai_rejected: shopping: 'sale'
● travel                         → ai_rejected: tourism: 'tourism'

Inbox candidates (discovered_by=ai): 3   ·   audit records (incl. rejects): 6
provenance(technologies): 'Artificial Intelligence, Kubernetes, Python' — matched catalog tech taxonomy
```

Note the deterministic-first gate firing (the JSON-LD page skips AI entirely) and every accepted
field being traceable to a source snippet.

## Testing

`tests/test_ai_discovery.py` — **15 deterministic tests, no network**: extraction (fields +
provenance), never-fabricate (UNKNOWN, no guessing), partial extraction, INFERRED-vs-EXTRACTED,
classification (tech + labels, non-tech), validator (off-topic + insufficient evidence + soft
override), confidence (combine/normalize, absent=excluded), deterministic-first deferral,
end-to-end accept/reject, and SQLite provenance round-trip. Full backend suite: **439 tests**.

## Future Gemini integration

`interfaces.py` fixes the seam: `GeminiAIExtractor` / `OpenAIAIExtractor` are `AIExtractor`
subclasses whose `extract()` currently raises `NotImplementedError`. A later phase implements the
call using `prompts.py` (system prompt = the never-fabricate contract), the app's existing Gemini
model (`gemini-flash-lite-latest`), `temperature=0` for determinism, and a strict JSON response
schema — with an **anti-fabrication post-check**: drop any returned field whose `source_snippet`
is not actually found in the page. The pipeline, validator, confidence engine, and store are
unchanged — only the extractor swaps. `MockAIExtractor` already exercises the exact contract, so
tests stay green.

## Critical self-review

**What is honestly true**
- The safety model is structural: no value can exist without a source snippet, UNKNOWN is a real
  outcome, and the deterministic-first gate provably fires (the JSON-LD page skips AI). Every
  accepted field in the spike traces to text.

**Where it is weak / what a real LLM changes**
1. **The "AI" is a heuristic mock.** `MockAIExtractor` is regex/keyword matching, not language
   understanding. It will miss paraphrase ("our fortnightly gathering of Pythonistas"), implicit
   cities, and org names not in an "organized by" pattern — exactly the prose-comprehension a real
   LLM provides. D4's architecture, contracts, and tests are real; the *understanding* is mocked.
2. **Heuristics can still under- or over-fire.** The mock extracts `organization` only from an
   explicit "organized by …" phrase (it correctly returned UNKNOWN before a case-insensitivity fix,
   proving the never-guess default) — a real page states organizers a hundred other ways. Curated
   community/platform/state lists are India-tuned and finite.
3. **Confidence is a heuristic blend, not calibrated.** The weights (0.30/0.30/0.25/0.15) and the
   0.4 acceptance threshold are reasoned defaults, not empirically tuned against labeled outcomes.
   `mean_confidence()` averages field confidences that are themselves hand-set constants.
4. **The validator is keyword-based.** It can be evaded by an off-topic page that avoids the trigger
   words, or mis-fire on a legitimate page that quotes them. Soft/hard split mitigates but doesn't
   eliminate this; semantic rejection needs the real model.
5. **Provenance integrity for a real LLM is not yet enforced in code.** The anti-fabrication
   snippet-check is specified (docs + prompt) but only implemented once `GeminiAIExtractor` exists;
   the mock is trivially honest because it only ever copies real substrings.
6. **No cross-page understanding.** D4 reads one page at a time; it can't yet combine an "about"
   page + an "events" page into one source profile.

## Where autonomous discovery / onboarding begins (NOT this phase)

D4 completes *understanding*. It still stops at the Discovery Inbox with `status=NEW` — a human/
later phase decides onboarding. Turning confident candidates into live providers automatically
(auto-onboarding), or letting the engine chase its own frontier without supervision, is the next
phase and requires explicit approval.

---

**Status:** D4 complete. Additive; frozen contracts untouched; 439 tests green; deterministic-first,
provenance-bearing, discovery-only, stops at the Discovery Inbox. **Stopping here — automatic
provider onboarding / autonomous discovery NOT started.**
