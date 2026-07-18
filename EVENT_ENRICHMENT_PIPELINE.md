# Event Enrichment Pipeline (Phase 5A)

The flow that turns a normalized event into an AI-understood object and makes it queryable by
similarity. Code: `backend/app/enrichment/`.

## Flow

```
Normalized Event  (from the frozen Repository)
   ▼  Topic Extraction        → topics[]          (taxonomy regex over title + description)
   ▼  Technology Extraction   → technologies[]    (taxonomy regex)
   ▼  Skill Extraction        → skills[]          (topics + event format)
   ▼  Audience Detection      → audiences[]       (topics + category + difficulty)
   ▼  Difficulty              → difficulty        (signal words + category prior)
   ▼  Career Relevance        → careers[]         (topics → careers)
   ▼  Summary                 → summary           (deterministic template)
   ▼  Metadata Store          → EventEnrichment persisted (separate from Event, by key)
   ▼  Event Similarity        → related events    (topic/tech/skill overlap + category + community)
```

`DeterministicEnricher.enrich(key, event)` runs steps 1–7 (order-preserving, so output is
deterministic); `EnrichmentPipeline` runs it across the catalog, persists into the
`EnrichmentStore`, and exposes `similarity()`.

## Running it

- **`pipeline.run(repo)`** — enrich the whole active catalog from the Repository.
- **`pipeline.enrich_events(events, graph=…)`** — enrich a specific set (used by tests + when
  the caller already has the entity graph).
- **`pipeline.store.get(key)`** — the `EventEnrichment` for one event.
- **`pipeline.similarity().similar_to(key, limit=…)`** — related events, best-first.

It reads the frozen Repository (and builds/borrows the Phase-3F entity graph for community-
aware similarity); it writes only into its own `EnrichmentStore`. No provider, search
component, or repository is aware of it.

## Example (real event)

Input: *"Hands-on GenAI Workshop: Building LLM apps with LangChain"* (workshop; description
"Learn prompt engineering and deploy on AWS with Python.")

```
topics       : [LLMs, Generative AI]
technologies : [Python, AWS, LangChain]
skills       : [Prompt Engineering, AI Engineering, Hands-on Building]
audiences    : [Developers, Researchers, Students]
difficulty   : beginner
careers      : [AI Engineer]
summary      : "A beginner-level workshop on LLMs, Generative AI featuring Python, AWS,
                LangChain, aimed at Developers, Researchers, in Bangalore."
```

## Determinism

Every stage is a pure function of the event text (+ category). Taxonomies are ordered lists,
so extraction output order is fixed. `test_enrichment.py` asserts exact topic/tech/skill/
audience/career/summary outputs and that `enrich()` is idempotent — no network, no LLM, no
randomness.

## Where the LLM plugs in

The pipeline takes an `Enricher`. Swapping `DeterministicEnricher` for a future `LLMEnricher`
(or wrapping the two as validate→retry→fallback) changes one constructor argument — the
pipeline, store, similarity, and everything frozen are untouched. See
[AI_EVENT_UNDERSTANDING.md](AI_EVENT_UNDERSTANDING.md).

## Reproduce

```
PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m spikes.m5a_enrichment
```
